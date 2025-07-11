#!/usr/bin/env python3
"""
Script para corregir automáticamente el error de sintaxis en main_unified_redis.py

Error: name 'optimized_conversation_manager' is used prior to global declaration

Este script encuentra y corrige automáticamente el problema de orden en las declaraciones globales.
"""

import os
import re
import shutil
from pathlib import Path

def fix_main_unified_redis():
    """
    Corrige el error de sintaxis en main_unified_redis.py
    """
    file_path = "src/api/main_unified_redis.py"
    
    if not os.path.exists(file_path):
        print(f"❌ Archivo no encontrado: {file_path}")
        return False
    
    print(f"🔧 Corrigiendo {file_path}...")
    
    # Crear backup
    backup_path = f"{file_path}.backup"
    shutil.copy2(file_path, backup_path)
    print(f"📦 Backup creado: {backup_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Detectar el patrón problemático
        # Buscar funciones que tienen declaraciones global después de usar las variables
        
        # Patrón 1: Función startup_event o fixed_startup_event
        startup_pattern = r'(@app\.on_event\("startup"\)\s*async def \w+\(\):.*?)(global optimized_conversation_manager, mcp_state_manager, personalization_engine)'
        
        # Verificar si existe el patrón problemático
        if 'global optimized_conversation_manager, mcp_state_manager, personalization_engine' in content:
            print("✅ Patrón problemático encontrado, aplicando corrección...")
            
            # Estrategia de corrección:
            # 1. Encontrar la función que contiene la declaración global problemática
            # 2. Mover todas las declaraciones global al inicio de la función
            
            lines = content.split('\n')
            fixed_lines = []
            inside_problematic_function = False
            function_start_line = -1
            global_declarations = []
            
            i = 0
            while i < len(lines):
                line = lines[i]
                stripped = line.strip()
                
                # Detectar inicio de función startup
                if '@app.on_event("startup")' in line or 'async def fixed_startup_event' in line:
                    inside_problematic_function = True
                    function_start_line = i
                    print(f"📍 Función problemática encontrada en línea {i+1}")
                
                # Si estamos dentro de la función problemática
                if inside_problematic_function:
                    # Detectar declaraciones global
                    if stripped.startswith('global '):
                        global_declarations.append(line)
                        print(f"🔍 Declaración global encontrada: {stripped}")
                        i += 1
                        continue  # Saltar esta línea por ahora
                    
                    # Detectar fin de función (nueva función o desindentación significativa)
                    if (stripped.startswith('def ') or stripped.startswith('async def ') or 
                        stripped.startswith('@') or stripped.startswith('class ')) and i > function_start_line + 5:
                        inside_problematic_function = False
                        # Insertar las declaraciones global al inicio de la función anterior
                        if global_declarations:
                            print(f"🔧 Insertando {len(global_declarations)} declaraciones global al inicio de la función")
                            # Encontrar la línea después de la definición de función
                            for j in range(function_start_line, len(fixed_lines)):
                                if 'async def' in fixed_lines[j] or 'def' in fixed_lines[j]:
                                    # Obtener indentación de la función
                                    func_line = fixed_lines[j]
                                    func_indent = len(func_line) - len(func_line.lstrip())
                                    inner_indent = func_indent + 4
                                    
                                    # Insertar declaraciones global
                                    insert_pos = j + 1
                                    
                                    # Añadir comentario explicativo
                                    comment_line = ' ' * inner_indent + '# ✅ CORRECCIÓN: Declaraciones globales movidas al inicio'
                                    fixed_lines.insert(insert_pos, comment_line)
                                    insert_pos += 1
                                    
                                    # Añadir declaraciones global con indentación correcta
                                    for global_decl in global_declarations:
                                        # Ajustar indentación
                                        global_content = global_decl.strip()
                                        indented_global = ' ' * inner_indent + global_content
                                        fixed_lines.insert(insert_pos, indented_global)
                                        insert_pos += 1
                                    
                                    # Añadir línea en blanco
                                    fixed_lines.insert(insert_pos, '')
                                    break
                            
                            global_declarations = []
                
                fixed_lines.append(line)
                i += 1
            
            # Escribir archivo corregido
            fixed_content = '\n'.join(fixed_lines)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            
            print("✅ Archivo corregido exitosamente")
            
            # Verificar que el problema se resolvió
            if 'global optimized_conversation_manager, mcp_state_manager, personalization_engine' in fixed_content:
                # Contar cuántas veces aparece después de la corrección
                count = fixed_content.count('global optimized_conversation_manager, mcp_state_manager, personalization_engine')
                print(f"📊 Declaraciones global restantes: {count}")
            
            return True
            
        else:
            print("⚠️ Patrón problemático no encontrado - el archivo puede ya estar corregido")
            return True
            
    except Exception as e:
        print(f"❌ Error durante la corrección: {e}")
        # Restaurar backup
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, file_path)
            print(f"📦 Backup restaurado")
        return False

def verify_syntax():
    """
    Verifica que el archivo corregido no tenga errores de sintaxis
    """
    file_path = "src/api/main_unified_redis.py"
    
    try:
        import ast
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Compilar para verificar sintaxis
        ast.parse(content)
        print("✅ Sintaxis verificada - no hay errores")
        return True
        
    except SyntaxError as e:
        print(f"❌ Error de sintaxis persistente: {e}")
        print(f"   Línea {e.lineno}: {e.text}")
        return False
    except Exception as e:
        print(f"❌ Error verificando sintaxis: {e}")
        return False

def main():
    """
    Función principal para ejecutar la corrección
    """
    print("🚀 CORRECCIÓN AUTOMÁTICA DEL ERROR DE SINTAXIS")
    print("=" * 50)
    
    # Cambiar al directorio del proyecto
    if os.path.exists("retail-recommender-system"):
        os.chdir("retail-recommender-system")
        print("📁 Cambiado al directorio del proyecto")
    
    # Aplicar corrección
    success = fix_main_unified_redis()
    
    if success:
        # Verificar sintaxis
        syntax_ok = verify_syntax()
        
        if syntax_ok:
            print("\n🎉 ¡CORRECCIÓN COMPLETADA EXITOSAMENTE!")
            print("✅ El archivo main_unified_redis.py ha sido corregido")
            print("🚀 Ahora puedes ejecutar: python src/api/run.py")
        else:
            print("\n⚠️ Corrección aplicada pero hay errores de sintaxis adicionales")
            print("🔍 Revisa el archivo manualmente")
    else:
        print("\n❌ No se pudo aplicar la corrección automáticamente")
        print("🔧 Aplicar corrección manual siguiendo las instrucciones")
    
    print("\n📝 BACKUP disponible en: src/api/main_unified_redis.py.backup")

if __name__ == "__main__":
    main()