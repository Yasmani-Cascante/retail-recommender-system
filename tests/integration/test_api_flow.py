"""
Pruebas de integración corregidas para los flujos principales de la API.

Este módulo contiene pruebas que verifican el funcionamiento end-to-end
de los principales flujos de trabajo de la API, usando mocks robustos
y datos de prueba consistentes.
"""

import pytest
import logging
from unittest.mock import patch, MagicMock

# Configurar logging para pruebas
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestAPIIntegrationFlows:
    """Pruebas de integración para los flujos principales de la API."""
    
    def test_health_check_flow(self, test_client):
        """Verifica el flujo completo del endpoint health check."""
        logger.info("Ejecutando test_health_check_flow")
        
        # Ejecutar solicitud
        response = test_client.get("/health")
        
        # Verificar respuesta
        assert response.status_code == 200, f"Error en health check: {response.content}"
        data = response.json()
        
        # Verificar estructura de respuesta
        assert "status" in data, "Falta campo 'status' en respuesta"
        assert "components" in data, "Falta campo 'components' en respuesta"
        assert "uptime_seconds" in data, "Falta campo 'uptime_seconds' en respuesta"
        
        # Verificar estado operacional
        assert data["status"] == "operational", f"Estado esperado 'operational', obtenido '{data['status']}'"
        assert "recommender" in data["components"], "Falta componente 'recommender'"
        assert data["components"]["recommender"]["status"] == "operational"
        
        logger.info("✅ test_health_check_flow completado exitosamente")
    
    def test_get_recommendations_flow(self, test_client):
        """Verifica el flujo completo del endpoint de recomendaciones."""
        logger.info("Ejecutando test_get_recommendations_flow")
        
        # Ejecutar solicitud para un producto que existe en SAMPLE_PRODUCTS
        response = test_client.get("/v1/recommendations/test_prod_1?n=5&content_weight=0.6")
        
        # Verificar respuesta
        assert response.status_code == 200, f"Error en la respuesta: {response.content.decode()}"
        data = response.json()
        
        # Verificar estructura de respuesta
        assert "recommendations" in data, "Falta campo 'recommendations'"
        assert "metadata" in data, "Falta campo 'metadata'"
        assert "product" in data, "Falta campo 'product'"
        
        # Verificar contenido
        assert len(data["recommendations"]) == 5, f"Se esperaban 5 recomendaciones, se obtuvieron {len(data['recommendations'])}"
        assert data["metadata"]["content_weight"] == 0.6, "content_weight no se aplicó correctamente"
        assert data["product"]["id"] == "test_prod_1", "ID de producto no coincide"
        
        # Verificar que las recomendaciones tienen la estructura esperada
        for rec in data["recommendations"]:
            assert "id" in rec, "Recomendación sin ID"
            assert "title" in rec, "Recomendación sin título"
        
        logger.info("✅ test_get_recommendations_flow completado exitosamente")
    
    def test_get_products_flow(self, test_client):
        """Verifica el flujo completo del endpoint de listado de productos."""
        logger.info("Ejecutando test_get_products_flow")
        
        # Ejecutar solicitud con paginación específica
        response = test_client.get("/v1/products/?page=1&page_size=10")
        
        # Verificar respuesta
        assert response.status_code == 200, f"Error en la respuesta: {response.content.decode()}"
        data = response.json()
        
        # Verificar estructura de respuesta
        assert "products" in data, "Falta campo 'products'"
        assert "total" in data, "Falta campo 'total'"
        assert "page" in data, "Falta campo 'page'"
        assert "page_size" in data, "Falta campo 'page_size'"
        assert "total_pages" in data, "Falta campo 'total_pages'"
        
        # Verificar contenido - debe devolver máximo 10 productos como se solicitó
        assert len(data["products"]) <= 10, f"Se esperaban máximo 10 productos, se obtuvieron {len(data['products'])}"
        assert data["page"] == 1, "Número de página no coincide"
        assert data["page_size"] == 10, "Tamaño de página no coincide"
        
        # El total debe ser el número de productos en SAMPLE_PRODUCTS
        from tests.data.sample_products import SAMPLE_PRODUCTS
        assert data["total"] == len(SAMPLE_PRODUCTS), f"Total esperado {len(SAMPLE_PRODUCTS)}, obtenido {data['total']}"
        
        logger.info("✅ test_get_products_flow completado exitosamente")
    
    def test_search_products_flow(self, test_client):
        """Verifica el flujo completo del endpoint de búsqueda de productos."""
        logger.info("Ejecutando test_search_products_flow")
        
        # Ejecutar solicitud de búsqueda
        response = test_client.get("/v1/products/search/?q=camiseta")
        
        # Verificar respuesta
        assert response.status_code == 200, f"Error en la respuesta: {response.content.decode()}"
        data = response.json()
        
        # Verificar estructura de respuesta
        assert "products" in data, "Falta campo 'products'"
        assert "total" in data, "Falta campo 'total'"
        assert "query" in data, "Falta campo 'query'"
        
        # Verificar que la query se registró correctamente
        assert data["query"] == "camiseta", "Query no coincide"
        
        # Debe encontrar al menos el producto "Camiseta básica de algodón" de SAMPLE_PRODUCTS
        assert data["total"] >= 1, f"Se esperaba al menos 1 resultado, se obtuvieron {data['total']}"
        assert len(data["products"]) >= 1, "No se encontraron productos que coincidan con la búsqueda"
        
        # Verificar que los productos encontrados contienen la palabra buscada
        for product in data["products"]:
            assert "camiseta" in product["title"].lower(), f"Producto '{product['title']}' no contiene 'camiseta'"
        
        logger.info("✅ test_search_products_flow completado exitosamente")
    
    def test_get_products_by_category_flow(self, test_client):
        """Verifica el flujo completo del endpoint de productos por categoría."""
        logger.info("Ejecutando test_get_products_by_category_flow")
        
        # Ejecutar solicitud para una categoría que existe en SAMPLE_PRODUCTS
        response = test_client.get("/v1/products/category/Ropa")
        
        # Verificar respuesta
        assert response.status_code == 200, f"Error en la respuesta: {response.content.decode()}"
        data = response.json()
        
        # Verificar que es una lista
        assert isinstance(data, list), "La respuesta debe ser una lista de productos"
        
        # Debe encontrar productos de la categoría "Ropa" en SAMPLE_PRODUCTS
        assert len(data) > 0, "No se encontraron productos en la categoría 'Ropa'"
        
        # Verificar que todos los productos pertenecen a la categoría solicitada
        for product in data:
            assert product.get("product_type", "").lower() == "ropa", f"Producto {product.get('title', '')} no pertenece a categoría 'Ropa'"
        
        logger.info("✅ test_get_products_by_category_flow completado exitosamente")
    
    def test_authentication_required(self, test_client_no_auth):
        """Verifica que los endpoints protegidos requieren autenticación."""
        logger.info("Ejecutando test_authentication_required")
        
        # Imprimir estado del cliente para debugging
        logger.info(f"Cliente sin autenticación headers: {test_client_no_auth.headers}")
        
        # Asegurar que no hay API key en los headers
        if "X-API-Key" in test_client_no_auth.headers:
            logger.warning("X-API-Key encontrada en headers, eliminando...")
            del test_client_no_auth.headers["X-API-Key"]
        
        # Intentar acceder sin API key válida
        response = test_client_no_auth.get("/v1/recommendations/test_prod_1")
        
        # Verificar la respuesta para debug
        logger.info(f"Respuesta de autenticación: status_code={response.status_code}, body={response.content}")
        
        # Verificar que se rechaza la solicitud
        assert response.status_code == 403, f"Se esperaba 403 pero se obtuvo {response.status_code}"
        
        # Verificar mensaje de error
        data = response.json()
        assert "detail" in data, "Falta campo 'detail' en respuesta de error"
        assert "API Key" in str(data["detail"]) or "válida" in str(data["detail"]) or "autenticación" in str(data["detail"]).lower(), "Mensaje de error no menciona API Key o autenticación"
        
        logger.info("✅ test_authentication_required completado exitosamente")
    
    def test_validation_errors(self, test_client):
        """Verifica que los errores de validación se manejan correctamente."""
        logger.info("Ejecutando test_validation_errors")
        
        # Probar con parámetro inválido (n negativo)
        response = test_client.get("/v1/recommendations/test_prod_1?n=-1")
        
        # Verificar que se devuelve error de validación
        assert response.status_code == 422, f"Se esperaba 422 pero se obtuvo {response.status_code}"
        data = response.json()
        assert "detail" in data, "Falta campo 'detail' en error de validación"
        
        logger.info("✅ test_validation_errors completado exitosamente")
    
    def test_error_handling_when_recommender_fails(self, test_client):
        """Verifica el manejo de errores cuando el recomendador falla."""
        logger.info("Ejecutando test_error_handling_when_recommender_fails")
        
        # Para este test, necesitamos patchear el método directamente en el endpoint
        # Ya que el mock está configurado globalmente
        
        with patch('src.api.main_unified.hybrid_recommender') as mock_hybrid:
            # Configurar el mock para que falle
            mock_hybrid.get_recommendations.side_effect = Exception("Error simulado")
            
            # Ejecutar solicitud
            response = test_client.get("/v1/recommendations/test_prod_1")
            
            # Verificar que se maneja el error correctamente
            assert response.status_code == 500, f"Se esperaba 500 pero se obtuvo {response.status_code}"
            data = response.json()
            assert "detail" in data, "Falta campo 'detail' en error"
            assert "Error simulado" in str(data["detail"]), f"Mensaje de error no contiene 'Error simulado': {data['detail']}"
        
        logger.info("✅ test_error_handling_when_recommender_fails completado exitosamente")
    
    def test_product_not_found_error(self, test_client):
        """Verifica el manejo de errores cuando no se encuentra un producto."""
        logger.info("Ejecutando test_product_not_found_error")
        
        # Solicitar recomendaciones para un producto que no existe
        response = test_client.get("/v1/recommendations/producto_inexistente")
        
        # Verificar que se devuelve error 404
        assert response.status_code == 404, f"Se esperaba 404 pero se obtuvo {response.status_code}"
        data = response.json()
        assert "detail" in data, "Falta campo 'detail' en error 404"
        assert "not found" in str(data["detail"]).lower(), "Mensaje de error no indica que no se encontró el producto"
        
        logger.info("✅ test_product_not_found_error completado exitosamente")

class TestExclusionFeature:
    """Pruebas específicas para la funcionalidad de exclusión de productos vistos."""
