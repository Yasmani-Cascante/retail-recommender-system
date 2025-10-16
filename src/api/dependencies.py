# src/api/dependencies.py
"""
FastAPI Dependency Injection Providers - Enterprise Architecture
=================================================================

Este módulo proporciona dependency providers para FastAPI siguiendo
el patrón de Dependency Injection moderno y best practices.

Propósito
---------
Centralizar la inyección de dependencias para todos los componentes del sistema,
eliminando el anti-pattern de imports globales y variables globales en routers.

Beneficios
----------
1. **Testability**: Fácil override de dependencies para testing
2. **Type Safety**: Type hints claros con Annotated
3. **Decoupling**: Routers no importan componentes directamente
4. **Lifecycle Management**: FastAPI maneja el ciclo de vida
5. **Modern Patterns**: Sigue FastAPI best practices

Uso Básico
----------
En un router:

    from fastapi import APIRouter, Depends
    from src.api.dependencies import get_hybrid_recommender
    from src.api.core.hybrid_recommender import HybridRecommender
    
    router = APIRouter()
    
    @router.get("/recommendations/{product_id}")
    async def get_recommendations(
        product_id: str,
        hybrid: HybridRecommender = Depends(get_hybrid_recommender)
    ):
        recommendations = await hybrid.get_recommendations(product_id)
        return {"recommendations": recommendations}

Testing con Dependency Override
--------------------------------
En tests:

    from fastapi.testclient import TestClient
    from src.api.dependencies import get_hybrid_recommender
    
    # Create mock
    mock_recommender = MockHybridRecommender()
    
    # Override dependency
    app.dependency_overrides[get_hybrid_recommender] = lambda: mock_recommender
    
    # Test
    client = TestClient(app)
    response = client.get("/recommendations/123")
    
    # Cleanup
    app.dependency_overrides.clear()

Type Aliases Usage
------------------
Para código más conciso, usa los type aliases:

    from src.api.dependencies import HybridRecommenderDep
    
    @router.get("/recommendations/{product_id}")
    async def get_recommendations(
        product_id: str,
        hybrid: HybridRecommenderDep  # ← Más conciso
    ):
        ...

Arquitectura
------------
Todas las dependencies se obtienen de ServiceFactory (implementado en Fase 1),
el cual garantiza:
- Singleton pattern thread-safe
- Async lock para concurrencia
- Auto-wiring de dependencias
- Configuration injection

Author: Senior Architecture Team
Date: 2025-10-16
Version: 1.0.0 - Fase 2 Implementation
Status: Production Ready
"""

import logging
from typing import Dict, Any, TYPE_CHECKING

# FastAPI dependency injection
from fastapi import Depends

# Python 3.9+ typing support
try:
    from typing import Annotated
except ImportError:
    # Fallback para Python < 3.9
    from typing_extensions import Annotated

# ServiceFactory - Source of truth para todos los componentes
from src.api.factories.service_factory import ServiceFactory

# ============================================================================
# TYPE CHECKING - Forward references para evitar circular imports
# ============================================================================

if TYPE_CHECKING:
    from src.recommenders.tfidf_recommender import TFIDFRecommender
    from src.recommenders.retail_api import RetailAPIRecommender
    from src.api.core.hybrid_recommender import HybridRecommender
    from src.api.core.product_cache import ProductCache
    from src.api.core.redis_service import RedisService
    from src.api.inventory.inventory_service import InventoryService

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# TYPE ALIASES - Modern FastAPI Pattern (Python 3.9+)
# ============================================================================

"""
Type aliases usando Annotated proporcionan:
1. Type hints claros para IDEs
2. Syntax más conciso en endpoints
3. DRY principle (no repetir Depends() en cada endpoint)

Uso:
    async def endpoint(hybrid: HybridRecommenderDep):
        # hybrid es automáticamente inyectado por FastAPI
        ...
"""

# Recommenders
TFIDFRecommenderDep = Annotated[
    'TFIDFRecommender',
    Depends(lambda: ServiceFactory.get_tfidf_recommender())
]
"""Type alias for TF-IDF recommender dependency injection."""

RetailRecommenderDep = Annotated[
    'RetailAPIRecommender',
    Depends(lambda: ServiceFactory.get_retail_recommender())
]
"""Type alias for Google Retail API recommender dependency injection."""

