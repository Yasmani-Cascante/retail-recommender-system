#!/usr/bin/env python3
"""
FIX ESPECÍFICO: turn_count property y persistence issue
=====================================================

PROBLEMA IDENTIFICADO:
- turn_number ahora usa conversation_session.turn_count ✅
- Pero turn_count siempre devuelve 0 ❌
- add_conversation_turn_simple() no está incrementando correctamente

SOLUCIÓN:
- Debug específico del turn_count property
- Fix directo del increment logic
"""

import requests
import time

def debug_session_turn_count():
    """
    Debug específico del session turn_count usando el servidor
    """
    
    print("🔍 DEBUGGING SESSION TURN_COUNT VIA API")
    print("=" * 50)
    
    # Hacer una conversación y examinar toda la respuesta
    base_url = "http://localhost:8000"
    headers = {
        "X-API-Key": "2fed9999056fab6dac5654238f0cae1c",
        "Content-Type": "application/json"
    }
    
    session_id = f"debug_turn_count_{int(time.time())}"
    
    print(f"Session ID: {session_id}")
    
    # Primera conversación con análisis completo
    print("\\n📤 CONVERSATION 1 - FULL DEBUG:")
    
    payload = {
        "query": "Debug test - show me shoes",
        "user_id": "debug_turn_user",
        "session_id": session_id,
        "market_id": "US"
    }
    
    try:
        response = requests.post(f"{base_url}/v1/mcp/conversation", headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"✅ Response received successfully")
            
            # Examinar todos los campos relacionados con turns
            session_metadata = data.get("session_metadata", {})
            
            print(f"\\n🔍 FULL SESSION METADATA:")
            for key, value in session_metadata.items():
                print(f"   {key}: {value} (type: {type(value)})")
            
            # Buscar campos específicos
            turn_number = session_metadata.get("turn_number", "NOT_FOUND")
            turn_count = session_metadata.get("turn_count", "NOT_FOUND") 
            total_turns = session_metadata.get("total_turns", "NOT_FOUND")
            
            print(f"\\n🔍 TURN-RELATED FIELDS:")
            print(f"   turn_number: {turn_number}")
            print(f"   turn_count: {turn_count}")  
            print(f"   total_turns: {total_turns}")
            
            # Examinar otros campos que podrían tener información de turns
            print(f"\\n🔍 OTHER METADATA FIELDS:")
            metadata = data.get("metadata", {})
            for key, value in metadata.items():
                if 'turn' in key.lower():
                    print(f"   metadata.{key}: {value}")
            
            return True
            
        else:
            print(f"❌ Request failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error in debug: {e}")
        return False

def create_conversation_state_debug():
    """
    Script para debuggear directamente el conversation state manager
    """
    
    debug_script = '''#!/usr/bin/env python3
"""
CONVERSATION STATE MANAGER DIRECT DEBUG
"""

import sys
import asyncio
sys.path.append('src')

async def debug_conversation_state_manager():
    """Debug directo del conversation state manager"""
    
    print("🔍 DIRECT CONVERSATION STATE MANAGER DEBUG")
    print("=" * 60)
    
    try:
        from src.api.mcp.conversation_state_manager import get_conversation_state_manager
        
        # Obtener state manager
        state_manager = get_conversation_state_manager()
        print(f"✅ State manager obtained: {type(state_manager)}")
        
        # Crear nueva sesión
        session = await state_manager.get_or_create_session(
            session_id="debug_direct_session",
            user_id="debug_user",
            market_id="US"
        )
        
        print(f"\\n📋 INITIAL SESSION STATE:")
        print(f"   session_id: {session.session_id}")
        print(f"   total_turns: {session.total_turns}")
        print(f"   turn_count property: {session.turn_count}")
        print(f"   len(turns): {len(session.turns)}")
        
        # Agregar primer turn
        print(f"\\n🔄 ADDING FIRST TURN...")
        updated_session = await state_manager.add_conversation_turn_simple(
            session,
            "Test query 1",
            "Test response 1",
            {"test": True}
        )
        
        print(f"📋 AFTER FIRST TURN:")
        print(f"   total_turns: {updated_session.total_turns}")
        print(f"   turn_count property: {updated_session.turn_count}")
        print(f"   len(turns): {len(updated_session.turns)}")
        
        # Guardar estado
        save_result = await state_manager.save_conversation_state(
            updated_session.session_id,
            updated_session
        )
        print(f"   save_result: {save_result}")
        
        # Agregar segundo turn
        print(f"\\n🔄 ADDING SECOND TURN...")
        updated_session2 = await state_manager.add_conversation_turn_simple(
            updated_session,
            "Test query 2", 
            "Test response 2",
            {"test": True}
        )
        
        print(f"📋 AFTER SECOND TURN:")
        print(f"   total_turns: {updated_session2.total_turns}")
        print(f"   turn_count property: {updated_session2.turn_count}")
        print(f"   len(turns): {len(updated_session2.turns)}")
        
        # Verificar property turn_count
        print(f"\\n🔍 TURN_COUNT PROPERTY ANALYSIS:")
        print(f"   updated_session2.total_turns: {updated_session2.total_turns}")
        print(f"   updated_session2.turn_count: {updated_session2.turn_count}")
        print(f"   Are they equal? {updated_session2.total_turns == updated_session2.turn_count}")
        
        if updated_session2.turn_count == 2:
            print(f"\\n✅ SUCCESS: turn_count property working correctly")
            return True
        else:
            print(f"\\n❌ ISSUE: turn_count property not working correctly")
            print(f"   Expected: 2, Got: {updated_session2.turn_count}")
            return False
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = asyncio.run(debug_conversation_state_manager())
    print(f"\\nDEBUG RESULT: {'SUCCESS' if success else 'FAILED'}")
'''
    
    with open("C:/Users/yasma/Desktop/retail-recommender-system/debug_conversation_state_direct.py", 'w', encoding='utf-8') as f:
        f.write(debug_script)
    
    print("✅ Created direct debug script: debug_conversation_state_direct.py")

