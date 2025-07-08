# tests/phase0_consolidation/test_mcp_bridge_integration.py
"""
Tests de integración para MCP Bridge - Node.js ↔ Python connectivity.
Valida que la comunicación entre Python y Node.js funciona correctamente.
"""

import pytest
import asyncio
import httpx
import time
from unittest.mock import Mock, AsyncMock, patch
from src.api.mcp.client.bridge_client import MCPBridgeClient, MCPBridgeError
from src.api.mcp.client.circuit_breaker import CircuitState

@pytest.fixture
def bridge_client():
    """Fixture para MCPBridgeClient con configuración de test"""
    client = MCPBridgeClient(
        bridge_host="localhost",
        bridge_port=3001,
        timeout=5,
        enable_circuit_breaker=True,
        max_retries=2
    )
    
    yield client
    
    # Cleanup se maneja automáticamente o en finalizer si es necesario
    # Para tests, no es crítico el cleanup async

@pytest.fixture
def mock_bridge_response():
    """Fixture para respuesta mock del bridge"""
    return {
        "success": True,
        "intent": {
            "type": "search",
            "confidence": 0.85,
            "attributes": ["product", "electronics"],
            "urgency": "medium",
            "source": "shopify_mcp"
        },
        "timestamp": "2025-01-01T00:00:00Z"
    }

class TestMCPBridgeClient:
    """Tests para MCPBridgeClient"""
    
    def test_client_initialization(self, bridge_client):
        """Test inicialización del cliente"""
        assert bridge_client.bridge_url == "http://localhost:3001"
        assert bridge_client.timeout == 5
        assert bridge_client.max_retries == 2
        assert bridge_client.circuit_breaker is not None
        assert bridge_client.metrics["total_requests"] == 0
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, bridge_client):
        """Test health check exitoso"""
        mock_health_response = {
            "status": "healthy",
            "mcp_connection": "connected",
            "uptime": 12345,
            "metrics": {
                "total_requests": 100,
                "total_errors": 2
            }
        }
        
        with patch.object(bridge_client.http_client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_health_response
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            health = await bridge_client.health_check()
            
            assert health["status"] == "healthy"
            assert health["bridge_status"] == "healthy"
            assert health["mcp_connection"] == "connected"
            assert "latency_ms" in health
            assert health["bridge_metrics"]["total_requests"] == 100
            assert bridge_client.metrics["bridge_available"] is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, bridge_client):
        """Test health check con fallo de conexión"""
        with patch.object(bridge_client.http_client, 'get') as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection failed")
            
            health = await bridge_client.health_check()
            
            assert health["status"] == "unhealthy"
            assert "error" in health
            assert bridge_client.metrics["bridge_available"] is False
    
    @pytest.mark.asyncio
    async def test_extract_intent_success(self, bridge_client, mock_bridge_response):
        """Test extracción de intención exitosa"""
        with patch.object(bridge_client, '_make_bridge_request') as mock_request:
            mock_request.return_value = mock_bridge_response
            
            result = await bridge_client.extract_intent(
                query="I'm looking for a laptop",
                market_context={"market_id": "US", "currency": "USD"},
                conversation_history=[{"user": "Hello"}]
            )
            
            assert result == mock_bridge_response
            mock_request.assert_called_once_with(
                "POST",
                "/mcp/extract-intent",
                {
                    "query": "I'm looking for a laptop",
                    "market_context": {"market_id": "US", "currency": "USD"},
                    "conversation_history": [{"user": "Hello"}]
                }
            )
    
    @pytest.mark.asyncio
    async def test_get_market_configuration_success(self, bridge_client):
        """Test obtención de configuración de mercado"""
        mock_config_response = {
            "success": True,
            "market_config": {
                "market_id": "ES",
                "currency": "EUR",
                "primary_language": "es",
                "timezone": "Europe/Madrid"
            }
        }
        
        with patch.object(bridge_client, '_make_bridge_request') as mock_request:
            mock_request.return_value = mock_config_response
            
            result = await bridge_client.get_market_configuration("ES")
            
            assert result == mock_config_response
            mock_request.assert_called_once_with(
                "POST",
                "/mcp/markets/get-config",
                {"market_id": "ES"}
            )
    
    @pytest.mark.asyncio
    async def test_check_inventory_availability(self, bridge_client):
        """Test verificación de disponibilidad de inventario"""
        mock_inventory_response = {
            "success": True,
            "availability": {
                "product1": {"available": True, "quantity": 5},
                "product2": {"available": False, "quantity": 0}
            },
            "market_id": "MX"
        }
        
        with patch.object(bridge_client, '_make_bridge_request') as mock_request:
            mock_request.return_value = mock_inventory_response
            
            result = await bridge_client.check_inventory_availability(
                "MX", ["product1", "product2"]
            )
            
            assert result == mock_inventory_response
            mock_request.assert_called_once_with(
                "POST",
                "/mcp/inventory/check-availability",
                {"market_id": "MX", "product_ids": ["product1", "product2"]}
            )

