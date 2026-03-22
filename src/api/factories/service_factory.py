# src/api/factories/service_factory.py - REDIS SINGLETON FIX
"""
Service Factory - Enterprise Dependency Injection FIXED
=======================================================

✅ FIXES APLICADOS:
1. Async lock para singleton thread-safety
2. Timeouts optimizados (3-5 segundos)
3. Circuit breaker pattern
4. Fast-fail strategy

Author: Senior Architecture Team  
Version: 2.1.0 - Redis Enterprise Integration FIXED
"""
import time
import logging
from typing import Optional, TYPE_CHECKING
import asyncio

import asyncpg

# Core services
from src.api.core.redis_service import get_redis_service, RedisService
from src.api.core.store import get_shopify_client
from src.api.core.product_cache import ProductCache

# ✅ TYPE CHECKING: Forward references para evitar circular imports
if TYPE_CHECKING:
    from src.api.core.intelligent_personalization_cache import IntelligentPersonalizationCache
    from src.recommenders.tfidf_recommender import TFIDFRecommender
    from src.recommenders.retail_api import RetailAPIRecommender
    from src.api.core.hybrid_recommender import HybridRecommender
    # Runtime decide dinámicamente (Enhanced o Basic)
    # from src.api.core.enhanced_hybrid_recommender import EnhancedHybridRecommender
    
    # MCP Components
    # from src.api.mcp.client.mcp_client import MCPClient 
    from src.api.mcp.client.mcp_client_enhanced import MCPClientEnhanced as MCPClient
    # from src.api.core.market.adapter import MarketContextManager
    from src.api.mcp.adapters.market_manager import MarketContextManager
    # from src.api.core.market.cache import MarketAwareProductCache
    from src.cache.market_aware.market_cache import MarketAwareProductCache
# MCPPersonalizationEngine type hinting moved to function level to avoid circular imports

# ✅ SOLUCIÓN 3: Redis Configuration Optimizada
try:
    from src.api.core.redis_config_optimized import get_optimized_config_for_service_factory
    REDIS_OPTIMIZATION_AVAILABLE = True
except ImportError:
    REDIS_OPTIMIZATION_AVAILABLE = False

# Business services  
from src.api.inventory.inventory_service import InventoryService
from src.api.inventory.availability_checker import create_availability_checker

from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
from src.api.services.shopify_kb_sync import ShopifyKBSyncService



logger = logging.getLogger(__name__)

