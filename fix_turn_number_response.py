#!/usr/bin/env python3
"""
FIX ESPECÍFICO: Turn Number Response Update Issue
===============================================

PROBLEMA IDENTIFICADO:
- add_conversation_turn_simple() se ejecuta ✅
- Pero turn_number en respuesta sigue siendo 1 ❌
- Necesitamos asegurar que session_metadata use el valor actualizado

SOLUCIÓN:
- Debug específico del flujo de turn_number en la respuesta
- Fix directo en la construcción de session_metadata
"""

import re
import os

def debug_turn_number_response():
    """
    Debug específico del turn_number en la respuesta
    """
    
    print("🔍 DEBUGGING TURN_NUMBER IN RESPONSE")
    print("=" * 50)
    
    router_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/routers/mcp_router.py"
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Buscar where session_metadata is constructed
        session_metadata_pattern = r'"session_metadata": \{'
        matches = list(re.finditer(session_metadata_pattern, content))
        
        print(f"📋 Found {len(matches)} session_metadata constructions")
        
        # Buscar específicamente el uso de turn_number en session_metadata
        turn_number_in_metadata = re.findall(r'"turn_number": [^,]+', content)
        
        print(f"📋 turn_number usage in metadata:")
        for usage in turn_number_in_metadata:
            print(f"   {usage}")
        
        # Buscar donde se define turn_number variable
        turn_number_assignments = re.findall(r'turn_number = [^\\n]+', content)
        
        print(f"📋 turn_number assignments:")
        for assignment in turn_number_assignments:
            print(f"   {assignment}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error debugging: {e}")
        return False

