"""
Pruebas unitarias para el recomendador híbrido.

Este módulo contiene pruebas unitarias para verificar el correcto funcionamiento
del recomendador híbrido, incluyendo la funcionalidad de exclusión de productos vistos.
"""

import pytest
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Asegurar que src está en el PYTHONPATH
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.api.core.hybrid_recommender import HybridRecommender, HybridRecommenderWithExclusion
from tests.data.sample_products import SAMPLE_PRODUCTS
from tests.data.sample_events import SAMPLE_USER_EVENTS, get_events_for_user

# Pruebas para el recomendador híbrido básico
class TestHybridRecommender:
    
    @pytest.fixture
    def content_recommender(self):
        """Fixture para un mock del recomendador basado en contenido."""
        recommender = AsyncMock()
        recommender.get_recommendations.return_value = SAMPLE_PRODUCTS[:3]
        recommender.loaded = True
        recommender.product_data = SAMPLE_PRODUCTS
        return recommender
        
    @pytest.fixture
    def retail_recommender(self):
        """Fixture para un mock del recomendador Retail API."""
        recommender = AsyncMock()
        recommender.get_recommendations.return_value = SAMPLE_PRODUCTS[3:6]
        recommender.record_user_event.return_value = {"status": "success"}
        return recommender
        
    @pytest.fixture
    def hybrid_recommender(self, content_recommender, retail_recommender):
        """Fixture para una instancia del recomendador híbrido básico."""
        return HybridRecommender(
            content_recommender=content_recommender,
            retail_recommender=retail_recommender,
            content_weight=0.5
        )
    
    @pytest.mark.asyncio
    async def test_basic_recommendations(self, hybrid_recommender):
        """Verifica que el recomendador híbrido combina resultados correctamente."""
        # Ejecutar método bajo prueba
        recommendations = await hybrid_recommender.get_recommendations(
            user_id="test_user_1",
            product_id="test_prod_1",
            n_recommendations=5
        )
        
        # Verificaciones
        assert recommendations is not None
        assert len(recommendations) == 5
        
        # Debe contener productos de ambas fuentes
        content_ids = [p["id"] for p in SAMPLE_PRODUCTS[:3]]
        retail_ids = [p["id"] for p in SAMPLE_PRODUCTS[3:6]]
        result_ids = [p["id"] for p in recommendations]
        
        # Debería haber al menos un producto de cada fuente
        assert any(pid in content_ids for pid in result_ids), "No hay productos del recomendador de contenido"
        assert any(pid in retail_ids for pid in result_ids), "No hay productos del recomendador retail"
    
    @pytest.mark.asyncio
    async def test_content_weight_full(self, hybrid_recommender, content_recommender, retail_recommender):
        """Verifica que cuando content_weight=1.0, solo se usan recomendaciones de contenido."""
        # Configurar peso de contenido al máximo
        hybrid_recommender.content_weight = 1.0
        
        # Ejecutar método bajo prueba
        recommendations = await hybrid_recommender.get_recommendations(
            user_id="test_user_1",
            product_id="test_prod_1",
            n_recommendations=3
        )
        
        # Verificar que solo se usan productos del recomendador de contenido
        result_ids = [p["id"] for p in recommendations]
        content_ids = [p["id"] for p in SAMPLE_PRODUCTS[:3]]
        
        assert all(pid in content_ids for pid in result_ids), "Se incluyeron productos que no son del recomendador de contenido"
        assert content_recommender.get_recommendations.called
        assert not retail_recommender.get_recommendations.called
    
    @pytest.mark.asyncio
    async def test_content_weight_zero(self, hybrid_recommender, content_recommender, retail_recommender):
        """Verifica que cuando content_weight=0.0, solo se usan recomendaciones de retail."""
        # Configurar peso de contenido al mínimo
        hybrid_recommender.content_weight = 0.0
        
        # Ejecutar método bajo prueba
        recommendations = await hybrid_recommender.get_recommendations(
            user_id="test_user_1",
            product_id="test_prod_1",
            n_recommendations=3
        )
        
        # Verificar que solo se usan productos del recomendador retail
        result_ids = [p["id"] for p in recommendations]
        retail_ids = [p["id"] for p in SAMPLE_PRODUCTS[3:6]]
        
        assert all(pid in retail_ids for pid in result_ids), "Se incluyeron productos que no son del recomendador retail"
        assert not content_recommender.get_recommendations.called
        assert retail_recommender.get_recommendations.called
    
    @pytest.mark.asyncio
    async def test_record_user_event(self, hybrid_recommender, retail_recommender):
        """Verifica que los eventos de usuario se registran correctamente."""
        # Ejecutar método bajo prueba
        result = await hybrid_recommender.record_user_event(
            user_id="test_user_1",
            event_type="detail-page-view",
            product_id="test_prod_1"
        )
        
        # Verificar
        assert result["status"] == "success"
        retail_recommender.record_user_event.assert_called_once_with(
            user_id="test_user_1",
            event_type="detail-page-view",
            product_id="test_prod_1",
            purchase_amount=None
        )
    
    @pytest.mark.asyncio
    async def test_fallback_when_retail_fails(self, hybrid_recommender, content_recommender, retail_recommender):
        """Verifica que se usa fallback cuando el recomendador retail falla."""
        # Configurar el recomendador retail para fallar
        retail_recommender.get_recommendations.side_effect = Exception("Error simulado")
        
        # Ejecutar método bajo prueba
        recommendations = await hybrid_recommender.get_recommendations(
            user_id="test_user_1",
            product_id="test_prod_1",
            n_recommendations=3
        )
        
        # Verificar que se usaron recomendaciones de contenido como fallback
        assert recommendations is not None
        assert len(recommendations) == 3
        result_ids = [p["id"] for p in recommendations]
        content_ids = [p["id"] for p in SAMPLE_PRODUCTS[:3]]
        assert all(pid in content_ids for pid in result_ids), "No se usaron las recomendaciones de contenido como fallback"


