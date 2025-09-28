#!/usr/bin/env python3
"""
SOLUCIÓN DEFINITIVA: Use the correct method that actually exists
==============================================================

PROBLEMA RAÍZ IDENTIFICADO:
- No existe add_conversation_turn_simple() ❌
- Por eso len(turns) = 0 siempre
- Necesitamos usar add_conversation_turn() que SÍ existe

SOLUCIÓN:
- Cambiar add_conversation_turn_simple() por add_conversation_turn()
- Adaptar los parámetros correctamente
"""

import re

def fix_use_correct_method():
    """Fix para usar el método correcto que sí existe"""
    
    print("🔧 FIXING: Use correct method that exists")
    print("=" * 50)
    
    router_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/routers/mcp_router.py"
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        backup_file = router_file + ".backup_correct_method"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup: {backup_file}")
        
        # STRATEGY: Replace add_conversation_turn_simple with add_conversation_turn
        # and adapt the parameters
        
        # Pattern to find add_conversation_turn_simple calls
        pattern = r'updated_session = await state_manager\.add_conversation_turn_simple\(\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\s*\)'
        
        def replace_with_correct_method(match):
            context_param = match.group(1).strip()
            user_query = match.group(2).strip()
            ai_response = match.group(3).strip()
            metadata = match.group(4).strip()
            
            # Build the correct call to add_conversation_turn
            return f'''updated_session = await state_manager.add_conversation_turn(
                context={context_param},
                user_query={user_query},
                intent_analysis={{
                    "intent": "general",
                    "confidence": 0.7,
                    "entities": [],
                    "market_context": {{"market_id": {context_param}.current_market_id}}
                }},
                ai_response={ai_response},
                recommendations=[],
                processing_time_ms=0.0
            )'''
        
        # Replace the calls
        new_content = re.sub(pattern, replace_with_correct_method, content, flags=re.DOTALL)
        
        if new_content != content:
            print("✅ Replaced add_conversation_turn_simple with add_conversation_turn")
            content = new_content
        else:
            # Try alternative pattern for multi-line calls
            lines = content.split('\n')
            new_lines = []
            i = 0
            
            while i < len(lines):
                line = lines[i]
                
                if 'await state_manager.add_conversation_turn_simple(' in line:
                    print(f"✅ Found add_conversation_turn_simple call at line {i+1}")
                    
                    # Replace with correct method call
                    indent = ' ' * (len(line) - len(line.lstrip()))
                    
                    new_lines.extend([
                        f'{indent}# ✅ FIXED: Using add_conversation_turn (the method that actually exists)',
                        f'{indent}updated_session = await state_manager.add_conversation_turn(',
                        f'{indent}    context=conversation_session,',
                        f'{indent}    user_query=conversation.query,',
                        f'{indent}    intent_analysis={{',
                        f'{indent}        "intent": "general",',
                        f'{indent}        "confidence": 0.7,',
                        f'{indent}        "entities": [],',
                        f'{indent}        "market_context": {{"market_id": conversation_session.current_market_id}}',
                        f'{indent}    }},',
                        f'{indent}    ai_response=final_ai_response,',
                        f'{indent}    recommendations=[],',
                        f'{indent}    processing_time_ms=(time.time() - start_time) * 1000',
                        f'{indent})'
                    ])
                    
                    # Skip the original multi-line call
                    while i < len(lines) - 1 and not lines[i].rstrip().endswith(')'):
                        i += 1
                    
                    # Skip the closing parenthesis line too
                    if i < len(lines) and lines[i].rstrip().endswith(')'):
                        i += 1
                    
                    continue
                
                new_lines.append(line)
                i += 1
            
            content = '\n'.join(new_lines)
            print("✅ Replaced multi-line add_conversation_turn_simple calls")
        
        # Write the corrected file
        with open(router_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ CORRECT METHOD FIX APPLIED!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 CORRECT METHOD FIX")
    print("🎯 Goal: Use add_conversation_turn() instead of non-existent add_conversation_turn_simple()")
    print("=" * 80)
    
    success = fix_use_correct_method()
    
    if success:
        print("\n✅ CORRECT METHOD FIX APPLIED!")
        print("\n🎯 NEXT STEPS:")
        print("   1. Restart server: python src/api/main_unified_redis.py")
        print("   2. Test: python test_simple_turn.py")
        print("   3. Should see proper turn increment now!")
        print("\n💡 Now using add_conversation_turn() which actually exists and adds turns to the array")
    else:
        print("\n❌ FIX FAILED")
    
    exit(0 if success else 1)
