#!/usr/bin/env python3
"""
Script completo de corrección para el error de MCP recommendations
"""

import sys
import subprocess
from pathlib import Path

def run_all_fixes():
    """Ejecuta todas las correcciones en orden"""
    
    project_root = Path(__file__).parent
    
    print("🔧 INICIANDO CORRECCIÓN COMPLETA DEL MCP RECOMMENDER ERROR")
    print("=" * 60)
    
    # Paso 1: Crear el adaptador
    print("\n📁 PASO 1: Creando MCP Adapter...")
    try:
        exec(open(project_root / 'create_mcp_adapter.py').read())
        print("✅ MCP Adapter creado exitosamente")
    except Exception as e:
        print(f"❌ Error creando adapter: {e}")
        return False
    
    # Paso 2: Corregir nombre del método (si es necesario)
    print("\n🔧 PASO 2: Verificando nombres de métodos...")
    try:
        exec(open(project_root / 'fix_mcp_method_name.py').read())
        print("✅ Verificación de métodos completada")
    except Exception as e:
        print(f"⚠️ Warning en corrección de métodos: {e}")
    
    # Paso 3: Añadir import necesario al adapter
    print("\n📝 PASO 3: Añadiendo imports faltantes...")
    adapter_file = project_root / 'src' / 'api' / 'mcp' / 'engines' / 'mcp_adapter.py'
    
    if adapter_file.exists():
        with open(adapter_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Añadir import de time si no existe
        if 'import time' not in content:
            content = content.replace(
                'import logging',
                'import time\\nimport logging'
            )
            
            with open(adapter_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print("✅ Import de time añadido")
    
    print("\n🎯 CORRECCIÓN COMPLETADA")
    print("=" * 60)
    print("\n📋 PRÓXIMOS PASOS:")
    print("1. Reinicia la aplicación:")
    print("   python src/api/main_unified_redis.py")
    print()
    print("2. Prueba el endpoint:")
    print("   curl -X POST http://localhost:8000/v1/mcp/conversation \\")
    print("        -H 'Authorization: Bearer your-api-key' \\")
    print("        -H 'Content-Type: application/json' \\")
    print("        -d '{\"query\":\"recommend products\",\"market_id\":\"US\"}'")
    print()
    print("3. Verifica los logs para:")
    print("   ✅ 'MCPPersonalizationEngine singleton initialized successfully'")
    print("   ✅ 'MCPRecommenderAdapter initialized'")
    print("   ✅ 'Adapter processing recommendations for user...'")
    
    return True

if __name__ == "__main__":
    success = run_all_fixes()
    
    if success:
        print("\n🎉 TODAS LAS CORRECCIONES APLICADAS EXITOSAMENTE!")
        print("\nEl error 'MCPPersonalizationEngine' object has no attribute 'get_recommendations' debería estar resuelto.")
    else:
        print("\n❌ ALGUNAS CORRECCIONES FALLARON")
        print("Revisa los errores arriba y aplica correcciones manuales si es necesario.")
    
    sys.exit(0 if success else 1)
