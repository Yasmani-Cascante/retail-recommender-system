# src/core/market/adapter.py
"""
Unified Market Adapter - Single Source of Truth
==============================================

This module provides the ONLY market adaptation logic for the entire system.
It handles currency conversion, text translation, and market-specific transformations.

Author: System Architect
Version: 2.1.0
Last Updated: 27/03/2026

CHANGELOG v2.1.0 (27/03/2026):
──────────────────────────────────────────────────────────────────────────────
BUG-CLP-01 — Precio incorrecto para mercado Chile (CL)

  SÍNTOMA:
    - ProductCard mostraba 9,54 € para un producto de 41.495 CLP.
    - El mensaje de Claude mencionaba "414,95 EUR" para el mismo producto.

  CAUSA RAÍZ (dos componentes):
    1. La tabla MARKETS no tenía entrada para "CL" → adapt_product()
       lanzaba MarketAdapterError("Unknown market: CL") y retornaba el
       producto sin adaptación, con price=41495.0 y currency="EUR" (default
       de sanitize_rec_for_frontend). El número 414,95 que menciona Claude
       es simplemente 41495 / 100 (formato de precio con separador de
       centésimas de otro path).
    2. El campo 'exchange_rate_from_cop' del dataclass y la lógica de
       detección de moneda sospechosa asumían que la moneda base de
       Latinoamérica es siempre COP (peso colombiano). Los productos de
       AI-Shoppings tienen precios en CLP (peso chileno, ~0,001 USD/CLP),
       no COP (~0,00025 USD/COP). Aplicar la tasa COP→EUR a un precio CLP
       produce valores ~4.3× demasiado bajos (9,54 € en lugar de ~41 €).

  TASA DE REFERENCIA (27/03/2026):
    1 CLP ≈ 0.00096 EUR (Banco Central de Chile, tipo de cambio de referencia)
    Precio real: 41.495 CLP × 0.00096 ≈ 39,83 EUR
    Shopify muestra: CHF 37 (correcto — CHF/EUR ≈ 1.0)

  FIX (tres cambios):
    A. Se añade "CL" a MARKETS con exchange_rate_from_native = 0.00096 CLP/EUR
       y exchange_rate_from_native = 0.00104 CLP/USD
    B. Se renombra exchange_rate_from_cop → exchange_rate_from_native en el
       dataclass para que el nombre describa correctamente la semántica:
       "tasa desde la moneda nativa del catálogo hacia la moneda destino".
    C. La lógica de detección de moneda sospechosa en _adapt_currency ahora
       usa NATIVE_CURRENCIES[market_id] para saber cuál es la moneda base
       en lugar de hardcodear "COP".

  MARKETS SOPORTADOS DESPUÉS DEL FIX:
    US (USD), ES (EUR), MX (MXN), CL (CLP), CO (COP), default (USD)
──────────────────────────────────────────────────────────────────────────────
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
    """
    Configuración inmutable de mercado.

    Campos:
      market_id              — Código del mercado (US, ES, MX, CL, CO…)
      currency_code          — Moneda destino (USD, EUR, MXN, CLP, COP…)
      language_code          — Idioma principal del mercado
      exchange_rate_from_native — Tasa de conversión DESDE la moneda nativa
                                  del catálogo HACIA currency_code.
                                  Para AI-Shoppings (catálogo en CLP):
                                    ES → CLP/EUR ≈ 0.00096
                                    US → CLP/USD ≈ 0.00104
                                  Para catálogos en COP (mercado Colombia):
                                    CO → COP/COP = 1.0
      native_currency        — Moneda en la que están los precios del catálogo.
                               Esencial para la detección de moneda sospechosa.
      decimal_places         — Decimales del precio destino
    """
    market_id: str
    currency_code: str
    language_code: str
    exchange_rate_from_native: Decimal  # FIX v2.1.0: renombrado desde exchange_rate_from_cop
    native_currency: str = "COP"        # FIX v2.1.0: moneda del catálogo (antes hardcodeado como COP)
    decimal_places: int = 2

    @property
    def currency_symbol(self) -> str:
        symbols = {"USD": "$", "EUR": "€", "MXN": "$", "COP": "$", "CLP": "$"}
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

    v2.1.0 CHANGES:
      - Added "CL" market (Chile, CLP) with correct CLP→EUR/USD rates.
      - Renamed exchange_rate_from_cop → exchange_rate_from_native.
      - Added native_currency field to each MarketConfiguration.
      - _adapt_currency now uses native_currency instead of hardcoded "COP".

    Usage:
        adapter = MarketAdapter()
        adapted_product = await adapter.adapt_product(product, "CL")
    """

    # ── Market configurations — SINGLE SOURCE OF TRUTH ───────────────────────
    #
    # exchange_rate_from_native:
    #   Tasa de conversión DESDE la moneda nativa del catálogo HACIA la
    #   moneda destino del mercado. Para AI-Shoppings el catálogo está
    #   en CLP (Shopify Admin muestra precios en CLP).
    #
    #   Tasas de referencia (27/03/2026, Banco Central de Chile):
    #     1 CLP = 0.00096 EUR  (USD/CLP ≈ 961, EUR/USD ≈ 1.08)
    #     1 CLP = 0.00104 USD
    #     1 CLP = 0.018  MXN
    #
    # ⚠️  IMPORTANTE: Estas tasas son estáticas (hardcoded) como referencia.
    #     Para producción real se recomienda un servicio de tasas live
    #     (ver TODO al final del archivo). Sin embargo, para el rango de
    #     precios típicos de la tienda (~5.000–150.000 CLP), el error por
    #     tasa desactualizada es <<5% — aceptable para v2.1.0.
    #
    MARKETS: Dict[str, MarketConfiguration] = {
        "US": MarketConfiguration(
            market_id="US",
            currency_code="USD",
            language_code="en",
            exchange_rate_from_native=Decimal("0.00104"),  # CLP → USD
            native_currency="CLP",
            decimal_places=2
        ),
        "ES": MarketConfiguration(
            market_id="ES",
            currency_code="EUR",
            language_code="es",
            exchange_rate_from_native=Decimal("0.00096"),  # CLP → EUR
            native_currency="CLP",
            decimal_places=2
        ),
        "MX": MarketConfiguration(
            market_id="MX",
            currency_code="MXN",
            language_code="es",
            exchange_rate_from_native=Decimal("0.018"),    # CLP → MXN
            native_currency="CLP",
            decimal_places=2
        ),
        # ── FIX v2.1.0: Mercado Chile añadido ────────────────────────────────
        # Para el mercado chileno el precio NO se convierte (la moneda nativa
        # del catálogo ya es CLP). exchange_rate_from_native = 1.0.
        "CL": MarketConfiguration(
            market_id="CL",
            currency_code="CLP",
            language_code="es",
            exchange_rate_from_native=Decimal("1.0"),       # CLP → CLP
            native_currency="CLP",
            decimal_places=0  # CLP no usa decimales
        ),
        # ── Mercado Suiza (CH) ──────────────────────────────────────────────
        # v2.2.0 (28/03/2026): Switzerland confirmado en Shopify Admin como mercado activo.
        # Shopify Admin muestra 'switzerland' con flag CH y moneda CHF.
        # CON OPCION A ACTIVA: esta tasa fallback solo actua si market_prices["CH"]
        # no esta disponible en el producto (error GraphQL en el startup).
        # Tasa fallback: 1 CLP ~ 0.00089 CHF (EUR/CHF ~ 0.93, marzo 2026).
        "CH": MarketConfiguration(
            market_id="CH",
            currency_code="CHF",
            language_code="de",
            exchange_rate_from_native=Decimal("0.00089"),
            native_currency="CLP",
            decimal_places=2
        ),
        # ── Mercado Colombia (CO, catálogo en COP) ────────────────────────
        # Se mantiene por compatibilidad. Si en el futuro se usa un catalogo
        # en COP para CO, native_currency="COP" y exchange_rate=1.0 son correctos.
        "CO": MarketConfiguration(
            market_id="CO",
            currency_code="COP",
            language_code="es",
            exchange_rate_from_native=Decimal("1.0"),       # COP -> COP
            native_currency="COP",
            decimal_places=0
        ),
        "default": MarketConfiguration(
            market_id="default",
            currency_code="USD",
            language_code="en",
            exchange_rate_from_native=Decimal("0.00104"),  # CLP -> USD
            native_currency="CLP",
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
            market_id: Target market ID (US, ES, MX, CL, CO)

        Returns:
            Adapted product dictionary with original values preserved

        Raises:
            MarketAdapterError: If adaptation fails
        """
        try:
            # Validar mercado — "CL" ahora está en MARKETS (fix v2.1.0)
            if market_id not in self.MARKETS:
                raise MarketAdapterError(
                    f"Unknown market: {market_id}. "
                    f"Supported markets: {list(self.MARKETS.keys())}"
                )

            market_config = self.MARKETS[market_id]

            # Clonar para no mutar el original
            adapted = product.copy()

            # Contabilizar adaptación
            self._adaptation_count += 1

            # 1. Conversión de moneda
            adapted = await self._adapt_currency(adapted, market_config)

            # 2. Traducción de texto (solo para mercados en inglés)
            if market_config.language_code == "en":
                adapted = await self._adapt_text(adapted, market_config)

            # 3. Reglas específicas del mercado
            adapted = await self._apply_market_rules(adapted, market_config)

            # 4. Metadata de adaptación
            adapted["market_adapted"] = True
            adapted["adapted_for_market"] = market_id
            adapted["_market_adaptation"] = {
                "adapted": True,
                "market_id": market_id,
                "adapter_version": "2.1.0",
                "timestamp": self._get_timestamp()
            }

            logger.info(
                f"Product adapted for {market_id}: "
                f"price={adapted.get('price')} {adapted.get('currency')}"
            )

            return adapted

        except Exception as e:
            self._error_count += 1
            logger.error(f"Error adapting product for {market_id}: {e}", exc_info=True)

            # Retornar original con flag de error (no crashear el pipeline)
            error_product = product.copy()
            error_product["market_adapted"] = False
            error_product["_market_adaptation"] = {
                "adapted": False,
                "error": str(e),
                "market_id": market_id
            }
            return error_product

    async def _adapt_currency(
        self,
        product: Dict[str, Any],
        market: MarketConfiguration
    ) -> Dict[str, Any]:
        """
        Convierte el precio del producto a la moneda del mercado.

        v2.2.0 — Opción A: Shopify como fuente de verdad de precios (28/03/2026)
        ─────────────────────────────────────────────────────────────────────────
        Si el producto tiene el campo 'market_prices' (poblado por
        ShopifyIntegration.get_products_with_shopify_prices() durante el startup),
        se usa directamente el precio de Shopify para el mercado solicitado.
        Shopify calcula las tasas de cambio correctas internamente — no hay
        conversión manual, no hay tasas hardcodeadas, no hay deuda técnica.

        Ejemplo:
          product["market_prices"] = {
              "CL": {"price": 160000.0, "currency": "CLP"},
              "CH": {"price": 153.60,   "currency": "CHF"},  # calculado por Shopify
              "MX": {"price": 2880.0,   "currency": "MXN"},
              "ES": {"price": 153.60,   "currency": "EUR"},
          }
          → adapt_product(product, "CH") usa 153.60 CHF directamente.
          → adapt_product(product, "ES") usa 153.60 EUR directamente.

        Fallback (retrocompatibilidad):
          Si 'market_prices' no existe o no tiene el mercado pedido, se
          aplica la conversión manual con tasas hardcodeadas (comportamiento
          anterior, preservado para productos cargados antes de la Opción A).

        FIX v2.1.0 — Cambios respecto a v2.0.0:
          • El campo 'exchange_rate_from_native' ahora describe la tasa desde
            la moneda nativa del catálogo (market.native_currency) en lugar
            de asumir siempre COP.
          • La detección de moneda sospechosa usa market.native_currency para
            determinar qué moneda "real" tiene el precio cuando el campo
            'currency' del producto está ausente o es incorrecto.
        """
        # ── OPCIÓN A: Precio autorizado por Shopify ───────────────────────────
        # Si el producto tiene market_prices (cargados via GraphQL en el startup),
        # usar el precio Shopify para este mercado sin ninguna conversión manual.
        market_prices = product.get("market_prices")
        if market_prices and isinstance(market_prices, dict):
            market_price_data = market_prices.get(market.market_id)
            if market_price_data and isinstance(market_price_data, dict):
                shopify_amount = market_price_data.get("price", 0)
                shopify_currency = market_price_data.get("currency", market.currency_code)
                if shopify_amount and float(shopify_amount) > 0:
                    # Precio verificado por Shopify — usar directamente
                    product["price"] = float(shopify_amount)
                    product["currency"] = shopify_currency
                    product["_price_source"] = "shopify_graphql"
                    logger.debug(
                        f"[Opción A] Market {market.market_id}: "
                        f"price={shopify_amount} {shopify_currency} (Shopify source)"
                    )
                    return product
            # Si el mercado no está en market_prices, fallback a conversión manual
            logger.debug(
                f"[Opción A] Market {market.market_id} not in market_prices, "
                f"falling back to manual conversion"
            )

        if "price" not in product:
            return product

        try:
            # ── Paso 1: Obtener y validar el valor del precio ─────────────────
            price_value = product.get("price")

            if price_value is None or price_value == "":
                logger.warning(
                    f"Invalid price (None/empty) for product "
                    f"{product.get('id', 'unknown')}: {price_value}"
                )
                product["currency"] = market.currency_code
                product["price_unavailable"] = True
                product["_price_validation"] = "none_or_empty"
                return product

            # ── Paso 2: Limpiar string ────────────────────────────────────────
            price_str = str(price_value).strip()

            # ── Paso 3: Detectar valores no numéricos comunes ─────────────────
            non_numeric_values = [
                "N/A", "n/a", "NA", "na", "TBD", "tbd",
                "Free", "free", "FREE", "Gratis", "gratis",
                "Unavailable", "unavailable", "-", "--", "---"
            ]
            if price_str in non_numeric_values:
                logger.warning(
                    f"Non-numeric price for product "
                    f"{product.get('id', 'unknown')}: '{price_str}'"
                )
                product["currency"] = market.currency_code
                product["price_special"] = price_str
                product["price"] = 0.00
                product["_price_validation"] = "non_numeric"
                return product

            if not price_str:
                logger.warning(
                    f"Empty price string for product "
                    f"{product.get('id', 'unknown')}"
                )
                product["currency"] = market.currency_code
                product["price_unavailable"] = True
                product["_price_validation"] = "empty_string"
                return product

            # ── Paso 4: Convertir a Decimal ───────────────────────────────────
            try:
                original_price = Decimal(price_str)
                if original_price < 0:
                    logger.warning(
                        f"Negative price for product "
                        f"{product.get('id', 'unknown')}: {original_price}"
                    )
                    product["currency"] = market.currency_code
                    product["price"] = 0.00
                    product["_price_validation"] = "negative"
                    return product

            except (ValueError, TypeError) as e:
                logger.error(
                    f"Cannot convert price to Decimal for product "
                    f"{product.get('id', 'unknown')}: '{price_str}' — "
                    f"{type(e).__name__}: {e}"
                )
                product["currency"] = market.currency_code
                product["price_conversion_failed"] = True
                product["price_original_value"] = price_str
                product["_price_validation"] = "conversion_failed"
                return product

            # ── Paso 5: Determinar la moneda de origen ────────────────────────
            #
            # FIX v2.1.0: Ya no se hardcodea "COP" como default.
            # Se usa market.native_currency (la moneda en que está el catálogo).
            #
            # Para AI-Shoppings:
            #   • El catálogo de Shopify tiene precios en CLP.
            #   • product.get("currency") puede ser None, "CLP", o incluso
            #     "USD"/"EUR" si algún path no lo limpió.
            #   • Si el precio es > 1000 y currency es USD o EUR → precio CLP
            #     mal etiquetado (la heurística de magnitud es válida para CLP).
            #
            product_currency = product.get("currency", market.native_currency)

            # Heurística de magnitud: precio alto etiquetado con moneda fuerte
            # → probablemente es la moneda nativa del catálogo mal etiquetada.
            # Umbral 1000: USD/EUR >1000 son raros para este tipo de moda;
            # CLP/COP >1000 son la norma.
            if original_price > Decimal("1000") and product_currency in ("USD", "EUR", "GBP"):
                logger.warning(
                    f"Suspicious price: {original_price} {product_currency} "
                    f"→ treating as {market.native_currency} for product "
                    f"{product.get('id', 'unknown')}"
                )
                product_currency = market.native_currency

            # Preservar valores originales para auditoría
            product["original_price"] = float(original_price)
            product["original_currency"] = product_currency
            product["_price_validation"] = "success"

            # ── Paso 6: Convertir si es necesario ─────────────────────────────
            if (product_currency == market.native_currency
                    and market.currency_code != market.native_currency):
                # Conversión: moneda nativa del catálogo → moneda destino del mercado
                converted_price = original_price * market.exchange_rate_from_native

                # Redondear según las convenciones del mercado
                quantize_to = Decimal(10) ** -market.decimal_places
                final_price = converted_price.quantize(quantize_to, rounding=ROUND_HALF_UP)

                product["price"] = float(final_price)
                product["currency"] = market.currency_code

                logger.info(
                    f"Price converted: {original_price} {product_currency} → "
                    f"{final_price} {market.currency_code} "
                    f"(rate: {market.exchange_rate_from_native}) "
                    f"for product {product.get('id', 'unknown')}"
                )

            else:
                # Sin conversión necesaria:
                # • Mercado local (CL: CLP→CLP)
                # • Precio ya en la moneda destino
                product["currency"] = market.currency_code
                logger.debug(
                    f"No conversion needed for product "
                    f"{product.get('id', 'unknown')}: "
                    f"{original_price} {product_currency} → {market.currency_code}"
                )

            return product

        except Exception as e:
            # Catch-all: retornar sin adaptación para no crashear el pipeline
            logger.error(
                f"Unexpected error converting price for product "
                f"{product.get('id', 'unknown')}: {e}",
                exc_info=True
            )
            product["currency"] = market.currency_code if hasattr(market, 'currency_code') else "USD"
            product["_price_validation"] = "unexpected_error"
            product["_price_error"] = str(e)
            return product

    async def _adapt_text(
        self,
        product: Dict[str, Any],
        market: MarketConfiguration
    ) -> Dict[str, Any]:
        """Translate product text fields for English markets"""
        text_fields = ["title", "name", "description", "category"]

        for field in text_fields:
            if field in product and product[field]:
                original_text = str(product[field])
                product[f"original_{field}"] = original_text

                translated = self._translate_text(original_text)
                if translated != original_text:
                    product[field] = translated
                    logger.debug(
                        f"Translated {field}: '{original_text}' → '{translated}'"
                    )

        return product

    @lru_cache(maxsize=1000)
    def _translate_text(self, text: str) -> str:
        """Basic translation using dictionary lookup"""
        if not text:
            return text

        text_lower = text.lower()
        translated = text_lower

        sorted_translations = sorted(
            self.TRANSLATIONS.items(),
            key=lambda x: len(x[0]),
            reverse=True
        )

        for spanish, english in sorted_translations:
            pattern = r'\b' + re.escape(spanish) + r'\b'
            translated = re.sub(pattern, english, translated, flags=re.IGNORECASE)

        if text != text_lower and translated != text_lower:
            return self._preserve_capitalization(text, translated)

        return translated

    def _preserve_capitalization(self, original: str, translated: str) -> str:
        """Preserve capitalization pattern from original text"""
        if original.istitle():
            return translated.title()
        if original.isupper():
            return translated.upper()
        if original and original[0].isupper():
            return (
                translated[0].upper() + translated[1:]
                if len(translated) > 1
                else translated.upper()
            )
        return translated

    async def _apply_market_rules(
        self,
        product: Dict[str, Any],
        market: MarketConfiguration
    ) -> Dict[str, Any]:
        """Apply market-specific business rules"""
        if market.market_id == "US" and "weight" in product:
            # TODO: Convert kg to lbs
            pass

        if market.market_id == "ES":
            product["requires_eco_label"] = True

        if market.market_id == "CL":
            # Para el mercado local chileno: el precio ya está en CLP.
            # Marcamos el producto para que el frontend sepa que no hubo
            # conversión y puede mostrar el precio original de Shopify.
            product["is_local_market"] = True

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
            "translation_terms": len(self.TRANSLATIONS),
            "adapter_version": "2.1.0"
        }

    async def validate_adaptation(self, product: Dict[str, Any]) -> bool:
        """
        Validate that a product has been properly adapted.
        Used in tests and monitoring.

        v2.2.0 (29/03/2026) — Opcion A: soporte para _price_source='shopify_graphql'
        ─────────────────────────────────────────────────────────────────────────────
        Con Opcion A activa, _adapt_currency() retorna en el bloque Shopify antes de
        setear 'original_price'. La validacion previa rechazaba todos los productos
        Opcion A (excepto CL/CO) porque 'original_price' no existia.

        Nuevo flujo de validacion:
          1. Si '_market_adaptation' no existe o adapted=False → invalido.
          2. Si '_price_source' == 'shopify_graphql' → valido: Shopify es la
             fuente de verdad, no hay conversion manual que validar.
          3. Para mercados que NO convierten (CL, CO) → valido sin revisar precio.
          4. Para mercados que SÍ convierten (US, ES, MX, CH) con conversion
             manual (fallback) → verificar que original_price existe y el precio
             cambio (comportamiento anterior preservado).
        """
        if "_market_adaptation" not in product:
            return False

        adaptation_meta = product["_market_adaptation"]
        if not adaptation_meta.get("adapted"):
            return False

        # ── Opcion A: precio procedente de Shopify GraphQL ────────────────────
        # _adapt_currency() setea _price_source='shopify_graphql' cuando usa el
        # bloque Opcion A. No hay original_price ni conversion manual que validar;
        # Shopify ya garantizo el precio correcto para el mercado.
        if product.get("_price_source") == "shopify_graphql":
            logger.debug(
                "[validate_adaptation] Opcion A — price from Shopify GraphQL: valid "
                "(market=%s, price=%s %s)",
                adaptation_meta.get("market_id", "?"),
                product.get("price"),
                product.get("currency", "?")
            )
            return True

        # ── Mercados que no convierten (conversion manual) ────────────────────
        # CL (CLP→CLP) y CO (COP→COP) tienen exchange_rate_from_native=1.0,
        # por lo que el precio no cambia. Omitir la verificacion de precio.
        market_id = adaptation_meta.get("market_id", "")
        if market_id in ("CO", "CL"):  # Estos no convierten
            return True

        # ── Mercados con conversion manual (fallback sin Opcion A) ────────────
        # Para US, ES, MX, CH: verificar que la conversion ocurrio.
        # Si original_price no existe → la adaptacion no siguio el path esperado.
        if "original_price" not in product:
            logger.warning(
                "[validate_adaptation] Adaptation flagged but no original_price "
                "preserved (market=%s). Posible fallo en conversion manual.",
                market_id
            )
            return False

        if product.get("price") == product.get("original_price"):
            logger.warning(
                "[validate_adaptation] Adaptation flagged but price unchanged "
                "(market=%s, price=%s). Verificar tasa de conversion.",
                market_id, product.get("price")
            )
            return False

        return True


# ── Singleton instance ────────────────────────────────────────────────────────
_adapter_instance: Optional[MarketAdapter] = None


def get_market_adapter() -> MarketAdapter:
    """Get the singleton market adapter instance"""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = MarketAdapter()
    return _adapter_instance


# ── Backwards-compatibility wrappers ─────────────────────────────────────────
async def adapt_product_for_market(
    product: Dict[str, Any],
    market_id: str
) -> Dict[str, Any]:
    """Backwards-compatible wrapper. Delegates to MarketAdapter.adapt_product()."""
    adapter = get_market_adapter()
    return await adapter.adapt_product(product, market_id)


# ── Prueba de la conversión (ejecutar directamente para verificar) ────────────
async def _test_clp_conversion():
    """
    Verifica la conversión CLP para el producto de referencia del bug report:
    Vestido Largo Maya Vuelos Fondo Azul/Mostaza — 41.495 CLP
    Shopify muestra CHF 37 (≈ EUR 40 al tipo de cambio 27/03/2026)
    """
    adapter = get_market_adapter()

    product = {
        "id": "debug-41495-clp",
        "title": "Vestido Largo Maya Vuelos Fondo Azul/Mostaza",
        "price": 41495,
        "currency": None,  # Sin campo currency → debe inferirse como CLP
    }

    print("🧪 Test conversión CLP — producto de referencia")
    print("=" * 60)
    print(f"Original: {product['price']} CLP")
    print()

    for market_id in ["CL", "ES", "US", "MX"]:
        adapted = await adapter.adapt_product(product.copy(), market_id)
        original = adapted.get("original_price", product["price"])
        final = adapted.get("price")
        currency = adapted.get("currency")
        valid = await adapter.validate_adaptation(adapted)
        print(
            f"{market_id}: {original} CLP → {final} {currency}  "
            f"{'✅' if valid else '⚠️ no validate'}"
        )

    print()
    print("Resultado esperado (aprox):")
    print("  CL: 41495 CLP (sin conversión)")
    print("  ES: ~39.8 EUR (41495 × 0.00096)")
    print("  US: ~43.2 USD (41495 × 0.00104)")
    print("  MX: ~746.9 MXN (41495 × 0.018)")


if __name__ == "__main__":
    import asyncio
    asyncio.run(_test_clp_conversion())

# ── TODO: Integrar tasas de cambio en tiempo real ────────────────────────────
# Las tasas actuales son estáticas (hardcoded). Para producción a escala:
#
# 1. Añadir servicio CurrencyRateService que consulte una API (Fixer.io,
#    ExchangeRate-API, o el endpoint del Banco Central de Chile:
#    https://si3.bcentral.cl/estadisticas/Principal1/Web/BancoCentralSi/ServicioFTP.htm)
# 2. Cachear en Redis con TTL de 1 hora.
# 3. Inyectar como dependencia en MarketAdapter.__init__().
# 4. Mantener las tasas hardcoded como fallback si la API falla.
