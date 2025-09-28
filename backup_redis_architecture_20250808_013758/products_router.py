# src/api/routers/products_router.py
"""
Products Router - Endpoints para gestión de productos
====================================================

Router que maneja endpoints relacionados con productos,
incluyendo integración con sistema de inventario.

Author: Technical Team
Version: 1.0.0
"""

import logging
import time
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

# Imports del sistema
from src.api.security_auth import get_api_key
from src.api.core.store import get_shopify_client
from src.api.inventory.inventory_service import create_inventory_service, InventoryService
from src.api.inventory.availability_checker import create_availability_checker

# from src.api.core.redis_client import RedisClient
from src.api.core.redis_config_fix import PatchedRedisClient as RedisClient

logger = logging.getLogger(__name__)

import asyncio
from src.api.core.product_cache import ProductCache

# Modelos Pydantic para respuestas
class ProductResponse(BaseModel):
    """Modelo de respuesta para productos individuales"""
    id: str
    title: str
    description: Optional[str] = None
    price: Optional[float] = None
    currency: str = "USD"
    image_url: Optional[str] = None
    category: Optional[str] = None
    
    # Campos de inventario
    availability: str = "available"
    in_stock: bool = True
    stock_quantity: int = 0
    inventory_status: str = "available"
    market_availability: Dict[str, bool] = {}
    low_stock_warning: bool = False
    estimated_restock: Optional[str] = None
    inventory_last_updated: Optional[float] = None

class ProductListResponse(BaseModel):
    """Modelo de respuesta para lista de productos"""
    products: List[ProductResponse]
    total: int
    page: int
    limit: int
    has_next: bool
    market_id: str
    inventory_summary: Dict[str, Any] = {}

# Router
router = APIRouter(prefix="/v1", tags=["Products"])

# Variables globales para servicios
_inventory_service: Optional[InventoryService] = None
_availability_checker = None
# ProductCache singleton
_product_cache: Optional[ProductCache] = None

def get_inventory_service() -> InventoryService:
    """Factory para obtener InventoryService singleton"""
    global _inventory_service
    if _inventory_service is None:
        try:
            # Intentar usar Redis si está disponible
            # redis_client = RedisClient() if hasattr(RedisClient, '__call__') else None
            redis_client = RedisClient(use_validated_config=True)
            logger.info("✅ InventoryService inicializado con Redis validado")
            _inventory_service = create_inventory_service(redis_client)        
        except Exception as e:
            logger.warning(f"Redis no disponible, InventoryService en modo fallback: {e}")
            _inventory_service = create_inventory_service(None)
    return _inventory_service

def get_availability_checker():
    """Factory para obtener AvailabilityChecker singleton"""
    global _availability_checker
    if _availability_checker is None:
        inventory_service = get_inventory_service()
        _availability_checker = create_availability_checker(inventory_service)
    return _availability_checker

def get_product_cache() -> ProductCache:
    """🚀 Factory para obtener ProductCache singleton"""
    global _product_cache
    if _product_cache is None:
        try:
            # Obtener dependencias
            shopify_client = get_shopify_client()
            
            # Intentar usar Redis si está disponible
            # try:
            #     redis_client = RedisClient() if hasattr(RedisClient, '__call__') else None
            #     if redis_client and hasattr(redis_client, 'connected') and redis_client.connected:
            #         logger.info("✅ ProductCache inicializado con Redis")
            #     else:
            #         redis_client = None
            #         logger.info("⚠️ ProductCache inicializado sin Redis (fallback mode)")
            # except Exception:
            #     redis_client = None
            #     logger.warning("Redis no disponible, usando ProductCache sin Redis")
            try:
                redis_client = RedisClient(use_validated_config=True)
                logger.info("✅ ProductCache inicializado con Redis validado")
            except Exception as e:
                redis_client = None
                logger.warning(f"Redis no disponible, ProductCache en (fallback mode): {e}")

            # Crear ProductCache con configuración optimizada
            _product_cache = ProductCache(
                redis_client=redis_client,
                local_catalog=None,
                shopify_client=shopify_client,
                product_gateway=None,
                ttl_seconds=900,  # 15 minutos (optimizado)
                prefix="products_v2:"
            )
            
            logger.info("✅ ProductCache singleton creado exitosamente")
            
        except Exception as e:
            logger.error(f"❌ Error creando ProductCache: {e}")
            _product_cache = None
            
    return _product_cache

