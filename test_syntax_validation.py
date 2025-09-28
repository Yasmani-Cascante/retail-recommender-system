#!/usr/bin/env python3
"""
Test de sintaxis para validate_phase2_complete.py
"""

import sys

def test_syntax():
    """Test de sintaxis del archivo corregido"""
    
    script_path = "tests/phase2_consolidation/validate_phase2_complete.py"
    
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Test de compilación
        compile(content, script_path, 'exec')
        
        print("✅ SINTAXIS CORRECTA")
        print(f"📁 Archivo: {script_path}")
        print("🎉 Todas las correcciones aplicadas exitosamente")
        print()
        print("📋 PRÓXIMO PASO:")
        print("python tests/phase2_consolidation/validate_phase2_complete.py")
        
        return True
        
    except SyntaxError as e:
        print(f"❌ ERROR DE SINTAXIS en línea {e.lineno}:")
        print(f"   {e.msg}")
        print(f"   Texto: {e.text}")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_syntax()
    sys.exit(0 if success else 1)
