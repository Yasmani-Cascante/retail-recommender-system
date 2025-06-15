"""
Punto de entrada principal unificado para la API del sistema de recomendaciones
con integración de Redis para caché.

Este archivo implementa la API REST para el sistema de recomendaciones,
utilizando la configuración centralizada, las fábricas de componentes
y el sistema de caché con Redis.
"""

import os
import time
import logging
import asyncio
from dotenv import load_dotenv
from datetime import datetime
from fastapi import FastAPI, Header, Query, HTTPException, BackgroundTasks, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import math
import random

# Intentar cargar variables de entorno, pero continuar si no existe el archivo
try:
    load_dotenv()
    logging.info("Variables de entorno cargadas desde .env")
except Exception as e:
    logging.warning(f"No se pudo cargar .env, usando variables de entorno del sistema: {e}")

# Importar configuración centralizada
from src.api.core.config import get_settings
from src.api.factories import RecommenderFactory
from src.api.startup_helper import StartupManager
from src.api.core.store import get_shopify_client, init_shopify
from src.api.security import get_api_key, get_current_user

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar configuración
settings = get_settings()

# Crear aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API",
    description="API para sistema de recomendaciones de retail con caché Redis",
    version=settings.app_version
)

# Agregar middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Crear recomendadores usando las fábricas
tfidf_recommender = RecommenderFactory.create_tfidf_recommender()
retail_recommender = RecommenderFactory.create_retail_recommender()

# Variables globales para Redis y caché de productos
redis_client = None
product_cache = None

# Inicialmente crear el recomendador híbrido sin caché
# Se actualizará después con la caché en el evento de startup
hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
    tfidf_recommender, retail_recommender
)

# Crear gestor de arranque
startup_manager = StartupManager(startup_timeout=settings.startup_timeout)

# Variables para uptime
start_time = time.time()

# Cargar extensiones según configuración
if settings.metrics_enabled:
    from src.api.extensions.metrics_extension import MetricsExtension
    metrics_extension = MetricsExtension(app, settings)
    metrics_extension.setup()

# Modelos de datos
class HealthStatus(BaseModel):
    status: str = Field(description="Estado general del servicio")
    components: Dict[str, Any] = Field(description="Estado de los componentes")
    uptime_seconds: float = Field(description="Tiempo de funcionamiento en segundos")

# Función para la carga asíncrona de productos y modelos
async def load_shopify_products():
    """Carga productos desde Shopify."""
    try:
        # Inicializar cliente Shopify
        client = init_shopify()
        if client:
            products = client.get_products()
            logger.info(f"Cargados {len(products)} productos desde Shopify")
            if products:
                logger.info(f"Primer producto: {products[0].get('title', 'No title')}")
            return products
        else:
            logger.warning("No se pudo inicializar el cliente de Shopify, intentando cargar productos de muestra")
    except Exception as e:
        logger.error(f"Error cargando productos desde Shopify: {e}")
    
    # Si falla Shopify, intentar cargar productos de muestra
    return await load_sample_data()

async def load_sample_data():
    """Carga datos de muestra para el recomendador si no se pueden obtener de Shopify."""
    try:
        # Intento 1: Cargar desde datos de muestra en el módulo
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        if SAMPLE_PRODUCTS:
            logger.info(f"Cargados {len(SAMPLE_PRODUCTS)} productos de muestra")
            return SAMPLE_PRODUCTS
    except Exception as e:
        logger.warning(f"No se pudieron cargar productos de muestra desde código: {e}")
    
    # Datos mínimos de fallback
    minimal_products = [
        {
            "id": "product1",
            "title": "Camiseta básica",
            "body_html": "Camiseta de algodón de alta calidad.",
            "product_type": "Ropa"
        },
        {
            "id": "product2",
            "title": "Pantalón vaquero",
            "body_html": "Pantalón vaquero clásico de corte recto.",
            "product_type": "Ropa"
        },
        {
            "id": "product3",
            "title": "Zapatillas deportivas",
            "body_html": "Zapatillas para running con amortiguación.",
            "product_type": "Calzado"
        }
    ]
    logger.info(f"Usando {len(minimal_products)} productos mínimos de muestra")
    return minimal_products

