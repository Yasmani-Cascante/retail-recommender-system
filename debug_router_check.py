"""
Script para verificar que la implementación en el router está correcta
"""

import os
import re

def check_router_implementation():
    """Verifica la implementación en el router MCP"""
    
    router_path = "src/api/routers/mcp_router.py"
    
    print("🔍 Verificando implementación del router...")
    print("="*60)
    
    if not os.path.exists(router_path):
        print(f"❌ No se encuentra el archivo: {router_path}")
        return
    
    with open(router_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verificaciones
    checks = {
        "Import de market_adapter": "from src.api.mcp.utils.market_utils import market_adapter" in content,
        "Adaptación en safe_transform": "market_adapter.adapt_product_for_market" in content,
        "Contexto de mercado": "market_id" in content and "market_context" in content,
    }
    
    print("Verificaciones:")
    all_good = True
    for check, result in checks.items():
        status = "✅" if result else "❌"
        print(f"{status} {check}")
        if not result:
            all_good = False
    
    # Buscar la función donde se aplica la adaptación
    print("\n📍 Buscando punto de adaptación...")
    
    # Buscar safe_transform_recommendation
    safe_transform_match = re.search(r'def safe_transform_recommendation.*?(?=\n(?:def|class|\Z))', content, re.DOTALL)
    if safe_transform_match:
        func_content = safe_transform_match.group(0)
        if "market_adapter" in func_content:
            print("✅ Adaptación encontrada en safe_transform_recommendation")
            
            # Mostrar las líneas relevantes
            lines = func_content.split('\n')
            for i, line in enumerate(lines):
                if "market_adapter" in line:
                    print(f"\n📌 Línea {i}: {line.strip()}")
                    # Mostrar contexto (3 líneas antes y después)
                    start = max(0, i-3)
                    end = min(len(lines), i+4)
                    print("\nContexto:")
                    for j in range(start, end):
                        prefix = ">>> " if j == i else "    "
                        print(f"{prefix}{lines[j]}")
        else:
            print("⚠️ safe_transform_recommendation existe pero no tiene adaptación")
    
    # Buscar en handle_mcp_conversation
    mcp_conv_match = re.search(r'async def handle_mcp_conversation.*?(?=\n(?:async def|def|class|\Z))', content, re.DOTALL)
    if mcp_conv_match:
        func_content = mcp_conv_match.group(0)
        if "market_adapter" in func_content:
            print("\n✅ Adaptación encontrada en handle_mcp_conversation")
    
    # Verificar que market_utils.py existe
    print("\n📁 Verificando archivos de utilidades...")
    utils_path = "src/api/mcp/utils/market_utils.py"
    if os.path.exists(utils_path):
        print(f"✅ {utils_path} existe")
        
        # Verificar contenido básico
        with open(utils_path, "r", encoding="utf-8") as f:
            utils_content = f.read()
            
        checks_utils = {
            "Clase MarketAdapter": "class MarketAdapter" in utils_content,
            "Método adapt_product_for_market": "def adapt_product_for_market" in utils_content,
            "Tasas de cambio": "EXCHANGE_RATES" in utils_content,
            "Traducciones básicas": "BASIC_TRANSLATIONS" in utils_content,
        }
        
        print("\nVerificaciones de market_utils.py:")
        for check, result in checks_utils.items():
            status = "✅" if result else "❌"
            print(f"{status} {check}")
    else:
        print(f"❌ {utils_path} NO existe")
    
    # Sugerencias finales
    print("\n" + "="*60)
    if all_good:
        print("✅ La implementación parece estar correcta")
        print("\n🔍 Si aún hay problemas, verifica:")
        print("1. Que el servidor se haya reiniciado después de los cambios")
        print("2. Que no haya errores de importación en los logs")
        print("3. Que el contexto de mercado se esté pasando correctamente")
    else:
        print("⚠️ Hay problemas con la implementación")
        print("\n🔧 Acciones recomendadas:")
        print("1. Revisar que los cambios se guardaron correctamente")
        print("2. Verificar que no hay errores de sintaxis")
        print("3. Reiniciar el servidor")

def check_api_structure():
    """Verifica la estructura esperada del API"""
    print("\n\n🔍 Verificando estructura del API...")
    print("="*60)
    
    # Buscar el modelo Pydantic para el request
    router_path = "src/api/routers/mcp_router.py"
    
    if os.path.exists(router_path):
        with open(router_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Buscar definiciones de modelos
        model_matches = re.findall(r'class (\w+Request)\(.*?\):', content)
        if model_matches:
            print("📋 Modelos de request encontrados:")
            for model in model_matches:
                print(f"  - {model}")
        
        # Buscar el endpoint específico
        endpoint_match = re.search(r'@router\.post\(["\']([^"\']+)["\'].*?async def (\w+)', content, re.DOTALL)
        if endpoint_match:
            endpoint_path = endpoint_match.group(1)
            function_name = endpoint_match.group(2)
            print(f"\n📍 Endpoint principal:")
            print(f"  Path: {endpoint_path}")
            print(f"  Función: {function_name}")
        
        # Buscar campos esperados
        print("\n📝 Campos esperados en el request:")
        field_patterns = [
            r'query["\']?\s*:\s*str',
            r'market_id["\']?\s*:\s*(?:str|Optional)',
            r'session_id["\']?\s*:\s*(?:str|Optional)',
            r'user_id["\']?\s*:\s*(?:str|Optional)',
        ]
        
        for pattern in field_patterns:
            if re.search(pattern, content):
                field_name = pattern.split('[')[0]
                print(f"  ✅ {field_name}")
            else:
                print(f"  ❓ {pattern.split('[')[0]} (no encontrado)")

if __name__ == "__main__":
    check_router_implementation()
    check_api_structure()
    
    print("\n\n💡 Si necesitas revisar manualmente:")
    print("1. Abre src/api/routers/mcp_router.py")
    print("2. Busca 'def safe_transform_recommendation'")
    print("3. Verifica que tiene el código de adaptación")
    print("4. Busca el modelo del request para ver campos exactos")