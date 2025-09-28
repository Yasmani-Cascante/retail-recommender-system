#!/usr/bin/env python3
"""
CORRECCIÓN 1: Router Patch Fix
==============================

Corrige el error de regex en router_async_patch.py
"""

import re

def patch_mcp_router_fixed():
    """Versión corregida del patch para mcp_router.py"""
    
    router_file = "src/api/routers/mcp_router.py"
    
    try:
        # Leer archivo actual
        with open(router_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"📝 Leyendo {router_file}...")
        
        # 1. Actualizar imports - CORRECCIÓN: Verificar antes de reemplazar
        if "from src.api.utils.market_utils import" in content:
            content = content.replace(
                "from src.api.utils.market_utils import",
                "from src.api.utils.market_utils import"  # Mantener igual por ahora
            )
            print("✅ Imports verificados")
        
        # 2. CORRECCIÓN: Regex simplificado para adapt_product_for_market
        # Buscar líneas que contienen adapt_product_for_market( sin await
        lines = content.split('\n')
        updated_lines = []
        
        for line in lines:
            if 'adapt_product_for_market(' in line and 'await' not in line and 'def ' not in line:
                # Añadir await antes de la función
                updated_line = line.replace('adapt_product_for_market(', 'await adapt_product_for_market_async(')
                print(f"🔧 Updated: {line.strip()} -> {updated_line.strip()}")
                updated_lines.append(updated_line)
            elif 'convert_price_to_market_currency(' in line and 'await' not in line and 'def ' not in line:
                # Añadir await antes de la función
                updated_line = line.replace('convert_price_to_market_currency(', 'await convert_price_to_market_currency_async(')
                print(f"🔧 Updated: {line.strip()} -> {updated_line.strip()}")
                updated_lines.append(updated_line)
            else:
                updated_lines.append(line)
        
        content = '\n'.join(updated_lines)
        
        # 3. CORRECCIÓN: Verificar que endpoints son async
        # Buscar definiciones de endpoints que no son async
        endpoint_pattern = r'@router\.(get|post|put|delete)\([^)]+\)\s*\ndef\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        matches = re.finditer(endpoint_pattern, content)
        
        for match in matches:
            method = match.group(1)
            func_name = match.group(2)
            print(f"📍 Found endpoint: {method.upper()} {func_name}")
            
            # Reemplazar def con async def
            old_pattern = f'@router.{method}([^)]+)\ndef {func_name}'
            new_pattern = f'@router.{method}(\\1)\nasync def {func_name}'
            content = re.sub(old_pattern, new_pattern, content)
        
        # 4. CORRECCIÓN: Añadir imports async si no existen
        if "adapt_product_for_market_async" not in content:
            # Buscar línea de imports existente
            import_lines = []
            for line in content.split('\n'):
                if 'from src.api.utils.market_utils import' in line:
                    import_lines.append(line)
            
            if import_lines:
                # Reemplazar import existente
                old_import = import_lines[0]
                new_import = """# ✅ ASYNC-FIRST IMPORTS FIXED
from src.api.utils.market_utils import (
    adapt_product_for_market_async,
    convert_price_to_market_currency_async,
    adapt_product_for_market,  # Sync wrapper for compatibility
    convert_price_to_market_currency  # Sync wrapper for compatibility
)"""
                content = content.replace(old_import, new_import)
                print("✅ Imports async añadidos")
        
        # Escribir archivo actualizado
        with open(router_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ MCP Router patch aplicado correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en router patch: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = patch_mcp_router_fixed()
    if success:
        print("🎉 Router patch fix completed successfully")
    else:
        print("❌ Router patch fix failed")