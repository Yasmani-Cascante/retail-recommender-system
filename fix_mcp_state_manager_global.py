#!/usr/bin/env python3
"""
FIX DEFINITIVO: Agregar mcp_state_manager como variable global en main_unified_redis.py
================================================================================

PROBLEMA CONFIRMADO:
- diagnostic_state_manager_issue.py muestra que mcp_state_manager NO existe en main_unified_redis
- Por eso mcp_router.py no puede acceder al state manager
- Causando fallback mode y turn_number siempre = 1

SOLUCIÓN:
- Agregar mcp_state_manager como variable global en main_unified_redis.py startup
"""

import os
import re

def apply_mcp_state_manager_fix():
    """
    Aplica el fix específico para agregar mcp_state_manager al startup de main_unified_redis.py
    """
    
    print("🔧 APPLYING MCP STATE MANAGER FIX TO MAIN_UNIFIED_REDIS.PY")
    print("=" * 70)
    
    main_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/main_unified_redis.py"
    
    try:
        # Leer archivo actual
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup del archivo original
        backup_file = main_file + ".backup_mcp_state_fix"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup created: {backup_file}")
        
        # Verificar si ya tiene el fix
        if "mcp_state_manager = None" in content and "global" in content and "mcp_state_manager" in content:
            print("✅ Fix already applied - mcp_state_manager found in file")
            return True
        
        # PASO 1: Agregar mcp_state_manager a las variables globales iniciales
        # Buscar la sección donde se declaran las variables globales iniciales
        global_vars_pattern = r"# Variables globales para Redis y caché de productos\nredis_client = None\nproduct_cache = None"
        
        if re.search(global_vars_pattern, content):
            replacement = """# Variables globales para Redis y caché de productos
redis_client = None
product_cache = None

# Variables globales para MCP y conversation state
mcp_state_manager = None"""
            
            content = re.sub(global_vars_pattern, replacement, content)
            print("✅ Step 1: Added mcp_state_manager global variable declaration")
        else:
            print("⚠️ Warning: Could not find global variables section, will add manually")
            # Buscar donde están las otras declaraciones y agregar ahí
            if "redis_client = None" in content and "product_cache = None" in content:
                content = content.replace(
                    "product_cache = None",
                    "product_cache = None\n\n# Variables globales para MCP y conversation state\nmcp_state_manager = None"
                )
                print("✅ Step 1: Added mcp_state_manager global variable declaration (manual)")
        
        # PASO 2: Agregar mcp_state_manager a la declaración global en fixed_startup_event
        # Buscar la línea de global en fixed_startup_event
        global_declaration_pattern = r"global redis_client, product_cache, hybrid_recommender, mcp_recommender"
        
        if re.search(global_declaration_pattern, content):
            replacement = "global redis_client, product_cache, hybrid_recommender, mcp_recommender, mcp_state_manager"
            content = re.sub(global_declaration_pattern, replacement, content)
            print("✅ Step 2: Added mcp_state_manager to global declaration in startup")
        else:
            print("⚠️ Warning: Could not find global declaration in startup")
        
        # PASO 3: Agregar inicialización de mcp_state_manager en el startup
        # Buscar donde se crea mcp_recommender y agregar después
        mcp_recommender_section = r"# Crear recomendador MCP\s*\n\s*mcp_recommender = MCPFactory\.create_mcp_recommender_fixed\("
        
        if re.search(mcp_recommender_section, content, re.MULTILINE):
            # Buscar el final de la sección de mcp_recommender
            insertion_point = content.find("logger.info(\"✅ Recomendador MCP inicializado correctamente\")")
            
            if insertion_point != -1:
                # Buscar el final de esa línea
                end_of_line = content.find("\n", insertion_point)
                
                if end_of_line != -1:
                    mcp_state_manager_code = '''
        
        # ==========================================
        # INICIALIZACIÓN MCP STATE MANAGER
        # ==========================================
        
        # Crear e inicializar mcp_state_manager global
        try:
            from src.api.mcp.conversation_state_manager import get_conversation_state_manager
            mcp_state_manager = get_conversation_state_manager()
            
            if mcp_state_manager:
                logger.info("✅ MCP State Manager inicializado correctamente")
            else:
                logger.warning("⚠️ MCP State Manager no disponible")
                
        except Exception as mcp_state_error:
            logger.error(f"❌ Error inicializando MCP State Manager: {mcp_state_error}")
            mcp_state_manager = None'''
                    
                    content = content[:end_of_line] + mcp_state_manager_code + content[end_of_line:]
                    print("✅ Step 3: Added mcp_state_manager initialization in startup")
                else:
                    print("⚠️ Warning: Could not find insertion point for mcp_state_manager initialization")
            else:
                print("⚠️ Warning: Could not find MCP recommender success log")
        else:
            # Si no encuentra la sección de mcp_recommender, agregar antes del summary
            summary_section = "# =========================================="
            summary_index = content.find("# RESUMEN FINAL DEL STARTUP")
            
            if summary_index != -1:
                mcp_state_manager_code = '''    # ==========================================
    # INICIALIZACIÓN MCP STATE MANAGER
    # ==========================================
    
    # Crear e inicializar mcp_state_manager global
    try:
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        mcp_state_manager = get_conversation_state_manager()
        
        if mcp_state_manager:
            logger.info("✅ MCP State Manager inicializado correctamente")
        else:
            logger.warning("⚠️ MCP State Manager no disponible")
            
    except Exception as mcp_state_error:
        logger.error(f"❌ Error inicializando MCP State Manager: {mcp_state_error}")
        mcp_state_manager = None
    
    '''
                content = content[:summary_index] + mcp_state_manager_code + content[summary_index:]
                print("✅ Step 3: Added mcp_state_manager initialization before summary")
        
        # PASO 4: Agregar mcp_state_manager al logging del resumen final
        # Buscar la sección del resumen y agregar la línea
        if "logger.info(f\"   {'✅' if personalization_engine else '❌'} Personalization:" in content:
            pattern = r"(logger\.info\(f\"   \{'✅' if personalization_engine else '❌'\} Personalization: \{'Disponible' if personalization_engine else 'No disponible'\}\"\))"
            replacement = r'''\1
    logger.info(f"   {'✅' if mcp_state_manager else '❌'} MCP State Manager: {'Disponible' if mcp_state_manager else 'No disponible'}")'''
            
            content = re.sub(pattern, replacement, content)
            print("✅ Step 4: Added mcp_state_manager to startup summary logging")
        
        # Escribir archivo modificado
        with open(main_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Fix applied successfully to {main_file}")
        
        # Verificar que el fix se aplicó correctamente
        with open(main_file, 'r', encoding='utf-8') as f:
            updated_content = f.read()
        
        checks = [
            ("Global variable declaration", "mcp_state_manager = None" in updated_content),
            ("Global in startup", "global redis_client, product_cache, hybrid_recommender, mcp_recommender, mcp_state_manager" in updated_content),
            ("Initialization code", "mcp_state_manager = get_conversation_state_manager()" in updated_content),
            ("Summary logging", "MCP State Manager:" in updated_content)
        ]
        
        print("\n📋 VERIFICATION:")
        all_passed = True
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"   {status} {check_name}")
            if not passed:
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Error applying fix: {e}")
        return False

