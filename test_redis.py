# Test avanzado con Redis activo:
import asyncio
import os
os.environ['USE_REDIS_CACHE'] = 'true'

from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
from src.api.mcp.conversation_state_manager import get_conversation_state_manager
from src.api.mcp.engines.mcp_personalization_engine import create_mcp_personalization_engine

async def test_with_redis():
    print('🔄 Testing with Redis enabled...')
    
    # Test conversation manager
    conv_mgr = OptimizedConversationAIManager('test_key')
    print('✅ OptimizedConversationAIManager created')
    
    # Test Redis functionality
    if hasattr(conv_mgr, '_redis_client'):
        print(f'📊 Redis client available: {conv_mgr._redis_client is not None}')
    
    # Test state manager  
    state_mgr = await get_conversation_state_manager()
    print('✅ ConversationStateManager created')
    
    # Test personalization engine
    engine = await create_mcp_personalization_engine('test_key')
    print('✅ PersonalizationEngine created')
    
    # Test Redis health if available
    try:
        from src.api.factories import ServiceFactory
        redis_service = await ServiceFactory.get_redis_service()
        health = await redis_service.health_check()
        print(f'📊 Redis health: {health.get("status", "unknown")}')
    except Exception as e:
        print(f'⚠️ Redis health check: {e}')

asyncio.run(test_with_redis())
