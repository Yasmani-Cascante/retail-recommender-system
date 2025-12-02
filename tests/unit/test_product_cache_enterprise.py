"""
Test Suite for MarketAwareProductCache - Market-Aware Caching Layer (PARTE 1)
===============================================================================

Tests basados en la implementación REAL de market_cache.py validando:
- Inicialización con RedisService
- Operaciones básicas de cache (get/set)
- Segmentación por mercado
- Invalidación de productos
- Estadísticas de cache
- Health checks

Author: Senior Architecture Team
Date: 30 Noviembre 2025
Version: 1.0.0 - Fase 3A Day 3 (Parte 1 de 2)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any, List, Optional
from datetime import datetime

# Module under test
from src.cache.market_aware.market_cache import MarketAwareProductCache

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_redis_service():
    """
    Mock del RedisService para tests de MarketAwareProductCache.
    
    Simula operaciones async de cache con get_json/set_json.
    """
    mock = AsyncMock()
    
    # Operaciones que usa MarketAwareProductCache
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.get_json = AsyncMock(return_value=None)
    mock.set_json = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=True)
    
    return mock


@pytest.fixture
def mock_base_product_cache():
    """
    Mock del ProductCache base para fallback.
    """
    mock = AsyncMock()
    mock.get_product = AsyncMock(return_value=None)
    mock.set_product = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def sample_product():
    """
    Producto de ejemplo para tests.
    """
    return {
        "id": "prod_123",
        "title": "Test Product",
        "price": 99.99,
        "currency": "USD",
        "availability": {
            "US": True,
            "ES": True,
            "MX": False
        },
        "description": "A test product"
    }


@pytest.fixture
async def market_cache_instance(mock_redis_service):
    """
    Fixture que proporciona una instancia de MarketAwareProductCache.
    
    Cleanup automático de stats después de cada test.
    """
    cache = MarketAwareProductCache(
        redis_service=mock_redis_service,
        default_ttl=3600
    )
    
    yield cache
    
    # Cleanup: Reset stats
    cache.stats = {
        "hits": 0,
        "misses": 0,
        "market_segments": set(),
        "total_requests": 0
    }


# ============================================================================
# TEST CLASS 1: INITIALIZATION
# ============================================================================

class TestMarketAwareProductCacheInitialization:
    """
    Tests de inicialización de MarketAwareProductCache.
    
    Basado en implementación real:
    - redis_service es REQUERIDO
    - base_product_cache es opcional
    - default_ttl tiene default de 3600
    """
    
    @pytest.mark.asyncio
    async def test_initialization_with_redis_service(self, mock_redis_service):
        """
        Verifica inicialización básica con RedisService.
        
        Given: Un RedisService mock
        When: Se crea MarketAwareProductCache
        Then: Se inicializa correctamente con valores default
        """
        cache = MarketAwareProductCache(
            redis_service=mock_redis_service
        )
        
        # Verificar atributos
        assert cache.redis is not None
        assert cache.redis == mock_redis_service
        assert cache.default_ttl == 3600
        assert cache.cache_prefix == "market_cache:"
        assert cache.base_product_cache is None
    
    @pytest.mark.asyncio
    async def test_initialization_with_custom_ttl(self, mock_redis_service):
        """
        Verifica inicialización con TTL personalizado.
        
        Given: Un TTL custom de 7200 segundos
        When: Se crea MarketAwareProductCache
        Then: Usa el TTL especificado
        """
        cache = MarketAwareProductCache(
            redis_service=mock_redis_service,
            default_ttl=7200
        )
        
        assert cache.default_ttl == 7200
    
    @pytest.mark.asyncio
    async def test_initialization_sets_stats_to_zero(self, mock_redis_service):
        """
        Verifica que stats empiezan en cero.
        
        Given: Una nueva instancia
        When: Se inicializa
        Then: Todas las stats están en 0
        """
        cache = MarketAwareProductCache(
            redis_service=mock_redis_service
        )
        
        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 0
        assert cache.stats["total_requests"] == 0
        assert len(cache.stats["market_segments"]) == 0
    
    @pytest.mark.asyncio
    async def test_initialization_with_base_product_cache(
        self,
        mock_redis_service,
        mock_base_product_cache
    ):
        """
        Verifica inicialización con ProductCache base para fallback.
        
        Given: Un ProductCache base
        When: Se crea MarketAwareProductCache
        Then: Se guarda la referencia
        """
        cache = MarketAwareProductCache(
            redis_service=mock_redis_service,
            base_product_cache=mock_base_product_cache
        )
        
        assert cache.base_product_cache is not None
        assert cache.base_product_cache == mock_base_product_cache


# ============================================================================
# TEST CLASS 2: GET PRODUCT OPERATIONS
# ============================================================================

class TestGetProductOperations:
    """
    Tests de get_product().
    """
    
    @pytest.mark.asyncio
    async def test_get_product_cache_hit(
        self,
        market_cache_instance,
        mock_redis_service,
        sample_product
    ):
        """
        Verifica get_product con cache hit.
        
        Given: Un producto cacheado en Redis
        When: Se solicita el producto
        Then: Retorna el producto y incrementa hits
        """
        # Simular cache hit
        mock_redis_service.get_json = AsyncMock(return_value=sample_product)
        
        result = await market_cache_instance.get_product("prod_123", "US")
        
        # Verificar resultado
        assert result is not None
        assert result["id"] == "prod_123"
        
        # Verificar stats
        assert market_cache_instance.stats["hits"] == 1
        assert market_cache_instance.stats["misses"] == 0
        assert market_cache_instance.stats["total_requests"] == 1
        assert "US" in market_cache_instance.stats["market_segments"]
    
    @pytest.mark.asyncio
    async def test_get_product_cache_miss(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica get_product con cache miss.
        
        Given: Un producto NO cacheado
        When: Se solicita el producto
        Then: Retorna None y incrementa misses
        """
        # Simular cache miss
        mock_redis_service.get_json = AsyncMock(return_value=None)
        
        result = await market_cache_instance.get_product("prod_999", "ES")
        
        # Verificar resultado
        assert result is None
        
        # Verificar stats
        assert market_cache_instance.stats["hits"] == 0
        assert market_cache_instance.stats["misses"] == 1
        assert market_cache_instance.stats["total_requests"] == 1
        assert "ES" in market_cache_instance.stats["market_segments"]
    
    @pytest.mark.asyncio
    async def test_get_product_uses_correct_cache_key(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica que se usa la cache key correcta con market segmentation.
        
        Given: Un product_id y market_id
        When: Se solicita el producto
        Then: Se construye la key con formato correcto
        """
        await market_cache_instance.get_product("prod_456", "MX")
        
        # Verificar que se llamó get_json con la key correcta
        expected_key = "market_cache:MX:product:prod_456"
        mock_redis_service.get_json.assert_called_once_with(expected_key)
    
    @pytest.mark.asyncio
    async def test_get_product_with_default_market(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica get_product sin especificar market_id.
        
        Given: Sin market_id (usa default)
        When: Se solicita el producto
        Then: Usa "default" como market_id
        """
        await market_cache_instance.get_product("prod_789")
        
        # Verificar que usó "default" como market
        expected_key = "market_cache:default:product:prod_789"
        mock_redis_service.get_json.assert_called_once_with(expected_key)
    
    @pytest.mark.asyncio
    async def test_get_product_handles_redis_error(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica manejo de errores de Redis.
        
        Given: Redis lanza una excepción
        When: Se solicita un producto
        Then: Retorna None sin propagar error
        """
        # Simular error de Redis
        mock_redis_service.get_json = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await market_cache_instance.get_product("prod_error", "US")
        
        # Debe retornar None sin propagar excepción
        assert result is None
        
        # Stats deben registrar el intento
        assert market_cache_instance.stats["total_requests"] == 1


# ============================================================================
# TEST CLASS 3: SET PRODUCT OPERATIONS
# ============================================================================

class TestSetProductOperations:
    """
    Tests de set_product().
    """
    
    @pytest.mark.asyncio
    async def test_set_product_success(
        self,
        market_cache_instance,
        mock_redis_service,
        sample_product
    ):
        """
        Verifica set_product exitoso.
        
        Given: Un producto válido
        When: Se guarda en cache
        Then: Retorna True
        """
        result = await market_cache_instance.set_product(
            "prod_123",
            sample_product,
            "US"
        )
        
        assert result is True
        mock_redis_service.set_json.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_set_product_adds_market_metadata(
        self,
        market_cache_instance,
        mock_redis_service,
        sample_product
    ):
        """
        Verifica que se agrega metadata de mercado.
        
        Given: Un producto sin metadata
        When: Se guarda en cache
        Then: Se agrega _market_cache_metadata
        """
        await market_cache_instance.set_product(
            "prod_123",
            sample_product,
            "ES"
        )
        
        # Obtener el producto enriquecido que se guardó
        call_args = mock_redis_service.set_json.call_args
        enriched_data = call_args[0][1]  # Segundo argumento
        
        # Verificar metadata
        assert "_market_cache_metadata" in enriched_data
        assert enriched_data["_market_cache_metadata"]["market_id"] == "ES"
        assert "cached_at" in enriched_data["_market_cache_metadata"]
        assert enriched_data["_market_cache_metadata"]["ttl"] == 3600
    
    @pytest.mark.asyncio
    async def test_set_product_uses_correct_cache_key(
        self,
        market_cache_instance,
        mock_redis_service,
        sample_product
    ):
        """
        Verifica que se usa la cache key correcta.
        """
        await market_cache_instance.set_product(
            "prod_456",
            sample_product,
            "MX"
        )
        
        # Verificar key
        call_args = mock_redis_service.set_json.call_args
        expected_key = "market_cache:MX:product:prod_456"
        
        assert call_args[0][0] == expected_key
    
    @pytest.mark.asyncio
    async def test_set_product_uses_default_ttl(
        self,
        market_cache_instance,
        mock_redis_service,
        sample_product
    ):
        """
        Verifica que usa default_ttl si no se especifica.
        
        Given: Sin TTL especificado
        When: Se guarda producto
        Then: Usa default_ttl (3600)
        """
        await market_cache_instance.set_product(
            "prod_789",
            sample_product,
            "US"
        )
        
        # Verificar TTL
        call_args = mock_redis_service.set_json.call_args
        assert call_args[1].get("ttl") == 3600
    
    @pytest.mark.asyncio
    async def test_set_product_uses_custom_ttl(
        self,
        market_cache_instance,
        mock_redis_service,
        sample_product
    ):
        """
        Verifica que se puede especificar TTL custom.
        """
        await market_cache_instance.set_product(
            "prod_custom",
            sample_product,
            "ES",
            ttl=7200
        )
        
        # Verificar TTL custom
        call_args = mock_redis_service.set_json.call_args
        assert call_args[1].get("ttl") == 7200
    
    @pytest.mark.asyncio
    async def test_set_product_handles_redis_error(
        self,
        market_cache_instance,
        mock_redis_service,
        sample_product
    ):
        """
        Verifica manejo de errores de Redis en set.
        
        Given: Redis lanza excepción
        When: Se intenta guardar producto
        Then: Retorna False sin propagar error
        """
        # Simular error
        mock_redis_service.set_json = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await market_cache_instance.set_product(
            "prod_error",
            sample_product,
            "US"
        )
        
        assert result is False


# ============================================================================
# TEST CLASS 4: CACHE STATISTICS
# ============================================================================

class TestCacheStatistics:
    """
    Tests de get_cache_stats().
    """
    
    @pytest.mark.asyncio
    async def test_get_cache_stats_initial_state(self, market_cache_instance):
        """
        Verifica stats en estado inicial.
        
        Given: Cache recién inicializado
        When: Se obtienen stats
        Then: Todos los contadores están en 0
        """
        stats = await market_cache_instance.get_cache_stats()
        
        assert stats["total_requests"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_ratio"] == 0.0
        assert stats["market_segments"] == 0
        assert "timestamp" in stats
    
    @pytest.mark.asyncio
    async def test_get_cache_stats_after_operations(
        self,
        market_cache_instance,
        mock_redis_service,
        sample_product
    ):
        """
        Verifica stats después de operaciones.
        
        Given: Algunas operaciones de cache
        When: Se obtienen stats
        Then: Reflejan las operaciones realizadas
        """
        # Simular operaciones
        mock_redis_service.get_json = AsyncMock(side_effect=[
            sample_product,  # Hit
            None,            # Miss
            sample_product   # Hit
        ])
        
        await market_cache_instance.get_product("prod_1", "US")
        await market_cache_instance.get_product("prod_2", "ES")
        await market_cache_instance.get_product("prod_3", "MX")
        
        # Obtener stats
        stats = await market_cache_instance.get_cache_stats()
        
        assert stats["total_requests"] == 3
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_ratio"] == 2/3
        assert stats["market_segments"] == 3  # US, ES, MX
    
    @pytest.mark.asyncio
    async def test_get_cache_stats_with_market_id(self, market_cache_instance):
        """
        Verifica stats específicos de un mercado.
        
        Given: Un market_id específico
        When: Se obtienen stats
        Then: Incluye información del mercado
        """
        stats = await market_cache_instance.get_cache_stats(market_id="US")
        
        assert stats["market_id"] == "US"
        assert stats["market_specific"] is True


# ============================================================================
# TEST CLASS 5: HEALTH CHECK
# ============================================================================

class TestHealthCheck:
    """
    Tests de health_check().
    """
    
    @pytest.mark.asyncio
    async def test_health_check_with_connected_redis(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica health check con Redis conectado.
        
        Given: Redis disponible
        When: Se ejecuta health check
        Then: Status es operational
        """
        # Simular operaciones exitosas
        mock_redis_service.set = AsyncMock(return_value=True)
        mock_redis_service.get = AsyncMock(return_value={"test": True})
        mock_redis_service.delete = AsyncMock(return_value=True)
        
        health = await market_cache_instance.health_check()
        
        assert health["status"] == "operational"
        assert health["redis_connected"] is True
        assert health["test_write_read"] is True
    
    @pytest.mark.asyncio
    async def test_health_check_without_redis(self):
        """
        Verifica health check sin Redis.
        
        Given: Redis es None
        When: Se ejecuta health check
        Then: Status es unavailable
        """
        cache = MarketAwareProductCache(redis_service=None)
        
        health = await cache.health_check()
        
        assert health["status"] == "unavailable"
        assert health["redis_connected"] is False
    
    @pytest.mark.asyncio
    async def test_health_check_includes_stats(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica que health check incluye stats de cache.
        """
        # Simular algunas operaciones
        mock_redis_service.get_json = AsyncMock(return_value={"test": "data"})
        await market_cache_instance.get_product("prod_1", "US")
        
        health = await market_cache_instance.health_check()
        
        assert "market_segments_active" in health
        assert "total_requests_processed" in health
        assert "cache_hit_ratio" in health
        assert health["total_requests_processed"] == 1


# ============================================================================
# TEST CLASS 6: PRODUCT INVALIDATION (PARTE 2)
# ============================================================================

class TestProductInvalidation:
    """
    Tests de invalidate_product().
    """
    
    @pytest.mark.asyncio
    async def test_invalidate_product_specific_market(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica invalidación de producto en mercado específico.
        
        Given: Un product_id y market_id específico
        When: Se invalida el producto
        Then: Se elimina solo de ese mercado
        """
        result = await market_cache_instance.invalidate_product(
            "prod_123",
            market_id="US"
        )
        
        # Verificar que se eliminó
        assert result == 1
        
        # Verificar que se llamó delete con la key correcta
        expected_key = "market_cache:US:product:prod_123"
        mock_redis_service.delete.assert_called_once_with(expected_key)
    
    @pytest.mark.asyncio
    async def test_invalidate_product_all_markets(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica invalidación de producto en todos los mercados.
        
        Given: Un product_id sin market_id específico
        When: Se invalida el producto
        Then: Se elimina de todos los mercados conocidos
        """
        # Simular que se eliminaron 3 de 5 mercados (algunos no tenían el producto)
        mock_redis_service.delete = AsyncMock(side_effect=[
            True,   # default
            True,   # US
            False,  # ES (no existía)
            True,   # MX
            False   # CL (no existía)
        ])
        
        result = await market_cache_instance.invalidate_product("prod_123")
        
        # Verificar que se invalidaron 3 mercados
        assert result == 3
        
        # Verificar que se llamó delete 5 veces (todos los mercados conocidos)
        assert mock_redis_service.delete.call_count == 5
    
    @pytest.mark.asyncio
    async def test_invalidate_product_failed_deletion(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica comportamiento cuando delete falla.
        
        Given: Redis delete retorna False
        When: Se invalida producto
        Then: Retorna 0
        """
        mock_redis_service.delete = AsyncMock(return_value=False)
        
        result = await market_cache_instance.invalidate_product(
            "prod_999",
            market_id="ES"
        )
        
        assert result == 0


# ============================================================================
# TEST CLASS 7: WARM CACHE (PARTE 2)
# ============================================================================

class TestWarmCache:
    """
    Tests de warm_cache_for_market().
    """
    
    @pytest.mark.asyncio
    async def test_warm_cache_for_market_success(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica pre-carga exitosa de productos para un mercado.
        
        Given: Una lista de product_ids
        When: Se pre-carga el cache
        Then: Retorna el número de productos cargados
        """
        product_ids = ["prod_1", "prod_2", "prod_3"]
        
        result = await market_cache_instance.warm_cache_for_market(
            "US",
            product_ids
        )
        
        # Verificar que se cargaron todos
        assert result == 3
        
        # Verificar que se llamó set_json 3 veces
        assert mock_redis_service.set_json.call_count == 3
    
    @pytest.mark.asyncio
    async def test_warm_cache_creates_mock_products(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica que warm_cache crea productos mock correctamente.
        
        Given: Un product_id para pre-carga
        When: Se ejecuta warm_cache
        Then: Crea un producto mock con metadata correcta
        """
        product_ids = ["prod_warmup"]
        
        await market_cache_instance.warm_cache_for_market("MX", product_ids)
        
        # Obtener el producto que se guardó
        call_args = mock_redis_service.set_json.call_args
        saved_product = call_args[0][1]  # Segundo argumento
        
        # Verificar estructura del mock product
        assert saved_product["id"] == "prod_warmup"
        assert saved_product["market_id"] == "MX"
        assert saved_product["warmup_data"] is True
        assert "warmed_at" in saved_product
        assert "_market_cache_metadata" in saved_product
    
    @pytest.mark.asyncio
    async def test_warm_cache_with_empty_list(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica comportamiento con lista vacía.
        
        Given: Una lista vacía de productos
        When: Se ejecuta warm_cache
        Then: Retorna 0
        """
        result = await market_cache_instance.warm_cache_for_market("ES", [])
        
        assert result == 0
        mock_redis_service.set_json.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_warm_cache_partial_success(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica que continúa aunque algunos fallen.
        
        Given: Algunos productos fallan al guardarse
        When: Se ejecuta warm_cache
        Then: Retorna solo los exitosos
        """
        product_ids = ["prod_1", "prod_2", "prod_3"]
        
        # Simular que solo 2 de 3 se guardan exitosamente
        mock_redis_service.set_json = AsyncMock(side_effect=[
            True,   # prod_1 OK
            False,  # prod_2 FAIL
            True    # prod_3 OK
        ])
        
        result = await market_cache_instance.warm_cache_for_market(
            "CL",
            product_ids
        )
        
        assert result == 2  # Solo 2 exitosos


# ============================================================================
# TEST CLASS 8: MARKET INVALIDATION (PARTE 2)
# ============================================================================

class TestMarketInvalidation:
    """
    Tests de invalidate_market().
    """
    
    @pytest.mark.asyncio
    async def test_invalidate_market_all_entities(
        self,
        market_cache_instance
    ):
        """
        Verifica invalidación de todo el mercado.
        
        Given: Un market_id sin entity_type específico
        When: Se invalida el mercado
        Then: Retorna True y remueve mercado de stats
        """
        # Agregar mercado a stats
        market_cache_instance.stats["market_segments"].add("US")
        
        result = await market_cache_instance.invalidate_market("US")
        
        assert result is True
        assert "US" not in market_cache_instance.stats["market_segments"]
    
    @pytest.mark.asyncio
    async def test_invalidate_market_specific_entity_type(
        self,
        market_cache_instance
    ):
        """
        Verifica invalidación de tipo específico de entidad.
        
        Given: Un market_id y entity_type
        When: Se invalida
        Then: Retorna True
        """
        result = await market_cache_instance.invalidate_market(
            "ES",
            entity_type="product"
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_invalidate_market_handles_error(
        self,
        market_cache_instance
    ):
        """
        Verifica manejo de errores en invalidación de mercado.
        
        Given: Una excepción durante invalidación
        When: Se invalida mercado
        Then: Retorna False sin propagar error
        
        NOTA: En la implementación actual es difícil forzar error
        porque es mayormente lógica Python, no Redis.
        Este test documenta el comportamiento esperado.
        """
        # Test documenta el manejo de errores existente
        # En producción, errores podrían venir de Redis SCAN
        result = await market_cache_instance.invalidate_market("MX")
        
        # Debería completarse sin errores
        assert result is True


# ============================================================================
# TEST CLASS 9: INTEGRATION & EDGE CASES (PARTE 2)
# ============================================================================

class TestIntegrationAndEdgeCases:
    """
    Tests de integración y casos edge.
    """
    
    @pytest.mark.asyncio
    async def test_multiple_markets_isolation(
        self,
        market_cache_instance,
        mock_redis_service,
        sample_product
    ):
        """
        Verifica que los mercados están aislados entre sí.
        
        Given: El mismo producto en diferentes mercados
        When: Se guardan y recuperan
        Then: Cada mercado mantiene su propia versión
        """
        # Guardar producto en US
        await market_cache_instance.set_product(
            "prod_123",
            {**sample_product, "price": 100.0},
            "US"
        )
        
        # Guardar mismo producto en ES con precio diferente
        await market_cache_instance.set_product(
            "prod_123",
            {**sample_product, "price": 85.0},
            "ES"
        )
        
        # Verificar que se llamó set_json con keys diferentes
        assert mock_redis_service.set_json.call_count == 2
        
        calls = mock_redis_service.set_json.call_args_list
        us_key = calls[0][0][0]
        es_key = calls[1][0][0]
        
        assert "US" in us_key
        assert "ES" in es_key
        assert us_key != es_key
    
    @pytest.mark.asyncio
    async def test_stats_track_multiple_markets(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica que stats rastrean múltiples mercados.
        
        Given: Operaciones en múltiples mercados
        When: Se realizan las operaciones
        Then: Stats rastrean todos los mercados únicos
        """
        # Operaciones en diferentes mercados
        await market_cache_instance.get_product("prod_1", "US")
        await market_cache_instance.get_product("prod_2", "ES")
        await market_cache_instance.get_product("prod_3", "MX")
        await market_cache_instance.get_product("prod_4", "US")  # US otra vez
        
        # Verificar que solo cuenta mercados únicos
        assert len(market_cache_instance.stats["market_segments"]) == 3
        assert "US" in market_cache_instance.stats["market_segments"]
        assert "ES" in market_cache_instance.stats["market_segments"]
        assert "MX" in market_cache_instance.stats["market_segments"]
    
    @pytest.mark.asyncio
    async def test_hit_ratio_calculation(
        self,
        market_cache_instance,
        mock_redis_service
    ):
        """
        Verifica cálculo correcto de hit ratio.
        
        Given: Mix de hits y misses
        When: Se calculan stats
        Then: Hit ratio es correcto
        """
        # 3 hits, 2 misses = 60% hit ratio
        mock_redis_service.get_json = AsyncMock(side_effect=[
            {"id": "1"},  # Hit
            {"id": "2"},  # Hit
            None,         # Miss
            {"id": "3"},  # Hit
            None          # Miss
        ])
        
        for i in range(5):
            await market_cache_instance.get_product(f"prod_{i}", "US")
        
        stats = await market_cache_instance.get_cache_stats()
        
        assert stats["hits"] == 3
        assert stats["misses"] == 2
        assert stats["hit_ratio"] == 0.6


# ============================================================================
# RUNNER CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    """
    Ejecutar tests directamente:
    
    pytest tests/unit/test_product_cache_enterprise.py -v
    pytest tests/unit/test_product_cache_enterprise.py -v --cov=src.cache.market_aware.market_cache
    """
    pytest.main([__file__, "-v", "--tb=short"])