HybridRecommenderDep = Annotated[
    'HybridRecommender',
    Depends(lambda: ServiceFactory.get_hybrid_recommender())
]
"""Type alias for Hybrid recommender dependency injection."""

# Infrastructure Components
ProductCacheDep = Annotated[
    'ProductCache',
    Depends(lambda: ServiceFactory.get_product_cache_singleton())
]
"""Type alias for ProductCache dependency injection."""

RedisServiceDep = Annotated[
    'RedisService',
    Depends(lambda: ServiceFactory.get_redis_service())
]
"""Type alias for RedisService dependency injection."""

InventoryServiceDep = Annotated[
    'InventoryService',
    Depends(lambda: ServiceFactory.get_inventory_service_singleton())
]
"""Type alias for InventoryService dependency injection."""

# ============================================================================
# EXPLICIT DEPENDENCY PROVIDER FUNCTIONS
# ============================================================================

"""
Explicit provider functions son preferibles cuando:
1. Necesitas documentación detallada
2. Quieres logging o error handling custom
3. La función tiene lógica adicional
4. Prefieres funciones nombradas sobre lambdas

Las type aliases usan estas funciones internamente.
"""

async def get_tfidf_recommender() -> 'TFIDFRecommender':
    """
    Get TF-IDF recommender singleton via ServiceFactory.
    
    El TF-IDF recommender proporciona recomendaciones basadas en contenido
    usando similarity de texto entre productos.
    
    Returns
    -------
    TFIDFRecommender
        Singleton instance del TF-IDF recommender, puede estar loaded o unloaded
        dependiendo de si StartupManager ha completado el training.
    
    Notes
    -----
    - Esta función retorna el singleton creado por ServiceFactory
    - El modelo se carga automáticamente via StartupManager en background
    - Primera llamada puede ser rápida (instancia ya existe desde startup)
    - Thread-safe: Usa async lock internamente
    
    Examples
    --------
    En un endpoint:
    
    >>> @router.get("/recommendations/content/{product_id}")
    >>> async def content_recommendations(
    ...     product_id: str,
    ...     tfidf: TFIDFRecommender = Depends(get_tfidf_recommender)
    ... ):
    ...     recs = tfidf.get_recommendations(product_id, n_recommendations=5)
    ...     return {"recommendations": recs}
    
    Testing con override:
    
    >>> mock_tfidf = MockTFIDFRecommender()
    >>> app.dependency_overrides[get_tfidf_recommender] = lambda: mock_tfidf
    """
    try:
        recommender = await ServiceFactory.get_tfidf_recommender()
        logger.debug(f"TF-IDF recommender dependency injected: loaded={getattr(recommender, 'loaded', False)}")
        return recommender
    except Exception as e:
        logger.error(f"Failed to get TF-IDF recommender: {e}")
        raise


async def get_retail_recommender() -> 'RetailAPIRecommender':
    """
    Get Google Retail API recommender singleton via ServiceFactory.
    
    El Retail API recommender proporciona recomendaciones personalizadas
    usando el servicio de Google Cloud Retail API con user behavior data.
    
    Returns
    -------
    RetailAPIRecommender
        Singleton instance del Retail API recommender configurado con
        project settings (project_number, location, catalog).
    
    Notes
    -----
    - Primera llamada puede tomar 4+ segundos (Google Cloud service init)
    - ALTS warnings son normales cuando no se ejecuta en GCP
    - Requiere configuración correcta en settings (google_project_number, etc.)
    - Thread-safe: Usa async lock internamente
    - Singleton: Llamadas subsecuentes son instantáneas
    
    Warnings
    --------
    Si los settings de Google Cloud no están configurados correctamente,
    el recommender puede no funcionar. Verificar:
    - settings.google_project_number
    - settings.google_location
    - settings.google_catalog
    - settings.google_serving_config
    
    Examples
    --------
    En un endpoint:
    
    >>> @router.get("/recommendations/personalized/{user_id}")
    >>> async def personalized_recommendations(
    ...     user_id: str,
    ...     retail: RetailAPIRecommender = Depends(get_retail_recommender)
    ... ):
    ...     recs = await retail.get_recommendations(user_id=user_id, n=5)
    ...     return {"recommendations": recs}
    """
    try:
        recommender = await ServiceFactory.get_retail_recommender()
        logger.debug("Retail API recommender dependency injected")
        return recommender
    except Exception as e:
        logger.error(f"Failed to get Retail API recommender: {e}")
        raise


