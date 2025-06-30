#!/usr/bin/env python3
"""
Script Simple para Corregir el Error MCP - "Unable to serialize unknown type: <class 'coroutine'>"

Este script corrige directamente el problema en los archivos relevantes sin usar expresiones
regulares complejas, para evitar el error 'look-behind requires fixed-width pattern'.
"""

import os
import sys
import shutil
from pathlib import Path

# Colores para la salida en terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    """Imprime un encabezado formateado"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD} {text} {Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}\n")

def print_success(text):
    """Imprime un mensaje de éxito"""
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")

def print_warning(text):
    """Imprime un mensaje de advertencia"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.ENDC}")

def print_error(text):
    """Imprime un mensaje de error"""
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")

def print_info(text):
    """Imprime un mensaje informativo"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.ENDC}")

def backup_file(file_path):
    """Crea una copia de seguridad del archivo"""
    backup_path = str(file_path) + '.bak'
    try:
        shutil.copy2(file_path, backup_path)
        print_success(f"Creada copia de seguridad en {backup_path}")
        return True
    except Exception as e:
        print_error(f"Error al crear copia de seguridad: {e}")
        return False

def fix_main_unified_redis(project_root):
    """Corrige el endpoint /health en main_unified_redis.py"""
    file_path = project_root / "src" / "api" / "main_unified_redis.py"
    
    if not file_path.exists():
        print_error(f"Archivo no encontrado: {file_path}")
        return False
    
    # Crear copia de seguridad
    if not backup_file(file_path):
        return False
    
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    
    modified_lines = []
    in_health_function = False
    mcp_metrics_line_found = False
    
    for line in lines:
        # Detectar si estamos dentro de la función health_check
        if "async def health_check()" in line:
            in_health_function = True
            modified_lines.append(line)
            continue
        
        # Detectar cuando termina la función health_check
        if in_health_function and line.strip().startswith("@app."):
            in_health_function = False
        
        # Corregir la línea con get_metrics sin await
        if in_health_function and '"metrics": mcp_recommender.get_metrics()' in line:
            corrected_line = line.replace(
                '"metrics": mcp_recommender.get_metrics()',
                '"metrics": await mcp_recommender.get_metrics()'
            )
            modified_lines.append(corrected_line)
            mcp_metrics_line_found = True
            continue
        
        # Agregar la línea sin cambios
        modified_lines.append(line)
    
    if not mcp_metrics_line_found:
        print_warning("No se encontró la línea problemática con mcp_recommender.get_metrics()")
    
    # Escribir el archivo modificado
    with open(file_path, 'w', encoding='utf-8') as file:
        file.writelines(modified_lines)
    
    print_success(f"Archivo {file_path.name} actualizado")
    return True

def fix_mcp_client_enhanced(project_root):
    """Asegura que get_metrics sea asíncrono en MCPClientEnhanced"""
    file_path = project_root / "src" / "api" / "mcp" / "client" / "mcp_client_enhanced.py"
    
    if not file_path.exists():
        print_error(f"Archivo no encontrado: {file_path}")
        return False
    
    # Crear copia de seguridad
    if not backup_file(file_path):
        return False
    
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Comprobar si get_metrics es síncrono y cambiarlo a asíncrono
    if "def get_metrics(self)" in content and "async def get_metrics(self)" not in content:
        content = content.replace(
            "def get_metrics(self)",
            "async def get_metrics(self)"
        )
        
        # Escribir el archivo modificado
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)
        
        print_success(f"Método get_metrics convertido a asíncrono en {file_path.name}")
    else:
        print_info(f"Método get_metrics ya es asíncrono en {file_path.name}")
    
    return True

def fix_mcp_aware_recommender(project_root):
    """Asegura que get_metrics sea asíncrono en MCPAwareRecommender"""
    file_path = project_root / "src" / "recommenders" / "mcp_aware_recommender.py"
    
    if not file_path.exists():
        print_error(f"Archivo no encontrado: {file_path}")
        return False
    
    # Crear copia de seguridad
    if not backup_file(file_path):
        return False
    
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Comprobar si get_metrics es síncrono y cambiarlo a asíncrono
    if "def get_metrics(self)" in content and "async def get_metrics(self)" not in content:
        content = content.replace(
            "def get_metrics(self)",
            "async def get_metrics(self)"
        )
        
        # Escribir el archivo modificado
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)
        
        print_success(f"Método get_metrics convertido a asíncrono en {file_path.name}")
    else:
        print_info(f"Método get_metrics ya es asíncrono en {file_path.name}")
    
    # Comprobar y corregir health_check si llama a mcp_client.get_metrics sin await
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    
    modified_lines = []
    in_health_check = False
    made_changes = False
    
    for line in lines:
        # Detectar si estamos dentro de la función health_check
        if "async def health_check(self)" in line:
            in_health_check = True
        elif in_health_check and line.strip().startswith("async def"):
            in_health_check = False
        
        # Corregir las llamadas a get_metrics sin await dentro de health_check
        if in_health_check and "get_metrics()" in line and "await" not in line:
            corrected_line = line.replace(
                ".get_metrics()",
                "await .get_metrics()"
            )
            modified_lines.append(corrected_line)
            made_changes = True
            continue
        
        # Agregar la línea sin cambios
        modified_lines.append(line)
    
    if made_changes:
        # Escribir el archivo modificado
        with open(file_path, 'w', encoding='utf-8') as file:
            file.writelines(modified_lines)
        
        print_success(f"Corregidas llamadas a get_metrics en health_check de {file_path.name}")
    
    return True

