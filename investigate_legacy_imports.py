#!/usr/bin/env python3
"""
Legacy Import Detective - Simplified
====================================

Script simplificado para encontrar imports legacy de redis_client.
"""

import os
import re

def find_legacy_imports():
    """Busca imports legacy de redis_client"""
    
    print("DETECTIVE DE IMPORTS LEGACY - REDIS_CLIENT")
    print("=" * 50)
    
    legacy_patterns = [
        'from src.api.core.redis_client import',
        'from .redis_client import', 
        'import redis_client',
        'redis_client.',
        'RedisClient('
    ]
    
    matches = []
    src_path = 'src'
    
    # Buscar en archivos Python
    for root, dirs, files in os.walk(src_path):
        # Skip cache directories
        dirs[:] = [d for d in dirs if d != '__pycache__']
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        lines = content.split('\n')
                        
                        for i, line in enumerate(lines, 1):
                            for pattern in legacy_patterns:
                                if pattern in line and not line.strip().startswith('#'):
                                    matches.append({
                                        'file': file_path,
                                        'line': i,
                                        'content': line.strip(),
                                        'pattern': pattern
                                    })
                except Exception as e:
                    print(f"Error leyendo {file_path}: {e}")
    
    # Mostrar resultados
    if matches:
        print(f"\nIMPORTS LEGACY ENCONTRADOS: {len(matches)}")
        
        files_with_legacy = {}
        for match in matches:
            file = match['file']
            if file not in files_with_legacy:
                files_with_legacy[file] = []
            files_with_legacy[file].append(match)
        
        for file_path, file_matches in files_with_legacy.items():
            relative_path = file_path.replace('src\\', '').replace('src/', '')
            print(f"\n📁 {relative_path}:")
            for match in file_matches:
                print(f"   L{match['line']}: {match['content']}")
        
        print(f"\n⚠️ PROBLEMA CONFIRMADO:")
        print(f"- {len(files_with_legacy)} archivos con imports legacy")
        print(f"- Arquitectura híbrida no intencionada")
        print(f"- Migración enterprise incompleta")
        
        return files_with_legacy
    else:
        print("\n✅ No se encontraron imports legacy directos")
        return {}

def check_specific_files():
    """Verifica archivos específicos conocidos"""
    
    print("\nVERIFICANDO ARCHIVOS ESPECÍFICOS:")
    print("=" * 40)
    
    suspect_files = [
        'src/api/integrations/ai/optimized_conversation_manager.py',
        'src/api/mcp/engines/mcp_personalization_engine.py',
        'src/api/mcp/conversation_state_manager.py'
    ]
    
    for file_path in suspect_files:
        if os.path.exists(file_path):
            print(f"\n🔍 {file_path}:")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if 'redis_client' in content.lower():
                    print("   ⚠️ Contiene referencias a 'redis_client'")
                    
                    # Mostrar líneas específicas
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if 'redis_client' in line.lower() and not line.strip().startswith('#'):
                            print(f"      L{i}: {line.strip()}")
                else:
                    print("   ✅ No contiene 'redis_client'")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
        else:
            print(f"\n❌ No encontrado: {file_path}")

if __name__ == "__main__":
    print("🕵️ INVESTIGACIÓN DE IMPORTS LEGACY")
    print("=" * 60)
    
    # Buscar imports legacy
    legacy_files = find_legacy_imports()
    
    # Verificar archivos específicos
    check_specific_files()
    
    # Conclusión
    if legacy_files:
        print("\n📊 CONCLUSIÓN:")
        print("❌ MIGRACIÓN ENTERPRISE INCOMPLETA")
        print("🔧 Acción requerida: Completar migración de archivos detectados")
        print("\nPróximo paso: python complete_migration_fix.py")
    else:
        print("\n📊 CONCLUSIÓN:")
        print("✅ MIGRACIÓN ENTERPRISE COMPLETA")
        print("No se detectaron imports legacy residuales")