async def get_hybrid_recommender() -> 'HybridRecommender':
    """
    Get Hybrid recommender singleton with auto-wired dependencies.
    
    El Hybrid recommender combina TF-IDF (content-based) y Retail API
    (collaborative filtering) para proporcionar recomendaciones óptimas.
    
    Returns
    -------
    HybridRecommender or HybridRecommenderWithExclusion
        Singleton instance del hybrid recommender con todas las dependencias
        auto-wired (tfidf, retail, product_cache).
        
        El tipo específico depende de settings.exclude_seen_products:
        - True: HybridRecommenderWithExclusion (excluye productos vistos)
        - False: HybridRecommender (básico, sin exclusión)
    
    Notes
    -----
    - **Auto-wiring**: Fetches TF-IDF, Retail, y ProductCache automáticamente
    - **Configuration-driven**: Lee settings para content_weight y exclude_seen
    - **Thread-safe**: Usa async lock internamente
    - **Singleton**: Una instancia compartida globalmente
    - **Performance**: Primera llamada ~50ms (dependencies ya son singletons)
    
    Auto-wiring Process
    -------------------
    1. Fetch TF-IDF recommender (singleton)
    2. Fetch Retail API recommender (singleton)
    3. Fetch ProductCache (singleton)
    4. Create Hybrid con dependencies inyectadas
    5. Apply configuration (content_weight, exclude_seen_products)
    
    Examples
    --------
    En un endpoint (uso típico):
    
    >>> @router.get("/recommendations/{product_id}")
    >>> async def get_recommendations(
    ...     product_id: str,
    ...     user_id: Optional[str] = None,
    ...     hybrid: HybridRecommender = Depends(get_hybrid_recommender)
    ... ):
    ...     if user_id:
    ...         # Personalized recommendations
    ...         recs = await hybrid.get_recommendations(
    ...             user_id=user_id,
    ...             product_id=product_id,
    ...             n_recommendations=5
    ...         )
    ...     else:
    ...         # Content-based only
    ...         recs = hybrid.content_recommender.get_recommendations(
    ...             product_id=product_id,
    ...             n_recommendations=5
    ...         )
    ...     return {"recommendations": recs}
    
    Testing con mock completo:
    
    >>> mock_hybrid = MockHybridRecommender()
    >>> app.dependency_overrides[get_hybrid_recommender] = lambda: mock_hybrid
    >>> # Run tests
    >>> app.dependency_overrides.clear()
    """
    try:
        recommender = await ServiceFactory.get_hybrid_recommender()
        
        # Log dependency info para debugging
        logger.debug(
            f"Hybrid recommender dependency injected: "
            f"has_content={recommender.content_recommender is not None}, "
            f"has_retail={recommender.retail_recommender is not None}, "
            f"has_cache={recommender.product_cache is not None}"
        )
        
        return recommender
    except Exception as e:
        logger.error(f"Failed to get Hybrid recommender: {e}")
        raise


async def get_product_cache() -> 'ProductCache':
    """
    Get ProductCache singleton via ServiceFactory.
    
    ProductCache proporciona caching inteligente de productos con múltiples
    fuentes (Redis, local catalog, Shopify) y fallback automático.
    
    Returns
    -------
    ProductCache
        Singleton instance del ProductCache con RedisService, local_catalog,
        y Shopify client inyectados.
    
    Notes
    -----
    - **Multi-source**: Redis (cache) → Local catalog → Shopify (source of truth)
    - **Fallback automático**: Si Redis falla, usa local catalog o Shopify
    - **TTL**: 24 horas (86400 segundos) configurable
    - **Background tasks**: Health checks periódicos si habilitado
    - **Thread-safe**: Usa async lock internamente
    
    Cache Strategy
    --------------
    1. Check Redis (fast)
    2. If miss, check local_catalog (TF-IDF product data)
    3. If miss, fetch from Shopify API
    4. Cache result in Redis para futuros requests
    
    Examples
    --------
    En un endpoint:
    
    >>> @router.get("/products/{product_id}")
    >>> async def get_product(
    ...     product_id: str,
    ...     cache: ProductCache = Depends(get_product_cache)
    ... ):
    ...     product = await cache.get_product(product_id)
    ...     if not product:
    ...         raise HTTPException(status_code=404, detail="Product not found")
    ...     return product
    
    Cache stats:
    
    >>> async def get_cache_stats(
    ...     cache: ProductCache = Depends(get_product_cache)
    ... ):
    ...     stats = cache.get_stats()
    ...     return {
    ...         "hit_ratio": stats["hit_ratio"],
    ...         "total_requests": stats["total_requests"],
    ...         "redis_hits": stats["redis_hits"]
    ...     }
    """
    try:
        cache = await ServiceFactory.get_product_cache_singleton()
        
        # Log cache info
        has_catalog = hasattr(cache, 'local_catalog') and cache.local_catalog is not None
        logger.debug(f"ProductCache dependency injected: has_local_catalog={has_catalog}")
        
        return cache
    except Exception as e:
        logger.error(f"Failed to get ProductCache: {e}")
        raise


