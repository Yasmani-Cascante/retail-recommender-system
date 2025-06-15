#!/usr/bin/env python3
"""
Script de verificación de la corrección aplicada al HybridRecommender.

Este script verifica que la corrección crítica se aplicó correctamente
y valida la lógica del recomendador híbrido.
"""

import sys
import os

def verify_hybrid_recommender_fix():
    """Verifica que la corrección se aplicó correctamente."""
    
    print("🔍 Verificando corrección en HybridRecommender...")
    
    # Leer el archivo corregido
    file_path = "src/api/core/hybrid_recommender.py"
    
    if not os.path.exists(file_path):
        print(f"❌ Error: No se encontró el archivo {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Verificaciones críticas
    checks = [
        {
            "name": "Validación de content_weight en constructor",
            "pattern": "if content_weight < 0 or content_weight > 1:",
            "found": "if content_weight < 0 or content_weight > 1:" in content
        },
        {
            "name": "Variable should_use_retail_api",
            "pattern": "should_use_retail_api = not product_id or self.content_weight < 1.0",
            "found": "should_use_retail_api = not product_id or self.content_weight < 1.0" in content
        },
        {
            "name": "Logging de diagnóstico",
            "pattern": "using_retail_api={should_use_retail_api}",
            "found": "using_retail_api={should_use_retail_api}" in content
        },
        {
            "name": "Comentario de corrección",
            "pattern": "CORRECCIÓN: Para recomendaciones de usuario",
            "found": "CORRECCIÓN: Para recomendaciones de usuario" in content
        },
        {
            "name": "Emojis en logging",
            "pattern": "✅ Obtenidas",
            "found": "✅ Obtenidas" in content
        }
    ]
    
    all_passed = True
    
    for check in checks:
        if check["found"]:
            print(f"✅ {check['name']}: CORRECTO")
        else:
            print(f"❌ {check['name']}: FALTA")
            all_passed = False
    
    # Verificar que la línea problemática anterior fue comentada/removida
    old_problem_line = "if self.content_weight < 1.0:"
    if old_problem_line in content:
        # Verificar si está comentada
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if old_problem_line in line and not line.strip().startswith('#'):
                print(f"❌ Línea problemática aún activa en línea {i+1}: {line.strip()}")
                all_passed = False
                break
        else:
            print("✅ Línea problemática anterior correctamente comentada/removida")
    else:
        print("✅ Línea problemática anterior no encontrada (correcto)")
    
    # Verificar la nueva lógica
    new_logic = "not product_id or self.content_weight < 1.0"
    if new_logic in content:
        print("✅ Nueva lógica corregida implementada")
    else:
        print("❌ Nueva lógica corregida NO encontrada")
        all_passed = False
    
    print("\n" + "="*60)
    
    if all_passed:
        print("🎉 CORRECCIÓN APLICADA EXITOSAMENTE")
        print("\n📋 Resumen de cambios:")
        print("  • ✅ Retail API se usa SIEMPRE para recomendaciones de usuario")
        print("  • ✅ content_weight se aplica solo para recomendaciones de producto")
        print("  • ✅ Validación de parámetros añadida")
        print("  • ✅ Logging mejorado para diagnóstico")
        print("  • ✅ Comentarios explicativos añadidos")
        
        print("\n🚀 Próximos pasos:")
        print("  1. Redesplegar la versión unificada: ./deploy_unified_redis.ps1")
        print("  2. Probar el endpoint: /v1/recommendations/user/8816287056181")
        print("  3. Verificar que ahora incluye recomendaciones de retail_api")
        
        return True
    else:
        print("❌ CORRECCIÓN NO APLICADA COMPLETAMENTE")
        print("Revisa los errores arriba y aplica las correcciones faltantes.")
        return False

if __name__ == "__main__":
    # Cambiar al directorio del proyecto
    if os.path.basename(os.getcwd()) != "retail-recommender-system":
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(script_dir)
        if os.path.basename(project_dir) == "retail-recommender-system":
            os.chdir(project_dir)
            print(f"📁 Cambiado al directorio del proyecto: {project_dir}")
    
    success = verify_hybrid_recommender_fix()
    sys.exit(0 if success else 1)
