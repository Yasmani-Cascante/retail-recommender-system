#!/usr/bin/env python3
"""
IMMEDIATE TEST: Verify startup event execution
"""

import sys
import time
sys.path.append('src')

def test_immediate_startup_fix():
    """Test inmediato del fix del startup"""
    
    print("🔍 IMMEDIATE STARTUP FIX TEST")
    print("=" * 50)
    
    try:
        # Clear any cached imports
        import importlib
        if 'src.api.main_unified_redis' in sys.modules:
            importlib.reload(sys.modules['src.api.main_unified_redis'])
        
        # Import fresh
        from src.api import main_unified_redis
        
        # Check mcp_state_manager
        has_attr = hasattr(main_unified_redis, 'mcp_state_manager')
        print(f"📋 mcp_state_manager exists: {has_attr}")
        
        if has_attr:
            mcp_sm = getattr(main_unified_redis, 'mcp_state_manager')
            print(f"📋 mcp_state_manager type: {type(mcp_sm) if mcp_sm else 'None'}")
            
            if mcp_sm is not None:
                print("✅ SUCCESS: mcp_state_manager is no longer None!")
                
                # Quick method check
                methods = ['get_or_create_session', 'save_conversation_state', 'load_conversation_state']
                for method in methods:
                    has_method = hasattr(mcp_sm, method)
                    print(f"   {method}: {'✅' if has_method else '❌'}")
                
                return True
            else:
                print("❌ STILL FAILED: mcp_state_manager is still None")
                print("💡 This means the startup event may not have run yet")
                print("💡 Try starting the server: python src/api/main_unified_redis.py")
                return False
        else:
            print("❌ FAILED: mcp_state_manager attribute missing")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_factory_function_isolation():
    """Test aislado de la factory function"""
    
    print("\n🔍 ISOLATED FACTORY FUNCTION TEST")
    print("-" * 40)
    
    try:
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        
        sm = get_conversation_state_manager()
        print(f"Factory result: {type(sm) if sm else 'None'}")
        
        if sm:
            print("✅ Factory function working correctly")
            return True
        else:
            print("❌ Factory function returning None")
            
            # Debug the global variable
            import src.api.mcp.conversation_state_manager as sm_module
            global_var = getattr(sm_module, '_global_conversation_state_manager', 'NOT_FOUND')
            print(f"Global variable: {type(global_var) if global_var and global_var != 'NOT_FOUND' else global_var}")
            
            # Force initialization
            print("🔧 Forcing re-initialization...")
            sm_module._global_conversation_state_manager = None
            sm2 = get_conversation_state_manager()
            print(f"Forced result: {type(sm2) if sm2 else 'None'}")
            
            return sm2 is not None
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    """Main test function"""
    
    print("🚀 IMMEDIATE STARTUP FIX VERIFICATION")
    print("🎯 Test if explicit startup fix resolved the issue")
    print("=" * 70)
    
    # Test 1: Factory function isolation
    factory_ok = test_factory_function_isolation()
    
    # Test 2: Immediate startup fix
    startup_ok = test_immediate_startup_fix()
    
    print(f"\n📊 IMMEDIATE TEST RESULTS")
    print("=" * 30)
    print(f"Factory function: {'✅ WORKING' if factory_ok else '❌ FAILED'}")
    print(f"Startup execution: {'✅ WORKING' if startup_ok else '❌ FAILED'}")
    
    if startup_ok:
        print("\n🎉 IMMEDIATE FIX SUCCESSFUL!")
        print("mcp_state_manager is now properly initialized")
        print("\n🎯 Next step: Test conversation state persistence")
    elif factory_ok:
        print("\n⚠️ PARTIAL SUCCESS")
        print("Factory function works but startup event needs execution")
        print("\n🎯 Next step: Start the server to trigger startup event")
    else:
        print("\n❌ FIX INCOMPLETE")
        print("Both factory and startup issues persist")
    
    return startup_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
