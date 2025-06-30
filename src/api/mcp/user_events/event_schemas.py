# src/api/mcp/user_events/event_schemas.py
"""
Schemas definidos para eventos MCP y validación de datos

Proporciona modelos Pydantic para validación consistente de eventos de usuario
y estructuras de datos relacionadas con personalización.
"""

from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator

class EventType(str, Enum):
    """Tipos de eventos soportados en el sistema MCP"""
    CONVERSATION_INTENT = "conversation_intent"
    MCP_EVENT = "mcp_event"
    PRODUCT_VIEW = "product_view"
    PRODUCT_SEARCH = "product_search"
    CART_ADD = "cart_add"
    CART_REMOVE = "cart_remove"
    PURCHASE = "purchase"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    RECOMMENDATION_CLICKED = "recommendation_clicked"
    WISHLIST_ADD = "wishlist_add"

class IntentType(str, Enum):
    """Tipos de intención conversacional"""
    SEARCH = "search"
    PURCHASE_INTENT = "purchase_intent"
    HIGH_PURCHASE_INTENT = "high_purchase_intent"
    COMPARISON_SHOPPING = "comparison_shopping"
    RECOMMENDATION = "recommendation"
    PRICE_INQUIRY = "price_inquiry"
    BROWSING = "browsing"
    GENERAL = "general"

class MarketID(str, Enum):
    """IDs de mercados soportados"""
    US = "US"
    ES = "ES"
    MX = "MX"
    CO = "CO"
    CL = "CL"
    AR = "AR"
    PE = "PE"
    DEFAULT = "default"

class IntentData(BaseModel):
    """Schema para datos de intención conversacional"""
    type: IntentType = Field(..., description="Tipo de intención detectada")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confianza de la detección")
    query: str = Field(..., description="Query original del usuario")
    keywords: List[str] = Field(default_factory=list, description="Palabras clave detectadas")
    market_id: Optional[MarketID] = Field(None, description="ID del mercado")
    source: str = Field("unknown", description="Fuente de la detección (mcp_bridge, local_nlp, etc.)")
    language: str = Field("en", description="Idioma detectado")
    
    class Config:
        use_enum_values = True

class ProductEventData(BaseModel):
    """Schema para eventos relacionados con productos"""
    product_id: str = Field(..., description="ID del producto")
    product_title: Optional[str] = Field(None, description="Título del producto")
    product_category: Optional[str] = Field(None, description="Categoría del producto")
    price: Optional[float] = Field(None, ge=0, description="Precio del producto")
    currency: str = Field("USD", description="Moneda del precio")
    quantity: int = Field(1, ge=1, description="Cantidad")
    
class PurchaseEventData(ProductEventData):
    """Schema específico para eventos de compra"""
    total_amount: float = Field(..., ge=0, description="Monto total de la compra")
    payment_method: Optional[str] = Field(None, description="Método de pago")
    order_id: Optional[str] = Field(None, description="ID de la orden")

class SearchEventData(BaseModel):
    """Schema para eventos de búsqueda"""
    query: str = Field(..., description="Consulta de búsqueda")
    results_count: int = Field(0, ge=0, description="Número de resultados")
    filters_applied: Dict[str, Any] = Field(default_factory=dict, description="Filtros aplicados")
    sort_by: Optional[str] = Field(None, description="Criterio de ordenamiento")

class UserEvent(BaseModel):
    """Schema base para eventos de usuario"""
    event_id: str = Field(..., description="ID único del evento")
    user_id: str = Field(..., description="ID del usuario")
    event_type: EventType = Field(..., description="Tipo de evento")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp del evento")
    session_id: Optional[str] = Field(None, description="ID de sesión")
    market_id: Optional[MarketID] = Field(None, description="ID del mercado")
    data: Dict[str, Any] = Field(default_factory=dict, description="Datos específicos del evento")
    ip_address: Optional[str] = Field(None, description="Dirección IP del usuario")
    user_agent: Optional[str] = Field(None, description="User agent del navegador")
    
    @validator('timestamp', pre=True)
    def parse_timestamp(cls, v):
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                return datetime.utcnow()
        return v if isinstance(v, datetime) else datetime.utcnow()
    
    class Config:
        use_enum_values = True

