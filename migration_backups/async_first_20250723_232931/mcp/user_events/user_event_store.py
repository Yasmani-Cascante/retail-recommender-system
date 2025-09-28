# src/api/mcp/user_events/user_event_store.py
"""
UserEventStore para almacenamiento de eventos de usuario en Redis

Sistema de almacenamiento diseñado para eventual extracción como microservicio
con schemas bien definidos y TTL policies automáticas.
"""

import json
import time
import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import redis.asyncio as redis
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)

class EventType(str, Enum):
    """Tipos de eventos soportados"""
    CONVERSATION_INTENT = "conversation_intent"
    MCP_EVENT = "mcp_event"
    PRODUCT_VIEW = "product_view"
    PRODUCT_SEARCH = "product_search"
    CART_ADD = "cart_add"
    CART_REMOVE = "cart_remove"
    PURCHASE = "purchase"
    SESSION_START = "session_start"
    SESSION_END = "session_end"

class IntentData(BaseModel):
    """Schema para datos de intención conversacional"""
    type: str = Field(..., description="Tipo de intención detectada")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confianza de la detección")
    query: str = Field(..., description="Query original del usuario")
    keywords: List[str] = Field(default_factory=list, description="Palabras clave detectadas")
    market_id: Optional[str] = Field(None, description="ID del mercado")
    source: str = Field("unknown", description="Fuente de la detección")

class UserEvent(BaseModel):
    """Schema base para eventos de usuario"""
    event_id: str = Field(..., description="ID único del evento")
    user_id: str = Field(..., description="ID del usuario")
    event_type: EventType = Field(..., description="Tipo de evento")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp del evento")
    session_id: Optional[str] = Field(None, description="ID de sesión")
    market_id: Optional[str] = Field(None, description="ID del mercado")
    data: Dict[str, Any] = Field(default_factory=dict, description="Datos específicos del evento")
    
    @validator('timestamp', pre=True)
    def parse_timestamp(cls, v):
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                return datetime.utcnow()
        return v if isinstance(v, datetime) else datetime.utcnow()

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

@dataclass
class TTLPolicy:
    """Política de TTL para diferentes tipos de datos"""
    events_ttl: int = 7 * 24 * 3600      # 7 días para eventos
    profiles_ttl: int = 30 * 24 * 3600    # 30 días para perfiles
    sessions_ttl: int = 24 * 3600         # 24 horas para sesiones activas
    intents_ttl: int = 3 * 24 * 3600      # 3 días para intenciones

