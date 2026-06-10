# src/api/core/kb_contextualizer.py
"""
KB Contextualizer — Adaptive KB Responses via Claude Haiku
============================================================

PROBLEM THIS SOLVES (BUG #1):
    "¿Qué métodos de pago aceptan?" and "¿Puedo pagar con mi Mastercard?"
    both classify as sub_intent=policy_payment and therefore return the
    SAME generic KB document verbatim.  The second query carries a specific
    entity ("Mastercard") that the generic document may or may not address
    directly — returning it unchanged gives a bad conversational experience.

SOLUTION ARCHITECTURE (Opción C from design session 25/03/2026):
    1. Rule-based specificity check (<1ms, free):
       Detect whether the user query contains named entities or constraints
       that go BEYOND the sub_intent label — brand names, payment providers,
       specific timeframes, carrier names, country names, product attributes.
       This is the "query has more info than its sub_intent" criterion.

    2. If specific: Claude Haiku call (async, ~300ms):
       Pass (query, kb_document) to Haiku with a tight prompt.
       Haiku reads the document and answers the specific question directly.
       max_tokens=250 — enough for 2-3 focused sentences.

    3. If generic: return kb_document as-is (zero added latency).
       This path covers ~70-80% of INFORMATIONAL queries.

WHY NOT THE ML MODEL (sklearn):
    The existing TF-IDF + Logistic Regression model classifies
    INFORMATIONAL vs TRANSACTIONAL only (see metadata.json: classes:
    ["INFORMATIONAL", "TRANSACTIONAL"]).  It has no concept of entity
    specificity, sub_intents, or named entities within a query.
    Extending it would require full retraining with a new labeling scheme.
    The rule-based heuristic delivers the same decision in <1ms with zero
    infrastructure changes and is interpretable/testable.

COST PROFILE:
    - Generic queries (no entities): 0 Claude calls, 0 added cost.
    - Specific queries (~20-30% of INFORMATIONAL): 1 Haiku call.
      At $0.25/1M input + $1.25/1M output tokens, a 400-token call ≈ $0.0001.
      At 1,000 KB calls/day with 25% specificity → ~$0.025/day (~$0.75/month).

ADDING NEW ENTITY PATTERNS:
    Each sub_intent has a list of compiled regex patterns in
    _ENTITY_PATTERNS_BY_SUB_INTENT.  To add a new sub_intent or new entity
    type within an existing one, add a compiled regex to the relevant list.
    The function has_specific_entities() iterates them and returns True on
    first match — order doesn't matter for correctness, but put the most
    common matches first for performance.

Author: Retail Recommender Team
Date: 25/03/2026
"""

import re
import asyncio
import logging
import os
import time
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    # Importacion solo para type hints — evita dependencias circulares en runtime.
    # SizeProfile vive en mcp_services; importarla aqui en runtime crearia un
    # ciclo: mcp_services → core → mcp_services. TYPE_CHECKING = False en runtime.
    from src.api.mcp_services.size_profile.service import SizeProfile

from src.api.core.llm_client import UnifiedLLMClient
from src.api.core.claude_config import LFM_KB_CONFIG, GPT4O_MINI_FALLBACK_CONFIG

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# ENTITY PATTERN REGISTRY
# ═══════════════════════════════════════════════════════════════════════
# Pre-compiled regex patterns, grouped by InformationalSubIntent value.
# Each pattern captures at least one named entity or specific constraint
# that exceeds what the sub_intent label alone expresses.
#
# Design rules:
#   • Patterns match ENTITIES, not generic topic keywords.
#     BAD:  r"\bpago\b"   (that's just the sub_intent keyword itself)
#     GOOD: r"\bmastercard\b"  (a specific card brand)
#   • Use word boundaries (\b) to avoid partial matches.
#   • re.IGNORECASE everywhere — users type in mixed case.
#   • Keep patterns tight — false positives waste Claude calls.