async def get_redis_service() -> 'RedisService':
    """
    Get RedisService singleton via ServiceFactory.
    
    RedisService proporciona acceso enterprise a Redis con connection pooling,
    circuit breaker, optimized timeouts, y health monitoring.
    
    Returns
    -------
    RedisService
        Singleton instance del RedisService con optimized Redis client,
        connection pooling (20 connections), y circuit breaker activo.
    
    Notes
    -----
    - **Connection pooling**: 20 concurrent connections
    - **Optimized timeouts**: 1.5s connect, 2.0s socket
    - **Circuit breaker**: Fast-fail después de 3 fallos consecutivos
    - **Health monitoring**: health_check() method disponible
    - **Thread-safe**: Usa async lock internamente
    - **Fallback**: Retorna mock service si Redis no disponible
    
    Circuit Breaker
    ---------------
    Si Redis falla 3 veces consecutivamente, el circuit breaker se abre
    y retorna un fallback service por 60 segundos antes de reintentar.
    
    Examples
    --------
    En un endpoint (raro - normalmente usar ProductCache en su lugar):
    
    >>> @router.get("/cache/test")
    >>> async def test_redis(
    ...     redis: RedisService = Depends(get_redis_service)
    ... ):
    ...     # Test Redis connection
    ...     health = await redis.health_check()
    ...     
    ...     # Set/Get test
    ...     await redis.set("test_key", "test_value", ttl=60)
    ...     value = await redis.get("test_key")
    ...     
    ...     return {
    ...         "health": health,
    ...         "test_value": value
    ...     }
    
    Health monitoring:
    
    >>> async def redis_health(
    ...     redis: RedisService = Depends(get_redis_service)
    ... ):
    ...     health = await redis.health_check()
    ...     return {
    ...         "status": health.get("status"),
    ...         "ping_ms": health.get("ping_time_ms"),
    ...         "connected": health.get("connected")
    ...     }
    """
    try:
        redis = await ServiceFactory.get_redis_service()
        logger.debug("RedisService dependency injected")
        return redis
    except Exception as e:
        logger.error(f"Failed to get RedisService: {e}")
        raise


async def get_inventory_service() -> 'InventoryService':
    """
    Get InventoryService singleton via ServiceFactory.
    
    InventoryService gestiona el inventario de productos integrando con
    Shopify y Redis para caching de disponibilidad.
    
    Returns
    -------
    InventoryService
        Singleton instance del InventoryService con RedisService y
        Shopify client inyectados.
    
    Notes
    -----
    - **Shopify integration**: Real-time inventory data
    - **Redis caching**: Cache de availability checks
    - **Thread-safe**: Usa async lock internamente
    - **Fallback mode**: Funciona sin Redis si no disponible
    
    Examples
    --------
    En un endpoint:
    
    >>> @router.get("/inventory/{product_id}")
    >>> async def check_inventory(
    ...     product_id: str,
    ...     inventory: InventoryService = Depends(get_inventory_service)
    ... ):
    ...     available = await inventory.check_availability(product_id)
    ...     stock = await inventory.get_stock_level(product_id)
    ...     
    ...     return {
    ...         "product_id": product_id,
    ...         "available": available,
    ...         "stock_level": stock
    ...     }
    """
    try:
        inventory = await ServiceFactory.get_inventory_service_singleton()
        logger.debug("InventoryService dependency injected")
        return inventory
    except Exception as e:
        logger.error(f"Failed to get InventoryService: {e}")
        raise


# ============================================================================
# COMPOSITE DEPENDENCIES - Bundle Multiple Components
# ============================================================================

"""
Composite dependencies son útiles cuando un endpoint necesita múltiples
componentes relacionados. En lugar de inyectar cada uno individualmente,
se inyecta un diccionario con todos.

Beneficios:
1. Menos parámetros en la firma del endpoint
2. Agrupa dependencies relacionadas lógicamente
3. Más fácil de testear (un solo override)
"""

