# patch_router_adaptation.py
"""
Parche para aplicar adaptación de mercado correctamente
"""

import os
import re

def patch_router():
    router_path = "src/api/routers/mcp_router.py"
    
    with open(router_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Buscar donde se crean las recomendaciones con market_adapted
    # Patrón para encontrar donde se añade el flag
    pattern = r'(\{[^}]*["']market_adapted["']\s*:\s*True[^}]*\})'
    
    matches = list(re.finditer(pattern, content, re.DOTALL))
    
    if not matches:
        print("No se encontró donde añadir la adaptación")
        return False
    
    # Trabajar de atrás hacia adelante para no afectar índices
    for match in reversed(matches):
        dict_content = match.group(0)
        
        # Si este diccionario parece ser una recomendación (tiene price, title, etc)
        if '"price"' in dict_content or "'price'" in dict_content:
            # Encontrar el inicio de este bloque
            block_start = match.start()
            
            # Buscar hacia atrás para encontrar la variable
            lines_before = content[:block_start].split('\n')
            
            # Buscar la línea donde se asigna este dict
            for i in range(len(lines_before)-1, max(0, len(lines_before)-20), -1):
                line = lines_before[i]
                
                # Buscar asignaciones tipo: rec = {...
                if '=' in line and '{' in line:
                    var_match = re.match(r'\s*(\w+)\s*=\s*\{', line)
                    if var_match:
                        var_name = var_match.group(1)
                        
                        # Insertar adaptación después de la creación
                        indent = ' ' * (len(line) - len(line.lstrip()))
                        
                        adaptation_code = f"""
{indent}# Aplicar adaptación de mercado
{indent}if market_context and 'market_id' in market_context:
{indent}    try:
{indent}        from src.api.mcp.utils.market_utils import market_adapter
{indent}        {var_name} = market_adapter.adapt_product_for_market({var_name}, market_context['market_id'])
{indent}    except Exception as e:
{indent}        logger.warning(f"Error adaptando producto: {{e}}")
"""
                        
                        # Encontrar el final del bloque (siguiente línea no indentada)
                        insert_pos = content.find('\n', match.end())
                        
                        # Insertar el código
                        content = content[:insert_pos] + adaptation_code + content[insert_pos:]
                        
                        print(f"✅ Adaptación añadida para variable '{var_name}'")
                        break
    
    # Guardar
    with open(router_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return True

if __name__ == "__main__":
    print("Aplicando parche de adaptación...")
    if patch_router():
        print("✅ Parche aplicado correctamente")
    else:
        print("❌ Error aplicando parche")