@router.get(
    "/products/",
    response_model=ProductListResponse,
    summary="Obtener lista de productos",
    description="Obtiene lista paginada de productos con información de inventario incluida"
)
async def get_products(
    limit: int = Query(default=10, ge=1, le=100, description="Número máximo de productos a retornar"),
    page: int = Query(default=1, ge=1, description="Página de resultados"),
    market_id: str = Query(default="US", description="ID del mercado para verificar disponibilidad"),
    include_inventory: bool = Query(default=True, description="Incluir información de inventario"),
    category: Optional[str] = Query(default=None, description="Filtrar por categoría"),
    available_only: bool = Query(default=False, description="Solo productos disponibles"),
    api_key: str = Depends(get_api_key)
):
    """
    Obtener lista de productos con información de inventario.
    
    Este endpoint:
    1. Obtiene productos desde Shopify
    2. Enriquece con información de inventario
    3. Filtra por disponibilidad si se requiere
    4. Retorna resultados paginados
    """
    try:
        start_time = time.time()
        logger.info(f"Getting products: limit={limit}, page={page}, market={market_id}")
        
        # 1. Obtener productos desde Shopify
        shopify_client = get_shopify_client()
        if not shopify_client:
            # Fallback con productos simulados si no hay Shopify
            # products = await _get_sample_products(limit, page)
            products = await _get_sample_products(limit, page)
        else:
            # Calcular offset para paginación
            offset = (page - 1) * limit
            products = await _get_shopify_products(shopify_client, limit, offset, category)
        
        if not products:
            return ProductListResponse(
                products=[],
                total=0,
                page=page,
                limit=limit,
                has_next=False,
                market_id=market_id,
                inventory_summary={}
            )
        
        # 2. Enriquecer con información de inventario si se requiere
        if include_inventory:
            inventory_service = get_inventory_service()
            enriched_products = await inventory_service.enrich_products_with_inventory(
                products, market_id
            )
        else:
            enriched_products = products
        
        # 3. Filtrar por disponibilidad si se requiere
        if available_only:
            availability_checker = get_availability_checker()
            enriched_products = await availability_checker.filter_available_products(
                enriched_products, market_id
            )
        
        # 4. Convertir a modelos de respuesta
        product_responses = []
        for product in enriched_products[:limit]:  # Asegurar límite
            try:
                product_response = ProductResponse(
                    id=str(product.get("id", "")),
                    title=product.get("title", ""),
                    description=product.get("description", ""),
                    price=float(product.get("price", 0)) if product.get("price") else None,
                    currency=product.get("currency", "USD"),
                    image_url=product.get("image_url") or product.get("featured_image"),
                    category=product.get("category") or product.get("product_type"),
                    
                    # Campos de inventario
                    availability=product.get("availability", "available"),
                    in_stock=product.get("in_stock", True),
                    stock_quantity=product.get("stock_quantity", 10),
                    inventory_status=product.get("inventory_status", "available"),
                    market_availability=product.get("market_availability", {market_id: True}),
                    low_stock_warning=product.get("low_stock_warning", False),
                    estimated_restock=product.get("estimated_restock"),
                    inventory_last_updated=product.get("inventory_last_updated")
                )
                product_responses.append(product_response)
            except Exception as e:
                logger.warning(f"Error processing product {product.get('id')}: {e}")
                continue
        
        # 5. Generar resumen de inventario
        inventory_summary = {}
        if include_inventory and product_responses:
            inventory_service = get_inventory_service()
            # Crear diccionario de inventario para el resumen
            inventory_dict = {
                p.id: type('InventoryInfo', (), {
                    'status': type('Status', (), {'value': p.inventory_status})(),
                    'available_quantity': p.stock_quantity
                })()
                for p in product_responses
            }
            inventory_summary = inventory_service.get_market_availability_summary(inventory_dict)
        
        # 6. Determinar si hay página siguiente
        has_next = len(enriched_products) > limit
        
        # 7. Crear respuesta final
        response = ProductListResponse(
            products=product_responses,
            total=len(product_responses),
            page=page,
            limit=limit,
            has_next=has_next,
            market_id=market_id,
            inventory_summary=inventory_summary
        )
        
        execution_time = (time.time() - start_time) * 1000
        logger.info(f"✅ Products endpoint: {len(product_responses)} products, {execution_time:.1f}ms")
        
        return response
        
    except Exception as e:
        logger.error(f"Error in get_products: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving products: {str(e)}"
        )

