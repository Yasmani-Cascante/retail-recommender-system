#!/usr/bin/env python3
"""
Diagnóstico: Estado de Importación ObservabilityManager
=====================================================

Verifica específicamente si ObservabilityManager se importa correctamente
en main_unified_redis.py y el estado de OBSERVABILITY_MANAGER_AVAILABLE
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.append('src')

def test_direct_import():
    """Test directo de importación de ObservabilityManager"""
    
    print("🔍 DIAGNÓSTICO: Importación Directa ObservabilityManager")
    print("=" * 60)
    
    try:
        from api.core.observability_manager import get_observability_manager
        print("✅ Importación directa: SUCCESS")
        
        # Test de instanciación
        observability = get_observability_manager()
        print("✅ Instanciación: SUCCESS")
        
        # Verificar metrics_collector
        if hasattr(observability, 'metrics_collector'):
            print("✅ metrics_collector attribute: EXISTS")
        else:
            print("❌ metrics_collector attribute: MISSING")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Error en importación directa: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_main_unified_redis_import():
    """Test de importación desde main_unified_redis.py"""
    
    print(f"\n🚀 DIAGNÓSTICO: Importación en main_unified_redis.py")
    print("=" * 55)
    
    try:
        # Importar el módulo main_unified_redis
        from api import main_unified_redis
        print("✅ Importación main_unified_redis module: SUCCESS")
        
        # Verificar la variable OBSERVABILITY_MANAGER_AVAILABLE
        if hasattr(main_unified_redis, 'OBSERVABILITY_MANAGER_AVAILABLE'):
            available = main_unified_redis.OBSERVABILITY_MANAGER_AVAILABLE
            print(f"✅ OBSERVABILITY_MANAGER_AVAILABLE variable: EXISTS")
            print(f"   Valor: {available}")
            
            if available:
                print("✅ ObservabilityManager: DISPONIBLE EN MAIN")
                
                # Test adicional: verificar que get_observability_manager funciona
                try:
                    from api.core.observability_manager import get_observability_manager
                    observability = get_observability_manager()
                    print("✅ get_observability_manager(): FUNCIONAL")
                    
                    # Verificar que el middleware puede usarlo
                    if hasattr(observability, 'metrics_collector'):
                        print("✅ metrics_collector en main context: DISPONIBLE")
                        return True
                    else:
                        print("❌ metrics_collector en main context: NO DISPONIBLE")
                        return False
                        
                except Exception as e:
                    print(f"❌ Error usando get_observability_manager en main: {e}")
                    return False
            else:
                print("❌ ObservabilityManager: NO DISPONIBLE EN MAIN")
                return False
        else:
            print("❌ OBSERVABILITY_MANAGER_AVAILABLE variable: NOT FOUND")
            return False
            
    except Exception as e:
        print(f"❌ Error importando main_unified_redis: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_middleware_compatibility():
    """Test de que el middleware puede usar ObservabilityManager"""
    
    print(f"\n🔧 DIAGNÓSTICO: Compatibilidad Middleware")
    print("=" * 45)
    
    try:
        # Simular lo que hace el middleware
        from api import main_unified_redis
        
        if main_unified_redis.OBSERVABILITY_MANAGER_AVAILABLE:
            from api.core.observability_manager import get_observability_manager
            observability = get_observability_manager()
            
            print("✅ ObservabilityManager disponible para middleware")
            
            # Test del método que usará el middleware
            if hasattr(observability, 'metrics_collector'):
                collector = observability.metrics_collector
                
                if hasattr(collector, 'record_request'):
                    print("✅ metrics_collector.record_request: MÉTODO DISPONIBLE")
                    print("✅ Middleware será FUNCIONAL")
                    return True
                else:
                    print("❌ metrics_collector.record_request: MÉTODO NO DISPONIBLE")
                    return False
            else:
                print("❌ metrics_collector: ATRIBUTO NO DISPONIBLE")
                return False
        else:
            print("❌ OBSERVABILITY_MANAGER_AVAILABLE = False")
            print("❌ Middleware usará fallback")
            return False
            
    except Exception as e:
        print(f"❌ Error en test de middleware: {e}")
        return False

def test_startup_logs_simulation():
    """Simula los logs que aparecerían en startup"""
    
    print(f"\n📊 DIAGNÓSTICO: Simulación Startup Logs")
    print("=" * 45)
    
    try:
        # Simular importación como en main_unified_redis
        import logging
        
        # Configurar logging temporal para capturar mensajes
        logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
        logger = logging.getLogger(__name__)
        
        print("Simulando try/except block de main_unified_redis.py:")
        print()
        
        try:
            from api.core.observability_manager import get_observability_manager
            OBSERVABILITY_MANAGER_AVAILABLE = True
            print("✅ INFO: ObservabilityManager loaded - Single source of truth enabled")
            
            # Test adicional que confirme funcionalidad
            observability = get_observability_manager()
            if hasattr(observability, 'metrics_collector'):
                print("✅ INFO: MetricsCollector integrated successfully")
            
            return True
            
        except ImportError as e:
            OBSERVABILITY_MANAGER_AVAILABLE = False
            print(f"⚠️ WARNING: ObservabilityManager not available: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Error en simulación: {e}")
        return False

def run_complete_diagnosis():
    """Ejecuta diagnóstico completo"""
    
    print("🎯 DIAGNÓSTICO COMPLETO - Estado ObservabilityManager Import")
    print("=" * 70)
    
    results = []
    
    # Test 1: Importación directa
    test1 = test_direct_import()
    results.append(("Importación Directa", test1))
    
    # Test 2: Importación en main_unified_redis
    test2 = test_main_unified_redis_import()
    results.append(("Importación en main_unified_redis", test2))
    
    # Test 3: Compatibilidad middleware
    test3 = test_middleware_compatibility()
    results.append(("Compatibilidad Middleware", test3))
    
    # Test 4: Simulación startup logs
    test4 = test_startup_logs_simulation()
    results.append(("Startup Logs Simulation", test4))
    
    # Resumen final
    print(f"\n📊 RESUMEN DEL DIAGNÓSTICO")
    print("=" * 30)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 RESULTADO FINAL: {passed}/{total} tests PASSED")
    
    if passed == total:
        print("\n🎉 OBSERVABILITY MANAGER COMPLETAMENTE FUNCIONAL")
        print("   ✅ Importación: EXITOSA")
        print("   ✅ OBSERVABILITY_MANAGER_AVAILABLE: True")
        print("   ✅ Middleware: COMPATIBLE")
        print("   ✅ metrics_collector: FUNCIONAL")
        print("\n💡 ACCIÓN RECOMENDADA:")
        print("   Reinicia el servidor para ver los logs de startup:")
        print("   python src/api/main_unified_redis.py")
    else:
        print("\n⚠️ PROBLEMAS DETECTADOS")
        print("   Revisa los errores específicos arriba")
        print("   Es posible que necesites:")
        print("   1. Verificar la sintaxis en observability_manager.py")
        print("   2. Verificar imports en main_unified_redis.py")
        print("   3. Reiniciar el intérprete de Python")
    
    return passed == total

if __name__ == "__main__":
    result = run_complete_diagnosis()
    sys.exit(0 if result else 1)
