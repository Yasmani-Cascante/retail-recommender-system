#!/usr/bin/env python3
"""
DIAGNÓSTICO ESPECÍFICO: State Manager Availability Issue
=======================================================

Script para diagnosticar por qué get_conversation_state_manager() retorna None
"""

import sys
import logging
sys.path.append('src')

# Configurar logging detallado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_state_manager_initialization():
    """Test detallado de inicialización del state manager"""
    
    print("🔍 TESTING STATE MANAGER INITIALIZATION")
    print("=" * 60)
    
    # Test 1: Import básico
    try:
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        print("✅ Import successful: get_conversation_state_manager")
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False
    
    # Test 2: Verificar configuración
    try:
        from src.api.core.config import get_settings
        settings = get_settings()
        print(f"✅ Settings loaded: use_redis_cache={settings.use_redis_cache}")
        print(f"   Redis host: {settings.redis_host}")
        print(f"   Redis port: {settings.redis_port}")
    except Exception as e:
        print(f"❌ Settings failed: {e}")
        return False
    
    # Test 3: RedisClient creation
    try:
        from src.api.core.redis_client import RedisClient
        redis_client = RedisClient(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            ssl=settings.redis_ssl
        )
        print(f"✅ RedisClient created: {type(redis_client)}")
    except Exception as e:
        print(f"❌ RedisClient creation failed: {e}")
        return False
    
    # Test 4: Redis connection
    try:
        import asyncio
        async def test_redis_connection():
            connected = await redis_client.connect()
            return connected
        
        connection_result = asyncio.run(test_redis_connection())
        print(f"✅ Redis connection: {connection_result}")
        
        if not connection_result:
            print("❌ Redis connection failed - this explains state_manager=None")
            return False
            
    except Exception as e:
        print(f"❌ Redis connection test failed: {e}")
        return False
    
    # Test 5: State manager creation
    try:
        state_manager = get_conversation_state_manager()
        print(f"✅ State manager result: {type(state_manager) if state_manager else 'None'}")
        
        if state_manager is None:
            print("❌ PROBLEM IDENTIFIED: get_conversation_state_manager() returns None")
            return False
        else:
            print("✅ State manager initialized successfully")
            return True
            
    except Exception as e:
        print(f"❌ State manager creation failed: {e}")
        return False

def test_global_state_manager():
    """Test del state manager global singleton"""
    
    print("\n🔍 TESTING GLOBAL STATE MANAGER")
    print("=" * 60)
    
    try:
        from src.api.mcp.conversation_state_manager import _global_conversation_state_manager
        print(f"Global state manager: {type(_global_conversation_state_manager) if _global_conversation_state_manager else 'None'}")
        
        # Forzar re-inicialización
        import src.api.mcp.conversation_state_manager as sm_module
        sm_module._global_conversation_state_manager = None
        
        print("🔄 Forcing re-initialization...")
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        state_manager = get_conversation_state_manager()
        
        print(f"Re-initialized state manager: {type(state_manager) if state_manager else 'None'}")
        
        return state_manager is not None
        
    except Exception as e:
        print(f"❌ Global state manager test failed: {e}")
        return False

def test_main_unified_redis_integration():
    """Test integración con main_unified_redis"""
    
    print("\n🔍 TESTING MAIN_UNIFIED_REDIS INTEGRATION")
    print("=" * 60)
    
    try:
        from src.api import main_unified_redis
        
        # Verificar variables globales
        globals_to_check = [
            'redis_client',
            'mcp_state_manager', 
            'personalization_engine',
            'optimized_conversation_manager'
        ]
        
        for var_name in globals_to_check:
            if hasattr(main_unified_redis, var_name):
                var_value = getattr(main_unified_redis, var_name)
                print(f"✅ {var_name}: {type(var_value) if var_value else 'None'}")
            else:
                print(f"❌ {var_name}: NOT FOUND")
        
        # Test específico para mcp_state_manager
        if hasattr(main_unified_redis, 'mcp_state_manager'):
            mcp_sm = getattr(main_unified_redis, 'mcp_state_manager')
            if mcp_sm:
                print(f"✅ MCP State Manager available in main: {type(mcp_sm)}")
                return True
            else:
                print("❌ MCP State Manager is None in main_unified_redis")
                return False
        else:
            print("❌ mcp_state_manager not found in main_unified_redis")
            return False
            
    except Exception as e:
        print(f"❌ Main unified redis test failed: {e}")
        return False

async def test_state_manager_operations():
    """Test operaciones básicas del state manager"""
    
    print("\n🔍 TESTING STATE MANAGER OPERATIONS")
    print("=" * 60)
    
    try:
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        state_manager = get_conversation_state_manager()
        
        if not state_manager:
            print("❌ No state manager available for operations test")
            return False
        
        # Test create session
        test_session = await state_manager.get_or_create_session(
            session_id="test_debug_session",
            user_id="test_user",
            market_id="US"
        )
        
        print(f"✅ Session created: {test_session.session_id}")
        print(f"   Turn count: {test_session.turn_count}")
        
        # Test save/load cycle
        save_result = await state_manager.save_conversation_state(
            test_session.session_id, 
            test_session
        )
        print(f"✅ Save result: {save_result}")
        
        loaded_session = await state_manager.load_conversation_state(test_session.session_id)
        print(f"✅ Load result: {type(loaded_session) if loaded_session else 'None'}")
        
        if loaded_session:
            print(f"   Loaded turn count: {loaded_session.turn_count}")
            return True
        else:
            print("❌ Session not loaded - persistence failed")
            return False
            
    except Exception as e:
        print(f"❌ State manager operations test failed: {e}")
        return False

async def main():
    """Función principal de diagnóstico"""
    
    print("🚀 STATE MANAGER DIAGNOSTIC SCRIPT")
    print("🎯 Goal: Identify why get_conversation_state_manager() returns None")
    print("=" * 80)
    
    tests = [
        ("Basic Initialization", test_state_manager_initialization),
        ("Global Singleton", test_global_state_manager),
        ("Main Unified Redis Integration", test_main_unified_redis_integration),
        ("State Manager Operations", test_state_manager_operations)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 RUNNING: {test_name}")
        print("-" * 40)
        
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
            
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"   Result: {status}")
            
        except Exception as e:
            print(f"   Result: ❌ ERROR - {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n📊 DIAGNOSTIC SUMMARY")
    print("=" * 40)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {test_name}")
    
    print(f"\n🎯 OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All tests passed - state manager should be working")
        print("💡 The issue might be in the router execution context")
    else:
        print("❌ Issues found - root cause identified")
        print("🔧 Fix the failing tests to resolve conversation state persistence")
    
    return passed == total

if __name__ == "__main__":
    import asyncio
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
