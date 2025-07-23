"""
Market Utils - Utilidades para conversión de moneda y traducción
==============================================================

Módulo que maneja las conversiones de moneda y traducción básica
para adaptación de contenido por mercado.
"""

import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Tasas de cambio base (actualizables desde API externa)
EXCHANGE_RATES = {
    "COP_TO_USD": 0.00025,  # 1 COP = 0.00025 USD (aprox 4000 COP = 1 USD)
    "COP_TO_EUR": 0.00023,  # 1 COP = 0.00023 EUR
    "COP_TO_MXN": 0.0044,   # 1 COP = 0.0044 MXN
    "USD_TO_COP": 4000.0,   # 1 USD = 4000 COP
    "EUR_TO_COP": 4350.0,   # 1 EUR = 4350 COP
    "MXN_TO_COP": 227.0,    # 1 MXN = 227 COP
}

# Traducciones básicas para términos comunes de productos
BASIC_TRANSLATIONS = {
    # Términos de ropa y accesorios
    "Vestido de Novia": "Wedding Dress",
    "Alas de Novia": "Bridal Wings",
    "Cinturon": "Belt",
    "Cinturón": "Belt", 
    "Indio": "Indian Style",
    "Hojas Dorado": "Golden Leaves",
    "Dorado": "Golden",
    "Ivory": "Ivory",
    "Metros": "Meters",
    "Box": "Box",
    "Indispensables": "Essentials",
    "Enterito": "Jumpsuit",
    "Fiesta": "Party",
    "Largo": "Long",
    "Un Hombro": "One Shoulder",
    "Azul Oscuro": "Dark Blue",
    
    # Descripciones comunes
    "confeccionado en": "made with",
    "tela elasticada": "stretch fabric",
    "forro interior": "inner lining",
    "escote cruzado": "crossover neckline",
    "manga": "sleeve",
    "cintura": "waist",
    "abertura lateral": "side opening",
    "cierre invisible": "invisible zipper",
    "tejido indio": "indian fabric",
    "detalles dorados": "golden details",
    "hecho a mano": "handmade",
    "importado": "imported",
    
    # Frases de marketing
    "perfecto para": "perfect for",
    "ideal para": "ideal for",
    "complemento perfecto": "perfect complement",
    "diseño versátil": "versatile design",
    "añade un toque": "adds a touch",
    "realza tu estilo": "enhances your style",
    "pocas unidades disponibles": "limited units available",
    "precio especial": "special price",
}

def convert_price_to_market_currency(
    price: float, 
    from_currency: str = "COP", 
    to_market_id: str = "US"
) -> Dict[str, Any]:
    """
    Convierte precio de una moneda a la moneda del mercado objetivo.
    
    Args:
        price: Precio original
        from_currency: Moneda origen (default: COP)
        to_market_id: ID del mercado destino
        
    Returns:
        Dict con precio convertido, moneda y metadata
    """
    try:
        # Mapear market_id a moneda
        market_currencies = {
            "US": "USD",
            "ES": "EUR", 
            "MX": "MXN",
            "CL": "CLP",
            "default": "USD"
        }
        
        target_currency = market_currencies.get(to_market_id, "USD")
        
        # Si ya está en la moneda correcta, retornar tal como está
        if from_currency == target_currency:
            return {
                "price": price,
                "currency": target_currency,
                "conversion_applied": False,
                "original_price": price,
                "original_currency": from_currency
            }
        
        # Aplicar conversión
        conversion_key = f"{from_currency}_TO_{target_currency}"
        rate = EXCHANGE_RATES.get(conversion_key)
        
        if rate is None:
            logger.warning(f"No hay tasa de cambio para {conversion_key}, usando precio original")
            return {
                "price": price,
                "currency": target_currency,  # Marcar con la moneda target aunque no se haya convertido
                "conversion_applied": False,
                "original_price": price,
                "original_currency": from_currency,
                "error": f"No exchange rate found for {conversion_key}"
            }
        
        # Calcular precio convertido
        converted_price = price * rate
        
        # Redondear según la moneda
        if target_currency == "USD":
            converted_price = round(converted_price, 2)  # 2 decimales para USD
        elif target_currency == "EUR":
            converted_price = round(converted_price, 2)  # 2 decimales para EUR
        elif target_currency in ["MXN", "CLP"]:
            converted_price = round(converted_price, 0)  # Sin decimales para MXN/CLP
        
        logger.info(f"Precio convertido: {price} {from_currency} -> {converted_price} {target_currency}")
        
        return {
            "price": converted_price,
            "currency": target_currency,
            "conversion_applied": True,
            "original_price": price,
            "original_currency": from_currency,
            "exchange_rate": rate
        }
        
    except Exception as e:
        logger.error(f"Error en conversión de moneda: {e}")
        return {
            "price": price,
            "currency": from_currency,
            "conversion_applied": False,
            "original_price": price,
            "original_currency": from_currency,
            "error": str(e)
        }