_ENTITY_PATTERNS_BY_SUB_INTENT: Dict[str, list] = {

    # ── policy_payment ───────────────────────────────────────────────
    # Trigger: user names a specific payment method, provider, or plan
    "policy_payment": [
        # Card brands / networks
        re.compile(r"\b(mastercard|visa|amex|american\s*express|discover|maestro)\b", re.IGNORECASE),
        # Digital wallets and payment platforms
        re.compile(r"\b(paypal|apple\s*pay|google\s*pay|mercado\s*pago|oxxo|spei|bizum|klarna|afterpay|affirm)\b", re.IGNORECASE),
        # Installment / financing mentions
        re.compile(r"\b(cuotas?|meses?\s*sin\s*intereses?|msi|diferido|financiación|financiacion)\b", re.IGNORECASE),
        # Specific card type mentions
        re.compile(r"\b(tarjeta\s*(de\s*)?(débito|credito|crédito|prepago|prepaid))\b", re.IGNORECASE),
        re.compile(r"\b(debit|credit)\s*card\b", re.IGNORECASE),
        # Crypto / alternative
        re.compile(r"\b(crypto|bitcoin|ethereum|criptomoneda)\b", re.IGNORECASE),
    ],

    # ── policy_shipping ──────────────────────────────────────────────
    # Trigger: user asks about a specific carrier, country, or timeline
    "policy_shipping": [
        # Carriers / couriers
        re.compile(r"\b(fedex|dhl|ups|usps|correos?|estafeta|redpack|trego|amazon\s*logistics)\b", re.IGNORECASE),
        # Shipping destinations (countries/regions beyond "my address")
        re.compile(r"\b(internacional|international|extranjero|abroad|outside|canada|mexico|españa|spain|usa|united\s*states)\b", re.IGNORECASE),
        # Specific timeframe questions ("within X days", "before X")
        re.compile(r"\b(en\s*\d+\s*días?|within\s*\d+\s*days?|antes\s*del\s*\d+|before\s*\w+\s*\d+)\b", re.IGNORECASE),
        # Express / overnight options
        re.compile(r"\b(express|overnight|same.?day|mismo.?día|urgente|next.?day|24\s*h)\b", re.IGNORECASE),
        # Pickup / store-related
        re.compile(r"\b(recoger|pickup|recog(er|ido)|en\s*tienda|in.?store)\b", re.IGNORECASE),
    ],

    # ── policy_return ────────────────────────────────────────────────
    # Trigger: user specifies a product type, condition, or exact duration
    "policy_return": [
        # Specific product categories in return context
        re.compile(r"\b(ropa\s*interior|underwear|swimsuit|traje\s*de\s*baño|swimwear)\b", re.IGNORECASE),
        re.compile(r"\b(joyas?|joyería|jewelry|reloj|watch|perfume)\b", re.IGNORECASE),
        re.compile(r"\b(outlet|rebaja|sale|clearance)\b", re.IGNORECASE),
        # Condition descriptors
        re.compile(r"\b(usado|usad[ao]|used|abierto|opened|sin\s*etiqueta|no\s*tag)\b", re.IGNORECASE),
        # Specific day counts ("30 días", "15 days", etc.)
        re.compile(r"\b\d+\s*días?\b", re.IGNORECASE),
        re.compile(r"\b\d+\s*days?\b", re.IGNORECASE),
        # Gift / recipient scenarios
        re.compile(r"\b(regalo|gift|gifted)\b", re.IGNORECASE),
    ],

    # ── policy_warranty ──────────────────────────────────────────────
    # Trigger: user names a specific brand, defect type, or repair term
    "policy_warranty": [
        # Named brands (placeholder — add real brands your store carries)
        re.compile(r"\b(nike|adidas|zara|h&m|mango|levi's|levis|tommy\s*hilfiger)\b", re.IGNORECASE),
        # Specific defect descriptions
        re.compile(r"\b(costura|seam|zipper|cremallera|sole|suela|sole\s*coming\s*off|se\s*descosió)\b", re.IGNORECASE),
        # Repair vs replacement distinction
        re.compile(r"\b(reparar|repair|reemplazar|replace|arreglar|fix)\b", re.IGNORECASE),
    ],

    # ── product_sizing ───────────────────────────────────────────────
    # Trigger: user provides a measurement or mentions a specific brand/fit
    "product_sizing": [
        # Numeric measurements
        re.compile(r"\b\d+\s*(cm|centímetros?|inches?|pulgadas?|\")\b", re.IGNORECASE),
        # Body measurements context ("mido 170", "I'm 5'8")
        re.compile(r"\b(mido|mide|altura|height|talla\s*\d+)\b", re.IGNORECASE),
        # Specific size labels beyond the generic "talla/size"
        re.compile(r"\b(s/m|m/l|talla\s*(unica|única|free\s*size))\b", re.IGNORECASE),
        # Brand-specific sizing systems
        re.compile(r"\b(us\s*size|eu\s*size|uk\s*size|talla\s*(europea|americana))\b", re.IGNORECASE),
    ],

    # ── product_material ─────────────────────────────────────────────
    # Trigger: user asks about a specific material component or allergy concern
    "product_material": [
        # Named materials (beyond generic "material/fabric")
        re.compile(r"\b(seda|silk|lino|linen|cachemira|cashmere|viscosa|viscose|lyocell|tencel|neopreno|neoprene)\b", re.IGNORECASE),
        # Allergy / skin sensitivity
        re.compile(r"\b(alergia|alérgico|alérgica|allergic|sensibilidad|sensitive\s*skin|piel\s*sensible)\b", re.IGNORECASE),
        # Specific blend percentages
        re.compile(r"\b\d+\s*%\s*(algodón|cotton|polyester|poliéster)\b", re.IGNORECASE),
    ],

    # ── product_care ─────────────────────────────────────────────────
    # Trigger: user asks about a specific care action beyond "wash"
    "product_care": [
        # Specific wash types
        re.compile(r"\b(lavadora|washing\s*machine|a\s*mano|hand\s*wash|en\s*seco|dry\s*clean)\b", re.IGNORECASE),
        # Temperature specifics
        re.compile(r"\b(\d+\s*°?\s*(c|celsius|f|fahrenheit|grados?))\b", re.IGNORECASE),
        # Specific care symbols / issues
        re.compile(r"\b(centrifug|spin|decolor|bleach|fade|destiñe|planchar|iron|temperatura)\b", re.IGNORECASE),
    ],

    # ── account_orders ───────────────────────────────────────────────
    # Trigger: user references a specific order ID or order status
    "account_orders": [
        # Order IDs (alphanumeric codes)
        re.compile(r"\b([A-Z]{2,5}-?\d{4,10}|\d{6,12})\b"),
        # Specific statuses beyond generic "my order"
        re.compile(r"\b(cancelado|cancelar|cancelled|cancel|perdido|lost|dañado|damaged|equivocado|wrong)\b", re.IGNORECASE),
        # Reference to a specific product in order context
        re.compile(r"\b(vestido|pantalon|pantalón|camisa|zapato|zapatos|bolso|abrigo)\s*(que|I|que\s*pedí)\b", re.IGNORECASE),
    ],
}

# Flat set of sub_intents that have entity patterns registered.
# Used for fast O(1) membership check before iterating patterns.
_SUB_INTENTS_WITH_PATTERNS = frozenset(_ENTITY_PATTERNS_BY_SUB_INTENT.keys())


# ═══════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS — Personal Sizing Context
# ═══════════════════════════════════════════════════════════════════════

# Patrones que indican que el usuario busca una recomendacion PERSONAL de talla,
# no informacion generica sobre guias de tallas.
# Distinguen "\u00bfque talla me recomiendas?" (personal) de "\u00bfcomo mido mi talla?" (generica).
# Se compilan una vez a nivel de modulo para reutilizarlos en cada request.
_PERSONAL_SIZING_PATTERNS = [
    # Pronombres de primera persona + talla
    re.compile(
        r"\b(mi\s*talla|talla\s*me|me\s*queda|que\s*talla\s*(tomo|uso|necesito|pido|elijo|recomiendas?)|cuanto\s*me|como\s*me|si\s*mi\s*talla)\b",
        re.IGNORECASE,
    ),
    # Preguntas directas al asistente sobre talla personal
    re.compile(
        r"\b(recomiend[ao]s?\s*(una\s*)?talla|deberia\s*(pedir|elegir|comprar)\s*(una\s*)?talla|que\s*talla\s*(me|seria)\b)",
        re.IGNORECASE,
    ),
    # Ingles
    re.compile(
        r"\b(what\s*size\s*(should|do|would)|my\s*size|size\s*for\s*me|recommend\s*a\s*size)\b",
        re.IGNORECASE,
    ),
    # Pregunta de disponibilidad en talla propia
    re.compile(
        r"\b(hay\s*en\s*mi\s*talla|queda\s*en\s*mi\s*talla|disponible\s*en\s*mi\s*talla)\b",
        re.IGNORECASE,
    ),
]

# Mapeo de product_type (Shopify) a nombre legible en espanol para el prompt.
# Solo incluye los tipos que tienen sizing relevante. Fallback: usar el raw type.
_PRODUCT_TYPE_LABELS: Dict[str, str] = {
    "VESTIDOS LARGOS":   "vestidos largos",
    "VESTIDOS CORTOS":   "vestidos cortos",
    "VESTIDOS MIDIS":    "vestidos midi",
    "NOVIAS LARGOS":     "vestidos de novia",
    "NOVIAS CORTOS":     "vestidos de novia cortos",
    "ENTERITOS LARGOS":  "enteritos largos",
    "ENTERITOS CORTOS":  "enteritos cortos",
    "TOPS":              "tops",
    "BRALETTES":         "bralettes",
    "FALDAS":            "faldas",
    "PANTALONES":        "pantalones",
    "LEGGINGS":          "leggings",
    "CONJUNTOS FALDAS":  "conjuntos",
    "CONJUNTOS PANTALONES": "conjuntos",
    "ZAPATOS":           "zapatos",
    "LENCERIA":          "lenceria",
    "ACCESORIOS":        "accesorios",
}

