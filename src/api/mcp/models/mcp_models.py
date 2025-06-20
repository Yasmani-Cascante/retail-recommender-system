# src/api/mcp/models/mcp_models.py
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class MarketID(str, Enum):
    """Mercados soportados"""
    US = "US"
    ES = "ES"
    MX = "MX"
    DEFAULT = "default"

class IntentType(str, Enum):
    """Tipos de intención conversacional"""
    PRODUCT_SEARCH = "product_search"
    RECOMMENDATION = "recommendation"
    COMPARE = "compare"
    CART_COMPLEMENT = "cart_complement"
    BUDGET_SEARCH = "budget_search"
    GIFT_SEARCH = "gift_search"
    BROWSE = "browse"
    GENERAL = "general"

class ConversationContext(BaseModel):
    """Contexto de conversación MCP"""
    session_id: str
    user_id: Optional[str] = None
    query: str
    market_id: MarketID = MarketID.DEFAULT
    language: str = "en"
    currency: str = "USD"
    history: List[Dict[str, Any]] = Field(default_factory=list)
    cart_items: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ExtractedIntent(BaseModel):
    """Intención extraída del procesamiento conversacional"""
    primary_intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    category: Optional[str] = None
    budget_range: Optional[Dict[str, float]] = None
    specific_requirements: List[str] = Field(default_factory=list)
    urgency: str = "normal"  # immediate, urgent, normal, flexible
    context_keywords: List[str] = Field(default_factory=list)

class MarketProduct(BaseModel):
    """Producto con información específica del mercado"""
    id: str
    title: str
    localized_title: Optional[str] = None
    description: str
    localized_description: Optional[str] = None
    base_price: float
    market_price: float
    landed_cost: Optional[float] = None  # Precio final con aranceles/impuestos
    currency: str
    availability: bool = True
    available_quantity: int = 0
    shipping_days: int = 7
    restricted: bool = False
    restriction_reason: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    brand: Optional[str] = None
    rating: Optional[float] = Field(ge=0.0, le=5.0, default=None)
    review_count: int = 0

class MarketAwareRecommendation(BaseModel):
    """Recomendación enriquecida con contexto de mercado"""
    product: MarketProduct
    score: float = Field(ge=0.0, le=1.0)
    market_score: float = Field(ge=0.0, le=1.0)
    reason: str
    market_factors: Dict[str, Any] = Field(default_factory=dict)
    viability_score: float = Field(ge=0.0, le=1.0)  # Considera todos los factores
    cultural_adaptation: Optional[Dict[str, Any]] = None
    
class MCPRecommendationRequest(BaseModel):
    """Request para recomendaciones MCP-aware"""
    user_id: str
    session_id: Optional[str] = None
    market_id: MarketID = MarketID.DEFAULT
    product_id: Optional[str] = None
    conversation_context: Optional[ConversationContext] = None
    n_recommendations: int = Field(default=5, ge=1, le=20)
    include_conversation_response: bool = True
    filters: Optional[Dict[str, Any]] = None

class MCPRecommendationResponse(BaseModel):
    """Respuesta de recomendaciones MCP"""
    recommendations: List[MarketAwareRecommendation]
    ai_response: Optional[str] = None  # Respuesta conversacional generada
    metadata: Dict[str, Any] = Field(default_factory=dict)
    market_context: Dict[str, Any] = Field(default_factory=dict)
    conversation_session: Optional[str] = None
    took_ms: float = 0.0

class MarketConfiguration(BaseModel):
    """Configuración completa de un mercado"""
    market_id: MarketID
    name: str
    currency: str
    language: str
    timezone: str
    currency_symbol: str
    decimal_places: int = 2
    scoring_weights: Dict[str, float]
    cache_settings: Dict[str, int]
    localization: Dict[str, Any]
    business_rules: Dict[str, Any]
    ai_prompts: Dict[str, str]
    peak_hours: Dict[str, List[str]]

class CacheKey(BaseModel):
    """Estructura para claves de caché market-aware"""
    prefix: str
    market_id: str
    entity_id: str
    context_hash: Optional[str] = None
    
    def to_string(self) -> str:
        """Convertir a string para Redis"""
        parts = [self.prefix, self.market_id, self.entity_id]
        if self.context_hash:
            parts.append(self.context_hash)
        return ":".join(parts)

class MarketMetrics(BaseModel):
    """Métricas específicas por mercado"""
    market_id: MarketID
    total_requests: int = 0
    conversion_rate: float = 0.0
    average_session_duration: float = 0.0
    top_categories: List[str] = Field(default_factory=list)
    peak_usage_hours: List[str] = Field(default_factory=list)
    cache_hit_ratio: float = 0.0
    average_response_time: float = 0.0
    user_satisfaction_score: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)