@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Obtener producto específico",
    description="Obtiene información detallada de un producto específico con datos de inventario"
)
async def get_product(
    product_id: str,
    market_id: str = Query(default="US", description="ID del mercado"),
    include_inventory: bool = Query(default=True, description="Incluir información de inventario"),
    api_key: str = Depends(get_api_key)
):
    """
    Obtener información detallada de un producto específico.
    """
    try:
        logger.info(f"Getting product {product_id} for market {market_id}")
        
        # 1. Obtener producto desde Shopify
        shopify_client = get_shopify_client()
        if not shopify_client:
            # Fallback con producto simulado
            product = await _get_sample_product(product_id)
        else:
            product = await _get_shopify_product(shopify_client, product_id)
        
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found"
            )
        
        # 2. Enriquecer con información de inventario
        if include_inventory:
            inventory_service = get_inventory_service()
            enriched_products = await inventory_service.enrich_products_with_inventory(
                [product], market_id
            )
            enriched_product = enriched_products[0] if enriched_products else product
        else:
            enriched_product = product
        
        # 3. Crear respuesta
        product_response = ProductResponse(
            id=str(enriched_product.get("id", product_id)),
            title=enriched_product.get("title", ""),
            description=enriched_product.get("description", ""),
            price=float(enriched_product.get("price", 0)) if enriched_product.get("price") else None,
            currency=enriched_product.get("currency", "USD"),
            image_url=enriched_product.get("image_url") or enriched_product.get("featured_image"),
            category=enriched_product.get("category") or enriched_product.get("product_type"),
            
            # Campos de inventario
            availability=enriched_product.get("availability", "available"),
            in_stock=enriched_product.get("in_stock", True),
            stock_quantity=enriched_product.get("stock_quantity", 10),
            inventory_status=enriched_product.get("inventory_status", "available"),
            market_availability=enriched_product.get("market_availability", {market_id: True}),
            low_stock_warning=enriched_product.get("low_stock_warning", False),
            estimated_restock=enriched_product.get("estimated_restock"),
            inventory_last_updated=enriched_product.get("inventory_last_updated")
        )
        
        logger.info(f"✅ Product {product_id}: {product_response.availability}")
        return product_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting product {product_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving product: {str(e)}"
        )

# Funciones helper para obtener productos

