# test_mcp_bridge_integration.py
import asyncio
from src.api.factories.service_factory import ServiceFactory

async def test_bridge_health():
    """Test health check del MCP Bridge"""
    print("🔍 Testing MCP Bridge health check...")
    
    client = await ServiceFactory.get_mcp_client()
    
    if client:
        try:
            health = await client.health_check()
            print(f"✅ Bridge health: {health}")
            return True
        except Exception as e:
            print(f"⚠️ Bridge health check failed: {e}")
            return False
    else:
        print("❌ MCP Client is None")
        return False

async def test_bridge_conversation():
    """Test conversation processing"""
    print("\n🔍 Testing conversation processing...")
    
    client = await ServiceFactory.get_mcp_client()
    
    if client:
        try:
            result = await client.process_conversation(
                query="Hello, test query",
                session_id="test_session_123"
            )
            print(f"✅ Conversation result: {result}")
            return True
        except Exception as e:
            print(f"⚠️ Conversation processing failed: {e}")
            return False
    else:
        print("❌ MCP Client is None")
        return False

async def test_bridge_intent():
    """Test intent analysis"""
    print("\n🔍 Testing intent analysis...")
    
    client = await ServiceFactory.get_mcp_client()
    
    if client:
        try:
            intent = await client.analyze_intent(
                text="I want to buy running shoes",
                context={"market": "US"}
            )
            print(f"✅ Intent detected: {intent}")
            return True
        except Exception as e:
            print(f"⚠️ Intent analysis failed: {e}")
            return False
    else:
        print("❌ MCP Client is None")
        return False

if __name__ == "__main__":
    print("═" * 70)
    print("  MCP BRIDGE INTEGRATION TESTS")
    print("═" * 70)
    
    results = []
    results.append(asyncio.run(test_bridge_health()))
    results.append(asyncio.run(test_bridge_conversation()))
    results.append(asyncio.run(test_bridge_intent()))
    
    print("\n" + "═" * 70)
    print(f"  RESULTS: {sum(results)}/{len(results)} tests passed")
    print("═" * 70)