# Grupos de talla: mapea product_type a categoria de tallas
# (mismo mapa que en SizeProfileService.CATEGORY_GROUPS)
_PRODUCT_TYPE_TO_SIZE_GROUP: Dict[str, str] = {
    "VESTIDOS LARGOS":   "VESTIDOS",
    "VESTIDOS CORTOS":   "VESTIDOS",
    "VESTIDOS MIDIS":    "VESTIDOS",
    "NOVIAS LARGOS":     "VESTIDOS",
    "NOVIAS CORTOS":     "VESTIDOS",
    "NOVIAS MIDIS":      "VESTIDOS",
    "ENTERITOS LARGOS":  "ENTERITOS",
    "ENTERITOS CORTOS":  "ENTERITOS",
    "TOPS":              "TOPS",
    "BRALETTES":         "TOPS",
    "FALDAS":            "FALDAS",
    "PANTALONES":        "PANTALONES",
    "LEGGINGS":          "PANTALONES",
    "CONJUNTOS FALDAS":  "CONJUNTOS",
    "CONJUNTOS PANTALONES": "CONJUNTOS",
}


def _is_personal_sizing_query(query: str) -> bool:
    """True si la query indica que el usuario busca su talla personal.

    Distingue entre:
      personal:  "\u00bfQu\u00e9 talla me recomiendas?" → True   (enriquecimiento con historial)
      generica:  "\u00bfC\u00f3mo mido mi talla?"          → False  (documento gen\u00e9rico de KB)

    Usa los patrones pre-compilados en _PERSONAL_SIZING_PATTERNS.
    Latencia: <1ms (pure Python regex sobre string corto).

    Args:
        query: La query del usuario en texto plano.

    Returns:
        True si la query es una pregunta personal de talla.
    """
    for pattern in _PERSONAL_SIZING_PATTERNS:
        if pattern.search(query):
            logger.debug("[sizing] Personal sizing query detected: '%s'", query[:60])
            return True
    return False


def _build_sizing_context_block(
    size_profile: "SizeProfile",
    product_context: Optional[Dict[str, Any]],
    language: str = "es",
) -> str:
    """Construye el bloque de contexto de tallas para el prompt de Haiku.

    Lee el size_profile y el producto actual y genera un fragmento de texto
    que se inyecta en el prompt de generate_contextual_answer() antes del
    documento de KB. Esto permite a Haiku responder con datos reales del
    historial del usuario en lugar del documento gen\u00e9rico.

    Si no hay talla identificable para la categor\u00eda del producto actual,
    retorna un string vacio para que el llamador no inserte nada.

    Args:
        size_profile:    SizeProfile con datos del historial del cliente.
        product_context: Dict con product_type, title, etc. Puede ser None.
        language:        "es" o "en" — controla el idioma del bloque.

    Returns:
        Bloque de texto para incrustar en el prompt, o "" si no hay datos \u00fatiles.
    """
    if not size_profile or not size_profile.has_data():
        return ""

    # Determinar la categor\u00eda del producto actual y su grupo de tallas
    product_type_raw = ""
    product_title = ""
    if product_context:
        product_type_raw = (product_context.get("product_type") or "").upper().strip()
        product_title = product_context.get("title") or ""

    # Mapear product_type a size_group (VESTIDOS CORTOS → VESTIDOS)
    size_group = _PRODUCT_TYPE_TO_SIZE_GROUP.get(product_type_raw, product_type_raw)

    # Obtener talla recomendada con su confianza
    # best_size_for_category() ya aplica el umbral m\u00ednimo de confianza (0.4)
    recommended_size = (
        size_profile.best_size_for_category(size_group)
        or size_profile.best_size_for_category(product_type_raw)
    )

    if not recommended_size:
        # No hay talla con confianza suficiente para esta categor\u00eda
        # → no enriquecer el prompt, el KB gen\u00e9rico es la mejor respuesta disponible
        logger.debug(
            "[sizing] No confident size for product_type='%s' (group='%s') — skipping enrichment",
            product_type_raw,
            size_group,
        )
        return ""

    # Confianza de la categor\u00eda espec\u00edfica (m\u00e1s precisa que la global)
    cat_confidence = (
        size_profile.confidence_by_category.get(size_group)
        or size_profile.confidence_by_category.get(product_type_raw)
        or size_profile.confidence
    )
    confidence_pct = int(cat_confidence * 100)
    orders_n = size_profile.orders_analyzed

    # Etiqueta legible de la categor\u00eda
    category_label = (
        _PRODUCT_TYPE_LABELS.get(size_group)
        or _PRODUCT_TYPE_LABELS.get(product_type_raw)
        or (size_group.lower() if size_group else "productos")
    )

    # Nombre corto del producto para el prompt (truncado para no inflar tokens)
    product_label = f'"{ product_title[:50]}"' if product_title else f"este {category_label}"

    logger.info(
        "[sizing] Building sizing context block: size=%s category=%s confidence=%d%% orders=%d",
        recommended_size,
        category_label,
        confidence_pct,
        orders_n,
    )

    if language == "es":
        return (
            f"\n--- Historial de tallas del cliente ---\n"
            f"En compras anteriores de {category_label}, este cliente suele pedir "
            f"talla {recommended_size} "
            f"(basado en {orders_n} pedido(s), confianza {confidence_pct}%).\n"
            f"Producto consultado: {product_label}.\n"
            f"Usa este dato como primera referencia. Si la talla {recommended_size} "
            f"es la adecuada para este producto seg\u00fan la gu\u00eda de tallas, conf\u00edrmalo. "
            f"Si hay alguna advertencia (ej. el modelo es oversize, talla peque\u00f1o), "
            f"ind\u00edcalo brevemente.\n"
            f"--- Fin historial ---\n"
        )
    else:
        return (
            f"\n--- Customer size history ---\n"
            f"In previous purchases of {category_label}, this customer usually orders "
            f"size {recommended_size} "
            f"(based on {orders_n} order(s), {confidence_pct}% confidence).\n"
            f"Product being consulted: {product_label}.\n"
            f"Use this as the primary reference. If size {recommended_size} is appropriate "
            f"for this product per the size guide, confirm it. If there is any caveat "
            f"(e.g. the model runs large or small), mention it briefly.\n"
            f"--- End history ---\n"
        )


# ═══════════════════════════════════════════════════════════════════════
# F-05: STOCK ALERT BLOCK BUILDER
# ═══════════════════════════════════════════════════════════════════════

