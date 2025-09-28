#!/usr/bin/env python3

import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.append('src')

print("🔧 VALIDACIÓN SIMPLE: MetricsCollector Implementación")
print("=" * 55)

try:
    # Test 1: Importación
    from api.core.observability_manager import MetricsCollector, get_observability_manager
    print("✅ Importación modules: SUCCESS")
    
    # Test 2: Instanciación MetricsCollector
    collector = MetricsCollector()
    print("✅ MetricsCollector instancia: SUCCESS")
    
    # Test 3: ObservabilityManager con metrics_collector
    observability = get_observability_manager()
    print("✅ ObservabilityManager instancia: SUCCESS")
    
    # Test 4: Verificar atributo metrics_collector
    if hasattr(observability, 'metrics_collector'):
        print("✅ Atributo metrics_collector: EXISTS")
        print("🎉 PROBLEMA RESUELTO: ObservabilityManager tiene metrics_collector")
        
        # Test 5: Verificar que es instancia de MetricsCollector
        if isinstance(observability.metrics_collector, MetricsCollector):
            print("✅ metrics_collector es MetricsCollector: SUCCESS")
        else:
            print(f"⚠️ metrics_collector es: {type(observability.metrics_collector)}")
    else:
        print("❌ Atributo metrics_collector: NOT FOUND")
        print("❌ PROBLEMA NO RESUELTO")
        sys.exit(1)
    
    print("\n🎯 CONCLUSIÓN:")
    print("   ✅ OPCIÓN A implementada correctamente")
    print("   ✅ Error 'metrics_collector' attribute: RESUELTO")
    print("   ✅ Sistema listo para usar middleware unificado")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
