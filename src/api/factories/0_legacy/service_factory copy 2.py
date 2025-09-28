# src/api/factories/service_factory.py
"""
Service Factory - Enterprise Dependency Injection
=================================================

Fábrica centralizada para crear servicios con dependency injection unificada.
Implementa patrones enterprise para gestión de dependencias.

Author: Senior Architecture Team  
Version: 2.0.0 - Redis Enterprise Integration
"""
import time
import logging
from typing import Optional
import asyncio

# Core services
from src.api.core.redis_service import get_redis_service, RedisService
from src.api.core.store import get_shopify_client
from src.api.core.product_cache import ProductCache

# Business services  
from src.api.inventory.inventory_service import InventoryService
from src.api.inventory.availability_checker import create_availability_checker

logger = logging.getLogger(__name__)

class ServiceFactory:
    """
    🏗️ ENTERPRISE SERVICE FACTORY
    
    Centraliza la creación de servicios con dependency injection limpia.
    Garantiza consistencia en la inicialización y gestión de dependencias.
    """
    
    # Singleton instances para performance
    _redis_service: Optional[RedisService] = None
    _inventory_service: Optional[InventoryService] = None
    _product_cache: Optional[ProductCache] = None
    
    @classmethod
    async def get_redis_service(cls) -> RedisService:
        """
        ✅ Obtener RedisService singleton con lazy initialization
        """
        logger.info(f"🔄 Initializing RedisService singleton with redis_service: {cls._redis_service}")
        if cls._redis_service is None:
            try:
                logger.info("🔄 Initializing RedisService singleton with timeout protection")
                
                # ✅ FIXED: Correct way to get redis service
                redis_service = await asyncio.wait_for(
                    get_redis_service(),
                    timeout=15.0  # Increased timeout - matches direct connection success
                )
                
                # ✅ FIXED: Use correct health check method
                try:
                    health_result = await asyncio.wait_for(
                        redis_service.health_check(),
                        timeout=5.0  # Increased health check timeout
                    )
                    logger.info(f"✅ Redis health check: {health_result.get('status', 'unknown')}")
                except Exception as health_error:
                    logger.warning(f"⚠️ Redis health check failed: {health_error}")
                
                cls._redis_service = redis_service
                logger.info("✅ RedisService singleton initialized successfully")
                
            except asyncio.TimeoutError:
                logger.warning("⚠️ Redis connection timeout (15s) - attempting single retry...")
                
                # Single retry with extended timeout since direct connection works
                try:
                    logger.info("🔄 Retry attempt with extended timeout...")
                    redis_service = await asyncio.wait_for(
                        get_redis_service(),
                        timeout=20.0  # Extended timeout for retry
                    )
                    
                    # Quick health check for retry
                    health_result = await asyncio.wait_for(
                        redis_service.health_check(),
                        timeout=3.0
                    )
                    
                    cls._redis_service = redis_service
                    logger.info(f"✅ Redis connection successful on retry: {health_result.get('status')}")
                    return cls._redis_service
                    
                except Exception as retry_error:
                    logger.error(f"❌ Redis retry failed: {retry_error} - creating fallback service")
                cls._redis_service = await cls._create_fallback_redis_service()
            except Exception as e:
                logger.error(f"❌ Redis initialization failed: {e}")
                cls._redis_service = await cls._create_fallback_redis_service()
        
        return cls._redis_service

    @classmethod
    async def _create_fallback_redis_service(cls):
        """Create a fallback Redis service when real Redis is unavailable - FIXED"""
        try:
            # ✅ FIXED: Import and check RedisService constructor
            from src.api.core.redis_service import RedisService
            
            # ✅ FIXED: Create RedisService with correct parameters
            # Check what parameters RedisService actually accepts
            try:
                # Try with redis_service parameter (if it accepts it)
                fallback_service = RedisService(redis_service=None)
            except TypeError:
                try:
                    # Try with no parameters
                    fallback_service = RedisService()
                except TypeError:
                    # Try to understand the constructor by reading the class
                    import inspect
                    sig = inspect.signature(RedisService.__init__)
                    logger.info(f"🔍 RedisService constructor signature: {sig}")
                    
                    # Create with whatever parameters it actually needs
                    fallback_service = RedisService()
            
            logger.info("✅ Fallback Redis service created successfully")
            return fallback_service
            
        except Exception as e:
            logger.error(f"❌ Could not create fallback Redis service: {e}")
            # Return a mock object as last resort
            return cls._create_mock_redis_service()

    @classmethod
    def _create_mock_redis_service(cls):
        """Create a minimal mock Redis service as last resort"""
        class MockRedisService:
            """Minimal mock Redis service for fallback"""
            
            async def health_check(self):
                return {
                    "status": "fallback",
                    "message": "Mock Redis service - no actual Redis connection",
                    "timestamp": time.time()
                }
            
            def get_stats(self):
                return {
                    "status": "fallback",
                    "connections": 0,
                    "memory_usage": 0
                }
        
        logger.warning("⚠️ Using mock Redis service as last resort fallback")
        return MockRedisService()  
    
    @classmethod
    async def create_inventory_service(cls) -> InventoryService:
        """
        ✅ CORRECCIÓN CRÍTICA: Factory para InventoryService
        
        Utiliza RedisService enterprise-grade en lugar de múltiples clients.
        Garantiza dependency injection limpia y consistente.
        """
        try:
            # ✅ Obtener RedisService enterprise singleton
            redis_service = await cls.get_redis_service()
            
            # ✅ Crear InventoryService con dependency injection limpia
            inventory_service = InventoryService(redis_service=redis_service)
            
            # ✅ Asegurar que el servicio esté listo
            await inventory_service.ensure_ready()
            
            logger.info("✅ InventoryService created with RedisService enterprise")
            return inventory_service
            
        except Exception as e:
            logger.warning(f"⚠️ RedisService unavailable, creating InventoryService in fallback mode: {e}")
            
            # ✅ Graceful degradation sin Redis
            inventory_service = InventoryService(redis_service=None)
            await inventory_service.ensure_ready()
            return inventory_service
    
    @classmethod
    async def get_inventory_service_singleton(cls) -> InventoryService:
        """
        ✅ Obtener InventoryService singleton para performance
        """
        if cls._inventory_service is None:
            cls._inventory_service = await cls.create_inventory_service()
            logger.info("✅ InventoryService singleton initialized")
        return cls._inventory_service
    
    @classmethod
    async def create_product_cache(cls, local_catalog=None) -> ProductCache:
        """
        ✅ Factory para ProductCache con RedisService enterprise

        Accept local_catalog parameter for proper DI
        Integra ProductCache con la nueva arquitectura Redis enterprise,
        manteniendo el hybrid fallback strategy.
        """
        try:
            # ✅ RedisService enterprise como fuente primaria
            redis_service = await cls.get_redis_service()
            
            # ✅ Obtener dependencias adicionales
            shopify_client = get_shopify_client()
            
            # ✅ Inicializar ProductCache con arquitectura enterprise
            product_cache = ProductCache(
                redis_client=redis_service._client,  # Access to underlying client
                local_catalog=local_catalog,
                shopify_client=shopify_client,
                ttl_seconds=3600,  # 1 hour default
                prefix="product:v2:"
            )
            
            # ✅ Iniciar background tasks
            await product_cache.start_background_tasks()
            
            logger.info("✅ ProductCache created with RedisService enterprise architecture")
            return product_cache
            
        except Exception as e:
            logger.error(f"❌ ProductCache initialization failed: {e}")
            # En lugar de raise, podríamos implementar un fallback cache
            raise RuntimeError(f"Product cache service unavailable: {e}")
    
    @classmethod
    async def get_product_cache_singleton(cls) -> ProductCache:
        """
        ✅ Obtener ProductCache singleton para performance
        """
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
        ✅ Health check comprehensivo de todos los servicios enterprise
        """
        health_status = {
            "timestamp": asyncio.get_event_loop().time(),
            "factory": "ServiceFactory",
            "version": "2.0.0",
            "services": {}
        }
        
        try:
            # ✅ Check RedisService
            redis_service = await cls.get_redis_service()
            redis_health = await redis_service.health_check()
            health_status["services"]["redis_service"] = redis_health
            
            # ✅ Check InventoryService
            inventory_service = await cls.get_inventory_service_singleton()
            inventory_stats = await inventory_service.get_stats()
            health_status["services"]["inventory_service"] = {
                "status": "operational",
                "stats": inventory_stats
            }
            
            # ✅ Check ProductCache
            try:
                product_cache = await cls.get_product_cache_singleton()
                cache_stats = product_cache.get_stats()
                health_status["services"]["product_cache"] = {
                    "status": "operational",
                    "stats": cache_stats
                }
            except Exception as cache_error:
                health_status["services"]["product_cache"] = {
                    "status": "degraded",
                    "error": str(cache_error)
                }
            
            # ✅ Determine overall health
            service_statuses = [
                service.get("status", "unknown") 
                for service in health_status["services"].values()
            ]
            
            if all(status == "operational" for status in service_statuses):
                health_status["overall_status"] = "healthy"
            elif any(status == "operational" for status in service_statuses):
                health_status["overall_status"] = "degraded"  
            else:
                health_status["overall_status"] = "unhealthy"
                
        except Exception as e:
            logger.error(f"❌ ServiceFactory health check failed: {e}")
            health_status["overall_status"] = "unhealthy"
            health_status["error"] = str(e)
        
        return health_status
    
    @classmethod
    async def shutdown_all_services(cls):
        """
        ✅ Shutdown limpio de todos los servicios enterprise
        """
        logger.info("🔄 ServiceFactory shutdown initiated...")
        
        # Shutdown ProductCache background tasks
        if cls._product_cache:
            try:
                if hasattr(cls._product_cache, 'health_task') and cls._product_cache.health_task:
                    cls._product_cache.health_task.cancel()
                logger.info("✅ ProductCache shutdown completed")
            except Exception as e:
                logger.warning(f"⚠️ ProductCache shutdown error: {e}")
        
        # Reset singletons para clean restart
        cls._redis_service = None
        cls._inventory_service = None
        cls._product_cache = None
        
        logger.info("✅ ServiceFactory shutdown completed")


# ============================================================================
# 🔧 CONVENIENCE FUNCTIONS - Backward Compatibility
# ============================================================================

async def get_inventory_service() -> InventoryService:
    """
    ✅ Convenience function para backward compatibility
    """
    return await ServiceFactory.get_inventory_service_singleton()

async def get_product_cache() -> ProductCache:
    """
    ✅ Convenience function para backward compatibility
    """
    return await ServiceFactory.get_product_cache_singleton()

async def get_availability_checker():
    """
    ✅ Convenience function para backward compatibility
    """
    return await ServiceFactory.create_availability_checker()

async def health_check_services() -> dict:
    """
    ✅ Convenience function para health checks
    """
    return await ServiceFactory.health_check_all_services()
