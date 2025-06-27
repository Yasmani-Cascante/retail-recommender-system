"""
Fábricas para crear componentes principales del sistema.

Este módulo proporciona fábricas para crear los diferentes componentes
del sistema de recomendaciones según la configuración.
"""

import logging
import asyncio
from src.api.core.config import get_settings
from src.recommenders.tfidf_recommender import TFIDFRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from typing import Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

class MCPFactory:
    """Fábrica para crear componentes relacionados con MCP."""
    
    @staticmethod
    def create_mcp_client():
        """
        Crea un cliente MCP para Shopify.
        
        Returns:
            MCPClient: Cliente MCP inicializado
        """
        settings = get_settings()
        
        try:
            from src.api.mcp.client.mcp_client import MCPClient
            
            logger.info(f"Creando cliente MCP bridge en puerto 3001")
            client = MCPClient(bridge_host="localhost", bridge_port=3001)
            
            return client
        except ImportError:
            logger.error("No se pudo importar MCPClient. Verifica la instalación.")
            return None
        except Exception as e:
            logger.error(f"Error creando cliente MCP: {str(e)}")
            return None
    
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
        user_event_store=None
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
                logger.info("Usando base recommender proporcionado")
            
            # 2. Usar MCP client proporcionado o crear uno nuevo
            if mcp_client is None:
                mcp_client = MCPFactory.create_mcp_client()
                if not mcp_client:
                    logger.warning("MCP client no disponible, usando fallback")
                else:
                    logger.info("MCP client creado automáticamente")
            else:
                logger.info("Usando MCP client proporcionado")
            
            # 3. Usar market manager proporcionado o crear uno nuevo
            if market_manager is None:
                market_manager = MCPFactory.create_market_manager()
                if not market_manager:
                    logger.warning("Market manager no disponible, usando fallback")
                else:
                    logger.info("Market manager creado automáticamente")
            else:
                logger.info("Usando market manager proporcionado")
            
            # 4. Usar market cache proporcionado o crear uno nuevo
            if market_cache is None:
                market_cache = MCPFactory.create_market_cache()
                if not market_cache:
                    logger.warning("Market cache no disponible, usando fallback")
                else:
                    logger.info("Market cache creado automáticamente")
            else:
                logger.info("Usando market cache proporcionado")
            
            # 5. Usar user_event_store proporcionado o crear uno nuevo
            if user_event_store is None:
                user_event_store = RecommenderFactory.create_user_event_store(redis_client)
                if not user_event_store:
                    logger.warning("UserEventStore no disponible, usando fallback")
                else:
                    logger.info("UserEventStore creado automáticamente")
            else:
                logger.info("Usando UserEventStore proporcionado")
            
            # 6. Crear el recomendador MCP con todos los componentes
            mcp_recommender = MCPAwareRecommender(
                base_recommender=base_recommender,
                mcp_client=mcp_client,
                user_event_store=user_event_store
            )
            
            logger.info("MCPAwareRecommender creado exitosamente")
            return mcp_recommender
                
        except ImportError as e:
            logger.error(f"No se pudo importar MCPAwareRecommender: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creando MCPAwareRecommender: {e}")
            return None


class RecommenderFactory:
    """Fábrica para crear recomendadores."""
    
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
            from src.api.core.redis_client import RedisClient
            
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
            
            # Iniciar conexión en segundo plano
            asyncio.create_task(redis_client.connect())
            
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
            
        try:
            from src.api.core.product_cache import ProductCache
            
            # Crear cliente Redis
            redis_client = RecommenderFactory.create_redis_client()
            if not redis_client:
                logger.warning("No se pudo crear cliente Redis, ProductCache desactivada")
                return None
            
            logger.info(f"Creando ProductCache con TTL={settings.cache_ttl}s")
            
            # Crear caché de productos
            cache = ProductCache(
                redis_client=redis_client,
                local_catalog=content_recommender,
                shopify_client=shopify_client,
                ttl_seconds=settings.cache_ttl,
                prefix=settings.cache_prefix
            )
            
            # Iniciar tareas en segundo plano si está configurado
            if settings.cache_enable_background_tasks:
                asyncio.create_task(cache.start_background_tasks())
                logger.info("Tareas en segundo plano de ProductCache iniciadas")
            
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
            
            # Verificar si tenemos un cliente Redis o necesitamos crear uno
            if not redis_client:
                from src.api.factories import RecommenderFactory
                redis_client = RecommenderFactory.create_redis_client()
                
                if not redis_client:
                    logger.warning("No se pudo crear cliente Redis para UserEventStore")
                    return None
            
            # Crear directorio de fallback si está configurado
            local_fallback_dir = getattr(settings, 'user_events_fallback_dir', None)
            if local_fallback_dir:
                import os
                os.makedirs(local_fallback_dir, exist_ok=True)
            
            # Crear instancia de UserEventStore
            redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
            
            user_event_store = UserEventStore(
                redis_url=redis_url,
                cache_ttl=getattr(settings, 'user_event_cache_ttl', 300),
                enable_circuit_breaker=True,
                cache_size=getattr(settings, 'user_event_cache_size', 1000),
                local_buffer_size=getattr(settings, 'user_event_buffer_size', 200),
                flush_interval_seconds=getattr(settings, 'user_event_flush_interval', 30),
                local_fallback_dir=local_fallback_dir
            )
            
            # Iniciar conexión en segundo plano
            import asyncio
            asyncio.create_task(user_event_store.connect())
            
            logger.info("UserEventStore resiliente creado correctamente")
            return user_event_store
        except ImportError as e:
            logger.error(f"No se pudo importar UserEventStore resiliente: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creando UserEventStore resiliente: {e}")
            return None