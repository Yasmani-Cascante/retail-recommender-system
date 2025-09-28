#!/usr/bin/env python3
"""
CORRECCIÓN DE ERRORES DE SINTAXIS - validate_phase2_complete.py
============================================================

Corrige los errores específicos de llaves sin cerrar y diccionarios mal formados.
"""

import os
import shutil
import re
from datetime import datetime

def fix_syntax_errors_validate_script():
    """Corrige errores de sintaxis específicos en validate_phase2_complete.py"""
    
    print("🔧 CORRIGIENDO ERRORES DE SINTAXIS EN validate_phase2_complete.py")
    print("=" * 65)
    
    script_path = "tests/phase2_consolidation/validate_phase2_complete.py"
    
    if not os.path.exists(script_path):
        print(f"❌ Script not found: {script_path}")
        return False
    
    # Crear backup
    backup_path = f"{script_path}.backup_syntax_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(script_path, backup_path)
    print(f"💾 Backup created: {backup_path}")
    
    # Leer archivo
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    print("🔍 Analizando errores específicos...")
    
    # Líneas problemáticas según los errores
    error_lines = [262, 266, 293, 295, 329, 333, 365, 369, 439, 442, 454, 457, 495, 498, 538, 541, 598, 599]
    
    fixes_applied = []
    
    for line_num in error_lines:
        if line_num <= len(lines):
            original_line = lines[line_num - 1]  # -1 porque lines es 0-indexed
            
            print(f"\\n🔍 Línea {line_num}: {original_line.strip()}")
            
            # Detectar patrones problemáticos y corregir
            fixed_line = fix_line_syntax(original_line, line_num)
            
            if fixed_line != original_line:
                lines[line_num - 1] = fixed_line
                fixes_applied.append(f"Línea {line_num}: Corregida")
                print(f"   ✅ Corregida: {fixed_line.strip()}")
            else:
                print(f"   ⚠️ No se detectó patrón de error conocido")
    
    # Aplicar correcciones adicionales globales
    content_fixed = '\\n'.join(lines)
    content_fixed = apply_global_syntax_fixes(content_fixed)
    
    # Escribir archivo corregido
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content_fixed)
    
    print(f"\\n✅ CORRECCIONES APLICADAS: {len(fixes_applied)}")
    for fix in fixes_applied:
        print(f"   • {fix}")
    
    # Verificar sintaxis
    print("\\n🔍 Verificando sintaxis corregida...")
    try:
        compile(content_fixed, script_path, 'exec')
        print("   ✅ Sintaxis correcta después de las correcciones")
        return True
    except SyntaxError as e:
        print(f"   ❌ Aún hay errores de sintaxis: {e}")
        print(f"   📍 Línea {e.lineno}: {e.text}")
        return False

def fix_line_syntax(line, line_num):
    """Corrige errores de sintaxis en una línea específica"""
    
    # Patrón 1: Diccionarios con llaves sin cerrar
    # Ejemplo: payload = {
    if re.search(r'\\s*=\\s*{\\s*$', line):
        # Si la línea termina con = {, agregar }
        return line + " }"
    
    # Patrón 2: Líneas con {" sin cerrar
    if '{"' in line and line.count('{') > line.count('}'):
        # Contar llaves faltantes
        missing_braces = line.count('{') - line.count('}')
        return line + ' }' * missing_braces
    
    # Patrón 3: Líneas con comas sueltas al final
    if line.strip().endswith(',') and '{' not in line and '}' not in line:
        # Puede ser parte de un diccionario, mantener como está
        return line
    
    # Patrón 4: Enable optimization flag mal formado
    if 'enable_optimization' in line and not line.strip().endswith('}'):
        if not line.strip().endswith(','):
            return line.rstrip() + ','
    
    # Patrón 5: JSON payload incompleto
    if '"query"' in line and line.count('{') > line.count('}'):
        # Completar estructura JSON básica
        missing_braces = line.count('{') - line.count('}')
        return line + ' }' * missing_braces
    
    return line

