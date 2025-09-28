#!/usr/bin/env python3
"""
Test: Verificación de Logs ObservabilityManager
==============================================

Simula la importación de main_unified_redis para verificar
que los logs de ObservabilityManager aparecen correctamente.
"""

import sys
import os
import logging
from dotenv import load_dotenv

# Configurar logging para capturar todos los mensajes
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()
sys.path.append('src')

print("🔍 TEST: Verificación de Logs ObservabilityManager")
print("=" * 55)
print("\nSimulando la secuencia de importación de main_unified_redis.py...")
print("\n" + "="*60)

# Simular exactamente lo que hace main_unified_redis.py
logger = logging.getLogger("main_unified_redis_test")

try:
    logger.info("🔄 Iniciando importación ObservabilityManager...")
    
    from api.core.observability_manager import get_observability_manager
    OBSERVABILITY_MANAGER_AVAILABLE = True
    logger.info("✅ ObservabilityManager loaded - Single source of truth enabled")
    
    # Test adicional para confirmar funcionalidad completa
    try:
        _test_observability = get_observability_manager()
        if hasattr(_test_observability, 'metrics_collector'):
            logger.info("✅ MetricsCollector integrated successfully - Middleware ready")
        else:
            logger.warning("⚠️ MetricsCollector not found in ObservabilityManager")
    except Exception as e:
        logger.warning(f"⚠️ ObservabilityManager test failed: {e}")
        
except ImportError as e:
    OBSERVABILITY_MANAGER_AVAILABLE = False
    logger.warning(f"⚠️ ObservabilityManager not available: {e}")

print("\n" + "="*60)
print(f"\n🎯 RESULTADO:")
print(f"   OBSERVABILITY_MANAGER_AVAILABLE = {OBSERVABILITY_MANAGER_AVAILABLE}")

if OBSERVABILITY_MANAGER_AVAILABLE:
    print("✅ Los logs deberían aparecer cuando ejecutes:")
    print("   python src/api/main_unified_redis.py")
    print("\n🔍 BUSCA ESTOS MENSAJES EN LA SALIDA:")
    print("   ✅ ObservabilityManager loaded - Single source of truth enabled")
    print("   ✅ MetricsCollector integrated successfully - Middleware ready")
else:
    print("❌ Hay un problema con la importación de ObservabilityManager")

print("\n💡 TIP: Si no ves los logs, verifica que el nivel de logging esté en INFO o DEBUG")
