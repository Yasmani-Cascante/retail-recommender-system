"""
Configuración mejorada para pruebas de integración del sistema de recomendaciones.

Este módulo configura fixtures y configuraciones robustas para todas las pruebas,
incluyendo mocks correctamente configurados y datos de prueba consistentes.
"""

import pytest
import os
import sys
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import Depends
from fastapi.testclient import TestClient
from typing import Optional, List, Dict

# Asegurar que src está en el PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# API Key para pruebas
TEST_API_KEY = "test-api-key-123"

# Importar datos de prueba consistentes
from tests.data.sample_products import SAMPLE_PRODUCTS

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configura el entorno para todas las pruebas."""
    # Guardar variables de entorno originales
    original_env = os.environ.copy()
    
    # Configurar variables de entorno para pruebas
    test_env_vars = {
        "TEST_MODE": "true",
        "API_KEY": TEST_API_KEY,
        "DEBUG": "true",
        "METRICS_ENABLED": "true",
        "EXCLUDE_SEEN_PRODUCTS": "true",
        "USE_REDIS_CACHE": "false",  # Desactivar Redis para pruebas
        "GOOGLE_PROJECT_NUMBER": "test-project-123",
        "GOOGLE_LOCATION": "global",
        "GOOGLE_CATALOG": "test_catalog",
        "GOOGLE_SERVING_CONFIG": "test_config",
        "STARTUP_TIMEOUT": "10.0"  # Timeout más corto para pruebas
    }
    
    for key, value in test_env_vars.items():
        os.environ[key] = value
    
    # Devolver control a las pruebas
    yield
    
    # Restaurar variables de entorno originales
    os.environ.clear()
    os.environ.update(original_env)

# Fixtures para componentes mockeados
@pytest.fixture
def mock_tfidf_recommender():
    """Mock robusto para el recomendador TF-IDF."""
    recommender = MagicMock()
    recommender.loaded = True
    recommender.product_data = SAMPLE_PRODUCTS
    recommender._validate_state.return_value = True
    
    # Configurar método get_product_by_id
    def mock_get_product_by_id(product_id):
        for product in SAMPLE_PRODUCTS:
            if str(product.get('id', '')) == str(product_id):
                return product
        return None
    
    recommender.get_product_by_id = mock_get_product_by_id
    
    # Configurar métodos asíncronos
    async def mock_get_recommendations(product_id, n=5):
        # Simular recomendaciones basadas en el producto solicitado
        if mock_get_product_by_id(product_id):
            return SAMPLE_PRODUCTS[:min(n, len(SAMPLE_PRODUCTS))]
        return []
        
    async def mock_search_products(query, n=10):
        # Simular búsqueda - devolver productos que contengan la query en el título
        results = [
            p for p in SAMPLE_PRODUCTS 
            if query.lower() in p.get('title', '').lower()
        ]
        return results[:n]
        
    async def mock_health_check():
        return {
            "status": "operational",
            "loaded": True,
            "products_count": len(SAMPLE_PRODUCTS)
        }
    
    async def mock_fit(products):
        recommender.product_data = products
        recommender.loaded = True
        return True
        
    async def mock_load():
        recommender.loaded = True
        return True
    
    recommender.get_recommendations = AsyncMock(side_effect=mock_get_recommendations)
    recommender.search_products = AsyncMock(side_effect=mock_search_products)
    recommender.health_check = AsyncMock(side_effect=mock_health_check)
    recommender.fit = AsyncMock(side_effect=mock_fit)
    recommender.load = AsyncMock(side_effect=mock_load)
    
    return recommender

@pytest.fixture
def mock_retail_recommender():
    """Mock robusto para el recomendador de Retail API."""
    recommender = MagicMock()
    
    async def mock_get_recommendations(user_id, product_id=None, n_recommendations=5):
        # Simular recomendaciones de Retail API
        return SAMPLE_PRODUCTS[:min(n_recommendations, len(SAMPLE_PRODUCTS))]
        
    async def mock_record_user_event(user_id, event_type, product_id=None, purchase_amount=None):
        return {
            "status": "success",
            "message": "Event recorded successfully",
            "event_type": event_type,
            "user_id": user_id,
            "product_id": product_id
        }
    
    async def mock_import_catalog(products):
        return {
            "status": "success",
            "products_imported": len(products)
        }
    
    async def mock_ensure_catalog_branches():
        return True
        
    async def mock_get_user_events(user_id):
        # Simular eventos para usuarios de prueba
        if user_id.startswith("test_"):
            return [
                {"user_id": user_id, "event_type": "detail-page-view", "product_id": "test_prod_1"},
                {"user_id": user_id, "event_type": "add-to-cart", "product_id": "test_prod_2"}
            ]
        return []
        
    recommender.get_recommendations = AsyncMock(side_effect=mock_get_recommendations)
    recommender.record_user_event = AsyncMock(side_effect=mock_record_user_event)
    recommender.import_catalog = AsyncMock(side_effect=mock_import_catalog)
    recommender.ensure_catalog_branches = AsyncMock(side_effect=mock_ensure_catalog_branches)
    recommender.get_user_events = AsyncMock(side_effect=mock_get_user_events)
    
    return recommender

@pytest.fixture
def mock_hybrid_recommender(mock_tfidf_recommender, mock_retail_recommender):
    """Mock robusto para el recomendador híbrido."""
    recommender = MagicMock()
    recommender.content_recommender = mock_tfidf_recommender
    recommender.retail_recommender = mock_retail_recommender
    recommender.content_weight = 0.5
    
    async def mock_get_recommendations(user_id, product_id=None, n_recommendations=5):
        # Simular combinación de recomendaciones
        return SAMPLE_PRODUCTS[:min(n_recommendations, len(SAMPLE_PRODUCTS))]
        
    async def mock_record_user_event(user_id, event_type, product_id=None, purchase_amount=None):
        return await mock_retail_recommender.record_user_event(
            user_id, event_type, product_id, purchase_amount
        )
    
    recommender.get_recommendations = AsyncMock(side_effect=mock_get_recommendations)
    recommender.record_user_event = AsyncMock(side_effect=mock_record_user_event)
    
    return recommender

@pytest.fixture
def mock_shopify_client():
    """Mock robusto para el cliente de Shopify."""
    client = MagicMock()
    
    # Datos de clientes de prueba consistentes
    test_customers = [
        {"id": "test_customer_1", "email": "test1@example.com", "first_name": "Test", "last_name": "User1"},
        {"id": "test_customer_2", "email": "test2@example.com", "first_name": "Test", "last_name": "User2"}
    ]
    
    client.get_products.return_value = SAMPLE_PRODUCTS
    client.get_customers.return_value = test_customers
    
    # Configurar método get_product para búsqueda individual
    def mock_get_product(product_id):
        for product in SAMPLE_PRODUCTS:
            if str(product.get('id', '')) == str(product_id):
                return product
        return None
    
    client.get_product = mock_get_product
    
    # Configurar órdenes por cliente
    def mock_get_orders_by_customer(customer_id):
        if customer_id.startswith("test_"):
            return [
                {"id": "order_1", "customer_id": customer_id, "line_items": [{"product_id": "test_prod_1"}]}
            ]
        return []
    
    client.get_orders_by_customer = mock_get_orders_by_customer
    
    return client

@pytest.fixture
def mock_startup_manager():
    """Mock para el gestor de arranque."""
    manager = MagicMock()
    manager.is_healthy.return_value = (True, "")
    manager.get_status.return_value = {
        "status": "operational",
        "components_loaded": True,
        "loading_complete": True
    }
    
    def mock_register_component(name, loader, required=True):
        pass
    
    async def mock_start_loading():
        return True
    
    manager.register_component = mock_register_component
    manager.start_loading = AsyncMock(side_effect=mock_start_loading)
    
    return manager

# Mock para autenticación
async def mock_get_api_key():
    """Mock para la función get_api_key que siempre retorna la API key de prueba."""
    return TEST_API_KEY

async def mock_get_current_user(api_key: str = Depends(mock_get_api_key)) -> Optional[str]:
    """Mock para la función get_current_user."""
    return "test_user"

# Mock para autenticación fallida
async def mock_get_api_key_failed():
    """Mock que simula fallo de autenticación."""
    from fastapi import HTTPException
    raise HTTPException(status_code=403, detail="API Key no válida")

@pytest.fixture
def mock_get_shopify_client(mock_shopify_client):
    """Mock para la función get_shopify_client."""
    return lambda: mock_shopify_client

@pytest.fixture
def test_app_with_mocks(
    mock_tfidf_recommender,
    mock_retail_recommender,
    mock_hybrid_recommender,
    mock_shopify_client,
    mock_startup_manager
):
    """
    Fixture que proporciona una app FastAPI completamente mockeada para pruebas.
    """
    # Patch los módulos antes de importar la aplicación
    with patch('src.api.factories.RecommenderFactory.create_tfidf_recommender') as mock_create_tfidf, \
         patch('src.api.factories.RecommenderFactory.create_retail_recommender') as mock_create_retail, \
         patch('src.api.factories.RecommenderFactory.create_hybrid_recommender') as mock_create_hybrid, \
         patch('src.api.core.store.get_shopify_client') as mock_get_shopify, \
         patch('src.api.core.store.init_shopify') as mock_init_shopify, \
         patch('src.api.startup_helper.StartupManager') as mock_startup_class:
        
        # Configurar los mocks de las fábricas
        mock_create_tfidf.return_value = mock_tfidf_recommender
        mock_create_retail.return_value = mock_retail_recommender
        mock_create_hybrid.return_value = mock_hybrid_recommender
        mock_get_shopify.return_value = mock_shopify_client
        mock_init_shopify.return_value = mock_shopify_client
        mock_startup_class.return_value = mock_startup_manager
        
        # Ahora importar la aplicación con todos los mocks en su lugar
        from src.api.main_unified import app
        
        # Configurar dependency overrides para autenticación
        from src.api.security import get_api_key, get_current_user
        app.dependency_overrides[get_api_key] = mock_get_api_key
        app.dependency_overrides[get_current_user] = mock_get_current_user
        
        # Asegurar que los componentes globales están disponibles
        app.state.tfidf_recommender = mock_tfidf_recommender
        app.state.retail_recommender = mock_retail_recommender
        app.state.hybrid_recommender = mock_hybrid_recommender
        app.state.startup_manager = mock_startup_manager
        
        yield app
        
        # Limpiar dependency overrides
        app.dependency_overrides.clear()

@pytest.fixture
def test_client(test_app_with_mocks):
    """Fixture que proporciona un cliente para pruebas con todos los mocks configurados."""
    with TestClient(test_app_with_mocks) as client:
        # Añadir API key a headers por defecto
        client.headers.update({"X-API-Key": TEST_API_KEY})
        yield client

@pytest.fixture
def test_client_no_auth(test_app_with_mocks):
    """Fixture que proporciona un cliente sin autenticación para probar errores de autenticación."""
    # Crear una app limpia para evitar problemas de estado entre pruebas
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from src.api.security import get_api_key, get_current_user
    
    # Función que siempre falla la autenticación
    async def always_fail_auth():
        raise HTTPException(status_code=403, detail="API Key inválida o no proporcionada")
    
    # Función que intenta obtener usuario y también falla
    async def fail_get_user():
        raise HTTPException(status_code=403, detail="Autenticación fallida")
    
    # Aplicar el override directamente en la app de prueba
    test_app = test_app_with_mocks
    
    # Guardar las dependencias originales para restaurarlas después
    original_overrides = test_app.dependency_overrides.copy()
    
    # Aplicar nuevos overrides
    test_app.dependency_overrides[get_api_key] = always_fail_auth
    test_app.dependency_overrides[get_current_user] = fail_get_user
    
    # Asegurar que se ha limpiado cualquier configuración anterior
    test_client = TestClient(test_app)
    
    # Eliminar cualquier API key de los headers
    test_client.headers.clear()
    
    # Log para verificar el estado
    print("\nFixture test_client_no_auth: Dependencias anuladas para forzar error 403")
    print(f"Headers del cliente: {test_client.headers}")
    
    # Devolver el cliente configurado
    yield test_client
    
    # Restaurar las dependencias originales
    test_app.dependency_overrides = original_overrides

# Fixture para datos de prueba adicionales
@pytest.fixture
def test_user_events():
    """Fixture que proporciona eventos de usuario de prueba."""
    return [
        {"user_id": "test_user_1", "event_type": "detail-page-view", "product_id": "test_prod_1"},
        {"user_id": "test_user_1", "event_type": "add-to-cart", "product_id": "test_prod_2"},
        {"user_id": "test_user_1", "event_type": "purchase-complete", "product_id": "test_prod_1", "purchase_amount": 19.99}
    ]

# Utilidades para pruebas asíncronas
def async_test(f):
    """Decorador para ejecutar funciones asíncronas en pruebas."""
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper
