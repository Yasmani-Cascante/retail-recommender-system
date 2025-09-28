#!/usr/bin/env python3
"""
Debug script para encontrar el problema de coroutine en mcp_router
"""

import os
import re
from pathlib import Path

def find_coroutine_problems():
    """Busca usos incorrectos de async functions sin await"""
    
    project_root = Path(__file__).parent
    router_file = project_root / 'src' / 'api' / 'routers' / 'mcp_router.py'
    
    if not router_file.exists():
        print(f"❌ No se encontró: {router_file}")
        return
    
    print(f"🔍 Analizando: {router_file}")
    
    with open(router_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    problems_found = []
    
    for i, line in enumerate(lines, 1):
        # Buscar get_mcp_recommender() sin await
        if 'get_mcp_recommender()' in line and 'await' not in line:
            problems_found.append({
                'line': i,
                'type': 'missing_await_get_mcp_recommender',
                'content': line.strip()
            })
        
        # Buscar .get_recommendations sin await  
        if '.get_recommendations(' in line and 'await' not in line and 'def' not in line:
            problems_found.append({
                'line': i,
                'type': 'missing_await_get_recommendations',
                'content': line.strip()
            })
        
        # Buscar assignment de función async
        if re.search(r'mcp_recommender\s*=.*get_mcp_recommender\(\)', line):
            if 'await' not in line:
                problems_found.append({
                    'line': i,
                    'type': 'async_assignment_without_await',
                    'content': line.strip()
                })
    
    print(f"\n📋 PROBLEMAS ENCONTRADOS: {len(problems_found)}")
    
    for problem in problems_found:
        print(f"\n❌ LÍNEA {problem['line']} ({problem['type']}):")
        print(f"   {problem['content']}")
        
        # Mostrar contexto
        start = max(0, problem['line'] - 3)
        end = min(len(lines), problem['line'] + 2)
        
        print("   CONTEXTO:")
        for line_num in range(start, end):
            marker = ">>> " if line_num == problem['line'] - 1 else "    "
            print(f"   {marker}{line_num + 1:3d}: {lines[line_num]}")
    
    return problems_found

if __name__ == "__main__":
    problems = find_coroutine_problems()
    
    if problems:
        print(f"\n🔧 CORRECCIONES SUGERIDAS:")
        for problem in problems:
            if problem['type'] == 'missing_await_get_mcp_recommender':
                print(f"   Línea {problem['line']}: Añadir 'await' antes de get_mcp_recommender()")
            elif problem['type'] == 'missing_await_get_recommendations':
                print(f"   Línea {problem['line']}: Añadir 'await' antes de .get_recommendations()")
            elif problem['type'] == 'async_assignment_without_await':
                print(f"   Línea {problem['line']}: Añadir 'await' antes de get_mcp_recommender()")
    else:
        print("\n✅ No se encontraron problemas obvios de await/async")
