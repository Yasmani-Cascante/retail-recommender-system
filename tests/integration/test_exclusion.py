"""
Pruebas de integración para la funcionalidad de exclusión de productos vistos.

Este módulo contiene pruebas que verifican que el sistema excluye correctamente
productos ya vistos por el usuario al generar recomendaciones.
"""

import pytest
import os
import logging
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

# Asegurar que src está en el PYTHONPATH
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Importar test_logging para configurar logging
from tests.test_logging import setup_test_logging
from tests.data.sample_products import SAMPLE_PRODUCTS
from tests.data.sample_events import get_events_for_user

# Configurar logging
logger = setup_test_logging()

class TestExclusionIntegration:
    """Pruebas de integración para la funcionalidad de exclusión de productos vistos."""
    
    @pytest.fixture
    def seen_product_ids(self):
        """Fixture que proporciona una lista de IDs de productos vistos por el usuario."""
        return ["test_prod_1", "test_prod_2", "test_prod_3"]
    
    @pytest.fixture
    def mock_recommenders(self, seen_product_ids):
        """Fixture que proporciona mocks configurados para los recomendadores."""
        # Mock para recomendador de contenido
        content_recommender = AsyncMock()
        content_recommender.get_recommendations.return_value = SAMPLE_PRODUCTS[:5]
        
        # Mock para recomendador retail
        retail_recommender = AsyncMock()
        retail_recommender.get_recommendations.return_value = SAMPLE_PRODUCTS[3:8]
        
        # Configurar eventos de usuario para simular productos vistos
        events = [
            {"productId": id, "eventType": "detail-page-view"} 
            for id in seen_product_ids
        ]
        retail_recommender.get_user_events.return_value = events
        
        return content_recommender, retail_recommender
    
    @pytest.mark.asyncio
    async def test_hybrid_recommender_excludes_seen_products(self, mock_recommenders, seen_product_ids):
        """
        Verifica que el recomendador híbrido excluye correctamente los productos vistos.
        
        Esta prueba comprueba que:
        1. Se obtienen los eventos de usuario correctamente
        2. Los productos ya vistos se excluyen de las recomendaciones
        3. Se obtienen recomendaciones adicionales si es necesario
        """
        content_recommender, retail_recommender = mock_recommenders
        
        # Importar clase del recomendador
        from src.api.core.hybrid_recommender import HybridRecommenderWithExclusion
        
        # Crear instancia del recomendador híbrido con exclusión
        recommender = HybridRecommenderWithExclusion(
            content_recommender=content_recommender,
            retail_recommender=retail_recommender,
            content_weight=0.5
        )
        
        # Solicitar recomendaciones
        n_recommendations = 5
        recommendations = await recommender.get_recommendations(
            user_id="test_user_1",
            n_recommendations=n_recommendations
        )
        
        # Verificaciones
        assert len(recommendations) == n_recommendations, "No se devolvió el número correcto de recomendaciones"
        
        # Verificar que se excluyeron los productos vistos
        result_ids = [p["id"] for p in recommendations]
        assert not any(pid in seen_product_ids for pid in result_ids), \
            "Las recomendaciones incluyen productos ya vistos"
        
        # Verificar que se obtuvieron los eventos de usuario
        retail_recommender.get_user_events.assert_called_once_with("test_user_1")
    
    @pytest.mark.asyncio
    async def test_api_endpoint_excludes_seen_products(self, seen_product_ids):
        """
        Verifica que el endpoint de la API excluye correctamente productos vistos.
        
        Esta prueba simula el flujo completo desde la solicitud HTTP hasta la respuesta,
        comprobando que los productos ya vistos se excluyen correctamente.
        """
        # Patching para simular componentes
        with patch('src.api.factories.RecommenderFactory.create_hybrid_recommender') as mock_create_hybrid, \
             patch('src.api.startup_helper.StartupManager.is_healthy') as mock_is_healthy:
            
            # Configurar recomendador híbrido mock
            mock_hybrid = MagicMock()
            # Simular exclusión de productos vistos
            available_products = [p for p in SAMPLE_PRODUCTS if p["id"] not in seen_product_ids]
            mock_hybrid.get_recommendations.return_value = available_products[:5]
            mock_create_hybrid.return_value = mock_hybrid
            
            # Configurar verificación de salud
            mock_is_healthy.return_value = (True, "")
            
            # Importar la aplicación
            from src.api.main_unified import app
            client = TestClient(app)
            
            # Configurar API key para autenticación
            headers = {"X-API-Key": "test-api-key-123"}
            
            # Ejecutar solicitud
            response = client.get(
                f"/v1/recommendations/user/test_user_1?n=5",
                headers=headers
            )
            
            # Verificar respuesta
            assert response.status_code == 200
            data = response.json()
            assert "recommendations" in data
            assert len(data["recommendations"]) == 5
            
            # Verificar que los productos vistos no están en las recomendaciones
            result_ids = [p["id"] for p in data["recommendations"]]
            assert not any(pid in seen_product_ids for pid in result_ids), \
                "Las recomendaciones incluyen productos ya vistos"
    
    @pytest.mark.asyncio
    async def test_additional_recommendations_when_many_seen(self, mock_recommenders):
        """
        Verifica que se obtienen recomendaciones adicionales cuando la mayoría de los productos
        recomendados ya han sido vistos por el usuario.
        """
        content_recommender, retail_recommender = mock_recommenders
        
        # Simular que casi todos los productos han sido vistos
        # (8 de los 10 productos de muestra)
        seen_product_ids = [p["id"] for p in SAMPLE_PRODUCTS[:8]]
        events = [
            {"productId": id, "eventType": "detail-page-view"} 
            for id in seen_product_ids
        ]
        retail_recommender.get_user_events.return_value = events
        
        # Importar clase del recomendador
        from src.api.core.hybrid_recommender import HybridRecommenderWithExclusion
        
        # Crear instancia del recomendador híbrido con exclusión
        recommender = HybridRecommenderWithExclusion(
            content_recommender=content_recommender,
            retail_recommender=retail_recommender,
            content_weight=0.5
        )
        
        # Solicitar recomendaciones (más de las que quedarían después de exclusión)
        n_recommendations = 5
        recommendations = await recommender.get_recommendations(
            user_id="test_user_1",
            n_recommendations=n_recommendations
        )
        
        # Verificaciones
        assert len(recommendations) == n_recommendations, \
            f"No se devolvieron {n_recommendations} recomendaciones a pesar de haber muchos productos vistos"
        
        # Verificar que se excluyeron los productos vistos
        result_ids = [p["id"] for p in recommendations]
        assert not any(pid in seen_product_ids for pid in result_ids), \
            "Las recomendaciones incluyen productos ya vistos"
        
        # Verificar que se realizaron múltiples llamadas para obtener recomendaciones adicionales
        assert content_recommender.get_recommendations.call_count > 1 or \
               retail_recommender.get_recommendations.call_count > 1, \
               "No se realizaron llamadas adicionales para obtener más recomendaciones"
    
    @pytest.mark.asyncio
    async def test_new_user_without_history(self, mock_recommenders):
        """
        Verifica el comportamiento con usuarios nuevos sin historial de productos vistos.
        """
        content_recommender, retail_recommender = mock_recommenders
        
        # Simular usuario sin eventos previos
        retail_recommender.get_user_events.return_value = []
        
        # Importar clase del recomendador
        from src.api.core.hybrid_recommender import HybridRecommenderWithExclusion
        
        # Crear instancia del recomendador híbrido con exclusión
        recommender = HybridRecommenderWithExclusion(
            content_recommender=content_recommender,
            retail_recommender=retail_recommender,
            content_weight=0.5
        )
        
        # Solicitar recomendaciones
        n_recommendations = 5
        recommendations = await recommender.get_recommendations(
            user_id="new_user",
            n_recommendations=n_recommendations
        )
        
        # Verificaciones
        assert len(recommendations) == n_recommendations, "No se devolvió el número correcto de recomendaciones"
        
        # Verificar que se intentó obtener eventos del usuario
        retail_recommender.get_user_events.assert_called_once_with("new_user")
        
        # Verificar que se usaron recomendaciones estándar sin exclusión
        assert content_recommender.get_recommendations.call_count == 1 or \
               retail_recommender.get_recommendations.call_count == 1, \
               "Se realizaron llamadas innecesarias para obtener recomendaciones"
