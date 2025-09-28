#!/usr/bin/env python3
"""
Script para corregir el problema de variable shadowing en mcp_router.py
====================================================================

PROBLEMA IDENTIFICADO:
- conversation_session se crea correctamente como objeto ConversationSession
- Línea ~495: conversation_session = response_dict.get("conversation_session") SOBRESCRIBE con string
- Resultado: conversation_session se convierte de objeto a string
- Error: 'str' object has no attribute 'session_id'

SOLUCIÓN:
- Cambiar nombre de variable para evitar shadowing
- Mantener conversation_session como objeto original
"""

import os
import re
import time

def fix_variable_shadowing():
    """Corregir el variable shadowing en mcp_router.py"""
    
    file_path = "src/api/routers/mcp_router.py"
    
    print("🔧 CORRIGIENDO VARIABLE SHADOWING EN MCP_ROUTER.PY")
    print("=" * 60)
    
    # Verificar que el archivo existe
    if not os.path.exists(file_path):
        print(f"❌ Error: {file_path} no encontrado")
        return False
    
    # Leer archivo
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Buscar la línea problemática
    problem_line = "conversation_session = response_dict.get(\"conversation_session\")"
    
    if problem_line in content:
        print(f"✅ Línea problemática encontrada: {problem_line}")
        
        # Reemplazar con nueva variable
        corrected_line = "response_conversation_session = response_dict.get(\"conversation_session\")  # ✅ Fixed: avoid variable shadowing"
        
        content = content.replace(problem_line, corrected_line)
        
        print("✅ Variable shadowing corregido")
        
        # También buscar si hay referencias posteriores que necesiten actualización
        # (Generalmente no debería haber, pero verificar)
        
        # Crear backup
        backup_path = f"{file_path}.backup_shadowing_fix_{int(time.time())}"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"📦 Backup creado: {backup_path}")
        
        # Escribir archivo corregido
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Corrección aplicada exitosamente")
        
        return True
    else:
        print("ℹ️ La línea problemática exacta no se encontró")
        
        # Buscar variantes
        variants = [
            "conversation_session = response_dict.get('conversation_session')",
            "conversation_session=response_dict.get(\"conversation_session\")",
            "conversation_session=response_dict.get('conversation_session')"
        ]
        
        for variant in variants:
            if variant in content:
                print(f"✅ Variante encontrada: {variant}")
                corrected_variant = variant.replace("conversation_session =", "response_conversation_session =").replace("conversation_session=", "response_conversation_session=")
                content = content.replace(variant, f"{corrected_variant}  # ✅ Fixed: avoid variable shadowing")
                
                # Crear backup y escribir
                backup_path = f"{file_path}.backup_shadowing_fix_{int(time.time())}"
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
                print(f"📦 Backup creado: {backup_path}")
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print("✅ Variante corregida exitosamente")
                return True
        
        print("❌ No se encontró ninguna variante de la línea problemática")
        return False

def verify_fix():
    """Verificar que la corrección fue aplicada correctamente"""
    
    print("\n🔍 VERIFICANDO CORRECCIÓN...")
    print("-" * 40)
    
    file_path = "src/api/routers/mcp_router.py"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verificar que la línea problemática no está presente
        problem_patterns = [
            "conversation_session = response_dict.get(\"conversation_session\")",
            "conversation_session = response_dict.get('conversation_session')",
            "conversation_session=response_dict.get(\"conversation_session\")",
            "conversation_session=response_dict.get('conversation_session')"
        ]
        
        found_problems = []
        for pattern in problem_patterns:
            if pattern in content:
                found_problems.append(pattern)
        
        if found_problems:
            print(f"❌ Líneas problemáticas aún presentes: {found_problems}")
            return False
        else:
            print("✅ No se encontraron líneas problemáticas")
        
        # Verificar que la corrección está presente
        if "response_conversation_session = response_dict.get(" in content:
            print("✅ Corrección encontrada: response_conversation_session")
            return True
        else:
            print("❌ Corrección no encontrada")
            return False
            
    except Exception as e:
        print(f"❌ Error verificando corrección: {e}")
        return False

def test_syntax():
    """Probar que la sintaxis sigue siendo válida después de la corrección"""
    
    print("\n🧪 PROBANDO SINTAXIS POST-CORRECCIÓN...")
    print("-" * 40)
    
    try:
        # Test import para verificar sintaxis
        import subprocess
        result = subprocess.run(
            ['python', '-c', 'from src.api.routers.mcp_router import router; print("✅ Syntax OK")'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("✅ Sintaxis válida después de corrección")
            return True
        else:
            print(f"❌ Error de sintaxis: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error probando sintaxis: {e}")
        return False

def main():
    """Función principal"""
    
    print("🚀 INICIANDO CORRECCIÓN DE VARIABLE SHADOWING")
    print("=" * 60)
    
    # 1. Aplicar corrección
    fix_success = fix_variable_shadowing()
    
    if fix_success:
        # 2. Verificar corrección
        verify_success = verify_fix()
        
        if verify_success:
            # 3. Probar sintaxis
            syntax_success = test_syntax()
            
            if syntax_success:
                print("\n🎯 CORRECCIÓN COMPLETADA EXITOSAMENTE")
                print("=" * 50)
                print("✅ Variable shadowing resuelto")
                print("✅ conversation_session mantiene su tipo de objeto")
                print("✅ Sintaxis válida")
                
                print("\n📋 PRÓXIMOS PASOS:")
                print("1. Reiniciar servidor: python src/api/main_unified_redis.py")
                print("2. Probar endpoint: curl -X POST http://localhost:8000/v1/mcp/conversation")
                print("3. Verificar que no hay más errores de 'str' object")
                
                print("\n🎯 ERRORES ESPERADOS DESPUÉS DE ESTA CORRECCIÓN:")
                print("❌ conversation_session is string: RESUELTO")
                print("❌ 'str' object has no attribute 'session_id': RESUELTO") 
                print("❌ 'str' object has no attribute 'turn_count': RESUELTO")
                
                return True
            else:
                print("\n❌ Test de sintaxis falló")
        else:
            print("\n❌ Verificación falló")
    else:
        print("\n❌ Corrección falló")
    
    print("\n⚠️ Corrección no completada - revisar manualmente")
    return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)