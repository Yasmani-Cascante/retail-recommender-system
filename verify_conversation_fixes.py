#!/usr/bin/env python3
"""
VERIFICACIÓN: Correcciones de persistencia aplicadas
====================================================
"""

import asyncio
import sys
import os

# Cambiar al directorio del proyecto
os.chdir('C:/Users/yasma/Desktop/retail-recommender-system')
sys.path.append('src')

async def verify_fixes():
    """Verifica que las correcciones funcionan correctamente"""
    
    print("🔍 VERIFICANDO CORRECCIONES")
    print("=" * 50)
    
    # 1. Verificar sintaxis
    print("\n1️⃣ Verificando sintaxis del archivo...")
    try:
        with open('src/api/mcp/conversation_state_manager.py', 'r', encoding='utf-8') as f:
            content = f.read()
        compile(content, 'conversation_state_manager.py', 'exec')
        print("   ✅ Sintaxis correcta")
    except SyntaxError as e:
        print(f"   ❌ Error de sintaxis en línea {e.lineno}: {e.msg}")
        return False
    
    # 2. Verificar imports
    print("\n2️⃣ Verificando imports...")
    try:
        from api.mcp.conversation_state_manager import MCPConversationStateManager, get_conversation_state_manager
        print("   ✅ Imports exitosos")
    except Exception as e:
        print(f"   ❌ Error en imports: {e}")
        return False
    
    # 3. Verificar Redis
    print("\n3️⃣ Verificando conexión Redis...")
    try:
        from api.core.redis_client import RedisClient
        redis = RedisClient()
        connected = await redis.ensure_connected()
        if connected:
            print("   ✅ Redis conectado")
        else:
            print("   ⚠️ Redis no disponible (las sesiones se guardarán en memoria)")
    except Exception as e:
        print(f"   ⚠️ Redis error: {e}")
    
    # 4. Test funcional rápido
    print("\n4️⃣ Test funcional de persistencia...")
    try:
        manager = get_conversation_state_manager()
        
        # Crear sesión
        test_session_id = "verify_test_session"
        session = await manager.get_or_create_session(
            session_id=test_session_id,
            user_id="test_user",
            market_id="US"
        )
        print(f"   ✅ Sesión creada: {session.session_id}")
        print(f"   ✅ Turns iniciales: {len(session.turns)}")
        
        # Verificar persistencia
        loaded = await manager.load_conversation_state(test_session_id)
        if loaded:
            print(f"   ✅ Sesión persistida y cargada exitosamente")
        else:
            print(f"   ⚠️ Sesión no se pudo cargar (verificar Redis)")
        
        # Añadir un turn
        await manager.add_conversation_turn(
            session_id=test_session_id,
            user_query="Test query",
            ai_response="Test response",
            recommendations=[],
            intent_info={"intent": "test"},
            market_info={"market_id": "US"}
        )
        print(f"   ✅ Turn añadido")
        
        # Cargar de nuevo
        loaded2 = await manager.load_conversation_state(test_session_id)
        if loaded2 and len(loaded2.turns) > 0:
            print(f"   ✅ Turn persistido: {len(loaded2.turns)} turns totales")
        else:
            print(f"   ⚠️ Turn no persistido")
            
    except Exception as e:
        print(f"   ❌ Error en test funcional: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n✅ VERIFICACIÓN COMPLETADA")
    return True

async def test_turn_increment():
    """Test específico del incremento de turn_number"""
    
    print("\n\n🧪 TEST TURN INCREMENT")
    print("=" * 50)
    
    from api.mcp.conversation_state_manager import get_conversation_state_manager
    
    manager = get_conversation_state_manager()
    session_id = f"turn_test_{int(asyncio.get_event_loop().time())}"
    
    # Crear sesión nueva
    session = await manager.get_or_create_session(
        session_id=session_id,
        user_id="test_user",
        market_id="US"
    )
    
    print(f"Sesión creada: {session_id}")
    print(f"Turns iniciales: {len(session.turns)}")
    
    # Añadir 3 turns
    for i in range(3):
        await manager.add_conversation_turn(
            session_id=session_id,
            user_query=f"Query {i+1}",
            ai_response=f"Response {i+1}",
            recommendations=[],
            intent_info={"intent": "test"},
            market_info={"market_id": "US"}
        )
        
        # Cargar y verificar
        loaded = await manager.load_conversation_state(session_id)
        if loaded:
            print(f"Turn {i+1}: {len(loaded.turns)} turns en sesión")
        else:
            print(f"Turn {i+1}: No se pudo cargar la sesión")
    
    print("\n✅ Test completado")

if __name__ == "__main__":
    print("🚀 INICIANDO VERIFICACIÓN DE CORRECCIONES\n")
    
    async def main():
        success = await verify_fixes()
        if success:
            await test_turn_increment()
    
    asyncio.run(main())
    
    print("\n📝 PRÓXIMOS PASOS:")
    print("1. Si todo está ✅, reinicia el servidor")
    print("2. Ejecuta: python test_turn_increment_fixed.py")
    print("3. Verifica en los logs que Redis está guardando las sesiones")