"""
Market Utils - MCP-First Compatibility Layer
===========================================

Compatibility layer que redirige las funciones existentes
hacia la nueva arquitectura MCP-First con service boundaries.

Este layer:
1. Mantiene compatibilidad total con código existente
2. Usa internamente la arquitectura MCP-First
3. Facilita migración gradual hacia microservicios
4. Elimina duplicación de lógica
"""

import logging
import asyncio
from typing import Dict, Any, Optional

# Import de la nueva arquitectura MCP-First
try:
    from src.api.mcp_services.orchestration.mcp_adapter import MCPMarketAdapter
    from src.api.mcp_services.models import MarketContext, MCPConversationContext
    from src.api.mcp_services.market_config.service import MarketConfigService
    from src.api.mcp_services.currency.service import CurrencyConversionService
    mcp_available = True
except ImportError as e:
    print(f"⚠️ WARNING: MCP services not available: {e}")
    mcp_available = False

logger = logging.getLogger(__name__)

# =============================================================================
# EXCHANGE RATES - Preservados para compatibilidad inmediata
# =============================================================================

EXCHANGE_RATES = {
    "USD": 1.0, "EUR": 0.85, "GBP": 0.73, "JPY": 110.0,
    "CAD": 1.25, "AUD": 1.35, "MXN": 20.0, "BRL": 5.2
}

BASIC_TRANSLATIONS = {
    "ES": {"size": "talla", "color": "color", "price": "precio"},
    "FR": {"size": "taille", "color": "couleur", "price": "prix"}
}

# =============================================================================
# COMPATIBILITY FUNCTIONS
# =============================================================================

def convert_price_to_market_currency(
    price: float, 
    from_currency: str = "USD", 
    to_market: str = "US"
) -> Dict[str, Any]:
    """
    COMPATIBILITY: Redirige a MCP-First currency service
    """
    if mcp_available:
        logger.info("🔄 Using MCP-First currency service")
        try:
            # Usar nuevo currency service
            currency_service = CurrencyConversionService()
            
            # Mapear market a currency
            market_currency_map = {"US": "USD", "ES": "EUR", "MX": "MXN"}
            to_currency = market_currency_map.get(to_market, "USD")
            
            # CRITICAL FIX: Usar método seguro para event loop
            from src.api.utils.market_utils import _execute_async_safely
            result = _execute_async_safely(
                currency_service.convert_price(price, from_currency, to_currency)
            )
            
            return {
                "original_price": result["original_amount"],
                "converted_price": result["converted_amount"], 
                "currency": to_currency,
                "exchange_rate": result["exchange_rate"],
                "conversion_successful": result["conversion_successful"],
                "service_used": "mcp_first_currency_service"
            }
            
        except Exception as e:
            logger.error(f"❌ Error using MCP currency service: {e}")
    
    # Fallback to legacy implementation
    logger.warning("⚠️ Using fallback currency conversion")
    market_currency_map = {"US": "USD", "ES": "EUR", "MX": "MXN"}
    to_currency = market_currency_map.get(to_market, "USD")
    
    if from_currency not in EXCHANGE_RATES or to_currency not in EXCHANGE_RATES:
        return {
            "original_price": price,
            "converted_price": price,
            "conversion_successful": False,
            "service_used": "fallback"
        }
    
    usd_price = price / EXCHANGE_RATES[from_currency]
    converted_price = usd_price * EXCHANGE_RATES[to_currency]
    
    return {
        "original_price": price,
        "converted_price": round(converted_price, 2),
        "currency": to_currency,
        "exchange_rate": EXCHANGE_RATES[to_currency] / EXCHANGE_RATES[from_currency],
        "conversion_successful": True,
        "service_used": "fallback"
    }

def adapt_product_for_market(product: Dict[str, Any], market_id: str) -> Dict[str, Any]:
    """
    COMPATIBILITY: Función principal que usa MCP-First architecture
    """
    if mcp_available:
        logger.info(f"🔄 Using MCP-First adapter for market: {market_id}")
        try:
            # Usar nueva arquitectura MCP-First
            adapter = MCPMarketAdapter()
            
            # CRITICAL FIX: Usar método seguro para event loop
            from src.api.utils.market_utils import _execute_async_safely
            result = _execute_async_safely(
                adapter.adapt_product_for_market_legacy(product, market_id)
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error using MCP adapter: {e}")
    
    # Fallback básico
    logger.warning("⚠️ Using basic fallback adaptation")
    adapted = product.copy()
    
    # Conversión básica de precio
    if "price" in product:
        price_conversion = convert_price_to_market_currency(
            product["price"], 
            product.get("currency", "USD"), 
            market_id
        )
        if price_conversion["conversion_successful"]:
            adapted["price"] = price_conversion["converted_price"]
            adapted["currency"] = price_conversion["currency"]
    
    # Metadata básica
    adapted["market_id"] = market_id
    adapted["market_adapted"] = True
    adapted["adapter_used"] = "fallback"
    
    return adapted

# Otras funciones de compatibilidad
def translate_basic_text(text: str, target_market: str = "US") -> Dict[str, Any]:
    """COMPATIBILITY: Traducción básica"""
    if target_market not in BASIC_TRANSLATIONS:
        return {"original_text": text, "translated_text": text, "translation_applied": False}
    
    translated = text.lower()
    for en_term, translated_term in BASIC_TRANSLATIONS[target_market].items():
        if en_term in translated:
            translated = translated.replace(en_term, translated_term)
    
    return {"original_text": text, "translated_text": translated, "translation_applied": True}

def clean_html_tags(text: str) -> str:
    """Compatibility function"""
    import re
    return re.sub(r'<[^>]+>', '', text).strip()

def get_market_currency_symbol(market_id: str) -> str:
    """Compatibility function"""
    symbols = {"US": "$", "ES": "€", "MX": "$", "GB": "£"}
    return symbols.get(market_id, "$")

def format_price_for_market(price: float, market_id: str) -> str:
    """Compatibility function"""
    symbol = get_market_currency_symbol(market_id)
    return f"{symbol}{price:,.2f}"
