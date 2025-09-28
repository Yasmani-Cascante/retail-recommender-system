#!/usr/bin/env python3
"""
FIX DIRECTO: Replace hardcoded turn_number = 1 assignments
==========================================================

PROBLEMA IDENTIFICADO:
- Múltiples "turn_number = 1" hardcodeados sobrescribiendo el valor real
- El valor correcto se calcula pero se sobrescribe después

SOLUCIÓN SIMPLE:
- Reemplazar todas las asignaciones hardcodeadas "turn_number = 1"
- Mantener solo las asignaciones dinámicas
"""

import re
import os

def fix_hardcoded_turn_numbers():
    """
    Fix directo: eliminar asignaciones hardcodeadas de turn_number = 1
    """
    
    print("🔧 FIXING HARDCODED TURN_NUMBER ASSIGNMENTS")
    print("=" * 50)
    
    router_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/routers/mcp_router.py"
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        backup_file = router_file + ".backup_hardcode_fix"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup created: {backup_file}")
        
        # Contador de cambios
        changes_made = 0
        
        # FIX 1: Reemplazar "turn_number = 1" con cálculo dinámico
        # Pero preservar comentarios importantes
        
        # Patrón para "turn_number = 1" seguido de comentario que indica que se actualizará
        pattern1 = r'turn_number = 1  # Temporal, se actualizará después del registro exitoso'
        if pattern1 in content:
            content = content.replace(
                pattern1,
                'turn_number = conversation_session.turn_count if conversation_session else 1  # Usar valor real del session'
            )
            changes_made += 1
            print("✅ Fixed: Temporal assignment with dynamic calculation")
        
        # FIX 2: Otros "turn_number = 1" genéricos
        # Necesitamos ser cuidadosos para no romper código legítimo
        lines = content.split('\\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            # Si la línea contiene "turn_number = 1" pero NO es una declaración legítima
            if 'turn_number = 1' in line and 'conversation_session' not in line:
                # Verificar el contexto para asegurar que no es una inicialización legítima
                context_lines = lines[max(0, i-2):i+3]  # 2 líneas antes y después
                context = '\\n'.join(context_lines)
                
                # Si está en un contexto de fallback, usar valor dinámico
                if any(keyword in context for keyword in ['fallback', 'Fallback', 'else:', 'except:']):
                    # Reemplazar con cálculo dinámico
                    fixed_line = line.replace(
                        'turn_number = 1',
                        'turn_number = conversation_session.turn_count if conversation_session else 1'
                    )
                    fixed_lines.append(fixed_line)
                    changes_made += 1
                    print(f"✅ Fixed line {i+1}: {line.strip()} -> dynamic calculation")
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)
        
        content = '\\n'.join(fixed_lines)
        
        # FIX 3: Asegurar que después de add_conversation_turn_simple se actualice turn_number
        # Buscar el patrón y agregar assignment explícito
        pattern_after_turn = r'(updated_session = await state_manager\\.add_conversation_turn_simple\\([^\\)]+\\))'
        
        def add_turn_update(match):
            original = match.group(1)
            return original + '''
                
                # ✅ CRITICAL: Update turn_number immediately after turn registration
                turn_number = updated_session.turn_count
                conversation_session = updated_session
                real_session_id = updated_session.session_id
                state_persisted = True
                
                logger.info(f"🔧 TURN UPDATE: turn_number updated to {turn_number} for session {real_session_id}")'''
        
        if re.search(pattern_after_turn, content, re.DOTALL):
            content = re.sub(pattern_after_turn, add_turn_update, content, flags=re.DOTALL)
            changes_made += 1
            print("✅ Added turn_number update after add_conversation_turn_simple")
        
        # FIX 4: En session_metadata, asegurar que use turn_number variable
        # Reemplazar cualquier "turn_number": 1 hardcodeado en session_metadata
        content = re.sub(
            r'"turn_number": 1([,}])',
            r'"turn_number": turn_number\\1',
            content
        )
        changes_made += 1
        print("✅ Fixed hardcoded turn_number in session_metadata")
        
        # Escribir archivo modificado
        with open(router_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\\n✅ HARDCODE FIX COMPLETED!")
        print(f"   Changes made: {changes_made}")
        print(f"   File updated: {router_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in hardcode fix: {e}")
        return False

def create_simple_test():
    """
    Crear test simple para verificar el fix
    """
    
    simple_test = '''#!/usr/bin/env python3
"""
SIMPLE TURN TEST: Quick verification
"""

import requests
import time

def test_simple_turn_increment():
    """Test simple de 2 conversaciones"""
    
    print("🔢 SIMPLE TURN INCREMENT TEST")
    print("=" * 40)
    
    base_url = "http://localhost:8000"
    headers = {
        "X-API-Key": "2fed9999056fab6dac5654238f0cae1c",
        "Content-Type": "application/json"
    }
    
    session_id = f"simple_test_{int(time.time())}"
    
    # Conversación 1
    print("📤 Conversation 1...")
    response1 = requests.post(f"{base_url}/v1/mcp/conversation", 
        headers=headers, 
        json={
            "query": "I need shoes",
            "user_id": "simple_user",
            "session_id": session_id,
            "market_id": "US"
        }, 
        timeout=20
    )
    
    if response1.status_code == 200:
        turn1 = response1.json().get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn 1: {turn1}")
    else:
        print(f"   Error: {response1.status_code}")
        return False
    
    time.sleep(2)
    
    # Conversación 2
    print("📤 Conversation 2...")
    response2 = requests.post(f"{base_url}/v1/mcp/conversation", 
        headers=headers, 
        json={
            "query": "What about running shoes?",
            "user_id": "simple_user", 
            "session_id": session_id,
            "market_id": "US"
        }, 
        timeout=20
    )
    
    if response2.status_code == 200:
        turn2 = response2.json().get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn 2: {turn2}")
    else:
        print(f"   Error: {response2.status_code}")
        return False
    
    # Resultado
    print(f"\\n🔍 RESULT:")
    print(f"   Turn 1: {turn1}")
    print(f"   Turn 2: {turn2}")
    
    if turn2 > turn1:
        print(f"\\n🎉 ✅ SUCCESS! Turn incremented from {turn1} to {turn2}")
        return True
    else:
        print(f"\\n❌ FAILED: Turn did not increment")
        return False

if __name__ == "__main__":
    success = test_simple_turn_increment()
    print(f"\\nResult: {'PASSED' if success else 'FAILED'}")
'''
    
    with open("C:/Users/yasma/Desktop/retail-recommender-system/test_simple_turn.py", 'w', encoding='utf-8') as f:
        f.write(simple_test)
    
    print("✅ Created simple test: test_simple_turn.py")

def main():
    """Función principal"""
    
    print("🚀 HARDCODED TURN_NUMBER FIX")
    print("🎯 Goal: Remove hardcoded turn_number = 1 assignments")
    print("=" * 60)
    
    # Aplicar fix de hardcoded values
    fix_ok = fix_hardcoded_turn_numbers()
    
    if fix_ok:
        print("\\n✅ HARDCODE FIX APPLIED SUCCESSFULLY!")
        
        # Crear test simple
        create_simple_test()
        
        print("\\n🎯 NEXT STEPS:")
        print("   1. Restart server: python src/api/main_unified_redis.py")
        print("   2. Simple test: python test_simple_turn.py")
        print("   3. If working, run full test: python test_turn_increment.py")
        
        return True
    else:
        print("\\n❌ HARDCODE FIX FAILED")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
