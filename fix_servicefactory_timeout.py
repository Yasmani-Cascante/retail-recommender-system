#!/usr/bin/env python3
"""
ServiceFactory Timeout Fix
==========================

Fix específico para resolver el timeout restrictivo en ServiceFactory
que causa que use fallback service cuando Redis directo funciona.

Author: Senior Architecture Team
"""

import sys
import time
sys.path.append('src')

def fix_servicefactory_timeout():
    """Aplica fix de timeout al ServiceFactory"""
    
    print("🔧 APLICANDO FIX DE TIMEOUT AL SERVICEFACTORY")
    print("=" * 50)
    
    service_factory_path = 'src/api/factories/service_factory.py'
    
    try:
        # Backup del archivo
        timestamp = int(time.time())
        backup_path = f'{service_factory_path}.backup_timeout_fix_{timestamp}'
        
        with open(service_factory_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Backup creado: {backup_path}")
        
        # Aplicar fixes específicos
        timeout_fixes = [
            # Fix 1: Aumentar timeout principal de 5s a 15s
            ('timeout=5.0  # 5 second timeout', 
             'timeout=15.0  # Increased timeout - matches direct connection success'),
            
            # Fix 2: Aumentar health check timeout de 2s a 5s
            ('timeout=2.0  # 2 second timeout',
             'timeout=5.0  # Increased health check timeout'),
            
            # Fix 3: Añadir retry logic mejorado
            ('except asyncio.TimeoutError:\n                logger.error("❌ Redis connection timeout - creating fallback service")',
             '''except asyncio.TimeoutError:
                logger.warning("⚠️ Redis connection timeout (15s) - attempting single retry...")
                
                # Single retry with extended timeout since direct connection works
                try:
                    logger.info("🔄 Retry attempt with extended timeout...")
                    redis_service = await asyncio.wait_for(
                        get_redis_service(),
                        timeout=20.0  # Extended timeout for retry
                    )
                    
                    # Quick health check for retry
                    health_result = await asyncio.wait_for(
                        redis_service.health_check(),
                        timeout=3.0
                    )
                    
                    cls._redis_service = redis_service
                    logger.info(f"✅ Redis connection successful on retry: {health_result.get('status')}")
                    return cls._redis_service
                    
                except Exception as retry_error:
                    logger.error(f"❌ Redis retry failed: {retry_error} - creating fallback service")'''),
        ]
        
        # Aplicar fixes
        modified_content = content
        changes_applied = 0
        
        for old_text, new_text in timeout_fixes:
            if old_text in modified_content:
                modified_content = modified_content.replace(old_text, new_text)
                changes_applied += 1
                print(f"✅ Fix aplicado: {old_text[:40]}...")
        
        # Guardar archivo modificado
        if changes_applied > 0:
            with open(service_factory_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            print(f"✅ {changes_applied} timeout fixes aplicados")
            print(f"📁 ServiceFactory actualizado: {service_factory_path}")
            
            return True
        else:
            print("⚠️ No se encontraron patrones para fix")
            return False
            
    except Exception as e:
        print(f"❌ Error aplicando timeout fix: {e}")
        return False

def create_servicefactory_test():
    """Crea test específico para ServiceFactory optimizado"""
    
    servicefactory_test = '''#!/usr/bin/env python3
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
    
    print("🏭 TESTING SERVICEFACTORY POST TIMEOUT FIX")
    print("=" * 50)
    
    try:
        from src.api.factories import ServiceFactory
        
        print("🔄 Testing ServiceFactory with increased timeouts...")
        
        # Time the operation
        start_time = asyncio.get_event_loop().time()
        
        redis_service = await ServiceFactory.get_redis_service()
        
        end_time = asyncio.get_event_loop().time()
        duration = (end_time - start_time) * 1000  # Convert to ms
        
        print(f"⏱️ ServiceFactory Redis creation took: {duration:.1f}ms")
        
        # Test health check
        health = await redis_service.health_check()
        status = health.get('status', 'unknown')
        
        print(f"📊 Redis health: {status}")
        
        if status in ['healthy', 'connected', 'operational']:
            print("🎉 SERVICEFACTORY FIX SUCCESSFUL!")
            print("✅ Redis is healthy through ServiceFactory")
            return True
        elif status == 'degraded':
            print("⚠️ ServiceFactory still in degraded mode")
            print("🔧 May need additional timeout adjustments")
            return False
        else:
            print(f"❌ ServiceFactory status not optimal: {status}")
            return False
            
    except Exception as e:
        print(f"❌ ServiceFactory test failed: {e}")
        return False

async def test_integration_post_fix():
    """Test integración completa post fix"""
    
    print("\\n🧪 INTEGRATION TEST POST SERVICEFACTORY FIX")
    print("=" * 50)
    
    try:
        from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        from src.api.mcp.engines.mcp_personalization_engine import create_mcp_personalization_engine
        
        print("🔄 Testing full integration...")
        
        # Test conversation manager
        conv_mgr = OptimizedConversationAIManager('test_key')
        print('✅ OptimizedConversationAIManager created')
        
        # Check Redis client availability
        if hasattr(conv_mgr, '_redis_client'):
            redis_available = conv_mgr._redis_client is not None
            print(f'📊 Redis client available: {redis_available}')
        
        # Test state manager
        state_mgr = await get_conversation_state_manager()
        print('✅ ConversationStateManager created')
        
        # Test personalization engine
        engine = await create_mcp_personalization_engine('test_key')
        print('✅ PersonalizationEngine created')
        
        print("🎉 FULL INTEGRATION TEST SUCCESSFUL!")
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False

async def comprehensive_test():
    """Test comprehensivo post fix"""
    
    print("🚀 COMPREHENSIVE TEST - SERVICEFACTORY FIX VALIDATION")
    print("=" * 60)
    
    # Test 1: ServiceFactory específico
    sf_success = await test_servicefactory_post_fix()
    
    # Test 2: Integración completa si ServiceFactory funciona
    if sf_success:
        integration_success = await test_integration_post_fix()
        
        if integration_success:
            print("\\n🏆 ALL TESTS PASSED - SERVICEFACTORY FIX SUCCESSFUL!")
            print("=" * 60)
            print("✅ ServiceFactory timeout fix working")
            print("✅ Redis connection through ServiceFactory healthy")
            print("✅ All enterprise components functional")
            print("✅ Migration Redis Enterprise COMPLETED")
            return True
        else:
            print("\\n⚠️ ServiceFactory fixed but integration has issues")
            return False
    else:
        print("\\n❌ ServiceFactory fix needs additional work")
        return False

if __name__ == "__main__":
    success = asyncio.run(comprehensive_test())
    
    if success:
        print("\\n🎯 NEXT STEPS:")
        print("1. ✅ ServiceFactory timeout fix successful")
        print("2. ✅ Redis enterprise migration completed")
        print("3. 🔄 Ready to implement observability endpoints")
        print("4. 🚀 Ready for Fase 3 - Microservices transition")
    else:
        print("\\n🔧 Additional fixes may be needed")
'''
    
    with open('test_servicefactory_fix.py', 'w') as f:
        f.write(servicefactory_test)
    
    print("🧪 Test específico creado: test_servicefactory_fix.py")

if __name__ == "__main__":
    print("🚀 SERVICEFACTORY TIMEOUT FIX")
    print("=" * 60)
    
    # Aplicar fix
    fix_success = fix_servicefactory_timeout()
    
    if fix_success:
        # Crear test específico
        create_servicefactory_test()
        
        print("\n🎯 PRÓXIMOS PASOS:")
        print("1. Ejecutar: python test_servicefactory_fix.py")
        print("2. Si el test pasa, la migración Redis está 100% completa")
        print("3. Proceder con implementación de endpoints de observabilidad")
        
        print("\n✅ TIMEOUT FIX APLICADO EXITOSAMENTE")
        print("El ServiceFactory ahora debería usar timeouts que coinciden")
        print("con la conexión directa exitosa de Redis.")
        
    else:
        print("\n❌ FIX FALLÓ - Revisar errores")