# Umbrales para clasificar el nivel de urgencia de stock.
# Deben coincidir con los de shopify_client._calculate_stock_alert_level().
# Se definen localmente para evitar importar shopify_client desde kb_contextualizer,
# lo que crearía una dependencia circular (core → integrations → core).
_STOCK_LOW_THRESHOLD = 5      # 1–5 unidades: alerta "low"
_STOCK_CRITICAL_THRESHOLD = 2  # 1–2 unidades: alerta "critical"


def _build_stock_alert_block(
    product_context: Dict[str, Any],
    language: str = "es",
) -> str:
    """
    Construye un bloque de contexto de urgencia de stock para el prompt de Claude.

    Se activa cuando `product_context["stock_alert"]` es "low" o "critical"
    y hay al menos una variante con stock positivo <= umbral.

    El bloque instruye a Claude a mencionar la disponibilidad limitada de
    forma natural — sin asustar al usuario, pero siendo honesto sobre
    la escasez. El tono es conversacional, no alarmista.

    F-05 Design notes:
      - La función NO genera alerta si stock_alert es None o "" (stock normal).
      - Si variant_inventory está vacío (GraphQL falló), retorna "".
      - Solo incluye variantes con stock bajo Y positivo (qty 1-umbral).
        Variantes agotadas (qty=0) se omiten: el mensaje es de escasez, no
        de agotamiento.
      - Bilingue: ES y EN. Default ES (mercado principal AI-Shoppings).
      - Se posiciona ANTES del documento KB en el user_prompt, igual que
        el bloque de sizing context, para que Claude lo lea primero.

    Args:
        product_context: Dict con 'stock_alert', 'variant_inventory' y 'title'.
        language:        "es" o "en" — controla el idioma del bloque.

    Returns:
        Bloque de texto para incrustar en el prompt, o "" si no hay alerta.
    """
    stock_alert = product_context.get("stock_alert")
    variant_inventory = product_context.get("variant_inventory", {})

    # Sin alerta o sin datos de inventario → bloque vacío (sin cambio en el prompt)
    if not stock_alert or not variant_inventory:
        return ""

    # Filtrar variantes con stock bajo positivo (1 <= qty <= umbral).
    # Excluir qty=0 (agotadas) — no son "pocas unidades", son "sin stock".
    low_stock_variants = {
        size: qty
        for size, qty in variant_inventory.items()
        if 0 < qty <= _STOCK_LOW_THRESHOLD
    }

    if not low_stock_variants:
        return ""

    is_critical = stock_alert == "critical"

    if language == "es":
        if len(low_stock_variants) == 1:
            # Una sola variante con stock bajo — mensaje específico
            size, qty = next(iter(low_stock_variants.items()))
            unit = "unidad" if qty == 1 else "unidades"
            header = (
                "\u26a0\ufe0f STOCK CR\u00cdTICO"
                if is_critical
                else "\u26a0\ufe0f STOCK LIMITADO"
            )
            return (
                f"\n--- {header} ---\n"
                f"Solo quedan {qty} {unit} disponible{'s' if qty > 1 else ''} "
                f"en talla {size}.\n"
                f"Si el usuario pregunta por este producto o por disponibilidad, "
                f"menciona la disponibilidad limitada de forma natural y cercana, "
                f"sin alarmar. Ejemplo: 'te cuento que la talla {size} solo tiene "
                f"{qty} {unit} en este momento'.\n"
                f"--- Fin alerta ---\n"
            )
        else:
            # Varias variantes con stock bajo — listar las más críticas
            # Ordenar por cantidad ascendente para mostrar las más escasas primero
            sorted_variants = sorted(low_stock_variants.items(), key=lambda x: x[1])
            lines = [f"{size}: {qty} ud." for size, qty in sorted_variants]
            header = (
                "\u26a0\ufe0f STOCK CR\u00cdTICO EN VARIAS TALLAS"
                if is_critical
                else "\u26a0\ufe0f STOCK LIMITADO EN VARIAS TALLAS"
            )
            return (
                f"\n--- {header} ---\n"
                f"Disponibilidad limitada: {', '.join(lines)}.\n"
                f"Si es relevante en la conversación, menciona que quedan pocas "
                f"unidades de forma natural, sin hacer el mensaje urgente de forma "
                f"artificial.\n"
                f"--- Fin alerta ---\n"
            )
    else:  # English
        if len(low_stock_variants) == 1:
            size, qty = next(iter(low_stock_variants.items()))
            unit = "unit" if qty == 1 else "units"
            header = "\u26a0\ufe0f CRITICAL STOCK" if is_critical else "\u26a0\ufe0f LOW STOCK"
            return (
                f"\n--- {header} ---\n"
                f"Only {qty} {unit} left in size {size}.\n"
                f"If the user asks about this product or availability, naturally "
                f"mention the limited stock in a friendly tone (not alarming). "
                f"Example: 'just so you know, size {size} only has {qty} {unit} right now'.\n"
                f"--- End alert ---\n"
            )
        else:
            sorted_variants = sorted(low_stock_variants.items(), key=lambda x: x[1])
            lines = [f"{size}: {qty} units" for size, qty in sorted_variants]
            header = (
                "\u26a0\ufe0f CRITICAL STOCK IN MULTIPLE SIZES"
                if is_critical
                else "\u26a0\ufe0f LOW STOCK IN MULTIPLE SIZES"
            )
            return (
                f"\n--- {header} ---\n"
                f"Limited availability: {', '.join(lines)}.\n"
                f"Naturally mention limited availability if relevant, "
                f"without creating artificial urgency.\n"
                f"--- End alert ---\n"
            )


# ═══════════════════════════════════════════════════════════════════════
# F-05: AVAILABILITY CONTEXT BLOCK BUILDER
# ═══════════════════════════════════════════════════════════════════════


