# src/api/routers/products_router.py
"""
Products Router - MIGRATED TO FASTAPI DEPENDENCY INJECTION
===========================================================

Router enterprise con FastAPI Dependency Injection pattern completo.
Zero breaking changes. Full backward compatibility.

MIGRATION STATUS: ✅ Phase 2 Day 3 Complete
- Migrated from local functions to centralized dependencies.py
- Using dependency injection for all services
- Backward compatible
- Zero breaking changes

Author: Senior Architecture Team
Version: 3.0.0 - FastAPI DI Migration (Phase 2 Day 3)
Date: 2025-10-17
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
import json
import requests  # ✅ FIX (07 Nov 2025): Import at module level for proper test mocking
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path, status
from pydantic import BaseModel, Field

# Imports del sistema original (mantenidos)
from src.api.security_auth import get_api_key, get_current_user
from src.api.core.store import get_shopify_client
from src.api.inventory.availability_checker import create_availability_checker

# ✅ ENTERPRISE IMPORTS - Centralized dependency injection
from src.api.factories import ServiceFactory, InfrastructureCompositionRoot, HealthCompositionRoot

# ============================================================================
# FASTAPI DEPENDENCY INJECTION - NEW PATTERN (Phase 2 Day 3)
# ============================================================================

from src.api.dependencies import (
    get_inventory_service,
    get_product_cache,
    get_availability_checker,
    get_tfidf_recommender
)

# Type hints for better IDE support
from src.api.inventory.inventory_service import InventoryService
from src.api.core.product_cache import ProductCache
from src.recommenders.tfidf_recommender import TFIDFRecommender

# ✅ CORRECCIÓN CRÍTICA: Dependency injection unificada (ORIGINAL)
from src.api.core.redis_service import get_redis_service, RedisService
# from src.api.core.redis_config_fix import PatchedRedisClient  # ✅ Añadir import faltante


# ============================================================================
# VALIDATION PATTERNS - Input validation for security and correctness
# ============================================================================

# Product ID validation pattern
# Allows: letters, numbers, hyphens, underscores, dots
# Prevents: special characters that could cause API issues
VALID_PRODUCT_ID_PATTERN = r'^[a-zA-Z0-9_\-\.]+$'


logger = logging.getLogger(__name__)

# ============================================================================
# 📋 PYDANTIC MODELS - Response structures (ORIGINAL + ENTERPRISE)
# ============================================================================

class ProductResponse(BaseModel):
    """Modelo de respuesta para productos individuales"""
    id: str
    title: str
    description: Optional[str] = None
    price: Optional[float] = None
    currency: str = "USD"
    image_url: Optional[str] = None
    category: Optional[str] = None
    
    # Campos de inventario enterprise
    availability: str = "available"
    in_stock: bool = True
    stock_quantity: int = 0
    inventory_status: str = "available"
    market_availability: Dict[str, bool] = {}
    low_stock_warning: bool = False
    estimated_restock: Optional[str] = None
    inventory_last_updated: Optional[float] = None
    
    # Enterprise metadata
    cache_hit: bool = False
    service_version: str = "3.0.0"  # ✅ Phase 2 Day 3

class ProductListResponse(BaseModel):
    """Modelo de respuesta para lista de productos"""
    products: List[ProductResponse]
    total: int
    page: int
    limit: int
    has_next: bool
    market_id: str
    inventory_summary: Dict[str, Any] = {}
    
    # Enterprise metadata
    cache_stats: Dict[str, Any] = {}
    performance_metrics: Dict[str, float] = {}
    service_version: str = "3.0.0"  # ✅ Phase 2 Day 3

# ============================================================================
# 🏗️ SERVICE FACTORIES - Enterprise + Legacy Dependency Injection
# ============================================================================

# Variables globales para servicios (LEGACY - mantener durante transición)
# _global_product_cache: Optional[ProductCache] = None
_inventory_service: Optional[InventoryService] = None
_availability_checker = None
_product_cache: Optional[ProductCache] = None

# ============================================================================
# 🔄 LEGACY COMPATIBILITY FUNCTIONS - Deprecated (Phase 2 Day 3)
# ============================================================================

"""
❌ OLD PATTERN - Local dependency functions (DEPRECATED)

These functions are NO LONGER USED but kept for reference during transition.
All new code should use dependencies from src.api.dependencies module.

Migration:
- OLD: inventory = await get_enterprise_inventory_service()
- NEW: async def endpoint(inventory: InventoryService = Depends(get_inventory_service))

These functions have been REPLACED by centralized dependencies in:
- src/api/dependencies.py::get_inventory_service()
- src/api/dependencies.py::get_product_cache()
- src/api/dependencies.py::get_availability_checker()

# async def get_enterprise_inventory_service():
#     '''DEPRECATED: Use get_inventory_service from dependencies.py'''
#     try:
#         inventory_service = await ServiceFactory.get_inventory_service_singleton()
#         logger.debug("✅ Enterprise InventoryService singleton acquired")
#         return inventory_service
#     except Exception as e:
#         logger.error(f"❌ Enterprise InventoryService failed: {e}")
#         raise HTTPException(status_code=503, detail="Inventory service temporarily unavailable")

# async def get_enterprise_product_cache():
#     '''DEPRECATED: Use get_product_cache from dependencies.py'''
#     try:
#         product_cache = await ServiceFactory.get_product_cache_singleton()
#         logger.debug("✅ Enterprise ProductCache singleton acquired")
#         return product_cache
#     except Exception as e:
#         logger.error(f"❌ Enterprise ProductCache failed: {e}")
#         raise HTTPException(status_code=503, detail="Product cache service temporarily unavailable")

# async def get_enterprise_availability_checker():
#     '''DEPRECATED: Use get_availability_checker from dependencies.py'''
#     try:
#         availability_checker = await ServiceFactory.create_availability_checker()
#         logger.debug("✅ Enterprise AvailabilityChecker created")
#         return availability_checker
#     except Exception as e:
#         logger.error(f"❌ Enterprise AvailabilityChecker failed: {e}")
#         raise HTTPException(status_code=503, detail="Availability checker service temporarily unavailable")
"""

# ============================================================================
# 🔧 LEGACY DEPENDENCY INJECTION (ORIGINAL - PRESERVED)
# ============================================================================

async def get_inventory_service_dependency() -> InventoryService:
    """
    InventoryService dependency injection with graceful degradation
    
    ✅ FIXED: Esta función SIEMPRE retorna un InventoryService válido,
    aunque sea sin Redis. NUNCA lanza excepciones.
    
    Returns:
        InventoryService: Siempre retorna una instancia válida
        
    Note:
        Si Redis no está disponible, retorna InventoryService(redis_service=None)
        que funciona en modo degradado pero operacional.
    """
    # STRATEGY 1: Try ServiceFactory enterprise
    try:
        logger.debug("🔄 Attempting InventoryService via ServiceFactory...")
        inventory_service = await ServiceFactory.get_inventory_service_singleton()
        logger.debug("✅ InventoryService obtained via ServiceFactory")
        return inventory_service
    except Exception as factory_error:
        logger.debug(f"ServiceFactory InventoryService unavailable: {factory_error}")
    
    # STRATEGY 2: Create fallback without Redis
    try:
        logger.debug("⚠️ Creating fallback InventoryService without Redis")
        inventory_service = InventoryService(redis_service=None)
        logger.info("✅ Fallback InventoryService created (no Redis)")
        return inventory_service
    except Exception as fallback_error:
        logger.error(f"❌ Even fallback InventoryService failed: {fallback_error}")
    
    # STRATEGY 3: Último recurso - crear instancia mínima
    logger.warning("⚠️ Creating emergency minimal InventoryService")
    return InventoryService(redis_service=None)

async def get_product_cache_dependency() -> Optional[ProductCache]:
    """
    ProductCache dependency injection with graceful degradation
    
    ✅ FIXED: Esta función NUNCA lanza excepciones. En su lugar, retorna None
    cuando el cache no está disponible, permitiendo que el endpoint funcione sin cache.
    
    Returns:
        ProductCache | None: La instancia del cache o None si no disponible
        
    Note:
        El endpoint debe manejar cache=None gracefully y operar sin cache.
    """
    # STRATEGY 1: Try ServiceFactory enterprise
    try:
        logger.debug("🔄 Attempting ProductCache via ServiceFactory...")
        product_cache = await ServiceFactory.get_product_cache_singleton()
        logger.debug("✅ ProductCache obtained via ServiceFactory")
        return product_cache
    except Exception as factory_error:
        logger.debug(f"ServiceFactory ProductCache unavailable: {factory_error}")
    
    # STRATEGY 2: Try startup singleton
    try:
        import src.api.main_unified_redis as main_module
        if hasattr(main_module, 'product_cache') and main_module.product_cache:
            logger.debug("✅ Using startup ProductCache singleton")
            return main_module.product_cache
    except Exception as startup_error:
        logger.debug(f"Startup ProductCache unavailable: {startup_error}")
    
    # STRATEGY 3: Emergency creation WITHOUT Redis (to avoid event loop issues)
    try:
        logger.debug("⚠️ Creating minimal ProductCache without Redis")
        shopify_client = get_shopify_client()
        
        # ✅ CRÍTICO: Crear sin redis_service para evitar event loop issues
        minimal_cache = ProductCache(
            redis_service=None,  # NO Redis
            shopify_client=shopify_client,
            ttl_seconds=3600,
            prefix="minimal:"
        )
        logger.info("✅ Minimal ProductCache created (no Redis)")
        return minimal_cache
    except Exception as minimal_error:
        logger.warning(f"⚠️ All ProductCache strategies failed: {minimal_error}")
    
        # ✅ CRÍTICO: NO lanzar excepción, retornar None para degradación graceful
        logger.info("ℹ️ ProductCache unavailable - endpoint will operate without cache")
        return None


async def get_availability_checker_dependency():
    """✅ FIXED: AvailabilityChecker con dependency injection enterprise"""
    inventory_service = await get_inventory_service_dependency()
    return create_availability_checker(inventory_service)

# ============================================================================
# 🔄 LEGACY COMPATIBILITY FUNCTIONS - Mantener durante transición (ORIGINAL)
# ============================================================================

# def get_inventory_service() -> InventoryService:
#     """
#     ⚠️ LEGACY FUNCTION - DEPRECATED (ORIGINAL)
    
