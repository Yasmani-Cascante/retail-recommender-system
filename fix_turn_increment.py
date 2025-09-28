#!/usr/bin/env python3
"""
FIX FINAL: Turn Number Increment Issue
=====================================

PROBLEMA CONFIRMADO:
- mcp_state_manager existe y funciona ✅
- Session ID es consistente ✅ 
- State persisted = True ✅
- Pero turn numbers no incrementan ❌

CAUSA RAÍZ:
- mcp_router.py no está usando mcp_state_manager correctamente
- O add_conversation_turn_simple() no está incrementando turn_count

SOLUCIÓN:
- Debug y fix del flujo de turn registration en mcp_router.py
"""

import re
import os

def analyze_mcp_router_turn_flow():
    """
    Analizar el flujo de turn registration en mcp_router.py
    """
    
    print("🔍 ANALYZING TURN REGISTRATION FLOW IN MCP_ROUTER")
    print("=" * 60)
    
    router_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/routers/mcp_router.py"
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Buscar cómo se obtiene el state_manager
        state_manager_pattern = r'state_manager = get_conversation_state_manager\(\)'
        if re.search(state_manager_pattern, content):
            print("✅ Found state_manager = get_conversation_state_manager()")
        else:
            print("❌ state_manager initialization not found")
            return False
        
        # Buscar el uso de state_manager para get_or_create_session
        session_pattern = r'conversation_session = await state_manager\.get_or_create_session\('
        if re.search(session_pattern, content):
            print("✅ Found get_or_create_session call")
        else:
            print("❌ get_or_create_session call not found")
            return False
        
        # Buscar add_conversation_turn calls
        turn_patterns = [
            r'add_conversation_turn_simple\(',
            r'add_conversation_turn\('
        ]
        
        turn_calls_found = 0
        for pattern in turn_patterns:
            matches = re.findall(pattern, content)
            turn_calls_found += len(matches)
            if matches:
                print(f"✅ Found {len(matches)} calls to {pattern[:-1]}")
        
        if turn_calls_found == 0:
            print("❌ No add_conversation_turn calls found - THIS IS THE PROBLEM!")
            return False
        
        # Buscar save_conversation_state calls
        save_pattern = r'save_conversation_state\('
        save_matches = re.findall(save_pattern, content)
        if save_matches:
            print(f"✅ Found {len(save_matches)} save_conversation_state calls")
        else:
            print("❌ No save_conversation_state calls found")
        
        return True
        
    except Exception as e:
        print(f"❌ Error analyzing router: {e}")
        return False

