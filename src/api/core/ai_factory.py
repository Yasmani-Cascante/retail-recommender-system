# src/api/core/ai_factory.py
"""
Factory para crear instancias de AI Conversation Manager
integrado con el sistema de configuración existente.
"""

import logging
from typing import Optional
from functools import lru_cache

from src.api.core.config import get_settings
from src.api.integrations.ai.ai_conversation_manager import ConversationAIManager

logger = logging.getLogger(__name__)

class AIManagerFactory:
    """Factory para crear y gestionar instancias de AI Manager"""
    
    _instance: Optional[ConversationAIManager] = None
    
    @classmethod
    @lru_cache(maxsize=1)
    def create_ai_manager(cls) -> Optional[ConversationAIManager]:
        """
        Crear instancia singleton de ConversationAIManager
        
        Returns:
            ConversationAIManager instance o None si no está configurado
        """
        settings = get_settings()
        
        if not settings.claude_available:
            logger.warning("Claude no está disponible - AI_CONVERSATION_ENABLED=false o ANTHROPIC_API_KEY no configurado")
            return None
        
        try:
            ai_manager = ConversationAIManager(
                anthropic_api_key=settings.anthropic_api_key,
                perplexity_api_key=settings.perplexity_api_key,
                use_perplexity_validation=settings.use_perplexity_validation
            )
            
            logger.info(f"✅ ConversationAIManager inicializado con modelo: {settings.claude_model}")
            logger.info(f"🔍 Validación Perplexity: {'Habilitada' if settings.use_perplexity_validation else 'Deshabilitada'}")
            
            cls._instance = ai_manager
            return ai_manager
            
        except Exception as e:
            logger.error(f"❌ Error creando ConversationAIManager: {e}")
            return None
    
    @classmethod
    def get_ai_manager(cls) -> Optional[ConversationAIManager]:
        """
        Obtener instancia existente o crear nueva
        
        Returns:
            ConversationAIManager instance o None
        """
        if cls._instance is None:
            cls._instance = cls.create_ai_manager()
        
        return cls._instance
    
    @classmethod
    def is_ai_available(cls) -> bool:
        """
        Verificar si AI está disponible sin crear instancia
        
        Returns:
            bool: True si AI está configurado y disponible
        """
        settings = get_settings()
        return settings.claude_available
    
    @classmethod
    async def cleanup(cls):
        """Limpiar recursos del AI Manager"""
        if cls._instance:
            await cls._instance.cleanup()
            cls._instance = None
            logger.info("✅ AI Manager recursos liberados")

# Funciones de conveniencia para usar en el resto del sistema
def get_ai_manager() -> Optional[ConversationAIManager]:
    """Función de conveniencia para obtener AI Manager"""
    return AIManagerFactory.get_ai_manager()

def is_ai_conversation_available() -> bool:
    """Función de conveniencia para verificar disponibilidad"""
    return AIManagerFactory.is_ai_available()

async def cleanup_ai_resources():
    """Función de conveniencia para limpiar recursos"""
    await AIManagerFactory.cleanup()

# src/api/integrations/ai/conversation_context_builder.py
"""
Builder para crear contexto de conversación desde datos del sistema existente
"""

from typing import Dict, List, Optional, Any
from dataclasses import asdict

from src.api.integrations.ai.ai_conversation_manager import ConversationContext

class ConversationContextBuilder:
    """Builder para crear ConversationContext desde datos del sistema"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Resetear builder para nueva construcción"""
        self._user_id = "anonymous"
        self._session_id = None
        self._market_id = "default"
        self._currency = "USD"
        self._conversation_history = []
        self._user_profile = {}
        self._cart_items = []
        self._browsing_history = []
        self._intent_signals = {}
        return self
    
    def with_user_session(self, user_id: str, session_id: str):
        """Configurar usuario y sesión"""
        self._user_id = user_id
        self._session_id = session_id
        return self
    
    def with_market_context(self, market_id: str, currency: str):
        """Configurar contexto de mercado"""
        self._market_id = market_id
        self._currency = currency
        return self
    
    def with_conversation_history(self, history: List[Dict]):
        """Agregar historial de conversación"""
        # Limitar a últimos N mensajes según configuración
        from src.api.core.config import get_settings
        settings = get_settings()
        
        max_history = settings.max_conversation_history
        self._conversation_history = history[-max_history:] if history else []
        return self
    
    def with_user_profile(self, profile: Dict):
        """Agregar perfil de usuario"""
        self._user_profile = profile or {}
        return self
    
    def with_cart_items(self, cart_items: List[Dict]):
        """Agregar items del carrito"""
        self._cart_items = cart_items or []
        return self
    
    def with_browsing_history(self, browsing_history: List[str]):
        """Agregar historial de navegación"""
        # Limitar a últimos 10 productos vistos
        self._browsing_history = browsing_history[-10:] if browsing_history else []
        return self
    
    def with_intent_signals(self, intent_signals: Dict):
        """Agregar señales de intención"""
        self._intent_signals = intent_signals or {}
        return self
    
    def build(self) -> ConversationContext:
        """Construir el ConversationContext final"""
        return ConversationContext(
            user_id=self._user_id,
            session_id=self._session_id,
            market_id=self._market_id,
            currency=self._currency,
            conversation_history=self._conversation_history,
            user_profile=self._user_profile,
            cart_items=self._cart_items,
            browsing_history=self._browsing_history,
            intent_signals=self._intent_signals
        )
    
    @classmethod
    def from_request_data(cls, request_data: Dict) -> ConversationContext:
        """
        Crear contexto desde datos de request típicos del sistema
        
        Args:
            request_data: Dict con datos de la request, puede incluir:
                - user_id, session_id
                - market_id, currency
                - conversation_history
                - user_profile, cart_items, etc.
        
        Returns:
            ConversationContext construido
        """
        builder = cls()
        
        # Configurar datos básicos
        user_id = request_data.get("user_id", "anonymous")
        session_id = request_data.get("session_id")
        if session_id:
            builder.with_user_session(user_id, session_id)
        else:
            builder._user_id = user_id
            builder._session_id = f"session_{user_id}_{hash(str(request_data))}"
        
        # Configurar mercado
        market_id = request_data.get("market_id", "default")
        currency = request_data.get("currency", "USD")
        builder.with_market_context(market_id, currency)
        
        # Configurar datos opcionales si están disponibles
        if "conversation_history" in request_data:
            builder.with_conversation_history(request_data["conversation_history"])
        
        if "user_profile" in request_data:
            builder.with_user_profile(request_data["user_profile"])
        
        if "cart_items" in request_data:
            builder.with_cart_items(request_data["cart_items"])
        
        if "browsing_history" in request_data:
            builder.with_browsing_history(request_data["browsing_history"])
        
        if "intent_signals" in request_data:
            builder.with_intent_signals(request_data["intent_signals"])
        
        return builder.build()

# Función helper para crear contexto desde datos mínimos
def create_minimal_context(
    user_id: str = "anonymous",
    market_id: str = "default",
    currency: str = "USD",
    **kwargs
) -> ConversationContext:
    """
    Crear contexto mínimo para testing o casos simples
    """
    return (ConversationContextBuilder()
            .with_user_session(user_id, f"session_{user_id}")
            .with_market_context(market_id, currency)
            .build())