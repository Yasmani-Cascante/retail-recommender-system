#!/usr/bin/env python3
"""
Script para encontrar las líneas exactas con mcp_recommender.get_recommendations
"""

import re
from pathlib import Path

def find_get_recommendations_calls():
    """Encuentra las líneas exactas con get_recommendations calls"""
    
    project_root = Path(__file__).parent
    router_file = project_root / 'src' / 'api' / 'routers' / 'mcp_router.py'
    
    if not router_file.exists():
        print(f"❌ Archivo no encontrado: {router_file}")
        return []
    
    print(f"🔍 Analizando: {router_file}")
    
    with open(router_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    matches = []
    
    for i, line in enumerate(lines, 1):
        if 'mcp_recommender.get_recommendations' in line:
            matches.append({
                'line_number': i,
                'content': line.strip(),
                'context': {
                    'before': [lines[j].strip() for j in range(max(0, i-4), i-1)],
                    'after': [lines[j].strip() for j in range(i, min(len(lines), i+3))]
                }
            })
    
    print(f"\n📋 ENCONTRADAS {len(matches)} LLAMADAS A get_recommendations:")
    
    for match in matches:
        print(f"\n🔍 LÍNEA {match['line_number']}:")
        print(f"   CÓDIGO: {match['content']}")
        print(f"   CONTEXTO ANTES:")
        for j, before_line in enumerate(match['context']['before']):
            print(f"      {match['line_number'] - len(match['context']['before']) + j}: {before_line}")
        print(f"   CONTEXTO DESPUÉS:")
        for j, after_line in enumerate(match['context']['after']):
            print(f"      {match['line_number'] + j}: {after_line}")
    
    return matches

if __name__ == "__main__":
    matches = find_get_recommendations_calls()
    
    if matches:
        print(f"\n✅ LÍNEAS ENCONTRADAS: {[match['line_number'] for match in matches]}")
        print("Estas líneas necesitan ser modificadas para usar la arquitectura correcta.")
    else:
        print("\n❌ No se encontraron llamadas a mcp_recommender.get_recommendations")
