# tests/factories/test_service_factory_mcp.py
import pytest
import asyncio
from src.api.factories.service_factory import ServiceFactory

@pytest.mark.asyncio
async def test_get_mcp_client_singleton():
    """Verificar que get_mcp_client() retorna singleton"""
    # Reset singleton
    ServiceFactory._mcp_client = None
    
    client1 = await ServiceFactory.get_mcp_client()
    client2 = await ServiceFactory.get_mcp_client()
    
    assert client1 is client2, "Should return same singleton instance"
    assert client1 is not None, "Client should not be None"

@pytest.mark.asyncio
async def test_get_mcp_client_enhanced_preferred():
    """Verificar que se prefiere Enhanced sobre Basic"""
    ServiceFactory._mcp_client = None
    
    client = await ServiceFactory.get_mcp_client()
    
    # Should be Enhanced if available
    from src.api.mcp.client.mcp_client_enhanced import MCPClientEnhanced
    assert isinstance(client, MCPClientEnhanced), "Should use Enhanced version"

@pytest.mark.asyncio
async def test_get_mcp_client_parameters():
    """Verificar que los parámetros son correctos"""
    ServiceFactory._mcp_client = None
    
    client = await ServiceFactory.get_mcp_client()
    
    # Check correct parameters (bridge, not Claude API)
    assert hasattr(client, 'base_url'), "Should have base_url (bridge)"
    assert 'localhost' in client.base_url or '3001' in str(client.base_url)
    
    # Should NOT have Claude API params
    assert not hasattr(client, 'anthropic_api_key'), "Should NOT have anthropic_api_key"

@pytest.mark.asyncio
async def test_get_mcp_client_features():
    """Verificar features del Enhanced client"""
    ServiceFactory._mcp_client = None
    
    client = await ServiceFactory.get_mcp_client()
    
    # Check Enhanced features
    if hasattr(client, 'circuit_breaker'):
        assert client.circuit_breaker is not None, "Circuit breaker should be enabled"
    
    if hasattr(client, 'enable_local_cache'):
        assert client.enable_local_cache is True, "Cache should be enabled"

if __name__ == "__main__":
    # Run tests
    asyncio.run(test_get_mcp_client_singleton())
    asyncio.run(test_get_mcp_client_enhanced_preferred())
    asyncio.run(test_get_mcp_client_parameters())
    asyncio.run(test_get_mcp_client_features())
    print("✅ All tests passed!")