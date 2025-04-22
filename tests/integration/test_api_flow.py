"""
Pruebas de integración para los flujos principales de la API.

Este módulo contiene pruebas que verifican el funcionamiento end-to-end
de los principales flujos de trabajo de la API, asegurando que los componentes
interactúan correctamente entre sí.
"""

import pytest
import os
import json
import logging
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Asegurar que src está en el PYTHONPATH
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Importar test_logging para configurar logging
from tests.test_logging import setup_test_logging
from tests.data.sample_products import SAMPLE_PRODUCTS

# Configurar logging
logger = setup_test_logging()

class TestAPIIntegrationFlows:
    """Pruebas de integración para los flujos principales de la API."""
    
    @pytest.fixture
    def mock_client(self):
        """
        Fixture que proporciona un cliente de prueba con mocks para componentes externos.
        
        Este enfoque permite probar flujos completos de la API sin depender de servicios externos.
        """
        # Patch múltiples componentes
        with patch('src.api.factories.RecommenderFactory.create_tfidf_recommender') as mock_create_tfidf, \
             patch('src.api.factories.RecommenderFactory.create_retail_recommender') as mock_create_retail, \
             patch('src.api.factories.RecommenderFactory.create_hybrid_recommender') as mock_create_hybrid, \
             patch('src.api.core.store.get_shopify_client') as mock_get_shopify, \
             patch('src.api.startup_helper.StartupManager.is_healthy') as mock_is_healthy:
            
            # Configurar mocks para recomendadores
            mock_tfidf = MagicMock()
            mock_tfidf.loaded = True
            mock_tfidf.product_data = SAMPLE_PRODUCTS
            mock_tfidf.get_product_by_id = lambda id: next((p for p in SAMPLE_PRODUCTS if str(p.get('id')) == str(id)), None)
            mock_tfidf.health_check.return_value = {"status": "operational", "loaded": True}
            mock_tfidf.search_products = MagicMock(return_value=SAMPLE_PRODUCTS[:3])
            mock_create_tfidf.return_value = mock_tfidf
            
            mock_retail = MagicMock()
            mock_create_retail.return_value = mock_retail
            
            mock_hybrid = MagicMock()
            mock_hybrid.get_recommendations.return_value = SAMPLE_PRODUCTS[:5]
            mock_hybrid.record_user_event.return_value = {"status": "success", "event_type": "detail-page-view"}
            mock_hybrid.content_weight = 0.5
            mock_create_hybrid.return_value = mock_hybrid
            
            # Configurar mock para Shopify
            mock_shopify = MagicMock()
            mock_shopify.get_products.return_value = SAMPLE_PRODUCTS
            mock_shopify.get_customers.return_value = [
                {"id": "customer_1", "email": "test1@example.com", "first_name": "Test", "last_name": "User1"},
                {"id": "customer_2", "email": "test2@example.com", "first_name": "Test", "last_name": "User2"}
            ]
            mock_get_shopify.return_value = mock_shopify
            
            # Configurar mock para verificación de salud
            mock_is_healthy.return_value = (True, "")
            
            # Importar aplicación e inicializar cliente
            from src.api.main_unified import app
            client = TestClient(app)
            
            # Añadir mocks al cliente para que puedan verificarse en los tests
            client.mock_tfidf = mock_tfidf
            client.mock_retail = mock_retail
            client.mock_hybrid = mock_hybrid
            client.mock_shopify = mock_shopify
            
            yield client
    
    def test_health_check_flow(self, mock_client):
        """Verifica el flujo completo del endpoint health check."""
        # Ejecutar solicitud
        response = mock_client.get("/health")
        
        # Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "uptime_seconds" in data
        assert data["components"]["recommender"]["status"] == "operational"
        
        # Verificar que se llamó al health check del recomendador
        mock_client.mock_tfidf.health_check.assert_called_once()
    
    def test_get_recommendations_flow(self, mock_client):
        """Verifica el flujo completo del endpoint de recomendaciones."""
        # Configurar API key para autenticación
        headers = {"X-API-Key": "test-api-key-123"}
        
        # Ejecutar solicitud
        response = mock_client.get(
            "/v1/recommendations/test_prod_1?n=5&content_weight=0.6",
            headers=headers
        )
        
        # Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert len(data["recommendations"]) == 5
        assert "metadata" in data
        assert data["metadata"]["content_weight"] == 0.6
        
        # Verificar que se llamó al método correcto del recomendador híbrido
        mock_client.mock_hybrid.get_recommendations.assert_called_once()
        # Verificar que se actualizó el content_weight
        assert mock_client.mock_hybrid.content_weight == 0.6
    
    def test_user_recommendations_flow(self, mock_client):
        """Verifica el flujo completo del endpoint de recomendaciones para usuario."""
        # Configurar API key para autenticación
        headers = {"X-API-Key": "test-api-key-123"}
        
        # Ejecutar solicitud
        response = mock_client.get(
            "/v1/recommendations/user/test_user_1?n=4",
            headers=headers
        )
        
        # Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert len(data["recommendations"]) == 5  # Devuelve lo que mockea mock_hybrid
        assert "metadata" in data
        assert data["metadata"]["user_id"] == "test_user_1"
        
        # Verificar que se llamó al método correcto
        mock_client.mock_hybrid.get_recommendations.assert_called_with(
            user_id="test_user_1",
            n_recommendations=4
        )
    
    def test_record_user_event_flow(self, mock_client):
        """Verifica el flujo completo del endpoint de registro de eventos de usuario."""
        # Configurar API key para autenticación
        headers = {"X-API-Key": "test-api-key-123"}
        
        # Ejecutar solicitud
        response = mock_client.post(
            "/v1/events/user/test_user_1?event_type=detail-page-view&product_id=test_prod_1",
            headers=headers
        )
        
        # Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "success"
        assert "detail" in data
        assert data["detail"]["user_id"] == "test_user_1"
        assert data["detail"]["event_type"] == "detail-page-view"
        assert data["detail"]["product_id"] == "test_prod_1"
        
        # Verificar que se llamó al método correcto
        mock_client.mock_hybrid.record_user_event.assert_called_once_with(
            user_id="test_user_1",
            event_type="detail-page-view",
            product_id="test_prod_1",
            purchase_amount=None
        )
    
    def test_get_products_flow(self, mock_client):
        """Verifica el flujo completo del endpoint de listado de productos."""
        # Ejecutar solicitud
        response = mock_client.get("/v1/products/")
        
        # Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["total"] == len(SAMPLE_PRODUCTS)
        
        # Verificar paginación
        response_page2 = mock_client.get("/v1/products/?page=2&page_size=3")
        assert response_page2.status_code == 200
        data_page2 = response_page2.json()
        assert len(data_page2["products"]) <= 3
        assert data_page2["page"] == 2
    
    def test_search_products_flow(self, mock_client):
        """Verifica el flujo completo del endpoint de búsqueda de productos."""
        # Configurar API key para autenticación
        headers = {"X-API-Key": "test-api-key-123"}
        
        # Configurar respuesta del recomendador TF-IDF para búsqueda
        mock_client.mock_tfidf.search_products.return_value = SAMPLE_PRODUCTS[:2]
        
        # Ejecutar solicitud
        response = mock_client.get(
            "/v1/products/search/?q=camiseta",
            headers=headers
        )
        
        # Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert "total" in data
        assert "query" in data
        assert data["query"] == "camiseta"
        assert data["total"] == 2
        
        # Verificar que se llamó al método correcto
        mock_client.mock_tfidf.search_products.assert_called_once_with("camiseta", 10)
    
    def test_get_customers_flow(self, mock_client):
        """Verifica el flujo completo del endpoint de listado de clientes."""
        # Configurar API key para autenticación
        headers = {"X-API-Key": "test-api-key-123"}
        
        # Ejecutar solicitud
        response = mock_client.get(
            "/v1/customers/",
            headers=headers
        )
        
        # Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert "customers" in data
        assert "total" in data
        assert data["total"] == 2
        
        # Verificar que se llamó al método correcto
        mock_client.mock_shopify.get_customers.assert_called_once()
    
    def test_get_products_by_category_flow(self, mock_client):
        """Verifica el flujo completo del endpoint de productos por categoría."""
        # Configurar API key para autenticación
        headers = {"X-API-Key": "test-api-key-123"}
        
        # Configurar productos filtrados por categoría
        category_products = [p for p in SAMPLE_PRODUCTS if p.get("product_type") == "Ropa"]
        mock_client.mock_shopify.get_products.return_value = SAMPLE_PRODUCTS
        
        # Ejecutar solicitud
        response = mock_client.get(
            "/v1/products/category/Ropa",
            headers=headers
        )
        
        # Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Verificar que se llamó al método correcto
        mock_client.mock_shopify.get_products.assert_called_once()
    
    def test_authentication_required(self, mock_client):
        """Verifica que los endpoints protegidos requieren autenticación."""
        # Intentar acceder sin API key
        response = mock_client.get("/v1/recommendations/test_prod_1")
        
        # Verificar que se rechaza la solicitud
        assert response.status_code == 401 or response.status_code == 403
    
    def test_validation_errors(self, mock_client):
        """Verifica que los errores de validación se manejan correctamente."""
        # Configurar API key para autenticación
        headers = {"X-API-Key": "test-api-key-123"}
        
        # Probar con parámetro inválido (n negativo)
        response = mock_client.get(
            "/v1/recommendations/test_prod_1?n=-1",
            headers=headers
        )
        
        # Verificar que se devuelve error de validación
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
    
    def test_error_handling_when_recommender_fails(self, mock_client):
        """Verifica el manejo de errores cuando el recomendador falla."""
        # Configurar API key para autenticación
        headers = {"X-API-Key": "test-api-key-123"}
        
        # Configurar mock para simular fallo
        mock_client.mock_hybrid.get_recommendations.side_effect = Exception("Error simulado")
        
        # Ejecutar solicitud
        response = mock_client.get(
            "/v1/recommendations/test_prod_1",
            headers=headers
        )
        
        # Verificar que se maneja el error correctamente
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "Error simulado" in data["detail"]


