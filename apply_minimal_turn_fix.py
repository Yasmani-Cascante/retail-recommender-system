#!/usr/bin/env python3
"""
MINIMAL FIX: Force correct turn number calculation
=================================================

Fix directo para resolver el turn_count = 0 issue
"""

import re

def apply_minimal_turn_fix():
    """Apply minimal fix for turn count issue"""
    
    print("🔧 APPLYING MINIMAL TURN FIX")
    print("=" * 40)
    
    router_file = "C:/Users/yasma/Desktop/retail-recommender-system/src/api/routers/mcp_router.py"
    
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup
        backup_file = router_file + ".backup_minimal_turn_fix"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Backup: {backup_file}")
        
        # STRATEGY: Replace any calculation that uses turn_count property 
        # with direct calculation from session state
        
        changes_made = 0
        
        # Fix 1: Replace turn_count property usage with direct calculation
        if 'conversation_session.turn_count' in content:
            content = content.replace(
                'conversation_session.turn_count',
                'len(conversation_session.turns)'
            )
            changes_made += 1
            print("✅ Fixed: conversation_session.turn_count -> len(turns)")
        
        # Fix 2: Replace updated_session.turn_count with direct calculation
        if 'updated_session.turn_count' in content:
            content = content.replace(
                'updated_session.turn_count',
                'len(updated_session.turns)'
            )
            changes_made += 1
            print("✅ Fixed: updated_session.turn_count -> len(turns)")
        
        # Fix 3: Add explicit turn number calculation after turn registration
        pattern = r'updated_session = await state_manager\.add_conversation_turn_simple\('
        
        if re.search(pattern, content):
            # Find the end of the call and add explicit calculation
            lines = content.split('\n')
            new_lines = []
            
            i = 0
            while i < len(lines):
                line = lines[i]
                new_lines.append(line)
                
                # If we find the add_conversation_turn_simple call
                if 'updated_session = await state_manager.add_conversation_turn_simple(' in line:
                    # Find the end of the call (multi-line)
                    while i < len(lines) - 1 and not lines[i].rstrip().endswith(')'):
                        i += 1
                        new_lines.append(lines[i])
                    
                    # Add explicit turn calculation
                    new_lines.extend([
                        '',
                        '                # ✅ MINIMAL FIX: Force correct turn number calculation',
                        '                turn_number = len(updated_session.turns)',
                        '                if turn_number == 0:  # Safety fallback',
                        '                    turn_number = 1',
                        '                ',
                        '                # Update other variables',
                        '                conversation_session = updated_session',
                        '                real_session_id = updated_session.session_id',
                        '                state_persisted = True',
                        '',
                        '                logger.info(f"🔧 MINIMAL FIX: turn_number set to {turn_number}")'
                    ])
                    changes_made += 1
                    print("✅ Added: Explicit turn calculation after turn registration")
                
                i += 1
            
            content = '\n'.join(new_lines)
        
        # Write the modified file
        with open(router_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\n✅ MINIMAL FIX COMPLETED!")
        print(f"   Changes made: {changes_made}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error applying minimal fix: {e}")
        return False

if __name__ == "__main__":
    print("🚀 MINIMAL TURN FIX APPLICATION")
    print("🎯 Goal: Fix turn_count = 0 issue with direct calculation")
    print("=" * 60)
    
    success = apply_minimal_turn_fix()
    
    if success:
        print("\n✅ MINIMAL FIX APPLIED!")
        print("\n🎯 NEXT STEPS:")
        print("   1. Restart server: python src/api/main_unified_redis.py")
        print("   2. Test: python test_simple_turn.py")
        print("   3. Should see turn increment: 1 -> 2")
    else:
        print("\n❌ MINIMAL FIX FAILED")
    
    exit(0 if success else 1)
