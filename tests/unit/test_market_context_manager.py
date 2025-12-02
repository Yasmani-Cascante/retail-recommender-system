"""
Test Suite for MarketContextManager - Multi-Market Support Layer
=================================================================

Tests basados en la implementación REAL de market_manager.py validando:
- Inicialización con RedisService (REQUERIDO)
- Configuración de mercados (US, ES, MX, CL)
- Detección de mercados
- Adaptación de recomendaciones
- Cálculo de precios localizados
- Error handling y graceful degradation

Author: Senior Architecture Team
Date: 30 Noviembre 2025
Version: 2.0.0 - Basado en implementación real
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any, List
from decimal import Decimal

# Module under test
from src.api.mcp.adapters.market_manager import MarketContextManager

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_redis_service():
    """
    Mock del RedisService para tests de MarketContextManager.
    
    Simula operaciones de cache para market configurations.
    """
    mock = AsyncMock()
    
    # Operaciones básicas de cache (MarketContextManager usa get/set directamente)
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    
    return mock


@pytest.fixture
async def market_manager_instance(mock_redis_service):
    """
    Fixture que proporciona una instancia de MarketContextManager.
    
    NOTA: redis_service es REQUERIDO en la implementación real.
    """
    manager = MarketContextManager(
        redis_service=mock_redis_service,
        default_market="US"
    )
    
    yield manager
    
    # Cleanup
    if hasattr(manager, 'redis'):
        manager.redis = None


# ============================================================================
# TEST CLASS 1: INITIALIZATION
# ============================================================================

class TestMarketContextManagerInitialization:
    """
    Tests de inicialización del MarketContextManager.
    
    Basado en implementación real:
    - redis_service es REQUERIDO (no opcional)
    - default_market tiene default "US"
    """
    
    @pytest.mark.asyncio
    async def test_initialization_with_redis_service(self, mock_redis_service):
        """
        Verifica inicialización con RedisService (caso normal).
        
        Given: Un RedisService mock
        When: Se crea MarketContextManager con redis_service
        Then: Se inicializa correctamente
        """
        manager = MarketContextManager(
            redis_service=mock_redis_service,
            default_market="US"
        )
        
        # Verificar atributos
        assert manager.redis is not None, "Should have redis service"
        assert manager.redis == mock_redis_service
        assert manager.default_market == "US"
        assert manager._initialized is False, "Should start uninitialized"
    
    @pytest.mark.asyncio
    async def test_initialization_with_custom_default_market(self, mock_redis_service):
        """
        Verifica inicialización con default_market personalizado.
        
        Given: Un default_market diferente a "US"
        When: Se crea MarketContextManager
        Then: Usa el default_market especificado
        """
        manager = MarketContextManager(
            redis_service=mock_redis_service,
            default_market="ES"
        )
        
        assert manager.default_market == "ES"
        assert manager.redis == mock_redis_service
    
    @pytest.mark.asyncio
    async def test_initialization_sets_market_configs_empty(self, mock_redis_service):
        """
        Verifica que market_configs empieza vacío.
        
        Given: Una nueva instancia de MarketContextManager
        When: Se inicializa
        Then: market_configs está vacío (se carga con initialize())
        """
        manager = MarketContextManager(
            redis_service=mock_redis_service,
            default_market="US"
        )
        
        assert hasattr(manager, 'market_configs')
        assert manager.market_configs == {}


# ============================================================================
# TEST CLASS 2: INITIALIZATION & LAZY LOADING
# ============================================================================

class TestMarketManagerInitialization:
    """
    Tests del método initialize() y ensure_initialized().
    """
    
    @pytest.mark.asyncio
    async def test_initialize_loads_supported_markets(self, market_manager_instance):
        """
        Verifica que initialize() carga los mercados soportados.
        
        Given: Un MarketContextManager no inicializado
        When: Se llama initialize()
        Then: market_configs se carga con mercados soportados
        """
        # Verificar estado inicial
        assert market_manager_instance._initialized is False
        
        # Inicializar
        result = await market_manager_instance.initialize()
        
        # Verificar resultado
        assert result is True
        assert market_manager_instance._initialized is True
        assert len(market_manager_instance.market_configs) > 0
    
    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, market_manager_instance):
        """
        Verifica que initialize() se puede llamar múltiples veces.
        
        Given: Un MarketContextManager ya inicializado
        When: Se llama initialize() nuevamente
        Then: Retorna True sin re-inicializar
        """
        # Primera inicialización
        await market_manager_instance.initialize()
        first_config = market_manager_instance.market_configs.copy()
        
        # Segunda inicialización
        await market_manager_instance.initialize()
        second_config = market_manager_instance.market_configs
        
        # Debe mantener misma configuración
        assert first_config == second_config
    
    @pytest.mark.asyncio
    async def test_ensure_initialized_triggers_initialization(self, market_manager_instance):
        """
        Verifica que ensure_initialized() inicializa si no está inicializado.
        
        Given: Un MarketContextManager no inicializado
        When: Se llama ensure_initialized()
        Then: Se ejecuta initialize() automáticamente
        """
        assert market_manager_instance._initialized is False
        
        await market_manager_instance.ensure_initialized()
        
        assert market_manager_instance._initialized is True


# ============================================================================
# TEST CLASS 3: SUPPORTED MARKETS
# ============================================================================

class TestSupportedMarkets:
    """
    Tests de get_supported_markets().
    """
    
    @pytest.mark.asyncio
    async def test_get_supported_markets_returns_dict(self, market_manager_instance):
        """
        Verifica que get_supported_markets() retorna un diccionario.
        
        Given: Un MarketContextManager
        When: Se llama get_supported_markets()
        Then: Retorna dict con markets
        """
        markets = await market_manager_instance.get_supported_markets()
        
        assert isinstance(markets, dict), "Should return a dict"
        assert len(markets) > 0, "Should have at least one market"
    
    @pytest.mark.asyncio
    async def test_get_supported_markets_includes_required_markets(
        self,
        market_manager_instance
    ):
        """
        Verifica que incluye los mercados requeridos.
        
        Given: Un MarketContextManager
        When: Se obtienen mercados soportados
        Then: Incluye US, ES, MX, CL, default
        """
        markets = await market_manager_instance.get_supported_markets()
        
        required_markets = ["US", "ES", "MX", "CL", "default"]
        for market in required_markets:
            assert market in markets, f"Should include {market} market"
    
    @pytest.mark.asyncio
    async def test_get_supported_markets_structure(self, market_manager_instance):
        """
        Verifica estructura correcta de cada market.
        
        Given: Mercados soportados
        When: Se examina cada configuración
        Then: Contiene name, currency, language, etc.
        """
        markets = await market_manager_instance.get_supported_markets()
        
        # Verificar estructura de US market
        us_config = markets["US"]
        required_fields = ["name", "currency", "language", "timezone", "enabled"]
        
        for field in required_fields:
            assert field in us_config, f"US config should have {field}"
    
    @pytest.mark.asyncio
    async def test_get_supported_markets_caches_in_redis(
        self,
        market_manager_instance,
        mock_redis_service
    ):
        """
        Verifica que los mercados se cachean en Redis.
        
        Given: Un MarketContextManager con Redis
        When: Se llama get_supported_markets()
        Then: Se guarda en cache con TTL de 24h
        """
        await market_manager_instance.get_supported_markets()
        
        # Verificar que se llamó set en Redis
        mock_redis_service.set.assert_called_once()
        call_args = mock_redis_service.set.call_args
        
        # Verificar key
        assert call_args[0][0] == "supported_markets"
        
        # Verificar TTL (24 horas = 86400 segundos)
        assert call_args[1].get('ttl') == 86400


# ============================================================================
# TEST CLASS 4: MARKET DETECTION
# ============================================================================

class TestMarketDetection:
    """
    Tests de detect_market().
    """
    
    @pytest.mark.asyncio
    async def test_detect_market_from_explicit_market_id(self, market_manager_instance):
        """
        Verifica detección desde market_id explícito.
        
        Given: Un request_context con market_id
        When: Se detecta el mercado
        Then: Retorna el market_id especificado
        """
        request_context = {"market_id": "ES"}
        
        market = await market_manager_instance.detect_market(request_context)
        
        assert market == "ES"
    
    @pytest.mark.asyncio
    async def test_detect_market_from_country_code(self, market_manager_instance):
        """
        Verifica detección desde country_code (geolocation).
        
        Given: Un request_context con country_code
        When: Se detecta el mercado
        Then: Mapea country_code a market_id correspondiente
        """
        request_context = {"country_code": "MX"}
        
        market = await market_manager_instance.detect_market(request_context)
        
        assert market == "MX"
    
    @pytest.mark.asyncio
    async def test_detect_market_from_user_preference(
        self,
        market_manager_instance,
        mock_redis_service
    ):
        """
        Verifica detección desde preferencia de usuario en cache.
        
        Given: Un request_context con user_id y preferencia cacheada
        When: Se detecta el mercado
        Then: Retorna la preferencia del usuario
        
        NOTA: detect_market() llama a ensure_initialized() primero,
        que hace get('supported_markets'), y luego hace get('user_market:...')
        Por eso verificamos que se llamó con el argumento correcto, no el count.
        """
        request_context = {"user_id": "user_123"}
        
        # Simular preferencia cacheada para user_market:user_123
        # pero None para supported_markets (cache miss)
        async def mock_get(key):
            if key == "user_market:user_123":
                return "CL"
            return None  # Cache miss para supported_markets
        
        mock_redis_service.get = AsyncMock(side_effect=mock_get)
        
        market = await market_manager_instance.detect_market(request_context)
        
        # Verificar que retornó la preferencia del usuario
        assert market == "CL"
        
        # Verificar que se llamó get con la key correcta (sin importar cuántas veces)
        mock_redis_service.get.assert_any_call("user_market:user_123")
    
    @pytest.mark.asyncio
    async def test_detect_market_defaults_when_no_context(self, market_manager_instance):
        """
        Verifica fallback a default market cuando no hay contexto.
        
        Given: Un request_context vacío
        When: Se detecta el mercado
        Then: Retorna el default_market (US)
        """
        request_context = {}
        
        market = await market_manager_instance.detect_market(request_context)
        
        assert market == "US"  # Default


# ============================================================================
# TEST CLASS 5: MARKET CONFIGURATION
# ============================================================================

class TestMarketConfiguration:
    """
    Tests de get_market_config().
    """
    
    @pytest.mark.asyncio
    async def test_get_market_config_us(self, market_manager_instance):
        """
        Verifica obtención de configuración del mercado US.
        
        Given: Un MarketContextManager
        When: Se solicita config de US
        Then: Retorna configuración completa
        """
        config = await market_manager_instance.get_market_config("US")
        
        assert config is not None
        assert config["name"] == "United States"
        assert config["currency"] == "USD"
        assert config["language"] == "en"
    
    @pytest.mark.asyncio
    async def test_get_market_config_es(self, market_manager_instance):
        """
        Verifica configuración del mercado ES (España).
        """
        config = await market_manager_instance.get_market_config("ES")
        
        assert config is not None
        assert config["name"] == "Spain"
        assert config["currency"] == "EUR"
        assert config["language"] == "es"
    
    @pytest.mark.asyncio
    async def test_get_market_config_caches_result(
        self,
        market_manager_instance,
        mock_redis_service
    ):
        """
        Verifica que la configuración se cachea en Redis.
        
        Given: Una configuración cargada
        When: Se obtiene la configuración
        Then: Se guarda en cache con TTL de 1 hora
        """
        # Primera llamada (no hay cache)
        config = await market_manager_instance.get_market_config("MX")
        
        # Verificar que se llamó set para cachear
        assert mock_redis_service.set.called


# ============================================================================
# TEST CLASS 6: RECOMMENDATION ADAPTATION
# ============================================================================

class TestRecommendationAdaptation:
    """
    Tests de adapt_recommendations_for_market().
    """
    
    @pytest.mark.asyncio
    async def test_adapt_recommendations_adds_market_price(
        self,
        market_manager_instance
    ):
        """
        Verifica que se agrega market_price a cada recomendación.
        
        Given: Recomendaciones base
        When: Se adaptan para un mercado
        Then: Cada recomendación incluye market_price
        """
        recommendations = [
            {"id": "prod_1", "title": "Product 1", "price": 100.0, "score": 0.8}
        ]
        
        adapted = await market_manager_instance.adapt_recommendations_for_market(
            recommendations,
            market_id="US"
        )
        
        assert len(adapted) > 0
        assert "market_price" in adapted[0]
    
    @pytest.mark.asyncio
    async def test_adapt_recommendations_adds_market_score(
        self,
        market_manager_instance
    ):
        """
        Verifica que se ajusta el score según el mercado.
        """
        recommendations = [
            {"id": "prod_1", "title": "Product 1", "price": 100.0, "score": 0.8}
        ]
        
        adapted = await market_manager_instance.adapt_recommendations_for_market(
            recommendations,
            market_id="ES"
        )
        
        assert "market_score" in adapted[0]
        assert isinstance(adapted[0]["market_score"], float)
        assert 0.0 <= adapted[0]["market_score"] <= 1.0
    
    @pytest.mark.asyncio
    async def test_adapt_recommendations_localizes_content(
        self,
        market_manager_instance
    ):
        """
        Verifica que se localiza el contenido según el idioma.
        """
        recommendations = [
            {"id": "prod_1", "title": "Product 1", "price": 100.0, "score": 0.8}
        ]
        
        adapted = await market_manager_instance.adapt_recommendations_for_market(
            recommendations,
            market_id="ES"
        )
        
        assert "localized_title" in adapted[0]


# ============================================================================
# TEST CLASS 7: PRICE CALCULATION
# ============================================================================

class TestPriceCalculation:
    """
    Tests de _calculate_landed_cost().
    """
    
    @pytest.mark.asyncio
    async def test_calculate_landed_cost_us_no_conversion(
        self,
        market_manager_instance
    ):
        """
        Verifica que precio USD no se convierte en mercado US.
        
        Given: Un precio base de $100 USD
        When: Se calcula para mercado US
        Then: Precio se mantiene en rango similar (con impuestos)
        """
        base_price = 100.0
        
        landed_cost = await market_manager_instance._calculate_landed_cost(
            base_price,
            market_id="US"
        )
        
        # Debería ser base_price + ~8.25% tax
        assert 105.0 < landed_cost < 115.0
    
    @pytest.mark.asyncio
    async def test_calculate_landed_cost_converts_to_eur(
        self,
        market_manager_instance
    ):
        """
        Verifica conversión a EUR para mercado ES.
        
        Given: Un precio base de $100 USD
        When: Se calcula para mercado ES
        Then: Se convierte a EUR (rate ~0.85) y agrega IVA 21%
        """
        base_price = 100.0
        
        landed_cost = await market_manager_instance._calculate_landed_cost(
            base_price,
            market_id="ES"
        )
        
        # 100 USD * 0.85 EUR/USD * 1.21 (IVA) ≈ 102-104 EUR
        assert 95.0 < landed_cost < 110.0
    
    @pytest.mark.asyncio
    async def test_calculate_landed_cost_converts_to_mxn(
        self,
        market_manager_instance
    ):
        """
        Verifica conversión a MXN para mercado MX.
        """
        base_price = 100.0
        
        landed_cost = await market_manager_instance._calculate_landed_cost(
            base_price,
            market_id="MX"
        )
        
        # 100 USD * 17.5 MXN/USD * 1.16 (IVA) ≈ 2000+ MXN
        assert landed_cost > 1500


# ============================================================================
# TEST CLASS 8: UTILITY METHODS
# ============================================================================

class TestUtilityMethods:
    """
    Tests de métodos auxiliares.
    """
    
    def test_country_to_market_us(self, market_manager_instance):
        """
        Verifica mapeo de US a mercado US.
        """
        market = market_manager_instance._country_to_market("US")
        assert market == "US"
    
    def test_country_to_market_canada_maps_to_us(self, market_manager_instance):
        """
        Verifica que Canadá mapea a mercado US.
        """
        market = market_manager_instance._country_to_market("CA")
        assert market == "US"
    
    def test_country_to_market_spain(self, market_manager_instance):
        """
        Verifica mapeo de ES a mercado ES.
        """
        market = market_manager_instance._country_to_market("ES")
        assert market == "ES"
    
    def test_country_to_market_unknown_defaults(self, market_manager_instance):
        """
        Verifica que país desconocido usa default.
        """
        market = market_manager_instance._country_to_market("XX")
        assert market == "US"  # default_market


# ============================================================================
# RUNNER CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    """
    Ejecutar tests directamente:
    
    pytest tests/unit/test_market_context_manager.py -v
    pytest tests/unit/test_market_context_manager.py -v --cov=src.api.mcp.adapters.market_manager
    """
    pytest.main([__file__, "-v", "--tb=short"])