async def _get_shopify_products(
    shopify_client, 
    limit: int, 
    offset: int = 0, 
    category: Optional[str] = None
) -> List[Dict]:
    """
    🚀 UPGRADED: Obtener productos usando ProductCache avanzado con market awareness
    """
    try:
        start_time = time.time()
        cache = get_product_cache()
        
        if not cache:
            # Fallback a shopify directo si ProductCache no está disponible
            logger.warning("⚠️ ProductCache not available, falling back to direct Shopify")
            return await _get_shopify_products_direct(shopify_client, limit, offset, category)
        
        # Calcular página para ProductCache
        page = (offset // limit) + 1
        market_id = "US"  # Default, podría extraerse del contexto
        
        logger.info(f"🚀 UPGRADED: Obteniendo productos con ProductCache - limit={limit}, page={page}, market={market_id}")
        
        # Estrategia 1: Intentar obtener productos populares del mercado
        try:
            popular_products = await cache.get_popular_products(market_id, limit * 2)
            logger.info(f"Estrategia 1")
            if popular_products:
                cached_products = []
                for product_id in popular_products[:limit]:
                    product = await cache.get_product(product_id)
                    if product:
                        # Filtrar por categoría si se especifica
                        if not category or product.get("category") == category or product.get("product_type") == category:
                            cached_products.append(product)
                        
                        if len(cached_products) >= limit:
                            break
                
                if len(cached_products) >= limit // 2:
                    response_time = (time.time() - start_time) * 1000
                    logger.info(f"✅ ProductCache hit: {len(cached_products)} productos en {response_time:.1f}ms")
                    return cached_products[:limit]
        
        except Exception as e:
            logger.warning(f"⚠️ Popular products strategy failed: {e}")
        
        # Estrategia 2: Fallback a Shopify con ProductCache
        if shopify_client:
            products = await _get_shopify_products_direct(shopify_client, limit, offset, category)
            # products = Productos reales de Shopify o productos de muestra si falla o depasa el timeout=10.0
           
            # Precargar productos en cache de forma asíncrona
            if products:
                product_ids = [str(p.get("id", "")) for p in products if p.get("id")]
                if product_ids:
                    logger.info(f"Pre-cargando en el router {len(product_ids)} en Estrategia 2 ")
                    asyncio.create_task(cache.preload_products(product_ids[:10]))
            
            response_time = (time.time() - start_time) * 1000
            logger.info(f"✅ UPGRADED: Productos obtenidos en {response_time:.1f}ms - {len(products)} productos")
            return products
        
        else:
            # Estrategia 3: Productos de muestra
            logger.info(f"Estrategia 3")
            return await _get_sample_products(limit, page, category)
        
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        logger.error(f"❌ UPGRADED: Error después de {response_time:.1f}ms: {e}")
        return await _get_sample_products(limit, offset // limit + 1, category)
    
    except Exception as e:
        logger.error(f"❌ Error obteniendo productos de Shopify: {e}")
        logger.info("🔄 Usando productos de muestra como fallback")
        # Fallback a productos simulados solo en caso de error
        return await _get_sample_products(limit, offset // limit + 1, category)


async def _get_shopify_products_direct(
    shopify_client, 
    limit: int, 
    offset: int = 0, 
    category: Optional[str] = None
) -> List[Dict]:
    """Obtener productos directamente de Shopify (mantiene lógica original)"""
    try:
        if not shopify_client:
            return await _get_sample_products(limit, offset // limit + 1, category)
        
        start_time = time.time()
        
        def fetch_shopify_sync():
            try:
                all_shopify_products = shopify_client.get_products()
                if not all_shopify_products:
                    return []
                
                normalized_products = []
                for shopify_product in all_shopify_products[:200]:
                    try:
                        variants = shopify_product.get('variants', [])
                        first_variant = variants[0] if variants else {}
                        images = shopify_product.get('images', [])
                        image_url = images[0].get('src') if images else None
                        
                        normalized_product = {
                            "id": str(shopify_product.get('id')),
                            "title": shopify_product.get('title', ''),
                            "description": shopify_product.get('body_html', ''),
                            "price": float(first_variant.get('price', 0)) if first_variant.get('price') else 0.0,
                            "currency": "USD",
                            "featured_image": image_url,
                            "image_url": image_url,
                            "product_type": shopify_product.get('product_type', ''),
                            "category": shopify_product.get('product_type', ''),
                            "vendor": shopify_product.get('vendor', ''),
                            "handle": shopify_product.get('handle', ''),
                            "sku": first_variant.get('sku', ''),
                            "inventory_quantity": first_variant.get('inventory_quantity', 0),
                        }
                        
                        normalized_products.append(normalized_product)
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Error normalizing product: {e}")
                        continue
                
                return normalized_products
                
            except Exception as e:
                logger.error(f"❌ Error fetching from Shopify: {e}")
                return []
        
        # Ejecutar en thread pool con timeout
        products = await asyncio.wait_for(
            asyncio.to_thread(fetch_shopify_sync),
            timeout=10.0
        )
        
        if products:
            # Filtrar por categoría
            if category:
                products = [
                    p for p in products 
                    if p.get("category", "").lower() == category.lower() or 
                       p.get("product_type", "").lower() == category.lower()
                ]
            
            # Aplicar paginación
            start_idx = offset
            end_idx = start_idx + limit
            paginated_products = products[start_idx:end_idx]
            
            response_time = (time.time() - start_time) * 1000
            logger.info(f"✅ Shopify direct: {len(paginated_products)} productos en {response_time:.1f}ms")
            
            return paginated_products
        
        else:
            return await _get_sample_products(limit, offset // limit + 1, category)
    
    except asyncio.TimeoutError:
        logger.error("❌ Shopify timeout - using fallback")
        return await _get_sample_products(limit, offset // limit + 1, category)
    except Exception as e:
        logger.error(f"❌ Error in Shopify direct: {e}")
        return await _get_sample_products(limit, offset // limit + 1, category)
    

async def _get_sample_products(limit: int, page: int = 1, category: Optional[str] = None) -> List[Dict]:
    """Generar productos de ejemplo para testing"""
    products = [
        {
            "id": f"prod_{i:03d}",
            "title": f"Producto Ejemplo {i}",
            "description": f"Descripción del producto ejemplo número {i}",
            "price": 25.99 + (i * 5.0),
            "currency": "USD",
            "featured_image": f"https://example.com/image_{i}.jpg",
            "product_type": "clothing" if i % 2 == 0 else "accessories",
            "category": "clothing" if i % 2 == 0 else "accessories"
        }
        for i in range(1, 51)  # 50 productos de ejemplo
    ]
    
    # Filtrar por categoría si se especifica
    if category:
        products = [p for p in products if p.get("category") == category]
    
    # Paginación
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    
    return products[start_idx:end_idx]    

async def _get_sample_product(product_id: str) -> Optional[Dict]:
    """Obtener producto de ejemplo específico"""
    try:
        # Extraer número del ID
        if product_id.startswith("prod_"):
            num = int(product_id.split("_")[1])
        else:
            num = 1
        
        return {
            "id": product_id,
            "title": f"Producto Ejemplo {num}",
            "description": f"Descripción detallada del producto ejemplo número {num}",
            "price": 25.99 + (num * 5.0),
            "currency": "USD",
            "featured_image": f"https://example.com/image_{num}.jpg",
            "product_type": "clothing" if num % 2 == 0 else "accessories",
            "category": "clothing" if num % 2 == 0 else "accessories"
        }
    except:
        return {
            "id": product_id,
            "title": "Producto Ejemplo",
            "description": "Descripción de ejemplo",
            "price": 29.99,
            "currency": "USD",
            "featured_image": "https://example.com/image.jpg",
            "product_type": "clothing",
            "category": "clothing"
        }
    
async def _get_shopify_product(shopify_client, product_id: str) -> Optional[Dict]:
    """
    Obtener producto específico REAL desde Shopify
    
    Esta función busca un producto específico por ID en los productos de Shopify
    """
    try:
        logger.info(f"🔍 Buscando producto específico ID: {product_id}")
        
        # Obtener todos los productos (en un sistema real, usarías el endpoint específico)
        all_products = shopify_client.get_products()
        
        if not all_products:
            logger.warning("⚠️ No se obtuvieron productos de Shopify")
            return await _get_sample_product(product_id)
        
        # Buscar el producto específico
        for shopify_product in all_products:
            if str(shopify_product.get('id')) == str(product_id):
                logger.info(f"✅ Producto encontrado: {shopify_product.get('title')}")
                
                # Normalizar el producto (misma lógica que _get_shopify_products)
                variants = shopify_product.get('variants', [])
                first_variant = variants[0] if variants else {}
                images = shopify_product.get('images', [])
                image_url = images[0].get('src') if images else None
                
                return {
                    "id": str(shopify_product.get('id')),
                    "title": shopify_product.get('title', ''),
                    "description": shopify_product.get('body_html', ''),
                    "price": float(first_variant.get('price', 0)) if first_variant.get('price') else 0.0,
                    "currency": "USD",
                    "featured_image": image_url,
                    "image_url": image_url,
                    "product_type": shopify_product.get('product_type', ''),
                    "category": shopify_product.get('product_type', ''),
                    "vendor": shopify_product.get('vendor', ''),
                    "handle": shopify_product.get('handle', ''),
                    "sku": first_variant.get('sku', ''),
                    "inventory_quantity": first_variant.get('inventory_quantity', 0),
                }
        
        # Si no se encuentra el producto
        logger.warning(f"⚠️ Producto ID {product_id} no encontrado en Shopify")
        return await _get_sample_product(product_id)
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo producto {product_id} de Shopify: {e}")
        return await _get_sample_product(product_id)
    

# FUNCIÓN ADICIONAL: Verificar conexión con Shopify
async def debug_shopify_connection(shopify_client) -> Dict:
    """
    Función de debugging para verificar la conexión con Shopify
    """
    try:
        if not shopify_client:
            return {
                "status": "error",
                "message": "Shopify client no disponible",
                "details": "El cliente de Shopify no fue inicializado correctamente"
            }
        
        # Intentar obtener el conteo de productos
        product_count = shopify_client.get_product_count()
        
        # Intentar obtener una muestra pequeña de productos
        sample_products = shopify_client.get_products()
        
        return {
            "status": "success",
            "message": "Conexión con Shopify exitosa",
            "details": {
                "shop_url": shopify_client.shop_url,
                "api_url": shopify_client.api_url,
                "product_count": product_count,
                "sample_products_fetched": len(sample_products) if sample_products else 0,
                "first_product_title": sample_products[0].get('title') if sample_products else None,
                "access_token_prefix": shopify_client.access_token[:4] + "..." if shopify_client.access_token else "No token"
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error conectando con Shopify: {str(e)}",
            "details": {
                "shop_url": shopify_client.shop_url if shopify_client else "No client",
                "error_type": type(e).__name__
            }
        }
# ========================================================================
# 🔍 DEBUG ENDPOINTS - TEMPORALES PARA DEBUGGING
# ========================================================================
@router.get("/debug/shopify", tags=["Debug"])
async def debug_shopify_connection_endpoint():
     """Endpoint para debugging de conexión Shopify"""
     shopify_client = get_shopify_client()
     return await debug_shopify_connection(shopify_client)

# ========================================================================
@router.get(
    "/debug/headers",
    summary="🔍 Debug Headers",
    description="Endpoint temporal para debugging de headers de autenticación",
    tags=["Debug"]
)
async def debug_headers(request: Request):
    """
    🔍 Endpoint debug para investigar problemas de autenticación.
    
    Este endpoint NO requiere autenticación y muestra todos los headers
    recibidos para diagnosticar problemas con X-API-Key.
    """
    import time
    
    return {
        "timestamp": time.time(),
        "method": request.method,
        "url": str(request.url),
        "client_host": request.client.host if request.client else "unknown",
        "headers": {
            # Convertir headers a dict para JSON serialization
            key: value for key, value in request.headers.items()
        },
        "specific_headers": {
            "x_api_key": request.headers.get("X-API-Key"),
            "x_api_key_present": "X-API-Key" in request.headers,
            "authorization": request.headers.get("Authorization"),
            "content_type": request.headers.get("Content-Type"),
            "user_agent": request.headers.get("User-Agent"),
            "origin": request.headers.get("Origin"),
            "referer": request.headers.get("Referer")
        },
        "header_analysis": {
            "total_headers_count": len(request.headers),
            "x_api_key_length": len(request.headers.get("X-API-Key", "")),
            "expected_api_key": "2fed9999056fab6dac5654238f0cae1c",
            "api_key_matches": request.headers.get("X-API-Key") == "2fed9999056fab6dac5654238f0cae1c"
        }
    }

@router.get(
    "/debug/auth-test",
    summary="🔐 Debug Auth Test",
    description="Endpoint que requiere autenticación para testing",
    tags=["Debug"]
)
async def debug_auth_test(
    request: Request,
    api_key: str = Depends(get_api_key)
):
    """
    🔐 Endpoint debug que SÍ requiere autenticación.
    
    Si este endpoint funciona, significa que la autenticación está OK.
    Si falla, podemos comparar con /debug/headers para ver qué cambió.
    """
    import time
    
    return {
        "timestamp": time.time(),
        "status": "authenticated_successfully",
        "message": "✅ Authentication working correctly!",
        "api_key_validated": api_key[:10] + "...",  # Solo primeros 10 chars por seguridad
        "headers_received": {
            key: value for key, value in request.headers.items()
        },
        "auth_flow": "Headers → FastAPI → APIKeyHeader → get_api_key() → SUCCESS"
    }

@router.get(
    "/debug/load-test",
    summary="🚀 Debug Load Test",
    description="Endpoint optimizado para load testing debugging",
    tags=["Debug"]
)
async def debug_load_test(
    request: Request,
    api_key: str = Depends(get_api_key),
    test_id: Optional[str] = Query(None, description="ID del test para tracking")
):
    """
    🚀 Endpoint específico para debugging de load testing.
    
    Retorna información mínima para reducir overhead durante tests de carga.
    """
    import time
    
    return {
        "test_id": test_id or "no_id",
        "timestamp": time.time(),
        "status": "ok",
        "auth": "valid",
        "api_key_prefix": api_key[:8],
        "response_time_start": time.time()
    }

# 🚀 ProductCache Management Endpoints

@router.get("/debug/product-cache", tags=["ProductCache"])
async def debug_product_cache():
    """Debug endpoint para ProductCache statistics"""
    try:
        cache = get_product_cache()
        
        if not cache:
            return {
                "timestamp": time.time(),
                "cache_available": False,
                "error": "ProductCache not initialized",
                "fallback_mode": True
            }
        
        stats = cache.get_stats()
        
        return {
            "timestamp": time.time(),
            "cache_available": True,
            "cache_stats": stats,
            "cache_health": "healthy" if stats["hit_ratio"] > 0.3 else "warming_up",
            "recommendations": {
                "warm_up_needed": stats["total_requests"] < 20,
                "hit_ratio_status": "excellent" if stats["hit_ratio"] > 0.7 else "good" if stats["hit_ratio"] > 0.4 else "needs_improvement"
            }
        }
    except Exception as e:
        return {
            "timestamp": time.time(),
            "cache_available": False,
            "error": str(e),
            "fallback_mode": True
        }

@router.post("/cache/warm-up", tags=["ProductCache"])
async def warm_up_product_cache(
    market_priorities: List[str] = Query(default=["US", "ES", "MX"], description="Markets to warm up"),
    max_products: int = Query(default=50, description="Max products per market"),
    api_key: str = Depends(get_api_key)
):
    """Warm up ProductCache intelligently"""
    try:
        cache = get_product_cache()
        
        if not cache:
            return {
                "success": False,
                "error": "ProductCache not available",
                "timestamp": time.time()
            }
        
        result = await cache.intelligent_cache_warmup(
            market_priorities=market_priorities,
            max_products_per_market=max_products
        )
        
        return {
            "success": True,
            "warm_up_result": result,
            "timestamp": time.time()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": time.time()
        }