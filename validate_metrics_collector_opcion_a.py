#!/usr/bin/env python3
"""
Validación: Implementación Completa MetricsCollector (Opción A)
============================================================

Valida que la implementación completa del MetricsCollector funciona correctamente
y que el ObservabilityManager tiene el atributo metrics_collector funcional.
"""

import sys
import os
import asyncio
import time
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Añadir src al path
sys.path.append('src')

async def test_metrics_collector_standalone():
    """Test del MetricsCollector independiente"""
    
    print("🔧 VALIDACIÓN: MetricsCollector Standalone")
    print("=" * 50)
    
    try:
        from api.core.observability_manager import MetricsCollector
        print("✅ Importación MetricsCollector: SUCCESS")
        
        # Test de instanciación
        collector = MetricsCollector()
        print("✅ Instanciación MetricsCollector: SUCCESS")
        
        # Test de método record_request
        await collector.record_request(
            success=True,
            response_time_ms=150.5,
            user_id="test_user",
            market_id="US",
            endpoint="/test/endpoint"
        )
        print("✅ Método record_request: SUCCESS")
        
        # Test de métricas básicas
        metrics = collector.get_current_metrics()
        print(f"✅ get_current_metrics: SUCCESS")
        print(f"   Total requests: {metrics['total_requests']}")
        print(f"   Successful requests: {metrics['successful_requests']}")
        print(f"   Error rate: {metrics['error_rate']:.3f}")
        print(f"   Avg response time: {metrics['average_response_time_ms']:.1f}ms")
        
        # Test adicional con fallo
        await collector.record_request(
            success=False,
            response_time_ms=300.0,
            error_type="timeout",
            endpoint="/test/endpoint"
        )
        
        metrics_updated = collector.get_current_metrics()
        print(f"✅ Métricas después de fallo:")
        print(f"   Total requests: {metrics_updated['total_requests']}")
        print(f"   Error rate: {metrics_updated['error_rate']:.3f}")
        
        return metrics_updated['total_requests'] == 2 and metrics_updated['error_rate'] == 0.5
        
    except Exception as e:
        print(f"❌ Error en test MetricsCollector: {e}")
        return False

async def test_observability_manager_integration():
    """Test de integración ObservabilityManager + MetricsCollector"""
    
    print(f"\n🎯 VALIDACIÓN: ObservabilityManager Integration")
    print("=" * 50)
    
    try:
        from api.core.observability_manager import get_observability_manager
        print("✅ Importación get_observability_manager: SUCCESS")
        
        # Test de instanciación
        observability = get_observability_manager()
        print("✅ Instanciación ObservabilityManager: SUCCESS")
        
        # Verificar que tiene metrics_collector
        if hasattr(observability, 'metrics_collector'):
            print("✅ Atributo metrics_collector: EXISTS")
        else:
            print("❌ Atributo metrics_collector: NOT FOUND")
            return False
        
        # Test del método record_request
        await observability.metrics_collector.record_request(
            success=True,
            response_time_ms=250.0,
            user_id="integration_test",
            market_id="ES",
            endpoint="/v1/mcp/conversation"
        )
        print("✅ metrics_collector.record_request: SUCCESS")
        
        # Test de get_unified_state
        unified_state = await observability.get_unified_state(force_refresh=True)
        print("✅ get_unified_state: SUCCESS")
        print(f"   Overall status: {unified_state.overall_status}")
        print(f"   Total requests: {unified_state.total_requests}")
        print(f"   Error rate: {unified_state.error_rate:.3f}")
        
        # Test de endpoints response methods
        health_response = await observability.get_health_response()
        print("✅ get_health_response: SUCCESS")
        
        metrics_response = await observability.get_metrics_response()
        print("✅ get_metrics_response: SUCCESS")
        
        loadtest_response = await observability.get_loadtest_response()
        print("✅ get_loadtest_response: SUCCESS")
        print(f"   Loadtest ready: {loadtest_response['loadtest_ready']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en test ObservabilityManager: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_main_unified_redis_compatibility():
    """Test de que main_unified_redis puede importar sin errores"""
    
    print(f"\n🚀 VALIDACIÓN: main_unified_redis Compatibility")
    print("=" * 50)
    
    try:
        # Test de importación
        from api.main_unified_redis import app, OBSERVABILITY_MANAGER_AVAILABLE
        print("✅ Importación main_unified_redis: SUCCESS")
        print(f"   OBSERVABILITY_MANAGER_AVAILABLE: {OBSERVABILITY_MANAGER_AVAILABLE}")
        
        if OBSERVABILITY_MANAGER_AVAILABLE:
            from api.core.observability_manager import get_observability_manager
            observability = get_observability_manager()
            
            if hasattr(observability, 'metrics_collector'):
                print("✅ metrics_collector disponible en main: SUCCESS")
                return True
            else:
                print("❌ metrics_collector NO disponible en main")
                return False
        else:
            print("⚠️ ObservabilityManager no está disponible")
            return False
        
    except Exception as e:
        print(f"❌ Error en test main_unified_redis: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_comprehensive_validation():
    """Ejecuta validación comprehensiva de la implementación"""
    
    print("🎯 VALIDACIÓN COMPREHENSIVA - MetricsCollector Implementación Completa")
    print("=" * 80)
    
    results = []
    
    # Test 1: MetricsCollector standalone
    test1 = await test_metrics_collector_standalone()
    results.append(("MetricsCollector Standalone", test1))
    
    # Test 2: ObservabilityManager integration
    test2 = await test_observability_manager_integration()
    results.append(("ObservabilityManager Integration", test2))
    
    # Test 3: main_unified_redis compatibility
    test3 = test_main_unified_redis_compatibility()
    results.append(("main_unified_redis Compatibility", test3))
    
    # Resumen final
    print(f"\n📊 RESUMEN DE VALIDACIÓN")
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
        print("🎉 IMPLEMENTACIÓN COMPLETA EXITOSA")
        print("   ✅ MetricsCollector: FUNCIONAL")
        print("   ✅ ObservabilityManager: INTEGRADO")
        print("   ✅ main_unified_redis: COMPATIBLE")
        print("   ✅ Error 'metrics_collector' attribute: RESUELTO")
    else:
        print("⚠️ IMPLEMENTACIÓN NECESITA CORRECCIONES")
        print("   Revisa los errores reportados arriba")
    
    return passed == total

if __name__ == "__main__":
    result = asyncio.run(run_comprehensive_validation())
    sys.exit(0 if result else 1)
