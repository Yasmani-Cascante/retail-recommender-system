#!/usr/bin/env python3
"""
PATCH CRÍTICO: validate_phase2_complete.py
==========================================

Corrige el script para usar el endpoint optimizado correcto.
"""

import os
import sys

def patch_validation_script():
    """Corrige validate_phase2_complete.py para usar endpoint optimizado"""
    
    script_path = "tests/phase2_consolidation/validate_phase2_complete.py"
    
    if not os.path.exists(script_path):
        print(f"❌ Script not found: {script_path}")
        return False
    
    print(f"🔧 Patching {script_path}...")
    
    # Leer archivo original
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Aplicar parches
    patches = [
        {
            'old': '/v1/mcp/conversation',
            'new': '/v1/mcp/conversation/optimized',
            'description': 'Use optimized endpoint'
        },
        {
            'old': '"enable_optimization": false',
            'new': '"enable_optimization": true',
            'description': 'Enable optimization flag'
        },
        {
            'old': '# TODO: Use optimized endpoint',
            'new': '# ✅ FIXED: Using optimized endpoint',
            'description': 'Update TODO comment'
        }
    ]
    
    modified = False
    for patch in patches:
        if patch['old'] in content:
            content = content.replace(patch['old'], patch['new'])
            print(f"   ✅ Applied: {patch['description']}")
            modified = True
        else:
            print(f"   ⚠️ Pattern not found: {patch['old']}")
    
    if modified:
        # Crear backup
        backup_path = f"{script_path}.backup_original"
        with open(backup_path, 'w', encoding='utf-8') as f:
            with open(script_path, 'r', encoding='utf-8') as original:
                f.write(original.read())
        print(f"   💾 Backup created: {backup_path}")
        
        # Escribir archivo corregido
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"   ✅ Patch applied successfully")
        return True
    else:
        print(f"   ⚠️ No changes needed")
        return False

def validate_patch():
    """Valida que el patch se aplicó correctamente"""
    script_path = "tests/phase2_consolidation/validate_phase2_complete.py"
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    checks = [
        ('/v1/mcp/conversation/optimized' in content, "Using optimized endpoint"),
        ('"enable_optimization": true' in content, "Optimization enabled"),
        ('conversation/optimized' in content, "Optimized path present")
    ]
    
    print("\n🔍 Validando patch:")
    all_good = True
    for check, description in checks:
        status = "✅" if check else "❌"
        print(f"   {status} {description}")
        if not check:
            all_good = False
    
    return all_good

def main():
    print("🚨 APLICANDO PATCH CRÍTICO - validate_phase2_complete.py")
    print("=" * 60)
    
    if patch_validation_script():
        if validate_patch():
            print("\n🎉 PATCH APLICADO EXITOSAMENTE")
            print("✅ validate_phase2_complete.py ahora usa endpoint optimizado")
            print("\n📋 Próximos pasos:")
            print("1. python tests/phase2_consolidation/validate_phase2_complete.py")
            print("2. Verificar que los tiempos son ~1,700ms en lugar de ~11,900ms")
            print("3. Success rate debería mejorar significativamente")
        else:
            print("\n❌ PATCH FALLÓ EN VALIDACIÓN")
            return False
    else:
        print("\n⚠️ NO SE APLICARON CAMBIOS")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
