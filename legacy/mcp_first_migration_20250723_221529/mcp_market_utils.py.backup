# improved_market_utils.py
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
            pattern = r'\b' + re.escape(spanish) + r'\b'
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
    print("\nAdaptaciones:")
    
    for market in ["US", "ES", "MX", "CO"]:
        adapted = market_adapter.adapt_product_for_market(test_product.copy(), market)
        print(f"\n{market}:")
        print(f"  Precio: {adapted.get('price')} {adapted.get('currency')}")
        print(f"  Título: {adapted.get('title')}")
        if adapted.get('original_price'):
            print(f"  (Original: {adapted.get('original_price')} {adapted.get('original_currency')})")

if __name__ == "__main__":
    test_adaptation()