def create_test_script():
    """Crea script para validar el fix"""
    
    test_script = '''#!/usr/bin/env python3
"""
VALIDATION SCRIPT: mcp_state_manager fix verification
"""

import sys
sys.path.append('src')

def test_mcp_state_manager_availability():
    """Test que mcp_state_manager está disponible en main_unified_redis"""
    
    print("🔍 TESTING MCP_STATE_MANAGER AVAILABILITY IN MAIN_UNIFIED_REDIS")
    print("=" * 70)
    
    try:
        # Importar main_unified_redis
        from src.api import main_unified_redis
        
        # Verificar si mcp_state_manager existe
        has_mcp_state_manager = hasattr(main_unified_redis, 'mcp_state_manager')
        
        print(f"📋 mcp_state_manager attribute exists: {has_mcp_state_manager}")
        
        if has_mcp_state_manager:
            mcp_state_manager = getattr(main_unified_redis, 'mcp_state_manager')
            print(f"📋 mcp_state_manager type: {type(mcp_state_manager) if mcp_state_manager else 'None'}")
            
            if mcp_state_manager:
                print("✅ SUCCESS: mcp_state_manager is available and initialized")
                return True
            else:
                print("⚠️ PARTIAL: mcp_state_manager exists but is None")
                return False
        else:
            print("❌ FAILED: mcp_state_manager attribute does not exist")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_mcp_state_manager_availability()
    
    if success:
        print("\\n🎉 FIX VERIFICATION SUCCESSFUL")
        print("mcp_state_manager is now available in main_unified_redis")
        print("\\n🎯 Next steps:")
        print("   1. Restart the server: python src/api/main_unified_redis.py")
        print("   2. Test conversation state persistence")
        print("   3. Re-run Phase 2 validation")
    else:
        print("\\n❌ FIX VERIFICATION FAILED")
        print("mcp_state_manager is still not properly available")
    
    sys.exit(0 if success else 1)
'''
    
    with open("C:/Users/yasma/Desktop/retail-recommender-system/test_mcp_state_manager_fix.py", 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print("✅ Created test script: test_mcp_state_manager_fix.py")

def main():
    """Función principal"""
    
    print("🚀 MCP STATE MANAGER FIX FOR CONVERSATION PERSISTENCE")
    print("🎯 Goal: Add mcp_state_manager as global variable in main_unified_redis.py")
    print("=" * 80)
    
    # Aplicar el fix
    success = apply_mcp_state_manager_fix()
    
    if success:
        print(f"\n✅ FIX APPLIED SUCCESSFULLY!")
        print("📋 Changes made:")
        print("   1. Added mcp_state_manager global variable declaration")
        print("   2. Added mcp_state_manager to startup global declaration")
        print("   3. Added mcp_state_manager initialization in startup")
        print("   4. Added mcp_state_manager to startup summary logging")
        
        # Crear script de test
        create_test_script()
        
        print(f"\n🎯 NEXT STEPS:")
        print("   1. Restart the server")
        print("   2. Run: python test_mcp_state_manager_fix.py")
        print("   3. Test conversation state persistence")
        print("   4. Re-run Phase 2 validation")
        
        return True
    else:
        print(f"\n❌ FIX APPLICATION FAILED")
        print("📋 Manual intervention required")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
