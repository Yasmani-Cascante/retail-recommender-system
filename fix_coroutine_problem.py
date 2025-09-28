#!/usr/bin/env python3
"""
Script de corrección rápida para el problema de coroutine en mcp_router
"""

import os
import sys
from pathlib import Path

def fix_coroutine_problem():
    """Corrige el problema de await missing en mcp_router.py"""
    
    project_root = Path(__file__).parent
    router_file = project_root / 'src' / 'api' / 'routers' / 'mcp_router.py'
    
    if not router_file.exists():
        print(f"❌ No se encontró: {router_file}")
        return False
    
    # Leer contenido actual
    with open(router_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    fixes_applied = 0
    
    # Fix 1: get_mcp_recommender() sin await
    if 'mcp_recommender = get_mcp_recommender()' in content:
        content = content.replace(
            'mcp_recommender = get_mcp_recommender()',
            'mcp_recommender = await get_mcp_recommender()'
        )
        fixes_applied += 1
        print("✅ Fix 1: Añadido await a get_mcp_recommender()")
    
    # Fix 2: Otras variaciones
    patterns_to_fix = [
        ('get_mcp_recommender()', 'await get_mcp_recommender()'),
        ('= get_mcp_recommender()', '= await get_mcp_recommender()'),
    ]
    
    for old_pattern, new_pattern in patterns_to_fix:
        if old_pattern in content and 'await ' + old_pattern not in content:
            # Solo reemplazar si no tiene await ya
            content = content.replace(old_pattern, new_pattern)
            fixes_applied += 1
            print(f"✅ Fix: {old_pattern} → {new_pattern}")
    
    # Fix 3: Asegurar que funciones que llaman a get_mcp_recommender sean async
    lines = content.split('\n')
    new_lines = []
    
    for i, line in enumerate(lines):
        if 'await get_mcp_recommender()' in line:
            # Buscar la función que contiene esta línea
            func_line_idx = None
            for j in range(i, -1, -1):
                if lines[j].strip().startswith('def ') or lines[j].strip().startswith('async def '):
                    func_line_idx = j
                    break
            
            if func_line_idx is not None and lines[func_line_idx].strip().startswith('def '):
                # Convertir def a async def
                lines[func_line_idx] = lines[func_line_idx].replace('def ', 'async def ', 1)
                fixes_applied += 1
                print(f"✅ Fix: Convertida función a async en línea {func_line_idx + 1}")
        
        new_lines.append(line)
    
    content = '\n'.join(new_lines)
    
    # Guardar si hay cambios
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
        return True
    else:
        print("\n❌ No se encontraron patrones que corregir")
        return False

if __name__ == "__main__":
    success = fix_coroutine_problem()
    sys.exit(0 if success else 1)
