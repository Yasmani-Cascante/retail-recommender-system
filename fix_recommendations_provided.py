#!/usr/bin/env python3
"""
Fix específico para el problema de recommendations_provided vacío
================================================================

PROBLEMA IDENTIFICADO en logs:
- Turn 1: recommendations_provided value: []
- Turn 2: recommendations_provided value: []
- RESULTADO: Diversification needed: False, shown_products: 0

CAUSA ROOT: Los turns se crean con recommendations_provided=[] y nunca se actualizan.

SOLUCIÓN: Implementar update_conversation_turn_with_recommendations() que actualice 
los turns existentes con los recommendation IDs después de que se generen.
"""

import sys
sys.path.append('src')

from src.api.mcp.conversation_state_manager import get_conversation_state_manager
import asyncio
import time
import logging

async def update_existing_turn_with_recommendations(session_id, turn_number, recommendation_ids):
    """
    Actualiza un turn existente con recommendation IDs
    
    Args:
        session_id: ID de la sesión
        turn_number: Número del turn a actualizar  
        recommendation_ids: Lista de IDs de productos recomendados
    """
    try:
        # Obtener state manager
        state_manager = await get_conversation_state_manager()
        
        # Cargar contexto existente
        mcp_context = await state_manager.load_conversation_context(session_id)
        
        if not mcp_context:
            print(f"❌ No context found for session {session_id}")
            return False
        
        print(f"📋 Context loaded: {len(mcp_context.turns)} turns")
        
        # Buscar el turn específico por número
        target_turn = None
        for turn in mcp_context.turns:
            if hasattr(turn, 'turn_number') and turn.turn_number == turn_number:
                target_turn = turn
                break
        
        if not target_turn:
            print(f"❌ Turn {turn_number} not found in context")
            return False
        
        # Actualizar recommendations_provided
        print(f"🔄 Updating turn {turn_number}:")
        print(f"   Before: {target_turn.recommendations_provided}")
        
        target_turn.recommendations_provided = recommendation_ids
        
        print(f"   After: {target_turn.recommendations_provided}")
        
        # Actualizar timestamp
        mcp_context.last_updated = time.time()
        
        # Guardar contexto actualizado
        success = await state_manager.save_conversation_context(mcp_context)
        
        if success:
            print(f"✅ Turn {turn_number} updated successfully with {len(recommendation_ids)} recommendation IDs")
            return True
        else:
            print(f"❌ Failed to save updated context")
            return False
            
    except Exception as e:
        print(f"❌ Error updating turn: {e}")
        return False

async def test_fix_implementation():
    """Test the fix implementation"""
    
    print("🧪 TESTING TURN UPDATE FIX")
    print("=" * 50)
    
    # Test data
    session_id = "debug_session_1758280706"  # From actual logs
    test_recommendations = ["9978754105653", "9978823573813", "9978727989557", "9978631127349", "9978486194485"]
    
    # Update Turn 1
    print("\\n1️⃣ UPDATING TURN 1:")
    success1 = await update_existing_turn_with_recommendations(session_id, 1, test_recommendations[:3])
    
    # Update Turn 2  
    print("\\n2️⃣ UPDATING TURN 2:")
    success2 = await update_existing_turn_with_recommendations(session_id, 2, test_recommendations[3:])
    
    if success1 and success2:
        print("\\n✅ BOTH TURNS UPDATED SUCCESSFULLY")
        print("\\n🧪 Now run the diversification test again:")
        print("python test_debug_simple.py")
        print("\\nExpected results:")
        print("- Turn 1: recommendations_provided with 3 IDs")
        print("- Turn 2: recommendations_provided with 2 IDs") 
        print("- Diversification needed: True")
        print("- shown_products count: 3")
        
    else:
        print("\\n❌ FAILED TO UPDATE TURNS")

if __name__ == "__main__":
    asyncio.run(test_fix_implementation())
