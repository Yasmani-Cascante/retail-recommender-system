"""
Pruebas unitarias para las fábricas de componentes.

Este módulo contiene pruebas para verificar que las fábricas crean correctamente
los diferentes componentes del sistema según la configuración.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from src.api.factories import RecommenderFactory
from src.recommenders.tfidf_recommender import TFIDFRecommender
from src.recommenders.retail_api import RetailAPIRecommender

@pytest.fixture
def mock_settings():
    """Fixture para simular la configuración con valores predeterminados."""
    with patch('src.api.factories.get_settings') as mock_get_settings:
        settings = MagicMock()
        settings.google_project_number = "test-project-123"
        settings.google_location = "global"
        settings.google_catalog = "test-catalog"
        settings.google_serving_config = "test-config"
        settings.content_weight = 0.5
        settings.exclude_seen_products = True
        mock_get_settings.return_value = settings
        yield settings

def test_create_tfidf_recommender():
    """Verifica que se crea correctamente un recomendador TF-IDF."""
    # Crear recomendador con el método de fábrica
    with patch('src.api.factories.TFIDFRecommender') as mock_tfidf:
        mock_instance = MagicMock()
        mock_tfidf.return_value = mock_instance
        
        # Llamar al método de fábrica
        recommender = RecommenderFactory.create_tfidf_recommender(model_path="test_path.pkl")
        
        # Verificar que se creó con los parámetros correctos
        mock_tfidf.assert_called_once_with(model_path="test_path.pkl")
        assert recommender is mock_instance

def test_create_retail_recommender(mock_settings):
    """Verifica que se crea correctamente un recomendador Retail API."""
    # Crear recomendador con el método de fábrica
    with patch('src.api.factories.RetailAPIRecommender') as mock_retail:
        mock_instance = MagicMock()
        mock_retail.return_value = mock_instance
        
        # Llamar al método de fábrica
        recommender = RecommenderFactory.create_retail_recommender()
        
        # Verificar que se creó con los parámetros correctos
        mock_retail.assert_called_once_with(
            project_number=mock_settings.google_project_number,
            location=mock_settings.google_location,
            catalog=mock_settings.google_catalog,
            serving_config_id=mock_settings.google_serving_config
        )
        assert recommender is mock_instance

def test_create_hybrid_recommender_with_exclusion(mock_settings):
    """Verifica que se crea correctamente un recomendador híbrido con exclusión."""
    # Configurar mock para que exclude_seen_products = True
    mock_settings.exclude_seen_products = True
    
    # Crear mocks para los módulos y clases importados
    with patch('src.api.factories.HybridRecommenderWithExclusion') as mock_hybrid_with_exclusion:
        # Configurar el mock para que devuelva una instancia específica
        mock_instance = MagicMock()
        mock_hybrid_with_exclusion.return_value = mock_instance
        
        # Crear mocks para los recomendadores que se pasarán como parámetros
        content_recommender = MagicMock()
        retail_recommender = MagicMock()
        
        # Llamar al método de fábrica
        recommender = RecommenderFactory.create_hybrid_recommender(
            content_recommender, retail_recommender
        )
        
        # Verificar que se creó con los parámetros correctos
        mock_hybrid_with_exclusion.assert_called_once_with(
            content_recommender=content_recommender,
            retail_recommender=retail_recommender,
            content_weight=mock_settings.content_weight
        )
        assert recommender is mock_instance

def test_create_hybrid_recommender_without_exclusion(mock_settings):
    """Verifica que se crea correctamente un recomendador híbrido sin exclusión."""
    # Configurar mock para que exclude_seen_products = False
    mock_settings.exclude_seen_products = False
    
    # Crear mocks para los módulos y clases importados
    with patch('src.api.factories.HybridRecommender') as mock_hybrid:
        # Configurar el mock para que devuelva una instancia específica
        mock_instance = MagicMock()
        mock_hybrid.return_value = mock_instance
        
        # Crear mocks para los recomendadores que se pasarán como parámetros
        content_recommender = MagicMock()
        retail_recommender = MagicMock()
        
        # Llamar al método de fábrica
        recommender = RecommenderFactory.create_hybrid_recommender(
            content_recommender, retail_recommender
        )
        
        # Verificar que se creó con los parámetros correctos
        mock_hybrid.assert_called_once_with(
            content_recommender=content_recommender,
            retail_recommender=retail_recommender,
            content_weight=mock_settings.content_weight
        )
        assert recommender is mock_instance

def test_create_hybrid_recommender_fallback(mock_settings):
    """Verifica el comportamiento fallback cuando falla la importación."""
    # Simular un error de importación
    with patch('src.api.factories.HybridRecommenderWithExclusion', side_effect=ImportError()), \
         patch('src.api.factories.HybridRecommender', side_effect=ImportError()), \
         patch('src.api.factories.HybridRecommender', new=None), \
         patch('src.recommenders.hybrid.HybridRecommender') as mock_hybrid_fallback:
        
        # Configurar el mock para que devuelva una instancia específica
        mock_instance = MagicMock()
        mock_hybrid_fallback.return_value = mock_instance
        
        # Crear mocks para los recomendadores que se pasarán como parámetros
        content_recommender = MagicMock()
        retail_recommender = MagicMock()
        
        # Llamar al método de fábrica
        recommender = RecommenderFactory.create_hybrid_recommender(
            content_recommender, retail_recommender
        )
        
        # Verificar que se usó la implementación de fallback
        mock_hybrid_fallback.assert_called_once_with(
            content_recommender=content_recommender,
            retail_recommender=retail_recommender,
            content_weight=mock_settings.content_weight
        )
        assert recommender is mock_instance
