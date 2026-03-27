"""
Intent Detection - Type Definitions
Defines all types used in intent detection system.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# INTENT ENUMS
# ═══════════════════════════════════════════════════════════════

class IntentType(str, Enum):
    """
    Primary user intent types.

    - TRANSACTIONAL: User wants to see/buy products
    - INFORMATIONAL: User wants information (policies, FAQs, etc)
    - GREETING: User sends a salutation or conversational opener
                ("Hi!", "Hola", "Buenos días", etc.).
                These require a warm conversational response, NOT products.
                Added 24/03/2026 — BUG #3 fix.
    """
    TRANSACTIONAL = "transactional"
    INFORMATIONAL = "informational"
    GREETING      = "greeting"


class InformationalSubIntent(str, Enum):
    """
    Sub-types for informational intents.
    Used to route to correct knowledge base section.

    ✅ ACTUALIZADO: Incluye TODOS los sub_intents existentes en kb_content
    ✅ SINCRONIZADO: Con páginas de Shopify KB (Sprint 1 + Sprint 2)

    IMPORTANTE — Regla de alineación enum ↔ DB ↔ Shopify:
    -------------------------------------------------------
    Cada valor de este enum DEBE coincidir EXACTAMENTE con:
      1. La columna `sub_intent` en la tabla `kb_contents` (PostgreSQL / Neon)
      2. El metafield `kb.sub_intent` de las páginas de Shopify CMS

    Si hay discrepancia (ej. enum="product_size", DB="product_sizing"),
    el KB retornará 0 resultados para esa clave → el sistema degrada
    silenciosamente a recomendaciones de productos en vez de la respuesta
    correcta, Y los endpoints /kb/stats y /kb/sub-intents mostrarán
    conteos distintos (N vs N+1).

    ❌ NUNCA mantener aliases "legacy" que no tengan contenido en DB.
    ✅ Si Shopify usa "product_sizing", el enum DEBE ser PRODUCT_SIZING = "product_sizing".
    """
    # ── Policies ────────────────────────────────────────────────
    POLICY_RETURN         = "policy_return"
    POLICY_SHIPPING       = "policy_shipping"
    POLICY_PAYMENT        = "policy_payment"
    POLICY_WARRANTY       = "policy_warranty"
    POLICY_PRIVACY        = "policy_privacy"

    # ── Product Information ─────────────────────────────────────
    PRODUCT_MATERIAL      = "product_material"
    # ✅ FIX (2026-03-04): Renombrado de PRODUCT_SIZE="product_size" (alias legacy sin
    #    contenido en DB) a PRODUCT_SIZING="product_sizing" que es el valor real usado
    #    en kb_contents y en los metafields de Shopify.
    #    Impacto: resuelve AttributeError en startup cuando se intentó eliminar,
    #    alinea /kb/stats (DB) con /kb/sub-intents (enum), y permite al KB
    #    responder correctamente queries sobre tallas.
    PRODUCT_SIZING        = "product_sizing"
    PRODUCT_CARE          = "product_care"
    PRODUCT_AVAILABILITY  = "product_availability"

    # ── Account ─────────────────────────────────────────────────
    ACCOUNT_ORDERS        = "account_orders"
    ACCOUNT_MODIFICATIONS = "account_modifications"

    # ── General ─────────────────────────────────────────────────
    GENERAL_FAQ           = "general_faq"
    UNKNOWN               = "unknown"


class TransactionalSubIntent(str, Enum):
    """
    Sub-types for transactional intents.
    Currently not used but defined for future expansion.
    """
    PRODUCT_SEARCH  = "product_search"
    PRODUCT_VIEW    = "product_view"
    PURCHASE_INTENT = "purchase_intent"


# ═══════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class IntentDetectionResult(BaseModel):
    """
    Result of intent detection.
    """
    primary_intent: IntentType = Field(
        ...,
        description="Primary intent detected (TRANSACTIONAL or INFORMATIONAL)"
    )

    sub_intent: Optional[str] = Field(
        None,
        description="Sub-intent for more specific routing"
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0)"
    )

    reasoning: str = Field(
        ...,
        description="Human-readable explanation of why this intent was detected"
    )

    matched_patterns: List[str] = Field(
        default_factory=list,
        description="Patterns that matched (for debugging)"
    )

    product_context: Optional[List[str]] = Field(
        None,
        description="Product categories mentioned (if any)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "primary_intent": "INFORMATIONAL",
                "sub_intent": "policy_return",
                "confidence": 0.95,
                "reasoning": "Question word 'cuál' + keyword 'devolución'",
                "matched_patterns": ["política.*devolución"],
                "product_context": ["VESTIDOS"]
            }
        }


class KnowledgeBaseAnswer(BaseModel):
    """
    Answer from knowledge base.
    """
    answer: str = Field(
        ...,
        description="Markdown-formatted answer"
    )

    sub_intent: InformationalSubIntent = Field(
        ...,
        description="Type of information provided"
    )

    sources: List[str] = Field(
        default_factory=list,
        description="Sources used (for future expansion)"
    )

    related_links: Optional[List[Dict[str, str]]] = Field(
        None,
        description="Related links (title, url)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "## Política de Devoluciones\n\n✅ 30 días...",
                "sub_intent": "policy_return",
                "sources": ["policies/returns.md"],
                "related_links": [
                    {"title": "Guía de Tallas", "url": "/help/sizing"}
                ]
            }
        }