class UserEventStore:
    """
    Almacenamiento de eventos de usuario para personalización
    DISEÑADO para eventual extracción como microservicio
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        key_prefix: str = "mcp_events:",
        ttl_policy: Optional[TTLPolicy] = None
    ):
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.ttl_policy = ttl_policy or TTLPolicy()
        
        # Métricas internas
        self.metrics = {
            "events_stored": 0,
            "profiles_generated": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0
        }
        
        logger.info(f"UserEventStore initialized with prefix: {key_prefix}")
    
    async def record_mcp_event(self, user_id: str, event_data: dict) -> bool:
        """
        Captura eventos MCP en tiempo real
        
        Args:
            user_id: ID del usuario
            event_data: Datos del evento
            
        Returns:
            True si el evento se guardó correctamente
        """
        try:
            event = UserEvent(
                event_id=f"mcp_{user_id}_{int(time.time() * 1000)}",
                user_id=user_id,
                event_type=EventType.MCP_EVENT,
                data=event_data,
                session_id=event_data.get("session_id"),
                market_id=event_data.get("market_id")
            )
            
            # Guardar evento en Redis
            key = f"{self.key_prefix}events:{user_id}:{event.event_id}"
            await self.redis.setex(
                key,
                self.ttl_policy.events_ttl,
                json.dumps(event.dict(), default=str)
            )
            
            # Actualizar índice de eventos del usuario
            await self._update_user_event_index(user_id, event.event_id)
            
            # Actualizar perfil de usuario en background
            asyncio.create_task(self._update_user_profile_async(user_id, event))
            
            self.metrics["events_stored"] += 1
            logger.debug(f"MCP event recorded for user {user_id}: {event.event_type}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error recording MCP event for user {user_id}: {e}")
            self.metrics["errors"] += 1
            return False
    
    async def record_conversation_intent(self, user_id: str, intent: dict) -> bool:
        """
        Almacena intenciones conversacionales
        
        Args:
            user_id: ID del usuario
            intent: Datos de intención
            
        Returns:
            True si se guardó correctamente
        """
        try:
            # Validar y estructurar datos de intención
            intent_data = IntentData(**intent)
            
            event = UserEvent(
                event_id=f"intent_{user_id}_{int(time.time() * 1000)}",
                user_id=user_id,
                event_type=EventType.CONVERSATION_INTENT,
                data=intent_data.dict(),
                market_id=intent.get("market_id")
            )
            
            # Guardar evento
            key = f"{self.key_prefix}intents:{user_id}:{event.event_id}"
            await self.redis.setex(
                key,
                self.ttl_policy.intents_ttl,
                json.dumps(event.dict(), default=str)
            )
            
            # Actualizar índice
            await self._update_user_event_index(user_id, event.event_id)
            
            # Actualizar perfil
            asyncio.create_task(self._update_user_profile_async(user_id, event))
            
            self.metrics["events_stored"] += 1
            logger.debug(f"Conversation intent recorded for user {user_id}: {intent_data.type}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error recording conversation intent for user {user_id}: {e}")
            self.metrics["errors"] += 1
            return False
    
    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Genera perfil de usuario basado en eventos MCP
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Perfil del usuario
        """
        try:
            # Intentar obtener perfil cacheado primero
            profile_key = f"{self.key_prefix}profiles:{user_id}"
            cached_profile = await self.redis.get(profile_key)
            
            if cached_profile:
                self.metrics["cache_hits"] += 1
                profile_data = json.loads(cached_profile)
                logger.debug(f"Profile cache hit for user {user_id}")
                return profile_data
            
            self.metrics["cache_misses"] += 1
            
            # Generar perfil desde eventos
            profile = await self._generate_user_profile(user_id)
            
            # Cachear perfil generado
            await self.redis.setex(
                profile_key,
                self.ttl_policy.profiles_ttl,
                json.dumps(profile.dict(), default=str)
            )
            
            self.metrics["profiles_generated"] += 1
            logger.debug(f"Profile generated for user {user_id}")
            
            return profile.dict()
            
        except Exception as e:
            logger.error(f"Error getting user profile for {user_id}: {e}")
            self.metrics["errors"] += 1
            
            # Perfil mínimo de fallback
            return {
                "user_id": user_id,
                "total_events": 0,
                "last_activity": datetime.utcnow().isoformat(),
                "intent_history": [],
                "category_affinity": {},
                "search_patterns": [],
                "session_count": 0,
                "market_preferences": {},
                "error": "Failed to generate profile"
            }
    
    async def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Obtiene preferencias inferidas del comportamiento
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Diccionario con preferencias del usuario
        """
        try:
            profile = await self.get_user_profile(user_id)
            
            # Extraer preferencias del perfil
            preferences = {
                "preferred_categories": list(profile.get("category_affinity", {}).keys())[:5],
                "search_behavior": {
                    "frequent_terms": profile.get("search_patterns", [])[:10],
                    "intent_patterns": self._analyze_intent_patterns(profile.get("intent_history", []))
                },
                "market_preferences": profile.get("market_preferences", {}),
                "activity_level": self._calculate_activity_level(profile),
                "last_active": profile.get("last_activity"),
                "profile_completeness": self._calculate_profile_completeness(profile)
            }
            
            return preferences
            
        except Exception as e:
            logger.error(f"Error getting user preferences for {user_id}: {e}")
            return {
                "preferred_categories": [],
                "search_behavior": {"frequent_terms": [], "intent_patterns": {}},
                "market_preferences": {},
                "activity_level": "unknown",
                "last_active": None,
                "profile_completeness": 0.0
            }
    
    async def _generate_user_profile(self, user_id: str) -> UserProfile:
        """Genera perfil completo del usuario desde sus eventos"""
        
        # Obtener índice de eventos del usuario
        events_index_key = f"{self.key_prefix}index:{user_id}"
        event_ids = await self.redis.lrange(events_index_key, 0, -1)
        
        profile = UserProfile(user_id=user_id)
        intent_history = []
        category_counts = {}
        search_patterns = []
        market_counts = {}
        sessions = set()
        
        # Procesar eventos
        for event_id_bytes in event_ids:
            event_id = event_id_bytes.decode('utf-8')
            
            # Intentar obtener el evento
            event_key = None
            if event_id.startswith("intent_"):
                event_key = f"{self.key_prefix}intents:{user_id}:{event_id}"
            else:
                event_key = f"{self.key_prefix}events:{user_id}:{event_id}"
            
            event_data = await self.redis.get(event_key)
            if not event_data:
                continue
                
            try:
                event = UserEvent(**json.loads(event_data))
                
                # Actualizar última actividad
                if event.timestamp > profile.last_activity:
                    profile.last_activity = event.timestamp
                
                # Procesar según tipo de evento
                if event.event_type == EventType.CONVERSATION_INTENT:
                    intent_data = IntentData(**event.data)
                    intent_history.append(intent_data)
                    
                    # Extraer patrones de búsqueda
                    if intent_data.query:
                        search_patterns.append(intent_data.query.lower())
                
                # Contar mercados
                if event.market_id:
                    market_counts[event.market_id] = market_counts.get(event.market_id, 0) + 1
                
                # Contar sesiones
                if event.session_id:
                    sessions.add(event.session_id)
                
                profile.total_events += 1
                
            except Exception as e:
                logger.warning(f"Error processing event {event_id} for user {user_id}: {e}")
                continue
        
        # Finalizar perfil
        profile.intent_history = intent_history[-20:]  # Últimas 20 intenciones
        profile.category_affinity = {cat: count/profile.total_events 
                                   for cat, count in category_counts.items()}
        profile.search_patterns = list(set(search_patterns))[-50:]  # Últimos 50 únicos
        profile.session_count = len(sessions)
        profile.market_preferences = market_counts
        
        return profile
    
    async def _update_user_event_index(self, user_id: str, event_id: str):
        """Actualiza índice de eventos del usuario"""
        index_key = f"{self.key_prefix}index:{user_id}"
        
        # Agregar evento al índice (mantener últimos 1000)
        pipe = self.redis.pipeline()
        pipe.lpush(index_key, event_id)
        pipe.ltrim(index_key, 0, 999)  # Mantener últimos 1000 eventos
        pipe.expire(index_key, self.ttl_policy.events_ttl)
        await pipe.execute()
    
    async def _update_user_profile_async(self, user_id: str, event: UserEvent):
        """Actualiza perfil de usuario de manera asíncrona"""
        try:
            # Invalidar caché del perfil para forzar regeneración
            profile_key = f"{self.key_prefix}profiles:{user_id}"
            await self.redis.delete(profile_key)
            
            logger.debug(f"Profile cache invalidated for user {user_id}")
            
        except Exception as e:
            logger.warning(f"Error updating profile async for user {user_id}: {e}")
    
    def _analyze_intent_patterns(self, intent_history: List[Dict]) -> Dict[str, Any]:
        """Analiza patrones en el historial de intenciones"""
        if not intent_history:
            return {}
        
        # Contar tipos de intención
        intent_counts = {}
        confidence_sum = 0
        
        for intent in intent_history:
            intent_type = intent.get("type", "unknown")
            intent_counts[intent_type] = intent_counts.get(intent_type, 0) + 1
            confidence_sum += intent.get("confidence", 0.5)
        
        avg_confidence = confidence_sum / len(intent_history)
        most_common = max(intent_counts.items(), key=lambda x: x[1]) if intent_counts else ("unknown", 0)
        
        return {
            "most_common_intent": most_common[0],
            "intent_distribution": intent_counts,
            "average_confidence": avg_confidence,
            "total_intents": len(intent_history)
        }
    
    def _calculate_activity_level(self, profile: Dict) -> str:
        """Calcula nivel de actividad del usuario"""
        total_events = profile.get("total_events", 0)
        session_count = profile.get("session_count", 0)
        
        if total_events >= 50 and session_count >= 10:
            return "high"
        elif total_events >= 20 and session_count >= 5:
            return "medium"
        elif total_events >= 5:
            return "low"
        else:
            return "new"
    
    def _calculate_profile_completeness(self, profile: Dict) -> float:
        """Calcula completitud del perfil (0.0 - 1.0)"""
        completeness = 0.0
        
        if profile.get("total_events", 0) > 0:
            completeness += 0.3
        if profile.get("intent_history", []):
            completeness += 0.3
        if profile.get("category_affinity", {}):
            completeness += 0.2
        if profile.get("search_patterns", []):
            completeness += 0.2
        
        return min(completeness, 1.0)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del UserEventStore"""
        try:
            # Estadísticas de Redis
            redis_info = await self.redis.info("memory")
            
            # Contar claves por tipo
            event_keys = await self.redis.keys(f"{self.key_prefix}events:*")
            intent_keys = await self.redis.keys(f"{self.key_prefix}intents:*")
            profile_keys = await self.redis.keys(f"{self.key_prefix}profiles:*")
            
            return {
                "metrics": self.metrics.copy(),
                "redis_memory_usage": redis_info.get("used_memory_human", "unknown"),
                "stored_data": {
                    "events": len(event_keys),
                    "intents": len(intent_keys),
                    "profiles": len(profile_keys)
                },
                "ttl_policy": asdict(self.ttl_policy),
                "key_prefix": self.key_prefix
            }
            
        except Exception as e:
            logger.error(f"Error getting UserEventStore stats: {e}")
            return {
                "metrics": self.metrics.copy(),
                "error": str(e)
            }
    
    async def cleanup_expired_data(self):
        """Limpieza manual de datos expirados (normalmente Redis lo hace automáticamente)"""
        try:
            # Esta función existe por si necesitamos limpieza manual
            # Redis maneja TTL automáticamente, pero podemos usar esto para limpieza adicional
            
            current_time = time.time()
            cleaned_count = 0
            
            # Limpiar índices de usuarios inactivos (ejemplo de limpieza adicional)
            index_keys = await self.redis.keys(f"{self.key_prefix}index:*")
            
            for key_bytes in index_keys:
                key = key_bytes.decode('utf-8')
                ttl = await self.redis.ttl(key)
                
                # Si TTL es -1 (sin expiración) y es muy viejo, limpiarlo
                if ttl == -1:
                    await self.redis.expire(key, self.ttl_policy.events_ttl)
                    cleaned_count += 1
            
            logger.info(f"Cleanup completed: {cleaned_count} keys updated")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0