async def load_recommender():
    """Carga y entrena el recomendador TF-IDF con productos de Shopify."""
    try:
        # Intentar cargar modelo pre-entrenado
        if os.path.exists("data/tfidf_model.pkl"):
            success = await tfidf_recommender.load()
            if success:
                logger.info("Modelo TF-IDF cargado correctamente desde archivo")
                return True
        
        # Si no existe o falla, entrenar con datos de Shopify o muestra
        products = await load_shopify_products()
        if not products:
            logger.error("No se pudieron cargar productos de ninguna fuente")
            return False
            
        logger.info(f"Entrenando recomendador TF-IDF con {len(products)} productos")
        success = await tfidf_recommender.fit(products)
        
        if success:
            logger.info("Recomendador TF-IDF entrenado correctamente")
            
            # Importar productos a Google Cloud Retail API
            try:
                logger.info("Importando productos a Google Cloud Retail API")
                import_result = await retail_recommender.import_catalog(products)
                logger.info(f"Resultado de importación: {import_result}")
            except Exception as e:
                logger.error(f"Error importando productos a Google Cloud Retail API: {str(e)}")
        else:
            logger.error("Error entrenando recomendador TF-IDF")
            
        return success
    except Exception as e:
        logger.error(f"Error cargando recomendador: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicación."""
    logger.info("🚀 Iniciando API de recomendaciones unificada con Redis...")
    
    # Verificar estructura del catálogo en Retail API si está habilitado
    if settings.validate_products:
        try:
            logger.info("Verificando estructura del catálogo en Google Cloud Retail API...")
            await retail_recommender.ensure_catalog_branches()
        except Exception as e:
            logger.warning(f"Error al verificar estructura del catálogo: {str(e)}")
    
    # Inicializar cliente Redis y caché de productos
    try:
        from src.api.factories import RecommenderFactory
        
        # Crear cliente Redis
        global redis_client
        redis_client = RecommenderFactory.create_redis_client()
        logger.info("Cliente Redis inicializado")
        
        # Crear caché de productos
        global product_cache
        product_cache = RecommenderFactory.create_product_cache(
            content_recommender=tfidf_recommender,
            shopify_client=get_shopify_client()
        )
        
        if product_cache:
            logger.info("Sistema de caché de productos inicializado correctamente")
            
            # Actualizar hybrid_recommender para usar la caché
            global hybrid_recommender
            hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
                tfidf_recommender,
                retail_recommender,
                product_cache=product_cache
            )
            logger.info("Recomendador híbrido actualizado para usar caché")
        else:
            logger.warning("Sistema de caché de productos no disponible - usando modo sin caché")
        
    except Exception as e:
        logger.error(f"Error inicializando sistemas de caché: {str(e)}")
        logger.info("Continuando sin caché...")
    
    # Registrar componentes en el gestor de arranque
    startup_manager.register_component(
        name="recommender",
        loader=load_recommender,
        required=True
    )
    
    # Iniciar carga en segundo plano
    loading_task = asyncio.create_task(startup_manager.start_loading())
    
    # Iniciar generación de datos de prueba si es necesario
    if settings.debug:
        from src.api.core.event_generator import initialize_with_test_data
        logger.info("Modo DEBUG: Programando generación de datos de prueba después de carga inicial")
        # Programar para después de que el recomendador esté cargado
        asyncio.create_task(
            initialize_with_test_data(retail_recommender, tfidf_recommender)
        )

@app.get("/", include_in_schema=False)
def read_root():
    return {
        "message": "Retail Recommender API unificada con Redis",
        "version": settings.app_version,
        "status": "online",
        "docs_url": "/docs"
    }

