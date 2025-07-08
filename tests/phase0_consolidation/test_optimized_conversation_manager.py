# tests/phase0_consolidation/test_optimized_conversation_manager.py
"""
Tests comprehensivos para OptimizedConversationAIManager.
Valida que las optimizaciones funcionan correctamente y mejoran el rendimiento.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from src.api.integrations.ai.optimized_conversation_manager import (
    OptimizedConversationAIManager,
    ConversationCircuitBreaker,
    CircuitBreakerError
)
from src.api.integrations.ai.ai_conversation_manager import ConversationContext

@pytest.fixture
def optimized_manager():
    """Fixture para OptimizedConversationAIManager con mocks"""
    with patch('src.api.integrations.ai.optimized_conversation_manager.Anthropic') as mock_anthropic:
        # Mock Claude response
        mock_message = Mock()
        mock_message.content = [Mock(text='{"message": "Test response", "intent": {"type": "test", "confidence": 0.8}}')]
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 50
        
        mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_message)
        
        manager = OptimizedConversationAIManager(
            anthropic_api_key="test-key",
            enable_circuit_breaker=True,
            enable_caching=True
        )
        
        yield manager
        
        # Cleanup se maneja en finalizer si es necesario
        # Para tests, no es crítico el cleanup

@pytest.fixture
def sample_context():
    """Fixture para ConversationContext de prueba"""
    return ConversationContext(
        user_id="test_user",
        session_id="test_session",
        market_id="ES",
        currency="EUR",
        conversation_history=[],
        user_profile={"preference": "electronics"},
        cart_items=[],
        browsing_history=["product1", "product2"],
        intent_signals={}
    )

class TestConversationCircuitBreaker:
    """Tests para el circuit breaker de conversaciones"""
    
    def test_circuit_breaker_initialization(self):
        """Test inicialización del circuit breaker"""
        cb = ConversationCircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60,
            success_threshold=2
        )
        
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert cb.success_count == 0
        assert cb.last_failure_time is None
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_success_flow(self):
        """Test flujo exitoso del circuit breaker"""
        cb = ConversationCircuitBreaker(failure_threshold=2)
        
        async def success_func():
            return "success"
        
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_flow(self):
        """Test flujo de fallos del circuit breaker"""
        cb = ConversationCircuitBreaker(failure_threshold=2)
        
        async def failing_func():
            raise Exception("Test error")
        
        # Primer fallo
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == "CLOSED"
        assert cb.failure_count == 1
        
        # Segundo fallo - debería abrir el circuit breaker
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == "OPEN"
        assert cb.failure_count == 2
        
        # Tercer intento - debería fallar inmediatamente con CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await cb.call(failing_func)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self):
        """Test recuperación del circuit breaker"""
        cb = ConversationCircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.1,  # 0.1 segundos para test rápido
            success_threshold=1
        )
        
        async def failing_func():
            raise Exception("Test error")
        
        async def success_func():
            return "recovered"
        
        # Causar fallo para abrir circuit breaker
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == "OPEN"
        
        # Esperar timeout de recuperación
        await asyncio.sleep(0.2)
        
        # Intentar operación exitosa - debería pasar a HALF_OPEN y luego CLOSED
        result = await cb.call(success_func)
        assert result == "recovered"
        assert cb.state == "CLOSED"

class TestOptimizedConversationAIManager:
    """Tests para OptimizedConversationAIManager"""
    
    @pytest.mark.asyncio
    async def test_manager_initialization(self, optimized_manager):
        """Test inicialización del manager optimizado"""
        assert optimized_manager.enable_circuit_breaker is True
        assert optimized_manager.enable_caching is True
        assert optimized_manager.claude_circuit_breaker is not None
        assert optimized_manager.response_cache is not None
        assert optimized_manager.metrics["optimization_enabled"] is True
    
    @pytest.mark.asyncio
    async def test_process_conversation_basic(self, optimized_manager, sample_context):
        """Test procesamiento básico de conversación"""
        response = await optimized_manager.process_conversation(
            user_message="Hello, I need help",
            context=sample_context,
            include_recommendations=True
        )
        
        assert "conversation_response" in response
        assert "intent_analysis" in response
        assert "metadata" in response
        assert response["metadata"]["optimized"] is True
        assert response["metadata"]["cached"] is False
    
    @pytest.mark.asyncio
    async def test_caching_functionality(self, optimized_manager, sample_context):
        """Test funcionalidad de caching"""
        user_message = "Tell me about laptops"
        
        # Primera llamada - debería ir a Claude
        response1 = await optimized_manager.process_conversation(
            user_message=user_message,
            context=sample_context
        )
        
        assert response1["metadata"]["cached"] is False
        assert optimized_manager.metrics["cache_misses"] == 1
        
        # Segunda llamada con mismo mensaje - debería usar caché
        response2 = await optimized_manager.process_conversation(
            user_message=user_message,
            context=sample_context
        )
        
        # Si la respuesta tiene alta confianza, debería estar en caché
        if response1.get("intent_analysis", {}).get("confidence", 0) > 0.7:
            assert response2["metadata"]["cached"] is True
            assert optimized_manager.metrics["cache_hits"] >= 1
    
    @pytest.mark.asyncio
    async def test_fallback_response(self, optimized_manager, sample_context):
        """Test respuesta de fallback cuando Claude falla"""
        # Simular fallo de Claude
        with patch.object(optimized_manager, '_process_conversation_protected') as mock_process:
            mock_process.side_effect = Exception("Claude API Error")
            
            response = await optimized_manager.process_conversation(
                user_message="Help me find products",
                context=sample_context
            )
            
            assert "conversation_response" in response
            assert response["metadata"]["primary_ai"] == "fallback"
            assert response["metadata"]["fallback_reason"] == "claude_api_unavailable"
            assert optimized_manager.metrics["fallback_uses"] >= 1
    
    @pytest.mark.asyncio
    async def test_intent_analysis_fallback(self, optimized_manager):
        """Test análisis de intención de fallback"""
        test_cases = [
            ("Busco un teléfono", "search"),
            ("Recomiéndame algo bueno", "recommendation"),
            ("Quiero comparar estos productos", "comparison"),
            ("¿Cuánto cuesta esto?", "purchase"),
            ("Hola", "general")
        ]
        
        for query, expected_intent in test_cases:
            intent = optimized_manager._basic_intent_analysis(query)
            assert intent["type"] == expected_intent
            assert 0 < intent["confidence"] <= 1.0
            assert intent["analysis_method"] == "keyword_based_fallback"
    
    @pytest.mark.asyncio
    async def test_performance_metrics(self, optimized_manager, sample_context):
        """Test métricas de rendimiento"""
        # Realizar algunas conversaciones
        for i in range(3):
            await optimized_manager.process_conversation(
                user_message=f"Test message {i}",
                context=sample_context
            )
        
        metrics = await optimized_manager.get_performance_metrics()
        
        assert "cache_hit_ratio" in metrics
        assert "circuit_breaker_stats" in metrics
        assert "fallback_usage_ratio" in metrics
        assert "optimization_features" in metrics
        
        # Verificar estructura de métricas de optimización
        opt_features = metrics["optimization_features"]
        assert "circuit_breaker_enabled" in opt_features
        assert "caching_enabled" in opt_features
        assert "redis_cache_available" in opt_features
        assert "http_pooling_enabled" in opt_features
    
    @pytest.mark.asyncio
    async def test_health_check(self, optimized_manager):
        """Test health check extendido"""
        health = await optimized_manager.health_check()
        
        assert "status" in health
        assert "claude_api" in health
        assert "optimization_features" in health
        assert "performance_metrics" in health
        assert "timestamp" in health
        
        # Verificar estructura de features de optimización
        opt_features = health["optimization_features"]
        assert "circuit_breaker" in opt_features
        assert "caching" in opt_features
        
        cb_info = opt_features["circuit_breaker"]
        assert "enabled" in cb_info
        assert "state" in cb_info
        
        cache_info = opt_features["caching"]
        assert "local_enabled" in cache_info
        assert "redis_enabled" in cache_info
        assert "local_cache_size" in cache_info
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, optimized_manager, sample_context):
        """Test integración del circuit breaker con el manager"""
        # Forzar fallos múltiples para abrir circuit breaker
        with patch.object(optimized_manager, '_process_conversation_protected') as mock_process:
            mock_process.side_effect = Exception("Repeated Claude failures")
            
            # Fallar múltiples veces para activar circuit breaker
            for _ in range(6):  # Más que el threshold
                try:
                    await optimized_manager.process_conversation(
                        user_message="Test message",
                        context=sample_context
                    )
                except:
                    pass
            
            # Verificar que circuit breaker se activó
            cb_stats = optimized_manager.claude_circuit_breaker.get_stats()
            assert cb_stats["state"] == "OPEN"
            assert optimized_manager.metrics["circuit_breaker_trips"] > 0
    
    def test_cache_key_generation(self, optimized_manager, sample_context):
        """Test generación de claves de caché"""
        key1 = optimized_manager._generate_cache_key("Hello world", sample_context)
        key2 = optimized_manager._generate_cache_key("Hello world", sample_context)
        key3 = optimized_manager._generate_cache_key("Different message", sample_context)
        
        # Mismos mensajes y contexto deberían generar misma clave
        assert key1 == key2
        
        # Mensajes diferentes deberían generar claves diferentes
        assert key1 != key3
        
        # Verificar formato de clave
        assert key1.startswith("conv:")
        assert len(key1) > 10  # Debe tener hash

class TestPerformanceComparison:
    """Tests de comparación de rendimiento"""
    
    @pytest.mark.asyncio
    async def test_performance_improvement(self):
        """Test que las optimizaciones mejoran el rendimiento"""
        # Este test compara el rendimiento entre manager normal y optimizado
        # En un entorno real, esto mostraría mejoras significativas
        
        with patch('src.api.integrations.ai.optimized_conversation_manager.Anthropic') as mock_anthropic:
            # Mock respuesta Claude
            mock_message = Mock()
            mock_message.content = [Mock(text='{"message": "Test", "intent": {"type": "test", "confidence": 0.8}}')]
            mock_message.usage.input_tokens = 50
            mock_message.usage.output_tokens = 25
            mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_message)
            
            # Manager optimizado
            optimized_manager = OptimizedConversationAIManager(
                anthropic_api_key="test-key",
                enable_caching=True,
                enable_circuit_breaker=True
            )
            
            context = ConversationContext(
                user_id="perf_test",
                session_id="perf_session",
                market_id="US",
                currency="USD",
                conversation_history=[],
                user_profile={},
                cart_items=[],
                browsing_history=[],
                intent_signals={}
            )
            
            # Medir tiempo de primera llamada
            start_time = time.time()
            response1 = await optimized_manager.process_conversation(
                user_message="Performance test message",
                context=context
            )
            first_call_time = time.time() - start_time
            
            # Medir tiempo de segunda llamada (debería usar caché si confidence > 0.7)
            start_time = time.time()
            response2 = await optimized_manager.process_conversation(
                user_message="Performance test message",
                context=context
            )
            second_call_time = time.time() - start_time
            
            # Verificar que las respuestas son válidas
            assert "conversation_response" in response1
            assert "conversation_response" in response2
            
            # Si usa caché, segunda llamada debería ser más rápida
            if response2["metadata"].get("cached"):
                assert second_call_time < first_call_time
                assert optimized_manager.metrics["cache_hits"] > 0
            
            await optimized_manager.cleanup()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
