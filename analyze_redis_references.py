#!/usr/bin/env python3
"""
Redis Reference Finder
======================

Encuentra todas las referencias a RedisClient en archivos específicos
para poder corregirlas paso a paso.
"""

import re

def find_redis_references(file_path):
    """Encuentra todas las referencias a RedisClient en un archivo"""
    
    print(f"🔍 Analizando: {file_path}")
    print("=" * 50)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        references = []
        
        for i, line in enumerate(lines, 1):
            if 'RedisClient' in line and not line.strip().startswith('#'):
                references.append({
                    'line': i,
                    'content': line.strip(),
                    'context': 'constructor' if '__init__' in line else 'usage'
                })
        
        if references:
            print(f"📍 REFERENCIAS ENCONTRADAS: {len(references)}")
            for ref in references:
                print(f"   Línea {ref['line']}: {ref['content']}")
                print(f"   ↳ Contexto: {ref['context']}")
                print()
        else:
            print("✅ No se encontraron referencias a RedisClient")
        
        return references
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def analyze_usage_patterns(file_path, references):
    """Analiza cómo se usa RedisClient en el archivo"""
    
    print(f"📊 ANÁLISIS DE PATRONES DE USO:")
    print("=" * 40)
    
    patterns = {
        'constructor_params': [],
        'type_hints': [],
        'variable_assignments': [],
        'method_calls': []
    }
    
    for ref in references:
        line_content = ref['content']
        
        if ': Optional[RedisClient]' in line_content or ': RedisClient' in line_content:
            patterns['type_hints'].append(ref)
        elif 'redis_client: RedisClient' in line_content:
            patterns['constructor_params'].append(ref)
        elif '= RedisClient(' in line_content:
            patterns['variable_assignments'].append(ref)
        elif 'RedisClient.' in line_content:
            patterns['method_calls'].append(ref)
    
    for pattern_type, refs in patterns.items():
        if refs:
            print(f"\n🏷️ {pattern_type.upper()}:")
            for ref in refs:
                print(f"   L{ref['line']}: {ref['content']}")
    
    return patterns

def suggest_fixes(file_path, patterns):
    """Sugiere fixes específicos basados en los patrones encontrados"""
    
    print(f"\n🔧 FIXES SUGERIDOS PARA {file_path}:")
    print("=" * 50)
    
    fixes = []
    
    # Fix para parámetros de constructor
    for ref in patterns['constructor_params']:
        old_text = ref['content']
        if 'redis_client: RedisClient = None' in old_text:
            new_text = old_text.replace('redis_client: RedisClient = None', 'redis_client = None  # Legacy compatibility - will use ServiceFactory')
            fixes.append({
                'line': ref['line'],
                'old': old_text,
                'new': new_text,
                'type': 'constructor_param'
            })
    
    # Fix para type hints
    for ref in patterns['type_hints']:
        old_text = ref['content']
        if ': Optional[RedisClient]' in old_text:
            new_text = old_text.replace(': Optional[RedisClient]', ': Optional[Any]  # Legacy compatibility')
            fixes.append({
                'line': ref['line'],
                'old': old_text,
                'new': new_text,
                'type': 'type_hint'
            })
    
    # Fix para asignaciones
    for ref in patterns['variable_assignments']:
        old_text = ref['content']
        if '= RedisClient(' in old_text:
            new_text = old_text.replace('RedisClient(', '# RedisClient(')  # Comment out
            fixes.append({
                'line': ref['line'],
                'old': old_text,
                'new': new_text,
                'type': 'assignment'
            })
    
    if fixes:
        for fix in fixes:
            print(f"\n📝 LÍNEA {fix['line']} ({fix['type']}):")
            print(f"   ANTES: {fix['old']}")
            print(f"   DESPUÉS: {fix['new']}")
    else:
        print("ℹ️ No se generaron fixes automáticos")
    
    return fixes

if __name__ == "__main__":
    print("🔍 REDIS REFERENCE ANALYZER")
    print("=" * 60)
    
    # Archivos a analizar
    files_to_check = [
        'src/api/integrations/ai/optimized_conversation_manager.py',
        'src/api/mcp/engines/mcp_personalization_engine.py'
    ]
    
    all_fixes = []
    
    for file_path in files_to_check:
        print(f"\n" + "="*60)
        
        # Encontrar referencias
        references = find_redis_references(file_path)
        
        if references:
            # Analizar patrones
            patterns = analyze_usage_patterns(file_path, references)
            
            # Sugerir fixes
            fixes = suggest_fixes(file_path, patterns)
            all_fixes.extend([(file_path, fix) for fix in fixes])
    
    # Resumen final
    print(f"\n" + "="*60)
    print("📋 RESUMEN DE FIXES REQUERIDOS")
    print("=" * 60)
    
    if all_fixes:
        print(f"Total fixes necesarios: {len(all_fixes)}")
        
        by_file = {}
        for file_path, fix in all_fixes:
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(fix)
        
        for file_path, fixes in by_file.items():
            print(f"\n📁 {file_path}: {len(fixes)} fixes")
    else:
        print("✅ No se requieren fixes")
