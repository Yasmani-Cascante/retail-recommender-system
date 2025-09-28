#!/usr/bin/env python3
"""
FIX: Corregir error de sintaxis en conversation_state_manager.py
================================================================

PROBLEMA: El script anterior introdujo un bloque try sin except/finally
SOLUCIÓN: Corregir la sintaxis manteniendo la funcionalidad
"""

import os
import re
from datetime import datetime

def fix_syntax_error():
    """Corrige el error de sintaxis en conversation_state_manager.py"""
    
    file_path = "src/api/mcp/conversation_state_manager.py"
    
    print("🔧 CORRIGIENDO ERROR DE SINTAXIS")
    print("=" * 60)
    
    # Leer el archivo con error
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Hacer backup
    backup_file = f"{file_path}.backup_syntax_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Backup creado: {backup_file}")
    
    # Buscar el patrón problemático alrededor de la línea 375
    # El problema es un try sin except/finally
    
    # Opción 1: Buscar bloques try incompletos
    # Patrón para encontrar try sin except/finally correspondiente
    problem_pattern = r'(\n\s+)(try:\s*\n(?:(?!\n\s*(?:except|finally)).)*?)(\n\s+try:)'
    
    # Si no encuentra el patrón anterior, buscar específicamente alrededor de save_conversation_state
    if 'try:\n' in content and content.count('try:') > content.count('except'):
        print("Detectado: Más bloques 'try' que 'except'")
        
        # Buscar el área problemática específica
        lines = content.split('\n')
        
        # Encontrar líneas con try sin su except/finally correspondiente
        for i in range(len(lines)):
            if i >= 370 and i <= 380:  # Alrededor de la línea 375
                print(f"Línea {i+1}: {lines[i][:50]}...")
        
        # Corregir el problema específico
        # El error común es que se añadió un try dentro de otro método sin cerrar
        
        # Buscar el patrón específico que causó el problema
        fix_pattern = r'''(logger\.info\(f"Created MCP conversation context for session {session_id}"\))
        
        # ✅ CRITICAL FIX: Save new session to Redis
        try:
            await self\.save_conversation_state\(context\)
            logger\.info\(f"✅ New session {session_id} saved to Redis"\)
        except Exception as e:
            logger\.error\(f"❌ Failed to save new session to Redis: {e}")((?:\s*\n\s*try:)?)'''
        
        # Si encuentra un try suelto después, eliminarlo
        content = re.sub(fix_pattern, 
                        r'''\1
        
        # ✅ CRITICAL FIX: Save new session to Redis
        try:
            await self.save_conversation_state(context)
            logger.info(f"✅ New session {session_id} saved to Redis")
        except Exception as e:
            logger.error(f"❌ Failed to save new session to Redis: {e}")''', 
                        content, flags=re.MULTILINE | re.DOTALL)
    
    # Verificar y corregir otros bloques try incompletos
    # Buscar específicamente el método add_conversation_turn
    add_turn_fix = r'''(# Add to turns list\s*context\.turns\.append\(turn\))
        
        # ✅ CRITICAL FIX: Save updated session to Redis after adding turn
        try:
            await self\.save_conversation_state\(context\)
            logger\.info\(f"✅ Session {session_id} updated in Redis with turn {turn.turn_number}"\)
        except Exception as e:
            logger\.error\(f"❌ Failed to save updated session to Redis: {e}")\s*$'''
    
    # Reemplazar asegurando que el bloque try tenga su except
    content = re.sub(add_turn_fix,
                    r'''\1
        
        # ✅ CRITICAL FIX: Save updated session to Redis after adding turn
        try:
            await self.save_conversation_state(context)
            logger.info(f"✅ Session {session_id} updated in Redis with turn {turn.turn_number}")
        except Exception as e:
            logger.error(f"❌ Failed to save updated session to Redis: {e}")''',
                    content, flags=re.MULTILINE)
    
    # Escribir el archivo corregido
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("\n✅ Error de sintaxis corregido")
    
    # Verificar que el archivo es válido Python
    try:
        compile(content, file_path, 'exec')
        print("✅ Archivo validado: sintaxis Python correcta")
    except SyntaxError as e:
        print(f"⚠️ Todavía hay un error de sintaxis en línea {e.lineno}: {e.msg}")
        print("Intentando corrección manual...")
        
        # Si aún hay error, hacer corrección más agresiva
        # Restaurar desde backup y aplicar correcciones manuales
        with open(backup_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Aplicar solo las correcciones esenciales de forma más cuidadosa
        content = apply_manual_fixes(original_content)
        
        # Escribir de nuevo
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Aplicadas correcciones manuales")
    
    return True

def apply_manual_fixes(content):
    """Aplica correcciones manuales más cuidadosas"""
    
    # Buscar el método get_or_create_session
    # Añadir guardado después de crear contexto
    create_context_pattern = r'(logger\.info\(f"Created MCP conversation context for session {session_id}"\))'
    
    # Verificar si ya existe el bloque try-except
    if 'await self.save_conversation_state(context)' not in content:
        content = re.sub(create_context_pattern,
                        r'''\1
        
        # Save new session to Redis
        try:
            await self.save_conversation_state(context)
            logger.info(f"New session {session_id} saved to Redis")
        except Exception as e:
            logger.error(f"Failed to save new session to Redis: {e}")''',
                        content)
    
    # Buscar el método add_conversation_turn
    # Añadir guardado después de append
    append_pattern = r'(context\.turns\.append\(turn\))'
    
    # Verificar si ya existe el guardado después del append
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'context.turns.append(turn)' in line:
            # Verificar las siguientes líneas
            next_lines = '\n'.join(lines[i:i+10])
            if 'save_conversation_state' not in next_lines:
                # Necesitamos añadir el guardado
                indent = len(line) - len(line.lstrip())
                save_block = f'''
{' ' * indent}# Save updated session to Redis
{' ' * indent}try:
{' ' * indent}    await self.save_conversation_state(context)
{' ' * indent}    logger.info(f"Session updated in Redis with new turn")
{' ' * indent}except Exception as e:
{' ' * indent}    logger.error(f"Failed to save updated session: {{e}}")'''
                
                lines.insert(i + 1, save_block)
                content = '\n'.join(lines)
                break
    
    return content

def create_clean_fix_script():
    """Crea un script limpio que aplique las correcciones correctamente"""
    
    clean_script = '''#!/usr/bin/env python3
"""
CLEAN FIX: Aplicar correcciones de persistencia sin errores de sintaxis
"""

import os
import asyncio
import sys
sys.path.append('src')

async def verify_persistence_methods():
    """Verifica que los métodos necesarios existan"""
    from api.mcp.conversation_state_manager import MCPConversationStateManager
    
    manager = MCPConversationStateManager()
    
    # Verificar métodos
    methods = ['save_conversation_state', 'load_conversation_state', 'get_or_create_session']
    
    print("Verificando métodos:")
    for method in methods:
        if hasattr(manager, method):
            print(f"  ✅ {method} exists")
        else:
            print(f"  ❌ {method} MISSING")
    
    # Test rápido
    print("\\nTest rápido de persistencia:")
    try:
        session = await manager.get_or_create_session(
            session_id="test_syntax_fix",
            user_id="test_user",
            market_id="US"
        )
        print(f"  ✅ Session created: {session.session_id}")
        
        # El guardado debería ocurrir automáticamente
        # Verificar cargando
        loaded = await manager.load_conversation_state("test_syntax_fix")
        if loaded:
            print(f"  ✅ Session persisted and loaded!")
        else:
            print(f"  ❌ Session NOT persisted!")
            
    except Exception as e:
        print(f"  ❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_persistence_methods())
'''
    
    with open('verify_persistence_fix.py', 'w', encoding='utf-8') as f:
        f.write(clean_script)
    
    print("\n✅ Script de verificación creado: verify_persistence_fix.py")

if __name__ == "__main__":
    # Cambiar al directorio del proyecto
    os.chdir('C:/Users/yasma/Desktop/retail-recommender-system')
    
    try:
        # Corregir el error de sintaxis
        success = fix_syntax_error()
        
        if success:
            create_clean_fix_script()
            
            print("\n🎯 PRÓXIMOS PASOS:")
            print("1. Verificar la corrección: python verify_persistence_fix.py")
            print("2. Si todo está bien, reiniciar el servidor")
            print("3. Ejecutar el test: python test_turn_increment_fixed.py")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()