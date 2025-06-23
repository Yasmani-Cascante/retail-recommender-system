# src/api/mcp/models/mcp_models.py
"""
Modelos de datos para MCP (Model Context Protocol) integration.
Define las estructuras de datos para conversaciones y recomendaciones market-aware.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class MarketID(str, Enum):
    """Identificadores de mercados soportados"""
    US = "US"
    SPAIN = "ES"
    MEXICO = "MX"
    CHILE = "CL"
    DEFAULT = "default"

class IntentType(str, Enum):
    """Tipos de intención conversacional"""
    SEARCH = "search"
    RECOMMEND = "recommend"
    COMPARE = "compare"
    PURCHASE = "purchase"
    QUESTION = "question"
    GENERAL = "general"

class ConversationContext(BaseModel):
    """Contexto de conversación MCP"""
    session_id: str = Field(description="ID de sesión de conversación")
    user_id: str = Field(description="ID del usuario")
    query: str = Field(description="Consulta del usuario")
    market_id: str = Field(default="default", description="ID del mercado")
    language: str = Field(default="en", description="Idioma de la conversación")
    intent: Optional[IntentType] = Field(default=None, description="Intención detectada")
    confidence: float = Field(default=0.5, description="Confianza en la intención")
    history: List[Dict] = Field(default_factory=list, description="Historial de conversación")
    
class ProductMCP(BaseModel):
    """Modelo de producto para MCP con localización"""
    id: str = Field(description="ID único del producto")
    title: str = Field(description="Título del producto")
    description: str = Field(default="", description="Descripción del producto")
    localized_title: Optional[str] = Field(default=None, description="Título localizado")
    localized_description: Optional[str] = Field(default=None, description="Descripción localizada")
    price: float = Field(description="Precio base")
    market_price: float = Field(description="Precio adaptado al mercado")
    currency: str = Field(default="USD", description="Moneda del precio")
    images: List[str] = Field(default_factory=list, description="URLs de imágenes")
    category: str = Field(default="", description="Categoría del producto")
    availability: bool = Field(default=True, description="Disponibilidad en el mercado")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata adicional")

class RecommendationMCP(BaseModel):
    """Recomendación MCP con contexto de mercado"""
    product: ProductMCP = Field(description="Producto recomendado")
    market_score: float = Field(description="Puntuación adaptada al mercado")
    viability_score: float = Field(description="Puntuación de viabilidad comercial")
    reason: str = Field(description="Razón de la recomendación")
    market_factors: Dict[str, Any] = Field(default_factory=dict, description="Factores del mercado")
    confidence: float = Field(default=0.8, description="Confianza en la recomendación")

class MCPRecommendationRequest(BaseModel):
    """Request para recomendaciones MCP"""
    user_id: str = Field(description="ID del usuario")
    session_id: Optional[str] = Field(default=None, description="ID de sesión")
    market_id: str = Field(default="default", description="ID del mercado")
    product_id: Optional[str] = Field(default=None, description="ID del producto base")
    conversation_context: Optional[ConversationContext] = Field(default=None, description="Contexto conversacional")
    n_recommendations: int = Field(default=5, ge=1, le=20, description="Número de recomendaciones")
    include_conversation_response: bool = Field(default=False, description="Incluir respuesta conversacional")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Filtros adicionales")

class MCPRecommendationResponse(BaseModel):
    """Respuesta de recomendaciones MCP"""
    recommendations: List[RecommendationMCP] = Field(description="Lista de recomendaciones")
    ai_response: Optional[str] = Field(default=None, description="Respuesta conversacional")
    conversation_session: Optional[str] = Field(default=None, description="ID de sesión conversacional")
    market_context: Dict[str, Any] = Field(default_factory=dict, description="Contexto del mercado")
    intent_analysis: Dict[str, Any] = Field(default_factory=dict, description="Análisis de intención")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata de la respuesta")
    
class MarketConfig(BaseModel):
    """Configuración específica de mercado"""
    id: str = Field(description="ID del mercado")
    name: str = Field(description="Nombre del mercado")
    currency: str = Field(description="Moneda del mercado")
    language: str = Field(description="Idioma principal")
    timezone: str = Field(description="Zona horaria")
    enabled: bool = Field(default=True, description="Si el mercado está habilitado")
    scoring_weights: Dict[str, float] = Field(default_factory=dict, description="Pesos para scoring")
    localization: Dict[str, Any] = Field(default_factory=dict, description="Configuración de localización")
    tax_rate: float = Field(default=0.0, description="Tasa de impuestos")
    shipping_config: Dict[str, Any] = Field(default_factory=dict, description="Configuración de envío")

class MCPAnalyticsEvent(BaseModel):
    """Evento de analytics para MCP"""
    event_id: str = Field(description="ID único del evento")
    user_id: str = Field(description="ID del usuario")
    session_id: Optional[str] = Field(default=None, description="ID de sesión")
    market_id: str = Field(description="ID del mercado")
    event_type: str = Field(description="Tipo de evento")
    product_id: Optional[str] = Field(default=None, description="ID del producto")
    recommendation_id: Optional[str] = Field(default=None, description="ID de la recomendación")
    intent_detected: Optional[IntentType] = Field(default=None, description="Intención detectada")
    conversation_turn: int = Field(default=1, description="Turno de conversación")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp del evento")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata adicional")

class MCPHealthStatus(BaseModel):
    """Estado de salud de componentes MCP"""
    mcp_client: str = Field(description="Estado del cliente MCP")
    market_manager: str = Field(description="Estado del gestor de mercados")
    market_cache: str = Field(description="Estado del caché market-aware")
    conversation_bridge: str = Field(description="Estado del bridge conversacional")
    supported_markets: List[str] = Field(description="Mercados soportados")
    active_sessions: int = Field(description="Sesiones activas")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp del estado")

class MCPConversationTurn(BaseModel):
    """Turno individual en una conversación MCP"""
    turn_id: str = Field(description="ID del turno")
    user_input: str = Field(description="Input del usuario")
    ai_response: str = Field(description="Respuesta de AI")
    intent: Optional[IntentType] = Field(default=None, description="Intención detectada")
    confidence: float = Field(description="Confianza en la detección")
    recommendations_provided: int = Field(description="Número de recomendaciones proporcionadas")
    market_id: str = Field(description="Mercado en el contexto")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp del turno")

class MCPSession(BaseModel):
    """Sesión completa de conversación MCP"""
    session_id: str = Field(description="ID de la sesión")
    user_id: str = Field(description="ID del usuario")
    market_id: str = Field(description="Mercado principal de la sesión")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Inicio de la sesión")
    last_activity: datetime = Field(default_factory=datetime.utcnow, description="Última actividad")
    turns: List[MCPConversationTurn] = Field(default_factory=list, description="Turnos de conversación")
    status: str = Field(default="active", description="Estado de la sesión")
    total_recommendations: int = Field(default=0, description="Total de recomendaciones en la sesión")
    conversion_events: List[str] = Field(default_factory=list, description="Eventos de conversión")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata de la sesión")