def translate_basic_text(text: str, target_market: str = "US") -> Dict[str, Any]:
    """
    Aplica traducción básica de términos comunes al texto.
    
    Args:
        text: Texto a traducir
        target_market: Mercado objetivo
        
    Returns:
        Dict con texto traducido y metadata
    """
    try:
        if target_market not in ["US"]:  # Solo traducir para mercado US por ahora
            return {
                "text": text,
                "translation_applied": False,
                "original_text": text,
                "target_language": "original"
            }
        
        translated_text = text
        translations_applied = []
        
        # Aplicar traducciones básicas
        for spanish_term, english_term in BASIC_TRANSLATIONS.items():
            if spanish_term.lower() in translated_text.lower():
                # Usar regex para reemplazar manteniendo capitalización
                pattern = re.compile(re.escape(spanish_term), re.IGNORECASE)
                translated_text = pattern.sub(english_term, translated_text)
                translations_applied.append(f"{spanish_term} -> {english_term}")
        
        # Limpiar HTML y caracteres especiales comunes
        translated_text = clean_html_tags(translated_text)
        
        return {
            "text": translated_text,
            "translation_applied": len(translations_applied) > 0,
            "original_text": text,
            "target_language": "en",
            "translations_applied": translations_applied
        }
        
    except Exception as e:
        logger.error(f"Error en traducción básica: {e}")
        return {
            "text": text,
            "translation_applied": False,
            "original_text": text,
            "target_language": "original",
            "error": str(e)
        }

def clean_html_tags(text: str) -> str:
    """
    Limpia tags HTML básicos del texto.
    
    Args:
        text: Texto con posibles tags HTML
        
    Returns:
        Texto limpio
    """
    try:
        # Remover tags HTML comunes
        html_patterns = [
            r'<meta[^>]*>',
            r'<p[^>]*>',
            r'</p>',
            r'<span[^>]*>',
            r'</span>',
            r'<strong[^>]*>',
            r'</strong>',
            r'<br[^>]*>',
            r'<div[^>]*>',
            r'</div>',
        ]
        
        cleaned_text = text
        for pattern in html_patterns:
            cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)
        
        # Limpiar espacios múltiples
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        return cleaned_text
        
    except Exception as e:
        logger.error(f"Error limpiando HTML: {e}")
        return text

def adapt_product_for_market(product: Dict[str, Any], market_id: str) -> Dict[str, Any]:
    """
    Adapta un producto completo para un mercado específico.
    
    Args:
        product: Producto original
        market_id: ID del mercado objetivo
        
    Returns:
        Producto adaptado
    """
    try:
        adapted_product = product.copy()
        adaptations_applied = []
        
        # 1. Convertir precio
        if "price" in product:
            price_conversion = convert_price_to_market_currency(
                product["price"], 
                from_currency="COP",  # Asumiendo que los precios vienen en COP
                to_market_id=market_id
            )
            
            adapted_product["price"] = price_conversion["price"]
            adapted_product["currency"] = price_conversion["currency"]
            
            if price_conversion["conversion_applied"]:
                adaptations_applied.append("price_conversion")
                adapted_product["original_price"] = price_conversion["original_price"]
                adapted_product["exchange_rate"] = price_conversion.get("exchange_rate")
        
        # 2. Traducir título
        if "title" in product:
            title_translation = translate_basic_text(product["title"], market_id)
            adapted_product["title"] = title_translation["text"]
            
            if title_translation["translation_applied"]:
                adaptations_applied.append("title_translation")
                adapted_product["original_title"] = title_translation["original_text"]
        
        # 3. Traducir descripción
        if "description" in product:
            desc_translation = translate_basic_text(product["description"], market_id)
            adapted_product["description"] = desc_translation["text"]
            
            if desc_translation["translation_applied"]:
                adaptations_applied.append("description_translation")
                adapted_product["original_description"] = desc_translation["original_text"]
        
        # 4. Añadir metadata de adaptación
        adapted_product["market_adapted"] = True
        adapted_product["adaptations_applied"] = adaptations_applied
        adapted_product["adaptation_timestamp"] = datetime.now().isoformat()
        
        logger.info(f"Producto {product.get('id', 'unknown')} adaptado para mercado {market_id}: {adaptations_applied}")
        
        return adapted_product
        
    except Exception as e:
        logger.error(f"Error adaptando producto para mercado: {e}")
        # Retornar producto original en caso de error
        return product

def get_market_currency_symbol(market_id: str) -> str:
    """
    Obtiene el símbolo de moneda para un mercado.
    
    Args:
        market_id: ID del mercado
        
    Returns:
        Símbolo de moneda
    """
    symbols = {
        "US": "$",
        "ES": "€",
        "MX": "$",
        "CL": "$",
        "default": "$"
    }
    return symbols.get(market_id, "$")

def format_price_for_market(price: float, market_id: str) -> str:
    """
    Formatea un precio según las convenciones del mercado.
    
    Args:
        price: Precio numérico
        market_id: ID del mercado
        
    Returns:
        Precio formateado como string
    """
    try:
        symbol = get_market_currency_symbol(market_id)
        
        if market_id == "US":
            return f"${price:,.2f}"
        elif market_id == "ES":
            return f"€{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        elif market_id in ["MX", "CL"]:
            return f"{symbol}{price:,.0f}"
        else:
            return f"{symbol}{price:,.2f}"
            
    except Exception as e:
        logger.error(f"Error formateando precio: {e}")
        return f"${price}"
