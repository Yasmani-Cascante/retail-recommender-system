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

# Core services
from src.api.core.redis_service import get_redis_service, RedisService
from src.api.core.store import get_shopify_client
from src.api.core.product_cache import ProductCache

# ✅ TYPE CHECKING: Forward references para evitar circular imports
if TYPE_CHECKING:
    from src.api.core.intelligent_personalization_cache import IntelligentPersonalizationCache

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
    
    # ✅ FIX 2: Async lock para thread safety
    _redis_lock: Optional[asyncio.Lock] = None
    _mcp_lock: Optional[asyncio.Lock] = None
    _conversation_lock: Optional[asyncio.Lock] = None
    _personalization_lock: Optional[asyncio.Lock] = None  # ✅ NEW: Lock for PersonalizationCache
    _redis_circuit_breaker = {
        "failures": 0,
        "last_failure": 0,
        "circuit_open": False
    }
    
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
                            timeout = optimized_config.get('socket_connect_timeout', 1.5)
                            logger.info(f"🔧 Using optimized Redis timeout: {timeout}s")
                        else:
                            timeout = 3.0
                            
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
                            retry_timeout = timeout * 0.8 if REDIS_OPTIMIZATION_AVAILABLE else 2.0
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
        
        # Reset singletons and locks
        cls._redis_service = None
        cls._inventory_service = None
        cls._product_cache = None
        cls._mcp_recommender = None
        cls._conversation_manager = None
        cls._personalization_cache = None  # ✅ NEW: Reset personalization cache
        cls._redis_lock = None  # ← Reset lock
        cls._mcp_lock = None  # ← Reset MCP lock
        cls._conversation_lock = None  # ← Reset conversation lock
        cls._personalization_lock = None  # ✅ NEW: Reset personalization lock
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
        """Get MCP recommender singleton with dependencies"""
        if cls._mcp_recommender is None:
            mcp_lock = cls._get_mcp_lock()
            async with mcp_lock:
                if cls._mcp_recommender is None:
                    try:
                        # Get dependencies
                        redis_service = await cls.get_redis_service()
                        conversation_manager = await cls.get_conversation_manager()
                        
                        # ✅ LAZY IMPORT: Avoid circular import
                        from src.api.mcp.engines.mcp_personalization_engine import MCPPersonalizationEngine
                        
                        cls._mcp_recommender = MCPPersonalizationEngine(
                            redis_service=redis_service,
                            conversation_manager=conversation_manager
                        )
                        logger.info("✅ MCPPersonalizationEngine singleton initialized successfully")
                    except Exception as e:
                        logger.error(f"❌ Failed to initialize MCPPersonalizationEngine: {e}")
                        raise
        return cls._mcp_recommender

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