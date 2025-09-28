"""
Instancias de recomendadores utilizadas en la aplicación.

Este módulo crea las instancias de recomendadores que serán utilizadas
en toda la aplicación, utilizando la fábrica para crear los componentes.
"""

import os
import logging
from src.api.factories.factories import RecommenderFactory
from src.api.core.config import get_settings

logger = logging.getLogger(__name__)

# Obtener configuración centralizada
settings = get_settings()

logger.info(f"ℹ️ Inicializando recomendadores con la siguiente configuración:")
logger.info(f"  Project={settings.google_project_number}")
logger.info(f"  Location={settings.google_location}")
logger.info(f"  Catalog={settings.google_catalog}")
logger.info(f"  ServingConfig={settings.google_serving_config}")
logger.info(f"  Content weight={settings.content_weight}")

# Crear recomendadores utilizando la factoría
try:
    # Crear recomendador basado en contenido (TF-IDF por defecto)
    content_recommender = RecommenderFactory.create_content_recommender()
    logger.info("✅ Recomendador basado en contenido creado")
    
    # Crear recomendador Retail API
    retail_recommender = RecommenderFactory.create_retail_recommender()
    logger.info("✅ Recomendador Retail API creado")
    
    # Crear caché de productos (si está habilitada)
    product_cache = RecommenderFactory.create_product_cache(
        content_recommender=content_recommender
    )
    logger.info("✅ Caché de productos creada" if product_cache else "ℹ️ Caché de productos deshabilitada")
    
    # Crear recomendador híbrido unificado
    hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
        content_recommender=content_recommender,
        retail_recommender=retail_recommender,
        product_cache=product_cache
    )
    logger.info("✅ Recomendador híbrido unificado creado")
    
except Exception as e:
    logger.error(f"❌ Error al crear recomendadores: {str(e)}")
    
    # Fallback para garantizar que la aplicación pueda iniciar
    from src.recommenders.tfidf_recommender import TFIDFRecommender
    from src.recommenders.retail_api import RetailAPIRecommender
    from src.api.core.hybrid_recommender import HybridRecommender
    
    logger.warning("⚠️ Usando inicialización de respaldo para recomendadores")
    
    content_recommender = TFIDFRecommender()
    logger.info("✅ Recomendador TF-IDF creado (fallback)")
    
    retail_recommender = RetailAPIRecommender(
        project_number=settings.google_project_number,
        location=settings.google_location,
        catalog=settings.google_catalog,
        serving_config_id=settings.google_serving_config
    )
    logger.info("✅ Recomendador Retail API creado (fallback)")
    
    hybrid_recommender = HybridRecommender(
        content_recommender=content_recommender,
        retail_recommender=retail_recommender,
        content_weight=settings.content_weight
    )
    logger.info("✅ Recomendador híbrido creado (fallback)")
    
    product_cache = None