class UserProfile(BaseModel):
    """Schema para perfil de usuario generado desde eventos"""
    user_id: str = Field(..., description="ID del usuario")
    total_events: int = Field(0, description="Total de eventos registrados")
    last_activity: datetime = Field(default_factory=datetime.utcnow, description="Última actividad")
    intent_history: List[IntentData] = Field(default_factory=list, description="Historial de intenciones")
    category_affinity: Dict[str, float] = Field(default_factory=dict, description="Afinidad por categorías")
    search_patterns: List[str] = Field(default_factory=list, description="Patrones de búsqueda")
    session_count: int = Field(0, description="Número de sesiones")
    market_preferences: Dict[str, int] = Field(default_factory=dict, description="Preferencias por mercado")
    purchase_history: List[PurchaseEventData] = Field(default_factory=list, description="Historial de compras")
    avg_session_duration: float = Field(0.0, description="Duración promedio de sesión en minutos")
    preferred_price_range: Dict[str, float] = Field(default_factory=dict, description="Rango de precios preferido")
    
    class Config:
        use_enum_values = True

class ConversationContext(BaseModel):
    """Schema para contexto de conversación MCP"""
    session_id: str = Field(..., description="ID de sesión conversacional")
    user_id: str = Field(..., description="ID del usuario")
    query: str = Field(..., description="Consulta del usuario")
    market_id: MarketID = Field(MarketID.DEFAULT, description="ID del mercado")
    language: str = Field("en", description="Idioma de la conversación")
    previous_queries: List[str] = Field(default_factory=list, description="Consultas anteriores en la sesión")
    
    class Config:
        use_enum_values = True

class RecommendationFeedback(BaseModel):
    """Schema para feedback de recomendaciones"""
    recommendation_id: str = Field(..., description="ID de la recomendación")
    user_id: str = Field(..., description="ID del usuario")
    product_id: str = Field(..., description="ID del producto recomendado")
    feedback_type: str = Field(..., description="Tipo de feedback (clicked, ignored, purchased)")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating del usuario (1-5)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp del feedback")
    
class SessionData(BaseModel):
    """Schema para datos de sesión de usuario"""
    session_id: str = Field(..., description="ID único de la sesión")
    user_id: str = Field(..., description="ID del usuario")
    start_time: datetime = Field(default_factory=datetime.utcnow, description="Inicio de sesión")
    end_time: Optional[datetime] = Field(None, description="Fin de sesión")
    page_views: int = Field(0, description="Páginas vistas en la sesión")
    products_viewed: List[str] = Field(default_factory=list, description="Productos vistos")
    searches_performed: int = Field(0, description="Búsquedas realizadas")
    cart_additions: int = Field(0, description="Productos añadidos al carrito")
    purchases_made: int = Field(0, description="Compras realizadas")
    market_id: Optional[MarketID] = Field(None, description="Mercado de la sesión")
    
    class Config:
        use_enum_values = True
        
    @property
    def duration_minutes(self) -> float:
        """Calcula duración de la sesión en minutos"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() / 60
        return (datetime.utcnow() - self.start_time).total_seconds() / 60

# Schemas para métricas y análisis
class UserBehaviorMetrics(BaseModel):
    """Métricas de comportamiento de usuario"""
    user_id: str = Field(..., description="ID del usuario")
    calculation_date: datetime = Field(default_factory=datetime.utcnow, description="Fecha de cálculo")
    
    # Métricas de actividad
    total_sessions: int = Field(0, description="Total de sesiones")
    avg_session_duration: float = Field(0.0, description="Duración promedio de sesión")
    total_page_views: int = Field(0, description="Total de páginas vistas")
    bounce_rate: float = Field(0.0, description="Tasa de rebote")
    
    # Métricas de engagement
    products_viewed: int = Field(0, description="Productos únicos vistos")
    searches_performed: int = Field(0, description="Búsquedas realizadas")
    cart_additions: int = Field(0, description="Productos añadidos al carrito")
    purchases_made: int = Field(0, description="Compras realizadas")
    
    # Métricas de conversión
    view_to_cart_rate: float = Field(0.0, description="Tasa de conversión vista → carrito")
    cart_to_purchase_rate: float = Field(0.0, description="Tasa de conversión carrito → compra")
    overall_conversion_rate: float = Field(0.0, description="Tasa de conversión general")
    
    # Métricas de valor
    total_spent: float = Field(0.0, description="Total gastado")
    avg_order_value: float = Field(0.0, description="Valor promedio de orden")
    lifetime_value: float = Field(0.0, description="Valor de por vida estimado")

class MarketMetrics(BaseModel):
    """Métricas específicas por mercado"""
    market_id: MarketID = Field(..., description="ID del mercado")
    calculation_date: datetime = Field(default_factory=datetime.utcnow, description="Fecha de cálculo")
    
    # Métricas de usuarios
    active_users: int = Field(0, description="Usuarios activos")
    new_users: int = Field(0, description="Usuarios nuevos")
    returning_users: int = Field(0, description="Usuarios recurrentes")
    
    # Métricas de engagement
    avg_session_duration: float = Field(0.0, description="Duración promedio de sesión")
    pages_per_session: float = Field(0.0, description="Páginas por sesión")
    bounce_rate: float = Field(0.0, description="Tasa de rebote")
    
    # Métricas de conversión
    conversion_rate: float = Field(0.0, description="Tasa de conversión")
    cart_abandonment_rate: float = Field(0.0, description="Tasa de abandono de carrito")
    
    # Métricas de negocio
    total_revenue: float = Field(0.0, description="Ingresos totales")
    avg_order_value: float = Field(0.0, description="Valor promedio de orden")
    orders_count: int = Field(0, description="Número de órdenes")
    
    class Config:
        use_enum_values = True

# Validadores y utilidades
def validate_event_data(event_type: EventType, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida y estructura los datos del evento según su tipo
    
    Args:
        event_type: Tipo del evento
        data: Datos sin estructurar del evento
        
    Returns:
        Datos validados y estructurados
        
    Raises:
        ValueError: Si los datos no son válidos para el tipo de evento
    """
    try:
        if event_type == EventType.CONVERSATION_INTENT:
            return IntentData(**data).dict()
        elif event_type in [EventType.PRODUCT_VIEW, EventType.CART_ADD, EventType.CART_REMOVE]:
            return ProductEventData(**data).dict()
        elif event_type == EventType.PURCHASE:
            return PurchaseEventData(**data).dict()
        elif event_type == EventType.PRODUCT_SEARCH:
            return SearchEventData(**data).dict()
        else:
            # Para otros tipos, validación básica
            return data
    except Exception as e:
        raise ValueError(f"Invalid data for event type {event_type}: {str(e)}")

