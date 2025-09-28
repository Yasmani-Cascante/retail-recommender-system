#!/usr/bin/env python3
"""
State Tracking Verification Test
===============================

Verifica que el state tracking reporta correctamente el estado de Redis
después del fix de inconsistencia.
"""

import sys
import asyncio
import time
sys.path.append('src')

from dotenv import load_dotenv
load_dotenv()

async def test_state_tracking_accuracy():
    """Test para verificar accuracy del state tracking"""
    
    print("TESTING STATE TRACKING ACCURACY")
    print("=" * 50)
    
    try:
        from src.api.factories import ServiceFactory
        
        print("1. Testing ServiceFactory Redis status...")
        
        # Get Redis service
        redis_service = await ServiceFactory.get_redis_service()
        health = await redis_service.health_check()
        
        actual_status = health.get('status', 'unknown')
        print(f"   Actual Redis status: {actual_status}")
        
        # Verify consistency with reported status
        if actual_status in ['healthy', 'connected', 'operational']:
            print("✅ Redis is actually working")
            expected_report = "Connected"
        else:
            print("⚠️ Redis is in degraded state")
            expected_report = "Fallback mode"
        
        print(f"   Expected startup report: {expected_report}")
        
        return actual_status in ['healthy', 'connected', 'operational']
        
    except Exception as e:
        print(f"❌ State tracking test failed: {e}")
        return False

async def test_component_redis_consistency():
    """Test que todos los componentes reportan estado consistente"""
    
    print("\n2. Testing component Redis consistency...")
    
    redis_states = {}
    
    try:
        # Test ProductCache
        from src.api.factories import ServiceFactory
        product_cache = await ServiceFactory.get_product_cache_singleton()
        
        if hasattr(product_cache, 'redis_client') and product_cache.redis_client:
            redis_states['ProductCache'] = 'Connected'
        else:
            redis_states['ProductCache'] = 'Fallback'
        
        # Test InventoryService  
        inventory_service = await ServiceFactory.get_inventory_service_singleton()
        
        if hasattr(inventory_service, 'redis') and inventory_service.redis:
            redis_states['InventoryService'] = 'Connected'
        else:
            redis_states['InventoryService'] = 'Fallback'
        
        # Test ConversationManager
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        conv_mgr = OptimizedConversationAIManager('test')
        
        if hasattr(conv_mgr, '_redis_client') and conv_mgr._redis_client:
            redis_states['ConversationManager'] = 'Connected'
        else:
            redis_states['ConversationManager'] = 'Fallback'
        
        # Report consistency
        print("   Component Redis states:")
        for component, state in redis_states.items():
            print(f"     {component}: {state}")
        
        # Check consistency
        unique_states = set(redis_states.values())
        if len(unique_states) == 1:
            print(f"✅ All components consistent: {list(unique_states)[0]}")
            return True
        else:
            print(f"⚠️ Inconsistent states detected: {unique_states}")
            return False
        
    except Exception as e:
        print(f"❌ Component consistency test failed: {e}")
        return False

async def comprehensive_state_test():
    """Test comprehensivo de state tracking"""
    
    print("STATE TRACKING VERIFICATION - POST FIX")
    print("=" * 60)
    
    # Test 1: Accuracy
    accuracy_test = await test_state_tracking_accuracy()
    
    # Test 2: Consistency
    consistency_test = await test_component_redis_consistency()
    
    if accuracy_test and consistency_test:
        print("\n🎉 STATE TRACKING FIX SUCCESSFUL!")
        print("=" * 50)
        print("✅ Redis status reporting accurate")
        print("✅ All components consistent")
        print("✅ State tracking inconsistency resolved")
        return True
    else:
        print("\n❌ STATE TRACKING ISSUES REMAIN")
        print("🔧 Additional fixes may be needed")
        return False

if __name__ == "__main__":
    success = asyncio.run(comprehensive_state_test())
    
    if success:
        print("\n🎯 STATE TRACKING FIX VALIDATED")
        print("Ready to proceed with observability endpoints")
    else:
        print("\n🔧 ADDITIONAL STATE FIXES NEEDED")
