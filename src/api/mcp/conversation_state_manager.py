"""
MCP Conversation State Manager - Advanced Implementation
===============================================

Gestiona el estado conversacional persistente utilizando Redis para:
- Historial de conversaciones multi-turn
- Tracking de intenciones evolutivas  
- Preferencias de mercado por usuario
- Context reconstruction inteligente
- Session lifecycle management

Integración: Redis async + MCPClient + PersonalizationEngine
"""

import json
import time
import logging
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

from src.api.core.redis_client import RedisClient

logger = logging.getLogger(__name__)

class ConversationStage(Enum):
    """Etapas del ciclo de vida conversacional"""
    INITIAL = "initial"
    EXPLORING = "exploring" 
    NARROWING = "narrowing"
    DECIDING = "deciding"
    TRANSACTING = "transacting"
    FOLLOW_UP = "follow_up"

class IntentEvolution(Enum):
    """Patrones de evolución de intenciones"""
    STABLE = "stable"           # Intent se mantiene
    NARROWING = "narrowing"     # De general a específico
    EXPANDING = "expanding"     # De específico a general
    SWITCHING = "switching"     # Cambio de categoría
    DEEPENING = "deepening"     # Más detalles del mismo intent

@dataclass
class ConversationTurn:
    """Representa un turno individual en la conversación"""
    turn_number: int
    timestamp: float
    user_query: str
    user_intent: str
    intent_confidence: float
    intent_entities: List[str]
    ai_response: str
    recommendations_provided: List[str]
    market_context: Dict[str, Any]
    processing_time_ms: float

@dataclass
class UserMarketPreferences:
    """Preferencias del usuario por mercado"""
    market_id: str
    currency_preference: str
    language_preference: str
    price_sensitivity: float  # 0.0 = price insensitive, 1.0 = very price sensitive
    brand_affinities: List[str]
    category_interests: Dict[str, float]  # category -> interest_score
    cultural_preferences: Dict[str, Any]
    updated_at: float

@dataclass
class MCPConversationContext:
    """Contexto completo de conversación enriquecido para MCP"""
    session_id: str
    user_id: str
    created_at: float
    last_updated: float
    conversation_stage: ConversationStage
    total_turns: int
    
    # Conversation history
    turns: List[ConversationTurn]
    intent_history: List[Dict[str, Any]]
    
    # User insights
    primary_intent: str
    intent_evolution_pattern: IntentEvolution
    market_preferences: Dict[str, UserMarketPreferences]  # market_id -> preferences
    
    # Behavioral patterns
    avg_response_time: float
    conversation_velocity: float  # turns per minute
    engagement_score: float  # 0.0 - 1.0
    
    # Session metadata
    user_agent: str
    initial_market_id: str
    current_market_id: str
    device_type: str

