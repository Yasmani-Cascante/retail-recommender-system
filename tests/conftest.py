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
import logging
from dotenv import load_dotenv
from pathlib import Path

# Asegurarse de que src está en el PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importar la configuración de logging
from tests.test_logging import setup_test_logging

# Inicializar logging para pruebas
setup_test_logging()

# Importar datos de prueba
from tests.data.sample_products import SAMPLE_PRODUCTS
from tests.data.sample_events import SAMPLE_USER_EVENTS, get_events_for_user
from tests.data.test_configs import TEST_CONFIGS, apply_config_to_env

# Fixture para cargar variables de entorno desde .env.test
@pytest.fixture(scope="session", autouse=True)
def load_test_env():
    """Carga las variables de entorno desde .env.test al inicio de las pruebas."""
    env_test_path = Path(__file__).parent.parent / '.env.test'
    if env_test_path.exists():
        logging.info(f"Cargando variables de entorno desde {env_test_path}")
        load_dotenv(env_test_path)
    else:
        logging.warning(f"Archivo .env.test no encontrado en {env_test_path}")
    
    yield
    # No se limpian las variables al finalizar para evitar afectar otras pruebas

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
        recommender.get_product_by_id = lambda id: next((p for p in SAMPLE_PRODUCTS if str(p.get('id')) == str(id)), None)
        
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
        recommender.ensure_catalog_branches.return_value = asyncio.Future()
        recommender.ensure_catalog_branches.return_value.set_result(True)
        
        # Configurar el constructor del mock para devolver nuestra instancia
        mock.return_value = recommender
        yield recommender

# Fixture para mock del recomendador híbrido
@pytest.fixture
def mock_hybrid_recommender(mock_tfidf_recommender, mock_retail_recommender):
    """Proporciona un mock para el recomendador híbrido."""
    with patch('src.api.core.hybrid_recommender.HybridRecommenderWithExclusion') as mock_class:
        recommender = MagicMock()
        # Configurar métodos necesarios
        recommender.get_recommendations.return_value = asyncio.Future()
        recommender.get_recommendations.return_value.set_result(SAMPLE_PRODUCTS[:5])
        recommender.record_user_event.return_value = asyncio.Future()
        recommender.record_user_event.return_value.set_result({"status": "success", "event_type": "detail-page-view"})
        recommender.content_weight = 0.5
        
        # Configurar constructor para devolver nuestra instancia
        mock_class.return_value = recommender
        
        # Proporcionar acceso a los recomendadores base
        recommender.content_recommender = mock_tfidf_recommender
        recommender.retail_recommender = mock_retail_recommender
        
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

# Fixture para simular un cliente Shopify
@pytest.fixture
def mock_shopify_client():
    """Proporciona un mock para el cliente de Shopify."""
    with patch('src.api.core.store.get_shopify_client') as mock_get_client:
        client = MagicMock()
        
        # Configurar métodos necesarios
        client.get_products.return_value = SAMPLE_PRODUCTS
        client.get_customers.return_value = [
            {"id": "customer_1", "email": "test1@example.com", "first_name": "Test", "last_name": "User1"},
            {"id": "customer_2", "email": "test2@example.com", "first_name": "Test", "last_name": "User2"},
        ]
        client.get_orders_by_customer.return_value = []
        
        # Configurar el mock para devolver nuestra instancia
        mock_get_client.return_value = client
        yield client

# Fixture para datos de rendimiento
@pytest.fixture
def performance_metrics():
    """Proporciona una estructura para recopilar métricas de rendimiento durante las pruebas."""
    import time
    
    class PerformanceMetrics:
        def __init__(self):
            self.start_times = {}
            self.end_times = {}
            self.durations = {}
            
        def start_timer(self, name):
            self.start_times[name] = time.time()
            
        def end_timer(self, name):
            if name in self.start_times:
                self.end_times[name] = time.time()
                self.durations[name] = self.end_times[name] - self.start_times[name]
                return self.durations[name]
            return None
            
        def get_duration(self, name):
            return self.durations.get(name)
            
        def log_all_metrics(self):
            for name, duration in self.durations.items():
                logging.info(f"Métrica de rendimiento - {name}: {duration:.6f} segundos")
    
    return PerformanceMetrics()