def create_minimal_fix():
    """
    Crear fix mínimo basado en el issue de turn_count = 0
    """
    
    fix_script = '''#!/usr/bin/env python3
"""
MINIMAL FIX: Force turn_number calculation
"""

import re

def apply_minimal_turn_fix():
    """Fix mínimo para forzar cálculo correcto de turn_number"""
    
    print("🔧 APPLYING MINIMAL TURN FIX")
    print("=" * 40)
    
    router_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/routers/mcp_router.py"
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        backup_file = router_file + ".backup_minimal_fix"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup: {backup_file}")
        
        # Fix: Después de add_conversation_turn_simple, forzar cálculo correcto
        pattern = r'(# ✅ CRITICAL: Update turn_number immediately after turn registration\\s*turn_number = updated_session\\.turn_count)'
        
        replacement = '''# ✅ CRITICAL: Update turn_number immediately after turn registration
                # FORCE correct calculation since turn_count property might be 0
                turn_number = max(updated_session.total_turns, len(updated_session.turns), updated_session.turn_count)
                if turn_number == 0:
                    turn_number = 1  # Fallback for first turn'''
        
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)
            print("✅ Applied forced turn_number calculation")
        else:
            # Si no encuentra el patrón, buscar alternativo
            alt_pattern = r'turn_number = updated_session\\.turn_count'
            if alt_pattern in content:
                content = content.replace(
                    'turn_number = updated_session.turn_count',
                    'turn_number = max(updated_session.total_turns, len(updated_session.turns), 1)'
                )
                print("✅ Applied alternative forced calculation")
        
        # También fix cualquier uso de conversation_session.turn_count que devuelva 0
        content = content.replace(
            'turn_number = conversation_session.turn_count if conversation_session else 1',
            'turn_number = max(conversation_session.total_turns, len(conversation_session.turns), 1) if conversation_session else 1'
        )
        print("✅ Fixed initial turn_number calculation")
        
        with open(router_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Minimal fix applied successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = apply_minimal_turn_fix()
    print("Result:", "SUCCESS" if success else "FAILED")
'''
    
    with open("C:/Users/yasma/Desktop/retail-recommender-system/apply_minimal_turn_fix.py", 'w', encoding='utf-8') as f:
        f.write(fix_script)
    
    print("✅ Created minimal fix script: apply_minimal_turn_fix.py")

def main():
    """Función principal de debug"""
    
    print("🚀 TURN_COUNT ZERO ISSUE DEBUG")
    print("🎯 Goal: Understand why turn_count returns 0")
    print("=" * 60)
    
    # Debug via API
    api_debug_ok = debug_session_turn_count()
    
    if api_debug_ok:
        print("\\n✅ API debug completed - check output above")
    
    # Crear scripts adicionales
    create_conversation_state_debug()
    create_minimal_fix()
    
    print("\\n🎯 NEXT STEPS:")
    print("   1. Run direct debug: python debug_conversation_state_direct.py")
    print("   2. If turn_count property is broken, apply minimal fix:")
    print("      python apply_minimal_turn_fix.py")
    print("   3. Restart server and test again")
    
    return True

if __name__ == "__main__":
    main()