def _build_availability_context_block(
    product_context: Dict[str, Any],
    size_profile=None,
    language: str = "es",
) -> str:
    """
    Construye un bloque de contexto de disponibilidad de variantes para el prompt.

    Se activa cuando NO hay `stock_alert` (stock normal o datos no disponibles),
    pero sí hay información de variantes en `product_context`.

    Complementa a `_build_stock_alert_block()` para cubrir los tres estados:
      - stock_alert=critical/low  → _build_stock_alert_block() maneja esto
      - stock normal/sin datos    → ESTA función: informa qué tallas hay disponibles
      - sin variantes (agotado)   → ESTA función: informa que está agotado

    Propósito: dar a Claude contexto específico del producto actual para que
    pueda responder queries de disponibilidad con información real en lugar
    de una respuesta genérica del documento KB.

    Design notes:
      - Se usa SOLO cuando `stock_alert is None` (no duplicar con el bloque de alerta).
      - Si `variant_inventory` está vacío (GraphQL falló o agotado),
        informa al usuario que el sistema no pudo obtener la disponibilidad.
      - Incluye la talla habitual del cliente (F-02) si está disponible,
        para que Claude pueda responder "Sí, está disponible en tu talla".
      - Bilingüe: ES y EN.

    Args:
        product_context: Dict con 'variant_inventory', 'title', 'stock_alert', 'tags'.
        size_profile:    Opcional. SizeProfile del cliente para personalización de talla.
        language:        "es" o "en".

    Returns:
        Bloque de texto para incrustar en el prompt, o "" si no hay información útil.
    """
    # Esta función solo actua cuando NO hay alerta de stock.
    # Si hay stock_alert, _build_stock_alert_block() ya está cubriendo el caso.
    if product_context.get("stock_alert"):
        return ""

    variant_inventory = product_context.get("variant_inventory", {})
    product_title = product_context.get("title", "este producto")
    product_type = (product_context.get("product_type") or "").lower()

    # Clasificar el estado del stock
    in_stock_variants = {k: v for k, v in variant_inventory.items() if v > 0}
    out_of_stock_variants = {k: v for k, v in variant_inventory.items() if v == 0}
    all_out_of_stock = bool(variant_inventory) and not in_stock_variants
    no_inventory_data = not variant_inventory  # GraphQL fallo o producto sin variantes

    # Talla habitual del cliente (F-02 integration)
    # Solo se usa si size_profile tiene datos confiables para este tipo de producto.
    customer_size = None
    if size_profile and product_context.get("product_type"):
        product_type_upper = (product_context.get("product_type") or "").upper().strip()
        SIZE_GROUP_MAP = {
            "VESTIDOS LARGOS": "VESTIDOS", "VESTIDOS CORTOS": "VESTIDOS",
            "VESTIDOS MIDIS": "VESTIDOS", "ENTERITOS LARGOS": "ENTERITOS",
            "ENTERITOS CORTOS": "ENTERITOS", "TOPS": "TOPS", "BRALETTES": "TOPS",
            "FALDAS": "FALDAS", "PANTALONES": "PANTALONES", "LEGGINGS": "PANTALONES",
        }
        size_group = SIZE_GROUP_MAP.get(product_type_upper, product_type_upper)
        if hasattr(size_profile, 'best_size_for_category'):
            customer_size = (
                size_profile.best_size_for_category(size_group)
                or size_profile.best_size_for_category(product_type_upper)
            )

    if language == "es":
        if all_out_of_stock:
            # Todas las variantes tienen qty=0 — producto agotado
            sizes_str = ", ".join(sorted(variant_inventory.keys()))
            block = (
                f"\n--- DISPONIBILIDAD DEL PRODUCTO ---\n"
                f"Producto: {product_title[:60]}\n"
                f"Estado: AGOTADO en todas las tallas ({sizes_str}).\n"
                f"Informa al usuario que este producto no está disponible actualmente.\n"
                f"Sugírele ver productos similares disponibles.\n"
                f"--- Fin disponibilidad ---\n"
            )
        elif in_stock_variants:
            # Stock normal — informar qué tallas hay
            sizes_available = sorted(in_stock_variants.keys())
            sizes_str = ", ".join(sizes_available)
            # Verificar si la talla del cliente está disponible
            customer_size_available = customer_size and customer_size in in_stock_variants
            personal_note = ""
            if customer_size_available:
                personal_note = (
                    f"La talla habitual de este cliente es {customer_size} "
                    f"y ESTÁ disponible en este producto. "
                    f"Confírmalo en la respuesta.\n"
                )
            elif customer_size:
                personal_note = (
                    f"La talla habitual de este cliente es {customer_size} "
                    f"pero NO está disponible. "
                    f"Sugírele la talla más cercana disponible.\n"
                )
            block = (
                f"\n--- DISPONIBILIDAD DEL PRODUCTO ---\n"
                f"Producto: {product_title[:60]}\n"
                f"Tallas disponibles: {sizes_str}.\n"
                f"{personal_note}"
                f"Confirma al usuario la disponibilidad de forma clara y directa.\n"
                f"--- Fin disponibilidad ---\n"
            )
        else:
            # Sin datos de inventario (GraphQL falló o producto sin variantes configuradas)
            # Dar contexto del nombre/tipo del producto para que Claude pueda responder
            # con información parcial del documento KB.
            block = (
                f"\n--- CONTEXTO DEL PRODUCTO ---\n"
                f"Producto consultado: {product_title[:60]}\n"
                f"Tipo: {product_type or 'desconocido'}.\n"
                f"No se pudo obtener el inventario en tiempo real. "
                f"Responde basandote en la información del documento y ofrece "
                f"al usuario contactar con soporte para confirmar disponibilidad.\n"
                f"--- Fin contexto ---\n"
            )
    else:  # English
        if all_out_of_stock:
            sizes_str = ", ".join(sorted(variant_inventory.keys()))
            block = (
                f"\n--- PRODUCT AVAILABILITY ---\n"
                f"Product: {product_title[:60]}\n"
                f"Status: OUT OF STOCK in all sizes ({sizes_str}).\n"
                f"Let the user know this product is currently unavailable.\n"
                f"Suggest similar available products.\n"
                f"--- End availability ---\n"
            )
        elif in_stock_variants:
            sizes_available = sorted(in_stock_variants.keys())
            sizes_str = ", ".join(sizes_available)
            customer_size_available = customer_size and customer_size in in_stock_variants
            personal_note = ""
            if customer_size_available:
                personal_note = (
                    f"The customer's usual size is {customer_size} "
                    f"and it IS available in this product. Confirm this in your response.\n"
                )
            elif customer_size:
                personal_note = (
                    f"The customer's usual size is {customer_size} "
                    f"but it is NOT available. Suggest the nearest available size.\n"
                )
            block = (
                f"\n--- PRODUCT AVAILABILITY ---\n"
                f"Product: {product_title[:60]}\n"
                f"Available sizes: {sizes_str}.\n"
                f"{personal_note}"
                f"Clearly confirm availability to the user.\n"
                f"--- End availability ---\n"
            )
        else:
            block = (
                f"\n--- PRODUCT CONTEXT ---\n"
                f"Product queried: {product_title[:60]}\n"
                f"Type: {product_type or 'unknown'}.\n"
                f"Real-time inventory data is unavailable. "
                f"Answer using the document and suggest the user contact support "
                f"to confirm availability.\n"
                f"--- End context ---\n"
            )

    logger.info(
        "F-05 availability_context_block built "
        "(handle=%s in_stock=%d out_of_stock=%d no_data=%s)",
        product_context.get("handle", "?"),
        len(in_stock_variants),
        len(out_of_stock_variants),
        no_inventory_data,
    )
    return block


# ═══════════════════════════════════════════════════════════════════════
# FIX (21/04/2026): MATERIAL CONTEXT BLOCK BUILDER
# ═══════════════════════════════════════════════════════════════════════