class TestExclusionIntegrationFlow:
    """Pruebas para el flujo de exclusión de productos vistos."""
    
    @pytest.fixture
    def prepare_user_events(self):
        """Fixture para preparar eventos de usuario para pruebas de exclusión."""
        # Lista de IDs de productos vistos
        seen_product_ids = ["test_prod_1", "test_prod_2"]
        # Crear diccionario para simular la caché de eventos
        user_events_cache = {
            "test_user_1": [
                {"productId": id, "eventType": "detail-page-view"} 
                for id in seen_product_ids
            ]
        }
        return seen_product_ids, user_events_cache
    
    @pytest.mark.asyncio
    async def test_exclusion_flow(self, prepare_user_events):
        """
        Verifica el flujo completo de exclusión de productos vistos.
        
        Esta prueba simula el escenario donde un usuario solicita recomendaciones
        y el sistema excluye productos que ya ha visto.
        """
        seen_product_ids, user_events_cache = prepare_user_events
        
        # Crear mocks para los recomendadores
        mock_content = MagicMock()
        mock_content.get_recommendations.return_value = SAMPLE_PRODUCTS[:5]
        
        mock_retail = MagicMock()
        mock_retail.get_recommendations.return_value = SAMPLE_PRODUCTS[3:8]
        mock_retail.get_user_events = MagicMock(
            return_value=[
                {"productId": id, "eventType": "detail-page-view"} 
                for id in seen_product_ids
            ]
        )
        
        # Crear recomendador híbrido con exclusión
        from src.api.core.hybrid_recommender import HybridRecommenderWithExclusion
        recommender = HybridRecommenderWithExclusion(
            content_recommender=mock_content,
            retail_recommender=mock_retail,
            content_weight=0.5
        )
        
        # Solicitar recomendaciones
        recommendations = await recommender.get_recommendations(
            user_id="test_user_1",
            n_recommendations=5
        )
        
        # Verificar que se excluyeron los productos vistos
        result_ids = [p["id"] for p in recommendations]
        assert not any(pid in seen_product_ids for pid in result_ids), \
            "Las recomendaciones incluyen productos ya vistos"
        
        # Verificar que se llamó al método para obtener eventos de usuario
        mock_retail.get_user_events.assert_called_once_with("test_user_1")