class MCPConversationStateManager:
    """
    Gestor avanzado de estado conversacional con capacidades de machine learning
    y análisis predictivo de comportamiento del usuario.
    
    Integra con ConversationAIManager existente para proporcionar persistencia
    y análisis avanzado de conversaciones.
    """
    
    def __init__(
        self, 
        redis_client: RedisClient,
        state_ttl: int = 86400,  # 24 hours
        conversation_ttl: int = 7 * 24 * 3600,  # 7 days
        max_turns_per_session: int = 50
    ):
        """
        Inicializa el gestor de estado conversacional.
        
        Args:
            redis_client: Cliente Redis asíncrono
            state_ttl: TTL para estado de sesión activa (segundos)
            conversation_ttl: TTL para historial completo (segundos)
            max_turns_per_session: Máximo de turnos por sesión
        """
        self.redis = redis_client
        self.state_ttl = state_ttl
        self.conversation_ttl = conversation_ttl
        self.max_turns_per_session = max_turns_per_session
        
        # Prefixes para diferentes tipos de datos
        self.CONVERSATION_PREFIX = "mcp:conversation"
        self.USER_PROFILE_PREFIX = "mcp:user_profile"
        self.MARKET_PREFS_PREFIX = "mcp:market_prefs"
        self.SESSION_INDEX_PREFIX = "mcp:session_index"
        
        # Métricas internas
        self.metrics = {
            "conversations_created": 0,
            "conversations_loaded": 0,
            "state_saves": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        logger.info("MCPConversationStateManager initialized")
    
    async def create_conversation_context(
        self,
        session_id: str,
        user_id: str,
        initial_query: str,
        market_context: Dict[str, Any],
        user_agent: str = "unknown"
    ) -> MCPConversationContext:
        """Crea un nuevo contexto conversacional."""
        try:
            current_time = time.time()
            market_id = market_context.get('market_id', 'default')
            
            context = MCPConversationContext(
                session_id=session_id,
                user_id=user_id,
                created_at=current_time,
                last_updated=current_time,
                conversation_stage=ConversationStage.INITIAL,
                total_turns=0,
                turns=[],
                intent_history=[],
                primary_intent="unknown",
                intent_evolution_pattern=IntentEvolution.STABLE,
                market_preferences={},
                avg_response_time=0.0,
                conversation_velocity=0.0,
                engagement_score=0.5,
                user_agent=user_agent,
                initial_market_id=market_id,
                current_market_id=market_id,
                device_type=self._detect_device_type(user_agent)
            )
            
            await self._load_user_market_preferences(context)
            await self._index_session_for_user(user_id, session_id, current_time)
            
            self.metrics["conversations_created"] += 1
            
            logger.info(f"Created MCP conversation context for session {session_id}")
            return context
            
        except Exception as e:
            logger.error(f"Error creating conversation context: {e}")
            raise
    
    async def add_conversation_turn(
        self,
        context: MCPConversationContext,
        user_query: str,
        intent_analysis: Dict[str, Any],
        ai_response: str,
        recommendations: List[str] = None,
        processing_time_ms: float = 0.0
    ) -> MCPConversationContext:
        """Añade un nuevo turno a la conversación y actualiza el contexto."""
        try:
            current_time = time.time()
            turn_number = len(context.turns) + 1
            
            turn = ConversationTurn(
                turn_number=turn_number,
                timestamp=current_time,
                user_query=user_query,
                user_intent=intent_analysis.get('intent', 'unknown'),
                intent_confidence=intent_analysis.get('confidence', 0.0),
                intent_entities=intent_analysis.get('entities', []),
                ai_response=ai_response,
                recommendations_provided=recommendations or [],
                market_context=intent_analysis.get('market_context', {}),
                processing_time_ms=processing_time_ms
            )
            
            context.turns.append(turn)
            context.total_turns = len(context.turns)
            context.last_updated = current_time
            
            intent_record = {
                "turn": turn_number,
                "timestamp": current_time,
                "intent": turn.user_intent,
                "confidence": turn.intent_confidence,
                "entities": turn.intent_entities
            }
            context.intent_history.append(intent_record)
            
            await self._analyze_intent_evolution(context)
            context.conversation_stage = self._determine_conversation_stage(context)
            await self._update_engagement_metrics(context)
            await self._update_market_preferences_from_turn(context, turn)
            
            if len(context.turns) > self.max_turns_per_session:
                context.turns = context.turns[-self.max_turns_per_session:]
                logger.warning(f"Trimmed conversation to {self.max_turns_per_session} turns")
            
            logger.debug(f"Added turn {turn_number} to conversation {context.session_id}")
            return context
            
        except Exception as e:
            logger.error(f"Error adding conversation turn: {e}")
            raise
    
    async def save_conversation_state(
        self,
        context: MCPConversationContext,
        force_save: bool = False
    ) -> bool:
        """Persiste el estado conversacional en Redis."""
        try:
            context_data = self._serialize_context(context)
            conversation_key = f"{self.CONVERSATION_PREFIX}:{context.session_id}"
            user_profile_key = f"{self.USER_PROFILE_PREFIX}:{context.user_id}"
            
            pipe = await self.redis.pipeline()
            
            pipe.set(
                conversation_key,
                json.dumps(context_data),
                ex=self.state_ttl
            )
            
            user_insights = self._extract_user_insights(context)
            pipe.hset(user_profile_key, mapping=user_insights)
            pipe.expire(user_profile_key, self.conversation_ttl)
            
            for market_id, prefs in context.market_preferences.items():
                market_key = f"{self.MARKET_PREFS_PREFIX}:{context.user_id}:{market_id}"
                pipe.set(
                    market_key,
                    json.dumps(asdict(prefs)),
                    ex=self.conversation_ttl
                )
            
            await pipe.execute()
            self.metrics["state_saves"] += 1
            
            logger.debug(f"Saved conversation state for session {context.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving conversation state: {e}")
            return False
    
    async def load_conversation_state(
        self,
        session_id: str
    ) -> Optional[MCPConversationContext]:
        """Carga el estado conversacional desde Redis."""
        try:
            conversation_key = f"{self.CONVERSATION_PREFIX}:{session_id}"
            context_data = await self.redis.get(conversation_key)
            
            if not context_data:
                self.metrics["cache_misses"] += 1
                logger.debug(f"No conversation state found for session {session_id}")
                return None
            
            context = self._deserialize_context(json.loads(context_data))
            self.metrics["cache_hits"] += 1
            self.metrics["conversations_loaded"] += 1
            
            logger.debug(f"Loaded conversation state for session {session_id}")
            return context
            
        except Exception as e:
            logger.error(f"Error loading conversation state: {e}")
            return None
    
    def convert_to_legacy_context(
        self, 
        mcp_context: MCPConversationContext
    ):
        """
        Convierte MCPConversationContext al formato ConversationContext legacy
        para compatibilidad con ConversationAIManager existente.
        """
        from src.api.integrations.ai.ai_conversation_manager import ConversationContext
        
        # Construir historial de conversación en formato legacy
        conversation_history = []
        for turn in mcp_context.turns:
            conversation_history.extend([
                {"role": "user", "content": turn.user_query},
                {"role": "assistant", "content": turn.ai_response}
            ])
        
        # Extraer preferencias de mercado actual
        current_prefs = mcp_context.market_preferences.get(
            mcp_context.current_market_id, 
            UserMarketPreferences(
                market_id=mcp_context.current_market_id,
                currency_preference="USD",
                language_preference="en",
                price_sensitivity=0.5,
                brand_affinities=[],
                category_interests={},
                cultural_preferences={},
                updated_at=time.time()
            )
        )
        
        user_profile = {
            "primary_intent": mcp_context.primary_intent,
            "engagement_score": mcp_context.engagement_score,
            "conversation_stage": mcp_context.conversation_stage.value,
            "price_sensitivity": current_prefs.price_sensitivity,
            "brand_affinities": current_prefs.brand_affinities,
            "category_interests": current_prefs.category_interests,
            "device_type": mcp_context.device_type
        }
        
        legacy_context = ConversationContext(
            user_id=mcp_context.user_id,
            session_id=mcp_context.session_id,
            market_id=mcp_context.current_market_id,
            currency=current_prefs.currency_preference,
            conversation_history=conversation_history,
            user_profile=user_profile,
            cart_items=[],
            browsing_history=[],
            intent_signals={
                "primary_intent": mcp_context.primary_intent,
                "evolution_pattern": mcp_context.intent_evolution_pattern.value,
                "confidence_avg": (
                    sum(turn["confidence"] for turn in mcp_context.intent_history) /
                    len(mcp_context.intent_history)
                    if mcp_context.intent_history else 0.0
                )
            }
        )
        
        return legacy_context
    
    def get_metrics(self) -> Dict[str, Any]:
        """Retorna métricas del estado conversacional."""
        return {
            "manager_metrics": self.metrics.copy(),
            "cache_hit_ratio": (
                self.metrics["cache_hits"] / 
                (self.metrics["cache_hits"] + self.metrics["cache_misses"])
                if (self.metrics["cache_hits"] + self.metrics["cache_misses"]) > 0 
                else 0.0
            )
        }
    
    # === MÉTODOS PRIVADOS ===
    
    def _serialize_context(self, context: MCPConversationContext) -> Dict[str, Any]:
        """Serializa el contexto conversacional para almacenamiento."""
        return {
            "session_id": context.session_id,
            "user_id": context.user_id,
            "created_at": context.created_at,
            "last_updated": context.last_updated,
            "conversation_stage": context.conversation_stage.value,
            "total_turns": context.total_turns,
            "turns": [asdict(turn) for turn in context.turns],
            "intent_history": context.intent_history,
            "primary_intent": context.primary_intent,
            "intent_evolution_pattern": context.intent_evolution_pattern.value,
            "market_preferences": {
                k: asdict(v) for k, v in context.market_preferences.items()
            },
            "avg_response_time": context.avg_response_time,
            "conversation_velocity": context.conversation_velocity,
            "engagement_score": context.engagement_score,
            "user_agent": context.user_agent,
            "initial_market_id": context.initial_market_id,
            "current_market_id": context.current_market_id,
            "device_type": context.device_type
        }
    
    def _deserialize_context(self, data: Dict[str, Any]) -> MCPConversationContext:
        """Deserializa el contexto conversacional desde almacenamiento."""
        turns = [ConversationTurn(**turn_data) for turn_data in data.get("turns", [])]
        
        market_prefs = {}
        for market_id, prefs_data in data.get("market_preferences", {}).items():
            market_prefs[market_id] = UserMarketPreferences(**prefs_data)
        
        return MCPConversationContext(
            session_id=data["session_id"],
            user_id=data["user_id"],
            created_at=data["created_at"],
            last_updated=data["last_updated"],
            conversation_stage=ConversationStage(data["conversation_stage"]),
            total_turns=data["total_turns"],
            turns=turns,
            intent_history=data.get("intent_history", []),
            primary_intent=data.get("primary_intent", "unknown"),
            intent_evolution_pattern=IntentEvolution(data.get("intent_evolution_pattern", "stable")),
            market_preferences=market_prefs,
            avg_response_time=data.get("avg_response_time", 0.0),
            conversation_velocity=data.get("conversation_velocity", 0.0),
            engagement_score=data.get("engagement_score", 0.5),
            user_agent=data.get("user_agent", "unknown"),
            initial_market_id=data.get("initial_market_id", "default"),
            current_market_id=data.get("current_market_id", "default"),
            device_type=data.get("device_type", "unknown")
        )
    
    def _detect_device_type(self, user_agent: str) -> str:
        """Detecta el tipo de dispositivo desde user agent."""
        user_agent_lower = user_agent.lower()
        if "mobile" in user_agent_lower or "android" in user_agent_lower:
            return "mobile"
        elif "tablet" in user_agent_lower or "ipad" in user_agent_lower:
            return "tablet"
        elif "bot" in user_agent_lower or "crawler" in user_agent_lower:
            return "bot"
        else:
            return "desktop"
    
    async def _analyze_intent_evolution(self, context: MCPConversationContext):
        """Analiza cómo han evolucionado las intenciones del usuario."""
        if len(context.intent_history) < 2:
            return
        
        recent_intents = [turn["intent"] for turn in context.intent_history[-3:]]
        
        if len(set(recent_intents)) == 1:
            context.intent_evolution_pattern = IntentEvolution.STABLE
        elif self._is_narrowing_pattern(recent_intents):
            context.intent_evolution_pattern = IntentEvolution.NARROWING
        elif self._is_expanding_pattern(recent_intents):
            context.intent_evolution_pattern = IntentEvolution.EXPANDING
        else:
            context.intent_evolution_pattern = IntentEvolution.SWITCHING
        
        intent_counts = {}
        for turn in context.intent_history:
            intent = turn["intent"]
            intent_counts[intent] = intent_counts.get(intent, 0) + 1
        
        if intent_counts:
            context.primary_intent = max(intent_counts, key=intent_counts.get)
    
    def _determine_conversation_stage(self, context: MCPConversationContext) -> ConversationStage:
        """Determina la etapa actual de la conversación."""
        if context.total_turns <= 1:
            return ConversationStage.INITIAL
        elif context.total_turns <= 3:
            return ConversationStage.EXPLORING
        elif context.intent_evolution_pattern == IntentEvolution.NARROWING:
            return ConversationStage.NARROWING
        elif any("purchase" in turn.user_intent for turn in context.turns[-2:]):
            return ConversationStage.TRANSACTING
        elif context.total_turns > 10:
            return ConversationStage.FOLLOW_UP
        else:
            return ConversationStage.DECIDING
    
    async def _update_engagement_metrics(self, context: MCPConversationContext):
        """Actualiza métricas de engagement del usuario."""
        if len(context.turns) < 2:
            return
        
        time_span = context.turns[-1].timestamp - context.turns[0].timestamp
        if time_span > 0:
            context.conversation_velocity = len(context.turns) / (time_span / 60)
        
        factors = {
            "query_length": sum(len(turn.user_query) for turn in context.turns) / len(context.turns),
            "intent_confidence": sum(turn.intent_confidence for turn in context.turns) / len(context.turns),
            "conversation_velocity": min(context.conversation_velocity, 10) / 10,
            "turn_count": min(len(context.turns), 20) / 20
        }
        
        weights = {"query_length": 0.3, "intent_confidence": 0.4, "conversation_velocity": 0.2, "turn_count": 0.1}
        normalized_query_length = min(factors["query_length"] / 50, 1.0)
        
        context.engagement_score = (
            weights["query_length"] * normalized_query_length +
            weights["intent_confidence"] * factors["intent_confidence"] +
            weights["conversation_velocity"] * factors["conversation_velocity"] +
            weights["turn_count"] * factors["turn_count"]
        )
    
    async def _load_user_market_preferences(self, context: MCPConversationContext):
        """Carga las preferencias de mercado del usuario."""
        try:
            market_key = f"{self.MARKET_PREFS_PREFIX}:{context.user_id}:{context.current_market_id}"
            prefs_data = await self.redis.get(market_key)
            
            if prefs_data:
                prefs_dict = json.loads(prefs_data)
                context.market_preferences[context.current_market_id] = UserMarketPreferences(**prefs_dict)
            else:
                context.market_preferences[context.current_market_id] = UserMarketPreferences(
                    market_id=context.current_market_id,
                    currency_preference="USD",
                    language_preference="en",
                    price_sensitivity=0.5,
                    brand_affinities=[],
                    category_interests={},
                    cultural_preferences={},
                    updated_at=time.time()
                )
                
        except Exception as e:
            logger.error(f"Error loading user market preferences: {e}")
    
    async def _update_market_preferences_from_turn(self, context: MCPConversationContext, turn: ConversationTurn):
        """Actualiza las preferencias de mercado basadas en el turno actual."""
        try:
            market_id = context.current_market_id
            prefs = context.market_preferences.get(market_id)
            
            if not prefs:
                return
            
            for entity in turn.intent_entities:
                if entity in prefs.category_interests:
                    prefs.category_interests[entity] = min(1.0, prefs.category_interests[entity] + 0.1)
                else:
                    prefs.category_interests[entity] = 0.1
            
            prefs.updated_at = time.time()
            
        except Exception as e:
            logger.error(f"Error updating market preferences: {e}")
    
    async def _index_session_for_user(self, user_id: str, session_id: str, timestamp: float):
        """Indexa la sesión para el usuario para búsquedas rápidas."""
        try:
            index_key = f"{self.SESSION_INDEX_PREFIX}:{user_id}"
            await self.redis.zadd(index_key, {session_id: timestamp})
            await self.redis.expire(index_key, self.conversation_ttl)
        except Exception as e:
            logger.error(f"Error indexing session: {e}")
    
    def _extract_user_insights(self, context: MCPConversationContext) -> Dict[str, str]:
        """Extrae insights del usuario para el perfil."""
        return {
            "last_session_id": context.session_id,
            "primary_intent": context.primary_intent,
            "avg_engagement_score": str(context.engagement_score),
            "preferred_market_id": context.current_market_id,
            "device_type": context.device_type,
            "last_activity": str(context.last_updated),
            "conversation_style": self._determine_conversation_style(context)
        }
    
    def _determine_conversation_style(self, context: MCPConversationContext) -> str:
        """Determina el estilo conversacional del usuario."""
        if context.conversation_velocity > 5:
            return "fast_paced"
        elif context.engagement_score > 0.7:
            return "engaged"
        elif len(context.turns) > 10:
            return "thorough"
        else:
            return "casual"
    
    def _is_narrowing_pattern(self, recent_intents: List[str]) -> bool:
        """Detecta si el patrón de intenciones está estrechándose."""
        general_intents = {"general", "browse", "explore"}
        specific_intents = {"purchase", "compare", "details"}
        
        if len(recent_intents) < 2:
            return False
        
        return (
            recent_intents[0] in general_intents and 
            recent_intents[-1] in specific_intents
        )
    
    def _is_expanding_pattern(self, recent_intents: List[str]) -> bool:
        """Detecta si el patrón de intenciones se está expandiendo."""
        general_intents = {"general", "browse", "explore"}
        specific_intents = {"purchase", "compare", "details"}
        
        if len(recent_intents) < 2:
            return False
        
        return (
            recent_intents[0] in specific_intents and 
            recent_intents[-1] in general_intents
        )
