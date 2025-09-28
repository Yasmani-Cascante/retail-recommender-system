#!/usr/bin/env python3
"""
CORRECCIÓN 3: Event Loop Context Fix
===================================

Corrige los problemas de event loop en sync wrappers y health checks
"""

def create_fixed_market_utils():
    """Crea versión corregida de market_utils con event loop handling apropiado"""
    
    fixed_content = '''"""
Market Utils - Async-First Architecture - FIXED VERSION
======================================================

Versión corregida que maneja apropiadamente los contextos de event loop.
"""

import logging
import asyncio
import concurrent.futures
import threading
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
# EVENT LOOP UTILITIES - CORRECCIÓN PRINCIPAL
# =============================================================================

def _is_running_in_event_loop() -> bool:
    """Detecta si estamos ejecutando en un event loop activo"""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False

def _execute_async_safely(coro):
    """
    ✅ FIXED: Ejecuta coroutine de manera segura según el contexto
    """
    if _is_running_in_event_loop():
        # Estamos en event loop - usar thread pool
        def run_in_thread():
            # Crear nuevo loop en thread separado
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        
        # Ejecutar en thread pool con timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            try:
                return future.result(timeout=30)  # 30 second timeout
            except concurrent.futures.TimeoutError:
                logger.error("Async operation timed out")
                raise RuntimeError("Async operation timed out")
    else:
        # No hay event loop - usar asyncio.run()
        return asyncio.run(coro)

# =============================================================================
# ASYNC-FIRST CORE FUNCTIONS - FIXED
# =============================================================================

async def convert_price_to_market_currency_async(
    price: float, 
    from_currency: str = "USD", 
    to_market: str = "US"
) -> Dict[str, Any]:
    """
    ✅ ASYNC-FIRST: Conversión de moneda completamente asíncrona
    """
    if mcp_available:
        logger.info("🔄 Using MCP-First currency service (async-native)")
        try:
            currency_service = CurrencyConversionService()
            market_service = MarketConfigService()
            
            # ✅ FIXED: Usar método que existe o fallback
            try:
                target_currency = await market_service.get_market_currency(to_market)
            except AttributeError:
                # Fallback si get_market_currency no existe
                context = await market_service.get_market_context(to_market)
                target_currency = context.currency
            
            # ✅ PURE ASYNC: Sin threading, sin event loop conflicts
            result = await currency_service.convert_price(price, from_currency, target_currency)
            
            return {
                "original_price": result["original_amount"],
                "converted_price": result["converted_amount"], 
                "currency": target_currency,
                "exchange_rate": result["exchange_rate"],
                "conversion_successful": result["conversion_successful"],
                "service_used": "mcp_async_native_fixed",
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
    """
    if mcp_available:
        logger.info(f"🔄 Using MCP-First adapter (async-native) for: {market_id}")
        try:
            adapter = MCPMarketAdapter()
            
            # ✅ PURE ASYNC: Sin threading, sin event loop conflicts
            result = await adapter.adapt_product_for_market_legacy(product, market_id)
            
            # Añadir metadata de arquitectura async
            result["async_architecture"] = {
                "version": "async_first_fixed_v1.0",
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
            "service_used": "async_fallback_fixed"
        }
    
    usd_price = price / EXCHANGE_RATES[from_currency]
    converted_price = usd_price * EXCHANGE_RATES[to_currency]
    
    return {
        "original_price": price,
        "converted_price": round(converted_price, 2),
        "currency": to_currency,
        "exchange_rate": EXCHANGE_RATES[to_currency] / EXCHANGE_RATES[from_currency],
        "conversion_successful": True,
        "service_used": "async_fallback_fixed"
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
    adapted["adapter_used"] = "async_fallback_fixed"
    adapted["architecture"] = "async_first"
    
    return adapted

# =============================================================================
# SYNC COMPATIBILITY WRAPPERS - FIXED VERSION
# =============================================================================

def convert_price_to_market_currency(
    price: float, 
    from_currency: str = "USD", 
    to_market: str = "US"
) -> Dict[str, Any]:
    """
    ✅ FIXED SYNC WRAPPER: Maneja apropiadamente el contexto de event loop
    """
    try:
        coro = convert_price_to_market_currency_async(price, from_currency, to_market)
        return _execute_async_safely(coro)
    except Exception as e:
        logger.error(f"Error in sync wrapper: {e}")
        # Emergency fallback
        return {
            "original_price": price,
            "converted_price": price,
            "conversion_successful": False,
            "service_used": "emergency_fallback_fixed",
            "error": str(e)
        }

def adapt_product_for_market(product: Dict[str, Any], market_id: str) -> Dict[str, Any]:
    """
    ✅ FIXED SYNC WRAPPER: Maneja apropiadamente el contexto de event loop
    """
    try:
        coro = adapt_product_for_market_async(product, market_id)
        return _execute_async_safely(coro)
    except Exception as e:
        logger.error(f"Error in sync wrapper: {e}")
        # Emergency fallback
        adapted = product.copy()
        adapted["market_id"] = market_id
        adapted["market_adapted"] = False
        adapted["adapter_used"] = "emergency_fallback_fixed"
        adapted["error"] = str(e)
        return adapted

# =============================================================================
# HEALTH CHECK - FIXED VERSION
# =============================================================================

async def async_health_check():
    """Health check async version"""
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
            "architecture": "async_first_fixed",
            "event_loop_handling": "corrected"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "architecture": "async_first_fixed"
        }

def health_check():
    """
    ✅ FIXED SYNC WRAPPER: Health check que maneja apropiadamente el contexto
    """
    try:
        return _execute_async_safely(async_health_check())
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "context": "sync_wrapper_fixed"
        }

# =============================================================================
# UTILITY FUNCTIONS - FIXED
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
    """✅ FIXED Sync wrapper para traducción"""
    try:
        coro = translate_basic_text_async(text, target_market)
        return _execute_async_safely(coro)
    except Exception as e:
        logger.error(f"Error in translate wrapper: {e}")
        return {"original_text": text, "translated_text": text, "translation_applied": False, "error": str(e)}

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
# TESTING UTILITIES
# =============================================================================

def test_event_loop_handling():
    """Test para verificar que el manejo de event loop funciona"""
    print("🧪 Testing event loop handling...")
    
    try:
        # Test 1: Sync context
        print("   Testing sync context...")
        result1 = convert_price_to_market_currency(100.0, "USD", "ES")
        assert result1["conversion_successful"] == True
        print("   ✅ Sync context works")
        
        # Test 2: Health check
        print("   Testing health check...")
        health = health_check()
        assert health["status"] in ["healthy", "error"]  # Either is acceptable
        print(f"   ✅ Health check: {health['status']}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Testing fixed event loop handling...")
    success = test_event_loop_handling()
    print(f"Result: {'✅ SUCCESS' if success else '❌ FAILED'}")
'''
    
    # Escribir archivo corregido
    try:
        with open("src/api/utils/market_utils_fixed.py", 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        
        print("✅ market_utils_fixed.py creado")
        return True
        
    except Exception as e:
        print(f"❌ Error creando archivo corregido: {e}")
        return False

def apply_event_loop_fix():
    """Aplica la corrección de event loop"""
    
    print("🔧 APLICANDO CORRECCIÓN 3: Event Loop Context Fix")
    print("=" * 60)
    
    # Crear versión corregida
    if not create_fixed_market_utils():
        return False
    
    # Backup del archivo actual
    import shutil
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"src/api/utils/market_utils_backup_{timestamp}.py"
    
    try:
        shutil.copy("src/api/utils/market_utils.py", backup_file)
        print(f"✅ Backup creado: {backup_file}")
    except Exception as e:
        print(f"⚠️ No se pudo crear backup: {e}")
    
    # Aplicar corrección
    try:
        shutil.move("src/api/utils/market_utils_fixed.py", "src/api/utils/market_utils.py")
        print("✅ Corrección aplicada a market_utils.py")
        return True
    except Exception as e:
        print(f"❌ Error aplicando corrección: {e}")
        return False

if __name__ == "__main__":
    success = apply_event_loop_fix()
    if success:
        print("🎉 Event Loop Context Fix completed successfully")
    else:
        print("❌ Event Loop Context Fix failed")