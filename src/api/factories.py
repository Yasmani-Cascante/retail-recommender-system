"""
Fábricas para crear componentes principales del sistema.

Este módulo proporciona fábricas para crear los diferentes componentes
del sistema de recomendaciones según la configuración.
"""

import logging
from src.api.core.config import get_settings
from src.recommenders.tfidf_recommender import TFIDFRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

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
    def create_hybrid_recommender(content_recommender, retail_recommender):
        """
        Crea un recomendador híbrido.
        
        Args:
            content_recommender: Recomendador basado en contenido
            retail_recommender: Recomendador de Retail API
            
        Returns:
            HybridRecommender: Instancia del recomendador híbrido
        """
        settings = get_settings()
        logger.info(f"Creando recomendador híbrido con content_weight={settings.content_weight}")
        logger.info(f"  Exclusión de productos vistos: {settings.exclude_seen_products}")
        
        try:
            # Importar la versión adecuada según la configuración
            if settings.exclude_seen_products:
                logger.info("Usando recomendador híbrido con exclusión de productos vistos")
                from src.api.core.hybrid_recommender import HybridRecommenderWithExclusion
                return HybridRecommenderWithExclusion(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender,
                    content_weight=settings.content_weight
                )
            else:
                logger.info("Usando recomendador híbrido básico")
                from src.api.core.hybrid_recommender import HybridRecommender
                return HybridRecommender(
                    content_recommender=content_recommender,
                    retail_recommender=retail_recommender,
                    content_weight=settings.content_weight
                )
        except ImportError:
            logger.warning("No se pudo cargar el recomendador híbrido unificado. Usando implementación original.")
            
            # Implementación básica como fallback
            from src.recommenders.hybrid import HybridRecommender
            return HybridRecommender(
                content_recommender=content_recommender,
                retail_recommender=retail_recommender, 
                content_weight=settings.content_weight
            )