class ServiceFactory:
    """
    🏗️ ENTERPRISE SERVICE FACTORY - REDIS SINGLETON FIXED
    
    ✅ FIXES:
    - Async lock para thread safety
    - Timeouts optimizados 
    - Circuit breaker pattern
    - Fast-fail strategy
    """
    
    # ✅ FIX 1: Singleton instances con async lock
    _redis_service: Optional[RedisService] = None
    _inventory_service: Optional[InventoryService] = None
    _product_cache: Optional[ProductCache] = None
    
    # ✅ NEW: MCP Recommender singleton
    _mcp_recommender = None
    _conversation_manager = None
    
    # ✅ NEW: PersonalizationCache singleton (T1 Implementation)
    _personalization_cache: Optional['IntelligentPersonalizationCache'] = None

    # ✅ FASE 3B: MCP Router Dependencies  
    _mcp_client = None
    # _mcp_client = Optional[MCPClient] = None
    _market_context_manager = None
    # _market_context_manager = Optional[MarketContextManager] = None
    _market_cache_service = None
    # _market_cache_service = Optional[MarketContextManager] = None

    _conversation_state_manager = None

    # ✅ FASE 1: Recommender singletons
    _tfidf_recommender: Optional['TFIDFRecommender'] = None
    _retail_recommender: Optional['RetailAPIRecommender'] = None
    _hybrid_recommender: Optional['HybridRecommender'] = None
    
    # ✅ FIX 2: Async lock para thread safety
    _redis_lock: Optional[asyncio.Lock] = None
    _mcp_lock: Optional[asyncio.Lock] = None
    _conversation_lock: Optional[asyncio.Lock] = None
    _personalization_lock: Optional[asyncio.Lock] = None  # ✅ NEW: Lock for PersonalizationCache
    _tfidf_lock: Optional[asyncio.Lock] = None  # ✅ FASE 1
    _retail_lock: Optional[asyncio.Lock] = None  # ✅ FASE 1
    _hybrid_lock: Optional[asyncio.Lock] = None  # ✅ FASE 1
    # ✅ FASE 3B: Locks for MCP Router dependencies
    _mcp_client_lock: Optional[asyncio.Lock] = None
    _market_manager_lock: Optional[asyncio.Lock] = None
    _market_cache_lock: Optional[asyncio.Lock] = None
    _state_manager_lock: Optional[asyncio.Lock] = None
    # Locks for Knowledge Base and DB pool
    _knowledge_base_lock: Optional[asyncio.Lock] = None
    _kb_sync_lock: Optional[asyncio.Lock] = None
    _db_pool_lock: Optional[asyncio.Lock] = None
    _redis_circuit_breaker = {
        "failures": 0,
        "last_failure": 0,
        "circuit_open": False
    }
    # Singletons KB
    _knowledge_base: Optional['ShopifyKnowledgeBase'] = None
    _kb_sync_service: Optional['ShopifyKBSyncService'] = None
    _db_pool: Optional['asyncpg.Pool'] = None
    
    @classmethod
    def _get_redis_lock(cls):
        """Get or create Redis lock (lazy initialization)"""
        if cls._redis_lock is None:
            cls._redis_lock = asyncio.Lock()
        return cls._redis_lock
    
    @classmethod
    def _get_mcp_lock(cls):
        """Get or create MCP lock (lazy initialization)"""
        if cls._mcp_lock is None:
            cls._mcp_lock = asyncio.Lock()
        return cls._mcp_lock
    
    @classmethod
    def _get_conversation_lock(cls):
        """Get or create conversation lock (lazy initialization)"""
        if cls._conversation_lock is None:
            cls._conversation_lock = asyncio.Lock()
        return cls._conversation_lock
    
    @classmethod
    def _get_personalization_lock(cls):
        """Get or create personalization cache lock (lazy initialization)"""
        if cls._personalization_lock is None:
            cls._personalization_lock = asyncio.Lock()
        return cls._personalization_lock
    
    @classmethod
    def _get_tfidf_lock(cls):
        """Get or create TF-IDF lock (lazy initialization)"""  
        if cls._tfidf_lock is None:
            cls._tfidf_lock = asyncio.Lock()
        return cls._tfidf_lock
    
    @classmethod
    def _get_retail_lock(cls):
        """Get or create Retail API lock (lazy initialization)"""
        if cls._retail_lock is None:
            cls._retail_lock = asyncio.Lock()
        return cls._retail_lock
    
    @classmethod
    def _get_hybrid_lock(cls):
        """Get or create Hybrid lock (lazy initialization)"""
        if cls._hybrid_lock is None:
            cls._hybrid_lock = asyncio.Lock()
        return cls._hybrid_lock
    
    @classmethod
    def _get_mcp_client_lock(cls):
        """Get or create MCP Client lock (lazy initialization)"""
        if cls._mcp_client_lock is None:
            cls._mcp_client_lock = asyncio.Lock()
        return cls._mcp_client_lock
    
    @classmethod
    def _get_market_manager_lock(cls):
        """Get or create Market Manager lock (lazy initialization)"""
        if cls._market_manager_lock is None:
            cls._market_manager_lock = asyncio.Lock()
        return cls._market_manager_lock
    
    @classmethod
    def _get_market_cache_lock(cls):
        """Get or create Market Cache lock (lazy initialization)"""
        if cls._market_cache_lock is None:
            cls._market_cache_lock = asyncio.Lock()
        return cls._market_cache_lock
    
    @classmethod
    def _get_state_manager_lock(cls):
        """Get or create State Manager lock (lazy initialization)"""
        if cls._state_manager_lock is None:
            cls._state_manager_lock = asyncio.Lock()
        return cls._state_manager_lock
    
    @classmethod
    def _get_knowledge_base_lock(cls):
        if cls._knowledge_base_lock is None:
            cls._knowledge_base_lock = asyncio.Lock()
        return cls._knowledge_base_lock


    @classmethod
    def _get_kb_sync_lock(cls):
        if cls._kb_sync_lock is None:
            cls._kb_sync_lock = asyncio.Lock()
        return cls._kb_sync_lock


    @classmethod
    def _get_db_pool_lock(cls):
        if cls._db_pool_lock is None:
            cls._db_pool_lock = asyncio.Lock()
        return cls._db_pool_lock

    @classmethod
    async def get_db_pool(cls) -> 'asyncpg.Pool':
        """Get PostgreSQL connection pool singleton.

        CRITICAL — por qué usamos os.environ con fallback a settings:
        Pydantic-settings resuelve variables en orden: class defaults →
        env_file (.env) → os.environ. En Cloud Run, las variables se
        inyectan como variables de sistema (os.environ). Sin embargo, en
        ciertas combinaciones de env_file='.env' + case_sensitive, si el
        archivo .env no existe en el contenedor, Pydantic puede no leer
        os.environ correctamente y retornar el default de la clase
        (e.g. db_host='localhost').

        os.environ.get('DB_HOST') or settings.db_host garantiza:
          1. Prioridad absoluta a variables de sistema / Cloud Run
          2. Fallback a settings si la env var no está definida
          3. Comportamiento idéntico al pool creado en main_unified_redis.py
        """
        lock = cls._get_db_pool_lock()
        
        async with lock:
            if cls._db_pool is None:
                logger.info("Initializing PostgreSQL connection pool (ServiceFactory)...")
                
                try:
                    import os
                    import asyncpg
                    from src.api.core.config import get_settings
                        
                    settings = get_settings()

                    # Leer credenciales con prioridad a os.environ (garantía Cloud Run)
                    db_host     = os.environ.get("DB_HOST")     or settings.db_host
                    db_port     = int(os.environ.get("DB_PORT", str(settings.db_port)))
                    db_user     = os.environ.get("DB_USER")     or settings.db_user
                    db_password = os.environ.get("DB_PASSWORD") or settings.db_password
                    db_name     = os.environ.get("DB_NAME")     or settings.db_name

                    # SSL: requerido en producción (Neon), desactivado en local.
                    db_ssl_env  = os.environ.get("DB_SSL", "").lower()
                    db_ssl      = db_ssl_env in ("true", "1", "yes") if db_ssl_env else settings.db_ssl
                    ssl_param   = "require" if db_ssl else None

                    # Log para diagnóstico — confirma qué valores se usaron
                    logger.info(
                        f"🔒 ServiceFactory DB pool: host={db_host}, port={db_port}, "
                        f"db={db_name}, ssl={'require' if db_ssl else 'disabled'}"
                    )

                    cls._db_pool = await asyncpg.create_pool(
                        host=db_host,
                        port=db_port,
                        user=db_user,
                        password=db_password,
                        database=db_name,
                        ssl=ssl_param,
                        min_size=5,
                        max_size=20,
                        command_timeout=30
                    )
                    
                    logger.info(f"✅ PostgreSQL pool initialized via ServiceFactory (ssl={'require' if db_ssl else 'disabled'})")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to create DB pool: {e}")
                    raise
            
            return cls._db_pool


    @classmethod
    async def get_knowledge_base(cls) -> 'ShopifyKnowledgeBase':
        """Get ShopifyKnowledgeBase singleton."""
        lock = cls._get_knowledge_base_lock()
        
        async with lock:
            if cls._knowledge_base is None:
                logger.info("Initializing ShopifyKnowledgeBase...")
                
                try:
                    from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
                    
                    db_pool = await cls.get_db_pool()
                    redis = await cls.get_redis_service()
                    shopify = get_shopify_client()
                    
                    cls._knowledge_base = ShopifyKnowledgeBase(
                        db=db_pool,
                        redis=redis,
                        shopify=shopify,
                        enable_fallback=True
                    )
                    
                    logger.info("✅ ShopifyKnowledgeBase initialized")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to create ShopifyKnowledgeBase: {e}")
                    raise
            
            return cls._knowledge_base


    @classmethod
    async def get_kb_sync_service(cls) -> 'ShopifyKBSyncService':
        """Get ShopifyKBSyncService singleton."""
        lock = cls._get_kb_sync_lock()
        
        async with lock:
            if cls._kb_sync_service is None:
                logger.info("Initializing ShopifyKBSyncService...")
                
                try:
                    from src.api.services.shopify_kb_sync import ShopifyKBSyncService
                    from src.api.core.store import get_shopify_kb_client  # ✅ CAMBIO: Import correcto
                    
                    db_pool = await cls.get_db_pool()
                    redis = await cls.get_redis_service()
                    shopify = get_shopify_kb_client()  # ✅ CAMBIO: Usar KB client
                    
                    if shopify is None:
                        raise RuntimeError("ShopifyKBClient initialization failed - check .env credentials")
                    
                    cls._kb_sync_service = ShopifyKBSyncService(
                        shopify_client=shopify,
                        db_pool=db_pool,
                        redis_service=redis
                    )
                    
                    logger.info("✅ ShopifyKBSyncService initialized")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to create ShopifyKBSyncService: {e}")
                    raise
            
            return cls._kb_sync_service
        
    @classmethod
    async def get_redis_service(cls) -> RedisService:
        """
        ✅ REDIS SINGLETON FIX - Thread-safe async singleton
        
        FIXES APLICADOS:
        1. Async lock para evitar race conditions
        2. Timeouts optimizados (3-5 segundos)
        3. Circuit breaker para fast-fail
        4. Double-check locking pattern
        """
        # ✅ FIX 3: Circuit breaker check
        if cls._is_circuit_open():
            logger.warning("⚠️ Redis circuit breaker OPEN - returning fallback service")
            return await cls._create_fallback_redis_service()
        
        # ✅ FIX 4: Thread-safe singleton pattern
        if cls._redis_service is None:
            redis_lock = cls._get_redis_lock()
            async with redis_lock:
                # ✅ Double-check locking
                if cls._redis_service is None:
                    try:
                        logger.info("🔄 Initializing RedisService singleton (THREAD-SAFE)")
                        
                        # ✅ FIX 5: Timeout optimizado con Solución 3
                        if REDIS_OPTIMIZATION_AVAILABLE:
                            optimized_config = get_optimized_config_for_service_factory()
                            # timeout = optimized_config.get('socket_connect_timeout', 1.5)
                            # ✅ CAMBIO: Usar timeout más largo para full connection flow
                            timeout = optimized_config.get('socket_timeout', 1.0)  # ← CAMBIAR de 'socket_connect_timeout' a 'socket_timeout'
                            logger.info(f"🔧 Using optimized Redis timeout: {timeout}s")
                        else:
                            # timeout = 3.0
                            timeout = 1.5  # ← CAMBIAR de 3.0 a 1.5s (suficiente para Redis Cloud)
                        redis_service = await asyncio.wait_for(
                            get_redis_service(),
                            timeout=timeout
                        )
                        
                        # ✅ FIX 6: Health check rápido (2 segundos)
                        try:
                            health_result = await asyncio.wait_for(
                                redis_service.health_check(),
                                timeout=2.0  # ← REDUCIDO DE 5s a 2s
                            )
                            logger.info(f"✅ Redis health check OK: {health_result.get('status')}")
                            
                            # ✅ Resetear circuit breaker en éxito
                            cls._reset_circuit_breaker()
                            
                        except asyncio.TimeoutError:
                            logger.warning("⚠️ Redis health check timeout - using service anyway")
                        
                        cls._redis_service = redis_service
                        logger.info("✅ RedisService singleton initialized successfully (THREAD-SAFE)")
                        
                    except asyncio.TimeoutError:
                        logger.warning("⚠️ Redis connection timeout (3s) - attempting fast retry...")
                        
                        # ✅ CRITICAL FIX: Single fast retry con state synchronization
                        try:
                            # retry_timeout = timeout * 0.8 if REDIS_OPTIMIZATION_AVAILABLE else 2.0
                            # ✅ CAMBIO: Aumentar multiplier para dar más tiempo en retry
                            retry_timeout = timeout * 1.5 if REDIS_OPTIMIZATION_AVAILABLE else 1.5  # ← CAMBIAR de 0.8 a 1.5
                            logger.info(f"🔄 Fast retry with timeout: {retry_timeout}s")
                            
                            # ✅ FIX: Get existing instance and force reconnection
                            redis_service = await asyncio.wait_for(
                                get_redis_service(),
                                timeout=retry_timeout
                            )
                            
                            # ✅ CRITICAL: Force connection state update in existing instance
                            if redis_service:
                                logger.info("🔄 Forcing connection state synchronization...")
                                connection_success = await asyncio.wait_for(
                                    redis_service._ensure_connection(),
                                    timeout=retry_timeout
                                )
                                
                                if connection_success:
                                    logger.info("✅ Redis connection AND state successfully synchronized")
                                    cls._redis_service = redis_service
                                    cls._reset_circuit_breaker()
                                else:
                                    logger.error("❌ Redis state synchronization failed")
                                    cls._record_circuit_failure()
                                    cls._redis_service = await cls._create_fallback_redis_service()
                            else:
                                logger.error("❌ Redis service creation failed on retry")
                                cls._record_circuit_failure()
                                cls._redis_service = await cls._create_fallback_redis_service()
                            
                        except Exception as retry_error:
                            logger.error(f"❌ Redis fast retry failed: {retry_error}")
                            cls._record_circuit_failure()
                            cls._redis_service = await cls._create_fallback_redis_service()
                            
                    except Exception as e:
                        logger.error(f"❌ Redis initialization failed: {e}")
                        cls._record_circuit_failure()
                        cls._redis_service = await cls._create_fallback_redis_service()
        
        return cls._redis_service
    
    @classmethod
    def _is_circuit_open(cls) -> bool:
        """
        ✅ FIX 8: Circuit breaker implementation
        
        Returns:
            True si el circuit breaker está abierto (no intentar Redis)
        """
        circuit = cls._redis_circuit_breaker
        
        # Si hay menos de 3 fallos, circuit cerrado
        if circuit["failures"] < 3:
            return False
        
        # Si han pasado más de 60 segundos, intentar de nuevo
        if time.time() - circuit["last_failure"] > 60:
            circuit["circuit_open"] = False
            circuit["failures"] = 0
            return False
        
        return circuit["circuit_open"]
    
    @classmethod
    def _record_circuit_failure(cls):
        """Record circuit breaker failure"""
        circuit = cls._redis_circuit_breaker
        circuit["failures"] += 1
        circuit["last_failure"] = time.time()
        
        if circuit["failures"] >= 3:
            circuit["circuit_open"] = True
            logger.warning(f"⚠️ Redis circuit breaker OPENED after {circuit['failures']} failures")
    
    @classmethod
    def _reset_circuit_breaker(cls):
        """Reset circuit breaker on success"""
        cls._redis_circuit_breaker = {
            "failures": 0,
            "last_failure": 0,
            "circuit_open": False
        }
    
    @classmethod
    async def _create_fallback_redis_service(cls):
        """
        ✅ FIX 9: Fallback service mejorado
        
        Crea un servicio Redis fallback que no bloquea la aplicación
        """
        try:
            # Intentar crear RedisService básico
            from src.api.core.redis_service import RedisService
            fallback_service = RedisService()
            logger.info("✅ Fallback Redis service created (no connection required)")
            return fallback_service
            
        except Exception as e:
            logger.error(f"❌ Could not create fallback Redis service: {e}")
            return cls._create_mock_redis_service()

    @classmethod
    def _create_mock_redis_service(cls):
        """
        ✅ FIX 10: Mock service como último recurso
        """
        class MockRedisService:
            """Minimal mock Redis service for last resort fallback"""
            
            async def health_check(self):
                return {
                    "status": "fallback_mock",
                    "message": "Mock Redis service - no actual Redis connection",
                    "timestamp": time.time()
                }
            
            def get_stats(self):
                return {
                    "status": "fallback_mock",
                    "connections": 0,
                    "memory_usage": 0
                }
            
            async def get(self, key: str):
                return None
            
            async def set(self, key: str, value: str, ttl: int = None):
                return False
            
            async def delete(self, key: str):
                return False
        
        logger.warning("⚠️ Using mock Redis service as last resort fallback")
        return MockRedisService()
    
    # ============================================================================
    # ✅ REST OF METHODS REMAIN THE SAME (but now use fixed Redis singleton)
    # ============================================================================
    
    @classmethod
    async def create_inventory_service(cls) -> InventoryService:
        """
        ✅ Factory para InventoryService usando Redis singleton fixed
        """
        try:
            redis_service = await cls.get_redis_service()
            inventory_service = InventoryService(redis_service=redis_service)
            await inventory_service.ensure_ready()
            logger.info("✅ InventoryService created with fixed RedisService singleton")
            return inventory_service
            
        except Exception as e:
            logger.warning(f"⚠️ RedisService unavailable, creating InventoryService in fallback mode: {e}")
            inventory_service = InventoryService(redis_service=None)
            await inventory_service.ensure_ready()
            return inventory_service
    
    @classmethod
    async def get_inventory_service_singleton(cls) -> InventoryService:
        """Get InventoryService singleton"""
        if cls._inventory_service is None:
            cls._inventory_service = await cls.create_inventory_service()
            logger.info("✅ InventoryService singleton initialized")
        return cls._inventory_service
    
    @classmethod
    async def create_product_cache(cls, local_catalog=None) -> ProductCache:
        """
        ✅ Factory para ProductCache usando RedisService enterprise
        
        Args:
            local_catalog: TFIDFRecommender u otro catálogo local con product_data
                          Si None, ProductCache funcionará solo con Redis/Shopify
        
        Returns:
            ProductCache configurado con todas las dependencies
            
        CRITICAL FIX (T1):
            Este método DEBE recibir local_catalog para que DiversityAwareCache
            use categorías dinámicas del catálogo real.
        """
        try:
            redis_service = await cls.get_redis_service()
            shopify_client = get_shopify_client()
            
            # ✅ LOGGING: Verificar si local_catalog fue provisto
            if local_catalog:
                catalog_info = "provided"
                if hasattr(local_catalog, 'loaded'):
                    catalog_info = f"loaded={local_catalog.loaded}"
                if hasattr(local_catalog, 'product_data'):
                    product_count = len(local_catalog.product_data) if local_catalog.product_data else 0
                    catalog_info += f", products={product_count}"
                logger.info(f"✅ Creating ProductCache with local_catalog: {catalog_info}")
            else:
                logger.warning("⚠️ Creating ProductCache WITHOUT local_catalog - will use Redis/Shopify only")
            
            # ✅ MIGRACIÓN: Usar RedisService en lugar de cliente directo
            product_cache = ProductCache(
                redis_service=redis_service,  # ✅ CAMBIO: redis_service en lugar de redis_client
                local_catalog=local_catalog,  # ✅ CRITICAL: Pass local_catalog parameter
                shopify_client=shopify_client,
                ttl_seconds=86400,  # ✅ CACHE INCONSISTENCY FIX: Mismo TTL que main (24h)
                prefix="product:"  # ✅ CACHE INCONSISTENCY FIX: Usar mismo prefijo que main
            )
            
            await product_cache.start_background_tasks()
            logger.info("✅ ProductCache created with enterprise RedisService architecture")
            return product_cache
            
        except Exception as e:
            logger.error(f"❌ ProductCache initialization failed: {e}")
            raise RuntimeError(f"Product cache service unavailable: {e}")
    
    @classmethod
    async def get_product_cache_singleton(cls, local_catalog=None) -> ProductCache:
        """
        Get ProductCache singleton.
        
        Args:
            local_catalog: TFIDFRecommender u otro catálogo local.
                          Solo se usa en la primera inicialización.
                          Llamadas subsecuentes ignoran este parámetro (singleton).
        
        Returns:
            ProductCache singleton instance
            
        Usage:
            # Primera llamada (desde main):
            cache = await ServiceFactory.get_product_cache_singleton(local_catalog=tfidf_recommender)
            
            # Llamadas subsecuentes (reusa singleton):
            cache = await ServiceFactory.get_product_cache_singleton()
        """
        if cls._product_cache is None:
            cls._product_cache = await cls.create_product_cache(local_catalog=local_catalog)
            logger.info("✅ ProductCache singleton initialized")
        return cls._product_cache
    
    # ============================================================================
    # 🤖 RECOMMENDER SINGLETONS - Fase 1 Implementation
    # ============================================================================
    
    @classmethod
    async def get_tfidf_recommender(cls, auto_load: bool = False) -> 'TFIDFRecommender':
        """
        ✅ FASE 1: Get TF-IDF recommender singleton.
        
        Args:
            auto_load: If True, load model immediately (for tests).
                      If False, return unloaded instance (compatible with StartupManager).
        
        Returns:
            TFIDFRecommender instance (loaded or unloaded based on auto_load)
        
        Examples:
            # For production (with StartupManager):
            recommender = await ServiceFactory.get_tfidf_recommender()
            # StartupManager will call recommender.load() later
            
            # For testing (immediate load):
            recommender = await ServiceFactory.get_tfidf_recommender(auto_load=True)
            # Model is loaded and ready to use
        
        Author: Senior Architecture Team
        Date: 2025-10-15
        Version: 1.0.0 - Fase 1 Implementation
        """
        from src.recommenders.tfidf_recommender import TFIDFRecommender
        from src.api.core.config import get_settings
        
        if cls._tfidf_recommender is None:
            tfidf_lock = cls._get_tfidf_lock()
            async with tfidf_lock:
                # Double-check locking pattern
                if cls._tfidf_recommender is None:
                    settings = get_settings()
                    model_path = getattr(settings, 'tfidf_model_path', 'data/tfidf_model.pkl')
                    
                    logger.info(f"✅ Creating TF-IDF recommender singleton: {model_path}")
                    cls._tfidf_recommender = TFIDFRecommender(model_path=model_path)
                    
                    # Optional: Auto-load for testing scenarios
                    if auto_load:
                        logger.info("🔄 Auto-loading TF-IDF model...")
                        import os
                        if os.path.exists(model_path):
                            success = await cls._tfidf_recommender.load()
                            if success:
                                product_count = len(cls._tfidf_recommender.product_data) if hasattr(cls._tfidf_recommender, 'product_data') else 0
                                logger.info(f"✅ TF-IDF model auto-loaded: {product_count} products")
                            else:
                                logger.warning("⚠️ TF-IDF auto-load failed")
                        else:
                            logger.warning(f"⚠️ Model file not found: {model_path}")
        
        return cls._tfidf_recommender
    
    @classmethod
    async def get_retail_recommender(cls) -> 'RetailAPIRecommender':
        """
        ✅ FASE 1: Get Google Retail API recommender singleton.
        
        Returns:
            RetailAPIRecommender instance configured with project settings
        
        Note:
            First call may take 4+ seconds due to Google Cloud service
            initialization. This is normal and expected behavior.
            
            ALTS warnings are normal when running outside GCP:
            "ALTS creds ignored. Not running on GCP"
        
        Author: Senior Architecture Team
        Date: 2025-10-15
        Version: 1.0.0 - Fase 1 Implementation
        """
        from src.recommenders.retail_api import RetailAPIRecommender
        from src.api.core.config import get_settings
        
        if cls._retail_recommender is None:
            retail_lock = cls._get_retail_lock()
            async with retail_lock:
                # Double-check locking
                if cls._retail_recommender is None:
                    settings = get_settings()
                    
                    logger.info("✅ Creating Retail API recommender singleton")
                    logger.info(f"   Project: {settings.google_project_number}")
                    logger.info(f"   Location: {settings.google_location}")
                    logger.info(f"   Catalog: {settings.google_catalog}")
                    
                    cls._retail_recommender = RetailAPIRecommender(
                        project_number=settings.google_project_number,
                        location=settings.google_location,
                        catalog=settings.google_catalog,
                        serving_config_id=settings.google_serving_config
                    )
                    
                    logger.info("✅ Retail API recommender singleton created successfully")
        
        return cls._retail_recommender
    
    @classmethod
    async def get_hybrid_recommender(
        cls,
        content_recommender=None,
        retail_recommender=None,
        product_cache=None
    ) -> 'HybridRecommender':
        """
        ✅ FASE 1: Get Hybrid recommender singleton with auto-wiring.
        
        Args:
            content_recommender: Optional TF-IDF recommender (auto-fetched if None)
            retail_recommender: Optional Retail recommender (auto-fetched if None)
            product_cache: Optional ProductCache (auto-fetched if None)
        
        Returns:
            HybridRecommender with all dependencies wired automatically
        
        Note:
            When dependencies are None, they are automatically fetched from
            ServiceFactory singletons. This ensures consistency and reduces
            boilerplate code.
            
        Examples:
            # Auto-wiring (recommended):
            hybrid = await ServiceFactory.get_hybrid_recommender()
            
            # Manual injection (for testing):
            hybrid = await ServiceFactory.get_hybrid_recommender(
                content_recommender=mock_tfidf,
                retail_recommender=mock_retail
            )
        
        Author: Senior Architecture Team
        Date: 2025-10-15
        Version: 1.0.0 - Fase 1 Implementation
        """
        from src.api.core.config import get_settings
        
        if cls._hybrid_recommender is None:
            hybrid_lock = cls._get_hybrid_lock()
            async with hybrid_lock:
                # Double-check locking
                if cls._hybrid_recommender is None:
                    settings = get_settings()
                    
                    logger.info("✅ Creating Hybrid recommender singleton with auto-wiring")
                    
                    # ✅ AUTO-WIRING: Fetch dependencies from ServiceFactory
                    if content_recommender is None:
                        logger.info("   🔄 Auto-fetching TF-IDF recommender...")
                        content_recommender = await cls.get_tfidf_recommender(auto_load=False)
                    
                    if retail_recommender is None:
                        logger.info("   🔄 Auto-fetching Retail recommender...")
                        retail_recommender = await cls.get_retail_recommender()
                    
                    if product_cache is None:
                        logger.info("   🔄 Auto-fetching ProductCache...")
                        product_cache = await cls.get_product_cache_singleton()
                    
                    # ✅ Prefer EnhancedHybridRecommender when product_cache is available
                    try:
                        settings = get_settings()
                        if product_cache is not None:
                            try:
                                from src.api.core.enhanced_hybrid_recommender import (
                                    EnhancedHybridRecommender,
                                    EnhancedHybridRecommenderWithExclusion
                                )
                                if settings.exclude_seen_products:
                                    logger.info("   Using EnhancedHybridRecommenderWithExclusion (product_cache available)")
                                    cls._hybrid_recommender = EnhancedHybridRecommenderWithExclusion(
                                        content_recommender=content_recommender,
                                        retail_recommender=retail_recommender,
                                        product_cache=product_cache,
                                        content_weight=settings.content_weight
                                    )
                                else:
                                    logger.info("   Using EnhancedHybridRecommender (product_cache available)")
                                    cls._hybrid_recommender = EnhancedHybridRecommender(
                                        content_recommender=content_recommender,
                                        retail_recommender=retail_recommender,
                                        product_cache=product_cache,
                                        content_weight=settings.content_weight
                                    )
                            except ImportError as ie:
                                logger.warning(f"⚠️ EnhancedHybridRecommender not available, falling back: {ie}")
                                # Fallback to basic Hybrid implementations
                                from src.api.core.hybrid_recommender import HybridRecommender, HybridRecommenderWithExclusion
                                if settings.exclude_seen_products:
                                    logger.info("   Using HybridRecommenderWithExclusion (fallback)")
                                    cls._hybrid_recommender = HybridRecommenderWithExclusion(
                                        content_recommender=content_recommender,
                                        retail_recommender=retail_recommender,
                                        content_weight=settings.content_weight,
                                        product_cache=product_cache
                                    )
                                else:
                                    logger.info("   Using HybridRecommender (basic, fallback)")
                                    cls._hybrid_recommender = HybridRecommender(
                                        content_recommender=content_recommender,
                                        retail_recommender=retail_recommender,
                                        content_weight=settings.content_weight,
                                        product_cache=product_cache
                                    )
                        else:
                            # No product_cache, use basic Hybrid implementations
                            from src.api.core.hybrid_recommender import HybridRecommender, HybridRecommenderWithExclusion
                            if settings.exclude_seen_products:
                                logger.info("   Using HybridRecommenderWithExclusion (no cache)")
                                cls._hybrid_recommender = HybridRecommenderWithExclusion(
                                    content_recommender=content_recommender,
                                    retail_recommender=retail_recommender,
                                    content_weight=settings.content_weight,
                                    product_cache=product_cache
                                )
                            else:
                                logger.info("   Using HybridRecommender (basic, no cache)")
                                cls._hybrid_recommender = HybridRecommender(
                                    content_recommender=content_recommender,
                                    retail_recommender=retail_recommender,
                                    content_weight=settings.content_weight,
                                    product_cache=product_cache
                                )
                    
                    except Exception:
                        # In case of any unexpected error, ensure we still create a basic HybridRecommender
                        from src.api.core.hybrid_recommender import HybridRecommender
                        logger.warning("⚠️ Error creating enhanced hybrid recommender, creating basic HybridRecommender as last resort")
                        cls._hybrid_recommender = HybridRecommender(
                            content_recommender=content_recommender,
                            retail_recommender=retail_recommender,
                            content_weight=settings.content_weight,
                            product_cache=product_cache
                        )
                    
                    logger.info("✅ Hybrid recommender singleton created successfully")
                    logger.info(f"   Content weight: {settings.content_weight}")
                    logger.info(f"   Exclude seen products: {settings.exclude_seen_products}")
        
        return cls._hybrid_recommender
    
    @classmethod
    async def get_personalization_cache(
        cls,
        default_ttl: int = 300,
        force_recreate: bool = False
    ) -> 'IntelligentPersonalizationCache':
        """
        ✅ ENTERPRISE FACTORY: PersonalizationCache con dependency injection completa
        
        Orquesta todas las dependencies:
        1. RedisService (singleton, thread-safe)
        2. ProductCache (singleton con local_catalog)
        3. DiversityAwareCache (configurado con local_catalog real)
        4. IntelligentPersonalizationCache (constructor injection)
        
        Esta implementación resuelve el Problema Crítico #1:
        - Inyecta local_catalog dinámicamente desde ProductCache
        - DiversityAwareCache usa categorías reales del catálogo (no hardcoded)
        - Patrón Opción B implementado correctamente
        
        Args:
            default_ttl: TTL por defecto para cache (300s = 5 minutos)
            force_recreate: Forzar recreación (useful for tests)
            
        Returns:
            IntelligentPersonalizationCache completamente configurado
            
        Usage:
            # En endpoint o servicio:
            cache = await ServiceFactory.get_personalization_cache()
            result = await cache.get_cached_personalization(...)
        
        Author: Senior Architecture Team
        Date: 2025-10-10
        Version: 1.0.0 - T1 Implementation
        """
        # ✅ Thread-safe singleton pattern
        if cls._personalization_cache is None or force_recreate:
            lock = cls._get_personalization_lock()
            async with lock:
                # Double-check locking
                if cls._personalization_cache is None or force_recreate:
                    try:
                        logger.info("🏗️ Building PersonalizationCache via enterprise factory...")
                        
                        # ===== DEPENDENCY 1: RedisService =====
                        redis_service = await cls.get_redis_service()
                        logger.info("  ✅ RedisService obtained")
                        
                        # ===== DEPENDENCY 2: ProductCache con local_catalog =====
                        product_cache = None
                        local_catalog = None
                        
                        try:
                            product_cache = await cls.get_product_cache_singleton()
                            
                            # ✅ CRITICAL: Extract local_catalog from ProductCache
                            if product_cache and hasattr(product_cache, 'local_catalog'):
                                local_catalog = product_cache.local_catalog
                                logger.info(f"  ✅ ProductCache obtained, local_catalog: {local_catalog is not None}")
                                
                                # ✅ Verify catalog has data
                                if local_catalog and hasattr(local_catalog, 'product_data'):
                                    product_count = len(local_catalog.product_data) if local_catalog.product_data else 0
                                    logger.info(f"  ✅ LocalCatalog loaded with {product_count} products")
                                else:
                                    logger.warning("  ⚠️ LocalCatalog exists but has no product_data")
                            else:
                                logger.warning("  ⚠️ ProductCache has no local_catalog attribute")
                                
                        except Exception as pc_error:
                            logger.warning(f"  ⚠️ ProductCache not available: {pc_error}")
                            logger.warning("  ⚠️ Will use fallback categories in DiversityAwareCache")
                        
                        # ===== DEPENDENCY 3: DiversityAwareCache con local_catalog =====
                        from src.api.core.diversity_aware_cache import create_diversity_aware_cache
                        
                        # ✅ CRITICAL: Pass product_cache AND local_catalog to factory
                        diversity_cache = await create_diversity_aware_cache(
                            redis_service=redis_service,
                            default_ttl=default_ttl,
                            product_cache=product_cache,      # ✅ Pass ProductCache
                            local_catalog=local_catalog        # ✅ Pass extracted local_catalog
                        )
                        
                        if local_catalog and hasattr(local_catalog, 'product_data'):
                            logger.info("  ✅ DiversityAwareCache created with DYNAMIC categories from catalog")
                        else:
                            logger.warning("  ⚠️ DiversityAwareCache created with FALLBACK hardcoded categories")
                        
                        # ===== DEPENDENCY 4: IntelligentPersonalizationCache con constructor injection =====
                        # ✅ LAZY IMPORT: Avoid circular import issues
                        from src.api.core.intelligent_personalization_cache import IntelligentPersonalizationCache
                        
                        # ✅ CONSTRUCTOR INJECTION: Pass diversity_cache directly
                        cls._personalization_cache = IntelligentPersonalizationCache(
                            redis_service=redis_service,
                            default_ttl=default_ttl,
                            diversity_cache=diversity_cache  # ✅ CRITICAL: Constructor injection
                        )
                        
                        logger.info("✅ PersonalizationCache singleton created via enterprise factory")
                        logger.info(f"   - Redis: {'Connected' if redis_service else 'None'}")
                        logger.info(f"   - ProductCache: {'Available' if product_cache else 'Unavailable'}")
                        logger.info(f"   - LocalCatalog: {'Loaded' if local_catalog else 'Fallback'}")
                        logger.info(f"   - DiversityAwareCache: {'Dynamic categories' if local_catalog else 'Hardcoded fallback'}")
                        
                    except Exception as e:
                        logger.error(f"❌ Error creating PersonalizationCache: {e}")
                        logger.error(f"   Traceback: {e.__class__.__name__}: {str(e)}")
                        
                        # ✅ Fallback graceful
                        logger.warning("⚠️ Creating PersonalizationCache with fallback (no dependencies)")
                        
                        from src.api.core.intelligent_personalization_cache import IntelligentPersonalizationCache
                        
                        cls._personalization_cache = IntelligentPersonalizationCache(
                            redis_service=redis_service,
                            default_ttl=default_ttl
                            # ⚠️ No diversity_cache injection - will create internally with fallback
                        )
                        
                        logger.warning("⚠️ PersonalizationCache created in fallback mode")
        
        return cls._personalization_cache
    
    @classmethod
    async def create_availability_checker(cls):
        """
        ✅ Factory para AvailabilityChecker con dependency injection enterprise
        """
        inventory_service = await cls.get_inventory_service_singleton()
        return create_availability_checker(inventory_service)
    
    @classmethod
    async def health_check_all_services(cls) -> dict:
        """
        ✅ Health check con circuit breaker awareness
        """
        health_status = {
            "timestamp": time.time(),
            "factory": "ServiceFactory",
            "version": "2.1.0-FIXED",
            "circuit_breaker": cls._redis_circuit_breaker,
            "services": {}
        }
        
        try:
            # Check RedisService
            redis_service = await cls.get_redis_service()
            redis_health = await redis_service.health_check()
            health_status["services"]["redis_service"] = redis_health
            
            # Check other services...
            # (rest of implementation same as before)
            
        except Exception as e:
            logger.error(f"❌ ServiceFactory health check failed: {e}")
            health_status["overall_status"] = "unhealthy"
            health_status["error"] = str(e)
        
        return health_status
    
    @classmethod
    async def shutdown_all_services(cls):
        """
        ✅ Shutdown limpio con cleanup de locks
        """
        logger.info("🔄 ServiceFactory shutdown initiated...")
        
        # Cleanup ProductCache
        if cls._product_cache:
            try:
                if hasattr(cls._product_cache, 'health_task') and cls._product_cache.health_task:
                    cls._product_cache.health_task.cancel()
                logger.info("✅ ProductCache shutdown completed")
            except Exception as e:
                logger.warning(f"⚠️ ProductCache shutdown error: {e}")
        
        # ✅ Close Redis connections properly
        if cls._redis_service:
            try:
                if hasattr(cls._redis_service, '_client') and cls._redis_service._client:
                    await cls._redis_service._client.close()
                logger.info("✅ Redis connections closed")
            except Exception as e:
                logger.warning(f"⚠️ Redis shutdown error: {e}")
        
        # ✅ Cleanup MCP components
        if cls._mcp_recommender:
            try:
                # Any cleanup needed for MCP components
                logger.info("✅ MCP recommender cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ MCP shutdown error: {e}")
        
        if cls._conversation_manager:
            try:
                # Any cleanup needed for conversation manager
                logger.info("✅ Conversation manager cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ Conversation manager shutdown error: {e}")
        
        # ✅ Cleanup PersonalizationCache
        if cls._personalization_cache:
            try:
                # Any cleanup needed for personalization cache
                logger.info("✅ PersonalizationCache cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ PersonalizationCache shutdown error: {e}")
        # ✅ FASE 3B: Cleanup MCP Router dependencies
        if cls._mcp_client:
            try:
                logger.info("✅ MCP Client cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ MCP Client shutdown error: {e}")
        
        if cls._market_context_manager:
            try:
                logger.info("✅ Market Context Manager cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ Market Context Manager shutdown error: {e}")
        
        if cls._market_cache_service:
            try:
                logger.info("✅ Market Cache Service cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ Market Cache Service shutdown error: {e}")
        
        if cls._conversation_state_manager:
            try:
                logger.info("✅ Conversation State Manager cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ State Manager shutdown error: {e}")

        # Reset singletons and locks
        cls._redis_service = None
        cls._inventory_service = None
        cls._product_cache = None
        cls._mcp_recommender = None
        cls._conversation_manager = None
        cls._personalization_cache = None  # ✅ NEW: Reset personalization cache
        cls._tfidf_recommender = None  # ✅ FASE 1: Reset TF-IDF
        cls._retail_recommender = None  # ✅ FASE 1: Reset Retail API
        cls._hybrid_recommender = None  # ✅ FASE 1: Reset Hybrid
        cls._redis_lock = None  # ← Reset lock
        cls._mcp_lock = None  # ← Reset MCP lock
        cls._conversation_lock = None  # ← Reset conversation lock
        cls._personalization_lock = None  # ✅ NEW: Reset personalization lock
        cls._tfidf_lock = None  # ✅ FASE 1: Reset TF-IDF lock
        cls._retail_lock = None  # ✅ FASE 1: Reset Retail lock
        cls._hybrid_lock = None  # ✅ FASE 1: Reset Hybrid lock
        # ✅ FASE 3B: Reset MCP Router singletons
        cls._mcp_client = None
        cls._market_context_manager = None
        cls._market_cache_service = None
        cls._conversation_state_manager = None
        cls._mcp_client_lock = None
        cls._market_manager_lock = None
        cls._market_cache_lock = None
        cls._state_manager_lock = None

        cls._reset_circuit_breaker()  # ← Reset circuit breaker
        
        logger.info("✅ ServiceFactory shutdown completed (ALL CLEAN)")

        
    @classmethod
    async def get_conversation_manager(cls):
        """Get the optimized conversation manager for Claude integration"""
        if cls._conversation_manager is None:
            conversation_lock = cls._get_conversation_lock()
            async with conversation_lock:
                if cls._conversation_manager is None:
                    try:
                        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
                        from src.api.core.config import get_settings
                        
                        settings = get_settings()
                        cls._conversation_manager = OptimizedConversationAIManager(
                            anthropic_api_key=settings.anthropic_api_key
                        )
                        logger.info("✅ OptimizedConversationAIManager initialized successfully")
                    except ImportError as e:
                        logger.warning(f"⚠️ OptimizedConversationAIManager not found, falling back to ConversationAIManager: {e}")
                        from src.api.integrations.ai.ai_conversation_manager import ConversationAIManager
                        from src.api.core.config import get_settings
                        
                        settings = get_settings()
                        cls._conversation_manager = ConversationAIManager(
                            anthropic_api_key=settings.anthropic_api_key
                        )
                        logger.info("✅ ConversationAIManager (fallback) initialized successfully")
        return cls._conversation_manager

    @classmethod
    async def get_mcp_recommender(cls):
        """Get MCP recommender singleton with dependencies.
        
        CRÍTICO: Se debe pasar anthropic_client al constructor.
        Sin él, self.claude = None y todas las llamadas a Claude
        fallan con 'NoneType has no attribute messages'.
        """
        if cls._mcp_recommender is None:
            mcp_lock = cls._get_mcp_lock()
            async with mcp_lock:
                if cls._mcp_recommender is None:
                    try:
                        import os
                        from anthropic import AsyncAnthropic
                        from src.api.mcp.engines.mcp_personalization_engine import MCPPersonalizationEngine

                        # Obtener dependencias
                        redis_service = await cls.get_redis_service()
                        conversation_manager = await cls.get_conversation_manager()

                        # Crear cliente Anthropic warm — se reutiliza en todas las requests.
                        # Este es el cliente que MCPPersonalizationEngine usa en self.claude.
                        #
                        # HTTP/2 DESACTIVADO (http2=False):
                        # AsyncAnthropic usa HTTP/2 por defecto. En Cloud Run, las conexiones
                        # HTTP/2 salientes son más propensas a fallar con "Connection error"
                        # cuando el NAT de GCP cierra el estado TCP tras períodos de inactividad.
                        # HTTP/1.1 con keep-alive es más resiliente en este entorno.
                        #
                        # TIMEOUT EXPLÍCITO:
                        # httpx.Timeout configura connect=10s (establecer la conexión TCP/TLS)
                        # y read=25s (leer la respuesta). Sin esto, la SDK usa defaults que
                        # pueden ser demasiado generosos o no respetarse en todos los paths.
                        import httpx
                        # Strip whitespace/newlines defensively — Secret Manager puede
                        # inyectar la clave con \r\n al final si fue creada desde
                        # Windows o con un editor que añade newline al guardar.
                        # httpx lanza LocalProtocolError si el header contiene \r\n.
                        anthropic_api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip() or None
                        if not anthropic_api_key:
                            logger.error("❌ ANTHROPIC_API_KEY not set — MCPPersonalizationEngine will have claude=None")
                        else:
                            logger.info(f"✅ ANTHROPIC_API_KEY loaded (length={len(anthropic_api_key)}, ends_with_newline=False)")
                        # anthropic_client = AsyncAnthropic(api_key=anthropic_api_key) if anthropic_api_key else None
                        # ────────────────────────────────────────────────────────────────
                        # CONFIGURACIÓN HTTPX PARA CLOUD RUN (18/03/2026)
                        # ────────────────────────────────────────────────────────────────
                        #
                        # PROBLEMA RAIZ del timeout MCP (~3.3s):
                        # AsyncAnthropic crea conexiones TCP lazy. En Cloud Run, el
                        # NAT de GCP cierra estados TCP salientes inactivos. El warm-up
                        # del PASO 8.5 establece la conexión, pero si la primera request
                        # real llega >keepalive_expiry segundos después, httpx descarta
                        # la conexión del pool y el siguiente intento hace un nuevo
                        # TCP connect que tarda ~1.5s y falla en Cloud Run.
                        #
                        # SOLUCIÓN PARTE A — keepalive_expiry=300s:
                        # El startup completo tarda ~90s. Las primeras requests pueden
                        # llegar 30-120s después. 300s da margen suficiente para que
                        # la conexión warm del PASO 8.5 siga viva cuando llegue la
                        # primera request real. La tarea keep-alive periódica del
                        # lifespan (PASO 8.6) renueva la conexión cada 90s indefinidamente.
                        #
                        # max_retries=0: el SDK no reintenta solo; el loop de
                        # _generate_claude_personalized_response ya maneja reintentos
                        # con sleep(50ms) entre intentos.
                        # ────────────────────────────────────────────────────────────────
                        anthropic_client = AsyncAnthropic(
                            api_key=anthropic_api_key,
                            max_retries=0,        # fallo rápido: el loop interno maneja reintentos
                            http_client=httpx.AsyncClient(
                                http2=False,      # HTTP/1.1: más resiliente en Cloud Run NAT
                                timeout=httpx.Timeout(
                                    connect=10.0,  # tiempo máx para establecer TCP/TLS
                                    read=25.0,     # tiempo máx para leer respuesta de Claude
                                    write=10.0,
                                    pool=5.0
                                ),
                                limits=httpx.Limits(
                                    max_keepalive_connections=5,
                                    max_connections=10,
                                    # 300s: cubre startup (~90s) + margen hasta primera request.
                                    # La tarea keep-alive periódica (PASO 8.6 en lifespan)
                                    # renueva la conexión cada 90s y mantiene el pool activo
                                    # indefinidamente mientras el servidor esté vivo.
                                    keepalive_expiry=300.0  # ← FIX: 120s → 300s
                                )
                            )
                        ) if anthropic_api_key else None

                        cls._mcp_recommender = MCPPersonalizationEngine(
                            redis_service=redis_service,
                            conversation_manager=conversation_manager,
                            anthropic_client=anthropic_client,  # ← CRÍTICO: evita self.claude = None
                        )
                        logger.info("✅ MCPPersonalizationEngine singleton initialized (claude=%s, http2=False)",
                                    "ready" if anthropic_client else "None — calls will fail")
                    except Exception as e:
                        logger.error(f"❌ Failed to initialize MCPPersonalizationEngine: {e}")
                        raise
        return cls._mcp_recommender

    @classmethod
    async def get_mcp_client(cls) -> 'MCPClient':
        if cls._mcp_client is None:
            lock = cls._get_mcp_client_lock()
            async with lock:
                if cls._mcp_client is None:
                    try:
                        from src.api.core.config import get_settings
                        settings = get_settings()
                        
                        # ✅ TRY ENHANCED FIRST
                        try:
                            from src.api.mcp.client.mcp_client_enhanced import MCPClientEnhanced
                            
                            cls._mcp_client = MCPClientEnhanced(
                                bridge_host=getattr(settings, 'mcp_bridge_host', 'localhost'),
                                bridge_port=getattr(settings, 'mcp_bridge_port', 3001),
                                enable_circuit_breaker=True,
                                enable_local_cache=True,
                                cache_ttl=300
                            )
                            
                        except ImportError:
                            from src.api.mcp.client.mcp_client import MCPClient
                            
                            cls._mcp_client = MCPClient(
                                bridge_host=getattr(settings, 'mcp_bridge_host', 'localhost'),
                                bridge_port=getattr(settings, 'mcp_bridge_port', 3001)
                            )
                            
                    except Exception as e:
                        logger.error(f"❌ Failed: {e}")
                        return None
        
        return cls._mcp_client
    
    @classmethod
    async def get_market_context_manager(cls) -> 'MarketContextManager':
        """
        ✅ FASE 3B: Get Market Context Manager singleton.
        
        Returns:
            MarketContextManager instance or None if unavailable
        """
        if cls._market_context_manager is None:
            lock = cls._get_market_manager_lock()
            async with lock:
                if cls._market_context_manager is None:
                    try:
                        logger.info("✅ Creating Market Context Manager singleton")
                        
                        from src.api.mcp.adapters.market_manager import MarketContextManager
                        from src.api.core.config import get_settings
                        
                        settings = get_settings()
                        redis_service = await cls.get_redis_service()
                        
                        cls._market_context_manager = MarketContextManager(
                            redis_service=redis_service,
                            default_market=getattr(settings, 'default_market', 'US')
                        )
                        
                        await cls._market_context_manager.initialize()
                        
                        logger.info("✅ Market Context Manager singleton created successfully")
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to create Market Context Manager: {e}")
                        return None
    
        return cls._market_context_manager
        
    @classmethod
    async def get_market_cache_service(cls) -> 'MarketAwareProductCache':
        """
        ✅ FASE 3B: Get Market-Aware Product Cache singleton.
        
        Returns:
            MarketAwareProductCache instance or None if unavailable
        """
        if cls._market_cache_service is None:
            lock = cls._get_market_cache_lock()
            async with lock:
                if cls._market_cache_service is None:
                    try:
                        logger.info("✅ Creating Market-Aware Cache singleton")
                        
                        from src.cache.market_aware.market_cache import MarketAwareProductCache
                        
                        redis_service = await cls.get_redis_service()
                        product_cache = await cls.get_product_cache_singleton()
                        
                        cls._market_cache_service = MarketAwareProductCache(
                            redis_service=redis_service,
                            base_product_cache=product_cache,
                            default_ttl=3600
                        )
                        
                        logger.info("✅ Market-Aware Cache singleton created successfully")
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to create Market-Aware Cache: {e}")
                        return None
        
        return cls._market_cache_service
    
    @classmethod
    async def get_conversation_state_manager(cls):
        """
        ✅ FASE 3B: Get Conversation State Manager singleton.
        
        Returns:
            ConversationStateManager instance or None if unavailable
        """
        if cls._conversation_state_manager is None:
            lock = cls._get_state_manager_lock()
            async with lock:
                if cls._conversation_state_manager is None:
                    try:
                        logger.info("✅ Creating Conversation State Manager singleton")
                        
                        from src.api.mcp.conversation_state_manager import MCPConversationStateManager
                        
                        redis_service = await cls.get_redis_service()
                        
                        cls._conversation_state_manager = MCPConversationStateManager(
                            redis_service=redis_service,
                            default_ttl=86400
                        )
                        
                        logger.info("✅ Conversation State Manager singleton created successfully")
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to create Conversation State Manager: {e}")
                        return None
        
        return cls._conversation_state_manager