@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Endpoint de verificación de salud del servicio."""
    recommender_status = await tfidf_recommender.health_check()
    startup_status = startup_manager.get_status()
    
    # Añadir estado de Redis/caché si está disponible
    cache_status = {}
    if 'product_cache' in globals() and product_cache:
        try:
            cache_stats = product_cache.get_stats()
            # Obtener estado de conexión Redis
            redis_status = "connected" if (product_cache.redis and product_cache.redis.connected) else "disconnected"
            
            cache_status = {
                "status": "operational" if redis_status == "connected" else "degraded",
                "redis_connection": redis_status,
                "hit_ratio": cache_stats["hit_ratio"],
                "stats": cache_stats
            }
        except Exception as e:
            cache_status = {
                "status": "error",
                "error": str(e)
            }
    else:
        cache_status = {
            "status": "unavailable",
            "message": "Product cache not initialized"
        }
    
    return {
        "status": startup_status["status"],
        "components": {
            "recommender": recommender_status,
            "startup": startup_status,
            "cache": cache_status  # Añadir componente de caché
        },
        "uptime_seconds": time.time() - start_time
    }

@app.get("/v1/recommendations/{product_id}", response_model=Dict)
async def get_recommendations(
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene recomendaciones basadas en un producto.
    Requiere autenticación mediante API key.
    """
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    # Obtener recomendaciones
    try:
        # Actualizar peso de contenido en el recomendador híbrido
        hybrid_recommender.content_weight = content_weight
        
        # Obtener producto específico
        client = get_shopify_client()
        product = None
        
        if client:
            # Obtener productos
            all_products = client.get_products()
            
            # Encontrar el producto específico
            product = next(
                (p for p in all_products if str(p.get('id')) == str(product_id)),
                None
            )
        
        if not product and tfidf_recommender.loaded:
            # Intentar obtener producto del recomendador
            product = tfidf_recommender.get_product_by_id(product_id)
        
        if not product:
            # Cambiar a HTTPException para mantener consistencia
            raise HTTPException(
                status_code=404,
                detail=f"Product ID {product_id} not found"
            )
            
        # Obtener recomendaciones del recomendador híbrido
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id or "anonymous",
            product_id=str(product_id),
            n_recommendations=n
        )
        
        # Calcular tiempo de procesamiento
        processing_time_ms = (time.time() - start_processing) * 1000
        
        # Registrar métricas si están habilitadas
        if settings.metrics_enabled and 'recommendation_metrics' in globals():
            from src.api.core.metrics import recommendation_metrics
            recommendation_metrics.record_recommendation_request(
                request_data={
                    "product_id": product_id,
                    "user_id": user_id or "anonymous",
                    "n": n,
                    "content_weight": content_weight
                },
                recommendations=recommendations,
                response_time_ms=processing_time_ms,
                user_id=user_id or "anonymous",
                product_id=product_id
            )
        
        return {
            "product": {
                "id": product.get('id'),
                "title": product.get('title')
            },
            "recommendations": recommendations,
            "metadata": {
                "content_weight": content_weight,
                "total_recommendations": len(recommendations),
                "source": "hybrid_tfidf_redis",
                "took_ms": processing_time_ms
            }
        }
    except HTTPException:
        # Re-lanzar HTTPExceptions directamente para mantener el código y mensaje
        raise
    except ValueError as e:
        # Convertir ValueError a HTTPException 404
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error obteniendo recomendaciones: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/recommendations/user/{user_id}", response_model=Dict)
async def get_user_recommendations(
    user_id: str,
    n: Optional[int] = Query(5, gt=0, le=20),
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene recomendaciones personalizadas para un usuario.
    Requiere autenticación mediante API key.
    """
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    try:
        client = get_shopify_client()
        
        logger.info(f"Obteniendo recomendaciones para usuario {user_id}")
        
        # Obtener órdenes del usuario si está disponible Shopify
        user_orders = []
        if client:
            user_orders = client.get_orders_by_customer(user_id)
            
            if user_orders:
                logger.info(f"Se encontraron {len(user_orders)} órdenes para el usuario {user_id}")
                
                # Registrar eventos de usuario basados en órdenes
                try:
                    await retail_recommender.process_shopify_orders(user_orders, user_id)
                    logger.info(f"Eventos de órdenes procesados para usuario {user_id}")
                except Exception as e:
                    logger.error(f"Error procesando órdenes: {e}")
            else:
                logger.info(f"No se encontraron órdenes para el usuario {user_id}")
        
        # Obtener recomendaciones
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=n
        )
        
        # Calcular tiempo de procesamiento
        processing_time_ms = (time.time() - start_processing) * 1000
        
        # Registrar métricas si están habilitadas
        if settings.metrics_enabled and 'recommendation_metrics' in globals():
            from src.api.core.metrics import recommendation_metrics
            recommendation_metrics.record_recommendation_request(
                request_data={
                    "user_id": user_id,
                    "n": n
                },
                recommendations=recommendations,
                response_time_ms=processing_time_ms,
                user_id=user_id,
                product_id=None
            )
        
        return {
            "recommendations": recommendations,
            "metadata": {
                "user_id": user_id,
                "total_recommendations": len(recommendations),
                "total_orders": len(user_orders) if user_orders else 0,
                "source": "hybrid_tfidf_user_redis",
                "took_ms": processing_time_ms
            }
        }
    except Exception as e:
        logger.error(f"Error obteniendo recomendaciones para usuario {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo recomendaciones: {str(e)}"
        )

@app.post("/v1/events/user/{user_id}")
async def record_user_event(
    user_id: str,
    event_type: str = Query(..., description="Tipo de evento (detail-page-view, add-to-cart, purchase-complete, etc.)"),
    product_id: Optional[str] = Query(None, description="ID del producto relacionado con el evento"),
    purchase_amount: Optional[float] = Query(None, description="Monto de la compra para eventos de tipo purchase-complete"),
    current_user: str = Depends(get_current_user)
):
    """
    Registra eventos de usuario para mejorar las recomendaciones futuras.
    Requiere autenticación mediante API key.
    
    Tipos de eventos válidos según Google Cloud Retail API:
    - add-to-cart: Cuando un usuario añade un producto al carrito
    - category-page-view: Cuando un usuario ve páginas especiales, como ofertas o promociones
    - detail-page-view: Cuando un usuario ve la página de detalle de un producto
    - home-page-view: Cuando un usuario visita la página de inicio
    - purchase-complete: Cuando un usuario completa una compra
    - search: Cuando un usuario realiza una búsqueda
    
    El sistema también acepta nombres alternativos simplificados:
    - 'view' o 'detail-page' → detail-page-view
    - 'add' o 'cart' → add-to-cart
    - 'buy', 'purchase' o 'checkout' → purchase-complete
    - 'home' → home-page-view
    - 'category' o 'promo' → category-page-view
    """
    try:
        # Validar product_id si está presente
        if product_id:
            # Verificar si es un ID existente en el catálogo
            if tfidf_recommender.loaded and tfidf_recommender.product_data:
                product_exists = any(str(p.get('id', '')) == product_id for p in tfidf_recommender.product_data)
                if not product_exists:
                    # Si el ID no existe, pero es un ID de desarrollo (empieza con 'prod_test_'), permitirlo
                    if not product_id.startswith(('test_', 'prod_test_', '123')):
                        logger.warning(f"ID de producto no encontrado en el catálogo: {product_id}")
                        # Aún permitimos el evento, pero advertimos
            
        logger.info(f"Registrando evento de usuario: {user_id}, tipo: {event_type}, producto: {product_id or 'N/A'}")
        
        # Registrar el evento
        result = await hybrid_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id,
            purchase_amount=purchase_amount
        )
        
        # Añadir información adicional a la respuesta
        if result.get("status") == "success":
            result["detail"] = {
                "user_id": user_id,
                "event_type": result.get("event_type", event_type),
                "product_id": product_id,
                "timestamp": datetime.utcnow().isoformat(),
                "note": "El evento fue registrado correctamente y ayudará a mejorar las recomendaciones futuras."
            }
            
            # Registrar interacción en métricas si están habilitadas
            if settings.metrics_enabled and 'recommendation_metrics' in globals():
                from src.api.core.metrics import recommendation_metrics
                recommendation_metrics.record_user_interaction(
                    user_id=user_id,
                    product_id=product_id,
                    event_type=event_type,
                    recommendation_id=None  # No podemos saber si vino de una recomendación sin contexto adicional
                )
        
        return result
    except Exception as e:
        logger.error(f"Error registrando evento de usuario: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error al registrar el evento: {str(e)}. Asegúrate de usar un tipo de evento válido (detail-page-view, add-to-cart, purchase-complete, category-page-view, home-page-view, search)."
        )

@app.get("/v1/customers/")
async def get_customers(
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene la lista de clientes de Shopify.
    Requiere autenticación mediante API key.
    """
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
            
        customers = client.get_customers()
        
        if not customers:
            logger.warning("No customers found")
            return {
                "total": 0,
                "customers": []
            }
            
        return {
            "total": len(customers),
            "customers": customers
        }
    except Exception as e:
        logger.error(f"Error fetching customers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/v1/products/")
async def get_products(
    page: int = Query(1, gt=0, description="Número de página"),
    page_size: int = Query(50, gt=0, le=100, description="Resultados por página")
):
    """
    Obtiene la lista de productos con paginación.
    """
    # Log del valor recibido para debugging
    logger.info(f"get_products: Parámetros recibidos - page={page}, page_size={page_size}")

    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    try:
        # Intentar obtener productos de Shopify primero
        client = get_shopify_client()
        if client:
            all_products = client.get_products()
            logger.info(f"Obtenidos {len(all_products)} productos desde Shopify")
        elif tfidf_recommender.loaded and tfidf_recommender.product_data:
            all_products = tfidf_recommender.product_data
            logger.info(f"Obtenidos {len(all_products)} productos desde el recomendador")
        else:
            # Si no hay productos disponibles, devolver respuesta vacía
            return {
                "products": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "loading_complete": False
            }
        
         # Validar explícitamente page_size para asegurar que se respeta el valor
        actual_page_size = min(page_size, 100)  # Asegurar que no exceda 100
        logger.info(f"Usando page_size={actual_page_size}")
        
        # Calcular índices de paginación
        start_idx = (page - 1) * actual_page_size
        end_idx = start_idx + actual_page_size
        
        # Calcular total de páginas
        total_products = len(all_products)
        total_pages = math.ceil(total_products / actual_page_size)

        # Verificar que los índices están dentro de límites
        if start_idx >= total_products:
            # Si página fuera de rango, devolver última página
            page = total_pages
            start_idx = (page - 1) * actual_page_size
            end_idx = total_products
        
        # Obtener productos paginados
        paginated_products = all_products[start_idx:end_idx]
        logger.info(f"Devolviendo {len(paginated_products)} productos (page={page}, page_size={actual_page_size})")
        
        # Construir y devolver respuesta
        return {
            "products": paginated_products,
            "total": total_products,
            "page": page,
            "page_size": actual_page_size,
            "total_pages": total_pages,
            "loading_complete": True
        }
    except Exception as e:
        logger.error(f"Error obteniendo productos: {e}")
        logger.error("Stack trace:", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error obteniendo productos: {str(e)}")

@app.get("/v1/products/category/{category}")
async def get_products_by_category(
    category: str,
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene productos filtrados por categoría.
    Requiere autenticación mediante API key.
    """
    try:
        client = get_shopify_client()
        all_products = []
        
        if client:
            logger.info(f"Obteniendo productos de Shopify para categoría: {category}")
            all_products = client.get_products()
        elif tfidf_recommender.loaded and tfidf_recommender.product_data:
            logger.info(f"Obteniendo productos del recomendador para categoría: {category}")
            all_products = tfidf_recommender.product_data
        else:
            raise HTTPException(
                status_code=503,
                detail="No hay productos disponibles. El servicio está cargando."
            )
            
        logger.info(f"Filtrando {len(all_products)} productos por categoría: {category}")
        
        # Filtrar por categoría (product_type en Shopify)
        category_products = [
            p for p in all_products 
            if p.get("product_type", "").lower() == category.lower()
        ]
        
        logger.info(f"Encontrados {len(category_products)} productos en categoría {category}")
        
        if not category_products:
            raise HTTPException(
                status_code=404,
                detail=f"No products found in category: {category}"
            )
        return category_products
    except HTTPException:
        # Re-lanzar excepciones HTTP que ya hemos creado
        raise
    except Exception as e:
        logger.error(f"Error en búsqueda por categoría: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/products/search/", response_model=Dict)
async def search_products(
    q: str = Query(..., min_length=1, description="Texto de búsqueda"),
    current_user: str = Depends(get_current_user)
):
    """
    Busca productos por texto utilizando similitud TF-IDF.
    Requiere autenticación mediante API key.
    """
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    if not tfidf_recommender.loaded:
        return {
            "products": [],
            "total": 0,
            "query": q,
            "loading_complete": False,
            "message": "El buscador está cargando. Intente más tarde."
        }
    
    # Realizar búsqueda
    start_processing = time.time()
    try:
        results = await tfidf_recommender.search_products(q, 10)
        processing_time_ms = (time.time() - start_processing) * 1000
        
        return {
            "products": results,
            "total": len(results),
            "query": q,
            "loading_complete": True,
            "took_ms": processing_time_ms
        }
    except Exception as e:
        logger.error(f"Error en búsqueda de productos: {e}")
        raise HTTPException(status_code=500, detail=f"Error en búsqueda: {str(e)}")

# Configuración para ejecutar con uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_unified_redis:app", host="0.0.0.0", port=port, reload=True)
