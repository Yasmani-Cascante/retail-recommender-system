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
import time
from typing import Optional, Dict, Any

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

    # Read model config from centralised service
    try:
        from src.api.core.claude_config import get_claude_config_service
        claude_config = get_claude_config_service()
        model_config = claude_config.get_model_config()
        model_name = model_config.model_name
        # Cap at 250 for this use-case regardless of global max_tokens setting.
        # This endpoint needs a focused 2-3 sentence answer, not a full document.
        max_tokens = min(model_config.max_tokens, 250)
    except Exception as cfg_e:
        logger.warning("⚠️ KB Contextualizer: Could not read claude_config, using Haiku defaults: %s", cfg_e)
        model_name = "claude-3-haiku-20240307"
        max_tokens = 250

    # System prompt — short, role-focused, language-locked
    # Kept under ~80 tokens to minimise time-to-first-token.
    system_prompt = (
        f"You are a helpful customer support assistant for an e-commerce fashion store. "
        f"You answer customer questions ONLY using the policy document provided. "
        f"Reply in {response_language}. Be concise: 2–3 sentences maximum. "
        f"If the document does not contain the specific information asked, say so clearly and briefly."
    )

    # User prompt — document first (context), then the specific question.
    # Placing the document before the question is the standard RAG pattern
    # and helps Haiku locate the relevant section quickly.
    user_prompt = (
        f"Policy document:\n\"\"\"\n{kb_document}\n\"\"\"\n\n"
        f"Customer question: {query}\n\n"
        f"Answer the customer's specific question based only on the document above."
    )

    logger.info(
        "🤖 KB Contextualizer: calling %s for sub_intent=%s, lang=%s",
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