# ============================================================================
# 🔧 CONVENIENCE FUNCTIONS - Backward Compatibility
# ============================================================================

async def get_inventory_service() -> InventoryService:
    """Convenience function para backward compatibility"""
    return await ServiceFactory.get_inventory_service_singleton()

async def get_product_cache() -> ProductCache:
    """Convenience function para backward compatibility"""
    return await ServiceFactory.get_product_cache_singleton()

async def get_availability_checker():
    """Convenience function para backward compatibility"""
    return await ServiceFactory.create_availability_checker()

async def get_mcp_recommender():
    """Convenience function para MCP recommender"""
    return await ServiceFactory.get_mcp_recommender()

async def get_conversation_manager():
    """Convenience function para conversation manager"""
    return await ServiceFactory.get_conversation_manager()

async def health_check_services() -> dict:
    """Convenience function para health checks"""
    return await ServiceFactory.health_check_all_services()

async def get_personalization_cache():
    """Convenience function para PersonalizationCache"""
    return await ServiceFactory.get_personalization_cache()

# ============================================================================
# 🔧 FASE 3B: MCP Router Convenience Functions
# ============================================================================

async def get_mcp_client():
    """Convenience function for MCP Client"""
    return await ServiceFactory.get_mcp_client()

async def get_market_context_manager():
    """Convenience function for Market Context Manager"""
    return await ServiceFactory.get_market_context_manager()

async def get_market_cache_service():
    """Convenience function for Market-Aware Cache"""
    return await ServiceFactory.get_market_cache_service()

async def get_conversation_state_manager_service():
    """Convenience function for Conversation State Manager"""
    return await ServiceFactory.get_conversation_state_manager()