async def get_recommendation_context() -> Dict[str, Any]:
    """
    Get full recommendation context with all recommender dependencies.
    
    Este composite dependency bundle todos los recommenders y cache
    en un solo diccionario, útil para endpoints que necesitan acceso
    a múltiples componentes.
    
    Returns
    -------
    dict
        Dictionary con keys:
        - 'tfidf': TFIDFRecommender singleton
        - 'retail': RetailAPIRecommender singleton
        - 'hybrid': HybridRecommender singleton
        - 'cache': ProductCache singleton
    
    Notes
    -----
    - Todas las dependencies son singletons (instancias compartidas)
    - Primera llamada toma ~50ms (singletons ya existen)
    - Llamadas subsecuentes son instantáneas (retorna mismos objetos)
    - Útil para endpoints complejos que necesitan múltiples recommenders
    
    Examples
    --------
    En un endpoint complejo:
    
    >>> @router.post("/recommendations/advanced")
    >>> async def advanced_recommendations(
    ...     request: AdvancedRequest,
    ...     context: Dict = Depends(get_recommendation_context)
    ... ):
    ...     # Access all recommenders
    ...     tfidf_recs = context["tfidf"].get_recommendations(...)
    ...     retail_recs = await context["retail"].get_recommendations(...)
    ...     hybrid_recs = await context["hybrid"].get_recommendations(...)
    ...     
    ...     # Combine results
    ...     return {
    ...         "tfidf": tfidf_recs,
    ...         "retail": retail_recs,
    ...         "hybrid": hybrid_recs
    ...     }
    
    Testing con override:
    
    >>> mock_context = {
    ...     "tfidf": MockTFIDFRecommender(),
    ...     "retail": MockRetailRecommender(),
    ...     "hybrid": MockHybridRecommender(),
    ...     "cache": MockProductCache()
    ... }
    >>> app.dependency_overrides[get_recommendation_context] = lambda: mock_context
    """
    try:
        logger.debug("Building recommendation context...")
        
        # Fetch all components in parallel for performance
        # (aunque son singletons, primera llamada puede tardar)
        context = {
            "tfidf": await get_tfidf_recommender(),
            "retail": await get_retail_recommender(),
            "hybrid": await get_hybrid_recommender(),
            "cache": await get_product_cache()
        }
        
        logger.debug("Recommendation context built successfully")
        return context
        
    except Exception as e:
        logger.error(f"Failed to build recommendation context: {e}")
        raise


# ============================================================================
# UTILITY FUNCTIONS - Helper para testing y debugging
# ============================================================================

def get_all_dependency_providers() -> Dict[str, Any]:
    """
    Get dictionary of all dependency provider functions.
    
    Útil para:
    - Testing: Iterar sobre todas las dependencies
    - Documentation: Listar todas las dependencies disponibles
    - Debugging: Verificar qué dependencies existen
    
    Returns
    -------
    dict
        Dictionary mapeando nombres a provider functions
    
    Examples
    --------
    >>> providers = get_all_dependency_providers()
    >>> for name, provider in providers.items():
    ...     print(f"{name}: {provider.__doc__.split('\\n')[0]}")
    """
    return {
        "tfidf_recommender": get_tfidf_recommender,
        "retail_recommender": get_retail_recommender,
        "hybrid_recommender": get_hybrid_recommender,
        "product_cache": get_product_cache,
        "redis_service": get_redis_service,
        "inventory_service": get_inventory_service,
        "recommendation_context": get_recommendation_context
    }


# ============================================================================
# MODULE METADATA
# ============================================================================

__all__ = [
    # Type Aliases (Annotated)
    "TFIDFRecommenderDep",
    "RetailRecommenderDep",
    "HybridRecommenderDep",
    "ProductCacheDep",
    "RedisServiceDep",
    "InventoryServiceDep",
    
    # Explicit Provider Functions
    "get_tfidf_recommender",
    "get_retail_recommender",
    "get_hybrid_recommender",
    "get_product_cache",
    "get_redis_service",
    "get_inventory_service",
    
    # Composite Dependencies
    "get_recommendation_context",
    
    # Utilities
    "get_all_dependency_providers"
]

__version__ = "1.0.0"
__author__ = "Senior Architecture Team"
__status__ = "Production"
