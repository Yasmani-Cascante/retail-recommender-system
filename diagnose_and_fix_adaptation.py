# diagnose_and_fix_adaptation.py
"""
Script para diagnosticar y corregir el problema de adaptación de mercado
"""

import os
import re
import json
from datetime import datetime

def diagnose_router():
    """Diagnostica el estado actual del router"""
    print("🔍 DIAGNÓSTICO DEL ROUTER MCP")
    print("="*60)
    
    router_path = "src/api/routers/mcp_router.py"
    
    if not os.path.exists(router_path):
        print(f"❌ No existe: {router_path}")
        return None
    
    with open(router_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Verificaciones
    checks = {
        "Import market_adapter": "from src.api.mcp.utils.market_utils import market_adapter" in content,
        "Llamada a adapt_product_for_market": "market_adapter.adapt_product_for_market" in content,
        "Flag market_adapted": '"market_adapted": True' in content or "'market_adapted': True" in content,
    }
    
    print("Verificaciones básicas:")
    for check, result in checks.items():
        print(f"{'✅' if result else '❌'} {check}")
    
    # Buscar dónde se establece market_adapted
    market_adapted_matches = list(re.finditer(r'["\']market_adapted["\']\s*:\s*True', content))
    
    if market_adapted_matches:
        print(f"\n📍 Flag 'market_adapted' encontrado en {len(market_adapted_matches)} lugares")
        
        for i, match in enumerate(market_adapted_matches[:2]):  # Mostrar máximo 2
            start = max(0, match.start() - 200)
            end = min(len(content), match.end() + 200)
            context = content[start:end]
            
            print(f"\nContexto {i+1}:")
            print("..." + context.strip() + "...")
            
            # Verificar si hay adaptación real cerca
            if "market_adapter" not in context:
                print("⚠️ Se establece el flag pero NO se llama a market_adapter")
    
    return content

def create_proper_adaptation():
    """Crea una implementación correcta de la adaptación"""
    print("\n🔧 CREANDO IMPLEMENTACIÓN CORRECTA")
    print("="*60)
    
    # Crear un parche directo para el router
    patch_content = '''# patch_router_adaptation.py
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
    pattern = r'(\{[^}]*["\']market_adapted["\']\s*:\s*True[^}]*\})'
    
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
            lines_before = content[:block_start].split('\\n')
            
            # Buscar la línea donde se asigna este dict
            for i in range(len(lines_before)-1, max(0, len(lines_before)-20), -1):
                line = lines_before[i]
                
                # Buscar asignaciones tipo: rec = {...
                if '=' in line and '{' in line:
                    var_match = re.match(r'\\s*(\\w+)\\s*=\\s*\\{', line)
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
                        insert_pos = content.find('\\n', match.end())
                        
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
'''
    
    with open("patch_router_adaptation.py", "w", encoding="utf-8") as f:
        f.write(patch_content)
    
    print("✅ Creado: patch_router_adaptation.py")
    
    # También crear una versión mejorada de market_utils
    improved_utils = '''# improved_market_utils.py
"""
Versión mejorada y verificada del adaptador de mercado
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class MarketAdapter:
    """Adaptador de mercado con conversión de moneda y traducción básica"""
    
    EXCHANGE_RATES = {
        "COP_TO_USD": 0.00025,  # 1 COP = 0.00025 USD (4000 COP = 1 USD)
        "COP_TO_EUR": 0.00023,  # 1 COP = 0.00023 EUR  
        "COP_TO_MXN": 0.0043,   # 1 COP = 0.0043 MXN
    }
    
    MARKET_CURRENCIES = {
        "US": "USD",
        "ES": "EUR",
        "MX": "MXN", 
        "CO": "COP"
    }
    
    BASIC_TRANSLATIONS = {
        # Jewelry
        "aros": "earrings",
        "aro": "earring",
        "argollas": "hoops",
        "argolla": "hoop",
        "maxi": "maxi",
        "luciana": "luciana",
        "dorado": "gold",
        "plateado": "silver",
        "pompón": "pompom",
        "pétalos": "petals",
        "morados": "purple",
        "flor": "flower",
        "brillo": "sparkle",
        "amarillo": "yellow",
        "fucsia": "fuchsia",
        "celeste": "light blue",
        "burdeo": "burgundy",
        "hoja": "leaf",
        "gota": "drop",
        "piedra": "stone",
        "verde": "green",
        "oscuro": "dark",
        "diana": "diana",
        # Clothing
        "vestido": "dress",
        "falda": "skirt", 
        "blusa": "blouse",
        "pantalón": "pants",
        "zapatos": "shoes",
        "bolso": "bag",
        "cinturón": "belt",
        # Descriptions
        "largo": "long",
        "corto": "short",
        "fiesta": "party",
        "casual": "casual",
        "elegante": "elegant"
    }
    
    def adapt_product_for_market(self, product: Dict[str, Any], market_id: str) -> Dict[str, Any]:
        """
        Adapta un producto para el mercado especificado
        
        Args:
            product: Producto a adaptar
            market_id: ID del mercado (US, ES, MX, CO)
            
        Returns:
            Producto adaptado con precio convertido y textos traducidos
        """
        try:
            # Logging para debug
            logger.info(f"Adaptando producto para mercado {market_id}")
            logger.debug(f"Producto original: price={product.get('price')}, currency={product.get('currency')}")
            
            # Clonar para no mutar el original
            adapted = product.copy()
            
            # 1. CONVERSIÓN DE PRECIO
            if "price" in adapted and market_id in self.MARKET_CURRENCIES:
                original_price = float(adapted["price"])
                
                # Guardar valores originales SIEMPRE
                adapted["original_price"] = original_price
                adapted["original_currency"] = adapted.get("currency", "COP")
                
                # Determinar moneda origen
                # Si ya tiene currency y no es la del mercado, probablemente es COP
                current_currency = adapted.get("currency", "COP")
                
                # Si el precio es > 1000 y la moneda es USD/EUR, probablemente es COP mal etiquetado
                if original_price > 1000 and current_currency in ["USD", "EUR"]:
                    logger.warning(f"Precio sospechoso: {original_price} {current_currency}, tratando como COP")
                    current_currency = "COP"
                
                # Convertir precio según mercado
                target_currency = self.MARKET_CURRENCIES[market_id]
                
                if current_currency == "COP" and target_currency != "COP":
                    # Convertir de COP a moneda destino
                    if target_currency == "USD":
                        adapted["price"] = round(original_price * self.EXCHANGE_RATES["COP_TO_USD"], 2)
                    elif target_currency == "EUR":
                        adapted["price"] = round(original_price * self.EXCHANGE_RATES["COP_TO_EUR"], 2)
                    elif target_currency == "MXN":
                        adapted["price"] = round(original_price * self.EXCHANGE_RATES["COP_TO_MXN"], 2)
                    
                    logger.info(f"Precio convertido: {original_price} COP -> {adapted['price']} {target_currency}")
                
                # Actualizar moneda
                adapted["currency"] = target_currency
            
            # 2. TRADUCCIÓN (solo para mercado US)
            if market_id == "US":
                # Traducir título/nombre
                for field in ["title", "name"]:
                    if field in adapted and adapted[field]:
                        original_text = str(adapted[field])
                        adapted[f"original_{field}"] = original_text
                        
                        # Traducir
                        translated = self._translate_text(original_text)
                        if translated != original_text:
                            adapted[field] = translated
                            logger.info(f"Traducido: '{original_text}' -> '{translated}'")
                
                # Traducir descripción (solo primeras palabras)
                if "description" in adapted and adapted["description"]:
                    original_desc = str(adapted["description"])
                    adapted["original_description"] = original_desc
                    
                    # Traducir solo el inicio
                    first_words = original_desc[:100]
                    translated_start = self._translate_text(first_words)
                    if translated_start != first_words:
                        adapted["description"] = translated_start + original_desc[100:]
            
            # 3. Verificar que la adaptación se aplicó
            if adapted.get("original_price") is not None:
                adapted["market_adapted"] = True
                adapted["adapted_for_market"] = market_id
                logger.info(f"✅ Adaptación completa para {market_id}")
            else:
                logger.warning(f"⚠️ Adaptación incompleta para {market_id}")
            
            return adapted
            
        except Exception as e:
            logger.error(f"Error adaptando producto: {e}", exc_info=True)
            # En caso de error, devolver original con flag
            product["adaptation_error"] = str(e)
            return product
    
    def _translate_text(self, text: str) -> str:
        """Traduce texto del español al inglés usando diccionario básico"""
        if not text:
            return text
        
        # Convertir a minúsculas para buscar
        text_lower = text.lower()
        translated_lower = text_lower
        
        # Aplicar traducciones palabra por palabra
        for spanish, english in self.BASIC_TRANSLATIONS.items():
            # Reemplazar palabras completas (con límites de palabra)
            import re
            pattern = r'\\b' + re.escape(spanish) + r'\\b'
            translated_lower = re.sub(pattern, english, translated_lower, flags=re.IGNORECASE)
        
        # Si hubo cambios, ajustar capitalización
        if translated_lower != text_lower:
            # Capitalizar primera letra si el original la tenía
            if text and text[0].isupper():
                words = translated_lower.split()
                if words:
                    words[0] = words[0].capitalize()
                    # Capitalizar nombres propios conocidos
                    for i, word in enumerate(words):
                        if word in ["luciana", "diana", "silvina"]:
                            words[i] = word.capitalize()
                    
                    return " ".join(words)
            
            return translated_lower
        
        # Si no se tradujo nada, devolver original
        return text


# Crear instancia global
market_adapter = MarketAdapter()

# Función de utilidad para testing
def test_adaptation():
    """Prueba la adaptación con un producto de ejemplo"""
    test_product = {
        "id": "123",
        "title": "AROS MAXI ARGOLLAS LUCIANA DORADO",
        "price": 12990.0,
        "currency": "USD",  # Mal etiquetado, es COP
        "description": "Aros de acero dorado"
    }
    
    print("Producto original:", test_product)
    print("\\nAdaptaciones:")
    
    for market in ["US", "ES", "MX", "CO"]:
        adapted = market_adapter.adapt_product_for_market(test_product.copy(), market)
        print(f"\\n{market}:")
        print(f"  Precio: {adapted.get('price')} {adapted.get('currency')}")
        print(f"  Título: {adapted.get('title')}")
        if adapted.get('original_price'):
            print(f"  (Original: {adapted.get('original_price')} {adapted.get('original_currency')})")

if __name__ == "__main__":
    test_adaptation()
'''
    
    with open("improved_market_utils.py", "w", encoding="utf-8") as f:
        f.write(improved_utils)
    
    print("✅ Creado: improved_market_utils.py")

def create_manual_test():
    """Crea un test manual para verificar la adaptación"""
    test_code = '''# test_manual_adaptation.py
"""
Test manual para verificar que la adaptación funciona
"""

import asyncio
import sys
import os

# Añadir el directorio raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.mcp.utils.market_utils import market_adapter

def test_market_adapter():
    """Prueba directa del adaptador"""
    print("🧪 TEST DIRECTO DEL ADAPTADOR")
    print("="*60)
    
    # Producto de prueba (como viene del sistema)
    test_product = {
        "id": "123",
        "title": "AROS MAXI ARGOLLAS LUCIANA DORADO",
        "price": 12990.0,
        "currency": "USD",  # Incorrectamente marcado
        "description": "Aros de acero, antialérgicos",
        "score": 0.8
    }
    
    print("Producto original:")
    print(f"  Título: {test_product['title']}")
    print(f"  Precio: {test_product['price']} {test_product['currency']}")
    
    print("\\nAdaptaciones por mercado:")
    print("-"*40)
    
    for market_id in ["US", "ES", "MX", "CO"]:
        adapted = market_adapter.adapt_product_for_market(
            test_product.copy(), 
            market_id
        )
        
        print(f"\\nMercado {market_id}:")
        print(f"  Título: {adapted.get('title')}")
        print(f"  Precio: {adapted.get('price')} {adapted.get('currency')}")
        
        if adapted.get('original_price'):
            print(f"  Original: {adapted.get('original_price')} {adapted.get('original_currency')}")
        
        if adapted.get('original_title'):
            print(f"  Título Original: {adapted.get('original_title')}")
        
        print(f"  Adaptado: {adapted.get('market_adapted', False)}")

if __name__ == "__main__":
    test_market_adapter()
'''
    
    with open("test_manual_adaptation.py", "w", encoding="utf-8") as f:
        f.write(test_code)
    
    print("✅ Creado: test_manual_adaptation.py")

def main():
    print("""
    ╔════════════════════════════════════════════════════════╗
    ║     DIAGNÓSTICO Y CORRECCIÓN - ADAPTACIÓN DE MERCADO   ║
    ╚════════════════════════════════════════════════════════╝
    """)
    
    # 1. Diagnosticar estado actual
    router_content = diagnose_router()
    
    if not router_content:
        return
    
    # 2. Crear archivos de corrección
    create_proper_adaptation()
    create_manual_test()
    
    print("\n" + "="*60)
    print("📋 PLAN DE CORRECCIÓN")
    print("="*60)
    
    print("\n1️⃣ Primero, prueba el adaptador directamente:")
    print("   python test_manual_adaptation.py")
    print("   (Esto verificará que market_utils funciona)")
    
    print("\n2️⃣ Si funciona, reemplaza market_utils.py:")
    print("   copy improved_market_utils.py src\\api\\mcp\\utils\\market_utils.py")
    
    print("\n3️⃣ Aplica el parche al router:")
    print("   python patch_router_adaptation.py")
    
    print("\n4️⃣ Reinicia el servidor y prueba:")
    print("   python -m uvicorn src.api.main_unified_redis:app --reload")
    print("   python test_market_adaptation_fixed.py")
    
    print("\n💡 El problema principal es que el flag 'market_adapted' se añade")
    print("   pero NO se está llamando realmente al adaptador.")

if __name__ == "__main__":
    main()