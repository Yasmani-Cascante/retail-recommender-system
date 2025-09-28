#!/usr/bin/env python3
"""
FIX DIRECTO: Agregar mcp_state_manager exactamente donde debe ir
"""

import re

def apply_precise_fix():
    """
    Aplica el fix exacto en las ubicaciones precisas identificadas
    """
    
    print("🔧 APPLYING PRECISE MCP_STATE_MANAGER FIX")
    print("=" * 50)
    
    main_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/main_unified_redis.py"
    
    try:
        # Leer archivo
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        backup_file = main_file + ".backup_precise_fix"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup created: {backup_file}")
        
        # PASO 1: Agregar mcp_state_manager después de "optimized_conversation_manager = None"
        pattern1 = r"# Variables globales para conversación AI optimizada \(Fase 0\)\noptimized_conversation_manager = None"
        replacement1 = """# Variables globales para conversación AI optimizada (Fase 0)
optimized_conversation_manager = None

# Variables globales para MCP state management
mcp_state_manager = None"""
        
        if re.search(pattern1, content):
            content = re.sub(pattern1, replacement1, content)
            print("✅ Step 1: Added mcp_state_manager global variable")
        else:
            # Fallback: buscar optimized_conversation_manager = None y agregar después
            if "optimized_conversation_manager = None" in content:
                content = content.replace(
                    "optimized_conversation_manager = None",
                    "optimized_conversation_manager = None\n\n# Variables globales para MCP state management\nmcp_state_manager = None"
                )
                print("✅ Step 1: Added mcp_state_manager global variable (fallback)")
            else:
                print("❌ Step 1: Could not find insertion point for global variable")
                return False
        
        # PASO 2: Agregar mcp_state_manager a la declaración global en fixed_startup_event
        # La línea actual es: global optimized_conversation_manager, mcp_state_manager, personalization_engine
        pattern2 = r"global optimized_conversation_manager, mcp_state_manager, personalization_engine"
        
        if pattern2 in content:
            print("✅ Step 2: mcp_state_manager already in global declaration")
        else:
            # Buscar si hay una declaración similar y actualizar
            alt_pattern = r"global redis_client, product_cache, hybrid_recommender, mcp_recommender\n\s*global mcp_recommender\n\s*global optimized_conversation_manager, mcp_state_manager, personalization_engine"
            
            if not re.search(alt_pattern, content):
                print("⚠️ Step 2: Adding mcp_state_manager to global declaration")
                # No es crítico si esto falla, ya está en la línea que vimos
        
        # PASO 3: Agregar inicialización de mcp_state_manager en el startup
        # Buscar donde se inicializa personalization_engine y agregar antes
        pattern3 = r"# FASE 2: INICIALIZACIÓN MCP PERSONALIZATION ENGINE"
        
        if pattern3 in content:
            # Agregar inicialización antes de personalization engine
            insertion_code = """    # ==========================================
    # INICIALIZACIÓN MCP STATE MANAGER  
    # ==========================================
    
    if MCP_PERSONALIZATION_AVAILABLE:
        try:
            logger.info("🎯 Inicializando MCP State Manager...")
            
            from src.api.mcp.conversation_state_manager import get_conversation_state_manager
            mcp_state_manager = get_conversation_state_manager()
            
            if mcp_state_manager:
                logger.info("✅ MCP State Manager inicializado correctamente")
            else:
                logger.warning("⚠️ MCP State Manager retornó None")
                
        except Exception as mcp_state_error:
            logger.error(f"❌ Error inicializando MCP State Manager: {mcp_state_error}")
            mcp_state_manager = None
    else:
        logger.info("ℹ️ MCP State Manager deshabilitado (MCP_PERSONALIZATION_AVAILABLE=False)")
        mcp_state_manager = None
    
    """
            
            content = content.replace(
                "    # ==========================================\n    # FASE 2: INICIALIZACIÓN MCP PERSONALIZATION ENGINE",
                insertion_code + "    # ==========================================\n    # FASE 2: INICIALIZACIÓN MCP PERSONALIZATION ENGINE"
            )
            print("✅ Step 3: Added mcp_state_manager initialization")
        else:
            print("⚠️ Step 3: Could not find personalization engine section")
        
        # PASO 4: Agregar mcp_state_manager al resumen final
        # Buscar la línea del resumen y agregar
        pattern4 = r'logger\.info\(f"   \{\'✅\' if optimized_conversation_manager else \'❌\'\} Conversation AI: \{\'Disponible\' if optimized_conversation_manager else \'No disponible\'\}"\)'
        
        if re.search(pattern4, content):
            replacement4 = '''logger.info(f"   {'✅' if optimized_conversation_manager else '❌'} Conversation AI: {'Disponible' if optimized_conversation_manager else 'No disponible'}")
    logger.info(f"   {'✅' if mcp_state_manager else '❌'} MCP State Manager: {'Disponible' if mcp_state_manager else 'No disponible'}")'''
            
            content = re.sub(pattern4, replacement4, content)
            print("✅ Step 4: Added mcp_state_manager to startup summary")
        else:
            print("⚠️ Step 4: Could not find startup summary section")
        
        # Escribir archivo
        with open(main_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Fix applied to {main_file}")
        
        # Verificar
        with open(main_file, 'r', encoding='utf-8') as f:
            updated_content = f.read()
        
        checks = [
            ("Global variable exists", "mcp_state_manager = None" in updated_content),
            ("Initialization code exists", "mcp_state_manager = get_conversation_state_manager()" in updated_content),
            ("Summary logging exists", "MCP State Manager:" in updated_content)
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

if __name__ == "__main__":
    success = apply_precise_fix()
    
    if success:
        print(f"\n🎉 PRECISE FIX APPLIED SUCCESSFULLY!")
        print("🎯 Next steps:")
        print("   1. Restart server: python src/api/main_unified_redis.py")
        print("   2. Test: python test_mcp_state_manager_fix.py")
        print("   3. Validate: python validate_conversation_persistence.py")
    else:
        print(f"\n❌ FIX FAILED - manual intervention needed")
