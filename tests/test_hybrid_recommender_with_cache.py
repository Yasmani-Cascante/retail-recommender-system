
"""
Pruebas de integración del recomendador híbrido con el sistema de caché.

Este módulo proporciona pruebas para verificar la integración correcta
entre el recomendador híbrido y el sistema de caché de productos.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch
import json
import logging

# Configurar logging para las pruebas
logging.basicConfig(level=logging.INFO)

@pytest.fixture
def mock_tfidf_recommender():
    """Crea un mock del recomendador TF-IDF."""
    recommender = MagicMock()
    recommender.get_recommendations = MagicMock(return_value=[
        {"id": "123", "title": "Product 1", "similarity_score": 0.9},
        {"id": "456", "title": "Product 2", "similarity_score": 0.8},
    ])
    recommender.loaded = True
    return recommender

@pytest.fixture
def mock_retail_recommender():
    """Crea un mock del recomendador Retail API."""
    recommender = MagicMock()
    recommender.get_recommendations = MagicMock(return_value=[
        {"id": "123", "title": "Product 1", "score": 0.8},
        {"id": "789", "title": "Product 3", "score": 0.7},
    ])
    return recommender

@pytest.fixture
def mock_product_cache():
    """Crea un mock del sistema de caché de productos."""
    cache = MagicMock()
    
    # Configurar el método get_product
    async def mock_get_product(product_id):
        products = {
            "123": {
                "id": "123",
                "title": "Enriched Product 1",
                "body_html": "Description of product 1",
                "product_type": "Category A",
                "variants": [{"price": "10.99"}],
                "images": [{"src": "http://example.com/image1.jpg"}]
            },
            "456": {
                "id": "456",
                "title": "Enriched Product 2",
                "body_html": "Description of product 2",
                "product_type": "Category B",
                "variants": [{"price": "20.99"}],
                "images": [{"src": "http://example.com/image2.jpg"}]
            },
            "789": {
                "id": "789",
                "title": "Enriched Product 3",
                "body_html": "Description of product 3",
                "product_type": "Category A",
                "variants": [{"price": "15.99"}],
                "images": [{"src": "http://example.com/image3.jpg"}]
            }
        }
        return products.get(product_id)
    
    cache.get_product = mock_get_product
    cache.preload_products = MagicMock(return_value=None)
    cache.get_stats = MagicMock(return_value={"hit_ratio": 0.75})
    
    return cache

@pytest.mark.asyncio
async def test_hybrid_recommender_with_cache():
    """Prueba el recomendador híbrido con sistema de caché."""
    from src.recommenders.hybrid import HybridRecommender
    
    # Crear mocks
    tfidf_recommender = MagicMock()
    retail_recommender = MagicMock()
    product_cache = MagicMock()
    
    # Configurar comportamiento del recomendador TF-IDF
    async def mock_tfidf_recommendations(product_id, n):
        return [
            {"id": "123", "title": "Product 1", "similarity_score": 0.9, "source": "content"},
            {"id": "456", "title": "Product 2", "similarity_score": 0.8, "source": "content"}
        ]
    
    tfidf_recommender.get_recommendations = mock_tfidf_recommendations
    
    # Configurar comportamiento del recomendador Retail API
    async def mock_retail_recommendations(user_id, product_id=None, n_recommendations=5):
        return [
            {"id": "123", "title": "Product 1", "score": 0.8, "source": "retail_api"},
            {"id": "789", "title": "Product 3", "score": 0.7, "source": "retail_api"}
        ]
    
    retail_recommender.get_recommendations = mock_retail_recommendations
    
    # Configurar comportamiento de la caché de productos
    products_db = {
        "123": {
            "id": "123",
            "title": "Enriched Product 1",
            "body_html": "Description of product 1",
            "product_type": "Category A",
            "variants": [{"price": "10.99"}],
            "images": [{"src": "http://example.com/image1.jpg"}]
        },
        "456": {
            "id": "456",
            "title": "Enriched Product 2",
            "body_html": "Description of product 2",
            "product_type": "Category B",
            "variants": [{"price": "20.99"}],
            "images": [{"src": "http://example.com/image2.jpg"}]
        },
        "789": {
            "id": "789",
            "title": "Enriched Product 3",
            "body_html": "Description of product 3",
            "product_type": "Category A",
            "variants": [{"price": "15.99"}],
            "images": [{"src": "http://example.com/image3.jpg"}]
        }
    }
    
    async def mock_get_product(product_id):
        return products_db.get(product_id)
    
    product_cache.get_product = mock_get_product
    product_cache.preload_products = MagicMock(return_value=None)
    product_cache.get_stats = MagicMock(return_value={"hit_ratio": 0.75})
    
    # Crear recomendador híbrido con caché
    recommender = HybridRecommender(
        content_recommender=tfidf_recommender,
        retail_recommender=retail_recommender,
        content_weight=0.6,
        product_cache=product_cache
    )
    
    # Obtener recomendaciones
    recommendations = await recommender.get_recommendations(
        user_id="test_user",
        product_id="123",
        n_recommendations=3
    )
    
    # Verificaciones
    assert len(recommendations) == 3
    
    # Verificar que los productos fueron enriquecidos
    for rec in recommendations:
        assert "title" in rec
        assert "description" in rec
        assert "price" in rec
        assert "category" in rec
        # Verificar que el título está enriquecido
        assert rec["title"].startswith("Enriched")
    
    # Verificar que se precargaron productos
    product_cache.preload_products.assert_called_once()
    
    # Verificar el orden de productos (basado en score combinado)
    assert recommendations[0]["id"] == "123"  # Debe ser el primero por tener mayor score combinado

@pytest.mark.asyncio
async def test_enrich_recommendations():
    """Prueba el método _enrich_recommendations del recomendador híbrido."""
    from src.recommenders.hybrid import HybridRecommender
    
    # Crear mocks
    tfidf_recommender = MagicMock()
    retail_recommender = MagicMock()
    product_cache = MagicMock()
    
    # Configurar comportamiento de la caché de productos
    products_db = {
        "123": {
            "id": "123",
            "title": "Enriched Product 1",
            "body_html": "Description of product 1",
            "product_type": "Category A",
            "variants": [{"price": "10.99"}],
            "images": [{"src": "http://example.com/image1.jpg"}]
        },
        "456": {
            "id": "456",
            "title": "Enriched Product 2",
            "body_html": "Description of product 2",
            "product_type": "Category B",
            "variants": [{"price": "20.99"}],
            "images": [{"src": "http://example.com/image2.jpg"}]
        }
    }
    
    async def mock_get_product(product_id):
        return products_db.get(product_id)
    
    product_cache.get_product = mock_get_product
    product_cache.preload_products = MagicMock(return_value=None)
    product_cache.get_stats = MagicMock(return_value={"hit_ratio": 0.75})
    
    # Crear recomendador híbrido con caché
    recommender = HybridRecommender(
        content_recommender=tfidf_recommender,
        retail_recommender=retail_recommender,
        content_weight=0.6,
        product_cache=product_cache
    )
    
    # Recomendaciones originales
    original_recs = [
        {"id": "123", "score": 0.9, "source": "retail_api"},
        {"id": "456", "score": 0.8, "source": "retail_api"},
        {"id": "999", "score": 0.7, "source": "retail_api"}  # Este no está en la caché
    ]
    
    # Enriquecer recomendaciones
    enriched_recs = await recommender._enrich_recommendations(original_recs, "test_user")
    
    # Verificaciones
    assert len(enriched_recs) == 3
    
    # Verificar que los productos existentes en la caché fueron enriquecidos
    assert enriched_recs[0]["title"] == "Enriched Product 1"
    assert enriched_recs[0]["description"] == "Description of product 1"
    assert float(enriched_recs[0]["price"]) == 10.99
    assert enriched_recs[0]["category"] == "Category A"
    assert enriched_recs[0]["image_url"] == "http://example.com/image1.jpg"
    
    assert enriched_recs[1]["title"] == "Enriched Product 2"
    
    # Verificar que el producto que no está en la caché tiene la marca de datos incompletos
    assert "_incomplete_data" in enriched_recs[2]
    
    # Verificar que se precargaron productos
    product_cache.preload_products.assert_called_once()

@pytest.mark.asyncio
async def test_hybrid_recommender_without_cache():
    """Prueba el recomendador híbrido sin sistema de caché."""
    from src.recommenders.hybrid import HybridRecommender
    
    # Crear mocks
    tfidf_recommender = MagicMock()
    retail_recommender = MagicMock()
    
    # Configurar comportamiento del recomendador TF-IDF
    async def mock_tfidf_recommendations(product_id, n):
        return [
            {"id": "123", "title": "Product 1", "similarity_score": 0.9, "source": "content"},
            {"id": "456", "title": "Product 2", "similarity_score": 0.8, "source": "content"}
        ]
    
    tfidf_recommender.get_recommendations = mock_tfidf_recommendations
    
    # Configurar comportamiento del recomendador Retail API
    async def mock_retail_recommendations(user_id, product_id=None, n_recommendations=5):
        return [
            {"id": "123", "title": "Product 1", "score": 0.8, "source": "retail_api"},
            {"id": "789", "title": "Product 3", "score": 0.7, "source": "retail_api"}
        ]
    
    retail_recommender.get_recommendations = mock_retail_recommendations
    
    # Crear recomendador híbrido sin caché
    recommender = HybridRecommender(
        content_recommender=tfidf_recommender,
        retail_recommender=retail_recommender,
        content_weight=0.6
    )
    
    # Obtener recomendaciones
    recommendations = await recommender.get_recommendations(
        user_id="test_user",
        product_id="123",
        n_recommendations=3
    )
    
    # Verificaciones
    assert len(recommendations) == 3
    
    # Verificar que los productos no fueron enriquecidos (mantienen información original)
    assert recommendations[0]["title"] == "Product 1"  # No "Enriched Product 1"
    assert "description" not in recommendations[0]
    
    # Verificar el orden de productos (basado en score combinado)
    assert recommendations[0]["id"] == "123"  # Debe ser el primero por tener mayor score combinado

if __name__ == "__main__":
    # Para ejecución manual con pytest
    pytest.main(["-xvs", __file__])
