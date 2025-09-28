"""
Utilidades para adaptación de mercado - Versión básica
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class MarketAdapter:
    """Adaptador básico de mercado para corrección inmediata"""
    
    EXCHANGE_RATES = {
        "COP_TO_USD": 0.00025,  # 1 COP = 0.00025 USD
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
        "alas de novia": "bridal wings",
        "cinturon": "belt",
        "cinturón": "belt",
        "indio": "indian style",
        "bolso": "bag",
        "falda": "skirt",
        "vestido": "dress",
        "blusa": "blouse",
        "collar": "necklace",
        "pulsera": "bracelet"
    }
    
    def adapt_product_for_market(self, product: Dict, market_id: str) -> Dict:
        """
        Adapta un producto para el mercado especificado
        
        Args:
            product: Producto a adaptar
            market_id: ID del mercado (US, ES, MX, CO)
            
        Returns:
            Producto adaptado con precio y textos convertidos
        """
        try:
            # Clonar para no mutar el original
            adapted = product.copy()
            
            # 1. Conversión de precio
            if "price" in adapted and market_id in self.MARKET_CURRENCIES:
                original_price = adapted["price"]
                
                # Guardar valores originales
                adapted["original_price"] = original_price
                adapted["original_currency"] = "COP"
                
                # Convertir precio
                if market_id == "US":
                    adapted["price"] = round(original_price * self.EXCHANGE_RATES["COP_TO_USD"], 2)
                    adapted["currency"] = "USD"
                elif market_id == "ES":
                    adapted["price"] = round(original_price * self.EXCHANGE_RATES["COP_TO_EUR"], 2)
                    adapted["currency"] = "EUR"
                elif market_id == "MX":
                    adapted["price"] = round(original_price * self.EXCHANGE_RATES["COP_TO_MXN"], 2)
                    adapted["currency"] = "MXN"
                else:  # CO
                    adapted["currency"] = "COP"
            
            # 2. Traducción básica (solo para US)
            if market_id == "US":
                # Traducir título/nombre
                for field in ["title", "name"]:
                    if field in adapted and adapted[field]:
                        original_text = adapted[field]
                        adapted[f"original_{field}"] = original_text
                        
                        # Traducción simple
                        translated = self._translate_basic(original_text)
                        adapted[field] = translated
                
                # Traducir descripción (primeras palabras)
                if "description" in adapted and adapted["description"]:
                    original_desc = adapted["description"]
                    adapted["original_description"] = original_desc
                    adapted["description"] = self._translate_basic(original_desc)
            
            # 3. Añadir metadata
            adapted["market_adapted"] = True
            adapted["adapted_for_market"] = market_id
            
            return adapted
            
        except Exception as e:
            logger.error(f"Error adapting product: {e}")
            return product
    
    def _translate_basic(self, text: str) -> str:
        """Traducción básica usando diccionario"""
        if not text:
            return text
        
        text_lower = text.lower()
        
        # Buscar coincidencias en el diccionario
        for es_term, en_term in self.BASIC_TRANSLATIONS.items():
            if es_term in text_lower:
                # Reemplazar manteniendo capitalización
                result = text.replace(es_term, en_term)
                result = result.replace(es_term.capitalize(), en_term.capitalize())
                result = result.replace(es_term.upper(), en_term.upper())
                return result
        
        # Si no se encuentra traducción, añadir indicador
        return f"{text} [EN]"

# Instancia global para uso directo
market_adapter = MarketAdapter()
