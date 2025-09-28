#!/usr/bin/env python3
"""
FIX VALIDATION SCRIPT - FIELD MAPPING CORRECTION
===============================================

Corrige validate_phase2_complete.py para que busque los campos correctos
que SÍ existen en la respuesta del endpoint optimizado.
"""

import os
import shutil
from datetime import datetime

def fix_validation_script_field_mapping():
    """
    Corrige el script de validación para usar los campos correctos.
    """
    
    print("🔧 FIXING VALIDATION SCRIPT - FIELD MAPPING CORRECTION")
    print("=" * 60)
    
    script_path = "tests/phase2_consolidation/validate_phase2_complete.py"
    
    if not os.path.exists(script_path):
        print(f"❌ Script not found: {script_path}")
        return False
    
    # Crear backup
    backup_path = f"{script_path}.backup_before_field_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(script_path, backup_path)
    print(f"💾 Backup created: {backup_path}")
    
    # Leer archivo actual
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # CORRECCIONES ESPECÍFICAS BASADAS EN EL DIAGNÓSTICO
    corrections = [
        {
            'old': "response_data.get('conversation_state', {})",
            'new': "response_data.get('session_tracking', {})",
            'description': 'Use session_tracking instead of conversation_state'
        },
        {
            'old': "state.get('turn', 0)",
            'new': "state.get('turn_number', 0)",
            'description': 'Use turn_number field name'
        },
        {
            'old': "state.get('session_tracked', False)",
            'new': "state.get('session_tracked', False)",
            'description': 'session_tracked field name is correct'
        },
        {
            'old': "response_data.get('intent_tracking', {})",
            'new': "response_data.get('intent_evolution', {})",
            'description': 'Use intent_evolution instead of intent_tracking'
        },
        {
            'old': "intent_data.get('count', 0)",
            'new': "intent_data.get('intents_tracked', 0)",
            'description': 'Use intents_tracked field name'
        },
        {
            'old': "intent_data.get('progression', [])",
            'new': "intent_data.get('intent_progression', [])",
            'description': 'Use intent_progression field name'
        },
        {
            'old': "intent_data.get('unique', 0)",
            'new': "intent_data.get('unique_intents', 0)",
            'description': 'Use unique_intents field name'
        }
    ]
    
    # Aplicar correcciones
    modified = False
    for correction in corrections:
        if correction['old'] in content:
            content = content.replace(correction['old'], correction['new'])
            print(f"   ✅ {correction['description']}")
            modified = True
        else:
            print(f"   ⚠️ Pattern not found: {correction['old']}")
    
    # CORRECCIÓN ADICIONAL: Asegurar que usa endpoint optimizado
    if '"/v1/mcp/conversation"' in content and '"/v1/mcp/conversation/optimized"' not in content:
        content = content.replace('"/v1/mcp/conversation"', '"/v1/mcp/conversation/optimized"')
        print("   ✅ Ensured using optimized endpoint")
        modified = True
    
    # CORRECCIÓN ADICIONAL: enable_optimization flag
    if '"enable_optimization": false' in content:
        content = content.replace('"enable_optimization": false', '"enable_optimization": true')
        print("   ✅ Enabled optimization flag")
        modified = True
    elif '"enable_optimization"' not in content:
        # Agregar enable_optimization si no existe
        import re
        # Buscar pattern de payload JSON
        payload_pattern = r'({[^}]*"query"[^}]*})'
        
        def add_optimization_flag(match):
            payload = match.group(1)
            # Quitar la llave de cierre y agregar el flag
            payload = payload.rstrip('}').rstrip()
            if not payload.endswith(','):
                payload += ','
            payload += '\\n            "enable_optimization": true\\n        }'
            return payload
        
        new_content = re.sub(payload_pattern, add_optimization_flag, content)
        if new_content != content:
            content = new_content
            print("   ✅ Added enable_optimization flag")
            modified = True
    
    if modified:
        # Escribir archivo corregido
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\\n✅ VALIDATION SCRIPT FIXED SUCCESSFULLY")
        print(f"📁 Script: {script_path}")
        print(f"💾 Backup: {backup_path}")
        return True
    else:
        print("\\n⚠️ No modifications were needed or patterns not found")
        return False

def create_field_mapping_patch():
    """
    Crear un patch adicional que específicamente mapee los campos correctos.
    """
    
    patch_content = '''#!/usr/bin/env python3
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
'''
    
    with open('field_mapping_patch.py', 'w', encoding='utf-8') as f:
        f.write(patch_content)
    
    print("✅ Created field mapping patch: field_mapping_patch.py")

def main():
    """Función principal para aplicar el fix"""
    
    print("🎯 PROBLEMA IDENTIFICADO:")
    print("• Endpoint optimizado funciona correctamente")
    print("• Validation script busca campos incorrectos")
    print("• Need to fix field mapping in validation script")
    print()
    
    # Aplicar fix principal
    if fix_validation_script_field_mapping():
        
        # Crear patch adicional
        create_field_mapping_patch()
        
        print("\\n" + "=" * 60)
        print("✅ FIX COMPLETED SUCCESSFULLY")
        print("=" * 60)
        
        print("🎯 CORRECCIONES APLICADAS:")
        print("• conversation_state → session_tracking")
        print("• turn → turn_number") 
        print("• intent_tracking → intent_evolution")
        print("• count → intents_tracked")
        print("• progression → intent_progression")
        print("• Endpoint: /conversation/optimized ✅")
        print("• enable_optimization: true ✅")
        
        print("\\n📋 VALIDATION INMEDIATA:")
        print("python tests/phase2_consolidation/validate_phase2_complete.py")
        print()
        print("📊 RESULTADOS ESPERADOS:")
        print("✅ Session tracked: True, Turn: >1")
        print("✅ Intents tracked: >0, Progression: [varied]")
        print("✅ Response Times: ~150ms avg")
        
        return True
    else:
        print("\\n❌ Fix failed - manual intervention needed")
        return False

if __name__ == "__main__":
    import time
    success = main()
    exit(0 if success else 1)
