"""
Tests para la implementación de la Arquitectura MCP corregida (Opción A)
========================================================================

Tests que validan que la implementación correcta:
1. HybridRecommender.get_recommendations() → recomendaciones base  
2. MCPPersonalizationEngine.generate_personalized_response() → personalización
3. MarketAdapter.adapt_product() → adaptación de mercado

Resuelve el error: 'MCPPersonalizationEngine' object has no attribute 'get_recommendations'

Author: Senior Architecture Team
Version: 1.0.0 - Option A Implementation Tests
Date: 2025-08-30
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, List, Any

# Imports para testing
try:
    from src.api.core.mcp_conversation_handler import (
        get_mcp_conversation_recommendations,
        get_mcp_market_recommendations,
        validate_mcp_dependencies,
        get_architecture_info
    )
    HANDLER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Warning: Handler not available for testing: {e}")
    HANDLER_AVAILABLE = False


class TestMCPArchitectureFix:
    """Test suite para validar la implementación correcta de la arquitectura MCP"""
    
    @pytest.mark.skipif(not HANDLER_AVAILABLE, reason="MCP handler not available")
    @pytest.mark.asyncio
    async def test_mcp_conversation_with_full_flow(self):
        """
        ✅ Test completo del flujo MCP con todos los componentes
        Valida: HybridRecommender → MCPPersonalizationEngine → MarketAdapter
        """
        # Mock dependencies
        mock_hybrid_rec = AsyncMock(return_value=[
            {"id": "123", "title": "Test Product", "price": 10.99, "score": 0.8}
        ])
        
        mock_mcp_engine = MagicMock()
        mock_mcp_engine.generate_personalized_response = AsyncMock(return_value={
            "personalized_recommendations": [
                {"id": "123", "title": "Personalized Product", "price": 10.99, "score": 0.9}
            ],
            "personalized_response": "Here's a personalized recommendation for you!",
            "personalization_metadata": {
                "strategy_used": "hybrid",
                "personalization_score": 0.85
            }
        })
        
        with patch('src.api.main_unified_redis') as mock_main:
            mock_main.hybrid_recommender = MagicMock()
            mock_main.hybrid_recommender.get_recommendations = mock_hybrid_rec
            
            with patch('src.api.mcp.engines.mcp_personalization_engine.create_mcp_personalization_engine', 
                      return_value=mock_mcp_engine):
                
                result = await get_mcp_conversation_recommendations(
                    validated_user_id="test_user",
                    validated_product_id="123",
                    conversation_query="show me recommendations",
                    market_id="US",
                    n_recommendations=5
                )
                
                # Validaciones de la respuesta
                assert "recommendations" in result
                assert "ai_response" in result
                assert "metadata" in result
                
                # Validar que se llamó a los componentes correctos
                mock_hybrid_rec.assert_called_once()
                mock_mcp_engine.generate_personalized_response.assert_called_once()
                
                # Validar metadatos de la implementación
                assert result["metadata"]["base_recommender_available"] == True
                assert result["metadata"]["mcp_engine_available"] == True
                assert result["metadata"]["personalization_applied"] == True
                
                print("✅ Test completo de flujo MCP - PASSED")

    @pytest.mark.skipif(not HANDLER_AVAILABLE, reason="MCP handler not available")
    @pytest.mark.asyncio 
    async def test_mcp_conversation_fallback_scenarios(self):
        """
        ✅ Test de escenarios de fallback
        Valida que el sistema maneja gracefully los componentes faltantes
        """
        # Test con HybridRecommender no disponible
        with patch('src.api.main_unified_redis') as mock_main:
            mock_main.hybrid_recommender = None
            
            result = await get_mcp_conversation_recommendations(
                validated_user_id="test_user",
                validated_product_id=None,
                conversation_query="test query",
                market_id="US",
                n_recommendations=5
            )
            
            assert result["metadata"]["base_recommender_available"] == False
            assert "error" not in result  # Debe manejar gracefully
            assert "recommendations" in result  # Lista vacía está OK
            
            print("✅ Test fallback HybridRecommender - PASSED")

    @pytest.mark.skipif(not HANDLER_AVAILABLE, reason="MCP handler not available")
    @pytest.mark.asyncio
    async def test_mcp_personalization_engine_correct_method(self):
        """
        ✅ Test crítico: Verifica que se llama al método correcto
        NO debe llamar a get_recommendations() sino a generate_personalized_response()
        """
        mock_engine = MagicMock()
        mock_engine.generate_personalized_response = AsyncMock(return_value={
            "personalized_recommendations": [],
            "personalized_response": "Personalized response",
            "personalization_metadata": {"strategy_used": "test"}
        })
        
        # Simular que get_recommendations() no existe (el error original)
        delattr(mock_engine, 'get_recommendations') if hasattr(mock_engine, 'get_recommendations') else None
        
        mock_hybrid_rec = AsyncMock(return_value=[{"id": "test", "title": "Test"}])
        
        with patch('src.api.main_unified_redis.hybrid_recommender') as mock_hybrid:
            mock_hybrid.get_recommendations = mock_hybrid_rec
            
            with patch('src.api.mcp.engines.mcp_personalization_engine.create_mcp_personalization_engine',
                      return_value=mock_engine):
                
                # Este test debe PASAR sin errores de AttributeError
                result = await get_mcp_conversation_recommendations(
                    validated_user_id="test_user",
                    validated_product_id=None,
                    conversation_query="test",
                    market_id="US",
                    n_recommendations=3
                )
                
                # Validar que NO se intentó llamar get_recommendations()
                assert not hasattr(mock_engine, 'get_recommendations')
                
                # Validar que SÍ se llamó generate_personalized_response()
                mock_engine.generate_personalized_response.assert_called_once()
                
                # Validar respuesta exitosa
                assert result["metadata"]["personalization_applied"] == True
                
                print("✅ Test método correcto MCPPersonalizationEngine - PASSED")

    @pytest.mark.skipif(not HANDLER_AVAILABLE, reason="MCP handler not available") 
    @pytest.mark.asyncio
    async def test_market_recommendations_endpoint_compatibility(self):
        """
        ✅ Test del endpoint de market recommendations 
        Valida compatibilidad con la arquitectura corregida
        """
        mock_recommendations = [
            {"id": "market_prod_1", "title": "Market Product", "price": 15.99}
        ]
        
        # Mock de get_mcp_conversation_recommendations
        async def mock_get_mcp_conv_recs(*args, **kwargs):
            return {
                "recommendations": mock_recommendations,
                "ai_response": "Market-adapted recommendations",
                "metadata": {
                    "market_adaptation_applied": True,
                    "processing_time_ms": 500.0
                }
            }
        
        with patch('src.api.core.mcp_conversation_handler.get_mcp_conversation_recommendations',
                  side_effect=mock_get_mcp_conv_recs):
            
            result = await get_mcp_market_recommendations(
                product_id="123",
                market_id="ES",
                user_id="test_user",
                n_recommendations=5
            )
            
            assert "recommendations" in result
            assert result["recommendations"] == mock_recommendations
            assert "ai_response" in result
            
            print("✅ Test market recommendations endpoint - PASSED")

    def test_validate_mcp_dependencies(self):
        """
        ✅ Test de validación de dependencias MCP
        """
        if not HANDLER_AVAILABLE:
            pytest.skip("Handler not available")
            
        result = validate_mcp_dependencies()
        
        assert "dependencies" in result
        assert "overall_health" in result
        assert "critical_missing" in result
        assert "timestamp" in result
        
        # Validar estructura de dependencies
        deps = result["dependencies"]
        expected_deps = [
            "hybrid_recommender",
            "mcp_context_classes", 
            "mcp_personalization_engine",
            "market_adapter",
            "anthropic_api_key"
        ]
        
        for dep in expected_deps:
            assert dep in deps
            
        print("✅ Test validación de dependencias - PASSED")

    def test_get_architecture_info(self):
        """
        ✅ Test de información arquitectónica
        """
        if not HANDLER_AVAILABLE:
            pytest.skip("Handler not available")
            
        result = get_architecture_info()
        
        assert "architecture_version" in result
        assert result["architecture_version"] == "option_a_implemented"
        assert "resolved_issue" in result
        assert "MCPPersonalizationEngine get_recommendations()" in result["resolved_issue"]
        
        # Validar estructura de componentes
        components = result["components"]
        assert "base_recommendations" in components
        assert "personalization" in components
        assert "market_adaptation" in components
        
        # Validar que especifica el método correcto
        assert "generate_personalized_response" in components["personalization"]
        
        print("✅ Test información arquitectónica - PASSED")

    @pytest.mark.skipif(not HANDLER_AVAILABLE, reason="MCP handler not available")
    @pytest.mark.asyncio
    async def test_timeout_and_error_handling(self):
        """
        ✅ Test de manejo de timeouts y errores
        """
        # Test timeout en HybridRecommender
        mock_hybrid_timeout = AsyncMock(side_effect=asyncio.TimeoutError("Timeout test"))
        
        with patch('src.api.main_unified_redis.hybrid_recommender') as mock_hybrid:
            mock_hybrid.get_recommendations = mock_hybrid_timeout
            
            result = await get_mcp_conversation_recommendations(
                validated_user_id="test_user",
                validated_product_id=None,
                conversation_query="timeout test",
                market_id="US",
                n_recommendations=5
            )
            
            # Debe manejar el timeout gracefully
            assert "recommendations" in result
            assert result["metadata"]["base_recommender_available"] == False
            assert "error" not in result  # No debe propagar el error
            
        print("✅ Test timeout y error handling - PASSED")

    @pytest.mark.skipif(not HANDLER_AVAILABLE, reason="MCP handler not available")
    @pytest.mark.asyncio
    async def test_performance_benchmarks(self):
        """
        ✅ Test de performance benchmarks
        Valida que la implementación cumple con targets de performance
        """
        # Mock rápido para base recommendations
        mock_hybrid_rec = AsyncMock(return_value=[
            {"id": f"perf_test_{i}", "title": f"Product {i}", "price": 10.0}
            for i in range(5)
        ])
        
        start_time = time.time()
        
        with patch('src.api.main_unified_redis.hybrid_recommender') as mock_hybrid:
            mock_hybrid.get_recommendations = mock_hybrid_rec
            
            result = await get_mcp_conversation_recommendations(
                validated_user_id="perf_test_user",
                validated_product_id=None,
                conversation_query="performance test",
                market_id="US",
                n_recommendations=5
            )
            
        total_time = (time.time() - start_time) * 1000  # ms
        
        # Validar targets de performance
        assert total_time < 12000, f"Performance target missed: {total_time}ms > 12000ms"
        assert result["metadata"]["processing_time_ms"] > 0
        
        print(f"✅ Test performance benchmarks - PASSED ({total_time:.2f}ms)")


class TestMCPRouterEndpoints:
    """Test suite para validar los nuevos endpoints en mcp_router.py"""
    
    def test_new_endpoints_added(self):
        """
        ✅ Test que valida que los nuevos endpoints fueron añadidos
        """
        # Importar el router para validar que tiene los endpoints
        try:
            from src.api.routers.mcp_router import router
            
            # Obtener todas las rutas del router
            routes = [route.path for route in router.routes]
            
            # Validar que los nuevos endpoints existen
            expected_endpoints = [
                "/conversation-fixed",
                "/recommendations-fixed/{product_id}",
                "/architecture-status"
            ]
            
            for endpoint in expected_endpoints:
                # Verificar que alguna ruta contiene el endpoint
                found = any(endpoint.replace("/{product_id}", "") in route for route in routes)
                assert found, f"Endpoint {endpoint} not found in router"
                
            print("✅ Test nuevos endpoints añadidos - PASSED")
            
        except ImportError as e:
            pytest.skip(f"Router not available for testing: {e}")


# Fixture para testing
@pytest.fixture
async def mock_mcp_components():
    """Fixture que proporciona componentes MCP mockeados para testing"""
    mock_hybrid = MagicMock()
    mock_hybrid.get_recommendations = AsyncMock(return_value=[
        {"id": "fixture_123", "title": "Fixture Product", "price": 20.99}
    ])
    
    mock_engine = MagicMock()  
    mock_engine.generate_personalized_response = AsyncMock(return_value={
        "personalized_recommendations": [
            {"id": "fixture_123", "title": "Fixture Personalized", "price": 20.99}
        ],
        "personalized_response": "Fixture personalized response",
        "personalization_metadata": {"strategy_used": "fixture_hybrid"}
    })
    
    return {
        "hybrid_recommender": mock_hybrid,
        "mcp_engine": mock_engine
    }


def run_architecture_tests():
    """
    Función helper para ejecutar los tests desde línea de comando
    """
    if not HANDLER_AVAILABLE:
        print("❌ Cannot run tests: MCP conversation handler not available")
        return False
        
    import subprocess
    import sys
    
    try:
        # Ejecutar tests específicos
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            __file__,
            "-v", 
            "--tb=short",
            "-k", "TestMCPArchitectureFix"
        ], capture_output=True, text=True)
        
        print("=== TEST RESULTS ===")
        print(result.stdout)
        if result.stderr:
            print("=== STDERR ===")
            print(result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


if __name__ == "__main__":
    print("🧪 Running MCP Architecture Fix Tests...")
    success = run_architecture_tests()
    exit(0 if success else 1)