def _build_material_context_block(
    product_context: Dict[str, Any],
    language: str = "es",
) -> str:
    """
    Construye un bloque de contexto de material para el prompt de Claude.

    Se activa cuando el sub_intent es 'product_material' y hay product_context
    disponible (usuario en pagina de producto). Inyecta información relevante
    del producto (tipo, tags, titulo) para que Claude pueda responder con
    detalles especificos sobre el material de este producto en particular.

    Design notes:
      - Usa tags del producto (que suelen incluir material: "algodon", "seda")
      - Incluye el tipo de producto para contexto (ej. "VESTIDOS", "TOPS")
      - El bloque es informativo, no reemplaza el documento KB.
      - Degradacion graceful: si no hay tags utiles, solo muestra el titulo.

    Args:
        product_context: Dict con 'title', 'product_type', 'tags', etc.
        language:        "es" o "en".

    Returns:
        Bloque de texto para incrustar en el prompt, o "" si no hay info util.
    """
    if not product_context:
        return ""

    product_title = product_context.get("title", "este producto")
    product_type = product_context.get("product_type", "")
    tags = product_context.get("tags", []) or []

    # Filtrar tags relevantes para materiales (case-insensitive)
    material_keywords = {
        "algodon", "cotton", "seda", "silk", "lino", "linen",
        "viscosa", "viscose", "polyester", "poliester", "poliéster",
        "lyocell", "tencel", "modal", "lana", "wool", "cachemira",
        "cashmere", "sintetico", "sintético", "synthetic", "cuero",
        "leather", "denim", "mezclilla", "nylon", "licra", "lycra",
        "spandex", "elastano", "elastano", "rayon", "acetato",
    }
    relevant_tags = [
        tag for tag in tags
        if any(kw.lower() in tag.lower() for kw in material_keywords)
    ]

    if language == "es":
        block_lines = ["\n--- CONTEXTO DEL PRODUCTO ---"]
        block_lines.append(f"Producto: {product_title[:60]}")
        if product_type:
            block_lines.append(f"Tipo: {product_type}")
        if relevant_tags:
            block_lines.append(f"Tags relacionados con material: {', '.join(relevant_tags[:5])}")
        block_lines.append(
            "Responde específicamente sobre el material/composición de este producto "
            "basándote en el documento. Si el documento no menciona materiales específicos "
            "para este tipo de producto, indícalo claramente."
        )
        block_lines.append("--- Fin contexto ---\n")
    else:
        block_lines = ["\n--- PRODUCT CONTEXT ---"]
        block_lines.append(f"Product: {product_title[:60]}")
        if product_type:
            block_lines.append(f"Type: {product_type}")
        if relevant_tags:
            block_lines.append(f"Material-related tags: {', '.join(relevant_tags[:5])}")
        block_lines.append(
            "Answer specifically about the material/composition of this product "
            "based on the document. If the document does not mention specific materials "
            "for this product type, state so clearly."
        )
        block_lines.append("--- End context ---\n")

    return "\n".join(block_lines)


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API — Specificity Check
# ═══════════════════════════════════════════════════════════════════════

def has_specific_entities(query: str, sub_intent: Optional[str]) -> bool:
    """
    Determine whether a query contains named entities or constraints that
    exceed what the sub_intent label alone expresses.

    This is the gating function: if it returns False, the KB document is
    returned verbatim (zero added latency, zero cost). If it returns True,
    the caller should invoke `generate_contextual_answer()` to get a
    Claude-adapted response.

    Args:
        query:      The raw user query string.
        sub_intent: The InformationalSubIntent value (e.g. "policy_payment").
                    If None or not in the registry, returns False.

    Returns:
        True  → query has specific entities; contextualisation adds value.
        False → query is generic; return KB doc as-is.

    Performance:
        ~0.1–0.5ms (pure Python regex on a short string, pre-compiled
        patterns, short-circuit on first match).

    Examples:
        >>> has_specific_entities("¿qué métodos de pago aceptan?", "policy_payment")
        False   # generic question, no named entity
        >>> has_specific_entities("¿puedo pagar con Mastercard?", "policy_payment")
        True    # "Mastercard" is a named entity
        >>> has_specific_entities("¿en cuántos días llega?", "policy_shipping")
        False   # asks about time, but no named carrier or country
        >>> has_specific_entities("¿mandan con DHL?", "policy_shipping")
        True    # "DHL" is a specific carrier
    """
    if not sub_intent or sub_intent not in _SUB_INTENTS_WITH_PATTERNS:
        return False

    patterns = _ENTITY_PATTERNS_BY_SUB_INTENT[sub_intent]
    for pattern in patterns:
        if pattern.search(query):
            logger.debug(
                "🎯 Specificity detected: sub_intent=%s, pattern=%s, query='%s'",
                sub_intent,
                pattern.pattern[:40],
                query[:60],
            )
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API — Contextual Answer Generation
# ═══════════════════════════════════════════════════════════════════════

