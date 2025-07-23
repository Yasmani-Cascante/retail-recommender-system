# src/core/market/adapter.py
"""
Unified Market Adapter - Single Source of Truth
==============================================

This module provides the ONLY market adaptation logic for the entire system.
It handles currency conversion, text translation, and market-specific transformations.

Author: System Architect
Version: 2.0.0
Last Updated: 2024-01-19
"""

import logging
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import asyncio

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketConfiguration:
    """Immutable market configuration"""
    market_id: str
    currency_code: str
    language_code: str
    exchange_rate_from_cop: Decimal
    decimal_places: int = 2
    
    @property
    def currency_symbol(self) -> str:
        symbols = {"USD": "$", "EUR": "€", "MXN": "$", "COP": "$"}
        return symbols.get(self.currency_code, self.currency_code)


class MarketAdapterError(Exception):
    """Base exception for market adapter errors"""
    pass


class MarketAdapter:
    """
    Unified market adapter for multi-market e-commerce system.
    
    This class is the SINGLE SOURCE OF TRUTH for all market adaptations.
    It provides currency conversion, basic translation, and market-specific
    transformations for product data.
    
    Usage:
        adapter = MarketAdapter()
        adapted_product = await adapter.adapt_product(product, "US")
    """
    
    # Market configurations - single source of truth
    MARKETS = {
        "US": MarketConfiguration(
            market_id="US",
            currency_code="USD",
            language_code="en",
            exchange_rate_from_cop=Decimal("0.00025"),
            decimal_places=2
        ),
        "ES": MarketConfiguration(
            market_id="ES",
            currency_code="EUR",
            language_code="es",
            exchange_rate_from_cop=Decimal("0.00023"),
            decimal_places=2
        ),
        "MX": MarketConfiguration(
            market_id="MX",
            currency_code="MXN",
            language_code="es",
            exchange_rate_from_cop=Decimal("0.0043"),
            decimal_places=2
        ),
        "CO": MarketConfiguration(
            market_id="CO",
            currency_code="COP",
            language_code="es",
            exchange_rate_from_cop=Decimal("1.0"),
            decimal_places=0
        ),
        "default": MarketConfiguration(
            market_id="default",
            currency_code="USD",
            language_code="en",
            exchange_rate_from_cop=Decimal("0.00025"),
            decimal_places=2
        )
    }
    
    # Translation dictionary for basic terms
    TRANSLATIONS = {
        # Jewelry terms
        "aros": "earrings",
        "aro": "earring",
        "argollas": "hoops",
        "argolla": "hoop",
        "anillo": "ring",
        "anillos": "rings",
        "collar": "necklace",
        "collares": "necklaces",
        "pulsera": "bracelet",
        "pulseras": "bracelets",
        "pendientes": "earrings",
        
        # Materials
        "oro": "gold",
        "dorado": "gold",
        "plata": "silver",
        "plateado": "silver",
        "acero": "steel",
        "piedra": "stone",
        "cristal": "crystal",
        
        # Colors
        "negro": "black",
        "blanco": "white",
        "rojo": "red",
        "azul": "blue",
        "verde": "green",
        "amarillo": "yellow",
        "morado": "purple",
        "rosa": "pink",
        "gris": "gray",
        "marrón": "brown",
        "dorado": "golden",
        "plateado": "silver",
        
        # Descriptors
        "grande": "large",
        "pequeño": "small",
        "maxi": "maxi",
        "mini": "mini",
        "largo": "long",
        "corto": "short",
        "elegante": "elegant",
        "moderno": "modern",
        "clásico": "classic",
        "brillante": "shiny",
        "mate": "matte",
        
        # Common words
        "de": "of",
        "con": "with",
        "para": "for",
        "y": "and",
        "o": "or"
    }
    
    def __init__(self):
        """Initialize the market adapter"""
        self._adaptation_count = 0
        self._error_count = 0
        
    async def adapt_product(self, product: Dict[str, Any], market_id: str) -> Dict[str, Any]:
        """
        Adapt a product for a specific market.
        
        This is the MAIN method that should be called for all product adaptations.
        It handles currency conversion, translation, and market-specific transformations.
        
        Args:
            product: Product dictionary to adapt
            market_id: Target market ID (US, ES, MX, CO)
            
        Returns:
            Adapted product dictionary with original values preserved
            
        Raises:
            MarketAdapterError: If adaptation fails
        """
        try:
            # Validate market
            if market_id not in self.MARKETS:
                raise MarketAdapterError(f"Unknown market: {market_id}")
            
            market_config = self.MARKETS[market_id]
            
            # Clone product to avoid mutations
            adapted = product.copy()
            
            # Track adaptation
            self._adaptation_count += 1
            
            # 1. Currency Conversion
            adapted = await self._adapt_currency(adapted, market_config)
            
            # 2. Text Translation (only for English markets)
            if market_config.language_code == "en":
                adapted = await self._adapt_text(adapted, market_config)
            
            # 3. Market-specific transformations
            adapted = await self._apply_market_rules(adapted, market_config)
            
            # 4. Add metadata
            adapted["market_adapted"] = True
            adapted["adapted_for_market"] = market_id
            adapted["_market_adaptation"] = {
                "adapted": True,
                "market_id": market_id,
                "adapter_version": "2.0.0",
                "timestamp": self._get_timestamp()
            }
            
            # Log successful adaptation
            logger.info(
                f"Product adapted for {market_id}: "
                f"price={adapted.get('price')} {adapted.get('currency')}"
            )
            
            return adapted
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Error adapting product for {market_id}: {e}", exc_info=True)
            
            # Return original with error flag
            error_product = product.copy()
            error_product["market_adapted"] = False
            error_product["_market_adaptation"] = {
                "adapted": False,
                "error": str(e),
                "market_id": market_id
            }
            return error_product
    
    async def _adapt_currency(self, product: Dict[str, Any], market: MarketConfiguration) -> Dict[str, Any]:
        """Convert product price to market currency"""
        if "price" not in product:
            return product
        
        try:
            # Get original price
            original_price = Decimal(str(product["price"]))
            original_currency = product.get("currency", "COP")
            
            # Preserve original values
            product["original_price"] = float(original_price)
            product["original_currency"] = original_currency
            
            # Detect if price is already in COP despite wrong currency label
            if original_price > 1000 and original_currency in ["USD", "EUR"]:
                logger.warning(
                    f"Suspicious price: {original_price} {original_currency}, "
                    f"treating as COP"
                )
                original_currency = "COP"
            
            # Convert if needed
            if original_currency == "COP" and market.currency_code != "COP":
                converted_price = original_price * market.exchange_rate_from_cop
                
                # Round to market decimal places
                quantize_to = Decimal(10) ** -market.decimal_places
                final_price = converted_price.quantize(quantize_to, rounding=ROUND_HALF_UP)
                
                product["price"] = float(final_price)
                product["currency"] = market.currency_code
                
                logger.debug(
                    f"Price converted: {original_price} COP -> "
                    f"{final_price} {market.currency_code}"
                )
            else:
                # Update currency even if no conversion needed
                product["currency"] = market.currency_code
            
            return product
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error converting price: {e}")
            return product
    
    async def _adapt_text(self, product: Dict[str, Any], market: MarketConfiguration) -> Dict[str, Any]:
        """Translate product text fields for English markets"""
        text_fields = ["title", "name", "description", "category"]
        
        for field in text_fields:
            if field in product and product[field]:
                original_text = str(product[field])
                
                # Preserve original
                product[f"original_{field}"] = original_text
                
                # Translate
                translated = self._translate_text(original_text)
                if translated != original_text:
                    product[field] = translated
                    logger.debug(f"Translated {field}: '{original_text}' -> '{translated}'")
        
        return product
    
    @lru_cache(maxsize=1000)
    def _translate_text(self, text: str) -> str:
        """Basic translation using dictionary lookup"""
        if not text:
            return text
        
        # Work with lowercase for matching
        text_lower = text.lower()
        translated = text_lower
        
        # Sort translations by length (longest first) to avoid partial replacements
        sorted_translations = sorted(
            self.TRANSLATIONS.items(),
            key=lambda x: len(x[0]),
            reverse=True
        )
        
        # Apply translations
        for spanish, english in sorted_translations:
            # Use word boundaries for accurate replacement
            pattern = r'\b' + re.escape(spanish) + r'\b'
            translated = re.sub(pattern, english, translated, flags=re.IGNORECASE)
        
        # Preserve original capitalization pattern
        if text != text_lower and translated != text_lower:
            return self._preserve_capitalization(text, translated)
        
        return translated
    
    def _preserve_capitalization(self, original: str, translated: str) -> str:
        """Preserve capitalization pattern from original text"""
        # Title case
        if original.istitle():
            return translated.title()
        
        # ALL CAPS
        if original.isupper():
            return translated.upper()
        
        # Sentence case
        if original and original[0].isupper():
            return translated[0].upper() + translated[1:] if len(translated) > 1 else translated.upper()
        
        return translated
    
    async def _apply_market_rules(self, product: Dict[str, Any], market: MarketConfiguration) -> Dict[str, Any]:
        """Apply market-specific business rules"""
        # Example: US market prefers imperial units
        if market.market_id == "US" and "weight" in product:
            # Convert kg to lbs if needed
            pass
        
        # Example: EU market requires eco labels
        if market.market_id == "ES":
            product["requires_eco_label"] = True
        
        return product
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get adapter performance metrics"""
        return {
            "adaptations_performed": self._adaptation_count,
            "errors_encountered": self._error_count,
            "error_rate": self._error_count / max(self._adaptation_count, 1),
            "supported_markets": list(self.MARKETS.keys()),
            "translation_terms": len(self.TRANSLATIONS)
        }
    
    async def validate_adaptation(self, product: Dict[str, Any]) -> bool:
        """
        Validate that a product has been properly adapted.
        
        This method should be used in tests and monitoring to ensure
        adaptations are actually happening, not just being flagged.
        """
        if "_market_adaptation" not in product:
            return False
        
        adaptation_meta = product["_market_adaptation"]
        
        # Check required fields
        if not adaptation_meta.get("adapted"):
            return False
        
        # For adapted products, verify transformations
        if adaptation_meta.get("market_id") != "CO":  # CO doesn't need conversion
            # Should have original price preserved
            if "original_price" not in product:
                logger.warning("Adaptation flagged but no original_price preserved")
                return False
            
            # Price should be different from original
            if product.get("price") == product.get("original_price"):
                logger.warning("Adaptation flagged but price unchanged")
                return False
        
        return True


# Singleton instance
_adapter_instance = None


def get_market_adapter() -> MarketAdapter:
    """Get the singleton market adapter instance"""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = MarketAdapter()
    return _adapter_instance


# Convenience function for backwards compatibility
async def adapt_product_for_market(product: Dict[str, Any], market_id: str) -> Dict[str, Any]:
    """
    Adapt a product for a specific market.
    
    This function provides backwards compatibility with existing code.
    """
    adapter = get_market_adapter()
    return await adapter.adapt_product(product, market_id)


# Testing utilities
async def test_adapter():
    """Test the market adapter with sample data"""
    adapter = get_market_adapter()
    
    test_product = {
        "id": "test-123",
        "title": "Aros Grandes de Oro con Piedras Azules",
        "price": 59990,
        "currency": "COP",
        "description": "Hermosos aros de oro con piedras azules brillantes"
    }
    
    print("🧪 Testing Market Adapter")
    print("=" * 60)
    print(f"Original: {test_product}")
    print("\nAdaptations:")
    
    for market_id in ["US", "ES", "MX", "CO"]:
        adapted = await adapter.adapt_product(test_product.copy(), market_id)
        
        print(f"\n{market_id}:")
        print(f"  Price: {adapted.get('price')} {adapted.get('currency')}")
        print(f"  Title: {adapted.get('title')}")
        
        if adapted.get('original_price'):
            print(f"  Original: {adapted.get('original_price')} {adapted.get('original_currency')}")
        
        # Validate adaptation
        is_valid = await adapter.validate_adaptation(adapted)
        print(f"  Valid: {'✅' if is_valid else '❌'}")
    
    print(f"\nMetrics: {adapter.get_metrics()}")


if __name__ == "__main__":
    # Run test when executed directly
    import asyncio
    asyncio.run(test_adapter())
