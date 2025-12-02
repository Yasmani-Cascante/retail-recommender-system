# tests/integration/test_mcp_router_di_migration.py
"""
Test Suite CORREGIDO para validar migración FastAPI DI de mcp_router.py

CAMBIOS APLICADOS:
1. ✅ Override de get_current_user para bypass authentication (FIX 403 errors)
2. ✅ Corrección de búsqueda de endpoint por path (handles router prefix)
3. ✅ Mejor manejo de errores con mensajes descriptivos
4. ✅ Validación de response code antes de acceder a JSON

RESULTADOS ESPERADOS: 11/11 tests PASSING

Author: Senior Architecture Team
Date: 27 Noviembre 2025
Version: 1.1 - FIXED
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from typing import Dict, Any, List

# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def mock_mcp_client():
    """Mock MCPClient para testing"""
    client = AsyncMock()
    client.send_message = AsyncMock(return_value={
        "response": "Test response",
        "recommendations": []
    })
    return client

@pytest.fixture
def mock_market_manager():
    """Mock MarketContextManager para testing"""
    manager = AsyncMock()
    manager.get_market_config = AsyncMock(return_value={
        "market_id": "US",
        "currency": "USD",
        "language": "en"
    })
    manager.get_supported_markets = AsyncMock(return_value={
        "US": {"name": "United States", "currency": "USD"}
    })
    return manager

@pytest.fixture
def mock_market_cache():
    """Mock MarketAwareProductCache para testing"""
    cache = AsyncMock()
    cache.get_product = AsyncMock(return_value={
        "id": "test_product",
        "title": "Test Product",
        "price": 99.99
    })
    cache.get_cache_stats = AsyncMock(return_value={
        "hit_rate": 0.85,
        "total_requests": 100
    })
    return cache

@pytest.fixture
def mock_mcp_recommender():
    """Mock MCPRecommender para testing"""
    recommender = AsyncMock()
    recommender.get_recommendations = AsyncMock(return_value={
        "recommendations": [
            {
                "id": "rec1",
                "title": "Recommendation 1",
                "score": 0.95
            }
        ],
        "ai_response": "Here are my recommendations",
        "metadata": {}
    })
    return recommender

@pytest.fixture
def app_with_di_overrides(
    mock_mcp_client,
    mock_market_manager,
    mock_market_cache,
    mock_mcp_recommender
):
    """FastAPI app con dependency overrides para testing"""
    from src.api.main_unified_redis import app
    from src.api.dependencies import (
        get_mcp_client,
        get_market_context_manager,
        get_market_cache_service,
        get_mcp_recommender
    )
    from src.api.security_auth import get_current_user
    
    # ✅ FIX: Mock functions ASYNC (para que FastAPI las awaitee correctamente)
    async def mock_get_mcp_client():
        """Async mock provider for MCP Client"""
        return mock_mcp_client
    
    async def mock_get_market_manager():
        """Async mock provider for Market Manager"""
        return mock_market_manager
    
    async def mock_get_market_cache():
        """Async mock provider for Market Cache"""
        return mock_market_cache
    
    async def mock_get_mcp_recommender():
        """Async mock provider for MCP Recommender"""
        return mock_mcp_recommender
    
    def mock_get_current_user():
        """Sync mock provider for Current User (auth bypass)"""
        return "test_user"
    
    # Override dependencies
    app.dependency_overrides[get_mcp_client] = mock_get_mcp_client  # ✅ Async
    app.dependency_overrides[get_market_context_manager] = mock_get_market_manager  # ✅ Async
    app.dependency_overrides[get_market_cache_service] = mock_get_market_cache  # ✅ Async
    app.dependency_overrides[get_mcp_recommender] = mock_get_mcp_recommender  # ✅ Async
    app.dependency_overrides[get_current_user] = mock_get_current_user  # Sync OK
    
    yield app
    
    # Cleanup
    app.dependency_overrides.clear()

@pytest.fixture
def client(app_with_di_overrides):
    """TestClient con DI configurado"""
    return TestClient(app_with_di_overrides)

# ============================================================================
# TESTS DE DEPENDENCY INJECTION
# ============================================================================

class TestMCPRouterDependencyInjection:
    """Tests para validar que mcp_router.py usa DI correctamente"""
    
    def test_conversation_endpoint_signature_has_all_dependencies(self):
        """Verificar que /conversation tiene todas las dependencies en signature"""
        from src.api.routers import mcp_router
        import inspect
        
        # ✅ FIX: Get endpoint function con búsqueda más robusta
        endpoint_func = None
        for route in mcp_router.router.routes:
            if hasattr(route, 'endpoint') and (
                route.path == "/conversation" or 
                route.path.endswith("/conversation") or
                "/conversation" in route.path
            ):
                endpoint_func = route.endpoint
                break
        
        # ✅ FIX: Mensaje de error más descriptivo
        available_routes = [r.path for r in mcp_router.router.routes if hasattr(r, 'path')]
        assert endpoint_func is not None, f"/conversation endpoint not found. Available routes: {available_routes}"
        
        # Check signature
        sig = inspect.signature(endpoint_func)
        params = sig.parameters
        
        # Verify all DI parameters present
        assert 'mcp_client' in params, "mcp_client dependency missing"
        assert 'market_manager' in params, "market_manager dependency missing"
        assert 'market_cache' in params, "market_cache dependency missing"
        assert 'mcp_recommender' in params, "mcp_recommender dependency missing"
        
    def test_conversation_endpoint_does_not_call_getters(self, client):
        """Verificar que endpoint NO usa getters directos internamente"""
        
        with patch('src.api.routers.mcp_router.get_mcp_client') as mock_getter:
            # Si el endpoint está migrado correctamente, este getter NO debe llamarse
            response = client.post("/v1/mcp/conversation", json={
                "query": "test query",
                "market_id": "US",
                "user_id": "test_user"
            })
            
            # ✅ FIX: Verificar response code primero
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
            
            # Verificar que getter NO fue llamado (usa DI en su lugar)
            assert not mock_getter.called, "Endpoint still using direct getter instead of DI"
    
    def test_conversation_uses_injected_dependencies(self,client):
        """Verificar que endpoint funciona correctamente con DI"""
        
        response = client.post("/v1/mcp/conversation", json={
            "query": "test query",
            "market_id": "US"
        })
        
        # ✅ FIX: Mensaje de error más descriptivo
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        
        data = response.json()

    # ✅ Verificar estructura completa (indica que DI funcionó)
        assert "answer" in data, "Missing 'answer' field"
        assert "recommendations" in data, "Missing 'recommendations' field"
        assert "session_metadata" in data, "Missing 'session_metadata' field"
        assert "metadata" in data, "Missing 'metadata' field"

# ============================================================================
# TESTS FUNCIONALES
# ============================================================================

class TestMCPRouterFunctionality:
    """Tests para validar funcionalidad después de migración"""
    
    def test_conversation_endpoint_basic_flow(self, client):
        """Test flujo básico de conversación"""
        
        response = client.post("/v1/mcp/conversation", json={
            "query": "recommend laptops",
            "market_id": "US",
            "user_id": "test_user",
            "n_recommendations": 5
        })
        
        # ✅ FIX: Mensaje de error más descriptivo
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        
        # Verify response structure
        assert "answer" in data, "Missing 'answer' field"
        assert "recommendations" in data, "Missing 'recommendations' field"
        assert "session_metadata" in data, "Missing 'session_metadata' field"
        assert "metadata" in data, "Missing 'metadata' field"
        assert "session_id" in data, "Missing 'session_id' field"
        
    def test_conversation_endpoint_with_session(self, client):
        """Test conversación con session_id existente"""
        
        # Primera conversación
        response1 = client.post("/v1/mcp/conversation", json={
            "query": "show me laptops",
            "market_id": "US"
        })
        
        # ✅ FIX: Validar response primero
        assert response1.status_code == 200, f"First request failed: {response1.status_code}: {response1.json()}"
        
        data1 = response1.json()
        assert "session_id" in data1, f"Missing session_id in first response: {data1.keys()}"
        
        session_id = data1["session_id"]
        
        # Segunda conversación con mismo session
        response2 = client.post("/v1/mcp/conversation", json={
            "query": "cheaper options",
            "session_id": session_id,
            "market_id": "US"
        })
        
        assert response2.status_code == 200, f"Second request failed: {response2.status_code}"
        assert response2.json()["session_id"] == session_id
        
    def test_markets_endpoint(self, client):
        """Test endpoint de mercados soportados"""
        
        response = client.get("/v1/mcp/markets")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        
        assert "markets" in data
        assert "default_market" in data
        assert "total" in data
        assert isinstance(data["markets"], list)
        
    def test_recommendations_by_product(self, client):
        """Test endpoint de recomendaciones por producto"""
        
        response = client.get(
            "/v1/mcp/recommendations/test_product",
            params={"market_id": "US", "n": 5}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        
        assert "product_id" in data
        assert "recommendations" in data
        assert "metadata" in data

# ============================================================================
# TESTS DE PERFORMANCE
# ============================================================================

class TestMCPRouterPerformance:
    """Tests para validar que DI no degrada performance"""
    
    @pytest.mark.asyncio
    async def test_di_overhead_is_minimal(self, app_with_di_overrides):
        """Verificar que overhead de DI es mínimo (<5ms)"""
        import time
        
        # Simulate 100 requests to measure DI overhead
        times = []
        
        for _ in range(100):
            start = time.perf_counter()
            
            # Dependency resolution simulation
            from src.api.dependencies import (
                get_mcp_client,
                get_market_context_manager,
                get_market_cache_service,
                get_mcp_recommender
            )
            
            # FastAPI caches these, so should be fast
            _ = await get_mcp_client()
            _ = await get_market_context_manager()
            _ = await get_market_cache_service()
            _ = await get_mcp_recommender()
            
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        
        # DI overhead should be < 5ms average
        assert avg_time < 5.0, f"DI overhead too high: {avg_time:.2f}ms"
        
    def test_response_time_maintained(self, client):
        """Verificar que response time se mantiene < 2s"""
        import time
        
        start = time.perf_counter()
        
        response = client.post("/v1/mcp/conversation", json={
            "query": "test",
            "market_id": "US"
        })
        
        elapsed = time.perf_counter() - start
        
        assert response.status_code == 200, f"Request failed: {response.status_code}"
        assert elapsed < 2.0, f"Response time too slow: {elapsed:.2f}s"

# ============================================================================
# TESTS DE REGRESIÓN
# ============================================================================

class TestMCPRouterRegression:
    """Tests para detectar breaking changes"""
    
    def test_api_contract_unchanged(self, client):
        """Verificar que contrato de API no cambió"""
        
        # Test request format (no cambios)
        valid_request = {
            "query": "test",
            "user_id": "test",
            "session_id": "test",
            "market_id": "US",
            "language": "en",
            "product_id": None,
            "n_recommendations": 5
        }
        
        response = client.post("/v1/mcp/conversation", json=valid_request)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        
    def test_response_structure_unchanged(self, client):
        """Verificar que estructura de respuesta no cambió"""
        
        response = client.post("/v1/mcp/conversation", json={
            "query": "test",
            "market_id": "US"
        })
        
        # ✅ FIX: Validar response code primero
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        
        data = response.json()
        
        # Required fields (no deben cambiar)
        required_fields = [
            "answer",
            "recommendations",
            "session_metadata",
            "intent_analysis",
            "market_context",
            "personalization_metadata",
            "metadata",
            "session_id",
            "took_ms"
        ]
        
        for field in required_fields:
            assert field in data, f"Required field '{field}' missing in response. Available: {list(data.keys())}"

# ============================================================================
# TESTS DE ERROR HANDLING
# ============================================================================

class TestMCPRouterErrorHandling:
    """Tests para validar manejo robusto de errores"""
    
    def test_handles_missing_dependencies_gracefully(self, client):
        """Verificar que endpoint maneja dependencies faltantes"""
        
        # Override con None para simular fallo
        from src.api.main_unified_redis import app
        from src.api.dependencies import get_mcp_recommender
        
        app.dependency_overrides[get_mcp_recommender] = lambda: None
        
        response = client.post("/v1/mcp/conversation", json={
            "query": "test",
            "market_id": "US"
        })
        
        # Debe responder (con fallback) no crashear
        assert response.status_code in [200, 503], f"Unexpected status: {response.status_code}"
        
        # Cleanup
        app.dependency_overrides.clear()
        
    def test_invalid_market_id(self, client):
        """Test con market_id inválido"""
        
        response = client.post("/v1/mcp/conversation", json={
            "query": "test",
            "market_id": "INVALID_MARKET"
        })
        
        # Debe manejar gracefully
        assert response.status_code in [200, 400, 422], f"Unexpected status: {response.status_code}"

# ============================================================================
# RUNNER CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])