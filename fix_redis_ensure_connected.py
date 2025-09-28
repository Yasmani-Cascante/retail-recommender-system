# ========================================================================
# SCRIPT AUTOMÁTICO PARA APLICAR EL FIX
# ========================================================================

import re
import os
import shutil
from datetime import datetime

def fix_redis_ensure_connected():
    """
    Aplica el fix para eliminar ensure_connected calls problemáticas
    """
    file_path = "src/api/mcp/conversation_state_manager.py"
    backup_path = f"{file_path}.backup_ensure_connected_{int(datetime.now().timestamp())}"
    
    # Verificar archivo existe
    if not os.path.exists(file_path):
        print(f"❌ Archivo no encontrado: {file_path}")
        return False
    
    # Crear backup
    shutil.copy2(file_path, backup_path)
    print(f"📁 Backup creado: {backup_path}")
    
    # Leer archivo
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Aplicar fixes
    fixes_applied = 0
    
    # Fix 1: Eliminar ensure_connected checks
    pattern1 = r'\s*if not await (\w+)\.ensure_connected\(\):\s*\n\s*.*?return False\s*\n'
    matches1 = re.findall(pattern1, content, re.MULTILINE)
    if matches1:
        content = re.sub(pattern1, '', content, flags=re.MULTILINE)
        fixes_applied += len(matches1)
        print(f"✅ Eliminadas {len(matches1)} verificaciones ensure_connected")
    
    # Fix 2: Reemplazar ensure_connected con try/catch
    pattern2 = r'(\s*)if not await (\w+)\.ensure_connected\(\):\s*\n\s*(.*?return.*?)\n'
    def replace_with_try(match):
        indent = match.group(1)
        client_var = match.group(2)
        return_stmt = match.group(3)
        return f'{indent}# Connection managed by ServiceFactory - no need for ensure_connected\n'
    
    if re.search(pattern2, content, re.MULTILINE):
        content = re.sub(pattern2, replace_with_try, content, flags=re.MULTILINE)
        fixes_applied += 1
        print("✅ Reemplazadas verificaciones ensure_connected con comentarios")
    
    # Fix 3: Eliminar imports innecesarios si existen
    pattern3 = r'from.*ensure_connected.*\n'
    if re.search(pattern3, content):
        content = re.sub(pattern3, '', content)
        fixes_applied += 1
        print("✅ Eliminados imports ensure_connected innecesarios")
    
    if fixes_applied > 0:
        # Escribir archivo corregido
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\n🎉 Fix aplicado exitosamente!")
        print(f"📊 Total de correcciones: {fixes_applied}")
        print(f"📁 Archivo original respaldado en: {backup_path}")
        print(f"📝 Archivo corregido: {file_path}")
        
        print("\n📋 PRÓXIMOS PASOS:")
        print("1. Reiniciar el servidor")
        print("2. Probar el endpoint /v1/mcp/conversation")
        print("3. Verificar que no aparezca más el error ensure_connected")
        
        return True
    else:
        print("⚠️ No se encontraron líneas ensure_connected para corregir")
        os.remove(backup_path)  # Eliminar backup innecesario
        return False

if __name__ == "__main__":
    fix_redis_ensure_connected()

# ========================================================================
# MANUAL STEPS (SI PREFIERES MANUAL)
# ========================================================================

# PASO 1: Abrir src/api/mcp/conversation_state_manager.py
# 
# PASO 2: Buscar líneas que contengan:
#         "ensure_connected"
#
# PASO 3: Comentar o eliminar estas líneas:
#         # if not await redis_client.ensure_connected():
#         #     return False
#
# PASO 4: Guardar archivo y reiniciar servidor