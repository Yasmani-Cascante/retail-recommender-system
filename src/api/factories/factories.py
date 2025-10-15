"""
Business Domain Factories - Enterprise Integration
===============================================

Fábricas especializadas para componentes de lógica de negocio del sistema.
Integradas con ServiceFactory para dependency injection enterprise.

Domains:
- RecommenderFactory: Core recommendation business logic
- MCPFactory: Conversation and AI integration

Integration:
- Uses ServiceFactory for Redis infrastructure
- Maintains business domain separation
- Prepared for microservices extraction

Author: Senior Architecture Team
Version: 2.1.0 - Enterprise Redis Integration
"""

import logging
import asyncio
from src.api.core.config import get_settings
from src.recommenders.tfidf_recommender import TFIDFRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from typing import Dict, Any, Optional, Union
from src.api.core.diversity_aware_cache import create_diversity_aware_cache


logger = logging.getLogger(__name__)

# ✅ ENTERPRISE INTEGRATION: Import ServiceFactory for Redis infrastructure
try:
    from .service_factory import ServiceFactory
    ENTERPRISE_INTEGRATION_AVAILABLE = True
    # Logger configured above in import section
    logger.info("✅ Enterprise integration: ServiceFactory loaded successfully")
except ImportError as e:
    ENTERPRISE_INTEGRATION_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️ Enterprise integration not available: {e}")



