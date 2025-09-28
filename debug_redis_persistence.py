#!/usr/bin/env python3
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
    
    print(f"\n1️⃣ Creando nueva sesión: {test_session_id}")
    
    # Crear sesión
    session = await state_manager.get_or_create_session(
        session_id=test_session_id,
        user_id=test_user_id,
        market_id="US"
    )
    
    print(f"   Session created: {session.session_id}")
    print(f"   Turns: {len(session.turns)}")
    
    # Verificar en Redis directamente
    print(f"\n2️⃣ Verificando en Redis...")
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
    print(f"\n3️⃣ Añadiendo un turn...")
    await state_manager.add_conversation_turn(
        session_id=test_session_id,
        user_query="Test query",
        ai_response="Test response",
        recommendations=[],
        intent_info={"intent": "test"},
        market_info={"market_id": "US"}
    )
    
    # Verificar de nuevo
    print(f"\n4️⃣ Verificando después de añadir turn...")
    redis_data2 = await redis_client.get(cache_key)
    if redis_data2:
        print(f"   ✅ Datos actualizados en Redis!")
        import json
        data = json.loads(redis_data2)
        print(f"   Total turns: {data.get('total_turns', 0)}")
    else:
        print(f"   ❌ SIGUE SIN HABER DATOS EN REDIS!")
    
    # Cargar sesión de nuevo
    print(f"\n5️⃣ Cargando sesión desde Redis...")
    loaded_session = await state_manager.load_conversation_state(test_session_id)
    if loaded_session:
        print(f"   ✅ Sesión cargada!")
        print(f"   Turns: {len(loaded_session.turns)}")
    else:
        print(f"   ❌ No se pudo cargar la sesión!")
    
    await redis_client.close()

if __name__ == "__main__":
    asyncio.run(debug_redis_persistence())
