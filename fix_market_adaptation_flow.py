# fix_market_adaptation_flow.py
"""
Script para corregir el flujo de adaptación de mercado
El problema es que necesitamos interceptar ANTES de que se marque como USD
"""

import os
import re
from datetime import datetime

def fix_mcp_router_adaptation():
    """Corrige la implementación en el router MCP"""
    
    router_path = "src/api/routers/mcp_router.py"
    
    print("🔧 Corrigiendo implementación de adaptación de mercado...")
    print("="*60)
    
    # Crear backup
    backup_path = f"{router_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    with open(router_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Guardar backup
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Backup creado: {backup_path}")
    
    # Buscar donde se procesan las recomendaciones en handle_mcp_conversation
    # Necesitamos encontrar DONDE se asigna currency = "USD" incorrectamente
    
    # Patrón 1: Buscar donde se establece currency
    currency_pattern = r'["\'](currency)["\']:\s*["\'](USD)["\']\s*(?![,}]?\s*#\s*CORREGIDO)'
    
    # Buscar todas las ocurrencias
    matches = list(re.finditer(currency_pattern, content))
    
    if matches:
        print(f"✅ Encontradas {len(matches)} asignaciones de currency USD")
        
        # Reemplazar cada ocurrencia con lógica condicional
        for match in reversed(matches):  # Reverso para no afectar índices
            start, end = match.span()
            
            # Obtener contexto alrededor
            context_start = max(0, start - 200)
            context_end = min(len(content), end + 200)
            context = content[context_start:context_end]
            
            # Si está en una transformación de recomendación
            if "recommendation" in context or "product" in context:
                # Reemplazar con lógica condicional
                replacement = '"currency": market_context.get("currency", "USD") if market_context else "USD"  # CORREGIDO'
                content = content[:start] + replacement + content[end:]
                print(f"✅ Corregida asignación de currency en posición {start}")
    
    # Buscar donde se llama a safe_transform_recommendation
    transform_calls = list(re.finditer(r'safe_transform_recommendation\s*\([^)]+\)', content))
    
    for call in transform_calls:
        call_text = call.group(0)
        
        # Si no pasa context, modificar para pasarlo
        if "context" not in call_text:
            # Buscar si hay market_context disponible en el scope
            scope_start = max(0, call.start() - 1000)
            scope = content[scope_start:call.start()]
            
            if "market_context" in scope:
                # Modificar la llamada para incluir market_context
                new_call = call_text.replace(")", ", context=market_context)")
                content = content[:call.start()] + new_call + content[call.end():]
                print(f"✅ Añadido context a llamada de safe_transform_recommendation")
    
    # Asegurar que safe_transform_recommendation use el context
    transform_func_match = re.search(
        r'(async\s+)?def\s+safe_transform_recommendation\s*\([^)]*\)\s*:.*?(?=\n(?:async\s+)?def|\Z)',
        content,
        re.DOTALL
    )
    
    if transform_func_match:
        func_content = transform_func_match.group(0)
        
        # Verificar si ya tiene la adaptación correcta
        if "market_adapter" not in func_content:
            print("⚠️ safe_transform_recommendation no tiene adaptación, añadiendo...")
            
            # Buscar el return
            return_match = re.search(r'return\s+recommendation', func_content)
            if return_match:
                # Insertar adaptación antes del return
                indent = "    "
                adaptation_code = f'''
    # Adaptar para el mercado si hay contexto disponible
    if context and isinstance(context, dict) and "market_id" in context:
        try:
            recommendation = market_adapter.adapt_product_for_market(
                recommendation, 
                context["market_id"]
            )
        except Exception as e:
            logger.warning(f"Error en adaptación de mercado: {{e}}")
    
    '''
                # Insertar antes del return
                insert_pos = func_content.rfind("return")
                new_func = func_content[:insert_pos] + adaptation_code + func_content[insert_pos:]
                
                # Reemplazar en el contenido
                content = content.replace(func_content, new_func)
                print("✅ Adaptación añadida a safe_transform_recommendation")
        else:
            # Verificar que use context correctamente
            if 'context.get("market_id")' not in func_content and 'context["market_id"]' not in func_content:
                print("⚠️ La adaptación existe pero no usa market_id del context")
                
                # Corregir para usar context
                content = content.replace(
                    'market_adapter.adapt_product_for_market(recommendation, "US")',
                    'market_adapter.adapt_product_for_market(recommendation, context.get("market_id", "US") if context else "US")'
                )
    
    # Guardar archivo corregido
    with open(router_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print("✅ Router MCP corregido")
    
    # Verificar market_utils.py
    verify_market_utils()

def verify_market_utils():
    """Verifica y corrige market_utils.py si es necesario"""
    
    utils_path = "src/api/mcp/utils/market_utils.py"
    
    if not os.path.exists(utils_path):
        print("❌ market_utils.py no existe")
        return
    
    with open(utils_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verificar que la conversión esté correcta
    if "original_currency" not in content:
        print("⚠️ market_utils.py no guarda currency original, corrigiendo...")
        
        # Buscar el método adapt_product_for_market
        method_match = re.search(
            r'def\s+adapt_product_for_market\s*\(.*?\)\s*:.*?(?=\n\s{0,4}def|\Z)',
            content,
            re.DOTALL
        )
        
        if method_match:
            method_content = method_match.group(0)
            
            # Asegurar que guarde currency original
            if 'adapted["original_currency"]' not in method_content:
                # Buscar donde se guarda original_price
                price_save = re.search(r'adapted\["original_price"\]\s*=', method_content)
                if price_save:
                    # Insertar después
                    insert_pos = method_content.find("\n", price_save.end())
                    new_line = '\n                adapted["original_currency"] = "COP"'
                    method_content = method_content[:insert_pos] + new_line + method_content[insert_pos:]
                    
                    # Reemplazar en el contenido
                    content = content.replace(method_match.group(0), method_content)
                    
                    with open(utils_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    print("✅ market_utils.py corregido")

def create_debug_endpoint():
    """Crea un endpoint de debug para verificar la adaptación"""
    
    debug_code = '''# debug_market_endpoint.py
"""
Endpoint de debug para verificar adaptación de mercado
Añadir temporalmente al router MCP
"""

@router.get("/v1/debug/market-test/{market_id}")
async def debug_market_adaptation(market_id: str):
    """Endpoint de debug para probar adaptación directamente"""
    
    # Producto de prueba
    test_product = {
        "id": "test123",
        "title": "Zapatos de Fiesta Elegantes",
        "description": "Zapatos elegantes para ocasiones especiales",
        "price": 59990.0,
        "currency": "COP",  # Originalmente en COP
        "score": 0.8
    }
    
    # Crear contexto de mercado
    market_context = {
        "market_id": market_id,
        "currency": {
            "US": "USD",
            "ES": "EUR",
            "MX": "MXN",
            "CO": "COP"
        }.get(market_id, "USD")
    }
    
    # Aplicar adaptación
    from src.api.mcp.utils.market_utils import market_adapter
    
    adapted_product = market_adapter.adapt_product_for_market(
        test_product.copy(),
        market_id
    )
    
    return {
        "market_id": market_id,
        "original_product": test_product,
        "adapted_product": adapted_product,
        "conversion_applied": adapted_product.get("price") != test_product["price"],
        "translation_applied": adapted_product.get("title") != test_product["title"]
    }
'''
    
    with open("debug_market_endpoint.py", "w", encoding="utf-8") as f:
        f.write(debug_code)
    
    print("\n📝 Endpoint de debug creado: debug_market_endpoint.py")
    print("Puedes añadirlo temporalmente al router para probar")

def main():
    print("""
    ╔════════════════════════════════════════════════════════╗
    ║        CORRECCIÓN DEFINITIVA - ADAPTACIÓN DE MERCADO    ║
    ╚════════════════════════════════════════════════════════╝
    """)
    
    # Aplicar correcciones
    fix_mcp_router_adaptation()
    create_debug_endpoint()
    
    print("\n" + "="*60)
    print("✅ CORRECCIONES APLICADAS")
    print("="*60)
    
    print("\n📋 Próximos pasos:")
    print("1. Reiniciar el servidor")
    print("2. Probar con: curl http://localhost:8000/v1/debug/market-test/US")
    print("3. Verificar que los precios se conviertan correctamente")
    
    print("\n💡 El problema era que 'currency' se establecía como 'USD'")
    print("   ANTES de aplicar la conversión de precios.")
    print("   Ahora debería funcionar correctamente.")

if __name__ == "__main__":
    main()