def create_event_id(user_id: str, event_type: EventType, timestamp: Optional[datetime] = None) -> str:
    """
    Crea un ID único para un evento
    
    Args:
        user_id: ID del usuario
        event_type: Tipo del evento
        timestamp: Timestamp del evento (opcional)
        
    Returns:
        ID único del evento
    """
    if timestamp is None:
        timestamp = datetime.utcnow()
    
    timestamp_str = str(int(timestamp.timestamp() * 1000))  # Milliseconds
    return f"{event_type.value}_{user_id}_{timestamp_str}"

# Modelos para requests de API
class ListUserEventsRequest(BaseModel):
    """Request para listar eventos de usuario"""
    user_id: str = Field(..., description="ID del usuario")
    limit: int = Field(50, ge=1, le=1000, description="Límite de eventos a retornar")
    offset: int = Field(0, ge=0, description="Offset para paginación")
    event_types: Optional[List[EventType]] = Field(None, description="Filtrar por tipos de evento")
    start_date: Optional[datetime] = Field(None, description="Fecha de inicio")
    end_date: Optional[datetime] = Field(None, description="Fecha de fin")
    
    class Config:
        use_enum_values = True

class ListUserEventsResponse(BaseModel):
    """Response para listar eventos de usuario"""
    events: List[UserEvent] = Field(description="Lista de eventos")
    total: int = Field(description="Total de eventos")
    user_id: str = Field(description="ID del usuario")
    pagination: Dict[str, Any] = Field(description="Información de paginación")

def calculate_user_activity_level(total_events: int, session_count: int, days_active: int) -> str:
    """
    Calcula el nivel de actividad de un usuario
    
    Args:
        total_events: Total de eventos del usuario
        session_count: Número de sesiones
        days_active: Días activos
        
    Returns:
        Nivel de actividad (new, low, medium, high, power_user)
    """
    if total_events == 0:
        return "new"
    
    events_per_day = total_events / max(days_active, 1)
    sessions_per_day = session_count / max(days_active, 1)
    
    if events_per_day >= 20 and sessions_per_day >= 3:
        return "power_user"
    elif events_per_day >= 10 and sessions_per_day >= 2:
        return "high"
    elif events_per_day >= 5 and sessions_per_day >= 1:
        return "medium"
    elif events_per_day >= 1:
        return "low"
    else:
        return "new"