class MCPFactory:
    """Fábrica para crear componentes relacionados con MCP."""
    
    # ==========================================
    # MÉTODOS ASÍNCRONOS PARA TESTING Y MCP
    # ==========================================
    
    @staticmethod
    async def create_mcp_client_async():
        """
        Crea un cliente MCP de forma asíncrona.
        
        Returns:
            MCPClientEnhanced: Cliente MCP inicializado
        """
        try:
            from src.api.mcp.client.mcp_client_enhanced import MCPClientEnhanced
            
            logger.info("Creando cliente MCPClientEnhanced asíncrono en puerto 3001")
            client = MCPClientEnhanced(
                bridge_host="localhost", 
                bridge_port=3001,
                enable_circuit_breaker=True,
                enable_local_cache=True,
                cache_ttl=300
            )
            
            logger.info(f"🔍 DEBUG asíncrono: MCPClientEnhanced creado: {type(client).__name__}")
            logger.info(f"🔍 DEBUG asíncrono: Tiene get_metrics: {hasattr(client, 'get_metrics')}")
            
            return client
            
        except ImportError as e:
            logger.warning(f"No se pudo importar MCPClientEnhanced: {e}")
            try:
                from src.api.mcp.client.mcp_client import MCPClient
                
                client = MCPClient(bridge_host="localhost", bridge_port=3001)
                
                async def mock_get_metrics():
                    return {
                        "client_type": "basic_mcp_client_async",
                        "status": "available",
                        "note": "Enhanced features not available - using basic client (async)"
                    }
                
                client.get_metrics = mock_get_metrics
                logger.info(f"🔍 DEBUG asíncrono: MCPClient básico creado: {type(client).__name__}")
                return client
                
            except ImportError:
                logger.error("No se pudo importar ningún cliente MCP asíncrono.")
                return None
                
        except Exception as e:
            logger.error(f"Error creando cliente MCP asíncrono: {str(e)}")
            return None
    
    @staticmethod
    async def create_mcp_recommender_async(
        base_recommender=None,
        mcp_client=None,
        market_manager=None,
        market_cache=None,
        user_event_store=None,
        redis_client=None
    ):
        """
        Crea un recomendador con capacidades MCP de forma asíncrona.
        
        Returns:
            MCPAwareRecommender: Recomendador con capacidades MCP
        """
        try:
            from src.recommenders.mcp_aware_recommender import MCPAwareRecommender
            
            logger.info("Creando recomendador MCPAwareRecommender asíncrono")
            
            # 1. Crear base_recommender si no se proporcionó
            if base_recommender is None:
                logger.info("Creando componentes base para MCP recommender (asíncrono)...")
                content_recommender = await RecommenderFactory.create_tfidf_recommender_async()
                retail_recommender = await RecommenderFactory.create_retail_recommender_async()
                
                base_recommender = await RecommenderFactory.create_hybrid_recommender_async(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender
                )
                logger.info("Base recommender creado automáticamente (asíncrono)")
            
            # 2. Crear MCP client si no se proporcionó
            if mcp_client is None:
                mcp_client = await MCPFactory.create_mcp_client_async()
                if not mcp_client:
                    logger.warning("MCP client no disponible (asíncrono), usando fallback")
            
            # 3. Crear user_event_store si no se proporcionó - ✅ ENTERPRISE INTEGRATION
            if user_event_store is None:
                if redis_client is None:
                    # ✅ Use ServiceFactory for enterprise Redis management
                    if ENTERPRISE_INTEGRATION_AVAILABLE:
                        redis_service = await ServiceFactory.get_redis_service()
                        redis_client = redis_service._client  # Access underlying client
                        logger.info("✅ Using enterprise Redis service for MCP recommender")
                    else:
                        # Fallback to legacy Redis client creation
                        redis_client = await RecommenderFactory.create_redis_client_async()
                        logger.warning("⚠️ Using legacy Redis client - enterprise integration unavailable")
                
                user_event_store = await RecommenderFactory.create_user_event_store_async(redis_client)
                if not user_event_store:
                    logger.warning("UserEventStore no disponible (asíncrono), usando fallback")
            
            # 4. Crear el recomendador MCP
            mcp_recommender = MCPAwareRecommender(
                base_recommender=base_recommender,
                mcp_client=mcp_client,
                user_event_store=user_event_store,
                market_manager=market_manager,
                market_cache=market_cache
            )
            
            logger.info(f"🔍 DEBUG asíncrono: MCPAwareRecommender creado: {type(mcp_recommender).__name__}")
            logger.info(f"🔍 DEBUG asíncrono: Verificando métodos - get_metrics: {hasattr(mcp_recommender, 'get_metrics')}")
            
            return mcp_recommender
                
        except ImportError as e:
            logger.error(f"No se pudo importar MCPAwareRecommender (asíncrono): {e}")
            return None
        except Exception as e:
            logger.error(f"Error creando MCPAwareRecommender (asíncrono): {e}")
            return None
    
    # ==========================================
    # MÉTODOS SÍNCRONOS ORIGINALES
    # ==========================================
    
    @staticmethod
    def create_mcp_client():
        """
        Crea un cliente MCP mejorado para Shopify.
        
        Returns:
            MCPClientEnhanced: Cliente MCP inicializado con circuit breaker y caching
        """
        settings = get_settings()
        
        try:
            # Intentar crear MCPClientEnhanced primero
            from src.api.mcp.client.mcp_client_enhanced import MCPClientEnhanced
            
            logger.info(f"Creando cliente MCPClientEnhanced bridge en puerto 3001")
            client = MCPClientEnhanced(
                bridge_host="localhost", 
                bridge_port=3001,
                enable_circuit_breaker=True,
                enable_local_cache=True,
                cache_ttl=300
            )
            
            logger.info(f"🔍 DEBUG: MCPClientEnhanced creado: {type(client).__name__}")
            logger.info(f"🔍 DEBUG: Tiene get_metrics: {hasattr(client, 'get_metrics')}")
            
            return client
            
        except ImportError as e:
            logger.warning(f"No se pudo importar MCPClientEnhanced: {e}")
            logger.warning("Intentando fallback a MCPClient básico...")
            
            # Fallback a MCPClient básico si MCPClientEnhanced no está disponible
            try:
                from src.api.mcp.client.mcp_client import MCPClient
                
                logger.info(f"Creando cliente MCP básico bridge en puerto 3001")
                client = MCPClient(bridge_host="localhost", bridge_port=3001)
                
                # Añadir método get_metrics simulado al MCPClient básico
                async def mock_get_metrics():
                    return {
                        "client_type": "basic_mcp_client",
                        "status": "available",
                        "note": "Enhanced features not available - using basic client"
                    }
                
                # Monkey patch para compatibilidad
                client.get_metrics = mock_get_metrics
                
                logger.info(f"🔍 DEBUG: MCPClient básico creado: {type(client).__name__}")
                logger.info(f"🔍 DEBUG: Tiene get_metrics: {hasattr(client, 'get_metrics')}")
                
                return client
                
            except ImportError:
                logger.error("No se pudo importar ningún cliente MCP. Verifica la instalación.")
                return None
                
        except Exception as e:
            logger.error(f"Error creando cliente MCP: {str(e)}")
            logger.warning("Intentando fallback a MCPClient básico...")
            
            # Fallback en caso de error de configuración
            try:
                from src.api.mcp.client.mcp_client import MCPClient
                
                client = MCPClient(bridge_host="localhost", bridge_port=3001)
                
                # Añadir método get_metrics simulado
                async def mock_get_metrics():
                    return {
                        "client_type": "basic_mcp_client_fallback",
                        "status": "fallback_mode",
                        "note": "Using basic client due to enhanced client error"
                    }
                
                client.get_metrics = mock_get_metrics
                
                logger.info(f"🔍 DEBUG: MCPClient fallback creado: {type(client).__name__}")
                return client
                
            except Exception as fallback_error:
                logger.error(f"Error en fallback MCP client: {fallback_error}")
                return None
            
    # ...existing class methods...
    @staticmethod
    def create_market_manager():
        """
        Crea un gestor de contexto de mercado.
        
        Returns:
            MarketContextManager: Gestor de mercados inicializado
        """
        try:
            from src.api.mcp.adapters.market_manager import MarketContextManager
            
            logger.info("Creando gestor de contexto de mercado")
            manager = MarketContextManager()
            
            # CORREGIDO: Inicializar de forma segura sin event loop
            # El manager se inicializará cuando sea necesario en contexto asíncrono
            logger.info("Market manager creado - inicialización diferida")
            
            return manager
        except ImportError:
            logger.error("No se pudo importar MarketContextManager. Verifica la instalación.")
            return None
        except Exception as e:
            logger.error(f"Error creando gestor de mercado: {str(e)}")
            return None
    
    @staticmethod
    def create_market_cache():
        """
        Crea un sistema de caché específico para mercados.
        
        Returns:
            MarketAwareProductCache: Cache market-aware
        """
        settings = get_settings()
        
        if not settings.use_redis_cache:
            logger.info("MarketAwareProductCache desactivada por configuración")
            return None
            
        try:
            from src.cache.market_aware.market_cache import MarketAwareProductCache
            
            logger.info("Creando cache market-aware")
            market_cache = MarketAwareProductCache()
            
            return market_cache
        except ImportError:
            logger.error("No se pudo importar MarketAwareProductCache.")
            return None
        except Exception as e:
            logger.error(f"Error creando MarketAwareProductCache: {str(e)}")
            return None
    
    @staticmethod
    def create_mcp_recommender(
        base_recommender=None,
        mcp_client=None,
        market_manager=None,
        market_cache=None,
        user_event_store=None,
        redis_client=None
    ):
        """
        Crea un recomendador con capacidades MCP.
        
        Args:
            base_recommender: Recomendador híbrido base (opcional)
            mcp_client: Cliente MCP (opcional)
            market_manager: Gestor de mercados (opcional)
            market_cache: Caché market-aware (opcional)
            user_event_store: Almacén de eventos de usuario (opcional)
                
        Returns:
            MCPAwareHybridRecommender: Recomendador con capacidades MCP
        """
        try:
            from src.recommenders.mcp_aware_recommender import MCPAwareRecommender
            
            logger.info("Creando recomendador MCPAwareRecommender con componentes proporcionados o automáticos")
            logger.info(f"🔍 DEBUG: Importing MCPAwareRecommender exitoso")
            
            # 1. Usar base_recommender proporcionado o crear uno nuevo
            if base_recommender is None:
                logger.info("Creando componentes base para MCP recommender...")
                content_recommender = RecommenderFactory.create_content_recommender()
                retail_recommender = RecommenderFactory.create_retail_recommender()
                
                # Crear recomendador híbrido base
                base_recommender = RecommenderFactory.create_hybrid_recommender(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender
                )
                logger.info("Base recommender creado automáticamente")
            else:
                logger.info(f"Usando base recommender proporcionado: {type(base_recommender).__name__}")
            
            # 2. Usar MCP client proporcionado o crear uno nuevo
            if mcp_client is None:
                mcp_client = MCPFactory.create_mcp_client()
                if not mcp_client:
                    logger.warning("MCP client no disponible, usando fallback")
                else:
                    logger.info(f"MCP client creado automáticamente: {type(mcp_client).__name__}")
            else:
                logger.info(f"Usando MCP client proporcionado: {type(mcp_client).__name__}")
            
            # 3. Usar market manager proporcionado o crear uno nuevo
            if market_manager is None:
                market_manager = MCPFactory.create_market_manager()
                if not market_manager:
                    logger.warning("Market manager no disponible, usando fallback")
                else:
                    logger.info(f"Market manager creado automáticamente: {type(market_manager).__name__}")
            else:
                logger.info(f"Usando market manager proporcionado: {type(market_manager).__name__}")
            
            # 4. Usar market cache proporcionado o crear uno nuevo
            if market_cache is None:
                market_cache = MCPFactory.create_market_cache()
                if not market_cache:
                    logger.warning("Market cache no disponible, usando fallback")
                else:
                    logger.info(f"Market cache creado automáticamente: {type(market_cache).__name__}")
            else:
                logger.info(f"Usando market cache proporcionado: {type(market_cache).__name__}")
            
            # 5. Usar user_event_store proporcionado o crear uno nuevo - ✅ ENTERPRISE INTEGRATION
            if user_event_store is None:
                # Crear redis_client si no se proporcionó
                if redis_client is None:
                    # Note: Sync method cannot directly use async ServiceFactory
                    # This is intentional - sync methods should migrate to async for enterprise features
                    redis_client = RecommenderFactory.create_redis_client()
                    if redis_client:
                        logger.info(f"Redis client (legacy) creado automáticamente: {type(redis_client).__name__}")
                        logger.info("ℹ️ For enterprise Redis features, use async methods with ServiceFactory")
                    else:
                        logger.warning("Redis client no disponible")
                
                user_event_store = RecommenderFactory.create_user_event_store(redis_client)
                if not user_event_store:
                    logger.warning("UserEventStore no disponible, usando fallback")
                else:
                    logger.info(f"UserEventStore creado automáticamente: {type(user_event_store).__name__}")
            else:
                logger.info(f"Usando UserEventStore proporcionado: {type(user_event_store).__name__}")
            
            # 6. Crear el recomendador MCP con todos los componentes
            logger.info("🔍 DEBUG: Creando MCPAwareRecommender con parámetros...")
            logger.info(f"  - base_recommender: {type(base_recommender).__name__ if base_recommender else 'None'}")
            logger.info(f"  - mcp_client: {type(mcp_client).__name__ if mcp_client else 'None'}")
            logger.info(f"  - user_event_store: {type(user_event_store).__name__ if user_event_store else 'None'}")
            
            mcp_recommender = MCPAwareRecommender(
                base_recommender=base_recommender,
                mcp_client=mcp_client,
                user_event_store=user_event_store
            )
            
            logger.info(f"🔍 DEBUG: MCPAwareRecommender creado exitosamente: {type(mcp_recommender).__name__}")
            logger.info(f"🔍 DEBUG: Verificando métodos - get_metrics: {hasattr(mcp_recommender, 'get_metrics')}")
            return mcp_recommender
                
        except ImportError as e:
            logger.error(f"No se pudo importar MCPAwareRecommender: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creando MCPAwareRecommender: {e}")
            return None



    @staticmethod
    def create_mcp_recommender_fixed(
        base_recommender=None,
        mcp_client=None,
        market_manager=None,
        market_cache=None,
        user_event_store=None,
        redis_client=None
    ):
        """
        🔧 VERSIÓN CORREGIDA: Crea un recomendador con capacidades MCP usando la versión fixed.
        """
        try:
            from src.recommenders.mcp_aware_hybrid_fixed import MCPAwareHybridRecommenderFixed
            
            logger.info("Creando recomendador MCPAwareHybridRecommenderFixed")
            
            # 1. Crear base_recommender si no se proporcionó
            if base_recommender is None:
                logger.info("Creando componentes base para MCP recommender corregido...")
                content_recommender = RecommenderFactory.create_content_recommender()
                retail_recommender = RecommenderFactory.create_retail_recommender()
                
                base_recommender = RecommenderFactory.create_hybrid_recommender(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender
                )
                logger.info("Base recommender creado automáticamente (corregido)")
            
            # 2. Crear MCP client si no se proporcionó
            if mcp_client is None:
                mcp_client = MCPFactory.create_mcp_client()
                if not mcp_client:
                    logger.warning("MCP client no disponible, usando fallback")
            
            # 3. Crear market manager si no se proporcionó
            if market_manager is None:
                market_manager = MCPFactory.create_market_manager()
                if not market_manager:
                    logger.warning("Market manager no disponible, usando fallback")
            
            # 4. Crear el recomendador MCP CORREGIDO
            mcp_recommender = MCPAwareHybridRecommenderFixed(
                base_recommender=base_recommender,
                mcp_client=mcp_client,
                market_manager=market_manager,
                market_cache=market_cache
            )
            
            logger.info(f"🔧 ÉXITO: MCPAwareHybridRecommenderFixed creado: {type(mcp_recommender).__name__}")
            return mcp_recommender
                
        except ImportError as e:
            logger.error(f"No se pudo importar MCPAwareHybridRecommenderFixed: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creando MCPAwareHybridRecommenderFixed: {e}")
            return None


    # ============================================================================
    # ✅ ENTERPRISE INTEGRATION METHODS - MCP with ServiceFactory
    # ============================================================================
    
    @staticmethod
    async def create_mcp_recommender_enterprise(
        base_recommender=None,
        mcp_client=None,
        market_manager=None,
        market_cache=None
    ):
        """
        ✅ ENTERPRISE: Creates MCP-aware recommender using ServiceFactory for Redis.
        
        This method leverages enterprise Redis integration for optimal performance
        and consistency with the overall system architecture.
        
        Args:
            base_recommender: Optional hybrid recommender base
            mcp_client: Optional MCP client
            market_manager: Optional market context manager
            market_cache: Optional market-aware cache
            
        Returns:
            MCPAwareRecommender with enterprise Redis integration
        """
        if not ENTERPRISE_INTEGRATION_AVAILABLE:
            logger.warning("⚠️ Enterprise integration not available - falling back to standard method")
            return await MCPFactory.create_mcp_recommender_async(
                base_recommender=base_recommender,
                mcp_client=mcp_client,
                market_manager=market_manager,
                market_cache=market_cache
            )
        
        try:
            from src.recommenders.mcp_aware_recommender import MCPAwareRecommender
            
            logger.info("✅ Creating MCP recommender with enterprise integration")
            
            # 1. Create base_recommender if not provided (using enterprise methods)
            if base_recommender is None:
                logger.info("Creating enterprise base recommender components...")
                
                # Use enterprise-integrated async methods
                content_recommender = await RecommenderFactory.create_tfidf_recommender_async()
                retail_recommender = await RecommenderFactory.create_retail_recommender_async()
                
                base_recommender = await RecommenderFactory.create_hybrid_recommender_async(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender
                )
                logger.info("✅ Enterprise base recommender created")
            
            # 2. Create MCP client if not provided
            if mcp_client is None:
                mcp_client = await MCPFactory.create_mcp_client_async()
                if mcp_client:
                    logger.info("✅ MCP client created for enterprise integration")
                else:
                    logger.warning("⚠️ MCP client not available")
            
            # 3. Create UserEventStore using enterprise Redis
            logger.info("✅ Creating UserEventStore with enterprise Redis...")
            user_event_store = await RecommenderFactory.create_user_event_store_enterprise()
            
            if not user_event_store:
                logger.warning("⚠️ Enterprise UserEventStore not available, using fallback")
                # Fallback to standard method
                redis_client = await RecommenderFactory.create_redis_client_enterprise()
                user_event_store = await RecommenderFactory.create_user_event_store_async(redis_client)
            
            # 4. Create the MCP recommender with enterprise components
            mcp_recommender = MCPAwareRecommender(
                base_recommender=base_recommender,
                mcp_client=mcp_client,
                user_event_store=user_event_store,
                market_manager=market_manager,
                market_cache=market_cache
            )
            
            logger.info("✅ Enterprise MCP recommender created successfully")
            logger.info(f"   Components: base={type(base_recommender).__name__ if base_recommender else 'None'}")
            logger.info(f"              mcp_client={type(mcp_client).__name__ if mcp_client else 'None'}")
            logger.info(f"              user_events={type(user_event_store).__name__ if user_event_store else 'None'}")
            
            return mcp_recommender
                
        except ImportError as e:
            logger.error(f"❌ Failed to import MCPAwareRecommender for enterprise: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to create enterprise MCP recommender: {e}")
            return None