def fix_turn_registration_in_router():
    """
    Fix el registro de turns en mcp_router.py
    """
    
    print("\\n🔧 FIXING TURN REGISTRATION IN MCP_ROUTER")
    print("=" * 50)
    
    router_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/routers/mcp_router.py"
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        backup_file = router_file + ".backup_turn_fix"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup created: {backup_file}")
        
        # Buscar donde se construye la respuesta final y agregar turn registration
        # Buscar el patrón donde se asigna final_session_id
        final_response_pattern = r'# Asegurar session_id válido \(ahora usando real_session_id actualizado\)\s*final_session_id = real_session_id'
        
        if re.search(final_response_pattern, content):
            # Insertar turn registration justo antes de construir la respuesta final
            turn_registration_code = '''
        # ==========================================
        # CRITICAL FIX: TURN REGISTRATION AND PERSISTENCE
        # ==========================================
        
        # Registrar turn en conversación y incrementar turn_count
        if state_manager and conversation_session:
            try:
                logger.info(f"🔧 TURN REGISTRATION: Starting turn registration for session {conversation_session.session_id}")
                logger.info(f"🔧 TURN REGISTRATION: Current turn_count before: {conversation_session.turn_count}")
                
                # Usar add_conversation_turn_simple para incrementar turn
                updated_session = await state_manager.add_conversation_turn_simple(
                    conversation_session,
                    conversation.query,
                    final_ai_response,
                    metadata={
                        "recommendations_count": len(safe_recommendations),
                        "processing_time_ms": (time.time() - start_time) * 1000,
                        "mcp_available": True,
                        "source": "mcp_router_fix"
                    }
                )
                
                logger.info(f"🔧 TURN REGISTRATION: Turn_count after add_turn: {updated_session.turn_count}")
                
                # Actualizar variables con el session actualizado
                conversation_session = updated_session
                real_session_id = updated_session.session_id
                turn_number = updated_session.turn_count
                
                # Guardar estado inmediatamente
                save_success = await state_manager.save_conversation_state(
                    updated_session.session_id, 
                    updated_session
                )
                
                logger.info(f"🔧 TURN REGISTRATION: Save successful: {save_success}")
                logger.info(f"🔧 TURN REGISTRATION: Final turn_number: {turn_number}")
                
                # Verificar que se guardó correctamente
                test_load = await state_manager.load_conversation_state(updated_session.session_id)
                if test_load:
                    logger.info(f"🔧 TURN REGISTRATION: Verification load successful, turn_count: {test_load.turn_count}")
                else:
                    logger.error(f"🔧 TURN REGISTRATION: Verification load failed")
                
            except Exception as turn_error:
                logger.error(f"❌ TURN REGISTRATION ERROR: {turn_error}")
                import traceback
                logger.error(f"❌ TURN REGISTRATION TRACEBACK: {traceback.format_exc()}")
        else:
            logger.warning(f"⚠️ TURN REGISTRATION: Skipped - state_manager: {state_manager is not None}, conversation_session: {conversation_session is not None}")
        '''
            
            # Insertar el código antes de "final_session_id = real_session_id"
            content = content.replace(
                "# Asegurar session_id válido (ahora usando real_session_id actualizado)\\n        final_session_id = real_session_id",
                turn_registration_code + "\\n        # Asegurar session_id válido (ahora usando real_session_id actualizado)\\n        final_session_id = real_session_id"
            )
            
            print("✅ Added turn registration code before final response")
        else:
            print("⚠️ Could not find final_session_id assignment, searching for alternative insertion point")
            
            # Buscar patrón alternativo
            alt_pattern = r'return \{'
            matches = list(re.finditer(alt_pattern, content))
            
            if matches:
                # Insertar antes del último return (respuesta final)
                last_return = matches[-1]
                insertion_point = last_return.start()
                
                turn_registration_code = '''        # ==========================================
        # CRITICAL FIX: TURN REGISTRATION AND PERSISTENCE
        # ==========================================
        
        # Registrar turn en conversación ANTES de retornar respuesta
        if state_manager and conversation_session:
            try:
                logger.info(f"🔧 TURN FIX: Registering turn for session {conversation_session.session_id}")
                
                # Usar add_conversation_turn_simple para incrementar turn
                updated_session = await state_manager.add_conversation_turn_simple(
                    conversation_session,
                    conversation.query,
                    final_ai_response or ai_response or "Response processed",
                    metadata={
                        "recommendations_count": len(safe_recommendations),
                        "processing_time_ms": (time.time() - start_time) * 1000,
                        "source": "mcp_router_turn_fix"
                    }
                )
                
                # Actualizar turn_number con el valor real
                turn_number = updated_session.turn_count
                real_session_id = updated_session.session_id
                
                # Guardar estado
                await state_manager.save_conversation_state(updated_session.session_id, updated_session)
                
                logger.info(f"✅ TURN FIX: Turn registered successfully, new count: {turn_number}")
                
            except Exception as turn_fix_error:
                logger.error(f"❌ TURN FIX ERROR: {turn_fix_error}")
        
        '''
                
                content = content[:insertion_point] + turn_registration_code + content[insertion_point:]
                print("✅ Added turn registration code before final return")
        
        # Asegurar que turn_number se use en session_metadata
        session_metadata_pattern = r'"turn_number": turn_number,'
        if session_metadata_pattern in content:
            print("✅ turn_number already used in session_metadata")
        else:
            # Buscar session_metadata y asegurar que use turn_number
            content = re.sub(
                r'"turn_number": \d+,',
                '"turn_number": turn_number,',
                content
            )
            print("✅ Updated session_metadata to use turn_number variable")
        
        # Escribir archivo modificado
        with open(router_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Turn registration fix applied to {router_file}")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing turn registration: {e}")
        return False