class TestMCPBridgeRequestHandling:
    """Tests para manejo de requests HTTP del bridge"""
    
    @pytest.mark.asyncio
    async def test_successful_request(self, bridge_client):
        """Test request HTTP exitoso"""
        mock_response_data = {"success": True, "data": "test"}
        
        with patch.object(bridge_client.http_client, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response
            
            result = await bridge_client._make_bridge_request(
                "POST", "/test", {"test": "data"}
            )
            
            assert result == mock_response_data
            assert bridge_client.metrics["successful_requests"] == 1
            assert bridge_client.metrics["total_requests"] == 1
    
    @pytest.mark.asyncio
    async def test_request_with_retries(self, bridge_client):
        """Test request con reintentos"""
        with patch.object(bridge_client.http_client, 'post') as mock_post:
            # Primer intento falla, segundo intento es exitoso
            mock_post.side_effect = [
                httpx.TimeoutException("Timeout"),
                Mock(json=lambda: {"success": True}, raise_for_status=lambda: None)
            ]
            
            result = await bridge_client._make_bridge_request(
                "POST", "/test", {"test": "data"}
            )
            
            assert result["success"] is True
            assert mock_post.call_count == 2
            assert bridge_client.metrics["successful_requests"] == 1
    
    @pytest.mark.asyncio
    async def test_request_failure_after_retries(self, bridge_client):
        """Test request que falla después de todos los reintentos"""
        with patch.object(bridge_client.http_client, 'post') as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Persistent timeout")
            
            with pytest.raises(MCPBridgeError) as exc_info:
                await bridge_client._make_bridge_request(
                    "POST", "/test", {"test": "data"}
                )
            
            assert "failed after" in str(exc_info.value)
            assert mock_post.call_count == bridge_client.max_retries + 1
            assert bridge_client.metrics["failed_requests"] == 1
    
    @pytest.mark.asyncio
    async def test_client_error_no_retry(self, bridge_client):
        """Test que errores 4xx no se reintentan"""
        with patch.object(bridge_client.http_client, 'post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_error = httpx.HTTPStatusError(
                "Bad Request", request=Mock(), response=mock_response
            )
            mock_post.side_effect = mock_error
            
            with pytest.raises(MCPBridgeError):
                await bridge_client._make_bridge_request(
                    "POST", "/test", {"test": "data"}
                )
            
            # Solo debería intentar una vez para errores 4xx
            assert mock_post.call_count == 1

class TestMCPBridgeFallbacks:
    """Tests para fallbacks del MCP Bridge"""
    
    @pytest.mark.asyncio
    async def test_fallback_intent_extraction(self, bridge_client):
        """Test fallback para extracción de intención"""
        payload = {
            "query": "Busco un teléfono móvil",
            "market_context": {"market_id": "ES"}
        }
        
        result = await bridge_client._fallback_intent_extraction(payload)
        
        assert result["success"] is True
        assert result["intent"]["type"] == "search"  # Debería detectar "busco"
        assert result["intent"]["confidence"] > 0.5
        assert result["intent"]["fallback"] is True
        assert result["intent"]["source"] == "fallback_analysis"
    
    @pytest.mark.asyncio
    async def test_fallback_market_config(self, bridge_client):
        """Test fallback para configuración de mercado"""
        payload = {"market_id": "CO"}
        
        result = await bridge_client._fallback_market_config(payload)
        
        assert result["success"] is True
        assert result["market_config"]["market_id"] == "CO"
        assert result["market_config"]["currency"] == "COP"
        assert result["market_config"]["primary_language"] == "es"
        assert result["market_config"]["fallback"] is True
    
    @pytest.mark.asyncio
    async def test_fallback_inventory_check(self, bridge_client):
        """Test fallback para verificación de inventario"""
        payload = {
            "market_id": "CL",
            "product_ids": ["prod1", "prod2", "prod3"]
        }
        
        result = await bridge_client._fallback_inventory_check(payload)
        
        assert result["success"] is True
        assert result["market_id"] == "CL"
        assert len(result["availability"]) == 3
        assert result["fallback"] is True
        
        # Verificar que todos los productos están marcados como disponibles
        for product_id in payload["product_ids"]:
            assert result["availability"][product_id]["available"] is True
            assert result["availability"][product_id]["quantity"] > 0

class TestMCPBridgeCircuitBreaker:
    """Tests para circuit breaker del MCP Bridge"""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self, bridge_client):
        """Test que circuit breaker se abre después de fallos - CORREGIDO"""
        # Simular fallos múltiples
        with patch.object(bridge_client, '_make_bridge_request') as mock_request:
            mock_request.side_effect = MCPBridgeError("Persistent failure")
            
            # Intentar múltiples veces para activar circuit breaker
            for _ in range(5):
                try:
                    await bridge_client.extract_intent("test query")
                except:
                    pass
            
            # Verificar que circuit breaker está abierto - CORREGIDO
            cb_stats = bridge_client.circuit_breaker.get_stats()
            assert cb_stats["state"] == "OPEN"  # Ahora coincide con enum corregido
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_fallback(self, bridge_client):
        """Test fallback cuando circuit breaker está abierto - CORREGIDO"""
        # CORREGIDO: Usar enum apropiado en lugar de string
        bridge_client.circuit_breaker.state = CircuitState.OPEN
        bridge_client.circuit_breaker.last_failure_time = time.time()
        
        # Intentar extracción de intención - debería usar fallback
        result = await bridge_client.extract_intent(
            "Necesito ayuda para encontrar productos"
        )
        
        # Verificar que usó fallback
        assert "intent" in result
        assert result["intent"]["source"] == "fallback_analysis"
        assert result["intent"]["type"] == "search"