class RecommenderFactory:
    """Fábrica para crear recomendadores."""
    
    # ==========================================
    # MÉTODOS ASÍNCRONOS PARA TESTING Y MCP
    # ==========================================
    
    @staticmethod
    async def create_redis_client_async():
        """
        Crea un cliente Redis de forma asíncrona con conexión inmediata.
        ✅ ENTERPRISE INTEGRATION: Prefers ServiceFactory when available.
        
        Returns:
            RedisClient: Cliente Redis conectado o None si falla
        """
        settings = get_settings()
        
        if not settings.use_redis_cache:
            logger.info("Caché Redis desactivada por configuración")
            return None
        
        # ✅ PREFER ENTERPRISE INTEGRATION
        if ENTERPRISE_INTEGRATION_AVAILABLE:
            try:
                logger.info("✅ Using enterprise RedisService for async Redis client")
                redis_service = await ServiceFactory.get_redis_service()
                return redis_service._client  # Return underlying client for compatibility
            except Exception as e:
                logger.warning(f"⚠️ Enterprise Redis service failed, falling back to legacy: {e}")
                # Continue to legacy implementation below
            
        # ☠️ LEGACY IMPLEMENTATION (Fallback)
        try:
            from src.api.core.redis_config_fix import PatchedRedisClient as RedisClient
           
            logger.info(f"Creando cliente Redis asíncrono (legacy): {settings.redis_host}:{settings.redis_port}")
            
            # Obtener parámetros para el cliente Redis
            client_params = {
                "host": settings.redis_host,
                "port": settings.redis_port,
                "db": settings.redis_db,
                "ssl": settings.redis_ssl
            }
            
            # Agregar password si está configurado
            if settings.redis_password:
                client_params["password"] = settings.redis_password
                
            # Agregar username si está configurado
            if hasattr(settings, "redis_username") and settings.redis_username:
                client_params["username"] = settings.redis_username
                
            redis_client = RedisClient(**client_params)
            
            # Conectar inmediatamente en contexto asíncrono
            connection_successful = await redis_client.connect()
            
            if connection_successful:
                logger.info("Cliente Redis (legacy) conectado exitosamente en modo asíncrono")
                return redis_client
            else:
                logger.error("No se pudo conectar a Redis en modo asíncrono")
                return None
                
        except ImportError:
            logger.error("No se pudo importar RedisClient. Asegúrate de que redis-py está instalado.")
            return None
        except Exception as e:
            logger.error(f"Error creando cliente Redis asíncrono: {str(e)}")
            return None
    
    @staticmethod
    async def create_user_event_store_async(redis_client=None):
        """
        Crea un almacén de eventos de usuario de forma asíncrona.
        
        Args:
            redis_client: Cliente Redis opcional
            
        Returns:
            UserEventStore: Almacén de eventos o None si falla
        """
        try:
            from src.api.mcp.user_events.resilient_user_event_store import UserEventStore
            from src.api.core.config import get_settings
            
            settings = get_settings()
            
            # Crear cliente Redis si no se proporcionó
            if not redis_client:
                redis_client = await RecommenderFactory.create_redis_client_async()
                
                if not redis_client:
                    logger.warning("No se pudo crear cliente Redis para UserEventStore")
                    return None
            
            # Construir URL de Redis
            redis_url = "redis://"
            
            if settings.redis_username and settings.redis_password:
                redis_url += f"{settings.redis_username}:{settings.redis_password}@"
            elif settings.redis_password:
                redis_url += f":{settings.redis_password}@"
            
            redis_url += f"{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
            
            logger.info("Creando UserEventStore asíncrono con Redis")
            
            user_event_store = UserEventStore(
                redis_url=redis_url,
                cache_ttl=getattr(settings, 'user_event_cache_ttl', 300),
                enable_circuit_breaker=True,
                cache_size=getattr(settings, 'user_event_cache_size', 1000),
                local_buffer_size=getattr(settings, 'user_event_buffer_size', 200),
                flush_interval_seconds=getattr(settings, 'user_event_flush_interval', 30),
                local_fallback_dir=getattr(settings, 'user_events_fallback_dir', None)
            )
            
            # Conectar en contexto asíncrono
            await user_event_store.connect()
            
            logger.info("UserEventStore conectado exitosamente en modo asíncrono")
            return user_event_store
            
        except ImportError as e:
            logger.error(f"No se pudo importar UserEventStore: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creando UserEventStore asíncrono: {e}")
            return None
    
    @staticmethod
    async def create_tfidf_recommender_async(model_path="data/tfidf_model.pkl"):
        """
        Crea un recomendador TF-IDF de forma asíncrona.
        
        Args:
            model_path: Ruta al archivo de modelo pre-entrenado
            
        Returns:
            TFIDFRecommender: Instancia del recomendador
        """
        logger.info(f"Creando recomendador TF-IDF asíncrono con modelo en: {model_path}")
        return TFIDFRecommender(model_path=model_path)
    
    @staticmethod
    async def create_retail_recommender_async():
        """
        Crea un recomendador de Google Cloud Retail API de forma asíncrona.
        
        Returns:
            RetailAPIRecommender: Instancia del recomendador
        """
        settings = get_settings()
        logger.info("Creando recomendador de Google Cloud Retail API asíncrono")
        
        return RetailAPIRecommender(
            project_number=settings.google_project_number,
            location=settings.google_location,
            catalog=settings.google_catalog,
            serving_config_id=settings.google_serving_config
        )
    
    @staticmethod
    async def create_hybrid_recommender_async(content_recommender, retail_recommender, product_cache=None):
        """
        Crea un recomendador híbrido de forma asíncrona.
        
        Args:
            content_recommender: Recomendador basado en contenido
            retail_recommender: Recomendador de Retail API
            product_cache: Caché de productos (opcional)
            
        Returns:
            HybridRecommender: Instancia del recomendador híbrido
        """
        settings = get_settings()
        logger.info(f"Creando recomendador híbrido asíncrono con content_weight={settings.content_weight}")
        
        try:
            if settings.exclude_seen_products:
                from src.api.core.hybrid_recommender import HybridRecommenderWithExclusion
                return HybridRecommenderWithExclusion(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender,
                    content_weight=settings.content_weight,
                    product_cache=product_cache
                )
            else:
                from src.api.core.hybrid_recommender import HybridRecommender
                return HybridRecommender(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender,
                    content_weight=settings.content_weight,
                    product_cache=product_cache
                )
        except ImportError as e:
            error_msg = f"Error crítico: No se pudo cargar el recomendador híbrido: {str(e)}"
            logger.error(error_msg)
            raise ImportError(error_msg)
    
    # ==========================================
    # MÉTODOS SÍNCRONOS ORIGINALES
    # ==========================================
    
    @staticmethod
    def create_tfidf_recommender(model_path="data/tfidf_model.pkl"):
        """
        Crea un recomendador TF-IDF.
        
        Args:
            model_path: Ruta al archivo de modelo pre-entrenado
            
        Returns:
            TFIDFRecommender: Instancia del recomendador
        """
        logger.info(f"Creando recomendador TF-IDF con modelo en: {model_path}")
        return TFIDFRecommender(model_path=model_path)
    
    @staticmethod
    def create_content_recommender():
        """
        Crea un recomendador basado en contenido, utilizando TF-IDF por defecto.
        
        Returns:
            Un recomendador basado en contenido (TFIDFRecommender por defecto)
        """
        settings = get_settings()
        logger.info("Creando recomendador basado en contenido")
        
        # Verificar si debemos usar ContentBasedRecommender
        use_transformers = getattr(settings, 'use_transformers', False)
        
        if use_transformers:
            # Intentar crear ContentBasedRecommender si está configurado
            try:
                from src.recommenders.content_based import ContentBasedRecommender
                logger.info("Usando ContentBasedRecommender con Sentence Transformers")
                return ContentBasedRecommender()
            except ImportError:
                logger.warning("No se pudo cargar ContentBasedRecommender, fallback a TF-IDF")
        
        # Usar TF-IDF como enfoque predeterminado
        model_path = getattr(settings, 'tfidf_model_path', "data/tfidf_model.pkl")
        logger.info(f"Usando TFIDFRecommender con modelo en: {model_path}")
        return RecommenderFactory.create_tfidf_recommender(model_path=model_path)
    
    @staticmethod
    def create_retail_recommender():
        """
        Crea un recomendador de Google Cloud Retail API.
        
        Returns:
            RetailAPIRecommender: Instancia del recomendador
        """
        settings = get_settings()
        logger.info(f"Creando recomendador de Google Cloud Retail API")
        logger.info(f"  Project: {settings.google_project_number}")
        logger.info(f"  Location: {settings.google_location}")
        logger.info(f"  Catalog: {settings.google_catalog}")
        
        return RetailAPIRecommender(
            project_number=settings.google_project_number,
            location=settings.google_location,
            catalog=settings.google_catalog,
            serving_config_id=settings.google_serving_config
        )
    
    @staticmethod
    def create_hybrid_recommender(
        content_recommender, 
        retail_recommender, 
        product_cache=None
    ):
        """
        Crea un recomendador híbrido utilizando exclusivamente la implementación unificada.
        
        Args:
            content_recommender: Recomendador basado en contenido
            retail_recommender: Recomendador de Retail API
            product_cache: Caché de productos (opcional)
            
        Returns:
            HybridRecommender: Instancia del recomendador híbrido unificado
        """
        settings = get_settings()
        logger.info(f"Creando recomendador híbrido unificado con content_weight={settings.content_weight}")
        logger.info(f"  Exclusión de productos vistos: {settings.exclude_seen_products}")
        
        try:
            # Importar la versión adecuada según la configuración
            if settings.exclude_seen_products:
                logger.info("Usando recomendador híbrido con exclusión de productos vistos")
                from src.api.core.hybrid_recommender import HybridRecommenderWithExclusion
                return HybridRecommenderWithExclusion(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender,
                    content_weight=settings.content_weight,
                    product_cache=product_cache
                )
            else:
                logger.info("Usando recomendador híbrido básico")
                from src.api.core.hybrid_recommender import HybridRecommender
                return HybridRecommender(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender,
                    content_weight=settings.content_weight,
                    product_cache=product_cache
                )
        except ImportError as e:
            # En la arquitectura unificada, no intentamos fallback a implementaciones antiguas
            # ya que hemos migrado completamente al nuevo sistema
            error_msg = f"Error crítico: No se pudo cargar el recomendador híbrido: {str(e)}. "
            error_msg += "Verifique la instalación y las dependencias del proyecto."
            logger.error(error_msg)
            raise ImportError(error_msg)

    @staticmethod
    def create_redis_client():
        """
        Crea un cliente Redis según la configuración.
        
        Returns:
            RedisClient: Cliente Redis configurado o None si está desactivado
        """
        settings = get_settings()
        
        if not settings.use_redis_cache:
            logger.info("Caché Redis desactivada por configuración")
            return None
            
        try:
            from src.api.core.redis_config_fix import PatchedRedisClient as RedisClient
            
            logger.info(f"Creando cliente Redis: {settings.redis_host}:{settings.redis_port}")
            
            # Obtener parámetros para el cliente Redis
            client_params = {
                "host": settings.redis_host,
                "port": settings.redis_port,
                "db": settings.redis_db,
                "ssl": settings.redis_ssl
            }
            
            # Agregar password si está configurado
            if settings.redis_password:
                client_params["password"] = settings.redis_password
                
            # Agregar username si está configurado
            if hasattr(settings, "redis_username") and settings.redis_username:
                client_params["username"] = settings.redis_username
                
            redis_client = RedisClient(**client_params)
            
            # CORREGIDO: Conexión diferida - el cliente se conectará automáticamente
            # cuando se realice la primera operación mediante ensure_connected()
            logger.info("Cliente Redis creado con conexión diferida")
            
            return redis_client
        except ImportError:
            logger.error("No se pudo importar RedisClient. Asegúrate de que redis-py está instalado.")
            return None
        except Exception as e:
            logger.error(f"Error creando cliente Redis: {str(e)}")
            return None
    
    @staticmethod
    def create_product_cache(content_recommender=None, shopify_client=None):
        """
        Crea un sistema de caché de productos.
        ℹ️ Note: For enterprise ProductCache, use ServiceFactory.get_product_cache_singleton() async method.
        
        Args:
            content_recommender: Recomendador TF-IDF para catálogo local
            shopify_client: Cliente de Shopify para fallback
            
        Returns:
            ProductCache: Sistema de caché configurado o None si está desactivado
        """
        settings = get_settings()
        
        if not settings.use_redis_cache:
            logger.info("ProductCache desactivada por configuración")
            return None
        
        # ℹ️ RECOMMENDATION: Use async ServiceFactory for enterprise features
        if ENTERPRISE_INTEGRATION_AVAILABLE:
            logger.info("ℹ️ Enterprise integration available - consider using ServiceFactory.get_product_cache_singleton() async method")
            logger.info("ℹ️ Current sync method provides legacy compatibility only")
            
        try:
            from src.api.core.product_cache import ProductCache
            
            # Crear cliente Redis (legacy)
            redis_client = RecommenderFactory.create_redis_client()
            if not redis_client:
                logger.warning("No se pudo crear cliente Redis, ProductCache desactivada")
                return None
            
            logger.info(f"Creando ProductCache (legacy) con TTL={getattr(settings, 'cache_ttl', 3600)}s")
            
            # Crear caché de productos
            cache = ProductCache(
                redis_client=redis_client,
                local_catalog=content_recommender,
                shopify_client=shopify_client,
                ttl_seconds=getattr(settings, 'cache_ttl', 3600),
                prefix=getattr(settings, 'cache_prefix', 'product:')
            )
            
            # Note: Background tasks should be started in async context
            # Sync method cannot properly handle async tasks
            logger.info("ProductCache (legacy) creado - background tasks omitidas en modo sync")
            logger.info("ℹ️ Use async ServiceFactory methods for full enterprise features")
            
            return cache
        except ImportError:
            logger.error("No se pudo importar ProductCache.")
            return None
        except Exception as e:
            logger.error(f"Error creando ProductCache: {str(e)}")
            return None
        
    @staticmethod
    def create_user_event_store(redis_client=None):
        """
        Crea un almacén de eventos de usuario resiliente.
        
        Args:
            redis_client: Cliente Redis opcional (se creará uno nuevo si no se proporciona)
            
        Returns:
            UserEventStore: Almacén de eventos con patrones de resiliencia
        """
        try:
            from src.api.mcp.user_events.resilient_user_event_store import UserEventStore
            from src.api.core.config import get_settings
            
            settings = get_settings()
            
            # CORRECCIÓN: Construir URL de Redis correctamente con credenciales
            redis_url = "redis://"
            
            # Agregar credenciales si están configuradas
            if settings.redis_username and settings.redis_password:
                redis_url += f"{settings.redis_username}:{settings.redis_password}@"
            elif settings.redis_password:
                # Solo password (Redis < v6)
                redis_url += f":{settings.redis_password}@"
            
            # Agregar host, puerto y base de datos
            redis_url += f"{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
            
            logger.info(f"Construyendo URL Redis: redis://***@{settings.redis_host}:{settings.redis_port}/{settings.redis_db}")
            
            # Verificar si tenemos un cliente Redis o necesitamos crear uno
            if not redis_client:
                redis_client = RecommenderFactory.create_redis_client()
                
                if not redis_client:
                    logger.warning("No se pudo crear cliente Redis para UserEventStore")
                    return None
            
            # Crear directorio de fallback si está configurado
            local_fallback_dir = getattr(settings, 'user_events_fallback_dir', None)
            if local_fallback_dir:
                import os
                os.makedirs(local_fallback_dir, exist_ok=True)
            
            # Crear instancia de UserEventStore con URL corregida
            user_event_store = UserEventStore(
                redis_url=redis_url,  # ✅ URL con credenciales correctas
                cache_ttl=getattr(settings, 'user_event_cache_ttl', 300),
                enable_circuit_breaker=True,
                cache_size=getattr(settings, 'user_event_cache_size', 1000),
                local_buffer_size=getattr(settings, 'user_event_buffer_size', 200),
                flush_interval_seconds=getattr(settings, 'user_event_flush_interval', 30),
                local_fallback_dir=local_fallback_dir
            )
            
            # CORREGIDO: Conexión diferida - el UserEventStore se conectará cuando sea necesario
            # en lugar de crear task asíncrono en contexto síncrono
            logger.info("UserEventStore resiliente creado correctamente con URL autenticada")
            logger.info("Nota: Conexión diferida - se conectará automáticamente al usarse")
            return user_event_store
        except ImportError as e:
            logger.error(f"No se pudo importar UserEventStore resiliente: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creando UserEventStore resiliente: {e}")
            return None
    
    # ============================================================================
    # ✅ ENTERPRISE INTEGRATION METHODS - Redis via ServiceFactory
    # ============================================================================
    
    @staticmethod
    async def create_redis_client_enterprise():
        """
        ✅ ENTERPRISE: Creates Redis client using ServiceFactory architecture.
        
        Returns:
            RedisService underlying client for direct compatibility
        """
        if not ENTERPRISE_INTEGRATION_AVAILABLE:
            logger.error("❌ Enterprise integration not available - use create_redis_client_async() instead")
            return None
            
        try:
            logger.info("✅ Creating Redis client via enterprise ServiceFactory")
            redis_service = await ServiceFactory.get_redis_service()
            logger.info("✅ Enterprise Redis client created successfully")
            return redis_service._client
        except Exception as e:
            logger.error(f"❌ Failed to create enterprise Redis client: {e}")
            return None
    
    @staticmethod
    async def create_product_cache_enterprise(content_recommender=None):
        """
        ✅ ENTERPRISE: Creates ProductCache using ServiceFactory architecture.
        
        Args:
            content_recommender: Optional content recommender for local catalog
            
        Returns:
            ProductCache with enterprise Redis integration
        """
        if not ENTERPRISE_INTEGRATION_AVAILABLE:
            logger.error("❌ Enterprise integration not available - use create_product_cache() instead")
            return None
            
        try:
            logger.info("✅ Creating ProductCache via enterprise ServiceFactory")
            product_cache = await ServiceFactory.get_product_cache_singleton()
            logger.info("✅ Enterprise ProductCache created successfully")
            return product_cache
        except Exception as e:
            logger.error(f"❌ Failed to create enterprise ProductCache: {e}")
            return None
    
    @staticmethod
    async def create_user_event_store_enterprise():
        """
        ✅ ENTERPRISE: Creates UserEventStore using enterprise Redis client.
        
        Returns:
            UserEventStore with enterprise Redis integration
        """
        if not ENTERPRISE_INTEGRATION_AVAILABLE:
            logger.error("❌ Enterprise integration not available - use create_user_event_store_async() instead")
            return None
            
        try:
            logger.info("✅ Creating UserEventStore via enterprise Redis service")
            
            # Get enterprise Redis client
            redis_client = await RecommenderFactory.create_redis_client_enterprise()
            if not redis_client:
                logger.error("❌ Enterprise Redis client not available")
                return None
            
            # Create UserEventStore with enterprise client
            user_event_store = await RecommenderFactory.create_user_event_store_async(redis_client)
            if user_event_store:
                logger.info("✅ Enterprise UserEventStore created successfully")
            else:
                logger.error("❌ Failed to create enterprise UserEventStore")
                
            return user_event_store
        except Exception as e:
            logger.error(f"❌ Failed to create enterprise UserEventStore: {e}")
            return None


    # ========== DIVERSITY CACHE - ENTERPRISE HELPER (module-level) ==========
    async def create_diversity_aware_cache_enterprise(default_ttl: int = 300, redis_service=None):
        """
        Crea DiversityAwareCache intentando derivar categorías reales desde el ProductCache singleton.

        Intenta usar ServiceFactory.get_product_cache_singleton() si está disponible. Devuelve
        una instancia de DiversityAwareCache creada por create_diversity_aware_cache.
        """
        product_cache = None
        local_catalog = None

        if ENTERPRISE_INTEGRATION_AVAILABLE:
            try:
                # Prefer the fully managed singleton
                product_cache = await ServiceFactory.get_product_cache_singleton()
            except Exception:
                # Fallback: try convenience function if present
                try:
                    from .service_factory import get_product_cache
                    product_cache = await get_product_cache()
                except Exception:
                    product_cache = None

        if product_cache:
            local_catalog = getattr(product_cache, 'local_catalog', None)

        cache = await create_diversity_aware_cache(
            redis_service=redis_service,
            default_ttl=default_ttl,
            product_categories=None,
            product_cache=product_cache,
            local_catalog=local_catalog
        )

        return cache