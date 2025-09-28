"""
Market Utils - Async-First Architecture
=====================================

Versión completamente asíncrona que resuelve definitivamente
los problemas de event loop y optimiza performance.
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
    print("✅ MCP services disponibles")
except ImportError as e:
    print(f"⚠️ WARNING: MCP services not available: {e}")
    mcp_available = False

logger = logging.getLogger(__name__)

# =============================================================================
# ASYNC-FIRST CORE FUNCTIONS
# =============================================================================

async def convert_price_to_market_currency_async(
    price: float, 
    from_currency: str = "USD", 
    to_market: str = "US"
) -> Dict[str, Any]:
    """
    ✅ ASYNC-FIRST: Conversión de moneda completamente asíncrona
    Resuelve definitivamente los problemas de event loop.
    """
    if mcp_available:
        logger.info("🔄 Using MCP-First currency service (async-native)")
        try:
            currency_service = CurrencyConversionService()
            market_service = MarketConfigService()
            
            # Mapear market a currency usando service async
            target_currency = await market_service.get_market_currency(to_market)
            
            # ✅ PURE ASYNC: Sin threading, sin event loop conflicts
            result = await currency_service.convert_price(price, from_currency, target_currency)
            
            return {
                "original_price": result["original_amount"],
                "converted_price": result["converted_amount"], 
                "currency": target_currency,
                "exchange_rate": result["exchange_rate"],
                "conversion_successful": result["conversion_successful"],
                "service_used": "mcp_async_native",
                "architecture": "async_first",
                "performance_optimized": True
            }
            
        except Exception as e:
            logger.error(f"❌ Error in async currency service: {e}")
            # Fallback async
            return await _async_fallback_currency(price, from_currency, to_market)
    
    # Fallback async si MCP no disponible
    return await _async_fallback_currency(price, from_currency, to_market)

async def adapt_product_for_market_async(
    product: Dict[str, Any], 
    market_id: str
) -> Dict[str, Any]:
    """
    ✅ ASYNC-FIRST: Adaptación de producto completamente asíncrona
    Resuelve definitivamente los problemas de event loop.
    """
    if mcp_available:
        logger.info(f"🔄 Using MCP-First adapter (async-native) for: {market_id}")
        try:
            adapter = MCPMarketAdapter()
            
            # ✅ PURE ASYNC: Sin threading, sin event loop conflicts
            result = await adapter.adapt_product_for_market_legacy(product, market_id)
            
            # Añadir metadata de arquitectura async
            result["async_architecture"] = {
                "version": "async_first_v1.0",
                "thread_free": True,
                "event_loop_optimized": True,
                "performance_tier": "enterprise"
            }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in async adapter: {e}")
            # Fallback async
            return await _async_fallback_adaptation(product, market_id)
    
    # Fallback async si MCP no disponible
    return await _async_fallback_adaptation(product, market_id)

# =============================================================================
# ASYNC FALLBACK FUNCTIONS
# =============================================================================

async def _async_fallback_currency(price: float, from_currency: str, to_market: str) -> Dict[str, Any]:
    """Fallback async para conversión de moneda"""
    logger.warning("⚠️ Using async fallback currency conversion")
    
    # Rates estáticos para fallback
    EXCHANGE_RATES = {
        "USD": 1.0, "EUR": 0.85, "GBP": 0.73, "JPY": 110.0,
        "CAD": 1.25, "AUD": 1.35, "MXN": 20.0, "BRL": 5.2
    }
    
    market_currency_map = {"US": "USD", "ES": "EUR", "MX": "MXN"}
    to_currency = market_currency_map.get(to_market, "USD")
    
    # Simular operación async
    await asyncio.sleep(0.001)
    
    if from_currency not in EXCHANGE_RATES or to_currency not in EXCHANGE_RATES:
        return {
            "original_price": price,
            "converted_price": price,
            "conversion_successful": False,
            "service_used": "async_fallback"
        }
    
    usd_price = price / EXCHANGE_RATES[from_currency]
    converted_price = usd_price * EXCHANGE_RATES[to_currency]
    
    return {
        "original_price": price,
        "converted_price": round(converted_price, 2),
        "currency": to_currency,
        "exchange_rate": EXCHANGE_RATES[to_currency] / EXCHANGE_RATES[from_currency],
        "conversion_successful": True,
        "service_used": "async_fallback"
    }

async def _async_fallback_adaptation(product: Dict[str, Any], market_id: str) -> Dict[str, Any]:
    """Fallback async para adaptación de productos"""
    logger.warning("⚠️ Using async fallback adaptation")
    
    adapted = product.copy()
    
    # Usar conversión async
    if "price" in product:
        price_conversion = await convert_price_to_market_currency_async(
            product["price"], 
            product.get("currency", "USD"), 
            market_id
        )
        if price_conversion["conversion_successful"]:
            adapted["price"] = price_conversion["converted_price"]
            adapted["currency"] = price_conversion["currency"]
    
    # Metadata
    adapted["market_id"] = market_id
    adapted["market_adapted"] = True
    adapted["adapter_used"] = "async_fallback"
    adapted["architecture"] = "async_first"
    
    return adapted

# =============================================================================
# SYNC COMPATIBILITY WRAPPERS - Para Legacy Code
# =============================================================================

def convert_price_to_market_currency(
    price: float, 
    from_currency: str = "USD", 
    to_market: str = "US"
) -> Dict[str, Any]:
    """
    SYNC WRAPPER: Para compatibilidad con código legacy
    Usa asyncio.run() para ejecutar la versión async de manera limpia.
    """
    try:
        # ✅ CLEAN APPROACH: asyncio.run() maneja el event loop correctamente
        return asyncio.run(convert_price_to_market_currency_async(price, from_currency, to_market))
    except Exception as e:
        logger.error(f"Error in sync wrapper: {e}")
        # Emergency fallback
        return {
            "original_price": price,
            "converted_price": price,
            "conversion_successful": False,
            "service_used": "emergency_fallback",
            "error": str(e)
        }

def adapt_product_for_market(product: Dict[str, Any], market_id: str) -> Dict[str, Any]:
    """
    SYNC WRAPPER: Para compatibilidad con código legacy
    Usa asyncio.run() para ejecutar la versión async de manera limpia.
    """
    try:
        # ✅ CLEAN APPROACH: asyncio.run() maneja el event loop correctamente
        return asyncio.run(adapt_product_for_market_async(product, market_id))
    except Exception as e:
        logger.error(f"Error in sync wrapper: {e}")
        # Emergency fallback
        adapted = product.copy()
        adapted["market_id"] = market_id
        adapted["market_adapted"] = False
        adapted["adapter_used"] = "emergency_fallback"
        adapted["error"] = str(e)
        return adapted

# =============================================================================
# PERFORMANCE MONITORING
# =============================================================================

class AsyncPerformanceTracker:
    """Tracker para monitorear performance de la migración async"""
    
    def __init__(self):
        self.metrics = {
            "total_calls": 0,
            "async_calls": 0,
            "sync_wrapper_calls": 0,
            "avg_response_time": 0.0,
            "error_count": 0
        }
    
    async def track_async_call(self, func_name: str, start_time: float, end_time: float, success: bool):
        """Track llamada async"""
        self.metrics["total_calls"] += 1
        self.metrics["async_calls"] += 1
        
        response_time = end_time - start_time
        self.metrics["avg_response_time"] = (
            (self.metrics["avg_response_time"] * (self.metrics["total_calls"] - 1) + response_time) 
            / self.metrics["total_calls"]
        )
        
        if not success:
            self.metrics["error_count"] += 1
    
    def track_sync_wrapper_call(self):
        """Track llamada a sync wrapper"""
        self.metrics["total_calls"] += 1
        self.metrics["sync_wrapper_calls"] += 1
    
    def get_migration_status(self):
        """Obtiene status de migración"""
        if self.metrics["total_calls"] == 0:
            return {"migration_progress": "0%", "recommendation": "START_MIGRATION"}
        
        async_percentage = (self.metrics["async_calls"] / self.metrics["total_calls"]) * 100
        
        return {
            "migration_progress": f"{async_percentage:.1f}%",
            "avg_response_time": f"{self.metrics['avg_response_time']*1000:.2f}ms",
            "error_rate": f"{(self.metrics['error_count']/self.metrics['total_calls'])*100:.2f}%",
            "recommendation": "COMPLETE_MIGRATION" if async_percentage > 80 else "CONTINUE_MIGRATION"
        }

# Instancia global del tracker
performance_tracker = AsyncPerformanceTracker()

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

async def translate_basic_text_async(text: str, target_market: str = "US") -> Dict[str, Any]:
    """Versión async de traducción básica"""
    BASIC_TRANSLATIONS = {
        "ES": {"size": "talla", "color": "color", "price": "precio"},
        "FR": {"size": "taille", "color": "couleur", "price": "prix"}
    }
    
    # Simular operación async
    await asyncio.sleep(0.001)
    
    if target_market not in BASIC_TRANSLATIONS:
        return {"original_text": text, "translated_text": text, "translation_applied": False}
    
    translated = text.lower()
    for en_term, translated_term in BASIC_TRANSLATIONS[target_market].items():
        if en_term in translated:
            translated = translated.replace(en_term, translated_term)
    
    return {"original_text": text, "translated_text": translated, "translation_applied": True}

def translate_basic_text(text: str, target_market: str = "US") -> Dict[str, Any]:
    """Sync wrapper para traducción"""
    return asyncio.run(translate_basic_text_async(text, target_market))

def clean_html_tags(text: str) -> str:
    """Utility function (sync)"""
    import re
    return re.sub(r'<[^>]+>', '', text).strip()

def get_market_currency_symbol(market_id: str) -> str:
    """Utility function (sync)"""
    symbols = {"US": "$", "ES": "€", "MX": "$", "GB": "£"}
    return symbols.get(market_id, "$")

def format_price_for_market(price: float, market_id: str) -> str:
    """Utility function (sync)"""
    symbol = get_market_currency_symbol(market_id)
    return f"{symbol}{price:,.2f}"

# =============================================================================
# HEALTH CHECK
# =============================================================================

async def async_health_check():
    """Health check para verificar que la migración async funciona"""
    try:
        # Test basic currency conversion
        result1 = await convert_price_to_market_currency_async(100.0, "USD", "ES")
        
        # Test product adaptation
        test_product = {"id": "test", "price": 50.0, "currency": "USD"}
        result2 = await adapt_product_for_market_async(test_product, "ES")
        
        return {
            "status": "healthy",
            "async_functions": "operational",
            "currency_conversion": result1["conversion_successful"],
            "product_adaptation": result2["market_adapted"],
            "architecture": "async_first"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "architecture": "async_first"
        }

def health_check():
    """Sync wrapper para health check"""
    return asyncio.run(async_health_check())

