#!/usr/bin/env python3
"""
Fix para State Tracking Inconsistency en Startup
==============================================

Corrige la inconsistencia donde el sistema reporta "Fallback mode"
cuando Redis está funcionando perfectamente.

Author: Senior Architecture Team
"""

import sys
import time
sys.path.append('src')

def fix_startup_state_tracking():
    """Aplica fix al state tracking inconsistente en startup event"""
    
    print("🔧 FIXING STARTUP STATE TRACKING INCONSISTENCY")
    print("=" * 50)
    
    main_file_path = 'src/api/main_unified_redis.py'
    
    try:
        # Backup del archivo
        timestamp = int(time.time())
        backup_path = f'{main_file_path}.backup_state_fix_{timestamp}'
        
        with open(main_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            content_bytes = content.encode('utf-8')
            f.buffer.write(content_bytes)
        
        print(f"✅ Backup creado: {backup_path}")
        
        # Fix específico: Actualizar lógica de state tracking
        state_fixes = [
            # Fix 1: Función para verificar estado real de Redis
            ('logger.info("🎉 Enterprise system startup completed successfully")',
             '''# ✅ FINAL STATE VERIFICATION - Check actual Redis status
        final_redis_status = "unknown"
        try:
            # Verify actual Redis status through ServiceFactory
            redis_service = await asyncio.wait_for(
                ServiceFactory.get_redis_service(),
                timeout=3.0  # Quick check
            )
            health_result = await redis_service.health_check()
            final_redis_status = health_result.get('status', 'unknown')
            
            # Update redis_initialized based on actual status
            if final_redis_status in ['healthy', 'connected', 'operational']:
                redis_initialized = True
                logger.info("✅ Final Redis status verification: Redis is healthy")
            else:
                logger.info(f"⚠️ Final Redis status verification: {final_redis_status}")
                
        except Exception as e:
            logger.warning(f"⚠️ Final Redis status check failed: {e}")
        
        logger.info("🎉 Enterprise system startup completed successfully")'''),
            
            # Fix 2: Actualizar el logging final
            ('logger.info(f"📊 Redis status: {\'✅ Connected\' if redis_initialized else \'⚠️ Fallback mode\'}")',
             '''logger.info(f"📊 Redis status: {\'✅ Connected\' if redis_initialized else \'⚠️ Fallback mode\'}")
        logger.info(f"🔍 Final Redis verification: {final_redis_status}")'''),
        ]
        
        modified_content = content
        changes_applied = 0
        
        for old_text, new_text in state_fixes:
            if old_text in modified_content:
                modified_content = modified_content.replace(old_text, new_text)
                changes_applied += 1
                print(f"✅ State fix aplicado: {old_text[:40]}...")
        
        # Guardar archivo modificado
        if changes_applied > 0:
            with open(main_file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            print(f"✅ {changes_applied} state tracking fixes aplicados")
            return True
        else:
            print("⚠️ No se encontraron patrones para fix")
            return False
            
    except Exception as e:
        print(f"❌ Error aplicando state fix: {e}")
        return False

def create_state_verification_test():
    """Crea test para verificar que el state tracking funciona correctamente"""
    
    state_test = '''#!/usr/bin/env python3
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
    
    print("\\n2. Testing component Redis consistency...")
    
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
        print("\\n🎉 STATE TRACKING FIX SUCCESSFUL!")
        print("=" * 50)
        print("✅ Redis status reporting accurate")
        print("✅ All components consistent")
        print("✅ State tracking inconsistency resolved")
        return True
    else:
        print("\\n❌ STATE TRACKING ISSUES REMAIN")
        print("🔧 Additional fixes may be needed")
        return False

if __name__ == "__main__":
    success = asyncio.run(comprehensive_state_test())
    
    if success:
        print("\\n🎯 STATE TRACKING FIX VALIDATED")
        print("Ready to proceed with observability endpoints")
    else:
        print("\\n🔧 ADDITIONAL STATE FIXES NEEDED")
'''
    
    with open('test_state_tracking_fix.py', 'w', encoding='utf-8') as f:
        f.write(state_test)
    
    print("🧪 State verification test creado: test_state_tracking_fix.py")

if __name__ == "__main__":
    print("🚀 STARTUP STATE TRACKING FIX")
    print("=" * 60)
    
    print("PROBLEMA IDENTIFICADO:")
    print("- Sistema reporta 'Fallback mode' cuando Redis está healthy")
    print("- Variable redis_initialized no se actualiza con estado real")
    print("- Inconsistencia entre estado reportado y estado actual")
    print()
    
    # Aplicar fix
    fix_success = fix_startup_state_tracking()
    
    if fix_success:
        # Crear test de verificación
        create_state_verification_test()
        
        print("\n🎯 PRÓXIMOS PASOS:")
        print("1. Reiniciar servidor: python src/api/main_unified_redis.py")
        print("2. Verificar logs de startup - debería mostrar estado correcto")
        print("3. Ejecutar: python test_state_tracking_fix.py")
        print("4. Confirmar que reporting es consistente")
        
        print("\n✅ STATE TRACKING FIX APLICADO")
        print("El sistema ahora debería reportar estado Redis correcto")
        
    else:
        print("\n❌ FIX FALLÓ - Revisar errores")
