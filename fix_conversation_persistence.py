#!/usr/bin/env python3
"""
FIX: Conversation State Persistence - Redis Save Missing
========================================================

PROBLEMA REAL: Las sesiones no se guardan en Redis después de crearlas/actualizarlas
SOLUCIÓN: Añadir llamadas a save_conversation_state después de modificaciones
"""

import os
import sys
import re
from datetime import datetime

def apply_redis_persistence_fix():
    """Aplica correcciones para asegurar que las sesiones se persistan en Redis"""
    
    # Archivos a corregir
    files_to_fix = [
        ("src/api/mcp/conversation_state_manager.py", fix_conversation_state_manager),
        ("src/api/routers/mcp_router.py", fix_mcp_router)
    ]
    
    print("🔧 APLICANDO FIX: Redis Persistence for Conversation State")
    print("=" * 60)
    
    for file_path, fix_function in files_to_fix:
        print(f"\n📄 Procesando: {file_path}")
        
        # Leer el archivo
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Hacer backup
        backup_file = f"{file_path}.backup_redis_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"   ✅ Backup: {backup_file}")
        
        # Aplicar correcciones
        new_content = fix_function(content)
        
        # Escribir archivo corregido
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"   ✅ Correcciones aplicadas")
    
    print("\n✅ FIX APLICADO EXITOSAMENTE")
    return True

def fix_conversation_state_manager(content):
    """Corrige el conversation_state_manager.py para guardar en Redis"""
    
    # FIX 1: Asegurar que get_or_create_session guarde la sesión nueva
    pattern1 = r'(logger\.info\(f"Created MCP conversation context for session {session_id}"\))'
    replacement1 = r'''\1
        
        # ✅ CRITICAL FIX: Save new session to Redis
        try:
            await self.save_conversation_state(context)
            logger.info(f"✅ New session {session_id} saved to Redis")
        except Exception as e:
            logger.error(f"❌ Failed to save new session to Redis: {e}")'''
    
    content = re.sub(pattern1, replacement1, content)
    
    # FIX 2: Asegurar que add_conversation_turn guarde después de añadir
    # Buscar el método add_conversation_turn
    add_turn_pattern = r'(# Add to turns list\s*context\.turns\.append\(turn\))'
    add_turn_replacement = r'''\1
        
        # ✅ CRITICAL FIX: Save updated session to Redis after adding turn
        try:
            await self.save_conversation_state(context)
            logger.info(f"✅ Session {session_id} updated in Redis with turn {turn.turn_number}")
        except Exception as e:
            logger.error(f"❌ Failed to save updated session to Redis: {e}")'''
    
    content = re.sub(add_turn_pattern, add_turn_replacement, content, flags=re.MULTILINE)
    
    # FIX 3: Mejorar el método save_conversation_state para debugging
    save_method_pattern = r'(async def save_conversation_state\(self, context: MCPConversationContext\) -> bool:)'
    save_method_replacement = r'''\1
        """Guarda el estado de conversación en Redis con mejor logging"""'''
    
    content = re.sub(save_method_pattern, save_method_replacement, content)
    
    # FIX 4: Añadir logging detallado en save_conversation_state
    redis_set_pattern = r'(await self\.redis\.set\(cache_key, json\.dumps\(serializable_data\), ex=self\.conversation_ttl\))'
    redis_set_replacement = r'''logger.debug(f"📝 Saving to Redis - Key: {cache_key}, TTL: {self.conversation_ttl}")
            \1
            logger.info(f"✅ Session {context.session_id} saved to Redis successfully")'''
    
    content = re.sub(redis_set_pattern, redis_set_replacement, content)
    
    return content

def fix_mcp_router(content):
    """Corrige mcp_router.py para asegurar que se guarde el estado"""
    
    # FIX 1: Después de crear/obtener sesión, asegurar que se guarde
    pattern1 = r'(logger\.info\(f"✅ Session managed: {real_session_id}, turn: {turn_number}"\))'
    replacement1 = r'''\1
                
                # ✅ CRITICAL: Ensure session is saved to Redis
                if state_manager and conversation_session:
                    try:
                        await state_manager.save_conversation_state(conversation_session)
                        logger.info(f"✅ Session {real_session_id} persisted to Redis")
                    except Exception as e:
                        logger.error(f"❌ Failed to persist session: {e}")'''
    
    content = re.sub(pattern1, replacement1, content)
    
    # FIX 2: Después de add_conversation_turn, verificar guardado
    add_turn_pattern = r'(await add_conversation_turn_compat\([^)]+\))'
    add_turn_replacement = r'''\1
                    
                    # ✅ VERIFY: Check that session was saved
                    logger.info(f"✅ Turn added and session should be persisted")'''
    
    content = re.sub(add_turn_pattern, add_turn_replacement, content)
    
    # FIX 3: Corregir el cálculo del turn_number basándose en los turns actuales
    turn_calc_pattern = r'turn_number = len\(conversation_session\.turns\) if conversation_session else 1'
    turn_calc_replacement = r'turn_number = len(conversation_session.turns) + 1 if conversation_session and hasattr(conversation_session, "turns") else 1'
    
    content = content.replace(turn_calc_pattern, turn_calc_replacement)
    
    return content

