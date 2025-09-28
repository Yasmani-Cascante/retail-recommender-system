# src/api/utils/__init__.py
"""
Utils package for API utilities
"""

from .market_utils import (
    convert_price_to_market_currency,
    translate_basic_text,
    adapt_product_for_market,
    format_price_for_market,
    get_market_currency_symbol
)

from .direct_corrections import (
    apply_direct_market_corrections,
    quick_price_fix,
    quick_translation_fix,
    apply_critical_fixes_simple
)

__all__ = [
    "convert_price_to_market_currency",
    "translate_basic_text", 
    "adapt_product_for_market",
    "format_price_for_market",
    "get_market_currency_symbol",
    "apply_direct_market_corrections",
    "quick_price_fix",
    "quick_translation_fix",
    "apply_critical_fixes_simple"
]
