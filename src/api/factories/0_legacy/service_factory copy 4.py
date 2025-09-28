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
from typing import Optional
import asyncio

# Core services
from src.api.core.redis_service import get_redis_service, RedisService
from src.api.core.store import get_shopify_client
from src.api.core.product_cache import ProductCache

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
    
    # ✅ FIX 2: Async lock para thread safety
    _redis_lock: Optional[asyncio.Lock] = None
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
                        
                        # ✅ FIX 7: Single fast retry optimizado
                        try:
                            retry_timeout = timeout * 0.8 if REDIS_OPTIMIZATION_AVAILABLE else 2.0
                            logger.info(f"🔄 Fast retry with timeout: {retry_timeout}s")
                            redis_service = await asyncio.wait_for(
                                get_redis_service(),
                                timeout=retry_timeout
                            )
                            cls._redis_service = redis_service
                            cls._reset_circuit_breaker()
                            logger.info("✅ Redis connection successful on fast retry")
                            
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
        ✅ Factory para ProductCache usando Redis singleton fixed
        """
        try:
            redis_service = await cls.get_redis_service()
            shopify_client = get_shopify_client()
            
            # ✅ Use underlying Redis client from service
            redis_client = getattr(redis_service, '_client', None)
            
            product_cache = ProductCache(
                redis_client=redis_client,
                local_catalog=local_catalog,
                shopify_client=shopify_client,
                ttl_seconds=3600,
                prefix="product:v2:"
            )
            
            await product_cache.start_background_tasks()
            logger.info("✅ ProductCache created with fixed RedisService architecture")
            return product_cache
            
        except Exception as e:
            logger.error(f"❌ ProductCache initialization failed: {e}")
            raise RuntimeError(f"Product cache service unavailable: {e}")
    
    @classmethod
    async def get_product_cache_singleton(cls) -> ProductCache:
        """Get ProductCache singleton"""
        if cls._product_cache is None:
            cls._product_cache = await cls.create_product_cache()
            logger.info("✅ ProductCache singleton initialized")
        return cls._product_cache
    
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
        
        # Reset singletons and locks
        cls._redis_service = None
        cls._inventory_service = None
        cls._product_cache = None
        cls._redis_lock = None  # ← Reset lock
        cls._reset_circuit_breaker()  # ← Reset circuit breaker
        
        logger.info("✅ ServiceFactory shutdown completed (ALL CLEAN)")


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

async def health_check_services() -> dict:
    """Convenience function para health checks"""
    return await ServiceFactory.health_check_all_services()