def fix_turn_number_response_issue():
    """
    Fix específico para asegurar que turn_number se actualice en la respuesta
    """
    
    print("\\n🔧 FIXING TURN_NUMBER RESPONSE ISSUE")
    print("=" * 50)
    
    router_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/routers/mcp_router.py"
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        backup_file = router_file + ".backup_turn_response_fix"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup created: {backup_file}")
        
        # APPROACH 1: Fix direct assignment after turn registration
        # Buscar el pattern donde se hace turn registration y agregar assignment explícito
        
        turn_registration_pattern = r'# Actualizar turn_number con el valor real\\s*turn_number = updated_session\\.turn_count'
        
        if re.search(turn_registration_pattern, content):
            print("✅ Found existing turn_number assignment after turn registration")
        else:
            print("⚠️ turn_number assignment after turn registration not found")
            
            # Buscar donde se hace el turn registration y agregar assignment
            registration_pattern = r'updated_session = await state_manager\\.add_conversation_turn_simple\\('
            
            if re.search(registration_pattern, content):
                # Buscar las líneas después de add_conversation_turn_simple
                lines = content.split('\\n')
                modified_lines = []
                
                for i, line in enumerate(lines):
                    modified_lines.append(line)
                    
                    # Si encontramos la línea de add_conversation_turn_simple
                    if 'updated_session = await state_manager.add_conversation_turn_simple(' in line:
                        # Buscar el final del call (puede ser multi-línea)
                        j = i + 1
                        while j < len(lines) and not lines[j].strip().endswith(')'):
                            modified_lines.append(lines[j])
                            j += 1
                        
                        if j < len(lines):
                            modified_lines.append(lines[j])  # La línea que termina con )
                        
                        # Agregar las líneas de actualización
                        modified_lines.extend([
                            '',
                            '                # ✅ CRITICAL FIX: Update turn_number with REAL value',
                            '                conversation_session = updated_session',
                            '                real_session_id = updated_session.session_id', 
                            '                turn_number = updated_session.turn_count  # ← ESTE ES EL FIX CRÍTICO',
                            '                state_persisted = True',
                            '',
                            '                logger.info(f"🔧 TURN RESPONSE FIX: Updated turn_number to {turn_number}")',
                            '                logger.info(f"🔧 TURN RESPONSE FIX: Session {real_session_id} now has {turn_number} turns")'
                        ])
                        
                        # Skip las líneas que ya procesamos
                        i = j
                        continue
                
                content = '\\n'.join(modified_lines)
                print("✅ Added turn_number update after turn registration")
            else:
                print("❌ Could not find turn registration pattern")
        
        # APPROACH 2: Fix session_metadata construction to ensure it uses updated turn_number
        
        # Buscar todos los lugares donde se construye session_metadata y asegurar que usen turn_number
        session_metadata_pattern = r'"session_metadata": \\{[^}]+\\}'
        
        def fix_session_metadata(match):
            metadata_content = match.group(0)
            
            # Si ya tiene "turn_number": turn_number, está bien
            if '"turn_number": turn_number' in metadata_content:
                return metadata_content
            
            # Si tiene un valor hardcoded como "turn_number": 1, reemplazarlo
            if '"turn_number": 1' in metadata_content or '"turn_number": \\d+' in metadata_content:
                fixed_content = re.sub(r'"turn_number": \\d+', '"turn_number": turn_number', metadata_content)
                return fixed_content
            
            # Si no tiene turn_number, agregarlo
            if '"turn_number"' not in metadata_content:
                # Insertar turn_number después del primer campo
                fixed_content = metadata_content.replace(
                    '{',
                    '{\\n                    "turn_number": turn_number,'
                )
                return fixed_content
            
            return metadata_content
        
        content = re.sub(session_metadata_pattern, fix_session_metadata, content, flags=re.DOTALL)
        print("✅ Fixed session_metadata to use turn_number variable")
        
        # APPROACH 3: Ensure turn_number is properly initialized at the start
        # Buscar donde se inicializa turn_number y asegurar que se actualice correctamente
        
        # Agregar inicialización explícita después de get_or_create_session
        session_creation_pattern = r'conversation_session = await state_manager\\.get_or_create_session\\('
        
        if re.search(session_creation_pattern, content):
            # Buscar las líneas después y agregar inicialización
            lines = content.split('\\n')
            modified_lines = []
            
            for i, line in enumerate(lines):
                modified_lines.append(line)
                
                if 'conversation_session = await state_manager.get_or_create_session(' in line:
                    # Buscar el final del call
                    j = i + 1
                    while j < len(lines) and not lines[j].strip().endswith(')'):
                        modified_lines.append(lines[j])
                        j += 1
                    
                    if j < len(lines):
                        modified_lines.append(lines[j])
                    
                    # Agregar inicialización explícita
                    modified_lines.extend([
                        '',
                        '                # ✅ CRITICAL: Initialize turn_number with current session state',
                        '                turn_number = conversation_session.turn_count',
                        '                logger.info(f"🔧 INITIAL: Session {conversation_session.session_id} has {turn_number} turns")'
                    ])
                    
                    i = j
                    continue
            
            content = '\\n'.join(modified_lines)
            print("✅ Added turn_number initialization after session creation")
        
        # Escribir archivo modificado
        with open(router_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Turn number response fix applied to {router_file}")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing turn number response: {e}")
        return False

