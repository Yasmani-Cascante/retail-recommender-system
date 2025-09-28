"""
MCP Services Domain Models
=========================

Modelos de dominio compartidos entre services.
Diseñados para ser serializables y transferibles entre microservicios.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from enum import Enum

class MarketTier(Enum):
    """Clasificación de mercados para estrategias diferenciadas"""
    TIER_1 = "tier_1"  # US, UK, DE, FR - Mercados premium
    TIER_2 = "tier_2"  # ES, CA, AU - Mercados establecidos  
    TIER_3 = "tier_3"  # MX, BR, IN - Mercados emergentes

@dataclass
class MarketContext:
    """Contexto de mercado - Preparado para ser microservicio independiente"""
    market_id: str
    currency: str
    language: str
    tier: MarketTier
    cultural_preferences: Dict[str, Any]
    regulatory_requirements: Dict[str, Any]
    
    # MCP-specific fields
    conversation_style: str
    ai_personality: str
    local_events: List[str]

@dataclass
class MCPConversationContext:
    """Contexto conversacional específico MCP"""
    session_id: str
    user_intent: Optional[str]
    conversation_history: List[Dict]
    market_context: MarketContext
    personalization_data: Dict[str, Any]

@dataclass
class AdaptationResult:
    """Resultado de adaptación - Con metadata para microservicios"""
    original_product: Dict[str, Any]
    adapted_product: Dict[str, Any]
    adaptations_applied: List[str]
    market_context: MarketContext
    adaptation_metadata: Dict[str, Any]
    service_used: str
    processing_time_ms: float
