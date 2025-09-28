#!/usr/bin/env python3
"""
FIX DEFINITIVO: Startup Event Debugging y Corrección
===================================================

PROBLEMA CONFIRMADO:
- Factory function funciona (✅ PASSED)
- mcp_state_manager sigue siendo None en main_unified_redis (❌ FAILED)
- Conclusión: El startup event no está ejecutando correctamente la inicialización

SOLUCIÓN:
- Debug y fix del startup event específicamente
- Asegurar que la variable global se actualice
"""

import os
import re

def debug_startup_event():
    """
    Debug del startup event para identificar por qué mcp_state_manager no se inicializa
    """
    
    print("🔍 DEBUGGING STARTUP EVENT")
    print("=" * 50)
    
    main_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/main_unified_redis.py"
    
    try:
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Buscar el startup event
        startup_pattern = r'@app\.on_event\("startup"\)\s*async def [^(]+\([^)]*\):'
        startup_match = re.search(startup_pattern, content)
        
        if startup_match:
            print("✅ Found startup event decorator")
            
            # Buscar la declaración global
            global_pattern = r'global redis_client[^\\n]*mcp_state_manager'
            global_match = re.search(global_pattern, content)
            
            if global_match:
                print("✅ Found global declaration with mcp_state_manager")
                print(f"   Declaration: {global_match.group()}")
            else:
                print("❌ Global declaration missing or incomplete")
                return False
            
            # Buscar la inicialización de mcp_state_manager
            mcp_init_pattern = r'mcp_state_manager = get_conversation_state_manager\(\)'
            mcp_init_match = re.search(mcp_init_pattern, content)
            
            if mcp_init_match:
                print("✅ Found mcp_state_manager initialization")
            else:
                print("❌ mcp_state_manager initialization missing")
                return False
            
            return True
        else:
            print("❌ Startup event not found")
            return False
            
    except Exception as e:
        print(f"❌ Error debugging startup: {e}")
        return False

def fix_startup_event_execution():
    """
    Fix directo del startup event para asegurar ejecución
    """
    
    print("\\n🔧 FIXING STARTUP EVENT EXECUTION")
    print("=" * 50)
    
    main_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/main_unified_redis.py"
    
    try:
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        backup_file = main_file + ".backup_startup_fix"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup created: {backup_file}")
        
        # Buscar y reemplazar la sección de inicialización de mcp_state_manager
        # con una versión que tenga logging explícito y verificación
        
        robust_mcp_init = '''    # ==========================================
    # INICIALIZACIÓN MCP STATE MANAGER - EXPLICIT FIX
    # ==========================================
    
    logger.info("🔧 EXPLICIT: Starting mcp_state_manager initialization...")
    
    try:
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        logger.info("🔧 EXPLICIT: Import successful")
        
        temp_mcp_state_manager = get_conversation_state_manager()
        logger.info(f"🔧 EXPLICIT: Factory result: {type(temp_mcp_state_manager) if temp_mcp_state_manager else 'None'}")
        
        if temp_mcp_state_manager:
            mcp_state_manager = temp_mcp_state_manager
            logger.info("✅ EXPLICIT: mcp_state_manager assigned successfully")
        else:
            logger.warning("⚠️ EXPLICIT: Factory returned None, creating manual instance...")
            from src.api.mcp.conversation_state_manager import MCPConversationStateManager
            
            if redis_client:
                mcp_state_manager = MCPConversationStateManager(redis_client)
                logger.info("✅ EXPLICIT: Manual creation with Redis successful")
            else:
                mcp_state_manager = MCPConversationStateManager(None)
                logger.info("✅ EXPLICIT: Manual creation without Redis successful")
        
        # Verificación inmediata
        logger.info(f"🔧 EXPLICIT: Final mcp_state_manager type: {type(mcp_state_manager) if mcp_state_manager else 'None'}")
        
        # Test básico inmediato
        if mcp_state_manager and hasattr(mcp_state_manager, 'get_or_create_session'):
            logger.info("✅ EXPLICIT: mcp_state_manager has required methods")
        else:
            logger.error("❌ EXPLICIT: mcp_state_manager missing required methods")
            
    except Exception as mcp_explicit_error:
        logger.error(f"❌ EXPLICIT: Error in mcp_state_manager initialization: {mcp_explicit_error}")
        logger.error(f"❌ EXPLICIT: Error type: {type(mcp_explicit_error)}")
        import traceback
        logger.error(f"❌ EXPLICIT: Traceback: {traceback.format_exc()}")
        mcp_state_manager = None
    
    logger.info(f"🔧 EXPLICIT: mcp_state_manager initialization completed. Result: {type(mcp_state_manager) if mcp_state_manager else 'None'}")'''
        
        # Buscar la sección existente de inicialización de mcp_state_manager
        existing_pattern = r'# ==========================================\s*# INICIALIZACIÓN MCP STATE MANAGER.*?logger\.info\(f"❌ Even fallback failed: \{fallback_error\}"\)\s*mcp_state_manager = None'
        
        if re.search(existing_pattern, content, re.DOTALL):
            content = re.sub(existing_pattern, robust_mcp_init, content, flags=re.DOTALL)
            print("✅ Replaced existing MCP initialization with explicit version")
        else:
            # Si no encuentra la sección, buscar otro patrón
            pattern2 = r'# Crear e inicializar mcp_state_manager global.*?mcp_state_manager = None'
            if re.search(pattern2, content, re.DOTALL):
                content = re.sub(pattern2, robust_mcp_init, content, flags=re.DOTALL)
                print("✅ Replaced MCP initialization (pattern 2)")
            else:
                print("⚠️ Could not find existing MCP initialization section")
                # Insertar antes del resumen
                summary_point = content.find("# RESUMEN FINAL DEL STARTUP")
                if summary_point != -1:
                    content = content[:summary_point] + robust_mcp_init + "\\n    \\n    " + content[summary_point:]
                    print("✅ Added explicit MCP initialization before summary")
        
        # Escribir archivo
        with open(main_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Explicit startup fix applied")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing startup: {e}")
        return False

