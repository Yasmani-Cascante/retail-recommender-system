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
    
    Only 2 types for simplicity:
    - TRANSACTIONAL: User wants to see/buy products
    - INFORMATIONAL: User wants information (policies, FAQs, etc)
    """
    TRANSACTIONAL = "transactional"
    INFORMATIONAL = "informational"


class InformationalSubIntent(str, Enum):
    """
    Sub-types for informational intents.
    Used to route to correct knowledge base section.
    """
    # Policies
    POLICY_RETURN = "policy_return"
    POLICY_SHIPPING = "policy_shipping"
    POLICY_PAYMENT = "policy_payment"
    
    # Product Information
    PRODUCT_MATERIAL = "product_material"
    PRODUCT_SIZE = "product_size"
    PRODUCT_CARE = "product_care"
    PRODUCT_AVAILABILITY = "product_availability"
    
    # General
    GENERAL_FAQ = "general_faq"
    UNKNOWN = "unknown"


class TransactionalSubIntent(str, Enum):
    """
    Sub-types for transactional intents.
    Currently not used but defined for future expansion.
    """
    PRODUCT_SEARCH = "product_search"
    PRODUCT_VIEW = "product_view"
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