
"""
Pruebas unitarias para el sistema de caché de productos.

Este módulo proporciona pruebas para la clase ProductCache,
verificando su funcionamiento con Redis y diferentes fuentes de datos.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import json
import logging

from src.api.core.product_cache import ProductCache

# Configurar logging para las pruebas
logging.basicConfig(level=logging.INFO)

@pytest.fixture
def mock_redis_client():
    """Crea un mock del cliente Redis."""
    redis = MagicMock()
    redis.connected = True
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.health_check = AsyncMock(return_value={"connected": True, "stats": {}})
    return redis

@pytest.fixture
def mock_shopify_client():
    """Crea un mock del cliente Shopify."""
    client = MagicMock()
    client.get_product = MagicMock(return_value={"id": "123", "title": "Test Product"})
    return client

@pytest.fixture
def mock_local_catalog():
    """Crea un mock del catálogo local."""
    catalog = MagicMock()
    catalog.product_data = [
        {"id": "123", "title": "Test Product", "product_type": "Test"}
    ]
    catalog.get_product_by_id = MagicMock(return_value={"id": "123", "title": "Test Product"})
    return catalog

@pytest.fixture
def product_cache(mock_redis_client, mock_local_catalog, mock_shopify_client):
    """Crea instancia de ProductCache con mocks."""
    cache = ProductCache(
        redis_client=mock_redis_client,
        local_catalog=mock_local_catalog,
        shopify_client=mock_shopify_client,
        ttl_seconds=3600
    )
    return cache

@pytest.mark.asyncio
async def test_get_product_from_redis(product_cache, mock_redis_client):
    """Prueba la obtención de producto desde Redis."""
    # Configurar mock de Redis para devolver datos
    test_product = {"id": "123", "title": "Redis Product"}
    # Crear un nuevo AsyncMock con el valor de retorno correcto instead of modifying return_value directly
    mock_redis_client.get = AsyncMock(return_value=json.dumps(test_product))
    
    # Obtener producto
    product = await product_cache.get_product("123")
    
    # Verificar
    assert product["title"] == "Redis Product"
    assert product_cache.stats["redis_hits"] == 1
    mock_redis_client.get.assert_called_once()

@pytest.mark.asyncio
async def test_get_product_from_local_catalog(product_cache, mock_redis_client, mock_local_catalog):
    """Prueba la obtención de producto desde el catálogo local cuando no está en Redis."""
    # Configurar mock de Redis para devolver None (no encontrado)
    mock_redis_client.get = AsyncMock(return_value=None)
    
    # Obtener producto
    product = await product_cache.get_product("123")
    
    # Verificar
    assert product["title"] == "Test Product"
    assert product_cache.stats["redis_misses"] == 1
    assert product_cache.stats["local_catalog_hits"] == 1
    mock_local_catalog.get_product_by_id.assert_called_once_with("123")
    
    # Verificar que se intentó guardar en Redis
    mock_redis_client.set.assert_called_once()

@pytest.mark.asyncio
async def test_get_product_from_shopify(product_cache, mock_redis_client, mock_local_catalog, mock_shopify_client):
    """Prueba la obtención de producto desde Shopify cuando no está en Redis ni catálogo local."""
    # Configurar mocks
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_local_catalog.get_product_by_id = MagicMock(return_value=None)
    
    # Configurar catálogo local para que no tenga el producto
    mock_local_catalog.product_data = []
    
    # Configurar Shopify client para ser async
    mock_shopify_client.get_product_async = AsyncMock(return_value={"id": "123", "title": "Test Product"})
    
    # Obtener producto
    product = await product_cache.get_product("123")
    
    # Verificar
    assert product["title"] == "Test Product"
    assert product_cache.stats["redis_misses"] == 1
    assert product_cache.stats["shopify_hits"] == 1
    
    # Verificar que se intentó guardar en Redis
    mock_redis_client.set.assert_called_once()

@pytest.mark.asyncio
async def test_product_not_found(product_cache, mock_redis_client, mock_local_catalog, mock_shopify_client):
    """Prueba el comportamiento cuando un producto no se encuentra en ninguna fuente."""
    # Configurar mocks para que no encuentren el producto
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_local_catalog.get_product_by_id = MagicMock(return_value=None)
    mock_local_catalog.product_data = []
    mock_shopify_client.get_product = MagicMock(return_value=None)
    mock_shopify_client.get_product_async = AsyncMock(return_value=None)
    
    # Obtener producto
    product = await product_cache.get_product("456")
    
    # Verificar
    assert product is None
    assert product_cache.stats["redis_misses"] == 1
    assert product_cache.stats["total_failures"] == 1
    assert mock_redis_client.set.call_count == 0  # No debería intentar guardar en caché

@pytest.mark.asyncio
async def test_preload_products(product_cache, mock_redis_client):
    """Prueba la precarga de múltiples productos."""
    # Configurar product_cache para espiar el método get_product
    product_cache.get_product = AsyncMock(return_value={"id": "test", "title": "Test"})
    
    # Llamar a preload_products
    await product_cache.preload_products(["1", "2", "3"])
    
    # Verificar que se llamó a get_product para cada ID
    assert product_cache.get_product.call_count == 3

@pytest.mark.asyncio
async def test_invalidate_product(product_cache, mock_redis_client):
    """Prueba la invalidación de un producto en caché."""
    # Invalidar producto
    result = await product_cache.invalidate("123")
    
    # Verificar
    assert result is True
    mock_redis_client.delete.assert_called_once()

@pytest.mark.asyncio
async def test_invalidate_multiple_products(product_cache):
    """Prueba la invalidación de múltiples productos."""
    # Configurar para espiar el método invalidate
    original_invalidate = product_cache.invalidate
    product_cache.invalidate = AsyncMock(return_value=True)
    
    # Invalidar múltiples productos
    result = await product_cache.invalidate_multiple(["1", "2", "3"])
    
    # Verificar
    assert result == 3
    assert product_cache.invalidate.call_count == 3
    
    # Restaurar método original para las siguientes pruebas
    product_cache.invalidate = original_invalidate

@pytest.mark.asyncio
async def test_redis_connection_failure(mock_local_catalog, mock_shopify_client):
    """Prueba el comportamiento cuando Redis no está disponible."""
    # Crear mock de Redis que simula fallo de conexión
    redis_client = MagicMock()
    redis_client.connected = False
    redis_client.get = AsyncMock(side_effect=Exception("Connection error"))
    
    # Crear ProductCache con este cliente
    cache = ProductCache(
        redis_client=redis_client,
        local_catalog=mock_local_catalog,
        shopify_client=mock_shopify_client
    )
    
    # Obtener producto - debería fallar en Redis pero recuperar del catálogo local
    product = await cache.get_product("123")
    
    # Verificar
    assert product is not None
    assert product["title"] == "Test Product"
    assert cache.stats["local_catalog_hits"] == 1
    
    # Verificar que no se intentó guardar en Redis (porque no está conectado)
    assert redis_client.set.call_count == 0

@pytest.mark.asyncio
async def test_corrupted_cache_data(product_cache, mock_redis_client):
    """Prueba el comportamiento cuando los datos en Redis están corruptos."""
    # Configurar mock de Redis para devolver datos JSON inválidos
    mock_redis_client.get = AsyncMock(return_value="{invalid json")
    
    # Obtener producto - debería fallar en Redis pero recuperar del catálogo local
    product = await product_cache.get_product("123")
    
    # Verificar
    assert product is not None
    assert product["title"] == "Test Product"
    assert product_cache.stats["local_catalog_hits"] == 1

def test_calculate_hit_ratio(product_cache):
    """Prueba el cálculo del ratio de aciertos."""
    # Configurar estadísticas
    product_cache.stats = {
        "redis_hits": 5,
        "local_catalog_hits": 3,
        "shopify_hits": 2,
        "gateway_hits": 0,
        "total_requests": 20,
        "redis_misses": 10,
        "total_failures": 0
    }
    
    # Calcular ratio
    ratio = product_cache._calculate_hit_ratio()
    
    # Verificar
    assert ratio == 0.5  # (5+3+2+0)/20 = 10/20 = 0.5

def test_get_stats(product_cache):
    """Prueba la obtención de estadísticas."""
    # Configurar estadísticas
    product_cache.stats = {
        "redis_hits": 5,
        "local_catalog_hits": 3,
        "shopify_hits": 2,
        "gateway_hits": 0,
        "total_requests": 20,
        "redis_misses": 10,
        "total_failures": 0
    }
    product_cache.ttl_seconds = 3600
    
    # Obtener estadísticas
    stats = product_cache.get_stats()
    
    # Verificar
    assert stats["hit_ratio"] == 0.5
    assert stats["total_requests"] == 20
    assert stats["ttl_seconds"] == 3600

if __name__ == "__main__":
    # Para ejecución manual con pytest
    pytest.main(["-xvs", __file__])
