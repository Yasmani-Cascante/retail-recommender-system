# tests/mcp/conftest.py
"""
Configuración de pytest para tests MCP

Este archivo configura fixtures compartidas y configuración para todos los tests MCP.
"""

import pytest
import asyncio
import tempfile
import shutil
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

# Fixtures compartidas para tests MCP

@pytest.fixture
def temp_dir():
    """Directorio temporal para tests"""
    temp_path = tempfile.mkdtemp(prefix="mcp_test_")
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)

@pytest.fixture
def mock_redis():
    """Mock de Redis client para tests"""
    mock = AsyncMock()
    mock.connected = True
    mock.set.return_value = True
    mock.get.return_value = None
    mock.lpush.return_value = 1
    mock.lrange.return_value = []
    mock.exists.return_value = 0
    return mock

@pytest.fixture
def mock_base_recommender():
    """Mock del base recommender"""
    mock = AsyncMock()
    mock.get_recommendations.return_value = [
        {
            "id": "test_product_1",
            "title": "Test Product",
            "final_score": 0.8,
            "category": "Test"
        }
    ]
    mock.record_user_event.return_value = {
        "status": "success",
        "user_id": "test_user",
        "event_type": "detail-page-view"
    }
    return mock

@pytest.fixture
def sample_products():
    """Productos de muestra para tests"""
    return [
        {
            "id": "test_product_1",
            "title": "Camiseta Test Azul",
            "body_html": "Camiseta de prueba para testing",
            "product_type": "Ropa",
            "category": "Ropa",
            "variants": [{"price": "25.99"}],
            "tags": ["test", "camiseta", "azul"]
        },
        {
            "id": "test_product_2",
            "title": "Pantalón Test Negro",
            "body_html": "Pantalón de prueba para testing",
            "product_type": "Ropa", 
            "category": "Ropa",
            "variants": [{"price": "45.99"}],
            "tags": ["test", "pantalón", "negro"]
        }
    ]

@pytest.fixture
def mock_mcp_responses():
    """Respuestas MCP de muestra"""
    return {
        "intent_responses": {
            "busco camiseta": {
                "type": "search",
                "confidence": 0.8,
                "query": "busco camiseta",
                "source": "mcp_bridge"
            },
            "quiero comprar": {
                "type": "purchase_intent",
                "confidence": 0.9,
                "query": "quiero comprar",
                "source": "mcp_bridge"
            }
        }
    }

# Configuración de asyncio para tests
@pytest.fixture(scope="session")
def event_loop():
    """Event loop para tests asincrónicos"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