def create_detailed_debug_script():
    """
    Crear script de debug detallado para el turn number
    """
    
    debug_script = '''#!/usr/bin/env python3
"""
DETAILED TURN DEBUG: Step by step analysis
"""

import requests
import time
import json

def test_single_conversation_detailed():
    """Test de una conversación con debug detallado"""
    
    print("🔍 DETAILED SINGLE CONVERSATION DEBUG")
    print("=" * 60)
    
    base_url = "http://localhost:8000"
    api_key = "2fed9999056fab6dac5654238f0cae1c"
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    session_id = f"debug_session_{int(time.time())}"
    
    print(f"Session ID: {session_id}")
    
    # Primera conversación con debug completo
    print("\\n📤 CONVERSATION 1 - DETAILED ANALYSIS:")
    payload1 = {
        "query": "I need running shoes",
        "user_id": "debug_user",
        "session_id": session_id,
        "market_id": "US"
    }
    
    response1 = requests.post(f"{base_url}/v1/mcp/conversation", headers=headers, json=payload1, timeout=30)
    
    if response1.status_code == 200:
        data1 = response1.json()
        
        print(f"✅ Response received successfully")
        print(f"📋 Full response keys: {list(data1.keys())}")
        
        session_metadata1 = data1.get("session_metadata", {})
        print(f"📋 Session metadata keys: {list(session_metadata1.keys())}")
        print(f"📋 Session metadata content: {json.dumps(session_metadata1, indent=2)}")
        
        turn_number1 = session_metadata1.get("turn_number", "NOT_FOUND")
        session_id_resp1 = session_metadata1.get("session_id", "NOT_FOUND")
        state_persisted1 = session_metadata1.get("state_persisted", "NOT_FOUND")
        
        print(f"\\n🔍 EXTRACTED VALUES:")
        print(f"   turn_number: {turn_number1} (type: {type(turn_number1)})")
        print(f"   session_id: {session_id_resp1}")
        print(f"   state_persisted: {state_persisted1}")
        
        # Pausa para ver logs del servidor
        print(f"\\n⏳ Check server logs for turn registration messages...")
        time.sleep(3)
        
        # Segunda conversación
        print("\\n📤 CONVERSATION 2 - SAME SESSION:")
        payload2 = {
            "query": "What about blue running shoes?",
            "user_id": "debug_user",
            "session_id": session_id,  # SAME SESSION
            "market_id": "US"
        }
        
        response2 = requests.post(f"{base_url}/v1/mcp/conversation", headers=headers, json=payload2, timeout=30)
        
        if response2.status_code == 200:
            data2 = response2.json()
            
            session_metadata2 = data2.get("session_metadata", {})
            turn_number2 = session_metadata2.get("turn_number", "NOT_FOUND")
            session_id_resp2 = session_metadata2.get("session_id", "NOT_FOUND")
            
            print(f"✅ Second response received")
            print(f"📋 Session metadata: {json.dumps(session_metadata2, indent=2)}")
            
            print(f"\\n🔍 COMPARISON:")
            print(f"   Conv 1 turn_number: {turn_number1}")
            print(f"   Conv 2 turn_number: {turn_number2}")
            print(f"   Session ID consistent: {session_id_resp1 == session_id_resp2}")
            
            if turn_number2 > turn_number1:
                print(f"\\n🎉 ✅ TURN INCREMENT WORKING!")
                print(f"   Successfully incremented from {turn_number1} to {turn_number2}")
            else:
                print(f"\\n❌ TURN INCREMENT STILL FAILING")
                print(f"   Expected: {turn_number1 + 1}, Got: {turn_number2}")
                print(f"\\n💡 CHECK SERVER LOGS FOR:")
                print(f"   - '🔧 TURN REGISTRATION:' messages")
                print(f"   - '🔧 TURN RESPONSE FIX:' messages")
                print(f"   - Any error messages during turn registration")
        else:
            print(f"❌ Second conversation failed: {response2.status_code}")
            print(f"   Error: {response2.text}")
    else:
        print(f"❌ First conversation failed: {response1.status_code}")
        print(f"   Error: {response1.text}")

if __name__ == "__main__":
    test_single_conversation_detailed()
'''
    
    with open("C:/Users/yasma/Desktop/retail-recommender-system/debug_turn_detailed.py", 'w', encoding='utf-8') as f:
        f.write(debug_script)
    
    print("✅ Created detailed debug script: debug_turn_detailed.py")

def main():
    """Función principal"""
    
    print("🚀 TURN NUMBER RESPONSE FIX")
    print("🎯 Goal: Fix turn_number not updating in response")
    print("=" * 60)
    
    # Debug actual
    debug_ok = debug_turn_number_response()
    
    # Aplicar fix específico
    fix_ok = fix_turn_number_response_issue()
    
    if fix_ok:
        print("\\n✅ TURN NUMBER RESPONSE FIX APPLIED!")
        
        # Crear debug script
        create_detailed_debug_script()
        
        print("\\n🎯 NEXT STEPS:")
        print("   1. Restart server: python src/api/main_unified_redis.py")
        print("   2. Detailed debug: python debug_turn_detailed.py")
        print("   3. If still failing, check server logs for turn registration messages")
        print("   4. Test increment: python test_turn_increment.py")
        
        return True
    else:
        print("\\n❌ TURN NUMBER RESPONSE FIX FAILED")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
