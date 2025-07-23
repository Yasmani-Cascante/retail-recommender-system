"""
Script para verificar la sintaxis del router MCP
"""

import ast
import sys

def check_syntax(filename):
    """Verifica la sintaxis de un archivo Python"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Intentar parsear el archivo
        ast.parse(content)
        print(f"✅ Sintaxis correcta en {filename}")
        return True
        
    except SyntaxError as e:
        print(f"❌ Error de sintaxis en {filename}")
        print(f"   Línea {e.lineno}: {e.msg}")
        print(f"   Texto: {e.text}")
        return False
    except Exception as e:
        print(f"❌ Error al verificar {filename}: {e}")
        return False

if __name__ == "__main__":
    filename = "src/api/routers/mcp_router.py"
    if check_syntax(filename):
        print("\n✅ El archivo está listo para ser ejecutado")
    else:
        print("\n❌ El archivo tiene errores que deben ser corregidos")