def create_turn_test_script():
    """
    Crear script específico para testear turn increment
    """
    
    test_script = '''#!/usr/bin/env python3
"""
TURN INCREMENT TEST: Specific test for turn number increment
"""

import requests
import time
import json

def test_turn_increment_specific():
    """Test específico para increment de turn numbers"""
    
    print("🔢 TURN INCREMENT SPECIFIC TEST")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    api_key = "2fed9999056fab6dac5654238f0cae1c"
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    # Session ID único
    session_id = f"turn_test_{int(time.time())}"
    
    print(f"Session ID: {session_id}")
    
    # Conversación 1
    print("\\n📤 Conversación 1:")
    payload1 = {
        "query": "Hello, I need help with shoes",
        "user_id": "turn_test_user",
        "session_id": session_id,
        "market_id": "US"
    }
    
    response1 = requests.post(f"{base_url}/v1/mcp/conversation", headers=headers, json=payload1, timeout=20)
    
    if response1.status_code == 200:
        data1 = response1.json()
        turn1 = data1.get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn number: {turn1}")
    else:
        print(f"   Error: {response1.status_code}")
        return False
    
    time.sleep(2)
    
    # Conversación 2
    print("\\n📤 Conversación 2:")
    payload2 = {
        "query": "What about running shoes specifically?",
        "user_id": "turn_test_user",
        "session_id": session_id,  # SAME SESSION
        "market_id": "US"
    }
    
    response2 = requests.post(f"{base_url}/v1/mcp/conversation", headers=headers, json=payload2, timeout=20)
    
    if response2.status_code == 200:
        data2 = response2.json()
        turn2 = data2.get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn number: {turn2}")
    else:
        print(f"   Error: {response2.status_code}")
        return False
    
    time.sleep(2)
    
    # Conversación 3
    print("\\n📤 Conversación 3:")
    payload3 = {
        "query": "Show me blue running shoes",
        "user_id": "turn_test_user", 
        "session_id": session_id,  # SAME SESSION
        "market_id": "US"
    }
    
    response3 = requests.post(f"{base_url}/v1/mcp/conversation", headers=headers, json=payload3, timeout=20)
    
    if response3.status_code == 200:
        data3 = response3.json()
        turn3 = data3.get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn number: {turn3}")
    else:
        print(f"   Error: {response3.status_code}")
        return False
    
    # Análisis
    print(f"\\n🔍 TURN PROGRESSION ANALYSIS:")
    print(f"   Conversation 1: {turn1}")
    print(f"   Conversation 2: {turn2}")
    print(f"   Conversation 3: {turn3}")
    
    success = turn1 == 1 and turn2 == 2 and turn3 == 3
    
    if success:
        print("\\n🎉 ✅ TURN INCREMENT WORKING PERFECTLY!")
        print("   Turn numbers increment correctly: 1 → 2 → 3")
        return True
    else:
        print("\\n❌ TURN INCREMENT STILL NOT WORKING")
        expected = [1, 2, 3]
        actual = [turn1, turn2, turn3]
        for i, (exp, act) in enumerate(zip(expected, actual)):
            status = "✅" if exp == act else "❌"
            print(f"   Conv {i+1}: Expected {exp}, Got {act} {status}")
        return False

if __name__ == "__main__":
    success = test_turn_increment_specific()
    exit(0 if success else 1)
'''
    
    with open("C:/Users/yasma/Desktop/retail-recommender-system/test_turn_increment.py", 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print("✅ Created turn increment test: test_turn_increment.py")

def main():
    """Función principal"""
    
    print("🚀 TURN NUMBER INCREMENT FIX")
    print("🎯 Goal: Fix turn numbers not incrementing (1→2→3)")
    print("=" * 60)
    
    # Analizar flujo actual
    analysis_ok = analyze_mcp_router_turn_flow()
    
    if not analysis_ok:
        print("❌ Router analysis failed - structural issues found")
    
    # Aplicar fix
    fix_ok = fix_turn_registration_in_router()
    
    if fix_ok:
        print("\\n✅ TURN REGISTRATION FIX APPLIED!")
        
        # Crear test específico
        create_turn_test_script()
        
        print("\\n🎯 NEXT STEPS:")
        print("   1. Restart server: python src/api/main_unified_redis.py") 
        print("   2. Test turn increment: python test_turn_increment.py")
        print("   3. If working, run final validation")
        
        return True
    else:
        print("\\n❌ TURN FIX FAILED")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