class TestMCPBridgeMetrics:
    """Tests para métricas del MCP Bridge"""
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self, bridge_client):
        """Test recolección de métricas - CORREGIDO"""
        
        # ESTRATEGIA CORREGIDA: Mock a nivel HTTP en lugar de _make_bridge_request
        # Esto permite que las métricas se actualicen correctamente
        
        with patch.object(bridge_client.http_client, 'post') as mock_post:
            # Configurar respuestas mock exitosas
            successful_response = Mock()
            successful_response.json.return_value = {"success": True, "intent": {"type": "search"}}
            successful_response.raise_for_status.return_value = None
            
            # Configurar respuesta fallida
            failed_response = Mock()
            failed_response.side_effect = httpx.TimeoutException("Test timeout")
            
            # Simular 2 operaciones exitosas
            mock_post.return_value = successful_response
            await bridge_client.extract_intent("test1")
            await bridge_client.get_market_configuration("US")
            
            # Simular 1 operación fallida
            mock_post.side_effect = failed_response
            try:
                await bridge_client.extract_intent("test2")
            except MCPBridgeError:
                pass  # Esperado
        
        # Ahora las métricas deberían estar actualizadas correctamente
        metrics = await bridge_client.get_metrics()
        
        assert metrics["client_metrics"]["total_requests"] == 3
        assert metrics["client_metrics"]["successful_requests"] == 2
        assert metrics["client_metrics"]["failed_requests"] == 1
        assert metrics["success_rate"] == 2/3
        assert "circuit_breaker" in metrics
        assert "bridge_url" in metrics

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