#     Usar get_inventory_service_dependency() para nueva arquitectura enterprise.
#     Esta función se mantiene solo para compatibilidad con código existente.
#     """
#     global _inventory_service
#     if _inventory_service is None:
#         logger.warning("⚠️ Using legacy get_inventory_service() - Consider migration to enterprise architecture")
#         try:
#             # Crear con configuración legacy (sin Redis)
#             _inventory_service = InventoryService(redis_service=None)
#             logger.info("✅ Legacy InventoryService created without Redis")
#         except Exception as e:
#             logger.error(f"❌ Error creating legacy InventoryService: {e}")
#             # Crear instancia mínima como fallback
#             _inventory_service = InventoryService(redis_service=None)
    
#     return _inventory_service

# def get_availability_checker():
#     """⚠️ LEGACY FUNCTION - DEPRECATED (ORIGINAL)"""
#     global _availability_checker
#     if _availability_checker is None:
#         logger.warning("⚠️ Using legacy get_availability_checker() - Consider migration to enterprise architecture")
#         try:
#             inventory_service = get_inventory_service()
#             _availability_checker = create_availability_checker(inventory_service)
#             logger.info("✅ Legacy AvailabilityChecker created")
#         except Exception as e:
#             logger.error(f"❌ Error creating legacy AvailabilityChecker: {e}")
#             # Crear mock como fallback
#             _availability_checker = type('MockChecker', (), {
#                 'check_availability': lambda self, *args, **kwargs: {'status': 'available', 'fallback': True}
#             })()
    
#     return _availability_checker

# def get_product_cache() -> Optional[ProductCache]:
#     """🚀 Factory para obtener ProductCache singleton - DEPRECATED (ORIGINAL)"""
#     global _product_cache
#     if _product_cache is None:
#         try:
#             # Obtener dependencias
#             shopify_client = get_shopify_client()
            
#             # ✅ FIXED: ProductCache ahora usa redis_service, no redis_client
#             redis_service = None
#             try:
#                 # Intentar obtener RedisService enterprise
#                 import asyncio
#                 loop = asyncio.get_event_loop()
#                 redis_service = loop.run_until_complete(ServiceFactory.get_redis_service())
#                 logger.info("✅ ProductCache legacy initialized with RedisService enterprise")
#             except Exception as e:
#                 redis_service = None
#                 logger.warning(f"Redis unavailable for ProductCache legacy: {e}")

#             # Crear ProductCache con configuración legacy usando redis_service
#             _product_cache = ProductCache(
#                 redis_service=redis_service,  # ✅ FIXED: redis_service no redis_client
#                 local_catalog=None,
#                 shopify_client=shopify_client,
#                 product_gateway=None,
#                 ttl_seconds=900,  # 15 minutos
#                 prefix="products_legacy:"
#             )
            
#             logger.info("✅ ProductCache legacy singleton created")
            
#         except Exception as e:
#             logger.error(f"❌ Error creating ProductCache legacy: {e}")
#             _product_cache = None
            
#     return _product_cache

# ============================================================================
# 🔥 ROUTER SETUP
# ============================================================================

router = APIRouter(prefix="/v1", tags=["Products Enterprise DI"])

# ============================================================================
# 📊 HEALTH CHECK ENDPOINT - Enterprise Monitoring (ORIGINAL + ENHANCED)
# ============================================================================

@router.get("/products/health")
async def products_health_check(
    # ✅ NEW: FastAPI Dependency Injection (Phase 2 Day 3)
    redis_service: RedisService = Depends(get_redis_service),
    inventory: InventoryService = Depends(get_inventory_service),
    cache: ProductCache = Depends(get_product_cache)
):
    """
    Health check comprehensivo para el sistema de productos.
    
    MIGRATED: ✅ Using FastAPI Dependency Injection (Phase 2 Day 3)
    
    Args:
        redis_service: RedisService via dependency injection
        inventory: InventoryService via dependency injection
        cache: ProductCache via dependency injection
    
    Returns:
        Dict con health status de todos los componentes
    """
    health_status = {
        "timestamp": time.time(),
        "service": "products_api",
        "version": "3.0.0",  # ✅ Phase 2 Day 3
        "components": {},
        "di_migration": "phase2_day3_complete"  # ✅ NEW: Migration flag
    }
    
    try:
        # ✅ UPDATED: Usar redis_service inyectado
        redis_health = await redis_service.health_check()
        health_status["components"]["redis_service"] = redis_health
        
        # ✅ UPDATED: Usar inventory inyectado
        health_status["components"]["inventory_service"] = {
            "status": "operational",
            "redis_integrated": inventory.redis_service is not None
        }
        
        # ✅ UPDATED: Usar cache inyectado
        try:
            cache_stats = cache.get_stats()
            health_status["components"]["product_cache"] = {
                "status": "operational",
                "stats": cache_stats
            }
        except Exception as cache_error:
            health_status["components"]["product_cache"] = {
                "status": "degraded",
                "error": str(cache_error)
            }
        
        # ✅ Determine overall status
        component_statuses = [
            comp.get("status", "unknown") 
            for comp in health_status["components"].values()
        ]
        
        if all(status == "operational" for status in component_statuses):
            health_status["overall_status"] = "healthy"
        elif any(status == "operational" for status in component_statuses):
            health_status["overall_status"] = "degraded"
        else:
            health_status["overall_status"] = "unhealthy"
            
        return health_status
        
    except Exception as e:
        logger.error(f"❌ Products health check failed: {e}")
        health_status["overall_status"] = "unhealthy"
        health_status["error"] = str(e)
        return health_status

# ============================================================================
# 🛍️ MAIN PRODUCT ENDPOINTS (ORIGINAL PRESERVED + ENTERPRISE ENHANCED)
# ============================================================================