# Pruebas para el recomendador híbrido con exclusión de productos vistos
class TestHybridRecommenderWithExclusion:
    
    @pytest.fixture
    def content_recommender(self):
        """Fixture para un mock del recomendador basado en contenido."""
        recommender = AsyncMock()
        recommender.get_recommendations.return_value = SAMPLE_PRODUCTS[:5]
        recommender.loaded = True
        recommender.product_data = SAMPLE_PRODUCTS
        return recommender
        
    @pytest.fixture
    def retail_recommender(self):
        """Fixture para un mock del recomendador Retail API."""
        recommender = AsyncMock()
        recommender.get_recommendations.return_value = SAMPLE_PRODUCTS[3:8]
        recommender.record_user_event.return_value = {"status": "success"}
        
        # Configurar get_user_events para simular eventos vistos
        events = get_events_for_user("test_user_1")
        recommender.get_user_events.return_value = events
        
        return recommender
        
    @pytest.fixture
    def hybrid_recommender_with_exclusion(self, content_recommender, retail_recommender):
        """Fixture para una instancia del recomendador híbrido con exclusión."""
        return HybridRecommenderWithExclusion(
            content_recommender=content_recommender,
            retail_recommender=retail_recommender,
            content_weight=0.5
        )
    
    @pytest.mark.asyncio
    async def test_exclude_seen_products(self, hybrid_recommender_with_exclusion, retail_recommender):
        """Verifica que se excluyen productos ya vistos por el usuario."""
        # Configurar eventos para simular productos vistos
        seen_product_ids = {"test_prod_1", "test_prod_2"}
        events = [
            {"productId": id, "eventType": "detail-page-view"} 
            for id in seen_product_ids
        ]
        retail_recommender.get_user_events.return_value = events
        
        # Ejecutar método bajo prueba
        recommendations = await hybrid_recommender_with_exclusion.get_recommendations(
            user_id="test_user_1",
            n_recommendations=5
        )
        
        # Verificar que los productos vistos no están en las recomendaciones
        result_ids = [p["id"] for p in recommendations]
        assert not any(pid in seen_product_ids for pid in result_ids), "Las recomendaciones incluyen productos ya vistos"
        
        # Verificar que se llamó al método para obtener eventos de usuario
        retail_recommender.get_user_events.assert_called_once_with("test_user_1")
    
    @pytest.mark.asyncio
    async def test_get_user_interactions(self, hybrid_recommender_with_exclusion, retail_recommender):
        """Verifica que se obtienen correctamente las interacciones de usuario."""
        # Configurar eventos para simular productos vistos
        seen_product_ids = {"test_prod_1", "test_prod_2", "test_prod_3"}
        events = [
            {"productId": id, "eventType": "detail-page-view"} 
            for id in seen_product_ids
        ]
        retail_recommender.get_user_events.return_value = events
        
        # Ejecutar método bajo prueba
        interactions = await hybrid_recommender_with_exclusion.get_user_interactions("test_user_1")
        
        # Verificar que se devuelven los IDs correctos
        assert interactions == seen_product_ids
        retail_recommender.get_user_events.assert_called_once_with("test_user_1")
    
    @pytest.mark.asyncio
    async def test_additional_recommendations_when_too_many_excluded(self, hybrid_recommender_with_exclusion, content_recommender, retail_recommender):
        """
        Verifica que se obtienen recomendaciones adicionales cuando muchos productos 
        necesitan ser excluidos y no quedan suficientes.
        """
        # Configurar un gran número de productos vistos
        # (casi todos los que devuelven los recomendadores)
        seen_product_ids = set(p["id"] for p in SAMPLE_PRODUCTS[:7])
        events = [
            {"productId": id, "eventType": "detail-page-view"} 
            for id in seen_product_ids
        ]
        retail_recommender.get_user_events.return_value = events
        
        # Solo dejar unos pocos productos disponibles
        available_products = [p for p in SAMPLE_PRODUCTS if p["id"] not in seen_product_ids]
        
        # Configurar recomendadores para devolver productos limitados
        content_recommender.get_recommendations.return_value = SAMPLE_PRODUCTS[:5]  # Mayormente vistos
        retail_recommender.get_recommendations.return_value = SAMPLE_PRODUCTS[3:8]  # Incluye algunos no vistos
        
        # Configurar la función get_diverse_category_products para que devuelva productos adicionales
        # cuando se necesiten más después de excluir los ya vistos
        mock_additional_products = [
            {
                "id": f"additional_{i}",
                "title": f"Producto Adicional {i}",
                "description": "Descripción de prueba",
                "price": 99.99,
                "category": "Categoría de prueba",
                "score": 0.5,
                "recommendation_type": "diverse_fallback"
            } for i in range(5)
        ]
        
        with patch('src.recommenders.improved_fallback_exclude_seen.ImprovedFallbackStrategies.get_diverse_category_products', 
                   new=AsyncMock(return_value=mock_additional_products)):
            
            # Ejecutar método bajo prueba - Pedimos más de los que quedarían después de excluir
            n_recommendations = 5  # Más de los que quedarían después de exclusión
            recommendations = await hybrid_recommender_with_exclusion.get_recommendations(
                user_id="test_user_1",
                n_recommendations=n_recommendations
            )
            
            # Verificar
            assert len(recommendations) == n_recommendations, f"No se devolvieron {n_recommendations} recomendaciones"
            result_ids = [p["id"] for p in recommendations]
            assert not any(pid in seen_product_ids for pid in result_ids), "Las recomendaciones incluyen productos ya vistos"
    
    @pytest.mark.asyncio
    async def test_recommendations_with_no_user_events(self, hybrid_recommender_with_exclusion, retail_recommender):
        """Verifica que se manejan correctamente usuarios sin eventos previos."""
        # Configurar para que no haya eventos previos
        retail_recommender.get_user_events.return_value = []
        
        # Ejecutar método bajo prueba
        recommendations = await hybrid_recommender_with_exclusion.get_recommendations(
            user_id="new_user",
            n_recommendations=5
        )
        
        # Verificar que se devuelven recomendaciones normalmente
        assert recommendations is not None
        assert len(recommendations) == 5
        retail_recommender.get_user_events.assert_called_once_with("new_user")