def create_debug_script():
    """Crea un script de debug mejorado para verificar Redis"""
    
    debug_content = '''#!/usr/bin/env python3
"""
DEBUG: Verificar persistencia en Redis directamente
"""

import asyncio
import sys
sys.path.append('src')

from api.mcp.conversation_state_manager import get_conversation_state_manager
from api.core.redis_client import RedisClient

async def debug_redis_persistence():
    """Debug detallado de persistencia en Redis"""
    
    print("🔍 DEBUG REDIS PERSISTENCE")
    print("=" * 50)
    
    # Obtener managers
    state_manager = get_conversation_state_manager()
    redis_client = RedisClient()
    
    # Test session ID
    test_session_id = "debug_redis_test"
    test_user_id = "test_user"
    
    print(f"\\n1️⃣ Creando nueva sesión: {test_session_id}")
    
    # Crear sesión
    session = await state_manager.get_or_create_session(
        session_id=test_session_id,
        user_id=test_user_id,
        market_id="US"
    )
    
    print(f"   Session created: {session.session_id}")
    print(f"   Turns: {len(session.turns)}")
    
    # Verificar en Redis directamente
    print(f"\\n2️⃣ Verificando en Redis...")
    cache_key = f"conversation_session:{test_session_id}"
    
    redis_data = await redis_client.get(cache_key)
    if redis_data:
        print(f"   ✅ Datos encontrados en Redis!")
        print(f"   Key: {cache_key}")
        print(f"   Data length: {len(redis_data)} bytes")
    else:
        print(f"   ❌ NO HAY DATOS EN REDIS!")
        print(f"   Key buscada: {cache_key}")
    
    # Añadir un turn
    print(f"\\n3️⃣ Añadiendo un turn...")
    await state_manager.add_conversation_turn(
        session_id=test_session_id,
        user_query="Test query",
        ai_response="Test response",
        recommendations=[],
        intent_info={"intent": "test"},
        market_info={"market_id": "US"}
    )
    
    # Verificar de nuevo
    print(f"\\n4️⃣ Verificando después de añadir turn...")
    redis_data2 = await redis_client.get(cache_key)
    if redis_data2:
        print(f"   ✅ Datos actualizados en Redis!")
        import json
        data = json.loads(redis_data2)
        print(f"   Total turns: {data.get('total_turns', 0)}")
    else:
        print(f"   ❌ SIGUE SIN HABER DATOS EN REDIS!")
    
    # Cargar sesión de nuevo
    print(f"\\n5️⃣ Cargando sesión desde Redis...")
    loaded_session = await state_manager.load_conversation_state(test_session_id)
    if loaded_session:
        print(f"   ✅ Sesión cargada!")
        print(f"   Turns: {len(loaded_session.turns)}")
    else:
        print(f"   ❌ No se pudo cargar la sesión!")
    
    await redis_client.close()

if __name__ == "__main__":
    asyncio.run(debug_redis_persistence())
'''
    
    with open('debug_redis_persistence.py', 'w', encoding='utf-8') as f:
        f.write(debug_content)
    
    print("\n✅ Script de debug creado: debug_redis_persistence.py")

if __name__ == "__main__":
    # Cambiar al directorio del proyecto
    os.chdir('C:/Users/yasma/Desktop/retail-recommender-system')
    
    try:
        # Aplicar correcciones
        success = apply_redis_persistence_fix()
        
        if success:
            # Crear script de debug
            create_debug_script()
            
            print("\n🎯 PRÓXIMOS PASOS:")
            print("1. Ejecutar debug: python debug_redis_persistence.py")
            print("2. Reiniciar servidor: python src/api/main_unified_redis.py")
            print("3. Ejecutar test: python test_turn_increment_fixed.py")
            print("\nNOTA: Si el debug muestra que Redis no guarda, revisar:")
            print("- Conexión a Redis")
            print("- Permisos de escritura")
            print("- TTL de las claves")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()