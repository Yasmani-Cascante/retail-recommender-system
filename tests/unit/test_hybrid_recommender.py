"""
Pruebas unitarias para el recomendador híbrido.

Este módulo contiene pruebas para verificar el funcionamiento del recomendador híbrido,
incluyendo la exclusión de productos vistos y el mecanismo de fallback.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from src.api.core.hybrid_recommender import HybridRecommender, HybridRecommenderWithExclusion

@pytest.fixture
def sample_products():
    """Fixture para generar productos de ejemplo."""
    return [
        {"id": "prod1", "title": "Producto 1", "category": "Categoría A", "score": 0.9},
        {"id": "prod2", "title": "Producto 2", "category": "Categoría B", "score": 0.8},
        {"id": "prod3", "title": "Producto 3", "category": "Categoría A", "score": 0.7},
        {"id": "prod4", "title": "Producto 4", "category": "Categoría C", "score": 0.6},
        {"id": "prod5", "title": "Producto 5", "category": "Categoría B", "score": 0.5},
    ]

@pytest.fixture
def mock_content_recommender(sample_products):
    """Fixture para simular un recomendador basado en contenido."""
    recommender = AsyncMock()
    
    # Configurar el método get_recommendations para devolver productos de ejemplo
    async def mock_get_recommendations(product_id, n_recommendations=5):
        # Devolver productos diferentes según el ID
        if product_id == "prod1":
            return sample_products[1:4]  # prod2, prod3, prod4
        else:
            return sample_products[0:3]  # prod1, prod2, prod3
            
    recommender.get_recommendations.side_effect = mock_get_recommendations
    recommender.loaded = True
    recommender.product_data = sample_products
    
    return recommender

@pytest.fixture
def mock_retail_recommender(sample_products):
    """Fixture para simular un recomendador basado en Retail API."""
    recommender = AsyncMock()
    
    # Configurar el método get_recommendations para devolver productos de ejemplo
    async def mock_get_recommendations(user_id, product_id=None, n_recommendations=5):
        # Devolver productos diferentes según el ID
        if product_id == "prod1":
            return sample_products[2:5]  # prod3, prod4, prod5
        else:
            return sample_products[1:4]  # prod2, prod3, prod4
            
    recommender.get_recommendations.side_effect = mock_get_recommendations
    
    # Configurar el método get_user_events para devolver eventos de ejemplo
    async def mock_get_user_events(user_id):
        if user_id == "user1":
            return [
                {"user_id": "user1", "product_id": "prod1", "event_type": "detail-page-view"},
                {"user_id": "user1", "product_id": "prod3", "event_type": "add-to-cart"}
            ]
        else:
            return []
            
    recommender.get_user_events.side_effect = mock_get_user_events
    
    # Configurar el método record_user_event
    recommender.record_user_event.return_value = {"status": "success"}
    
    return recommender

@pytest.mark.asyncio
async def test_basic_hybrid_recommender(mock_content_recommender, mock_retail_recommender, sample_products):
    """Prueba el funcionamiento básico del recomendador híbrido."""
    # Crear instancia del recomendador híbrido
    hybrid = HybridRecommender(
        content_recommender=mock_content_recommender,
        retail_recommender=mock_retail_recommender,
        content_weight=0.6
    )
    
    # Obtener recomendaciones para un producto
    recommendations = await hybrid.get_recommendations(
        user_id="anonymous",
        product_id="prod1",
        n_recommendations=3
    )
    
    # Verificar que se llamaron los métodos correctos
    mock_content_recommender.get_recommendations.assert_called_with("prod1", 3)
    mock_retail_recommender.get_recommendations.assert_called_with(
        user_id="anonymous",
        product_id="prod1",
        n_recommendations=3
    )
    
    # Verificar que se devolvieron recomendaciones
    assert len(recommendations) == 3
    # Verificar que cada recomendación tiene un ID y un score
    for rec in recommendations:
        assert "id" in rec
        assert "final_score" in rec

@pytest.mark.asyncio
async def test_combine_recommendations(mock_content_recommender, mock_retail_recommender, sample_products):
    """Prueba el método de combinación de recomendaciones."""
    # Crear instancia del recomendador híbrido
    hybrid = HybridRecommender(
        content_recommender=mock_content_recommender,
        retail_recommender=mock_retail_recommender,
        content_weight=0.7
    )
    
    # Preparar datos de prueba
    content_recs = [
        {"id": "prod1", "title": "Producto 1", "similarity_score": 0.9},
        {"id": "prod2", "title": "Producto 2", "similarity_score": 0.8}
    ]
    
    retail_recs = [
        {"id": "prod2", "title": "Producto 2", "score": 0.7},
        {"id": "prod3", "title": "Producto 3", "score": 0.6}
    ]
    
    # Llamar al método de combinación
    combined = await hybrid._combine_recommendations(
        content_recs,
        retail_recs,
        2
    )
    
    # Verificar el resultado
    assert len(combined) == 2
    
    # Verificar que prod2 tiene score combinado (aparece en ambas fuentes)
    prod2 = next((r for r in combined if r["id"] == "prod2"), None)
    assert prod2 is not None
    assert "final_score" in prod2
    # 0.7 * 0.8 (content) + 0.3 * 0.7 (retail) = 0.56 + 0.21 = 0.77
    assert pytest.approx(prod2["final_score"], 0.01) == 0.77

@pytest.mark.asyncio
async def test_fallback_recommendations(mock_content_recommender, mock_retail_recommender):
    """Prueba el mecanismo de fallback cuando no hay recomendaciones disponibles."""
    # Configurar el recomendador Retail API para devolver lista vacía
    mock_retail_recommender.get_recommendations.return_value = []
    
    # Crear instancia del recomendador híbrido
    hybrid = HybridRecommender(
        content_recommender=mock_content_recommender,
        retail_recommender=mock_retail_recommender,
        content_weight=0.5
    )
    
    # Intentar obtener recomendaciones para un usuario (sin product_id)
    with patch.object(hybrid, '_get_fallback_recommendations') as mock_fallback:
        mock_fallback.return_value = [{"id": "fallback1", "title": "Fallback 1"}]
        
        recommendations = await hybrid.get_recommendations(
            user_id="user1",
            n_recommendations=2
        )
        
        # Verificar que se llamó al mecanismo de fallback
        mock_fallback.assert_called_once_with("user1", 2)
        
        # Verificar que se devolvieron recomendaciones de fallback
        assert len(recommendations) == 1
        assert recommendations[0]["id"] == "fallback1"

@pytest.mark.asyncio
async def test_hybrid_recommender_with_exclusion(mock_content_recommender, mock_retail_recommender, sample_products):
    """Prueba el recomendador híbrido con exclusión de productos vistos."""
    # Crear instancia del recomendador con exclusión
    hybrid = HybridRecommenderWithExclusion(
        content_recommender=mock_content_recommender,
        retail_recommender=mock_retail_recommender,
        content_weight=0.5
    )
    
    # Mockear get_user_interactions para devolver productos vistos
    with patch.object(hybrid, 'get_user_interactions') as mock_interactions:
        mock_interactions.return_value = {"prod1", "prod3"}  # Productos a excluir
        
        # Obtener recomendaciones para un producto
        recommendations = await hybrid.get_recommendations(
            user_id="user1",
            product_id="prod2",
            n_recommendations=3
        )
        
        # Verificar que se llamó al método para obtener interacciones
        mock_interactions.assert_called_once_with("user1")
        
        # Verificar que se excluyeron los productos vistos
        product_ids = {rec["id"] for rec in recommendations}
        assert "prod1" not in product_ids
        assert "prod3" not in product_ids

@pytest.mark.asyncio
async def test_get_user_interactions(mock_content_recommender, mock_retail_recommender):
    """Prueba la obtención de interacciones de usuario."""
    # Crear instancia del recomendador con exclusión
    hybrid = HybridRecommenderWithExclusion(
        content_recommender=mock_content_recommender,
        retail_recommender=mock_retail_recommender,
        content_weight=0.5
    )
    
    # Obtener interacciones para un usuario con eventos
    interactions = await hybrid.get_user_interactions("user1")
    
    # Verificar que se llamó al método get_user_events
    mock_retail_recommender.get_user_events.assert_called_once_with("user1")
    
    # Verificar que se devolvieron los productos correctos
    assert "prod1" in interactions
    assert "prod3" in interactions
    assert len(interactions) == 2
    
    # Probar con un usuario sin eventos
    mock_retail_recommender.get_user_events.reset_mock()
    
    interactions = await hybrid.get_user_interactions("user2")
    
    # Verificar que se llamó al método get_user_events
    mock_retail_recommender.get_user_events.assert_called_once_with("user2")
    
    # Verificar que se devolvió un conjunto vacío
    assert len(interactions) == 0

@pytest.mark.asyncio
async def test_record_user_event(mock_content_recommender, mock_retail_recommender):
    """Prueba el registro de eventos de usuario."""
    # Crear instancia del recomendador híbrido
    hybrid = HybridRecommender(
        content_recommender=mock_content_recommender,
        retail_recommender=mock_retail_recommender,
        content_weight=0.5
    )
    
    # Registrar un evento
    result = await hybrid.record_user_event(
        user_id="user1",
        event_type="add-to-cart",
        product_id="prod1",
        purchase_amount=None
    )
    
    # Verificar que se llamó al método correcto
    mock_retail_recommender.record_user_event.assert_called_once_with(
        user_id="user1",
        event_type="add-to-cart",
        product_id="prod1",
        purchase_amount=None
    )
    
    # Verificar el resultado
    assert result["status"] == "success"