def create_immediate_test_script():
    """
    Crear script para test inmediato después del fix
    """
    
    test_content = '''#!/usr/bin/env python3
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
    
    print("\\n🔍 ISOLATED FACTORY FUNCTION TEST")
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
    
    print(f"\\n📊 IMMEDIATE TEST RESULTS")
    print("=" * 30)
    print(f"Factory function: {'✅ WORKING' if factory_ok else '❌ FAILED'}")
    print(f"Startup execution: {'✅ WORKING' if startup_ok else '❌ FAILED'}")
    
    if startup_ok:
        print("\\n🎉 IMMEDIATE FIX SUCCESSFUL!")
        print("mcp_state_manager is now properly initialized")
        print("\\n🎯 Next step: Test conversation state persistence")
    elif factory_ok:
        print("\\n⚠️ PARTIAL SUCCESS")
        print("Factory function works but startup event needs execution")
        print("\\n🎯 Next step: Start the server to trigger startup event")
    else:
        print("\\n❌ FIX INCOMPLETE")
        print("Both factory and startup issues persist")
    
    return startup_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
'''
    
    with open("C:/Users/yasma/Desktop/retail-recommender-system/test_immediate_startup_fix.py", 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    print("✅ Created immediate test script: test_immediate_startup_fix.py")

def main():
    """Función principal"""
    
    print("🚀 STARTUP EVENT EXPLICIT FIX")
    print("🎯 Goal: Fix startup event execution for mcp_state_manager")
    print("=" * 70)
    
    # Debug startup event
    debug_ok = debug_startup_event()
    
    if debug_ok:
        print("✅ Startup event structure is correct")
    else:
        print("❌ Startup event has structural issues")
    
    # Apply explicit fix
    fix_ok = fix_startup_event_execution()
    
    if fix_ok:
        print("\\n✅ EXPLICIT STARTUP FIX APPLIED!")
        
        # Create immediate test
        create_immediate_test_script()
        
        print("\\n🎯 IMMEDIATE NEXT STEPS:")
        print("   1. Run immediate test: python test_immediate_startup_fix.py")
        print("   2. If still None, restart server: python src/api/main_unified_redis.py")
        print("   3. Run test again after server starts")
        print("   4. Then test conversation persistence")
        
        return True
    else:
        print("\\n❌ EXPLICIT FIX FAILED")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
