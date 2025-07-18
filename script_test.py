#!/usr/bin/env python3
"""
Script de ejecución corregido para Fase 2
==========================================

CORRECCIÓN CRÍTICA: Ejecutar main_unified_redis.py que contiene
la implementación completa de Fase 2 (MCP + Claude + Personalization)

Cambios:
- ❌ main_tfidf_shopify_with_metrics (legacy)
- ✅ main_unified_redis (Fase 2 completa)
"""

import uvicorn
import sys
import os
from pathlib import Path

def validate_phase2_setup():
    """Validar que el setup de Fase 2 esté correcto"""
    
    # Verificar que existe main_unified_redis.py
    main_unified_path = Path("src/api/main_unified_redis.py")
    if not main_unified_path.exists():
        print("❌ ERROR: src/api/main_unified_redis.py no encontrado")
        print("   Este archivo contiene la implementación de Fase 2")
        sys.exit(1)
    
    # Verificar startup event
    startup_event_path = Path("startup_event_fixed.py")
    if not startup_event_path.exists():
        print("⚠️ WARNING: startup_event_fixed.py no encontrado")
        print("   Puede que la inicialización de Fase 2 no funcione correctamente")
    
    # Verificar variables de entorno críticas
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️ WARNING: .env no encontrado")
        print("   Configurar variables de entorno para Redis, Claude API, etc.")
    
    print("✅ Configuración de Fase 2 validada")

def main():
    """Ejecutar servidor con configuración de Fase 2"""
    
    # Validar setup antes de ejecutar
    validate_phase2_setup()
    
    print("🚀 Iniciando Retail Recommender API - Fase 2")
    print("   Implementación: main_unified_redis.py")
    print("   Funcionalidades: MCP + Claude + Personalization + Redis")
    print("   Puerto: 8000")
    print("   Documentación: http://localhost:8000/docs")
    print("")
    
    try:
        # ✅ CORRECCIÓN: Usar main_unified_redis para Fase 2
        uvicorn.run(
            "src.api.main_unified_redis:app",  # Fase 2 completa
            host="localhost", 
            port=8000, 
            reload=True,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n⚠️ Servidor detenido por usuario")
    except Exception as e:
        print(f"\n❌ Error ejecutando servidor: {e}")
        print("   Verificar configuración de dependencias y variables de entorno")
        sys.exit(1)

if __name__ == "__main__":
    main()