async def generate_contextual_answer(
    query: str,
    kb_document: str,
    sub_intent: str,
    language: str = "es",
    anthropic_client=None,
    size_profile: Optional["SizeProfile"] = None,
    product_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Ask Claude Haiku to answer `query` using `kb_document` as its knowledge
    source.  Returns a focused, conversational response (2-3 sentences).

    This is intentionally a THIN wrapper: the prompt is minimal, Haiku is
    fast, and max_tokens is capped at 250 so the response is always terse.
    We do NOT pass conversation history — this is a one-shot KB lookup, not
    a multi-turn conversation.

    Args:
        query:            The exact user query string.
        kb_document:      The raw KB document text retrieved for sub_intent.
        sub_intent:       The InformationalSubIntent value (used in system prompt).
        language:         "es" or "en" — controls the response language.
                          Normalised to base code: "en-US" → "en".
        anthropic_client: AsyncAnthropic instance.  If None, this function
                          attempts to retrieve the application singleton from
                          ServiceFactory.  Callers should always pass it when
                          available to avoid an extra import.
        size_profile:     Optional SizeProfile with customer's size history.
                          If provided and relevant to sub_intent (e.g., product_sizing),
                          enriches the prompt with personalized size recommendations.
        product_context:  Optional Dict with product metadata (product_type, title, etc.).
                          Used alongside size_profile to build personalized context.

    Returns:
        Contextualised answer string, or None if the call fails.
        On None, the caller must fall back to returning kb_document as-is.

    Timeout:
        3.0 seconds hard limit via asyncio.wait_for().  Haiku typically
        responds in 300–700ms for a 250-token response; 3.0s gives 4x
        headroom without blocking the request pipeline.
    """
    start_time = time.time()

    # Normalise language to base code
    lang_key = (language or "es").split("-")[0].lower()
    response_language = "español" if lang_key == "es" else "English"

    # Retrieve Claude client if not injected
    if anthropic_client is None:
        try:
            from src.api.factories.service_factory import ServiceFactory
            mcp_engine = await ServiceFactory.get_mcp_recommender()
            if mcp_engine is not None:
                anthropic_client = mcp_engine.claude
        except Exception as client_e:
            logger.error("❌ KB Contextualizer: Could not obtain Anthropic client: %s", client_e)
            return None

    if anthropic_client is None:
        logger.warning("⚠️ KB Contextualizer: No Anthropic client available — skipping contextualisation")
        return None

    # FIX (10/06/2026): max_tokens se define aqui solo para controlar la longitud
    # del system/user prompt compartido entre LFM, GPT-4o-mini y Claude.
    # claude_config ya NO se inicializa al inicio de la funcion porque dispara
    # claude_config_effective en cada request aunque Claude nunca sea invocado
    # (GPT-4o-mini o LFM ya habrán retornado antes de llegar al bloque Claude).
    #
    # Regla: 250 tokens para respuestas conversacionales; 500 para product_sizing
    # (tablas de medidas necesitan más espacio para presentar tallas completas).
    # Estos valores son constantes independientes del modelo activo.
    max_tokens = 500 if sub_intent == "product_sizing" else 250

    # model_name y model_config se resuelven mas abajo, dentro del bloque Claude
    # (legacy path), solo si LFM y GPT-4o-mini no pudieron responder.
    model_name = None   # asignado dentro del bloque Claude si se llega a el
    model_config = None  # idem — evita NameError si el bloque Claude no se ejecuta

    # System prompt — short, role-focused, language-locked
    # Kept under ~80 tokens to minimise time-to-first-token.
    # FIX (19/04/2026 — BUG-SIZING-KB): For product_sizing, relaxed the "2-3 sentences" constraint.
    # The KB sizing document contains measurement tables and specific size data.
    # LFM2.5-1.2B was generating vague summaries ("Follow the guide") because the
    # conciseness instruction prevented it from presenting the actual table content.
    # product_sizing needs a longer, more detailed response to be useful.

    # ── Solución B (UX): Instrucción para mencionar producto en respuestas ─────
    # Cuando hay product_context (usuario en página de producto), instruir al modelo
    # a mencionar el nombre del producto para que el usuario sepa que la respuesta
    # es específica a ese item.
    product_mention_instruction = ""
    if product_context and product_context.get("title"):
        product_mention_instruction = (
            f"IMPORTANT: The customer is asking about the product '{product_context['title']}'. "
            f"ALWAYS mention this product name at the start of your answer so they know "
            f"you're responding about this specific item. "
        )
        logger.info(
            "Solución B: Adding product mention instruction for KB contextualization "
            "(product='%s', sub_intent='%s')",
            product_context['title'],
            sub_intent
        )
    # ── Fin Solución B ────────────────────────────────────────────────────────

    if sub_intent == "product_sizing":
        system_prompt = (
            f"You are a helpful customer support assistant for an e-commerce fashion store. "
            f"You help customers find their correct size using the sizing guide provided. "
            f"Reply in {response_language}. "
            f"{product_mention_instruction}"
            f"If the document contains a size chart or measurements, PRESENT THE ACTUAL DATA "
            f"(sizes, measurements in cm) so the customer can directly find their size. "
            f"Be specific and practical: tell the customer exactly how to measure and which size to pick. "
            f"You may use up to 5 sentences or a short list if needed to present the sizing information clearly."
        )
    else:
        system_prompt = (
            f"You are a helpful customer support assistant for an e-commerce fashion store. "
            f"You answer customer questions ONLY using the policy document provided. "
            f"Reply in {response_language}. Be concise: 2–3 sentences maximum. "
            f"{product_mention_instruction}"
            f"If the document does not contain the specific information asked, say so clearly and briefly."
        )

    # Build optional sizing context block if size_profile and product_context are provided
    sizing_context = ""
    if size_profile and product_context:
        # Check if this sub_intent is related to sizing
        if sub_intent == "product_sizing":
            sizing_context = _build_sizing_context_block(
                size_profile=size_profile,
                product_context=product_context,
                language=lang_key,
            )
            if sizing_context:
                # FIX (12/04/2026): Loggear la confianza por categoria del producto
                # actual, no la confianza global (que es baja por diseno en catalogos
                # multi-categoria). La confianza global mostraba 37% aunque la categoria
                # relevante tuviera 100%.
                _pt = (product_context.get("product_type") or "").upper().strip()
                _cat_group = _PRODUCT_TYPE_TO_SIZE_GROUP.get(_pt, _pt) or "GENERAL"
                _cat_conf = size_profile.confidence_by_category.get(
                    _cat_group, size_profile.confidence
                )
                logger.info(
                    "✨ F-02 Informational SubIntent: Adding personalized sizing context to prompt "
                    "(category=%s confidence_cat=%d%% confidence_global=%d%%)",
                    _cat_group,
                    int(_cat_conf * 100),
                    int(size_profile.confidence * 100),
                )

    # User prompt — sizing context (if any), then document, then specific question.
    # Placing the document before the question is the standard RAG pattern
    # and helps Haiku locate the relevant section quickly.
    # Sizing context is prepended if available to give Haiku customer's size history first.
    #
    # F-05 (13/04/2026): stock_alert_context is inserted after sizing_context and before
    # the KB document. If no alert is active, the string is "" (no-op).
    stock_alert_context = ""
    if product_context and product_context.get("stock_alert"):
        stock_alert_context = _build_stock_alert_block(
            product_context=product_context,
            language=lang_key,
        )
        if stock_alert_context:
            logger.info(
                "⚠️ F-05 Stock Alert: Adding stock alert block to prompt "
                "(alert=%s handle=%s variants=%s)",
                product_context["stock_alert"],
                product_context.get("handle", "?"),
                list(product_context.get("variant_inventory", {}).keys()),
            )

    # F-05 (14/04/2026): Para product_availability sin stock_alert activo,
    # inyectar el bloque de disponibilidad que informa a Claude sobre el estado
    # real del inventario (stock normal, agotado, o sin datos).
    #
    # Este bloque y stock_alert_context son mutuamente excluyentes:
    # _build_availability_context_block() devuelve "" si hay stock_alert.
    # Resultado: exactamente uno de los dos bloques estara activo en el prompt.
    availability_context = ""
    if sub_intent == "product_availability" and product_context:
        availability_context = _build_availability_context_block(
            product_context=product_context,
            size_profile=size_profile,
            language=lang_key,
        )

    # FIX (21/04/2026): Contexto específico de material para product_material.
    # Inyecta información del producto actual (tags, tipo) para que Claude pueda
    # responder con detalles específicos sobre el material de este producto.
    material_context = ""
    if sub_intent == "product_material" and product_context:
        material_context = _build_material_context_block(
            product_context=product_context,
            language=lang_key,
        )

    # ── Solución B (UX): Nota sobre el contexto del producto ─────────────────
    # Agregar contexto explícito sobre el producto que el usuario está viendo
    product_context_note = ""
    if product_context and product_context.get("title"):
        product_context_note = (
            f"\nNote: The customer is viewing the product '{product_context['title']}'. "
            f"Your answer should specifically address this product.\n\n"
        )
    # ── Fin Solución B ───────────────────────────────────────────────────────

    user_prompt = (
        f"{sizing_context}"
        f"{stock_alert_context}"        # F-05: urgencia de stock bajo/critico
        f"{availability_context}"        # F-05: disponibilidad normal/agotado
        f"{material_context}"            # FIX: contexto de material del producto
        f"Policy document:\n\"\"\"\n{kb_document}\n\"\"\"\n\n"
        f"{product_context_note}"
        f"Customer question: {query}\n\n"
        f"Answer the customer's specific question based only on the document above."
    )

    # ── RUTA LFM — Fase B (activa si LFM_KB_ENABLED=true) ──────────────────
    # Lee la variable directamente de os.environ — nunca via lru_cache.
    # Razón: lru_cache congela el valor al momento del import; en Cloud Run
    # el secret llega después del import y el flag quedaría siempre False.
    # Patrón idéntico al usado en mcp_personalization_engine.py (21/03/2026).
    _lfm_kb_enabled = os.environ.get('LFM_KB_ENABLED', 'false').lower() == 'true'
    # DEBUG FLAG: cuando FORCE_GPT4O_MINI_FALLBACK=true, salta LFM en ambas rutas
    # (MCP + KB) para testear el fallback GPT-4o-mini con el stack completo activo.
    # Patron identico al implementado en mcp_personalization_engine.py (10/06/2026).
    _force_gpt_fallback_kb = os.environ.get('FORCE_GPT4O_MINI_FALLBACK', 'false').lower() == 'true'
    if _force_gpt_fallback_kb:
        logger.info('FORCE_GPT4O_MINI_FALLBACK=true: skipping LFM KB, routing to GPT-4o-mini fallback')
    elif _lfm_kb_enabled:
        try:
            # Se crea una instancia de UnifiedLLMClient en cada llamada.
            # Esto es deliberado: el client es un objeto ligero (AsyncOpenAI wrapper).
            # La alternativa (singleton de módulo) requeriría manejo de estado
            # y complicaría el rollback. El overhead es ~0.1ms, negligible.
            _lfm_kb_client = UnifiedLLMClient(
                provider=LFM_KB_CONFIG['provider'],
                model=LFM_KB_CONFIG['model'],
                max_tokens=min(LFM_KB_CONFIG['max_tokens'], 250),  # misma cota que Haiku
                temperature=LFM_KB_CONFIG['temperature'],
            )
            resp = await asyncio.wait_for(
                _lfm_kb_client.complete(system_prompt, user_prompt),
                timeout=5.0,  # LFM2.5-1.2B es más lento que Haiku; 5s da margen
            )
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "✅ KB Contextualizer (LFM): answer in %.0fms (%d chars) model=%s sub_intent=%s",
                elapsed_ms, len(resp.content), resp.model, sub_intent,
            )
            return resp.content
        except Exception as lfm_e:
            # Cualquier fallo de LFM (timeout, API error, etc.) cae aqui.
            # El sistema continua hacia GPT-4o-mini (si activo) o Claude sin interrumpir.
            logger.warning(
                "KB Contextualizer: LFM call failed, falling back to GPT-4o-mini / Claude: %s", lfm_e
            )
            # La ejecucion continua hacia el bloque GPT-4o-mini a continuacion

    # -- RUTA GPT-4o-mini (fallback KB cuando LFM falla, Fase B) ------------------
    # Lee la variable directamente de os.environ (patron identico a LFM_KB_ENABLED).
    # Prerequisito: OPENROUTER_API_KEY configurado (compartido con LFM).
    _gpt4o_mini_kb_enabled = os.environ.get('GPT4O_MINI_FALLBACK_ENABLED', 'false').lower() == 'true'
    if _gpt4o_mini_kb_enabled:
        try:
            # UnifiedLLMClient es ligero (AsyncOpenAI wrapper). Instancia por llamada,
            # mismo razonamiento que el bloque LFM de arriba.
            _gpt4o_mini_kb_client = UnifiedLLMClient(
                provider=GPT4O_MINI_FALLBACK_CONFIG['provider'],
                model=GPT4O_MINI_FALLBACK_CONFIG['model'],
                max_tokens=min(GPT4O_MINI_FALLBACK_CONFIG['max_tokens'], max_tokens),
                temperature=0.3,   # temperatura baja: respuesta KB factual y determinista
            )
            resp = await asyncio.wait_for(
                _gpt4o_mini_kb_client.complete(system_prompt, user_prompt),
                timeout=5.0,  # mismo que LFM; GPT-4o-mini tipicamente <500ms
            )
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "KB Contextualizer (GPT-4o-mini): answer in %.0fms (%d chars) model=%s sub_intent=%s",
                elapsed_ms, len(resp.content), resp.model, sub_intent,
            )
            return resp.content
        except Exception as gpt4o_mini_e:
            # Fallo de GPT-4o-mini: cae hacia Claude Haiku como ultimo recurso.
            logger.warning(
                "KB Contextualizer: GPT-4o-mini call failed, falling back to Claude: %s", gpt4o_mini_e
            )

    # ── RUTA CLAUDE (legacy — solo si LFM y GPT-4o-mini no pudieron responder) ──
    # Se resuelve el modelo Claude solo aqui, no al inicio de la funcion,
    # para evitar que claude_config_effective se dispare en cada KB request
    # cuando Claude nunca llega a ser invocado.
    try:
        from src.api.core.claude_config import get_claude_config_service
        _kb_claude_config = get_claude_config_service()
        _kb_model_config = _kb_claude_config.get_model_config()
        model_name = _kb_model_config.model_name
        # Respetar el max_tokens ya calculado arriba (250 o 500 segun sub_intent)
    except Exception as _cfg_e:
        logger.warning("KB Contextualizer: Could not read claude_config, using Haiku: %s", _cfg_e)
        model_name = "claude-3-haiku-20240307"

    logger.info(
        "🤖 KB Contextualizer (Claude legacy): calling %s for sub_intent=%s, lang=%s",
        model_name, sub_intent, lang_key,
    )

    try:
        response = await asyncio.wait_for(
            anthropic_client.messages.create(
                model=model_name,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=max_tokens,
                temperature=0.3,  # Low temperature: factual, deterministic answers
            ),
            timeout=3.0,  # Hard cap — do not let this block the request pipeline
        )

        answer = response.content[0].text.strip()
        elapsed_ms = (time.time() - start_time) * 1000

        logger.info(
            "✅ KB Contextualizer: answer generated in %.0fms (%d chars)",
            elapsed_ms,
            len(answer),
        )

        return answer

    except asyncio.TimeoutError:
        logger.warning(
            "⏰ KB Contextualizer: Claude timeout (3.0s) for sub_intent=%s — "
            "falling back to generic KB document",
            sub_intent,
        )
        return None

    except Exception as api_e:
        logger.error(
            "❌ KB Contextualizer: Claude API error for sub_intent=%s: %s",
            sub_intent,
            api_e,
            exc_info=True,
        )
        return None