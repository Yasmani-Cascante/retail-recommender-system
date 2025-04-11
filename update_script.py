"""
Script para actualizar el archivo main_tfidf_shopify_with_metrics.py
con el nuevo endpoint de eventos.
"""

import os
import re
import sys
import shutil

def update_main_file():
    # Rutas de archivos
    main_file = os.path.join('src', 'api', 'main_tfidf_shopify_with_metrics.py')
    endpoints_file = os.path.join('src', 'api', 'endpoints.py')
    backup_file = main_file + '.bak'
    
    # Crear backup
    shutil.copy2(main_file, backup_file)
    print(f"Backup creado en {backup_file}")
    
    # Leer el nuevo endpoint
    with open(endpoints_file, 'r', encoding='utf-8') as f:
        new_endpoint = f.read()
    
    # Leer el archivo principal
    with open(main_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Buscar el inicio del endpoint a reemplazar
    start_line = -1
    end_line = -1
    for i, line in enumerate(lines):
        if '@app.post("/v1/events/user/{user_id}")' in line:
            start_line = i
            break
    
    if start_line == -1:
        print("No se encontró el endpoint para reemplazar")
        sys.exit(1)
    
    # Buscar el final del endpoint
    brace_count = 0
    for i in range(start_line, len(lines)):
        line = lines[i]
        if '{' in line:
            brace_count += line.count('{')
        if '}' in line:
            brace_count -= line.count('}')
        
        if 'return result' in line or 'raise HTTPException' in line:
            # Encontrar el final de la función (buscar la última línea con indentación)
            for j in range(i+1, len(lines)):
                if lines[j].strip() and not lines[j].startswith('    '):
                    end_line = j - 1
                    break
            if end_line != -1:
                break
    
    if end_line == -1:
        print("No se pudo determinar el final del endpoint")
        sys.exit(1)
    
    # Reemplazar el endpoint
    updated_lines = lines[:start_line] + [new_endpoint + '\n\n'] + lines[end_line+1:]
    
    # Guardar el archivo actualizado
    with open(main_file, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)
    
    print(f"Endpoint actualizado en {main_file}")

if __name__ == "__main__":
    update_main_file()
