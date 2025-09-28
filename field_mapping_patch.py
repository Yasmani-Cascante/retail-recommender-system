#!/usr/bin/env python3
"""
FIELD MAPPING PATCH for validate_phase2_complete.py
=================================================

Patch que corrige la extracción de campos para que coincida
con la estructura real del endpoint optimizado.
"""

def extract_conversation_state_data(response_data):
    """
    Extrae datos de estado de conversación usando la estructura correcta.
    """
    
    # CAMPOS CORRECTOS según el diagnóstico
    session_data = response_data.get('session_tracking', {})
    intent_data = response_data.get('intent_evolution', {})
    persistence_data = response_data.get('state_persistence', {})
    
    return {
        'session_tracked': session_data.get('session_tracked', False),
        'turn_number': session_data.get('turn_number', 0),
        'session_id_match': session_data.get('session_id_match', False),
        'session_active': session_data.get('session_active', False),
        'intents_tracked': intent_data.get('intents_tracked', 0),
        'unique_intents': intent_data.get('unique_intents', 0),
        'intent_progression': intent_data.get('intent_progression', []),
        'current_intent': intent_data.get('current_intent', ''),
        'state_persisted': persistence_data.get('state_persisted', False),
        'persistence_timestamp': persistence_data.get('persistence_timestamp', '')
    }

def extract_performance_metrics(response_data):
    """
    Extrae métricas de performance de la respuesta.
    """
    
    performance_data = response_data.get('performance_metrics', {})
    
    return {
        'processing_time_ms': performance_data.get('processing_time_ms', 0),
        'optimization_applied': performance_data.get('optimization_level') == 'moderate',
        'functionality_preserved': performance_data.get('functionality_preserved', False),
        'target_achieved': performance_data.get('target_achievement', False)
    }

def create_test_payload_optimized():
    """
    Crear payload de test que funcione con el endpoint optimizado.
    """
    
    return {
        "query": "I need running shoes for marathon training",
        "user_id": "validation_test_user",
        "session_id": f"validation_session_{int(time.time())}",
        "market_id": "US",
        "n_recommendations": 5,
        "enable_optimization": True  # CRÍTICO: Flag de optimización
    }

# Usage example:
# response_data = make_request_to_optimized_endpoint(payload)
# state_data = extract_conversation_state_data(response_data)
# performance_data = extract_performance_metrics(response_data)
