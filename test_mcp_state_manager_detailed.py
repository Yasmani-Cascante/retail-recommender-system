#!/usr/bin/env python3
"""
ENHANCED TEST: Detailed mcp_state_manager verification
"""

import sys
import asyncio
sys.path.append('src')

async def test_mcp_state_manager_detailed():
    """Test detallado del mcp_state_manager"""
    
    print("🔍 DETAILED MCP_STATE_MANAGER TESTING")
    print("=" * 60)
    
    try:
        # Test 1: Verificar existencia en main_unified_redis
        print("\n📋 TEST 1: Existence in main_unified_redis")
        from src.api import main_unified_redis
        
        has_attr = hasattr(main_unified_redis, 'mcp_state_manager')
        print(f"   Attribute exists: {has_attr}")
        
        if not has_attr:
            print("❌ FAILED: mcp_state_manager attribute missing")
            return False
        
        mcp_sm = getattr(main_unified_redis, 'mcp_state_manager')
        print(f"   Type: {type(mcp_sm) if mcp_sm else 'None'}")
        
        if mcp_sm is None:
            print("❌ FAILED: mcp_state_manager is None")
            return False
        
        print("✅ PASSED: mcp_state_manager exists and is not None")
        
        # Test 2: Verificar métodos básicos
        print("\n📋 TEST 2: Basic methods")
        required_methods = ['get_or_create_session', 'save_conversation_state', 'load_conversation_state']
        
        for method in required_methods:
            has_method = hasattr(mcp_sm, method)
            print(f"   {method}: {'✅' if has_method else '❌'}")
            if not has_method:
                print(f"❌ FAILED: Missing method {method}")
                return False
        
        print("✅ PASSED: All required methods present")
        
        # Test 3: Test funcional básico
        print("\n📋 TEST 3: Basic functionality")
        
        try:
            # Test crear sesión
            session = await mcp_sm.get_or_create_session(
                session_id="test_validation_session",
                user_id="test_user",
                market_id="US"
            )
            
            print(f"   Session created: {session.session_id}")
            print(f"   Turn count: {session.turn_count}")
            
            # Test save
            save_result = await mcp_sm.save_conversation_state(session.session_id, session)
            print(f"   Save successful: {save_result}")
            
            # Test load
            loaded_session = await mcp_sm.load_conversation_state(session.session_id)
            print(f"   Load successful: {loaded_session is not None}")
            
            if loaded_session:
                print(f"   Loaded turn count: {loaded_session.turn_count}")
            
            print("✅ PASSED: Basic functionality working")
            return True
            
        except Exception as func_error:
            print(f"❌ FAILED: Functionality test error: {func_error}")
            return False
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_factory_function():
    """Test directo de get_conversation_state_manager()"""
    
    print("\n🔍 TESTING FACTORY FUNCTION DIRECTLY")
    print("-" * 40)
    
    try:
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        
        # Test directo
        sm = get_conversation_state_manager()
        print(f"Factory function result: {type(sm) if sm else 'None'}")
        
        if sm:
            print("✅ PASSED: Factory function works")
            return True
        else:
            print("❌ FAILED: Factory function returns None")
            
            # Debug why it returns None
            print("\n🔍 Debugging factory function...")
            
            # Check global variable
            import src.api.mcp.conversation_state_manager as sm_module
            global_sm = getattr(sm_module, '_global_conversation_state_manager', 'NOT_FOUND')
            print(f"Global state manager: {type(global_sm) if global_sm and global_sm != 'NOT_FOUND' else global_sm}")
            
            # Test Redis availability
            try:
                from src.api.core.config import get_settings
                settings = get_settings()
                print(f"Redis cache enabled: {settings.use_redis_cache}")
                
                if settings.use_redis_cache:
                    from src.api.core.redis_client import RedisClient
                    redis_test = RedisClient(
                        host=settings.redis_host,
                        port=settings.redis_port,
                        password=settings.redis_password,
                        ssl=settings.redis_ssl
                    )
                    print("Redis client created successfully")
                
            except Exception as redis_debug:
                print(f"Redis debug error: {redis_debug}")
            
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

async def main():
    """Función principal de test"""
    
    print("🚀 ENHANCED MCP STATE MANAGER VALIDATION")
    print("🎯 Detailed verification of mcp_state_manager initialization")
    print("=" * 80)
    
    # Test factory function first
    factory_ok = test_factory_function()
    
    # Test in main_unified_redis
    detailed_ok = await test_mcp_state_manager_detailed()
    
    print(f"\n📊 RESULTS SUMMARY")
    print("=" * 30)
    print(f"Factory function: {'✅ PASSED' if factory_ok else '❌ FAILED'}")
    print(f"Detailed testing: {'✅ PASSED' if detailed_ok else '❌ FAILED'}")
    
    overall_success = factory_ok and detailed_ok
    
    if overall_success:
        print("\n🎉 ALL TESTS PASSED!")
        print("mcp_state_manager is fully functional")
        print("\n🎯 Ready for conversation state persistence testing")
    else:
        print("\n❌ TESTS FAILED")
        print("mcp_state_manager needs additional fixes")
        
        if not factory_ok:
            print("\n💡 Suggested actions:")
            print("   1. Check Redis configuration in .env")
            print("   2. Verify get_conversation_state_manager() implementation")
            print("   3. Check for import or dependency errors")
    
    return overall_success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
