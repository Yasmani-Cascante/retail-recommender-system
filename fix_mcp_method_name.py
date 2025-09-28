#!/usr/bin/env python3
"""
Corrección para el método incorrecto en MCPPersonalizationEngine
"""

import re
from pathlib import Path

def fix_mcp_method_name():
    """
    Corrige el nombre del método de get_recommendations() a generate_personalized_response()
    """
    
    project_root = Path(__file__).parent
    router_file = project_root / 'src' / 'api' / 'routers' / 'mcp_router.py'
    
    if not router_file.exists():
        print(f"❌ Archivo no encontrado: {router_file}")
        return False
    
    print(f"🔧 Corrigiendo nombre de método en: {router_file}")
    
    with open(router_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    fixes_applied = 0
    
    # PATRÓN 1: mcp_recommender.get_recommendations(...)
    if 'mcp_recommender.get_recommendations(' in content:
        content = content.replace(
            'mcp_recommender.get_recommendations(',
            'mcp_recommender.generate_personalized_response('
        )
        fixes_applied += 1
        print("✅ Corregido: .get_recommendations() → .generate_personalized_response()")
    
    # PATRÓN 2: await mcp_recommender.get_recommendations(...)
    if 'await mcp_recommender.get_recommendations(' in content:
        content = content.replace(
            'await mcp_recommender.get_recommendations(',
            'await mcp_recommender.generate_personalized_response('
        )
        fixes_applied += 1
        print("✅ Corregido: await .get_recommendations() → await .generate_personalized_response()")
    
    # PATRÓN 3: Cualquier variable.get_recommendations(...) donde la variable podría ser mcp_recommender
    pattern = r'(\w+)\.get_recommendations\('
    matches = re.findall(pattern, content)
    
    for var_name in matches:
        if 'recommender' in var_name.lower() and 'mcp' in var_name.lower():
            old_pattern = f'{var_name}.get_recommendations('
            new_pattern = f'{var_name}.generate_personalized_response('
            content = content.replace(old_pattern, new_pattern)
            fixes_applied += 1
            print(f"✅ Corregido: {old_pattern} → {new_pattern}")
    
    # Guardar cambios si los hay
    if content != original_content:
        # Hacer backup
        backup_file = router_file.with_suffix('.py.backup')
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(original_content)
        
        # Guardar corrección
        with open(router_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\n✅ CORRECCIÓN COMPLETADA: {fixes_applied} fixes aplicados")
        print(f"   Backup guardado en: {backup_file}")
        print("\n⚠️  IMPORTANTE: Revisa los parámetros de generate_personalized_response()")
        print("   Este método puede necesitar parámetros diferentes a get_recommendations()")
        
        return True
    else:
        print("\n❌ No se encontraron patrones get_recommendations() para corregir")
        return False

if __name__ == "__main__":
    success = fix_mcp_method_name()
    
    if success:
        print("\n📋 PRÓXIMOS PASOS:")
        print("1. Revisar los parámetros que se pasan a generate_personalized_response()")
        print("2. Verificar que el método reciba los parámetros correctos")
        print("3. Probar el endpoint /conversation nuevamente")
        print("4. Verificar logs para errores de parámetros")