def apply_global_syntax_fixes(content):
    """Aplica correcciones globales de sintaxis"""
    
    # Fix 1: Asegurar que payloads JSON estén bien formados
    patterns_to_fix = [
        # Patrón: payload = { "query": "...", sin cerrar
        (r'(payload\\s*=\\s*{[^}]*"[^"]*"[^}]*),\\s*$', r'\\1 }'),
        
        # Patrón: { "key": "value", enable_optimization sin cerrar
        (r'({[^}]*"enable_optimization":\\s*true)\\s*$', r'\\1 }'),
        
        # Patrón: Líneas que terminan con { sin }
        (r'(\\w+\\s*=\\s*{)\\s*$', r'\\1 }'),
    ]
    
    for pattern, replacement in patterns_to_fix:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    # Fix 2: Asegurar enable_optimization en payloads
    content = ensure_enable_optimization_flag(content)
    
    # Fix 3: Corregir field mapping si no está ya corregido
    content = apply_field_mapping_corrections(content)
    
    return content

def ensure_enable_optimization_flag(content):
    """Asegura que enable_optimization esté en todos los payloads"""
    
    # Buscar payloads que no tengan enable_optimization
    payload_pattern = r'(payload\\s*=\\s*{[^}]*"query"[^}]*)(})'
    
    def add_optimization_flag(match):
        payload_content = match.group(1)
        closing_brace = match.group(2)
        
        if 'enable_optimization' not in payload_content:
            # Agregar enable_optimization antes de cerrar
            if not payload_content.rstrip().endswith(','):
                payload_content += ','
            payload_content += '\\n            "enable_optimization": true'
        
        return payload_content + closing_brace
    
    return re.sub(payload_pattern, add_optimization_flag, content, flags=re.DOTALL)

def apply_field_mapping_corrections(content):
    """Aplica correcciones de field mapping"""
    
    corrections = [
        # Cambios de field mapping
        ("response_data.get('conversation_state'", "response_data.get('session_tracking'"),
        ("state.get('turn'", "state.get('turn_number'"),
        ("response_data.get('intent_tracking'", "response_data.get('intent_evolution'"),
        ("intent_data.get('count'", "intent_data.get('intents_tracked'"),
        ("intent_data.get('progression'", "intent_data.get('intent_progression'"),
        ("intent_data.get('unique'", "intent_data.get('unique_intents'"),
        
        # Asegurar endpoint optimizado
        ('"/v1/mcp/conversation"', '"/v1/mcp/conversation/optimized"'),
        ('"enable_optimization": false', '"enable_optimization": true'),
    ]
    
    for old, new in corrections:
        content = content.replace(old, new)
    
    return content

def create_fixed_test_payload_function(content):
    """Crea una función de test payload corregida"""
    
    fixed_payload_function = '''
def create_test_payload():
    """Crea payload de test corregido para endpoint optimizado"""
    return {
        "query": "I need running shoes for marathon training",
        "user_id": "test_user_validation",
        "session_id": f"validation_session_{int(time.time())}",
        "market_id": "US",
        "n_recommendations": 5,
        "enable_optimization": True
    }
'''
    
    # Si no existe la función, agregarla
    if 'def create_test_payload' not in content:
        # Agregar después de los imports
        import_end = content.find('\\nclass') if '\\nclass' in content else content.find('\\ndef')
        if import_end != -1:
            content = content[:import_end] + fixed_payload_function + content[import_end:]
    
    return content

def main():
    """Función principal"""
    
    print("🚨 CORRECCIÓN DE ERRORES DE SINTAXIS")
    print("Errores detectados: llaves sin cerrar, diccionarios mal formados")
    print()
    
    if fix_syntax_errors_validate_script():
        print("\\n" + "=" * 65)
        print("✅ ERRORES DE SINTAXIS CORREGIDOS EXITOSAMENTE")
        print("=" * 65)
        
        print("🔧 CORRECCIONES APLICADAS:")
        print("• Llaves { sin cerrar → Corregidas")
        print("• Diccionarios mal formados → Corregidos")
        print("• Field mapping → Actualizado")
        print("• enable_optimization flag → Agregado")
        print("• Endpoint optimizado → Configurado")
        
        print("\\n📋 VALIDACIÓN INMEDIATA:")
        print("python tests/phase2_consolidation/validate_phase2_complete.py")
        print()
        print("📊 RESULTADOS ESPERADOS:")
        print("✅ Sin errores de sintaxis")
        print("✅ Session tracked: True, Turn: >1")
        print("✅ Intents tracked: >0, Progression: [varied]")
        
        return True
    else:
        print("\\n❌ No se pudieron corregir todos los errores")
        print("Se recomienda revisión manual del archivo")
        return False

if __name__ == "__main__":
    import time
    success = main()
    exit(0 if success else 1)
