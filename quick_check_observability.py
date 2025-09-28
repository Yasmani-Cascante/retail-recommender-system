#!/usr/bin/env python3
"""
Quick Check: Estado OBSERVABILITY_MANAGER_AVAILABLE
==================================================
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.append('src')

print("🔍 QUICK CHECK: Estado ObservabilityManager en main_unified_redis")
print("=" * 65)

try:
    # Importar main_unified_redis y verificar las variables
    from api import main_unified_redis
    
    print("✅ Importación main_unified_redis: SUCCESS")
    
    # Verificar OBSERVABILITY_MANAGER_AVAILABLE
    if hasattr(main_unified_redis, 'OBSERVABILITY_MANAGER_AVAILABLE'):
        available = main_unified_redis.OBSERVABILITY_MANAGER_AVAILABLE
        print(f"📊 OBSERVABILITY_MANAGER_AVAILABLE = {available}")
        
        if available:
            print("✅ STATUS: ObservabilityManager DISPONIBLE")
            
            # Verificar que realmente funciona
            try:
                from api.core.observability_manager import get_observability_manager
                obs = get_observability_manager()
                
                if hasattr(obs, 'metrics_collector'):
                    print("✅ STATUS: metrics_collector DISPONIBLE")
                    print("✅ STATUS: Middleware será FUNCIONAL")
                    print("\n🎯 RESULTADO: TODO CORRECTO")
                    print("   El error 'metrics_collector' attribute está RESUELTO")
                    print("   El middleware unified_observability_middleware funcionará")
                else:
                    print("❌ STATUS: metrics_collector NO disponible")
                    
            except Exception as e:
                print(f"❌ ERROR verificando funcionalidad: {e}")
        else:
            print("❌ STATUS: ObservabilityManager NO DISPONIBLE")
            print("   El middleware usará fallback")
    else:
        print("❌ OBSERVABILITY_MANAGER_AVAILABLE: Variable no encontrada")
        
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n💡 PARA VER LOGS DE STARTUP:")
print("   python src/api/main_unified_redis.py")
print("   (Busca mensajes con ✅ ObservabilityManager y ✅ MetricsCollector)")
