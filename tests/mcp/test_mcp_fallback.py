# test_mcp_fallback.py
import asyncio
from src.api.factories.service_factory import ServiceFactory

async def test_enhanced_fallback():
    """Test fallback cuando bridge no disponible"""
    print("🔍 Testing Enhanced client fallback mechanisms...")
    
    client = await ServiceFactory.get_mcp_client()
    
    if hasattr(client, '_extract_intent_fallback'):
        print("✅ Enhanced client has fallback methods")
        
        # Test fallback intent detection
        context = {"query": "busco zapatos deportivos"}
        result = await client._extract_intent_fallback(context)
        
        print(f"Fallback intent: {result}")
        assert result.get('fallback_used') is True
        print("✅ Fallback working correctly")
    else:
        print("⚠️ Using Basic client (no fallback methods)")

async def test_circuit_breaker():
    """Test circuit breaker functionality"""
    print("\n🔍 Testing circuit breaker...")
    
    client = await ServiceFactory.get_mcp_client()
    
    if hasattr(client, 'circuit_breaker') and client.circuit_breaker:
        print("✅ Circuit breaker enabled")
        
        # Get circuit breaker stats
        if hasattr(client.circuit_breaker, 'get_stats'):
            stats = client.circuit_breaker.get_stats()
            print(f"Circuit breaker stats: {stats}")
        
        # Check if circuit is open
        if hasattr(client.circuit_breaker, 'is_open'):
            is_open = client.circuit_breaker.is_open
            print(f"Circuit breaker status: {'OPEN' if is_open else 'CLOSED'}")
    else:
        print("⚠️ Circuit breaker not available (using Basic client)")

async def test_local_cache():
    """Test local caching functionality"""
    print("\n🔍 Testing local cache...")
    
    client = await ServiceFactory.get_mcp_client()
    
    if hasattr(client, 'intent_cache'):
        print("✅ Local cache enabled")
        
        # Get metrics
        if hasattr(client, 'get_metrics'):
            metrics = await client.get_metrics()
            print(f"Cache metrics: {metrics}")
    else:
        print("⚠️ Local cache not available (using Basic client)")

if __name__ == "__main__":
    print("═" * 70)
    print("  MCP FALLBACK & RESILIENCE TESTS")
    print("═" * 70)
    
    asyncio.run(test_enhanced_fallback())
    asyncio.run(test_circuit_breaker())
    asyncio.run(test_local_cache())
    
    print("\n✅ All fallback tests completed")