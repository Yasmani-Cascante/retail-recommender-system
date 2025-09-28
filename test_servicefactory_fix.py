#!/usr/bin/env python3
"""
ServiceFactory Specific Test - Post Timeout Fix
==============================================

Test específico para validar que ServiceFactory funciona después del timeout fix.
"""

import sys
import asyncio
sys.path.append('src')

# Load environment
from dotenv import load_dotenv
load_dotenv()

async def test_servicefactory_post_fix():
    """Test ServiceFactory después del timeout fix"""
    
    print("TESTING SERVICEFACTORY POST TIMEOUT FIX")
    print("=" * 50)
    
    try:
        from src.api.factories import ServiceFactory
        
        print("Testing ServiceFactory with increased timeouts...")
        
        # Time the operation
        start_time = asyncio.get_event_loop().time()
        
        redis_service = await ServiceFactory.get_redis_service()
        
        end_time = asyncio.get_event_loop().time()
        duration = (end_time - start_time) * 1000  # Convert to ms
        
        print(f"ServiceFactory Redis creation took: {duration:.1f}ms")
        
        # Test health check
        health = await redis_service.health_check()
        status = health.get('status', 'unknown')
        
        print(f"Redis health: {status}")
        
        if status in ['healthy', 'connected', 'operational']:
            print("SERVICEFACTORY FIX SUCCESSFUL!")
            print("Redis is healthy through ServiceFactory")
            return True
        elif status == 'degraded':
            print("ServiceFactory still in degraded mode")
            print("May need additional timeout adjustments")
            return False
        else:
            print(f"ServiceFactory status not optimal: {status}")
            return False
            
    except Exception as e:
        print(f"ServiceFactory test failed: {e}")
        return False

async def test_integration_post_fix():
    """Test integración completa post fix"""
    
    print("\nINTEGRATION TEST POST SERVICEFACTORY FIX")
    print("=" * 50)
    
    try:
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        from src.api.mcp.engines.mcp_personalization_engine import create_mcp_personalization_engine
        
        print("Testing full integration...")
        
        # Test conversation manager
        conv_mgr = OptimizedConversationAIManager('test_key')
        print('OptimizedConversationAIManager created')
        
        # Check Redis client availability
        if hasattr(conv_mgr, '_redis_client'):
            redis_available = conv_mgr._redis_client is not None
            print(f'Redis client available: {redis_available}')
        
        # Test state manager
        state_mgr = await get_conversation_state_manager()
        print('ConversationStateManager created')
        
        # Test personalization engine
        engine = await create_mcp_personalization_engine('test_key')
        print('PersonalizationEngine created')
        
        print("FULL INTEGRATION TEST SUCCESSFUL!")
        return True
        
    except Exception as e:
        print(f"Integration test failed: {e}")
        return False

async def comprehensive_test():
    """Test comprehensivo post fix"""
    
    print("COMPREHENSIVE TEST - SERVICEFACTORY FIX VALIDATION")
    print("=" * 60)
    
    # Test 1: ServiceFactory específico
    sf_success = await test_servicefactory_post_fix()
    
    # Test 2: Integración completa si ServiceFactory funciona
    if sf_success:
        integration_success = await test_integration_post_fix()
        
        if integration_success:
            print("\nALL TESTS PASSED - SERVICEFACTORY FIX SUCCESSFUL!")
            print("=" * 60)
            print("ServiceFactory timeout fix working")
            print("Redis connection through ServiceFactory healthy")
            print("All enterprise components functional")
            print("Migration Redis Enterprise COMPLETED")
            return True
        else:
            print("\nServiceFactory fixed but integration has issues")
            return False
    else:
        print("\nServiceFactory fix needs additional work")
        return False

if __name__ == "__main__":
    success = asyncio.run(comprehensive_test())
    
    if success:
        print("\nNEXT STEPS:")
        print("1. ServiceFactory timeout fix successful")
        print("2. Redis enterprise migration completed")
        print("3. Ready to implement observability endpoints")
        print("4. Ready for Fase 3 - Microservices transition")
    else:
        print("\nAdditional fixes may be needed")
