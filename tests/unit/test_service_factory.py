"""
Test Suite for ServiceFactory - Enterprise Dependency Injection
===============================================================

Tests basados en la implementación REAL de service_factory.py validando:
- Singleton pattern con async locks
- Thread-safe double-check locking
- Circuit breaker pattern para Redis
- Auto-wiring de dependencies
- Fallback mechanisms
- Cleanup y shutdown

Author: Senior Architecture Team
Date: 1 Diciembre 2025
Version: 1.0.0 - Fase 3A Day 5 - CORRECTED PATCHES
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call

# Module under test
from src.api.factories.service_factory import ServiceFactory

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(autouse=True)
async def cleanup_factory():
    """
    Auto-fixture que resetea ServiceFactory antes y después de cada test.
    
    CRÍTICO para tests de singleton - garantiza estado limpio.
    """
    # Reset ANTES del test
    ServiceFactory._redis_service = None
    ServiceFactory._product_cache = None
    ServiceFactory._inventory_service = None
    ServiceFactory._tfidf_recommender = None
    ServiceFactory._retail_recommender = None
    ServiceFactory._hybrid_recommender = None
    ServiceFactory._personalization_cache = None
    ServiceFactory._mcp_client = None
    ServiceFactory._market_context_manager = None
    ServiceFactory._market_cache_service = None
    ServiceFactory._conversation_state_manager = None
    
    # Reset locks
    ServiceFactory._redis_lock = None
    ServiceFactory._tfidf_lock = None
    ServiceFactory._retail_lock = None
    ServiceFactory._hybrid_lock = None
    ServiceFactory._personalization_lock = None
    ServiceFactory._mcp_client_lock = None
    ServiceFactory._market_manager_lock = None
    ServiceFactory._market_cache_lock = None
    ServiceFactory._state_manager_lock = None
    
    # Reset circuit breaker
    ServiceFactory._redis_circuit_breaker = {
        "failures": 0,
        "last_failure": 0,
        "circuit_open": False
    }
    
    yield
    
    # Reset DESPUÉS del test (cleanup)
    ServiceFactory._redis_service = None
    ServiceFactory._product_cache = None
    ServiceFactory._inventory_service = None
    ServiceFactory._tfidf_recommender = None
    ServiceFactory._retail_recommender = None
    ServiceFactory._hybrid_recommender = None
    ServiceFactory._personalization_cache = None
    ServiceFactory._mcp_client = None
    ServiceFactory._market_context_manager = None
    ServiceFactory._market_cache_service = None
    ServiceFactory._conversation_state_manager = None
    
    ServiceFactory._redis_lock = None
    ServiceFactory._tfidf_lock = None
    ServiceFactory._retail_lock = None
    ServiceFactory._hybrid_lock = None
    ServiceFactory._personalization_lock = None
    ServiceFactory._mcp_client_lock = None
    ServiceFactory._market_manager_lock = None
    ServiceFactory._market_cache_lock = None
    ServiceFactory._state_manager_lock = None
    
    ServiceFactory._redis_circuit_breaker = {
        "failures": 0,
        "last_failure": 0,
        "circuit_open": False
    }


@pytest.fixture
def mock_redis_service():
    """Mock de RedisService."""
    mock = AsyncMock()
    mock.health_check = AsyncMock(return_value={"status": "healthy"})
    mock._client = AsyncMock()
    mock._client.close = AsyncMock()
    mock._ensure_connection = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_settings():
    """Mock de configuración."""
    mock = MagicMock()
    mock.google_project_number = "test-project-123"
    mock.google_location = "global"
    mock.google_catalog = "test-catalog"
    mock.google_serving_config = "test-config"
    mock.content_weight = 0.5
    mock.exclude_seen_products = False
    mock.tfidf_model_path = "data/tfidf_model.pkl"
    mock.default_market = "US"
    mock.mcp_bridge_host = "localhost"
    mock.mcp_bridge_port = 3001
    return mock


@pytest.fixture
def mock_tfidf_recommender():
    """Mock de TFIDFRecommender."""
    mock = MagicMock()
    mock.loaded = False
    mock.product_data = []
    mock.load = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_retail_recommender():
    """Mock de RetailAPIRecommender."""
    mock = MagicMock()
    mock.get_recommendations = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_product_cache():
    """Mock de ProductCache."""
    mock = AsyncMock()
    mock.local_catalog = None
    mock.start_background_tasks = AsyncMock()
    mock.health_task = None
    return mock


# ============================================================================
# TEST CLASS 1: INITIALIZATION
# ============================================================================

class TestServiceFactoryInitialization:
    """
    Tests de inicialización de ServiceFactory.
    """
    
    def test_class_variables_initialized_to_none(self):
        """
        Verifica que variables de clase empiezan en None.
        
        Given: ServiceFactory recién importado
        When: Se verifican las variables de clase
        Then: Todas las instancias singleton están en None
        """
        assert ServiceFactory._redis_service is None
        assert ServiceFactory._product_cache is None
        assert ServiceFactory._tfidf_recommender is None
        assert ServiceFactory._retail_recommender is None
        assert ServiceFactory._hybrid_recommender is None
    
    def test_circuit_breaker_initialized_correctly(self):
        """
        Verifica inicialización del circuit breaker.
        """
        cb = ServiceFactory._redis_circuit_breaker
        
        assert cb["failures"] == 0
        assert cb["last_failure"] == 0
        assert cb["circuit_open"] is False


# ============================================================================
# TEST CLASS 2: REDIS SERVICE SINGLETON (CRÍTICO)
# ============================================================================

class TestRedisServiceSingleton:
    """
    Tests del singleton de RedisService con circuit breaker.
    """
    
    @pytest.mark.asyncio
    async def test_get_redis_service_singleton_pattern(self):
        """
        Verifica patrón singleton - dos llamadas retornan misma instancia.
        
        Given: ServiceFactory sin Redis service
        When: Se llama get_redis_service() dos veces
        Then: Ambas llamadas retornan la MISMA instancia
        
        ESTRATEGIA: No mockear, usar implementación real para verificar singleton
        """
        # Primera llamada - crea singleton
        result1 = await ServiceFactory.get_redis_service()
        
        # Segunda llamada - debe retornar MISMA instancia
        result2 = await ServiceFactory.get_redis_service()
        
        # Verificar que es SINGLETON (misma instancia)
        assert result1 is result2
        assert ServiceFactory._redis_service is not None
    
    @pytest.mark.asyncio
    async def test_redis_service_uses_async_lock(self, mock_redis_service):
        """
        Verifica que se usa async lock para thread safety.
        """
        with patch('src.api.core.redis_service.get_redis_service',
                   new_callable=AsyncMock, return_value=mock_redis_service):
            
            await ServiceFactory.get_redis_service()
            
            # Verificar que lock fue creado
            assert ServiceFactory._redis_lock is not None
            assert isinstance(ServiceFactory._redis_lock, asyncio.Lock)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_three_failures(self):
        """
        Verifica que circuit breaker se abre después de 3 fallos.
        
        Given: ServiceFactory con Redis fallando
        When: Ocurren 3 fallos consecutivos
        Then: Circuit breaker se abre
        
        ESTRATEGIA: Simular fallos manualmente manipulando circuit breaker
        """
        # Simular 3 fallos directamente en el circuit breaker
        ServiceFactory._record_circuit_failure()
        ServiceFactory._record_circuit_failure()
        ServiceFactory._record_circuit_failure()
        
        # Verificar circuit breaker
        assert ServiceFactory._redis_circuit_breaker["failures"] >= 3
        assert ServiceFactory._redis_circuit_breaker["circuit_open"] is True
        
        # Verificar que _is_circuit_open retorna True
        assert ServiceFactory._is_circuit_open() is True
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_resets_on_success(self, mock_redis_service):
        """
        Verifica que circuit breaker se resetea en éxito.
        """
        # Simular un fallo primero
        ServiceFactory._redis_circuit_breaker["failures"] = 1
        ServiceFactory._redis_circuit_breaker["last_failure"] = time.time()
        
        with patch('src.api.core.redis_service.get_redis_service',
                   new_callable=AsyncMock, return_value=mock_redis_service):
            
            await ServiceFactory.get_redis_service()
            
            # Verificar reset
            assert ServiceFactory._redis_circuit_breaker["failures"] == 0
            assert ServiceFactory._redis_circuit_breaker["circuit_open"] is False
    
    @pytest.mark.asyncio
    async def test_redis_fallback_on_timeout(self, mock_redis_service):
        """
        Verifica fallback cuando hay timeout.
        """
        with patch('src.api.core.redis_service.get_redis_service',
                   side_effect=asyncio.TimeoutError("Connection timeout")):
            with patch.object(ServiceFactory, '_create_fallback_redis_service',
                             new_callable=AsyncMock, return_value=mock_redis_service):
                
                result = await ServiceFactory.get_redis_service()
                
                # Debe retornar fallback service
                assert result is not None


# ============================================================================
# TEST CLASS 3: RECOMMENDER SINGLETONS (FASE 1)
# ============================================================================

class TestRecommenderSingletons:
    """
    Tests de singletons de recommenders (TF-IDF, Retail, Hybrid).
    """
    
    @pytest.mark.asyncio
    async def test_get_tfidf_recommender_singleton(self, mock_tfidf_recommender, mock_settings):
        """
        Verifica singleton de TF-IDF recommender.
        
        Given: ServiceFactory sin TF-IDF
        When: Se llama get_tfidf_recommender()
        Then: Retorna singleton TFIDFRecommender
        """
        # ✅ CORRECTED: Patchear módulo origen
        with patch('src.api.core.config.get_settings', return_value=mock_settings):
            with patch('src.recommenders.tfidf_recommender.TFIDFRecommender',
                       return_value=mock_tfidf_recommender):
                
                result = await ServiceFactory.get_tfidf_recommender()
                
                assert result is mock_tfidf_recommender
                assert ServiceFactory._tfidf_recommender is not None
    
    @pytest.mark.asyncio
    async def test_get_retail_recommender_singleton(self, mock_retail_recommender, mock_settings):
        """
        Verifica singleton de Retail API recommender.
        """
        # ✅ CORRECTED: Patchear módulo origen
        with patch('src.api.core.config.get_settings', return_value=mock_settings):
            with patch('src.recommenders.retail_api.RetailAPIRecommender',
                       return_value=mock_retail_recommender):
                
                result = await ServiceFactory.get_retail_recommender()
                
                assert result is mock_retail_recommender
                assert ServiceFactory._retail_recommender is not None
    
    @pytest.mark.asyncio
    async def test_get_hybrid_recommender_auto_wiring(
        self,
        mock_tfidf_recommender,
        mock_retail_recommender,
        mock_product_cache,
        mock_settings
    ):
        """
        Verifica auto-wiring de Hybrid recommender.
        
        Given: ServiceFactory sin dependencies
        When: Se llama get_hybrid_recommender() sin params
        Then: Auto-fetch TF-IDF, Retail, y ProductCache
        """
        mock_hybrid = MagicMock()
        
        # ✅ CORRECTED: Patchear módulo origen
        with patch('src.api.core.config.get_settings', return_value=mock_settings):
            with patch.object(ServiceFactory, 'get_tfidf_recommender',
                             new_callable=AsyncMock, return_value=mock_tfidf_recommender):
                with patch.object(ServiceFactory, 'get_retail_recommender',
                                 new_callable=AsyncMock, return_value=mock_retail_recommender):
                    with patch.object(ServiceFactory, 'get_product_cache_singleton',
                                     new_callable=AsyncMock, return_value=mock_product_cache):
                        with patch('src.api.core.hybrid_recommender.HybridRecommender',
                                  return_value=mock_hybrid):
                            
                            result = await ServiceFactory.get_hybrid_recommender()
                            
                            # Verificar que llamó a las subfactories
                            ServiceFactory.get_tfidf_recommender.assert_called_once()
                            ServiceFactory.get_retail_recommender.assert_called_once()
                            ServiceFactory.get_product_cache_singleton.assert_called_once()
                            
                            assert result is mock_hybrid
    
    @pytest.mark.asyncio
    async def test_hybrid_recommender_with_manual_injection(self, mock_settings):
        """
        Verifica que Hybrid acepta dependencies manuales.
        """
        manual_tfidf = MagicMock()
        manual_retail = MagicMock()
        mock_hybrid = MagicMock()
        
        # ✅ CORRECTED: Patchear módulo origen
        with patch('src.api.core.config.get_settings', return_value=mock_settings):
            with patch('src.api.core.hybrid_recommender.HybridRecommender',
                       return_value=mock_hybrid):
                
                result = await ServiceFactory.get_hybrid_recommender(
                    content_recommender=manual_tfidf,
                    retail_recommender=manual_retail
                )
                
                # NO debe llamar a subfactories
                assert result is mock_hybrid


# ============================================================================
# TEST CLASS 4: CACHE SINGLETONS
# ============================================================================

class TestCacheSingletons:
    """
    Tests de singletons de cache (ProductCache, PersonalizationCache).
    """
    
    @pytest.mark.asyncio
    async def test_get_product_cache_singleton(self):
        """
        Verifica singleton de ProductCache.
        
        ESTRATEGIA: Verificar que dos llamadas retornan misma instancia (singleton real)
        """
        # Primera llamada - crea singleton
        result1 = await ServiceFactory.get_product_cache_singleton()
        
        # Segunda llamada - debe retornar MISMA instancia
        result2 = await ServiceFactory.get_product_cache_singleton()
        
        # Verificar singleton
        assert result1 is result2
        assert ServiceFactory._product_cache is not None
        assert ServiceFactory._product_cache is result1
    
    @pytest.mark.asyncio
    async def test_get_personalization_cache_enterprise(self, mock_redis_service):
        """
        Verifica singleton de PersonalizationCache con enterprise factory.
        """
        mock_pers_cache = AsyncMock()
        mock_diversity_cache = AsyncMock()
        
        with patch.object(ServiceFactory, 'get_redis_service',
                         new_callable=AsyncMock, return_value=mock_redis_service):
            with patch.object(ServiceFactory, 'get_product_cache_singleton',
                             new_callable=AsyncMock, return_value=None):
                # ✅ CORRECTED: Patchear módulo origen
                with patch('src.api.core.diversity_aware_cache.create_diversity_aware_cache',
                          new_callable=AsyncMock, return_value=mock_diversity_cache):
                    with patch('src.api.core.intelligent_personalization_cache.IntelligentPersonalizationCache',
                              return_value=mock_pers_cache):
                        
                        result = await ServiceFactory.get_personalization_cache()
                        
                        assert result is mock_pers_cache
                        assert ServiceFactory._personalization_cache is not None
    
    @pytest.mark.asyncio
    async def test_product_cache_uses_local_catalog(self):
        """
        Verifica que ProductCache recibe local_catalog.
        
        ESTRATEGIA: Mockear todas las dependencies y verificar call
        """
        mock_catalog = MagicMock()
        mock_catalog.product_data = [{"id": "1"}, {"id": "2"}]
        
        # Mockear RedisService
        mock_redis = AsyncMock()
        mock_redis.health_check = AsyncMock(return_value={"status": "healthy"})
        
        # Mockear Shopify client
        mock_shopify = MagicMock()
        
        # Patchear TODAS las dependencies
        with patch('src.api.core.redis_service.get_redis_service',
                   new_callable=AsyncMock, return_value=mock_redis):
            with patch('src.api.core.store.get_shopify_client',
                       return_value=mock_shopify):
                with patch('src.api.factories.service_factory.ProductCache') as MockProductCache:
                    mock_instance = AsyncMock()
                    mock_instance.start_background_tasks = AsyncMock()
                    MockProductCache.return_value = mock_instance
                    
                    # Crear ProductCache con local_catalog
                    result = await ServiceFactory.create_product_cache(local_catalog=mock_catalog)
                    
                    # Verificar que ProductCache fue llamado
                    assert MockProductCache.called
                    
                    # Verificar que local_catalog está en los kwargs
                    call_kwargs = MockProductCache.call_args[1]
                    assert 'local_catalog' in call_kwargs
                    assert call_kwargs['local_catalog'] is mock_catalog


# ============================================================================
# TEST CLASS 5: MCP DEPENDENCIES (FASE 3B)
# ============================================================================

class TestMCPDependencies:
    """
    Tests de dependencies MCP (Fase 3B).
    """
    
    @pytest.mark.asyncio
    async def test_get_mcp_client_singleton(self, mock_settings):
        """
        Verifica singleton de MCP Client.
        """
        mock_client = MagicMock()
        
        # ✅ CORRECTED: Patchear módulos origen
        with patch('src.api.core.config.get_settings', return_value=mock_settings):
            with patch('src.api.mcp.client.mcp_client_enhanced.MCPClientEnhanced',
                       return_value=mock_client):
                
                result = await ServiceFactory.get_mcp_client()
                
                assert result is mock_client
                assert ServiceFactory._mcp_client is not None
    
    @pytest.mark.asyncio
    async def test_get_market_context_manager(self, mock_redis_service, mock_settings):
        """
        Verifica singleton of Market Context Manager.
        """
        mock_manager = AsyncMock()
        mock_manager.initialize = AsyncMock()
        
        # ✅ CORRECTED: Patchear módulos origen
        with patch('src.api.core.config.get_settings', return_value=mock_settings):
            with patch.object(ServiceFactory, 'get_redis_service',
                             new_callable=AsyncMock, return_value=mock_redis_service):
                with patch('src.api.mcp.adapters.market_manager.MarketContextManager',
                          return_value=mock_manager):
                    
                    result = await ServiceFactory.get_market_context_manager()
                    
                    assert result is mock_manager
                    assert ServiceFactory._market_context_manager is not None
                    mock_manager.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_market_cache_service(self, mock_redis_service, mock_product_cache):
        """
        Verifica singleton de Market Cache Service.
        """
        mock_market_cache = MagicMock()
        
        with patch.object(ServiceFactory, 'get_redis_service',
                         new_callable=AsyncMock, return_value=mock_redis_service):
            with patch.object(ServiceFactory, 'get_product_cache_singleton',
                             new_callable=AsyncMock, return_value=mock_product_cache):
                # ✅ CORRECTED: Patchear módulo origen
                with patch('src.cache.market_aware.market_cache.MarketAwareProductCache',
                          return_value=mock_market_cache):
                    
                    result = await ServiceFactory.get_market_cache_service()
                    
                    assert result is mock_market_cache
                    assert ServiceFactory._market_cache_service is not None
    
    @pytest.mark.asyncio
    async def test_get_conversation_state_manager(self):
        """
        Verifica singleton de Conversation State Manager.
        
        ESTRATEGIA: Mockear redis_service Y la clase MCPConversationStateManager
        """
        mock_state_mgr = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.health_check = AsyncMock(return_value={"status": "healthy"})
        
        # Patchear AMBAS dependencies
        with patch('src.api.core.redis_service.get_redis_service',
                   new_callable=AsyncMock, return_value=mock_redis):
            with patch('src.api.mcp.conversation_state_manager.MCPConversationStateManager',
                      return_value=mock_state_mgr):
                
                result = await ServiceFactory.get_conversation_state_manager()
                
                assert result is mock_state_mgr
                assert ServiceFactory._conversation_state_manager is not None


# ============================================================================
# TEST CLASS 6: SHUTDOWN AND CLEANUP
# ============================================================================

class TestShutdownAndCleanup:
    """
    Tests de shutdown y cleanup.
    """
    
    @pytest.mark.asyncio
    async def test_shutdown_all_services_resets_singletons(self):
        """
        Verifica que shutdown resetea todos los singletons.
        
        Given: ServiceFactory con varios singletons activos
        When: Se llama shutdown_all_services()
        Then: Todos los singletons se resetean a None
        """
        # Simular singletons activos
        ServiceFactory._redis_service = MagicMock()
        ServiceFactory._product_cache = MagicMock()
        ServiceFactory._tfidf_recommender = MagicMock()
        ServiceFactory._hybrid_recommender = MagicMock()
        
        await ServiceFactory.shutdown_all_services()
        
        # Verificar reset
        assert ServiceFactory._redis_service is None
        assert ServiceFactory._product_cache is None
        assert ServiceFactory._tfidf_recommender is None
        assert ServiceFactory._hybrid_recommender is None
    
    @pytest.mark.asyncio
    async def test_shutdown_resets_locks(self):
        """
        Verifica que shutdown resetea los locks.
        """
        # Simular locks activos
        ServiceFactory._redis_lock = asyncio.Lock()
        ServiceFactory._tfidf_lock = asyncio.Lock()
        
        await ServiceFactory.shutdown_all_services()
        
        # Verificar reset
        assert ServiceFactory._redis_lock is None
        assert ServiceFactory._tfidf_lock is None


# ============================================================================
# RUNNER CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    """
    Ejecutar tests directamente:
    
    pytest tests/unit/test_service_factory.py -v
    pytest tests/unit/test_service_factory.py -v --cov=src.api.factories.service_factory
    """
    pytest.main([__file__, "-v", "--tb=short"])