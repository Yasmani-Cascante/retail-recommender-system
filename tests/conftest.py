"""
Configuración para pruebas de PyTest para el sistema de recomendaciones.

Este módulo proporciona fixtures y configuraciones para facilitar las pruebas
del sistema de recomendaciones.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import asyncio

# Asegurarse de que src está en el PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importar datos de prueba
from tests.data.sample_products import SAMPLE_PRODUCTS
from tests.data.sample_events import SAMPLE_USER_EVENTS, get_events_for_user
from tests.data.test_configs import TEST_CONFIGS, apply_config_to_env

# Fixture para configurar variables de entorno de prueba
@pytest.fixture
def test_env():
    """Configura variables de entorno básicas para pruebas."""
    old_environ = dict(os.environ)
    os.environ.update({
        "GOOGLE_PROJECT_NUMBER": "test-project-123",
        "GOOGLE_LOCATION": "global",
        "GOOGLE_CATALOG": "test-catalog",
        "GOOGLE_SERVING_CONFIG": "test-config",
        "API_KEY": "test-api-key-123",
        "DEBUG": "true",
        "METRICS_ENABLED": "true",
        "EXCLUDE_SEEN_PRODUCTS": "true",
        "VALIDATE_PRODUCTS": "true",
        "USE_FALLBACK": "true",
        "CONTENT_WEIGHT": "0.5"
    })
    yield
    os.environ.clear()
    os.environ.update(old_environ)

# Fixture para configurar variables de entorno con una configuración específica
@pytest.fixture
def config_env(request):
    """
    Configura variables de entorno según una configuración específica.
    
    Uso: @pytest.mark.parametrize("config_env", ["full_features", "no_metrics", ...], indirect=True)
    """
    config_name = request.param
    old_environ = dict(os.environ)
    
    # Aplicar configuración base de prueba
    os.environ.update({
        "GOOGLE_PROJECT_NUMBER": "test-project-123",
        "GOOGLE_LOCATION": "global",
        "GOOGLE_CATALOG": "test-catalog",
        "GOOGLE_SERVING_CONFIG": "test-config",
        "API_KEY": "test-api-key-123"
    })
    
    # Aplicar configuración específica
    config = TEST_CONFIGS.get(config_name, TEST_CONFIGS["full_features"])
    os.environ.update(config)
    
    yield config_name
    
    os.environ.clear()
    os.environ.update(old_environ)

# Fixture para mock de TFIDFRecommender
@pytest.fixture
def mock_tfidf_recommender():
    """Proporciona un mock para el recomendador TF-IDF."""
    with patch('src.recommenders.tfidf_recommender.TFIDFRecommender') as mock:
        recommender = MagicMock()
        # Configurar el mock para que tenga los métodos necesarios
        recommender.fit.return_value = asyncio.Future()
        recommender.fit.return_value.set_result(True)
        recommender.get_recommendations.return_value = asyncio.Future()
        recommender.get_recommendations.return_value.set_result(SAMPLE_PRODUCTS[:3])
        recommender.search_products.return_value = asyncio.Future()
        recommender.search_products.return_value.set_result(SAMPLE_PRODUCTS[:2])
        recommender.loaded = True
        recommender.product_data = SAMPLE_PRODUCTS
        recommender.health_check.return_value = asyncio.Future()
        recommender.health_check.return_value.set_result({"status": "operational", "loaded": True})
        
        # Configurar el constructor del mock para devolver nuestra instancia
        mock.return_value = recommender
        yield recommender

# Fixture para mock de RetailAPIRecommender
@pytest.fixture
def mock_retail_recommender():
    """Proporciona un mock para el recomendador Retail API."""
    with patch('src.recommenders.retail_api.RetailAPIRecommender') as mock:
        recommender = MagicMock()
        # Configurar el mock para que tenga los métodos necesarios
        recommender.import_catalog.return_value = asyncio.Future()
        recommender.import_catalog.return_value.set_result({"status": "success", "products_imported": len(SAMPLE_PRODUCTS)})
        recommender.get_recommendations.return_value = asyncio.Future()
        recommender.get_recommendations.return_value.set_result(SAMPLE_PRODUCTS[3:6])
        recommender.record_user_event.return_value = asyncio.Future()
        recommender.record_user_event.return_value.set_result({"status": "success"})
        recommender.get_user_events.return_value = asyncio.Future()
        recommender.get_user_events.return_value.set_result(get_events_for_user("test_user_1"))
        
        # Configurar el constructor del mock para devolver nuestra instancia
        mock.return_value = recommender
        yield recommender

# Fixture para FastAPI TestClient
@pytest.fixture
def client():
    """Proporciona un cliente de prueba para la API."""
    from fastapi.testclient import TestClient
    from src.api.main_unified import app
    
    return TestClient(app)

# Fixture para el loop de eventos de asyncio
@pytest.fixture
def event_loop():
    """Proporciona un loop de eventos para pruebas asíncronas."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