def restart_services(project_root):
    """Intenta reiniciar los servicios necesarios"""
    print_info("Intentando reiniciar servicios...")
    
    # Detectar si estamos en Windows o Unix
    is_windows = os.name == 'nt'
    
    # Matar procesos actuales
    if is_windows:
        os.system('taskkill /f /im python.exe 2>nul')
        os.system('taskkill /f /im node.exe 2>nul')
    else:
        os.system('pkill -f "python.*run.py" 2>/dev/null')
        os.system('pkill -f "node.*server.js" 2>/dev/null')
    
    # Esperar a que terminen
    print_info("Esperando a que terminen los procesos actuales...")
    import time
    time.sleep(2)
    
    # Iniciar el MCP bridge mock
    bridge_script = "start_mcp_bridge_mock.bat" if is_windows else "./start_mcp_bridge_mock.sh"
    bridge_path = project_root / bridge_script
    
    if bridge_path.exists():
        print_info(f"Iniciando MCP bridge: {bridge_script}")
        if is_windows:
            os.system(f'start cmd /c "{bridge_path}"')
        else:
            os.system(f'bash "{bridge_path}" &')
    else:
        print_warning(f"Script de bridge no encontrado: {bridge_path}")
    
    # Esperar a que inicie
    print_info("Esperando a que inicie el bridge...")
    time.sleep(3)
    
    # Iniciar el servidor principal
    run_script = project_root / "run.py"
    if run_script.exists():
        print_info(f"Iniciando servidor principal: {run_script}")
        if is_windows:
            os.system(f'start cmd /c "python {run_script}"')
        else:
            os.system(f'python "{run_script}" &')
    else:
        print_warning(f"Script run.py no encontrado: {run_script}")
    
    print_success("Servicios reiniciados. Espere unos segundos a que inicien completamente.")
    return True

def main():
    """Función principal del script"""
    print_header("SOLUCIÓN PARA ERROR 'Unable to serialize unknown type: <class 'coroutine'>'")
    
    # Encontrar el directorio raíz del proyecto
    project_root = Path(os.path.dirname(os.path.abspath(__file__)))
    print_info(f"Directorio del proyecto: {project_root}")
    
    # Verificar que los archivos necesarios existen
    main_file = project_root / "src" / "api" / "main_unified_redis.py"
    mcp_client_file = project_root / "src" / "api" / "mcp" / "client" / "mcp_client_enhanced.py"
    mcp_recommender_file = project_root / "src" / "recommenders" / "mcp_aware_recommender.py"
    
    files_exist = True
    for file_path in [main_file, mcp_client_file, mcp_recommender_file]:
        if not file_path.exists():
            print_error(f"No se encontró: {file_path}")
            files_exist = False
    
    if not files_exist:
        print_error("No se encontraron todos los archivos necesarios. Verifica la ruta del proyecto.")
        return 1
    
    # Realizar las correcciones
    success = True
    print_info("Aplicando correcciones...")
    
    success &= fix_main_unified_redis(project_root)
    success &= fix_mcp_client_enhanced(project_root)
    success &= fix_mcp_aware_recommender(project_root)
    
    if success:
        print_success("Todas las correcciones aplicadas correctamente!")
        
        # Preguntar si reiniciar los servicios
        should_restart = input("¿Desea reiniciar los servicios ahora? (s/n): ").lower().startswith('s')
        
        if should_restart:
            restart_services(project_root)
            print_info("Ahora puede probar el endpoint /health para verificar que funciona correctamente.")
        else:
            print_info("Para que los cambios surtan efecto, reinicie manualmente los servicios:")
            print_info("1. Cierre los procesos python.exe y node.exe actuales")
            print_info("2. Ejecute start_mcp_bridge_mock.bat para iniciar el bridge")
            print_info("3. Ejecute python run.py para iniciar el servidor principal")
    else:
        print_error("Hubo errores al aplicar las correcciones. Revise los mensajes anteriores.")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print_warning("\nOperación cancelada por el usuario.")
        sys.exit(130)
    except Exception as e:
        print_error(f"Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)