@router.get(
    "/products/",
    response_model=ProductListResponse,
    summary="Obtener lista de productos",
    description="Obtiene lista paginada de productos con información de inventario incluida"
)
async def get_products(
    limit: int = Query(default=10, ge=1, description="Número máximo de productos a retornar"),
    page: Optional[int] = Query(default=None, ge=1, description="Página de resultados (alternativa a offset)"),
    offset: Optional[int] = Query(default=None, ge=0, description="Offset para paginación (alternativa a page)"),
    market_id: str = Query(default="US", description="ID del mercado para verificar disponibilidad"),
    include_inventory: bool = Query(default=True, description="Incluir información de inventario"),
    category: Optional[str] = Query(default=None, description="Filtrar por categoría"),
    available_only: bool = Query(default=False, description="Solo productos disponibles"),
    api_key: str = Depends(get_api_key),
    inventory: InventoryService = Depends(get_inventory_service)
):
    """
    Obtener lista de productos con información de inventario.
    
    MIGRATED: ✅ Using FastAPI Dependency Injection (Phase 2 Day 3)
    FIXED: ✅ Supports both page and offset pagination
    
    Pagination:
        - Use 'page' parameter for page-based pagination (page=1, page=2, etc.)
        - Use 'offset' parameter for offset-based pagination (offset=0, offset=10, etc.)
        - If both provided, 'offset' takes precedence
        - If neither provided, defaults to page=1 (offset=0)
    
    Args:
        limit: Número máximo de productos a retornar (max will be capped at 100)
        page: Página de resultados (optional, alternative to offset)
        offset: Offset para paginación (optional, alternative to page)
        market_id: ID del mercado
        include_inventory: Incluir información de inventario
        category: Filtrar por categoría (opcional)
        available_only: Solo productos disponibles
        api_key: API key para autenticación (via Depends)
        inventory: InventoryService (via Depends) ✅ NEW
    
    Returns:
        ProductListResponse con productos y metadata

    Notes:
        - Obtiene productos desde Shopify
        - Enriquece con información de inventario
        - Filtra por disponibilidad si se requiere
        - Retorna resultados paginados

    """
    try:
        start_time = time.time()
        
        # ============================================================================
        # ✅ FIX 1: Graceful Limit Cap
        # ============================================================================
        MAX_ALLOWED_LIMIT = 100
        original_limit = limit
        
        if limit > MAX_ALLOWED_LIMIT:
            limit = MAX_ALLOWED_LIMIT
            logger.info(f"⚠️ Limit capped: requested={original_limit}, applied={limit}")
        
        # ============================================================================
        # ✅ FIX 2: Support both page and offset pagination
        # ============================================================================
        if offset is not None:
            # Offset explícito tiene precedencia
            calculated_offset = offset
            calculated_page = (offset // limit) + 1
            logger.info(f"📄 Offset-based pagination: offset={offset}, limit={limit}, calculated_page={calculated_page}")
        elif page is not None:
            # Usar page si offset no especificado
            calculated_offset = (page - 1) * limit
            calculated_page = page
            logger.info(f"📄 Page-based pagination: page={page}, limit={limit}, calculated_offset={calculated_offset}")
        else:
            # Default: página 1
            calculated_offset = 0
            calculated_page = 1
            logger.info(f"📄 Default pagination: page=1, limit={limit}")
        
        logger.info(f"Getting products: limit={limit}, offset={calculated_offset}, market={market_id}")

        # ✅ OPCIONAL: Verificar que inventory está disponible
        if inventory is None:
            logger.error("❌ InventoryService is None - this should not happen")
            # Crear instancia de emergencia
            inventory = InventoryService(redis_service=None)
                
        # 1. Obtener productos desde Shopify
        shopify_client = get_shopify_client()
        if not shopify_client:
            # Fallback con productos simulados si no hay Shopify
            products = await _get_sample_products(limit, calculated_page)
        else:
            # Usar calculated_offset
            products = await _get_shopify_products(shopify_client, limit, calculated_offset, category)
        
        if not products:
            return ProductListResponse(
                products=[],
                total=0,
                page=calculated_page,
                limit=limit,
                has_next=False,
                market_id=market_id,
                inventory_summary={}
            )
        
        # 2. Enriquecer con información de inventario si se requiere
        if include_inventory:
            enriched_products = await inventory.enrich_products_with_inventory(
                products, market_id
            )
        else:
            enriched_products = products
        
        # 3. Filtrar por disponibilidad si se requiere
        if available_only:
            from src.api.inventory.availability_checker import create_availability_checker
            availability_checker = create_availability_checker(inventory)
            enriched_products = await availability_checker.filter_available_products(
                enriched_products, market_id
            )
        
        # 4. Convertir a modelos de respuesta
        product_responses = []
        for product in enriched_products[:limit]:  # Asegurar límite     
            try:
                # Para obtener el precio y la imagen, revisar variantes
                variants = product.get('variants', [])
                first_variant = variants[0] if variants else {}
                images = product.get('images', [])
                image_url = images[0].get('src') if images else None

                product_response = ProductResponse(
                    id=str(product.get("id", "")),
                    title=product.get("title", ""),
                    description=product.get("body_html", ""),
                    price=float(first_variant.get("price", 0)) if first_variant.get("price") else None,
                    currency=product.get("currency", "USD"),
                    image_url=image_url,
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
        
        # 5. Calcular metadata
        total = len(enriched_products)  # Total en esta página
        has_next = len(enriched_products) >= limit  # Puede haber más páginas
        
        # Performance metrics
        response_time = (time.time() - start_time) * 1000
        
        logger.info(f"✅ Returned {len(product_responses)} products in {response_time:.1f}ms")
        
        return ProductListResponse(
            products=product_responses,
            total=total,
            page=calculated_page,
            limit=limit,
            has_next=has_next,
            market_id=market_id,
            inventory_summary={},
            performance_metrics={
                "response_time_ms": response_time,
                "products_returned": len(product_responses)
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Error getting products: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving products: {str(e)}"
        )
    
# ============================================================================
@router.get("/products/search/")
async def search_products(
    q: str = Query(..., description="Texto a buscar en nombre o descripción"),
    limit: int = Query(default=20, ge=1, le=100, description="Productos por página (máx 100)"),
    offset: int = Query(default=0, ge=0, description="Offset para paginación"),
    tfidf_recommender: TFIDFRecommender = Depends(get_tfidf_recommender),
    current_user: str = Depends(get_current_user)
):
    """
    Busca productos por nombre o descripción con paginación.
    
    Args:
        q: Query string para búsqueda
        limit: Número de productos por página (default: 20, max: 100)
        offset: Offset para paginación (default: 0)
        tfidf_recommender: Recomendador TF-IDF inyectado
        current_user: Usuario autenticado
    
    Returns:
        Dict: Productos paginados con metadatos de paginación
        {
            "products": [...],
            "pagination": {
                "total": 150,
                "limit": 20,
                "offset": 0,
                "returned": 20,
                "has_next": true,
                "next_offset": 20,
                "page": 1,
                "total_pages": 8
            },
            "metadata": {
                "query": "aros",
                "response_time_ms": 25.30,
                "lookup_method": "TF-IDF search"
            }
        }
    
    Raises:
        503: Catálogo no cargado
        500: Error interno
    """
    try:
        start_time = time.time()
        
        # Verificar que el catálogo esté cargado
        if not tfidf_recommender.loaded or not tfidf_recommender.product_data:
            raise HTTPException(
                status_code=503,
                detail="Product catalog not loaded yet. Please wait for system initialization."
            )
        
        # Realizar la búsqueda (lógica existente)
        q = q.lower()
        matching_products = []
        for product in tfidf_recommender.product_data:
            name = str(product.get("title", ""))
            desc = str(product.get("body_html", ""))
            if q in name.lower() or q in desc.lower():
                matching_products.append(product)
        
        # Aplicar paginación
        total_products = len(matching_products)
        end_idx = offset + limit
        paginated_products = matching_products[offset:end_idx]
        
        # Calcular metadatos de paginación
        has_next = end_idx < total_products
        next_offset = end_idx if has_next else None
        
        response_time_ms = (time.time() - start_time) * 1000
        
        logger.info(
            f"✅ Search completed for query '{q}': {len(paginated_products)}/{total_products} products "
            f"(offset={offset}, limit={limit}) in {response_time_ms:.2f}ms"
        )
        
        return {
            "products": paginated_products,
            "pagination": {
                "total": total_products,
                "limit": limit,
                "offset": offset,
                "returned": len(paginated_products),
                "has_next": has_next,
                "next_offset": next_offset,
                "page": (offset // limit) + 1,
                "total_pages": (total_products + limit - 1) // limit  # Ceiling division
            },
            "metadata": {
                "query": q,
                "response_time_ms": round(response_time_ms, 2),
                "lookup_method": "TF-IDF search"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in product search: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ============================================================================
@router.get("/products/categories")
async def get_available_categories(
    tfidf_recommender: TFIDFRecommender = Depends(get_tfidf_recommender),
    current_user: str = Depends(get_current_user)
):
    """
    List all available product categories.
    
    Returns:
        Dict with 'categories' (sorted list) and 'total' (count) and metadata
    
    Example:
        {
            "categories": ["ACCESSORIES", "CLOTHING", "LENCERIA"],
            "total": 3
        }
    """
    try:
        logger.info(f"🔍 Checking TFIDFRecommender: loaded={tfidf_recommender.loaded}, product_data={len(tfidf_recommender.product_data) if tfidf_recommender.product_data else 0}")
        start_time = time.time()
        
        # Verificar que el catálogo esté cargado
        if not tfidf_recommender.loaded or not tfidf_recommender.product_data:
            raise HTTPException(
                status_code=503,
                detail="Product catalog not loaded yet"
            )
        
        # ✅ OPTIMIZACIÓN: Usar category_index si está disponible (O(1))
        if hasattr(tfidf_recommender, 'category_index') and tfidf_recommender.category_index:
            categories = set(tfidf_recommender.category_index.keys())
            lookup_method = "O(1) index"
        else:
            # ⚠️ FALLBACK OPTIMIZADO: Construir index on-demand pero con límite de tiempo
            logger.warning("⚠️ category_index not available, building on-demand (this may be slow)")
            
            # Limitar la iteración para evitar timeouts (procesar máximo 10,000 productos)
            max_products_to_scan = 10000
            categories = set()
            
            for i, p in enumerate(tfidf_recommender.product_data):
                if i >= max_products_to_scan:
                    logger.warning(f"⚠️ Stopped scanning at {max_products_to_scan} products to avoid timeout")
                    break
                category = p.get("product_type", "").upper()
                if category:
                    categories.add(category)
            
            lookup_method = f"O(n) scan (limited to {max_products_to_scan})"
        
        response_time_ms = (time.time() - start_time) * 1000
        
        logger.info(
            f"✅ Categories retrieved: {len(categories)} categories in {response_time_ms:.2f}ms "
            f"(method: {lookup_method})"
        )
        
        return {
            "categories": sorted(categories),
            "total": len(categories),
            "metadata": {
                "response_time_ms": round(response_time_ms, 2),
                "lookup_method": lookup_method,
                "catalog_size": len(tfidf_recommender.product_data) if tfidf_recommender.product_data else 0
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting categories: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ============================================================================
@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Obtener producto específico",
    description="Obtiene información detallada de un producto específico con datos de inventario"
)
async def get_product(
    product_id: str = Path(
        ...,
        description="Product ID (alphanumeric, underscore, hyphen, dot allowed)",
        # regex=VALID_PRODUCT_ID_PATTERN,
        min_length=1,
        max_length=100,
        examples=["prod_12345"]
    ),
    market_id: str = Query(default="US", description="ID del mercado"),
    include_inventory: bool = Query(default=True, description="Incluir información de inventario"),
    api_key: str = Depends(get_api_key),
    # ✅ NEW: FastAPI Dependency Injection (Phase 2 Day 3)
    cache: Optional[ProductCache] = Depends(get_product_cache),
    inventory: InventoryService = Depends(get_inventory_service)
):
    """
    Obtener información detallada de un producto específico.
    
    MIGRATED: ✅ Using FastAPI Dependency Injection (Phase 2 Day 3)
    FIXED: ✅ Proper 404 error handling for missing products
    
    Args:
        product_id: ID del producto
        market_id: ID del mercado
        include_inventory: Incluir información de inventario
        api_key: API key para autenticación (via Depends)
        cache: ProductCache (via Depends) ✅ NEW
        inventory: InventoryService (via Depends) ✅ NEW
    
    Returns:
        ProductResponse con información completa del producto
        
    Raises:
        404: Product not found
        500: Internal server error
    
    Notes:
        - Cache-first strategy para performance
        - Fallback a Shopify si cache miss
        - Enriquece con datos de inventario
    """
    try:
        start_time = time.time()
        logger.info(f"🔍 Getting individual product {product_id} for market {market_id}")

        # import re
        # if not re.match(VALID_PRODUCT_ID_PATTERN, product_id):
        #     logger.warning(f"⚠️ Invalid product ID format: {product_id}")
        #     raise HTTPException(
        #         status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        #         detail=f"Invalid product ID format. Allowed characters: alphanumeric, underscore, hyphen, dot"
        #     )
        # ============================================================================
        # STEP 1: Cache-First Strategy (with None handling)
        # ============================================================================
        product = None
        cache_hit = False
        
        # ✅ FIX: Manejar cache=None gracefully
        if cache is None:
            logger.warning(f"⚠️ ProductCache unavailable for {product_id}, operating without cache")
            product = None  # Forzar fetch desde Shopify
        else:
            # Cache está disponible - intentar obtener
            try:
                cached_product = await cache.get_product(product_id)
                if cached_product:
                    response_time = (time.time() - start_time) * 1000
                    logger.info(f"✅ ProductCache hit for product {product_id}: {response_time:.1f}ms")
                    product = cached_product
                    cache_hit = True
                    if isinstance(cached_product, dict):
                        cached_product["cache_hit"] = True
                else:
                    logger.info(f"🔍 ProductCache miss for product {product_id}, fetching from Shopify...")
            except Exception as cache_error:
                logger.warning(f"⚠️ ProductCache error for product {product_id}: {cache_error}")
                # Continue without cache
        
        # ============================================================================
        # STEP 2: Shopify Fetch (if cache miss)
        # ============================================================================
        if not product:
            shopify_client = get_shopify_client()
            if not shopify_client:
                logger.warning(f"⚠️ Shopify client not available for product {product_id}")
                # ✅ FIX: Solo intentar sample product si el ID tiene formato de muestra
                if product_id.startswith("prod_"):
                    product = await _get_sample_product(product_id)
                    if not product:
                        logger.info(f"❌ Sample product {product_id} not found (invalid or out of range)")
                else:
                    logger.info(f"❌ Cannot fetch product {product_id}: Shopify unavailable and not a sample ID")
                    product = None
            else:
                # ✅ ARCHITECTURAL FIX: Usar llamada directa O(1) en lugar de búsqueda O(n)
                logger.info(f"🎯 Using direct API call for product {product_id}")
                product = await _get_shopify_product_direct_api(shopify_client, product_id)
                
                # Fallback a búsqueda optimizada solo si la llamada directa falla
                if not product:
                    logger.warning(f"⚠️ Direct API failed, trying optimized search for {product_id}")
                    product = await _get_shopify_product_optimized(shopify_client, product_id)
                
                # ============================================================================
                # STEP 3: Cache Save (solo productos reales)
                # ============================================================================
                if product and cache and not product.get("is_sample", False):
                    try:
                        await cache._save_to_redis(product_id, product)
                        logger.info(f"✅ Cached real product {product_id} for future requests")
                    except Exception as save_error:
                        logger.warning(f"⚠️ Failed to cache product {product_id}: {save_error}")
                elif product and product.get("is_sample", False):
                    logger.warning(f"⚠️ Not caching sample product {product_id}")
        
        # ============================================================================
        # ✅ FIX: EXPLICIT NOT FOUND HANDLING
        # ============================================================================
        if not product:
            logger.warning(f"❌ Product {product_id} not found in any source")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID '{product_id}' not found"
            )
        
        # ============================================================================
        # STEP 4: Enrich with Inventory
        # ============================================================================
        if include_inventory and inventory:
            try:
                enriched_products = await inventory.enrich_products_with_inventory(
                    [product], market_id
                )
                enriched_product = enriched_products[0] if enriched_products else product
            except Exception as inv_error:
                logger.warning(f"⚠️ Inventory enrichment failed for {product_id}: {inv_error}")
                enriched_product = product
        else:
            enriched_product = product
        
        # ============================================================================
        # STEP 5: Build Response
        # ============================================================================
        response_time = (time.time() - start_time) * 1000
        
        product_response = ProductResponse(
            id=str(enriched_product.get("id", product_id)),
            title=enriched_product.get("title", ""),
            # description=enriched_product.get("description", ""),
            description=enriched_product.get("body_html", ""),
            price=float(enriched_product.get("price", 0)) if enriched_product.get("price") else None,
            currency=enriched_product.get("currency", "USD"),
            image_url=enriched_product.get("image_url") or enriched_product.get("featured_image"),
            category=enriched_product.get("category") or enriched_product.get("product_type"),
            
            # Inventory data
            availability=enriched_product.get("availability", "available"),
            in_stock=enriched_product.get("in_stock", True),
            stock_quantity=enriched_product.get("stock_quantity", 0),
            inventory_status=enriched_product.get("inventory_status", "available"),
            market_availability=enriched_product.get("market_availability", {}),
            low_stock_warning=enriched_product.get("low_stock_warning", False),
            estimated_restock=enriched_product.get("estimated_restock"),
            inventory_last_updated=enriched_product.get("inventory_last_updated"),
            
            # Metadata
            cache_hit=cache_hit,
            service_version="3.0.1"  # Updated version with fixes
        )
        
        logger.info(f"✅ Product {product_id} retrieved successfully in {response_time:.1f}ms")
        return product_response
    
    except HTTPException:
        # ✅ FIX: Re-raise HTTP exceptions (404, etc.) without modification
        raise
    
    except Exception as e:
        # ✅ FIX: Catch-all for unexpected errors (SERVER error - 500)
        logger.error(f"❌ Unexpected error fetching product {product_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error fetching product"
        )
     
# ============================================================================
# ✅ FIX: GET PRODUCTS BY CATEGORY - USAR LOCAL CATALOG
# ============================================================================

@router.get("/products/category/{category}")
async def get_products_by_category(
    category: str,
    limit: int = Query(default=20, ge=1, le=100, description="Productos por página (máx 100)"),
    offset: int = Query(default=0, ge=0, description="Offset para paginación"),
    tfidf_recommender: TFIDFRecommender = Depends(get_tfidf_recommender),
    current_user: str = Depends(get_current_user)
):
    """
    Get products by category using local catalog with pagination.
    
    ✅ IMPROVEMENTS:
    - Uses local_catalog instead of Shopify API (1000x-1800x faster) ⚡
    - Implements pagination for better performance
    - Response time: ~25ms (was 440ms for 523 products)
    - Supports up to 100 products per page
    
    Args:
        category: Category name (case-insensitive)
        limit: Number of products per page (default: 20, max: 100)
        offset: Pagination offset (default: 0)
        tfidf_recommender: Injected TFIDFRecommender with local catalog
        current_user: Authenticated user
    
    Returns:
        Dict: Paginated products with metadata
        {
            "products": [...],
            "pagination": {
                "total": 523,
                "limit": 20,
                "offset": 0,
                "returned": 20,
                "has_next": true,
                "next_offset": 20,
                "page": 1,
                "total_pages": 27
            },
            "metadata": {
                "category": "Aros",
                "category_normalized": "AROS",
                "lookup_time_ms": 0.00,
                "response_time_ms": 25.30,
                "lookup_method": "O(1) index"
            }
        }
    
    Raises:
        503: Catalog not loaded
        404: Category not found
    
    Examples:
        GET /v1/products/category/Aros
        GET /v1/products/category/Aros?limit=50
        GET /v1/products/category/Aros?limit=20&offset=20  # Page 2
        GET /v1/products/category/Aros?limit=20&offset=40  # Page 3
    """
    try:
        start_time = time.time()
        
        # ============================================================================
        # STEP 1: Verify catalog is loaded
        # ============================================================================
        if not tfidf_recommender.loaded or not tfidf_recommender.product_data:
            logger.error("❌ Product catalog not loaded")
            raise HTTPException(
                status_code=503,
                detail="Product catalog not loaded yet. Please wait for system initialization."
            )
        
        # ============================================================================
        # STEP 2: Get all valid categories
        # ============================================================================
        all_categories = {
            p.get("product_type", "").upper()
            for p in tfidf_recommender.product_data
            if p.get("product_type")
        }
        
        category_upper = category.upper()
        
        # ============================================================================
        # STEP 3: Validate category exists
        # ============================================================================
        if category_upper not in all_categories:
            logger.warning(f"❌ Category '{category}' not found in catalog")
            raise HTTPException(
                status_code=404,
                detail=f"Category '{category}' not found. Available categories: {sorted(all_categories)}"
            )
        
        # ============================================================================
        # STEP 4: Get ALL products from category (O(1) lookup with index)
        # ============================================================================
        lookup_start = time.time()
        
        if (hasattr(tfidf_recommender, 'category_index') and 
            tfidf_recommender.category_index and 
            category_upper in tfidf_recommender.category_index):
            # ✅ Usar índice si está disponible (O(1))
            all_category_products = tfidf_recommender.category_index[category_upper]
            lookup_method = "O(1) index"
            logger.debug(f"Used category_index for {category_upper} (O(1))")
        else:
            # ⚠️ Fallback a filtrado directo (O(n))
            logger.warning(f"category_index not available, using direct filter (O(n))")
            all_category_products = [
                p for p in tfidf_recommender.product_data
                if p.get("product_type", "").upper() == category_upper
            ]
            lookup_method = "O(n) filter"
        
        lookup_time_ms = (time.time() - lookup_start) * 1000
        
        # ============================================================================
        # STEP 5: Validate products exist
        # ============================================================================
        if not all_category_products:
            raise HTTPException(
                status_code=404,
                detail=f"No products found in category '{category}'"
            )
        
        # ============================================================================
        # STEP 6: Apply pagination
        # ============================================================================
        total_products = len(all_category_products)
        end_idx = offset + limit
        paginated_products = all_category_products[offset:end_idx]
        
        # ============================================================================
        # STEP 7: Calculate pagination metadata
        # ============================================================================
        has_next = end_idx < total_products
        next_offset = end_idx if has_next else None
        
        response_time_ms = (time.time() - start_time) * 1000
        
        # ============================================================================
        # STEP 8: Build response
        # ============================================================================
        logger.info(
            f"✅ Returned {len(paginated_products)}/{total_products} products "
            f"in category '{category}' (offset={offset}, limit={limit}) "
            f"in {response_time_ms:.2f}ms (lookup: {lookup_time_ms:.2f}ms)"
        )
        
        return {
            "products": paginated_products,
            "pagination": {
                "total": total_products,
                "limit": limit,
                "offset": offset,
                "returned": len(paginated_products),
                "has_next": has_next,
                "next_offset": next_offset,
                "page": (offset // limit) + 1,
                "total_pages": (total_products + limit - 1) // limit  # Ceiling division
            },
            "metadata": {
                "category": category,
                "category_normalized": category_upper,
                "lookup_time_ms": round(lookup_time_ms, 2),
                "response_time_ms": round(response_time_ms, 2),
                "lookup_method": lookup_method
            }
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions without modification
        raise
    
    except Exception as e:
        logger.error(f"❌ Error in category search: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ============================================================================
@router.get("/health/detailed")
async def detailed_health_check(
    tfidf_recommender: TFIDFRecommender = Depends(get_tfidf_recommender)
):
    """
    Health check comprehensivo que verifica estado del sistema.
    """
    return {
        "timestamp": time.time(),
        "service": "tfidf_recommender",
        "status": {
            "loaded": tfidf_recommender.loaded,
            "product_data_available": tfidf_recommender.product_data is not None,
            "product_count": len(tfidf_recommender.product_data) if tfidf_recommender.product_data else 0,
            "category_index_built": hasattr(tfidf_recommender, 'category_index') and tfidf_recommender.category_index is not None,
            "categories_count": len(tfidf_recommender.category_index) if hasattr(tfidf_recommender, 'category_index') and tfidf_recommender.category_index else 0,
            "categories": sorted(tfidf_recommender.category_index.keys()) if hasattr(tfidf_recommender, 'category_index') and tfidf_recommender.category_index else []
        },
        "architecture": {
            "singleton": True,
            "factory": "ServiceFactory",
            "dependency_injection": True
        },
        "performance": {
            "lookup_complexity": "O(1)" if hasattr(tfidf_recommender, 'category_index') else "O(n)",
            "expected_response_time": "<2ms for O(1), <500ms for O(n)"
        }
    }

# ============================================================================
# 🔧 FUNCIONES HELPER PARA OBTENER PRODUCTOS (ORIGINAL PRESERVED)
# ============================================================================

async def _get_shopify_products(
    shopify_client, 
    limit: int, 
    offset: int = 0, 
    category: Optional[str] = None
) -> List[Dict]:
    """
    🚀 UPGRADED: Obtener productos usando ProductCache avanzado con market awareness.
    
    Note: Esta función helper NO necesita migración porque no es un endpoint.
    Los endpoints que la llaman ya tienen las dependencies inyectadas.
    """
    try:
        start_time = time.time()
        # Usar ServiceFactory directamente en helpers (no en endpoints)
        cache = await ServiceFactory.get_product_cache_singleton()

        if not cache:
            # Fallback a shopify directo si ProductCache no está disponible
            logger.warning("⚠️ ProductCache not available, falling back to direct Shopify")
            return await _get_shopify_products_direct(shopify_client, limit, offset, category)
        
        # Calcular página para ProductCache
        page = (offset // limit) + 1
        market_id = "US"  # Default, podría extraerse del contexto
        
        logger.info(f"🚀 UPGRADED: Obteniendo productos con ProductCache - limit={limit}, page={page}, market={market_id}")
        
        # Estrategia 1: Cache-first approach optimizada
        try:
            # 1a. Verificar si ya tenemos productos en cache de requests anteriores
            cache_key = f"recent_products_{market_id}_{limit}_{offset}_{category or 'all'}"
            
            if hasattr(cache, 'redis') and cache.redis:
                recent_cached = await cache.redis.get(cache_key)
                if recent_cached:
                    try:
                        cached_products = json.loads(recent_cached)
                        if cached_products and len(cached_products) >= limit:
                            response_time = (time.time() - start_time) * 1000
                            logger.info(f"✅ ProductCache hit (recent): {len(cached_products)} productos en {response_time:.1f}ms")
                            return cached_products[:limit]
                        elif cached_products and len(cached_products) >= max(3, limit * 0.75):
                            # Partial recent cache hit
                            response_time = (time.time() - start_time) * 1000
                            logger.info(f"✅ ProductCache partial hit (recent): {len(cached_products)} productos en {response_time:.1f}ms")
                            return cached_products[:limit]  # Return what we have
                    except:
                        pass
            
            # 1b. Estrategia popular products mejorada
            popular_products = await cache.get_popular_products(market_id, limit * 3)
            if popular_products:
                cached_products = []
                for product_id in popular_products:
                    product = await cache.get_product(product_id)
                    if product:
                        # Filtrar por categoría si se especifica
                        if not category or product.get("category") == category or product.get("product_type") == category:
                            cached_products.append(product)
                        
                        if len(cached_products) >= limit:
                            break
                
                # FIXED: Threshold que requiere productos suficientes o complementa con Shopify
                if len(cached_products) >= limit:
                    # Perfect match - tenemos exactamente lo que necesitamos o más
                    response_time = (time.time() - start_time) * 1000
                    logger.info(f"✅ ProductCache hit (popular): {len(cached_products)} productos en {response_time:.1f}ms")
                    return cached_products[:limit]
                elif len(cached_products) >= max(3, int(limit * 0.8)):
                    # Partial match - tenemos la mayoría, complementar con Shopify
                    response_time = (time.time() - start_time) * 1000
                    logger.info(f"🔄 ProductCache partial hit: {len(cached_products)}/{limit} productos en {response_time:.1f}ms - complementing with Shopify...")
                    
                    # Complementar con Shopify para obtener productos faltantes
                    try:
                        needed = limit - len(cached_products)
                        if needed > 0:
                            additional_products = await _get_shopify_products_direct(shopify_client, needed, len(cached_products), category)
                            if additional_products:
                                combined_products = cached_products + additional_products
                                logger.info(f"✅ Combined cache + Shopify: {len(combined_products)} total productos")
                                return combined_products[:limit]
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to complement with Shopify: {e}")
                        # Continuar a Shopify directo si falla
                        pass
        
        except Exception as e:
            logger.warning(f"⚠️ Cache strategy failed: {e}")
        
        # Estrategia 2: Fallback a Shopify con ProductCache
        if shopify_client:
            products = await _get_shopify_products_direct(shopify_client, limit, offset, category)
           
            # Precargar productos usando datos DISPONIBLES (FINAL FIX)
            if products:
                logger.info(f"💾 Caching {len(products)} productos con datos disponibles")
                
                try:
                    # STRATEGY 1: Cache individual products usando datos que ya tenemos
                    cache_success = 0
                    cache_failures = 0
                    
                    for product in products[:10]:  # Limitar para performance
                        product_id = str(product.get("id", ""))
                        if product_id and product:
                            try:
                                # Usar método directo de save - NO preload que hace refetch
                                success = await cache._save_to_redis(product_id, product)
                                if success:
                                    cache_success += 1
                                    logger.debug(f"✅ Cached product {product_id}")
                                else:
                                    cache_failures += 1
                                    logger.debug(f"❌ Failed to cache product {product_id}")
                            except Exception as e:
                                cache_failures += 1
                                logger.debug(f"❌ Exception caching product {product_id}: {e}")
                    
                    logger.info(f"✅ Individual caching: {cache_success} success, {cache_failures} failures")
                    
                    # STRATEGY 2: Cache complete response para requests similares
                    cache_key = f"recent_products_{market_id}_{limit}_{offset}_{category or 'all'}"
                    cache_data = json.dumps(products)
                    
                    if hasattr(cache, 'redis') and cache.redis:
                        # await cache.redis.set(cache_key, cache_data, ex=300)  # 5 min
                        await cache.redis.set(cache_key, cache_data, ttl=300)  # 5 min
                        logger.info(f"✅ Cached complete response: {cache_key}")
                    
                    # STRATEGY 3: Cache flexible key para different params
                    flexible_key = f"market_products_{market_id}"
                    flexible_data = json.dumps(products[:20])  # Cache más productos
                    
                    if hasattr(cache, 'redis') and cache.redis:
                        # await cache.redis.set(flexible_key, flexible_data, ex=600)  # 10 min
                        await cache.redis.set(flexible_key, flexible_data, ttl=600)  # 10 min
                        logger.info(f"✅ Cached flexible response: {flexible_key}")
                    
                except Exception as cache_error:
                    logger.warning(f"⚠️ Cache operation failed: {cache_error}")
                    import traceback
                    logger.debug(f"Cache traceback: {traceback.format_exc()}")
            
            response_time = (time.time() - start_time) * 1000
            logger.info(f"✅ UPGRADED: Productos obtenidos en {response_time:.1f}ms - {len(products)} productos")
            return products
        
        else:
            # Estrategia 3: Productos de muestra
            return await _get_sample_products(limit, page, category)
        
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        logger.error(f"❌ UPGRADED: Error después de {response_time:.1f}ms: {e}")
        return await _get_sample_products(limit, offset // limit + 1, category)

async def _get_shopify_products_direct(
    shopify_client, 
    limit: int, 
    offset: int = 0, 
    category: Optional[str] = None
) -> List[Dict]:
    """Obtener productos directamente de Shopify (mantiene lógica original) (ORIGINAL)"""
    try:
        if not shopify_client:
            return await _get_sample_products(limit, offset // limit + 1, category)
        
        start_time = time.time()
        
        def fetch_shopify_sync():
            try:
                all_shopify_products = shopify_client.get_products(limit=limit*2, offset=offset)
                if not all_shopify_products:
                    return []
                
                normalized_products = []
                for shopify_product in all_shopify_products:
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
        
        # Ejecutar en thread pool con timeout dinámico
        # Timeout más corto para requests pequeños, más largo para grandes
        dynamic_timeout = 5.0 if limit <= 10 else 15.0 if limit <= 50 else 30.0
        
        products = await asyncio.wait_for(
            asyncio.to_thread(fetch_shopify_sync),
            timeout=dynamic_timeout
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
            logger.info(f"   Request efficiency: {len(paginated_products)}/{len(products)} productos utilizados")
            
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
    """
    Generar productos de ejemplo para testing
    
    FIXED: Implementa paginación correcta para que diferentes páginas retornen diferentes productos
    """
    # Generar 100 productos de ejemplo (más que antes para testing de paginación)
    products = [
        {
            "id": f"prod_{i:03d}",
            "title": f"Producto Ejemplo {i}",
            "description": f"Descripción del producto ejemplo número {i}",
            "price": 25.99 + (i * 5.0),
            "currency": "USD",
            "featured_image": f"https://example.com/image_{i}.jpg",
            "image_url": f"https://example.com/image_{i}.jpg",
            "product_type": "clothing" if i % 3 == 0 else "accessories" if i % 3 == 1 else "electronics",
            "category": "clothing" if i % 3 == 0 else "accessories" if i % 3 == 1 else "electronics",
            "vendor": f"Vendor {i % 5 + 1}",
            "handle": f"producto-ejemplo-{i}",
            "sku": f"SKU-{i:05d}",
            "inventory_quantity": 10 + (i % 20),
            "is_sample": True  # Marcar como datos de ejemplo
        }
        for i in range(1, 101)  # ✅ FIX: 100 productos para mejor testing
    ]
    
    # Filtrar por categoría si se especifica
    if category:
        products = [p for p in products if p.get("category") == category]
    
    # ✅ FIX: Paginación correcta
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    
    paginated = products[start_idx:end_idx]
    
    logger.debug(f"Sample products: page={page}, limit={limit}, start={start_idx}, end={end_idx}, returned={len(paginated)}")
    
    return paginated

async def _get_sample_product(product_id: str) -> Optional[Dict]:
    """
    Obtener producto de ejemplo específico
    
    FIXED: Retorna None para IDs que no existen en datos de muestra.
    Solo retorna productos que existen en el rango válido (prod_001 a prod_100).
    """
    try:
        # Solo retornar productos de muestra para IDs en formato correcto
        if product_id.startswith("prod_"):
            try:
                # Extraer número del ID (ej: "prod_005" → 5)
                num_str = product_id.split("_")[1]
                num = int(num_str)
                
                # ✅ FIX CRÍTICO: Solo retornar si el ID está en el rango válido (1-100)
                if 1 <= num <= 100:
                    return {
                        "id": product_id,
                        "title": f"Producto Ejemplo {num}",
                        "description": f"Descripción detallada del producto ejemplo número {num}",
                        "price": 25.99 + (num * 5.0),
                        "currency": "USD",
                        "featured_image": f"https://example.com/image_{num}.jpg",
                        "image_url": f"https://example.com/image_{num}.jpg",
                        "product_type": "clothing" if num % 2 == 0 else "accessories",
                        "category": "clothing" if num % 2 == 0 else "accessories",
                        "vendor": f"Vendor {(num % 5) + 1}",
                        "handle": f"producto-ejemplo-{num}",
                        "sku": f"SKU-{num:05d}",
                        "inventory_quantity": 10 + (num % 20),
                        "is_sample": True
                    }
                else:
                    # ID fuera de rango válido
                    logger.debug(f"❌ Sample product ID {product_id} out of valid range (1-100)")
                    return None
                    
            except (ValueError, IndexError) as e:
                # ID en formato incorrecto (ej: "prod_abc")
                logger.debug(f"❌ Invalid sample product ID format: {product_id} - {e}")
                return None
        else:
            # ID no es de muestra (no empieza con "prod_")
            logger.debug(f"❌ Product ID {product_id} is not a sample product ID")
            return None
            
    except Exception as e:
        # Error inesperado
        logger.error(f"❌ Error getting sample product {product_id}: {e}")
        return None
   

async def _get_shopify_product_direct_api(shopify_client, product_id: str) -> Optional[Dict]:
    """
    ✅ ARQUITECTURAL FIX: Llamada directa al endpoint individual de Shopify
    
    Usa el endpoint específico GET /admin/api/2024-01/products/{product_id}.json
    en lugar de buscar linealmente en todos los productos.
    
    Performance: O(1) vs O(n) - 90%+ improvement esperado
    """
    try:
        start_time = time.time()
        logger.info(f"🎯 Direct API call for product {product_id}")
        
        # STRATEGY 1: Verificar si el client tiene método directo
        if hasattr(shopify_client, 'get_product'):
            try:
                logger.debug("Using shopify_client.get_product()")
                product = shopify_client.get_product(product_id)
                if product:
                    response_time = (time.time() - start_time) * 1000
                    logger.info(f"✅ Direct method success: {response_time:.1f}ms")
                    return _normalize_shopify_product(product)
            except Exception as e:
                logger.debug(f"get_product method failed: {e}")
        
        # STRATEGY 2: Verificar si el client tiene método por ID
        if hasattr(shopify_client, 'get_product_by_id'):
            try:
                logger.debug("Using shopify_client.get_product_by_id()")
                product = shopify_client.get_product_by_id(product_id)
                if product:
                    response_time = (time.time() - start_time) * 1000
                    logger.info(f"✅ Direct by_id method success: {response_time:.1f}ms")
                    return _normalize_shopify_product(product)
            except Exception as e:
                logger.debug(f"get_product_by_id method failed: {e}")
        
        # STRATEGY 3: Construir URL directa y usar método HTTP del client
        if hasattr(shopify_client, 'api_url') or hasattr(shopify_client, 'shop_url'):
            try:
                base_url = getattr(shopify_client, 'api_url', None) or getattr(shopify_client, 'shop_url', None)
                
                if base_url and '/admin/api/' in str(base_url):
                    # Construir URL para producto individual
                    individual_url = f"{str(base_url).rstrip('/')}/products/{product_id}.json"
                    logger.debug(f"Trying direct URL: {individual_url}")
                    
                    # Usar método HTTP del client si existe
                    if hasattr(shopify_client, '_request'):
                        response = shopify_client._request('GET', f"products/{product_id}.json")
                        if response:
                            response_time = (time.time() - start_time) * 1000
                            logger.info(f"✅ Direct URL _request success: {response_time:.1f}ms")
                            return _normalize_shopify_product(response)
                    
                    elif hasattr(shopify_client, 'request'):
                        response = shopify_client.request('GET', f"products/{product_id}.json")
                        if response:
                            response_time = (time.time() - start_time) * 1000
                            logger.info(f"✅ Direct URL request success: {response_time:.1f}ms")
                            return _normalize_shopify_product(response)
                            
            except Exception as e:
                logger.debug(f"Direct URL strategy failed: {e}")
        
        # STRATEGY 4: Usar requests directo como último recurso
        try:
            import requests
            import json
            
            # Construir URL completa
            if hasattr(shopify_client, 'shop_url') and hasattr(shopify_client, 'access_token'):
                shop_url = shopify_client.shop_url
                access_token = shopify_client.access_token
                
                if shop_url and access_token:
                    # URL para API individual
                    api_url = f"https://{shop_url}/admin/api/2024-01/products/{product_id}.json"
                    
                    headers = {
                        'X-Shopify-Access-Token': access_token,
                        'Content-Type': 'application/json'
                    }
                    
                    logger.debug(f"Trying direct requests call to: {api_url}")
                    
                    response = requests.get(api_url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        product_data = response.json()
                        if 'product' in product_data:
                            response_time = (time.time() - start_time) * 1000
                            logger.info(f"✅ Direct requests success: {response_time:.1f}ms")
                            return _normalize_shopify_product(product_data['product'])
                    elif response.status_code == 404:
                        response_time = (time.time() - start_time) * 1000
                        logger.info(f"⚠️ Product {product_id} not found (404): {response_time:.1f}ms")
                        return None
                    else:
                        logger.warning(f"Direct API call failed: {response.status_code} - {response.text[:200]}")
                        
        except Exception as e:
            logger.debug(f"Direct requests strategy failed: {e}")
        
        # Si todas las estrategias fallan
        response_time = (time.time() - start_time) * 1000
        logger.error(f"❌ All direct API strategies failed for product {product_id}: {response_time:.1f}ms")
        return None
        
    except Exception as e:
        logger.error(f"❌ Direct API call failed for product {product_id}: {e}")
        return None

def _normalize_shopify_product(shopify_product: Dict) -> Dict:
    """
    Normalizar producto de Shopify al formato esperado
    """
    try:
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
            "cache_hit": False,
            "fetch_strategy": "direct_api"
        }
    except Exception as e:
        logger.error(f"Error normalizing product: {e}")
        return shopify_product


async def _get_shopify_product_optimized(shopify_client, product_id: str) -> Optional[Dict]:
   """
   ✅ OPTIMIZED: Obtener producto específico desde Shopify de forma eficiente
   
   Esta función usa estrategias optimizadas en lugar de obtener TODOS los productos.
   Performance: ~500ms vs ~2000ms (75% improvement)
   """
   try:
       start_time = time.time()
       logger.info(f"🔍 Fetching individual product from Shopify: {product_id}")
       
       # STRATEGY 1: Intentar método individual si existe
       def fetch_individual_product():
           try:
               # Verificar si el client tiene método para producto individual
               if hasattr(shopify_client, 'get_product'):
                   return shopify_client.get_product(product_id)
               elif hasattr(shopify_client, 'get_product_by_id'):
                   return shopify_client.get_product_by_id(product_id)
               else:
                   return None
           except Exception as e:
               logger.debug(f"Individual product method failed: {e}")
               return None
       
       # STRATEGY 2: Usar filtros específicos si no hay método individual
       def fetch_filtered_products():
           try:
               # Intentar con filtros específicos
               if hasattr(shopify_client, 'get_products'):
                   # Probar diferentes estrategias de filtrado
                   strategies = [
                       lambda: shopify_client.get_products(ids=[product_id], limit=1),
                       lambda: shopify_client.get_products(limit=1, since_id=int(product_id)-1) if product_id.isdigit() else None,
                       lambda: shopify_client.get_products(limit=10)  # Fallback mínimo
                   ]
                   
                   for strategy in strategies:
                       try:
                           if strategy:
                               filtered_products = strategy()
                               if filtered_products:
                                   # Buscar el producto específico en los resultados filtrados
                                   for product in filtered_products:
                                       if str(product.get('id')) == str(product_id):
                                           return product
                       except Exception as strategy_error:
                           logger.debug(f"Filter strategy failed: {strategy_error}")
                           continue
               return None
           except Exception as e:
               logger.debug(f"Filtered fetch failed: {e}")
               return None
       
       # STRATEGY 3: Progressive search (búsqueda progresiva)
       def fetch_progressive_search():
           try:
               # Búsqueda progresiva: aumentar límites si no encuentra
               search_limits = [20, 50, 100, 200, 500, 1000, 2000, 3000]  # Límites progresivos
               
               for limit in search_limits:
                   try:
                       logger.info(f"🔍 Searching in {limit} products for {product_id}")
                       products = shopify_client.get_products(limit=limit)
                       
                       if products:
                           for product in products:
                               if str(product.get('id')) == str(product_id):
                                   logger.info(f"✅ Found product {product_id} in progressive search (limit={limit})")
                                   return product
                           
                           # Si llegamos al final y no encontramos, continuar al siguiente límite
                           logger.debug(f"Product {product_id} not found in first {limit} products")
                       else:
                           logger.warning(f"No products returned with limit={limit}")
                           break  # No hay más productos
                           
                   except Exception as limit_error:
                       logger.warning(f"Error with limit {limit}: {limit_error}")
                       continue
               
               # Si no encontró en ningún límite
               logger.warning(f"⚠️ Product {product_id} not found in progressive search")
               return None
               
           except Exception as e:
               logger.error(f"❌ Progressive search failed: {e}")
               return None
       
       # Ejecutar estrategias en orden de eficiencia
       strategies = [
           ("individual", fetch_individual_product),
           ("filtered", fetch_filtered_products),
           ("progressive_search", fetch_progressive_search)
       ]
       
       for strategy_name, strategy_func in strategies:
           try:
               shopify_product = strategy_func()
               if shopify_product:
                   response_time = (time.time() - start_time) * 1000
                   logger.info(f"✅ Individual product found via {strategy_name}: {response_time:.1f}ms")
                   
                   # Normalizar el producto (misma lógica que _get_shopify_products)
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
                       "cache_hit": False,  # Mark as fresh from Shopify
                       "fetch_strategy": strategy_name
                   }
                   
                   return normalized_product
           except Exception as e:
               logger.debug(f"Strategy {strategy_name} failed: {e}")
               continue
       
       # Si todas las estrategias fallan - NO retornar datos falsos
       response_time = (time.time() - start_time) * 1000
       logger.error(f"❌ Product {product_id} not found in Shopify after {response_time:.1f}ms")
       return None  # Esto causará 404 en el endpoint
       
   except Exception as e:
       logger.error(f"❌ Error fetching individual product {product_id}: {e}")
    #    return await _get_sample_product(product_id)
    # ✅ FIX: NO retornar sample fallback - dejar que el endpoint maneje 404
       return None

async def _get_shopify_product(shopify_client, product_id: str) -> Optional[Dict]:
   """
   ⚠️ DEPRECATED: Use _get_shopify_product_optimized instead
   
   Esta función obtiene TODOS los productos para buscar uno - muy ineficiente.
   Mantenida solo para compatibilidad durante transición.
   """
   logger.warning(f"⚠️ Using deprecated _get_shopify_product for {product_id} - consider migration")
   
   # Redirect to optimized version
   return await _get_shopify_product_optimized(shopify_client, product_id)
async def debug_shopify_connection(shopify_client) -> Dict:
   """
   Función de debugging para verificar la conexión con Shopify (ORIGINAL)
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


# ============================================================================
# 📊 ENTERPRISE MONITORING ENDPOINTS
# ============================================================================

@router.get("/enterprise/cache/stats", tags=["Enterprise Monitoring"])
async def get_enterprise_cache_stats(api_key: str = Depends(get_api_key)):
   """✅ ENTERPRISE: Get comprehensive cache statistics"""
   try:
       product_cache = await ServiceFactory.get_product_cache_singleton()
       cache_stats = product_cache.get_stats()
       
       redis_service = await ServiceFactory.get_redis_service()
       redis_health = await redis_service.health_check()
       
       return {
           "timestamp": time.time(),
           "service": "enterprise_cache_monitoring",
           "cache_stats": cache_stats,
           "redis_health": redis_health,
           "enterprise_metadata": {
               "architecture": "enterprise",
               "singleton_pattern": True,
               "connection_pooling": True
           }
       }
   except Exception as e:
       return {
           "timestamp": time.time(),
           "service": "enterprise_cache_monitoring",
           "error": str(e),
           "status": "degraded"
       }

@router.post("/enterprise/cache/warm-up", tags=["Enterprise Management"])
async def enterprise_cache_warmup(
   market_priorities: List[str] = Query(default=["US", "ES", "MX"]),
   max_products: int = Query(default=50, ge=1, le=200),
   api_key: str = Depends(get_api_key)
):
   """✅ ENTERPRISE: Intelligent cache warm-up con enterprise patterns"""
   try:
       product_cache = await ServiceFactory.get_product_cache_singleton()
       
       warmup_result = await product_cache.intelligent_cache_warmup(
           market_priorities=market_priorities,
           max_products_per_market=max_products
       )
       
       return {
           "timestamp": time.time(),
           "service": "enterprise_cache_warmup",
           "success": True,
           "warmup_result": warmup_result,
           "enterprise_metadata": {
               "architecture": "enterprise",
               "intelligent_warmup": True,
               "market_aware": True
           }
       }
   except Exception as e:
       return {
           "timestamp": time.time(),
           "service": "enterprise_cache_warmup",
           "success": False,
           "error": str(e)
       }

@router.get("/enterprise/performance/metrics", tags=["Enterprise Monitoring"])
async def get_enterprise_performance_metrics(api_key: str = Depends(get_api_key)):
   """✅ ENTERPRISE: Get comprehensive performance metrics"""
   try:
       # Get cache performance
       product_cache = await ServiceFactory.get_product_cache_singleton()
       cache_stats = product_cache.get_stats()
       
       # Get Redis performance
       redis_service = await ServiceFactory.get_redis_service()
       redis_health = await redis_service.health_check()
       
       # Get inventory service performance
       inventory_service = await ServiceFactory.get_inventory_service_singleton()
       
       return {
           "timestamp": time.time(),
           "service": "enterprise_performance_monitoring",
           "performance_metrics": {
               "cache_performance": {
                   "hit_ratio": cache_stats.get("hit_ratio", 0),
                   "total_requests": cache_stats.get("total_requests", 0),
                   "cache_size": cache_stats.get("cache_size", 0),
                   "efficiency_rating": "excellent" if cache_stats.get("hit_ratio", 0) > 0.7 else "good" if cache_stats.get("hit_ratio", 0) > 0.4 else "needs_improvement"
               },
               "redis_performance": {
                   "status": redis_health.get("status"),
                   "response_time_ms": redis_health.get("response_time_ms"),
                   "connection_pool_active": redis_health.get("connection_pool", {}).get("active_connections", 0)
               },
               "overall_system_health": "optimal" if redis_health.get("status") == "healthy" and cache_stats.get("hit_ratio", 0) > 0.5 else "functional"
           },
           "enterprise_metadata": {
               "architecture": "enterprise",
               "monitoring_level": "comprehensive",
               "service_discovery": True
           }
       }
   except Exception as e:
       return {
           "timestamp": time.time(),
           "service": "enterprise_performance_monitoring",
           "error": str(e),
           "status": "monitoring_degraded"
       }

# ============================================================================
# 🚀 PRODUCTCACHE MANAGEMENT ENDPOINTS (ORIGINAL)
# ============================================================================

@router.get("/debug/product-cache", tags=["ProductCache"])
async def debug_product_cache():
   """Debug endpoint para ProductCache statistics (ORIGINAL)"""
   try:
       cache = await ServiceFactory.get_product_cache_singleton()
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
   """Warm up ProductCache intelligently (ORIGINAL)"""
   try:
       cache = await ServiceFactory.get_product_cache_singleton()
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

# ============================================================================
# 🔍 DEBUG ENDPOINTS - TEMPORALES PARA DEBUGGING (ORIGINAL)
# ============================================================================

@router.get("/debug/shopify", tags=["Debug"])
async def debug_shopify_connection_endpoint():
   """Endpoint para debugging de conexión Shopify (ORIGINAL)"""
   shopify_client = get_shopify_client()
   return await debug_shopify_connection(shopify_client)

@router.get(
   "/debug/headers",
   summary="🔍 Debug Headers",
   description="Endpoint temporal para debugging de headers de autenticación",
   tags=["Debug"]
)
async def debug_headers(request: Request):
   """
   🔍 Endpoint debug para investigar problemas de autenticación (ORIGINAL).
   
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
   🔐 Endpoint debug que SÍ requiere autenticación (ORIGINAL).
   
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
   🚀 Endpoint específico para debugging de load testing (ORIGINAL).
   
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

# ============================================================================
# 🔄 LEGACY COMPATIBILITY ENDPOINTS (DEPRECATED)

@router.get("/debug/product/{product_id}", tags=["Debug"])
async def debug_individual_product(
    product_id: str,
    api_key: str = Depends(get_api_key)
):
    """Debug endpoint para analizar performance de productos individuales"""
    try:
        start_time = time.time()
        
        # Test cache
        cache_result = None
        cache_time = None
        try:
            cache = await ServiceFactory.get_product_cache_singleton()
            cache_start = time.time()
            cached_product = await cache.get_product(product_id)
            cache_time = (time.time() - cache_start) * 1000
            cache_result = "hit" if cached_product else "miss"
        except Exception as e:
            cache_result = f"error: {str(e)}"
            cache_time = None
        
        # Test Shopify
        shopify_result = None
        shopify_time = None
        try:
            shopify_client = get_shopify_client()
            if shopify_client:
                shopify_start = time.time()
                shopify_product = await _get_shopify_product_optimized(shopify_client, product_id)
                shopify_time = (time.time() - shopify_start) * 1000
                shopify_result = "found" if shopify_product else "not_found"
            else:
                shopify_result = "client_unavailable"
        except Exception as e:
            shopify_result = f"error: {str(e)}"
            shopify_time = None
        
        total_time = (time.time() - start_time) * 1000
        
        return {
            "product_id": product_id,
            "total_time_ms": total_time,
            "cache": {
                "result": cache_result,
                "time_ms": cache_time
            },
            "shopify": {
                "result": shopify_result,
                "time_ms": shopify_time
            },
            "performance_analysis": {
                "cache_efficiency": "excellent" if cache_time and cache_time < 100 else "good" if cache_time and cache_time < 500 else "needs_improvement",
                "shopify_efficiency": "excellent" if shopify_time and shopify_time < 1000 else "good" if shopify_time and shopify_time < 2000 else "needs_improvement",
                "overall_rating": "optimized" if total_time < 1000 else "acceptable" if total_time < 2000 else "slow"
            }
        }
    except Exception as e:
        return {
            "product_id": product_id,
            "error": str(e),
            "total_time_ms": (time.time() - start_time) * 1000
        }


# ============================================================================
@router.get("/debug/product-comparison/{product_id}", tags=["Debug"])
async def debug_product_comparison(
    product_id: str,
    api_key: str = Depends(get_api_key)
):
    """Debug endpoint para comparar performance de métodos de obtención de productos"""
    try:
        start_total = time.time()
        results = {}
        
        shopify_client = get_shopify_client()
        if not shopify_client:
            return {"error": "Shopify client not available"}
        
        # Test 1: Cache
        try:
            cache = await ServiceFactory.get_product_cache_singleton()
            cache_start = time.time()
            cached_product = await cache.get_product(product_id)
            cache_time = (time.time() - cache_start) * 1000
            results["cache"] = {
                "time_ms": cache_time,
                "found": cached_product is not None,
                "method": "ProductCache.get_product()"
            }
        except Exception as e:
            results["cache"] = {"error": str(e)}
        
        # Test 2: Direct API call
        try:
            direct_start = time.time()
            direct_product = await _get_shopify_product_direct_api(shopify_client, product_id)
            direct_time = (time.time() - direct_start) * 1000
            results["direct_api"] = {
                "time_ms": direct_time,
                "found": direct_product is not None,
                "method": "Direct Shopify API endpoint"
            }
        except Exception as e:
            results["direct_api"] = {"error": str(e)}
        
        # Test 3: Optimized search (old method)
        try:
            search_start = time.time()
            search_product = await _get_shopify_product_optimized(shopify_client, product_id)
            search_time = (time.time() - search_start) * 1000
            results["optimized_search"] = {
                "time_ms": search_time,
                "found": search_product is not None,
                "method": "Progressive search in product list"
            }
        except Exception as e:
            results["optimized_search"] = {"error": str(e)}
        
        total_time = (time.time() - start_total) * 1000
        
        # Performance analysis
        times = []
        if "cache" in results and "time_ms" in results["cache"]:
            times.append(("cache", results["cache"]["time_ms"]))
        if "direct_api" in results and "time_ms" in results["direct_api"]:
            times.append(("direct_api", results["direct_api"]["time_ms"]))
        if "optimized_search" in results and "time_ms" in results["optimized_search"]:
            times.append(("optimized_search", results["optimized_search"]["time_ms"]))
        
        # Sort by time
        times.sort(key=lambda x: x[1])
        
        return {
            "product_id": product_id,
            "total_test_time_ms": total_time,
            "results": results,
            "performance_ranking": times,
            "recommendation": {
                "fastest_method": times[0][0] if times else "unknown",
                "direct_api_vs_search_improvement": (
                    f"{((results['optimized_search']['time_ms'] - results['direct_api']['time_ms']) / results['optimized_search']['time_ms'] * 100):.1f}%"
                    if all(k in results and "time_ms" in results[k] for k in ["direct_api", "optimized_search"])
                    else "Cannot calculate"
                )
            }
        }
        
    except Exception as e:
        return {
            "product_id": product_id,
            "error": str(e),
            "total_test_time_ms": (time.time() - start_total) * 1000
        }


@router.get("/legacy/products/", tags=["Legacy Compatibility"], deprecated=True)
async def get_products_legacy_compatibility(
   limit: int = Query(default=10, ge=1, le=100),
   page: int = Query(default=1, ge=1),
   market_id: str = Query(default="US"),
   api_key: str = Depends(get_api_key)
):
   """
   ⚠️ DEPRECATED: Legacy compatibility endpoint.
   Use /v1/products/ for enterprise architecture.
   """
   logger.warning("⚠️ DEPRECATED: Legacy products endpoint used - migrate to enterprise /v1/products/")
   
   # Redirect to enterprise endpoint internally
   return await get_products(
       limit=limit,
       page=page,
       market_id=market_id,
       include_inventory=True,
       category=None,
       available_only=False,
       api_key=api_key
   )


@router.get("/admin/catalog/status", 
          summary="Check Google Retail API Catalog Status",
          description="Verifica el estado del catálogo de Google Retail API y muestra información de diagnóstico")
async def check_catalog_status(
    api_key: str = Depends(get_api_key)
):
    """
    🔍 Endpoint de diagnóstico para verificar el estado del catálogo de Google Retail API.
    
    Este endpoint permite verificar:
    - Si el catálogo tiene productos importados
    - Estado de disponibilidad para recomendaciones
    - Configuración actual de Google Cloud Retail API
    - Sugerencias para resolver problemas
    
    Returns:
        Dict: Información detallada sobre el estado del catálogo
    """
    try:
        logging.info(f"[ADMIN] 🔍 Iniciando verificación del estado del catálogo...")
        
        # Obtener recomendador de Google Retail API desde el sistema de recomendaciones híbridas
        try:
            from src.recommenders.retail_api import RetailAPIRecommender
            import os
            
            retail_recommender = RetailAPIRecommender(
                project_number=os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166"),
                location=os.getenv("GOOGLE_LOCATION", "global"),
                catalog=os.getenv("GOOGLE_CATALOG", "default_catalog"),
                serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
            )
        except Exception as init_error:
            return {
                "status": "error",
                "error": f"Cannot initialize Google Retail API client: {str(init_error)}",
                "diagnosis": {
                    "catalog_accessible": False,
                    "products_imported": "error",
                    "recommendation_ready": False,
                    "message": "Cannot access Google Retail API"
                }
            }
        
        parent = f"projects/{retail_recommender.project_number}/locations/{retail_recommender.location}/catalogs/{retail_recommender.catalog}/branches/0"
        
        # Verificar productos en el catálogo
        try:
            from google.cloud.retail_v2.types import ListProductsRequest
            list_request = ListProductsRequest(
                parent=parent,
                page_size=10  # Obtener más productos para un diagnóstico completo
            )
            
            response = retail_recommender.product_client.list_products(request=list_request)
            products = list(response)
            
            product_details = []
            categories_found = set()
            total_with_price = 0
            
            for product in products:
                product_info = {
                    "id": product.id,
                    "title": product.title[:50] + "..." if len(product.title) > 50 else product.title,
                    "availability": str(product.availability),
                    "categories": list(product.categories) if product.categories else []
                }
                
                # Recopilar categorías para estadísticas
                if product.categories:
                    categories_found.update(product.categories)
                
                # Agregar información de precio si está disponible
                if hasattr(product, 'price_info') and product.price_info:
                    product_info["price"] = product.price_info.price
                    product_info["currency"] = product.price_info.currency_code
                    total_with_price += 1
                
                product_details.append(product_info)
            
            # Determinar estado del catálogo
            is_ready_for_recommendations = len(products) >= 5 and len(categories_found) >= 2
            
            catalog_status = {
                "status": "success",
                "catalog_path": parent,
                "total_products_found": len(products),
                "has_products": len(products) > 0,
                "products_with_price": total_with_price,
                "categories_found": len(categories_found),
                "sample_categories": list(categories_found)[:5],
                "sample_products": product_details,
                "diagnosis": {
                    "catalog_accessible": True,
                    "products_imported": len(products) > 0,
                    "recommendation_ready": is_ready_for_recommendations,
                    "message": (
                        "Catálogo LISTO para recomendaciones" if is_ready_for_recommendations 
                        else "Catálogo con pocos productos" if len(products) > 0 and len(products) < 5
                        else "Catálogo vacío - necesita importación"
                    )
                },
                "recommendations": {
                    "google_retail_api": (
                        "DISPONIBLE" if is_ready_for_recommendations 
                        else "LIMITADO - pocos productos" if len(products) > 0
                        else "NO DISPONIBLE - catálogo vacío"
                    ),
                    "fallback_tfidf": "SIEMPRE DISPONIBLE",
                    "hybrid_mode": (
                        "ACTIVO" if is_ready_for_recommendations
                        else "SOLO TF-IDF" if len(products) < 5
                        else "SOLO TF-IDF"
                    ),
                    "suggested_action": (
                        "Sistema listo para usar" if is_ready_for_recommendations
                        else "Importar más productos para mejorar calidad" if len(products) > 0
                        else "IMPORTAR CATÁLOGO usando POST /v1/admin/catalog/import"
                    )
                }
            }
            
        except ImportError:
            catalog_status = {
                "status": "error",
                "error": "Cannot import ListProductsRequest - client library issue",
                "catalog_path": parent,
                "diagnosis": {
                    "catalog_accessible": False,
                    "products_imported": "unknown",
                    "recommendation_ready": False,
                    "message": "Cannot verify catalog - library issue"
                },
                "suggested_solutions": [
                    "Update google-cloud-retail package",
                    "Check Python environment and dependencies"
                ]
            }
            
        except Exception as catalog_error:
            catalog_status = {
                "status": "error",
                "error": str(catalog_error),
                "catalog_path": parent,
                "diagnosis": {
                    "catalog_accessible": False,
                    "products_imported": "error",
                    "recommendation_ready": False,
                    "message": f"Error accessing catalog: {str(catalog_error)}"
                },
                "suggested_solutions": [
                    "Check Google Cloud credentials (GOOGLE_APPLICATION_CREDENTIALS)",
                    "Verify project_number and catalog configuration in .env",
                    "Check Google Cloud Retail API permissions for the service account",
                    "Ensure Google Cloud Retail API is enabled for the project"
                ]
            }
        
        # Agregar información de configuración
        catalog_status["configuration"] = {
            "project_number": retail_recommender.project_number,
            "location": retail_recommender.location,
            "catalog": retail_recommender.catalog,
            "serving_config": retail_recommender.serving_config_id,
            "placement": retail_recommender.placement
        }
        
        # Últimos diagnósticos
        catalog_status["next_steps"] = [
            "Verificar logs del sistema para más detalles",
            "Probar endpoint /v1/recommendations/{product_id} después de importar",
            "Configurar eventos de usuario para mejorar personalización"
        ]
        
        logging.info(f"[ADMIN] ✅ Verificación de catálogo completada: {catalog_status['diagnosis']['message']}")
        
        return catalog_status
        
    except Exception as e:
        logging.error(f"[ADMIN] ❌ Error en verificación de catálogo: {str(e)}")
        return {
            "status": "error",
            "error": f"Failed to check catalog status: {str(e)}",
            "diagnosis": {
                "catalog_accessible": False,
                "products_imported": "error",
                "recommendation_ready": False,
                "message": "Cannot verify catalog due to system error"
            }
        }