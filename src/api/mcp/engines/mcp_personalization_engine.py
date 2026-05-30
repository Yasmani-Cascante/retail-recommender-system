# src/api/mcp/engines/mcp_personalization_engine.py
"""
MCPPersonalizationEngine - Motor de Personalización Avanzado para Fase 2
========================================================================

Motor de personalización que integra:
- Análisis profundo de preferencias de usuario por mercado
- Personalización cultural y lingüística avanzada  
- Integración con Claude para respuestas contextualizadas
- Machine learning para patrones de comportamiento
- Optimización de recomendaciones por mercado específico

REFACTORIZADO: Uso de configuración centralizada Claude.
Eliminado hardcoding de modelos.

Integración: MCPConversationStateManager + OptimizedConversationAIManager + HybridRecommender
"""

import json
import time
import logging
import hashlib
import asyncio  # ✅ ADDED: For timeout handling
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
# from anthropic import Anthropic
from anthropic import AsyncAnthropic

# 🚀 NUEVA IMPORTACIÓN: Configuración centralizada Claude
from src.api.core.claude_config import get_claude_config_service

# ✅ ENTERPRISE MIGRATION: Using ServiceFactory for Redis  
# Legacy import removed - using ServiceFactory
# NOTE: ServiceFactory import moved to avoid circular imports

from src.api.mcp.conversation_state_manager import (
    MCPConversationStateManager, 
    MCPConversationContext,
    ConversationStage,
    UserMarketPreferences,
)
from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
from src.api.mcp.models.mcp_models import (
    MarketConfig, 
    RecommendationMCP, 
    ProductMCP,
    IntentType
)
# Liquid AI integration
import os
from src.api.core.llm_client import UnifiedLLMClient, LLMResponse
from src.api.core.claude_config import LFM_MCP_CONFIG

logger = logging.getLogger(__name__)

class PersonalizationStrategy(Enum):
    """Estrategias de personalización disponibles"""
    BEHAVIORAL = "behavioral"           # Basado en comportamiento pasado
    CULTURAL = "cultural"               # Adaptación cultural por mercado
    CONTEXTUAL = "contextual"           # Contexto actual de conversación
    PREDICTIVE = "predictive"           # Predicción de intenciones futuras
    HYBRID = "hybrid"                   # Combinación de todas las estrategias

@dataclass
class PersonalizationProfile:
    """Perfil de personalización completo del usuario"""
    user_id: str
    market_preferences: Dict[str, UserMarketPreferences]
    behavioral_patterns: Dict[str, Any]
    conversation_style: str
    purchase_propensity: float
    category_affinities: Dict[str, float]
    price_sensitivity_curve: Dict[str, float]  # price_range -> sensitivity
    temporal_patterns: Dict[str, Any]
    cross_market_insights: Dict[str, Any]
    last_updated: float

@dataclass
class PersonalizationContext:
    """Contexto específico para personalización"""
    mcp_context: MCPConversationContext
    personalization_profile: PersonalizationProfile
    market_config: MarketConfig
    real_time_signals: Dict[str, Any]
    conversation_momentum: float
    urgency_indicators: List[str]

class MCPPersonalizationEngine:
    """
    Motor de personalización avanzado que combina análisis de comportamiento,
    adaptación cultural y machine learning para generar experiencias 
    conversacionales altamente personalizadas por mercado.
    """
    
    def __init__(
        self,
        redis_service=None,  # ✅ ENTERPRISE: Use service instead of client
        redis_client = None,  # Legacy compatibility - will use ServiceFactory
        anthropic_client: AsyncAnthropic = None,
        conversation_manager: OptimizedConversationAIManager = None,
        state_manager: MCPConversationStateManager = None,
        profile_ttl: int = 7 * 24 * 3600,  # 7 days
        enable_ml_predictions: bool = True,
        shopify_client=None,  # Inyeccion para resolucion lazy de precios
    ):
        """
        Inicializa el motor de personalización.
        
        Args:
            redis_client: Cliente Redis para persistencia
            anthropic_client: Cliente Claude para generación de respuestas
            conversation_manager: Gestor de conversaciones optimizado
            state_manager: Gestor de estado conversacional MCP
            profile_ttl: TTL para perfiles de personalización
            enable_ml_predictions: Habilitar predicciones ML
        """
        # 🚀 REFACTORIZADO: Configuración centralizada Claude
        self.claude_config = get_claude_config_service()

        # Leer flag directamente de env (no via lru_cache — lección aprendida 21/03)
        self._lfm_mcp_enabled = os.environ.get('LFM_MCP_ENABLED', 'false').lower() == 'true'
        if self._lfm_mcp_enabled:
            self._lfm_client = UnifiedLLMClient(
                provider=LFM_MCP_CONFIG['provider'],
                model=LFM_MCP_CONFIG['model'],
                max_tokens=LFM_MCP_CONFIG['max_tokens'],
                temperature=LFM_MCP_CONFIG['temperature'],
            )
            logger.info('LFM MCP personalisation enabled: model=%s', LFM_MCP_CONFIG['model'])
        else:
            self._lfm_client = None
            logger.info('LFM MCP personalisation disabled — using Claude')
        
        # ✅ ENTERPRISE: Support both service and client approaches
        self.redis_service = redis_service
        self.redis = redis_client  # Legacy compatibility
        # Cliente Shopify para resolucion lazy de precios por turno.
        # Opcional: si es None, _format_price_for_market() usa CLP_RATES fallback.
        self.shopify_client = shopify_client
        
        # ✅ DEFENSIVE: Log Redis status for debugging
        if self.redis_service:
            logger.info("✅ MCPPersonalizationEngine: Using Redis service")
        elif self.redis:
            logger.info("✅ MCPPersonalizationEngine: Using Redis client (legacy)")
        else:
            logger.warning("⚠️ MCPPersonalizationEngine: No Redis available - running in fallback mode")
        self.claude = anthropic_client
        self.conversation_manager = conversation_manager
        self.state_manager = state_manager
        self.profile_ttl = profile_ttl
        self.enable_ml_predictions = enable_ml_predictions
        
        # Configuración de mercados
        self.market_configs = self._load_market_configurations()
        
        # Prefixes Redis
        self.PROFILE_PREFIX = "mcp:personalization:profile"
        self.INSIGHTS_PREFIX = "mcp:personalization:insights"
        self.ML_MODEL_PREFIX = "mcp:personalization:ml_model"
        
        # Estrategias de personalización
        self.personalization_strategies = {
            PersonalizationStrategy.BEHAVIORAL: self._behavioral_personalization,
            PersonalizationStrategy.CULTURAL: self._cultural_personalization,
            PersonalizationStrategy.CONTEXTUAL: self._contextual_personalization,
            PersonalizationStrategy.PREDICTIVE: self._predictive_personalization,
            PersonalizationStrategy.HYBRID: self._hybrid_personalization
        }
        
        # Métricas internas extendidas
        self.metrics = {
            "personalizations_generated": 0,
            "profile_updates": 0,
            "ml_predictions": 0,
            "cultural_adaptations": 0,
            "avg_personalization_time_ms": 0.0,
            "claude_model_tier": self.claude_config.claude_model_tier.value,
            "configuration_source": "centralized"
        }
        
        logger.info(f"🎯 MCPPersonalizationEngine initialized with centralized Claude config: {self.claude_config.claude_model_tier.value}")
    
    async def generate_personalized_response(
        self,
        mcp_context: MCPConversationContext,
        recommendations: List[Dict],
        strategy: PersonalizationStrategy = None,  # ✅ CAMBIO: None permite auto-detección
        detected_language: Optional[str] = None,   # FIX (19/04/2026): idioma ya detectado por router
    ) -> Dict[str, Any]:
        """
        Genera respuesta altamente personalizada usando estrategia especificada o auto-detectada.
        
        Args:
            mcp_context: Contexto conversacional MCP
            recommendations: Recomendaciones base a personalizar
            strategy: Estrategia de personalización a usar (None = auto-detección)
            detected_language: Idioma ya detectado por el router (None = re-detectar desde query).
                Cuando se provee, evita que el engine re-detecte el idioma con _detect_user_language(),
                que tiene una lista de keywords limitada y falla con contracciones (i'm, can't)
                y queries cortas sin artículos.
            
        Returns:
            Dict con respuesta personalizada, recomendaciones adaptadas y metadata

        FIX (27/03/2026): conversational_response es ahora siempre un str puro
        (devuelto por _generate_claude_personalized_response tras el refactor).
        El dict de respuesta lo usa directamente como "personalized_response" — sin
        envolturas de dict.  conversation_enhancement usa safe defaults porque la
        versión string no lleva esas claves.
        """
        start_time = time.time()
        
        try:
            # ✅ NUEVA FUNCIONALIDAD: Auto-detección de estrategia
            # if strategy is None:
            #     strategy = await self._determine_optimal_strategy(
            #         mcp_context.user_message, 
            #         mcp_context.market_id,
            #         mcp_context.user_id
            #     )
            #     logger.info(f"Auto-detected strategy: {strategy.value} for query: '{mcp_context.user_message[:50]}...'")
            # ✅ NUEVA FUNCIONALIDAD: Auto-detección de estrategia
            if strategy is None:
                # ✅ FIXED: Extract user query from context properly
                current_query = None
                if hasattr(mcp_context, 'current_query'):
                    current_query = mcp_context.current_query
                elif mcp_context.turns and len(mcp_context.turns) > 0:
                    current_query = mcp_context.turns[-1].user_query  # Last turn's query
                else:
                    current_query = "general query"  # Fallback
                
                strategy = await self._determine_optimal_strategy(
                    current_query,  # ✅ FIXED: Use extracted query
                    mcp_context.current_market_id,
                    mcp_context.user_id
                )
                
                # ✅ DEFENSIVE: Ensure strategy is never None
                if strategy is None:
                    logger.warning(f"_determine_optimal_strategy returned None, falling back to HYBRID")
                    strategy = PersonalizationStrategy.HYBRID
                    
                logger.info(f"Auto-detected strategy: {strategy.value} for query: '{current_query[:50]}...'")
            
            # ✅ ULTIMATE VALIDATION: Final check before proceeding
            if strategy is None:
                logger.error("Critical error: strategy is still None - forcing HYBRID")
                strategy = PersonalizationStrategy.HYBRID   
           
            # 1. Cargar/actualizar perfil de personalización
            personalization_profile = await self._get_or_create_personalization_profile(
                mcp_context.user_id
            )
            
            # 2. Construir contexto de personalización
            personalization_context = await self._build_personalization_context(
                mcp_context, personalization_profile
            )
            
            # 3. Aplicar estrategia de personalización
            personalized_result = await self.personalization_strategies[strategy](
                personalization_context, recommendations
            )
            
            # 4. Generar respuesta conversacional personalizada con Claude
            # FIX (27/03/2026): _generate_claude_personalized_response ahora devuelve
            # siempre un str puro, nunca un dict. No llamar .get() sobre el resultado.
            conversational_response = await self._generate_claude_personalized_response(
                personalization_context, personalized_result,
                detected_language=detected_language,  # FIX (19/04/2026): propagar idioma del router
            )
            
            # 5. Actualizar perfil con nuevos insights
            await self._update_personalization_profile(
                personalization_profile, mcp_context, personalized_result
            )
            
            # 6. Registrar métricas y analytics
            processing_time = (time.time() - start_time) * 1000
            await self._record_personalization_analytics(
                mcp_context, strategy, processing_time
            )
            
            # 7. Construir respuesta final
            # conversational_response es un str puro — conversation_enhancement usa defaults
            # seguros porque ya no hay dict con esas claves que extraer.
            response = {
                "personalized_response": conversational_response,  # str
                "personalized_recommendations": personalized_result["recommendations"],
                "personalization_metadata": {
                    "strategy_used": strategy.value,
                    "strategy_auto_detected": strategy is None,  # ✅ AÑADIDO
                    "personalization_score": personalized_result.get("personalization_score", 0.0),
                    "cultural_adaptation": personalized_result.get("cultural_adaptation", {}),
                    "behavioral_insights": personalized_result.get("behavioral_insights", {}),
                    "market_optimization": personalized_result.get("market_optimization", {}),
                    "processing_time_ms": processing_time
                },
                # conversation_enhancement preserved for API consumers that expect it,
                # but populated with safe defaults since the response is now a string.
                "conversation_enhancement": {
                    "tone_adaptation": "standard",
                    "cultural_context": {},
                    "personalization_elements": [],
                    "engagement_hooks": []
                }
            }
            
            self.metrics["personalizations_generated"] += 1
            self.metrics["avg_personalization_time_ms"] = (
                (self.metrics["avg_personalization_time_ms"] * (self.metrics["personalizations_generated"] - 1) + 
                 processing_time) / self.metrics["personalizations_generated"]
            )
            
            logger.info(f"Generated personalized response for user {mcp_context.user_id} using {strategy.value} strategy")
            return response
            
        except Exception as e:
            logger.error(
                "Error generating personalized response: %s",
                e,
                exc_info=True,  # FIX (18/04/2026): traceback completo en GCP Logs
            )
            # ✅ SAFE FALLBACK: Ensure we always return a valid response
            if strategy is None:
                strategy = PersonalizationStrategy.HYBRID
            # Fallback a respuesta estándar
            return await self._fallback_personalized_response(mcp_context, recommendations)
    
    async def _determine_optimal_strategy(
        self, 
        user_query: str,  # ✅ FIXED: Use direct parameter instead of mcp_context.user_message
        market_id: str, 
        user_id: str
    ) -> PersonalizationStrategy:
        """
        Determina la estrategia óptima de personalización basada en análisis de query,
        historial del usuario y contexto de mercado.
        
        Args:
            user_query: Query del usuario a analizar  # ✅ FIXED: Updated parameter name
            market_id: ID del mercado para contexto cultural
            user_id: ID del usuario para análisis histórico
            
        Returns:
            PersonalizationStrategy más apropiada
        """
        try:
            # Análisis de patrones en el mensaje
            message_lower = user_query.lower()  # ✅ FIXED: Use parameter instead of user_message
            
            # 1. BEHAVIORAL: Referencias al comportamiento pasado
            behavioral_indicators = [
                "similar", "like before", "bought", "purchased", "last time", 
                "previously", "again", "same as", "repeat", "reorder",
                "my usual", "favorites", "preferred", "typically"
            ]
            
            # 2. CULTURAL: Referencias culturales y regionales
            cultural_indicators = [
                "popular", "trending", "in my region", "local", "traditional",
                "cultural", "typical", "common here", "everyone", "most people",
                "in my country", "popular here", "local style", "regional"
            ]
            
            # 3. CONTEXTUAL: Situaciones específicas y ocasiones
            contextual_indicators = [
                "gift", "present", "birthday", "anniversary", "wedding", "party",
                "work", "office", "meeting", "date", "dinner", "event", "occasion",
                "vacation", "travel", "weekend", "special", "formal", "casual"
            ]
            
            # 4. PREDICTIVE: Indicadores de intención futura o exploración
            predictive_indicators = [
                "might", "maybe", "considering", "thinking about", "planning",
                "future", "next", "eventually", "looking for", "searching",
                "need", "want", "wish", "dream", "goal", "aspire"
            ]
            
            # Calcular scores para cada estrategia
            behavioral_score = sum(1 for indicator in behavioral_indicators if indicator in message_lower)
            cultural_score = sum(1 for indicator in cultural_indicators if indicator in message_lower)
            contextual_score = sum(1 for indicator in contextual_indicators if indicator in message_lower)
            predictive_score = sum(1 for indicator in predictive_indicators if indicator in message_lower)
            
            # Pesos adicionales basados en contexto
            # Obtener historial del usuario para ajustar scores
            user_profile = await self._get_user_strategy_history(user_id)
            
            # Ajustar scores basado en historial
            if user_profile:
                if user_profile.get("has_purchase_history", False):
                    behavioral_score += 1
                if user_profile.get("cultural_preference_detected", False):
                    cultural_score += 1
                if user_profile.get("frequent_contextual_queries", False):
                    contextual_score += 1
            
            # Ajustar por mercado
            market_weights = self._get_market_strategy_weights(market_id)
            behavioral_score *= market_weights.get("behavioral", 1.0)
            cultural_score *= market_weights.get("cultural", 1.0)
            contextual_score *= market_weights.get("contextual", 1.0)
            predictive_score *= market_weights.get("predictive", 1.0)
            
            # Determinar estrategia ganadora
            scores = {
                PersonalizationStrategy.BEHAVIORAL: behavioral_score,
                PersonalizationStrategy.CULTURAL: cultural_score,
                PersonalizationStrategy.CONTEXTUAL: contextual_score,
                PersonalizationStrategy.PREDICTIVE: predictive_score
            }
            
            # Encontrar la estrategia con mayor score
            max_score = max(scores.values())
            
            # ✅ FASE 2: MEJORA - Weighted Strategy Selection con Probabilistic Selection
            # Si no hay clara ganadora o scores muy bajos, usar HYBRID
            if max_score < 0.5:
                logger.info(f"Using HYBRID strategy - scores too low: {scores}")
                return PersonalizationStrategy.HYBRID
            
            # ✅ NUEVA FUNCIONALIDAD: Manejo inteligente de empates y selección probabilística
            if list(scores.values()).count(max_score) > 1:
                logger.info(f"Multiple strategies tied with max score {max_score}: {scores}")
                
                # Identificar estrategias empatadas en el máximo score
                tied_strategies = [(strategy, score) for strategy, score in scores.items() 
                                 if score == max_score]
                
                # Selección probabilística ponderada entre estrategias empatadas
                if len(tied_strategies) > 1:
                    strategies = [strategy for strategy, _ in tied_strategies]
                    weights = [score for _, score in tied_strategies]
                    
                    # Normalizar pesos para probabilidades
                    weight_sum = sum(weights)
                    probabilities = [w / weight_sum for w in weights] if weight_sum > 0 else [1/len(weights)] * len(weights)
                    
                    # Selección probabilística usando numpy.random.choice
                    selected_strategy = np.random.choice(strategies, p=probabilities)
                    
                    logger.info(
                        f"Probabilistic selection from tied strategies: {strategies} -> {selected_strategy.value}"
                    )
                    
                    # ✅ FASE 3: Registrar selección para A/B testing
                    await self._track_strategy_effectiveness(
                    selected_strategy, user_id, user_query, max_score, scores  # ✅ FIXED: Use user_query
                    )
                    
                    return selected_strategy
            
            # Si hay estrategia ganadora clara
            winning_strategy = max(scores.items(), key=lambda x: x[1])[0]
            
            # ✅ MEJORA: Verificar si hay competencia cercana (diferencia < 30%)
            second_best_score = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
            score_difference_ratio = (max_score - second_best_score) / max_score if max_score > 0 else 1
            
            # Si la diferencia es pequeña (< 30%), considerar selección probabilística
            if score_difference_ratio < 0.3 and max_score >= 0.7:
                # Obtener las top 2 estrategias para selección probabilística
                top_strategies = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:2]
                strategies = [strategy for strategy, _ in top_strategies]
                weights = [score for _, score in top_strategies]
                
                # Selección probabilística ponderada
                weight_sum = sum(weights)
                probabilities = [w / weight_sum for w in weights]
                
                selected_strategy = np.random.choice(strategies, p=probabilities)
                
                logger.info(
                    f"Close competition detected (diff: {score_difference_ratio:.2f}). "
                    f"Probabilistic selection: {[s.value for s in strategies]} -> {selected_strategy.value}"
                )
                
                # ✅ FASE 3: Registrar para A/B testing
                await self._track_strategy_effectiveness(
                    selected_strategy, user_id, user_query, max_score, scores  # ✅ FIXED: Use user_query
                )
                
                return selected_strategy
            
            # Selección estándar - ganador claro
            logger.info(
                f"Strategy determination for '{user_query[:30]}...': "  # ✅ FIXED: Use user_query
                f"{winning_strategy.value} (score: {max_score:.2f}, margin: {score_difference_ratio:.2f})"
            )
            
            # ✅ FASE 3: Registrar estrategia seleccionada para analytics
            await self._track_strategy_effectiveness(
                winning_strategy, user_id, user_query, max_score, scores  # ✅ FIXED: Use user_query
            )
            
            return winning_strategy
            
        except Exception as e:
            logger.warning(f"Error determining strategy, falling back to HYBRID: {e}")
            # ✅ GUARANTEED FALLBACK: Always return a valid strategy
            return PersonalizationStrategy.HYBRID
    
    async def _get_user_strategy_history(self, user_id: str) -> Dict[str, Any]:
        """
        Obtiene el historial de estrategias del usuario para ajustar decisiones.
        """
        try:
            # ✅ ENTERPRISE ALIGNED: Use proper RedisService API
            if not self.redis and not self.redis_service:
                logger.warning("Redis not available, returning empty strategy history")
                return {
                    "has_purchase_history": False,
                    "cultural_preference_detected": False,
                    "frequent_contextual_queries": False,
                    "created_at": time.time()
                }
            
            # Use redis_service (enterprise) with correct API
            redis_client = self.redis_service or self.redis
            
            cache_key = f"{self.PROFILE_PREFIX}:strategy_history:{user_id}"
            cached_history = await redis_client.get(cache_key)
            
            if cached_history:
                return json.loads(cached_history)
            
            # Si no hay cache, crear perfil básico
            basic_profile = {
                "has_purchase_history": False,
                "cultural_preference_detected": False,
                "frequent_contextual_queries": False,
                "created_at": time.time()
            }
            
            # ✅ ENTERPRISE API: Use ttl= instead of ex=
            if hasattr(redis_client, 'set'):
                # RedisService enterprise API
                await redis_client.set(cache_key, json.dumps(basic_profile), ttl=24 * 3600)
            else:
                # Fallback for legacy Redis clients
                logger.warning("Using legacy Redis client - performance may be degraded")
                await redis_client.setex(cache_key, 24 * 3600, json.dumps(basic_profile))
                
            return basic_profile
            
        except Exception as e:
            logger.warning(f"Error getting user strategy history: {e}")
            # ✅ SAFE FALLBACK: Return default profile
            return {
                "has_purchase_history": False,
                "cultural_preference_detected": False,
                "frequent_contextual_queries": False,
                "created_at": time.time()
            }
    
    def _get_market_strategy_weights(self, market_id: str) -> Dict[str, float]:
        """
        Obtiene pesos de estrategia especificos por mercado.

        Cada mercado activo en Shopify Admin tiene una entrada aqui con pesos
        que reflejan las caracteristicas culturales de sus clientes.

        MERCADOS ACTIVOS (confirmados Shopify Admin 28/03/2026):
          CL  Chile          -> CLP  (mercado primario)
          CH  Switzerland    -> CHF
          MX  Mexico         -> MXN
          ES  International  -> EUR  (27 regiones, representante europeo)

        REGLA: Cuando se anade un nuevo mercado en Shopify Admin, anadir
        una entrada aqui Y en _load_market_configurations().
        El fallback (todos en 1.0) aplica si el market_id no esta listado.
        """
        # Tabla unica — todos los mercados activos declarados juntos.
        # v2.2.0 (28/03/2026): Refactorizado de dict inicial + asignaciones
        # separadas a un unico dict consolidado. Comportamiento identico,
        # pero mas facil de mantener cuando se anaden mercados futuros.
        market_weights = {
            # -- Latinoamerica --------------------------------------------------
            "CL": {
                "behavioral": 1.0,
                "cultural": 1.2,   # Fuerte identidad cultural chilena
                "contextual": 1.1,  # Fiestas patrias, ocasiones sociales importantes
                "predictive": 0.9
            },
            "MX": {
                "behavioral": 1.0,
                "cultural": 1.2,
                "contextual": 1.2,  # Contexto familiar y social muy relevante
                "predictive": 0.8
            },
            # -- Europa --------------------------------------------------------
            "CH": {
                # Suiza: mercado premium y cosmopolita (4 idiomas oficiales).
                # Clientes valoran calidad y contexto de uso sobre identidad nacional.
                "behavioral": 1.1,  # Historial de compra relevante en mercado premium
                "cultural": 1.1,   # Menos dependiente de identidad nacional
                "contextual": 1.2,  # Regalo/lujo: el contexto de uso es clave
                "predictive": 1.0
            },
            "ES": {
                # Internacional/Europa: representante de 27 regiones.
                # Mayor peso cultural que en mercados anglosajones.
                "behavioral": 1.0,
                "cultural": 1.3,   # Mayor peso cultural en mercados europeos
                "contextual": 1.0,
                "predictive": 0.9
            },
            # -- Anglosajones --------------------------------------------------
            "US": {
                "behavioral": 1.2,  # Usuarios US valoran personalizacion por comportamiento
                "cultural": 0.8,
                "contextual": 1.1,
                "predictive": 1.0
            },
        }

        # Fallback: mercado no listado -> pesos neutros (todos 1.0)
        return market_weights.get(market_id, {
            "behavioral": 1.0,
            "cultural": 1.0,
            "contextual": 1.0,
            "predictive": 1.0
        })
    
    # ✅ FASE 3: A/B TESTING FRAMEWORK - Strategy Effectiveness Tracking
    async def _track_strategy_effectiveness(
    self,
    strategy: PersonalizationStrategy,
    user_id: str,
    user_query: str,  # ✅ FIXED: Parameter name corrected
    score: float,
    all_scores: Dict[PersonalizationStrategy, float]
    ) -> None:
        """
        Sistema de tracking de efectividad de estrategias para A/B testing y mejora continua.
        
        Registra datos de selección de estrategias para:
        - Análisis de performance por estrategia
        - Identificación de patrones de éxito
        - A/B testing automático
        - Optimización continua del algoritmo de selección
        
        Args:
            strategy: Estrategia seleccionada
            user_id: ID del usuario
            user_query: Query original del usuario
            score: Score de la estrategia seleccionada
            all_scores: Scores de todas las estrategias evaluadas
        """
        try:
            # Generar hash único para la selección
            selection_id = hashlib.md5(
                f"{user_id}_{strategy.value}_{int(time.time())}_{user_query[:20]}".encode()  # ✅ FIXED: Use user_query
            ).hexdigest()[:12]
            
            # Preparar datos de tracking
            tracking_data = {
                "selection_id": selection_id,
                "strategy_selected": strategy.value,
                "user_id": user_id,
                "query_length": len(user_query),  # ✅ FIXED: Use user_query
                "selected_score": float(score),
                "all_strategy_scores": {
                    s.value: float(sc) for s, sc in all_scores.items()
                },
                "timestamp": time.time(),
                "market_context": {
                    "hour_of_day": datetime.now().hour,
                    "day_of_week": datetime.now().weekday()
                },
                "competition_analysis": {
                    "second_best_score": sorted(all_scores.values(), reverse=True)[1] if len(all_scores) > 1 else 0,
                    "score_variance": float(np.var(list(all_scores.values()))),
                    "clear_winner": score > max(v for k, v in all_scores.items() if k != strategy) * 1.3 if len(all_scores) > 1 else True
                }
            }
            
            # ✅ ENTERPRISE FIX (17/03/2026): Usar redis_service si está disponible,
            # fallback a redis (legacy). self.redis es None cuando el engine fue
            # creado via ServiceFactory.get_mcp_recommender() porque ese método
            # inyecta redis_service=redis_service, redis_client=None (default).
            # El bug causaba: "Error recording personalization analytics:
            # 'NoneType' object has no attribute 'set'"
            redis_client = self.redis_service or self.redis
            if not redis_client:
                logger.warning("Redis not available - skipping strategy effectiveness tracking")
                return

            # Almacenar en Redis con TTL de 30 días para análisis
            effectiveness_key = f"strategy_effectiveness:{strategy.value}:{user_id}:{selection_id}"
            await redis_client.set(
                effectiveness_key,
                json.dumps(tracking_data),
                ttl=30 * 24 * 3600  # 30 días; RedisService usa ttl= (no ex=)
            )

            # Mantener contador agregado por estrategia.
            # RedisService no expone incr/expire nativos — simulamos con get/set.
            strategy_counter_key = f"strategy_usage_counter:{strategy.value}"
            current_count_raw = await redis_client.get(strategy_counter_key)
            current_count = int(current_count_raw) if current_count_raw else 0
            await redis_client.set(
                strategy_counter_key,
                str(current_count + 1),
                ttl=90 * 24 * 3600  # 90 días
            )
            
            logger.debug(
                f"Strategy effectiveness tracked: {strategy.value} "
                f"(score: {score:.2f}, competition: {tracking_data['competition_analysis']['score_variance']:.3f})"
            )
            
        except Exception as e:
            logger.error(f"Error tracking strategy effectiveness: {e}")
            # No fallar la operación principal si hay error en tracking
    
    # ✅ MÉTODO PÚBLICO: Obtener métricas A/B testing para dashboard
    async def get_strategy_effectiveness_report(self, days_back: int = 7) -> Dict[str, Any]:
        """
        Genera reporte de efectividad de estrategias para análisis y optimización.
        
        Args:
            days_back: Días hacia atrás para el análisis
            
        Returns:
            Reporte completo de efectividad por estrategia
        """
        try:
            cutoff_time = time.time() - (days_back * 24 * 3600)
            report = {
                "analysis_period": {
                    "days_back": days_back,
                    "start_time": cutoff_time,
                    "end_time": time.time(),
                    "generated_at": datetime.utcnow().isoformat()
                },
                "strategies": {},
                "global_insights": {},
                "usage_distribution": {},
                "recommendations": []
            }
            
            # Analizar cada estrategia
            total_usage = 0
            for strategy in PersonalizationStrategy:
                strategy_data = await self._analyze_single_strategy_performance(
                    strategy, cutoff_time
                )
                report["strategies"][strategy.value] = strategy_data
                total_usage += strategy_data.get("usage_count", 0)
            
            # Calcular distribución de uso
            for strategy_name, data in report["strategies"].items():
                usage_count = data.get("usage_count", 0)
                report["usage_distribution"][strategy_name] = {
                    "count": usage_count,
                    "percentage": (usage_count / max(total_usage, 1)) * 100
                }
            
            # Generar insights globales
            report["global_insights"] = self._generate_global_strategy_insights(
                report["strategies"]
            )
            
            # Generar recomendaciones
            report["recommendations"] = self._generate_strategy_optimization_recommendations(
                report["strategies"], report["usage_distribution"]
            )
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating strategy effectiveness report: {e}")
            return {"error": "Failed to generate report"}
    
    async def _analyze_single_strategy_performance(
        self, 
        strategy: PersonalizationStrategy, 
        cutoff_time: float
    ) -> Dict[str, Any]:
        """
        Analiza el performance de una estrategia específica.
        """
        try:
            # ✅ ENTERPRISE FIX (17/03/2026): Usar redis_service si está disponible,
            # fallback a redis (legacy). Método de dashboard — no en path crítico,
            # pero debe ser consistente con el patrón enterprise.
            redis_client = self.redis_service or self.redis
            if not redis_client:
                return {
                    "strategy": strategy.value,
                    "usage_count": 0,
                    "recent_selections": 0,
                    "avg_score": 0.0,
                    "error": "Redis not available"
                }

            # Obtener contador de uso
            strategy_counter_key = f"strategy_usage_counter:{strategy.value}"
            usage_count = await redis_client.get(strategy_counter_key)
            usage_count = int(usage_count) if usage_count else 0

            # Buscar datos de efectividad recientes
            effectiveness_pattern = f"strategy_effectiveness:{strategy.value}:*"
            effectiveness_keys = await redis_client.keys(effectiveness_pattern)

            recent_data = []
            total_score = 0.0
            competition_scores = []

            for key in effectiveness_keys[:50]:  # Limitar a últimas 50 para performance
                data = await redis_client.get(key)
                if data:
                    try:
                        effectiveness_data = json.loads(data)
                        if effectiveness_data.get("timestamp", 0) >= cutoff_time:
                            recent_data.append(effectiveness_data)
                            total_score += effectiveness_data.get("selected_score", 0)
                            competition_scores.append(
                                effectiveness_data.get("competition_analysis", {}).get("score_variance", 0)
                            )
                    except json.JSONDecodeError:
                        continue
            
            # Calcular métricas
            avg_score = total_score / max(len(recent_data), 1)
            avg_competition = np.mean(competition_scores) if competition_scores else 0
            
            return {
                "strategy": strategy.value,
                "usage_count": usage_count,
                "recent_selections": len(recent_data),
                "avg_score": round(avg_score, 3),
                "avg_competition_level": round(avg_competition, 3),
                "performance_trend": "stable",  # Simplificado
                "last_used": max(
                    [d.get("timestamp", 0) for d in recent_data], default=0
                )
            }
            
        except Exception as e:
            logger.error(f"Error analyzing strategy {strategy.value}: {e}")
            return {
                "strategy": strategy.value,
                "usage_count": 0,
                "recent_selections": 0,
                "avg_score": 0.0,
                "error": str(e)
            }
    
    def _generate_global_strategy_insights(self, strategies_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Genera insights globales comparando todas las estrategias.
        """
        try:
            valid_strategies = {
                k: v for k, v in strategies_data.items() 
                if v.get("usage_count", 0) > 0 and "error" not in v
            }
            
            if not valid_strategies:
                return {"insight": "No sufficient data for analysis"}
            
            # Ranking por performance
            strategy_ranking = sorted(
                valid_strategies.items(),
                key=lambda x: x[1].get("avg_score", 0),
                reverse=True
            )
            
            insights = {
                "top_performing_strategy": strategy_ranking[0][0] if strategy_ranking else None,
                "performance_ranking": [
                    {
                        "strategy": name,
                        "avg_score": data.get("avg_score", 0),
                        "usage_count": data.get("usage_count", 0)
                    } for name, data in strategy_ranking
                ],
                "total_active_strategies": len(valid_strategies),
                "avg_performance_across_strategies": round(
                    np.mean([data.get("avg_score", 0) for data in valid_strategies.values()]), 3
                ),
                "performance_variance": round(
                    np.var([data.get("avg_score", 0) for data in valid_strategies.values()]), 3
                )
            }
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating global insights: {e}")
            return {"error": "Failed to generate insights"}
    
    def _generate_strategy_optimization_recommendations(
        self, 
        strategies_data: Dict[str, Any], 
        usage_distribution: Dict[str, Any]
    ) -> List[str]:
        """
        Genera recomendaciones de optimización basadas en el análisis.
        """
        recommendations = []
        
        try:
            # Buscar estrategias con alto performance pero bajo uso
            for strategy, data in strategies_data.items():
                if "error" in data:
                    continue
                    
                avg_score = data.get("avg_score", 0)
                usage_percentage = usage_distribution.get(strategy, {}).get("percentage", 0)
                
                if avg_score > 0.7 and usage_percentage < 15:
                    recommendations.append(
                        f"Consider increasing usage of '{strategy}' strategy - high performance ({avg_score:.2f}) but low usage ({usage_percentage:.1f}%)"
                    )
                elif avg_score < 0.4 and usage_percentage > 40:
                    recommendations.append(
                        f"Review '{strategy}' strategy - high usage ({usage_percentage:.1f}%) but low performance ({avg_score:.2f})"
                    )
            
            # Verificar balance general
            usage_percentages = [d.get("percentage", 0) for d in usage_distribution.values()]
            if usage_percentages and max(usage_percentages) > 60:
                recommendations.append(
                    "Strategy usage is heavily skewed - consider rebalancing selection algorithm"
                )
            
            if not recommendations:
                recommendations.append("Strategy performance appears balanced - continue monitoring")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return ["Error generating recommendations - check logs"]
    
    async def analyze_user_journey(
        self, 
        user_id: str,
        market_id: str,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Analiza el journey completo del usuario para insights de personalización.
        
        Args:
            user_id: ID del usuario
            market_id: Mercado a analizar
            lookback_days: Días hacia atrás para el análisis
            
        Returns:
            Análisis completo del journey del usuario
        """
        try:
            # 1. Obtener sesiones históricas
            user_sessions = await self._get_user_historical_sessions(
                user_id, market_id, lookback_days
            )
            
            # 2. Analizar patrones conversacionales
            conversation_patterns = self._analyze_conversation_patterns(user_sessions)
            
            # 3. Detectar intenciones evolutivas
            intent_evolution = self._analyze_intent_evolution(user_sessions)
            
            # 4. Calcular métricas de engagement
            engagement_metrics = self._calculate_engagement_metrics(user_sessions)
            
            # 5. Identificar oportunidades de personalización
            personalization_opportunities = await self._identify_personalization_opportunities(
                user_sessions, conversation_patterns
            )
            
            # 6. Generar insights predictivos
            predictive_insights = {}
            if self.enable_ml_predictions:
                predictive_insights = await self._generate_predictive_insights(
                    user_id, market_id, user_sessions
                )
            
            journey_analysis = {
                "user_id": user_id,
                "market_id": market_id,
                "analysis_period": {
                    "lookback_days": lookback_days,
                    "sessions_analyzed": len(user_sessions),
                    "generated_at": datetime.utcnow().isoformat()
                },
                "conversation_patterns": conversation_patterns,
                "intent_evolution": intent_evolution,
                "engagement_metrics": engagement_metrics,
                "personalization_opportunities": personalization_opportunities,
                "predictive_insights": predictive_insights,
                "recommendations": self._generate_journey_recommendations(
                    conversation_patterns, engagement_metrics, predictive_insights
                )
            }
            
            # ✅ ENTERPRISE FIX (17/03/2026): Usar redis_service si está disponible,
            # fallback a redis (legacy). self.redis es None cuando el engine fue
            # creado via ServiceFactory.
            cache_key = f"{self.INSIGHTS_PREFIX}:{user_id}:{market_id}:journey_analysis"
            redis_client_journey = self.redis_service or self.redis
            if redis_client_journey:
                await redis_client_journey.set(
                    cache_key,
                    json.dumps(journey_analysis),
                    ttl=24 * 3600  # Cache por 24 horas; RedisService usa ttl= (no ex=)
                )
            else:
                logger.warning("Redis not available - journey analysis not cached")
            
            logger.info(f"Completed user journey analysis for {user_id} in market {market_id}")
            return journey_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing user journey: {e}")
            return {}
    
    async def optimize_for_market(
        self,
        recommendations: List[Dict],
        market_id: str,
        user_profile: Dict[str, Any]
    ) -> List[Dict]:
        """
        Optimiza recomendaciones específicamente para un mercado.
        
        Args:
            recommendations: Recomendaciones base
            market_id: ID del mercado objetivo
            user_profile: Perfil del usuario
            
        Returns:
            Recomendaciones optimizadas para el mercado
        """
        try:
            market_config = self.market_configs.get(market_id, {})
            
            # 1. Aplicar scoring específico del mercado
            market_scored_recs = self._apply_market_specific_scoring(
                recommendations, market_config, user_profile
            )
            
            # 2. Ajustar precios por mercado
            price_adjusted_recs = self._adjust_prices_for_market(
                market_scored_recs, market_config
            )
            
            # 3. Filtrar por disponibilidad en mercado
            available_recs = await self._filter_by_market_availability(
                price_adjusted_recs, market_id
            )
            
            # 4. Aplicar preferencias culturales
            culturally_adapted_recs = self._apply_cultural_preferences(
                available_recs, market_config, user_profile
            )
            
            # 5. Reordenar por relevancia de mercado
            final_recs = self._reorder_by_market_relevance(
                culturally_adapted_recs, market_config, user_profile
            )
            
            logger.info(f"Optimized {len(recommendations)} recommendations for market {market_id}")
            return final_recs
            
        except Exception as e:
            logger.error(f"Error optimizing for market {market_id}: {e}")
            return recommendations
    
    def get_personalization_metrics(self) -> Dict[str, Any]:
        """Retorna métricas del motor de personalización."""
        return {
            "engine_metrics": self.metrics.copy(),
            "strategies_available": [s.value for s in PersonalizationStrategy],
            "markets_configured": len(self.market_configs),
            "ml_predictions_enabled": self.enable_ml_predictions
        }
    
    # === MÉTODOS PRIVADOS - ESTRATEGIAS DE PERSONALIZACIÓN ===
    
    async def _behavioral_personalization(
        self,
        context: PersonalizationContext,
        recommendations: List[Dict]
    ) -> Dict[str, Any]:
        """Personalización basada en patrones de comportamiento."""
        profile = context.personalization_profile
        
        # Analizar patrones de interacción históricos
        interaction_patterns = profile.behavioral_patterns.get("interaction_patterns", {})
        
        # Aplicar filtros basados en comportamiento
        filtered_recs = []
        for rec in recommendations:
            behavioral_score = self._calculate_behavioral_score(rec, interaction_patterns)
            rec["behavioral_score"] = behavioral_score
            
            # Solo incluir recomendaciones con score mínimo
            if behavioral_score > 0.3:
                filtered_recs.append(rec)
        
        # Ordenar por score behavioral
        filtered_recs.sort(key=lambda x: x["behavioral_score"], reverse=True)
        
        return {
            "recommendations": filtered_recs,
            "personalization_score": 0.8,
            "behavioral_insights": {
                "patterns_analyzed": len(interaction_patterns),
                "score_distribution": self._get_score_distribution(filtered_recs)
            }
        }
    
    async def _cultural_personalization(
        self,
        context: PersonalizationContext,
        recommendations: List[Dict]
    ) -> Dict[str, Any]:
        """Personalización basada en adaptación cultural."""
        market_config = context.market_config
        cultural_prefs = market_config.localization.get("cultural_preferences", {})
        
        # Adaptar recomendaciones a preferencias culturales
        adapted_recs = []
        for rec in recommendations:
            cultural_adaptation = self._apply_cultural_adaptation(rec, cultural_prefs)
            rec.update(cultural_adaptation)
            adapted_recs.append(rec)
        
        self.metrics["cultural_adaptations"] += 1
        
        return {
            "recommendations": adapted_recs,
            "personalization_score": 0.7,
            "cultural_adaptation": {
                "market_id": market_config.id,
                "adaptations_applied": len(cultural_prefs),
                "cultural_elements": list(cultural_prefs.keys())
            }
        }
    
    async def _contextual_personalization(
        self,
        context: PersonalizationContext,
        recommendations: List[Dict]
    ) -> Dict[str, Any]:
        """Personalización basada en contexto actual de conversación."""
        mcp_context = context.mcp_context
        
        # Analizar contexto conversacional actual
        current_intent = mcp_context.primary_intent
        conversation_stage = mcp_context.conversation_stage
        
        # Adaptar recomendaciones al contexto
        contextual_recs = []
        for rec in recommendations:
            contextual_score = self._calculate_contextual_relevance(
                rec, current_intent, conversation_stage
            )
            rec["contextual_score"] = contextual_score
            contextual_recs.append(rec)
        
        # Ordenar por relevancia contextual
        contextual_recs.sort(key=lambda x: x["contextual_score"], reverse=True)
        
        return {
            "recommendations": contextual_recs,
            "personalization_score": 0.9,
            "contextual_insights": {
                "primary_intent": current_intent,
                "conversation_stage": conversation_stage.value,
                "context_factors": len(mcp_context.turns)
            }
        }
    
    async def _predictive_personalization(
        self,
        context: PersonalizationContext,
        recommendations: List[Dict]
    ) -> Dict[str, Any]:
        """Personalización basada en predicciones ML."""
        if not self.enable_ml_predictions:
            return await self._behavioral_personalization(context, recommendations)
        
        # Generar predicciones de intención futura
        future_intent_predictions = await self._predict_future_intents(context)
        
        # Adaptar recomendaciones a intenciones predichas
        predictive_recs = []
        for rec in recommendations:
            predictive_score = self._calculate_predictive_score(
                rec, future_intent_predictions
            )
            rec["predictive_score"] = predictive_score
            predictive_recs.append(rec)
        
        # Ordenar por score predictivo
        predictive_recs.sort(key=lambda x: x["predictive_score"], reverse=True)
        
        self.metrics["ml_predictions"] += 1
        
        return {
            "recommendations": predictive_recs,
            "personalization_score": 0.85,
            "predictive_insights": {
                "future_intents": future_intent_predictions,
                "prediction_confidence": 0.75,
                "model_version": "v1.0"
            }
        }
    
    async def _hybrid_personalization(
        self,
        context: PersonalizationContext,
        recommendations: List[Dict]
    ) -> Dict[str, Any]:
        """Personalización híbrida combinando todas las estrategias."""
        # Aplicar todas las estrategias
        behavioral_result = await self._behavioral_personalization(context, recommendations)
        cultural_result = await self._cultural_personalization(context, recommendations)
        contextual_result = await self._contextual_personalization(context, recommendations)
        
        # Combinar scores con pesos
        weights = {
            "behavioral": 0.3,
            "cultural": 0.2,
            "contextual": 0.4,
            "predictive": 0.1
        }
        
        # Crear diccionario de recomendaciones con scores combinados
        rec_scores = {}
        for rec in recommendations:
            rec_id = rec.get("id", str(hash(json.dumps(rec))))
            
            # Obtener scores de cada estrategia
            behavioral_score = next(
                (r["behavioral_score"] for r in behavioral_result["recommendations"] 
                 if r.get("id") == rec_id), 0.5
            )
            
            cultural_score = 0.7  # Score por adaptación cultural
            contextual_score = next(
                (r["contextual_score"] for r in contextual_result["recommendations"] 
                 if r.get("id") == rec_id), 0.5
            )
            predictive_score = 0.6  # Score predictivo base
            
            # Calcular score combinado
            combined_score = (
                weights["behavioral"] * behavioral_score +
                weights["cultural"] * cultural_score +
                weights["contextual"] * contextual_score +
                weights["predictive"] * predictive_score
            )
            
            rec_scores[rec_id] = {
                "recommendation": rec,
                "combined_score": combined_score,
                "individual_scores": {
                    "behavioral": behavioral_score,
                    "cultural": cultural_score,
                    "contextual": contextual_score,
                    "predictive": predictive_score
                }
            }
        
        # Ordenar por score combinado
        sorted_recs = sorted(
            rec_scores.values(),
            key=lambda x: x["combined_score"],
            reverse=True
        )
        
        # Extraer recomendaciones finales
        final_recommendations = []
        for item in sorted_recs:
            rec = item["recommendation"].copy()
            rec["hybrid_score"] = item["combined_score"]
            rec["score_breakdown"] = item["individual_scores"]
            final_recommendations.append(rec)
        
        return {
            "recommendations": final_recommendations,
            "personalization_score": 0.95,
            "hybrid_insights": {
                "strategies_combined": len(weights),
                "weights_used": weights,
                "avg_combined_score": np.mean([item["combined_score"] for item in sorted_recs])
            }
        }
    
    # === MÉTODOS AUXILIARES ===
    
    async def _generate_claude_personalized_response(
        self,
        context: PersonalizationContext,
        personalization_result: Dict[str, Any],
        detected_language: Optional[str] = None,  # FIX (19/04/2026): idioma del router
    ) -> str:
        """   
        Liquid Integration (16/04/2026):
        Genera respuesta personalizada usando Claude o LFM2-24B según feature flag.
        La lógica de prompt (system + user) no cambia — solo el cliente que lo ejecuta.

        FIX (27/03/2026): Este método ahora siempre devuelve un str puro, nunca un dict.

        FIX (19/04/2026 — BUG-LANG-MCP): Usar detected_language cuando está disponible
        en lugar de re-detectar con _detect_user_language(). El detector interno usaba
        tokenización simple que no manejaba contracciones inglesas ("i'm" ≠ "i") y
        tenía muy pocos keywords. Ahora:
          1. Si detected_language viene del router (resultado de detect_language_from_text
             con regex robustos) → usarlo directamente.
          2. Si no viene (llamadas legacy sin el parámetro) → usar _detect_user_language()
             como fallback de compatibilidad hacia atrás.

        Returns:
            str: El texto plano de respuesta para la burbuja de chat.
        """
        # FIX (18/04/2026): Las dos llamadas de prompt-building estaban FUERA de
        # cualquier try/except. Cuando _build_advanced_personalization_prompt lanza
        # 'NoneType' object is not subscriptable, la excepcion escapaba hasta el
        # outer except de generate_personalized_response() y se logaba como:
        #   "Error generating personalized response: 'NoneType' object is not subscriptable"
        # (sin "Claude" en el mensaje — evidencia del punto de escape confirmado por logs).
        # CAUSA: la funcion _build_advanced_personalization_prompt accede a algun
        # campo None con subscript ([]) — la linea exacta quedara expuesta en el
        # traceback que ahora se logara con exc_info=True.
        # Fix: envolver en try/except con prompts de fallback seguros para no
        # interrumpir el flujo. El traceback expondrá la raíz del crash.
        # FIX (18/04/2026) — LAZY RESOLUTION ANTES DE CUALQUIER PROMPT:
        # La llamada a _enrich_recommendations_lazy() estaba dentro del bloque
        # de la ruta Claude (mas abajo), lo que provocaba que la ruta LFM
        # construyera el prompt con CLP_RATES y retornara SIN enriquecer:
        #
        #   1. _build_advanced_personalization_prompt()  ← CLP_RATES warnings aqui
        #   2. LFM: return resp.content                 ← sale antes del enriquecimiento
        #   3. await _enrich_recommendations_lazy()     ← nunca se ejecuta con LFM
        #
        # Fix: mover el await AQUI, antes de construir ningun prompt.
        # Tanto LFM como Claude recibiran precios Shopify en el prompt.
        # La logica de fallback de _enrich_recommendations_lazy() garantiza
        # que si Shopify no esta disponible, el metodo retorna silenciosamente
        # y _format_price_for_market() usa CLP_RATES como ultimo recurso.
        _market_id_for_enrich = (
            context.mcp_context.current_market_id
            if hasattr(context.mcp_context, 'current_market_id')
            else "CL"
        )

        # F-01 FIX (28/05/2026 — price_clp=10): Enriquecer el producto actual junto
        # con los recomendados en una sola llamada lazy-price (cero overhead HTTP si
        # ya esta en Redis — cache hit ~1ms).
        #
        # Problema: ref_price_clp se calculaba desde top_recs[0], que tras
        # diversificacion puede ser un accesorio barato (ej. 10 CLP).
        # Solucion: fetch del precio del producto que el usuario ESTA VIENDO
        # (product_ctx.id), fuente semanticamente correcta para el tier de upsell.
        # Principio arquitectonico: precio Shopify autorizado (lazy-price) como
        # fuente primaria; conversion interna solo como ultimo fallback.
        _ctx_price_holder: Optional[Dict] = None
        _product_ctx_for_price = getattr(
            context.mcp_context, "current_product_context", None
        )
        if _product_ctx_for_price and _product_ctx_for_price.get("id"):
            # Holder minimo: solo necesitamos "id" para que _enrich_recommendations_lazy
            # lo incluya en el batch de Shopify. Tras la llamada tendra "market_prices".
            _ctx_price_holder = {"id": str(_product_ctx_for_price["id"])}

        # Construir lista de enriquecimiento: recs + producto actual (si aplica).
        # list() crea copia superficial para no mutar la lista original de recs.
        _recs_for_enrich = list(personalization_result.get("recommendations", []))
        if _ctx_price_holder is not None:
            _recs_for_enrich.append(_ctx_price_holder)

        await self._enrich_recommendations_lazy(
            recommendations=_recs_for_enrich,
            market_id=_market_id_for_enrich,
        )

        # Extraer precio CLP del producto actual (Shopify-autorizado, no conversion interna).
        # Si fallo (timeout / producto sin precios CL en Shopify), _ctx_ref_price_clp
        # queda en 0.0 y _build_advanced_personalization_prompt usa el fallback (top_recs[0]).
        _ctx_ref_price_clp: float = 0.0
        if _ctx_price_holder and "market_prices" in _ctx_price_holder:
            _mp_ctx = _ctx_price_holder["market_prices"]
            if "CL" in _mp_ctx:
                try:
                    _ctx_ref_price_clp = float(_mp_ctx["CL"].get("price", 0))
                except (TypeError, ValueError):
                    _ctx_ref_price_clp = 0.0
            logger.info(
                "F-01 ctx_product_price_clp=%.0f product_id=%s (fuente: Shopify lazy-price)",
                _ctx_ref_price_clp,
                _product_ctx_for_price.get("id", "?"),
            )

        # FIX (20/04/2026 — BUG-LANG-LFM): Calcular user_language ANTES de los builders
        # para que TANTO la ruta LFM como la ruta Claude usen el idioma correcto.
        #
        # Antes: user_language se calculaba DENTRO del bloque try: de la ruta Claude,
        # que solo se ejecuta si LFM no está activo. Con LFM_MCP_ENABLED=true, los builders
        # se llamaban sin user_language y usaban market_config.language (ej. 'de' para CH,
        # 'es' para CL) en lugar del idioma real del usuario.
        #
        # Solución: determinar user_language aquí, antes del try/except de builders.
        # Prioridad:
        #   1. detected_language del router (patrones regex robustos, maneja contracciones)
        #   2. _detect_user_language() desde la query actual (fallback legacy)
        if detected_language:
            _pre_user_language = detected_language
            logger.info(
                "[lang] LFM path: using router-detected language='%s'",
                _pre_user_language,
            )
        else:
            _query_for_pre_lang = (
                getattr(context.mcp_context, 'current_query', None)
                or (context.mcp_context.turns[-1].user_query if context.mcp_context.turns else "")
                or ""
            )
            _pre_user_language = self._detect_user_language(_query_for_pre_lang)
            logger.info(
                "[lang] LFM path: re-detected language='%s' for query='%s' (legacy fallback)",
                _pre_user_language, _query_for_pre_lang[:50],
            )

        try:
            system_prompt = self._build_personalized_system_prompt(
                context, user_language=_pre_user_language
            )
            user_prompt = self._build_advanced_personalization_prompt(
                context, personalization_result,
                user_language=_pre_user_language,
                ctx_ref_price_clp=_ctx_ref_price_clp,
            )
        except Exception as _prompt_build_err:
            logger.error(
                "prompt_build_error: %s — falling back to safe defaults",
                _prompt_build_err,
                exc_info=True,  # EXPONE traceback completo con linea exacta del crash
            )
            # Prompts de emergencia: suficientes para que LFM o Claude generen
            # una respuesta util sin bloquear el flujo completo.
            market_id = getattr(context.mcp_context, 'current_market_id', 'CL')
            current_query = (
                getattr(context.mcp_context, 'current_query', None)
                or "productos de moda"
            )
            recs_safe = (personalization_result or {}).get("recommendations", [])
            rec_titles = ", ".join(
                r.get("title", "producto") for r in recs_safe[:3]
            ) or "productos disponibles"
            system_prompt = (
                f"Eres un asistente de moda util. Responde brevemente al mercado {market_id}."
            )
            user_prompt = (
                f"El usuario busca: {current_query}\n"
                f"Productos sugeridos: {rec_titles}\n"
                "Recomienda de forma breve y personalizada."
            )

        # ── RUTA LFM (si flag activo) ──────────────────────────────────────────
        _lfm_failed = False  # flag para saber si LFM fallo y necesitamos el fallback
        if self._lfm_mcp_enabled and self._lfm_client:
            try:
                resp = await asyncio.wait_for(
                    self._lfm_client.complete(system_prompt, user_prompt),
                    timeout=10.0
                    # ── DISEÑO DEL TIMEOUT INNER LFM ───────────────────────────────────────
                    # Valor: 10s (inner). El outer timeout en mcp_conversation_handler.py
                    # es 12.0s desde que generate_personalized_response() inicia.
                    # Lazy-price tarda ~0.6s antes de que LFM empiece; por tanto:
                    #   inner dispara a: 0.6 + 10.0 = 10.6s desde el inicio del outer
                    #   outer dispara a: 12.0s desde el inicio del outer
                    # El inner (10.6s) dispara ANTES que el outer (12.0s), garantizando
                    # que _lfm_failed=True se ejecute y se omita la ruta Claude.
                    #
                    # Cold-start Together.ai: ~11-12s — supera este timeout.
                    # El PASO 8.5c (warmup al startup) y el PASO 8.7 (LFM keep-alive
                    # periódico cada 5 min) pre-calientan el modelo en Together.ai,
                    # eliminando cold starts en tráfico normal de producción.
                    # Warm: ~440ms — muy dentro del presupuesto de 10s.
                    #
                    # Diagnóstico confirmado 26/05/2026:
                    #   Turn 11 (cold):       11.34s → timeout | Turn 13 (semi-warm): 6.11s → ok
                    #   Turn 14 (fully warm):  0.44s → ok      | Mejora: 80.3% (1.973s total)
                )
                logger.info('LFM MCP response: model=%s in=%d out=%d',
                        resp.model, resp.input_tokens, resp.output_tokens)
                return resp.content
            except Exception as e:
                logger.warning('LFM MCP call failed, falling back to Claude: %s', e)
                _lfm_failed = True

        # ── RUTA CLAUDE (default o fallback) ──────────────────────────────────────
        # ⚠️ TODO TEMPORAL (Sprint httpx 24/05/2026):
        # Cuando LFM falla, el flujo llega aqui para usar Claude como fallback.
        # Con credito Anthropic agotado (HTTP 400), Claude ejecuta 3 retries
        # que acumulan ~580ms sin resultado util.
        # FIX TEMPORAL: si LFM fallo, retornar respuesta por defecto directamente.
        # CUANDO ELIMINAR: al integrar el modelo de reemplazo para Claude,
        # configurar las nuevas credenciales y eliminar el bloque marcado TEMPORAL.
        if _lfm_failed:  # TEMPORAL
            logger.info(
                "lfm_failed_claude_skipped: LFM timeout + Claude sin credito (400). "
                "TEMPORAL: eliminar cuando se integre el modelo de reemplazo."
            )
            return "Te ayudo a encontrar lo que buscas. ¿Qué te interesa hoy?"  # TEMPORAL

        # ── RUTA CLAUDE (default o fallback) ─────────────────────────────────
        model_config = self.claude_config.get_model_config()
        try:
            # Determinar el idioma de la query del usuario.
            #
            # FIX (19/04/2026 — BUG-LANG-MCP): Prioridad:
            #   1. detected_language del router (detect_language_from_text con regex robustos)
            #      → más fiable: maneja contracciones, usa patrones lookahead/lookbehind.
            #   2. _detect_user_language() local (fallback legacy)
            #      → menos fiable: lista de keywords limitada, tokenizador simple.
            #
            # Ejemplo de bug sin este fix:
            #   Query: "I'm looking for elegant dresses"
            #   _detect_user_language(): tokens=["i'm", "looking", "for"] → EN=0 → "es" ❌
            #   detect_language_from_text(): "looking" y "for" regex → EN=2 → "en" ✅
            if detected_language:
                user_language = detected_language
                logger.info("[lang] Using router-detected language='%s' (skipping re-detection)", user_language)
            else:
                user_query_for_lang = (
                    context.mcp_context.current_query
                    or (context.mcp_context.turns[-1].user_query if context.mcp_context.turns else "")
                    or ""
                )
                user_language = self._detect_user_language(user_query_for_lang)
                logger.info("[lang] Re-detected language='%s' for query='%s' (legacy fallback)",
                            user_language, user_query_for_lang[:50])

            personalization_prompt = self._build_advanced_personalization_prompt(
                context, personalization_result,
                user_language=user_language,
                ctx_ref_price_clp=_ctx_ref_price_clp,
            )

            # CLAUDE CALL con retry controlado por presupuesto de tiempo.
            #
            # DISEÑO DELIBERADO:
            # El handler externo (mcp_conversation_handler.py) envuelve esta función
            # con asyncio.wait_for(timeout=3.0). El retry loop interno debe respetar
            # ese presupuesto. El timeout=15 interno nunca se alcanza — el externo
            # cancela antes.
            #
            # PROBLEMA PREVIO:
            # asyncio.sleep(1) entre intentos consumía ~1s del presupuesto de 3.0s,
            # dejando <0.8s para el reintento. Claude Sonnet necesita ~1.5-2.5s →
            # el reintento siempre llegaba tarde y el handler lanzaba TimeoutError.
            #
            # FIX APLICADO:
            # sleep reducido a 0.05s (50ms) — suficiente para que la SDK libere el
            # descriptor de socket del intento fallido, sin consumir el presupuesto.
            # El intento 2 tiene ahora ~1.7s disponibles para completarse.
            model_config = self.claude_config.get_model_config()

            max_retries = 2
            timeout = 15  # interno; el externo (8.0s) lo cancela primero en prod
            response_text = "Te ayudo a encontrar lo que buscas. ¿Qué te interesa hoy?"
            
            for attempt in range(max_retries + 1):
                try:
                    # Llamada a Claude usando configuracion centralizada (no hardcoded)
                    claude_response = await asyncio.wait_for(
                        self.claude.messages.create(
                            model=model_config.model_name,      # <- lee CLAUDE_MODEL_TIER (Haiku)
                            system=self._build_personalized_system_prompt(context, user_language=user_language),
                            messages=[{"role": "user", "content": personalization_prompt}],
                            max_tokens=model_config.max_tokens,  # <- lee CLAUDE_MAX_TOKENS (200)
                            temperature=model_config.temperature  # <- consistente con claude_config
                        ),
                        timeout=timeout
                    )
                    
                    response_text = claude_response.content[0].text
                    break  # Success, exit retry loop
                    
                except asyncio.TimeoutError:
                    logger.warning(f"Claude API timeout on attempt {attempt + 1}/{max_retries + 1}")
                    if attempt < max_retries:
                        await asyncio.sleep(0.05)  # ← FIX: 1s→50ms; libera socket sin consumir presupuesto
                        
                except Exception as api_error:
                    logger.warning(f"Claude API error on attempt {attempt + 1}: {api_error}")
                    # Error 400 (billing) es permanente: reintentar no lo resuelve.
                    # Sin este check se desperdician ~580ms en 3 retries inutiles.
                    # Un 429 (rate-limit) o 5xx (server error) SI merece reintento.
                    if hasattr(api_error, 'status_code') and api_error.status_code == 400:
                        logger.warning(
                            "Claude billing error (400) — skipping remaining retries. "
                            "Add credits at console.anthropic.com/settings/billing."
                        )
                        break  # Salir del loop inmediatamente
                    if attempt < max_retries:
                        await asyncio.sleep(0.05)  # ← FIX: 1s→50ms; libera socket sin consumir presupuesto
            
            # FIX (27/03/2026): Extraer el string de texto plano de la respuesta.
            # Claude fue instruido a responder sin JSON ("Respuesta directa sin JSON"),
            # pero ocasionalmente devuelve un objeto JSON de todos modos. Si lo hace,
            # extraemos el texto de la clave "response"/"answer"/"content"/"text".
            # En ambos casos devolvemos un str puro — nunca un dict.
            raw = response_text.strip()
            if raw.startswith('{'):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        extracted = (
                            parsed.get("response")
                            or parsed.get("answer")
                            or parsed.get("text")
                            or parsed.get("content")
                            or raw  # último recurso: texto crudo
                        )
                        response_text = str(extracted) if not isinstance(extracted, str) else extracted
                except json.JSONDecodeError:
                    pass  # response_text ya es el string de Claude, mantenerlo

            logger.info(f"✅ Claude personalized response ready ({len(response_text)} chars)")
            return response_text

        except Exception as e:
            logger.error(f"Error generating Claude personalized response: {e}")
            return "Te ayudo a encontrar lo que buscas. ¿Qué te interesa hoy?"
    
    def _load_market_configurations(self) -> Dict[str, MarketConfig]:
        """Carga configuraciones de mercado.

        FIX (27/03/2026 — BUG-CLP-02): Añadido mercado 'CL' (Chile, CLP).
        Sin esta entrada, mcp_context.current_market_id='CL' caía en el
        fallback a 'US', haciendo que market_config.currency='USD' y
        market_config.language='en' en el prompt de Claude.
        """
        # Esta función cargaría desde base de datos o configuración
        # Por ahora, configuraciones predefinidas
        return {
            "US": MarketConfig(
                id="US",
                name="United States",
                currency="USD",
                language="en",
                timezone="America/New_York",
                scoring_weights={"price": 0.4, "brand": 0.3, "reviews": 0.3},
                localization={"cultural_preferences": {"communication_style": "direct"}},
                tax_rate=0.08,
                shipping_config={"free_shipping_threshold": 50.0}
            ),
            "ES": MarketConfig(
                id="ES",
                name="Spain",
                currency="EUR",
                language="es",
                timezone="Europe/Madrid",
                scoring_weights={"price": 0.3, "brand": 0.4, "reviews": 0.3},
                localization={"cultural_preferences": {"communication_style": "formal"}},
                tax_rate=0.21,
                shipping_config={"free_shipping_threshold": 40.0}
            ),
            "MX": MarketConfig(
                id="MX",
                name="Mexico",
                currency="MXN",
                language="es",
                timezone="America/Mexico_City",
                scoring_weights={"price": 0.5, "brand": 0.2, "reviews": 0.3},
                localization={"cultural_preferences": {"communication_style": "warm"}},
                tax_rate=0.16,
                shipping_config={"free_shipping_threshold": 800.0}
            ),
            # FIX v2.1.0 (27/03/2026): Mercado primario de AI-Shoppings.
            # Precio en CLP. Sin conversion interna (el MarketAdapter ya lo
            # normaliza en la FASE 5 del pipeline antes de llegar aqui).
            "CL": MarketConfig(
                id="CL",
                name="Chile",
                currency="CLP",
                language="es",
                timezone="America/Santiago",
                scoring_weights={"price": 0.4, "brand": 0.3, "reviews": 0.3},
                localization={"cultural_preferences": {"communication_style": "calido"}},
                tax_rate=0.19,                              # IVA Chile 19%
                shipping_config={"free_shipping_threshold": 50000.0}  # ~50 USD en CLP
            ),
            # v2.2.0 (28/03/2026): Switzerland confirmado en Shopify Admin.
            # Sin esta entrada, market_id="CH" caia al fallback "US" en
            # _build_personalization_context() -> Claude respondia en ingles con USD.
            # Idioma: aleman (mayoritario en Suiza). Tono: preciso y directo.
            # communication_style="preciso" refleja la cultura suiza de concision.
            "CH": MarketConfig(
                id="CH",
                name="Switzerland",
                currency="CHF",
                language="de",
                timezone="Europe/Zurich",
                scoring_weights={"price": 0.3, "brand": 0.4, "reviews": 0.3},
                localization={"cultural_preferences": {"communication_style": "preciso"}},
                tax_rate=0.077,                             # IVA Suiza 7.7%
                shipping_config={"free_shipping_threshold": 100.0}  # CHF 100 envio gratis
            ),
        }
    
    async def _get_or_create_personalization_profile(
        self, 
        user_id: str
    ) -> PersonalizationProfile:
        """Obtiene o crea perfil de personalización del usuario."""
        try:
            # ✅ DEFENSIVE: Check if redis is available
            if not self.redis and not self.redis_service:
                logger.warning(f"Redis not available, creating in-memory profile for {user_id}")
                # Return default profile without Redis
                return PersonalizationProfile(
                    user_id=user_id,
                    market_preferences={},
                    behavioral_patterns={},
                    conversation_style="standard",
                    purchase_propensity=0.5,
                    category_affinities={},
                    price_sensitivity_curve={"low": 0.3, "medium": 0.5, "high": 0.8},
                    temporal_patterns={},
                    cross_market_insights={},
                    last_updated=time.time()
                )
            
            # Use redis_service if available, fallback to redis
            redis_client = self.redis_service or self.redis
            
            profile_key = f"{self.PROFILE_PREFIX}:{user_id}"
            profile_data = await redis_client.get(profile_key)
            
            if profile_data:
                profile_dict = json.loads(profile_data)
                # Reconstruir objetos UserMarketPreferences
                market_prefs = {}
                for market_id, prefs_data in profile_dict.get("market_preferences", {}).items():
                    market_prefs[market_id] = UserMarketPreferences(**prefs_data)
                
                profile_dict["market_preferences"] = market_prefs
                return PersonalizationProfile(**profile_dict)
            else:
                # Crear nuevo perfil
                new_profile = PersonalizationProfile(
                    user_id=user_id,
                    market_preferences={},
                    behavioral_patterns={},
                    conversation_style="standard",
                    purchase_propensity=0.5,
                    category_affinities={},
                    price_sensitivity_curve={"low": 0.3, "medium": 0.5, "high": 0.8},
                    temporal_patterns={},
                    cross_market_insights={},
                    last_updated=time.time()
                )
                
                # Guardar nuevo perfil
                await self._save_personalization_profile(new_profile)
                return new_profile
                
        except Exception as e:
            logger.error(f"Error getting personalization profile for {user_id}: {e}")
            # ✅ SAFE FALLBACK: Retornar perfil básico en caso de error
            return PersonalizationProfile(
                user_id=user_id,
                market_preferences={},
                behavioral_patterns={},
                conversation_style="standard",
                purchase_propensity=0.5,
                category_affinities={},
                price_sensitivity_curve={"low": 0.3, "medium": 0.5, "high": 0.8},
                temporal_patterns={},
                cross_market_insights={},
                last_updated=time.time()
            )
    
    async def _build_personalization_context(
        self,
        mcp_context: MCPConversationContext,
        personalization_profile: PersonalizationProfile
    ) -> PersonalizationContext:
        """Construye contexto completo de personalización."""
        try:
            # Obtener configuración del mercado
            market_config = self.market_configs.get(
                mcp_context.current_market_id,
                self.market_configs.get("US")  # Fallback a US
            )
            
            # Analizar señales en tiempo real
            real_time_signals = await self._analyze_real_time_signals(mcp_context)
            
            # Calcular momentum conversacional
            conversation_momentum = self._calculate_conversation_momentum(mcp_context)
            
            # Detectar indicadores de urgencia
            urgency_indicators = self._detect_urgency_indicators(mcp_context)
            
            return PersonalizationContext(
                mcp_context=mcp_context,
                personalization_profile=personalization_profile,
                market_config=market_config,
                real_time_signals=real_time_signals,
                conversation_momentum=conversation_momentum,
                urgency_indicators=urgency_indicators
            )
            
        except Exception as e:
            logger.error(f"Error building personalization context: {e}")
            # Retornar contexto básico
            return PersonalizationContext(
                mcp_context=mcp_context,
                personalization_profile=personalization_profile,
                market_config=self.market_configs.get("US"),
                real_time_signals={},
                conversation_momentum=0.5,
                urgency_indicators=[]
            )
    
    async def _save_personalization_profile(self, profile: PersonalizationProfile):
        """Guarda perfil de personalización en Redis."""
        try:
            # ✅ DEFENSIVE: Check if redis is available
            if not self.redis and not self.redis_service:
                logger.warning(f"Redis not available, skipping profile save for {profile.user_id}")
                return
                
            # Use redis_service if available, fallback to redis
            redis_client = self.redis_service or self.redis
            
            profile_key = f"{self.PROFILE_PREFIX}:{profile.user_id}"
            
            # Serializar market_preferences correctamente
            serializable_profile = asdict(profile)
            market_prefs_serializable = {}
            for market_id, prefs in profile.market_preferences.items():
                market_prefs_serializable[market_id] = asdict(prefs)
            serializable_profile["market_preferences"] = market_prefs_serializable
            
            # ✅ ENTERPRISE API: Use ttl= instead of ex=
            if hasattr(redis_client, 'set') and hasattr(redis_client, '__class__') and 'RedisService' in str(redis_client.__class__):
                # RedisService enterprise API
                await redis_client.set(
                    profile_key,
                    json.dumps(serializable_profile),
                    ttl=self.profile_ttl
                )
            else:
                # Fallback for legacy Redis clients
                logger.warning("Using legacy Redis client - performance may be degraded")
                if hasattr(redis_client, 'set'):
                    # Standard Redis client with ex parameter
                    await redis_client.set(
                        profile_key,
                        json.dumps(serializable_profile),
                        ex=self.profile_ttl
                    )
                else:
                    logger.error("Redis client doesn't support required set operations")
                    return
            
            self.metrics["profile_updates"] += 1
            logger.debug(f"Saved personalization profile for user {profile.user_id}")
            
        except Exception as e:
            logger.error(f"Error saving personalization profile: {e}")
    
    async def _update_personalization_profile(
        self,
        profile: PersonalizationProfile,
        mcp_context: MCPConversationContext,
        personalization_result: Dict[str, Any]
    ):
        """Actualiza perfil con nuevos insights de la conversación."""
        try:
            # Actualizar patrones de comportamiento
            self._update_behavioral_patterns(profile, mcp_context)
            
            # Actualizar afinidades de categoría
            self._update_category_affinities(profile, personalization_result)
            
            # Actualizar estilo conversacional
            self._update_conversation_style(profile, mcp_context)
            
            # Actualizar propensión de compra
            self._update_purchase_propensity(profile, mcp_context)
            
            # Actualizar insights cross-market
            self._update_cross_market_insights(profile, mcp_context)
            
            # Actualizar timestamp
            profile.last_updated = time.time()
            
            # Guardar perfil actualizado
            await self._save_personalization_profile(profile)
            
        except Exception as e:
            logger.error(f"Error updating personalization profile: {e}")
    
    def _format_price_for_market(
        self,
        rec: Dict[str, Any],
        market_id: str,
        market_currency: str
    ) -> str:
        """Formatea el precio de un producto para el mercado indicado.

        Fuente de precio unica (Opcion A, 28/03/2026).
        Reemplaza las dos funciones locales identicas que existian en
        _build_advanced_personalization_prompt y _build_personalized_user_prompt.

        Prioridad de lectura:
          1. market_prices[market_id]  <- Opcion A: precio Shopify autorizado
          2. market_prices['CL']       <- fallback al precio nativo CLP
          3. Conversion manual con CLP_RATES <- ultimo recurso (deuda tecnica)

        Cuando se activa la Prioridad 3, emite un WARNING para facilitar la
        deteccion de productos sin market_prices en produccion.

        Args:
            rec:             Diccionario del producto (con o sin 'market_prices')
            market_id:       Codigo de mercado, ej. 'CL', 'CH', 'MX', 'ES'
            market_currency: Moneda destino del mercado, ej. 'CHF', 'CLP', 'EUR'

        Returns:
            String formateado, ej. 'CHF 110.36' o 'CLP 160,000'
        """
        market_prices = rec.get("market_prices") or {}

        # Prioridad 1: precio Shopify para este mercado exacto
        if market_id in market_prices:
            price_data = market_prices[market_id]
            price = price_data.get("price", 0)
            currency = price_data.get("currency", market_currency)

        # Prioridad 2: precio nativo CLP de Shopify (como referencia)
        elif "CL" in market_prices:
            price_data = market_prices["CL"]
            price = price_data.get("price", 0)
            currency = price_data.get("currency", "CLP")

        # Prioridad 3 (LAZY RESOLUTION): precio obtenido en tiempo real desde Shopify.
        # Este campo es inyectado por _fetch_and_inject_prices() justo antes de
        # construir el prompt de Claude, en paralelo con la llamada a Claude.
        # No tiene coste de latencia porque corre concurrentemente con Claude (~1.2s).
        # Se activa cuando el producto no paso por el enriquecimiento batch del startup
        # (por ejemplo, primeros 9 minutos despues de un restart) pero si por el
        # pre-fetch lazy de este turno.
        elif rec.get("_lazy_prices") and market_id in rec["_lazy_prices"]:
            price_data = rec["_lazy_prices"][market_id]
            price = price_data.get("price", 0)
            currency = price_data.get("currency", market_currency)

        # Prioridad 4: conversion manual hardcodeada (fallback de ultimo recurso)
        # Solo activa para productos sin market_prices Y sin lazy prices.
        # TASAS CORRECTAS (28/03/2026): CHF=0.00089 (no EUR=0.00096)
        # Verificacion: 124.000 CLP * 0.00089 = 110.36 CHF (coincide con ProductCard)
        else:
            # ALERTA: market_prices no disponible para este producto.
            # Causa tipica: pickle del TF-IDF cargado antes del deploy de Opcion A,
            # o producto insertado sin pasar por get_products_with_shopify_prices().
            # Este WARNING es la unica forma de detectarlo silenciosamente en produccion.
            logger.warning(
                "[OpcionA-fallback] product '%s' sin market_prices para mercado %s. "
                "Usando CLP_RATES hardcodeado. Verificar que el producto paso por "
                "get_products_with_shopify_prices() en el ultimo startup.",
                rec.get("id", "?"), market_id
            )
            CLP_RATES = {
                "CLP": 1.0, "CHF": 0.00089, "EUR": 0.00096,
                "USD": 0.00104, "MXN": 0.018, "COP": 4.1
            }
            try:
                raw_float = float(rec.get("price") or 0)
            except (TypeError, ValueError):
                raw_float = 0.0
            rate = CLP_RATES.get(market_currency, 1.0)
            price = raw_float * rate
            currency = market_currency

        try:
            price_float = float(price)
        except (TypeError, ValueError):
            price_float = 0.0

        # CLP/COP sin decimales; CHF/EUR/USD/MXN con 2 decimales
        if currency in ("CLP", "COP"):
            return f"{currency} {price_float:,.0f}"
        else:
            return f"{currency} {price_float:,.2f}"

    async def _fetch_and_inject_prices(
        self,
        recommendations: list,
        context: "PersonalizationContext"
    ) -> None:
        """
        Pre-fetch lazy de precios para los N productos recomendados.

        Consulta Shopify Admin GraphQL con una unica query que incluye
        un alias por cada (producto, mercado). Se ejecuta en paralelo
        con la llamada a Claude para que el overhead neto sea cero.

        Solo consulta los productos que NO tienen market_prices en RAM
        (es decir, que no pasaron por el enriquecimiento batch del startup).
        Los resultados se inyectan en rec["_lazy_prices"] para que
        _format_price_for_market() los use como Prioridad 3.

        Args:
            recommendations: Lista de dicts de productos recomendados.
            context:         PersonalizationContext con market_config.
        """
        import requests as _req_lib
        import re as _re
        import os
        # Filtrar solo los productos que aun no tienen precios de Shopify.
        # Si el batch de startup ya los enriquecio, no hay nada que hacer.
        products_needing_prices = [
            rec for rec in recommendations
            if not rec.get("market_prices")
        ]
        if not products_needing_prices:
            logger.debug("[lazy-price] Todos los productos ya tienen market_prices. Skip.")
            return

        ACTIVE_MARKETS = [
            {"market_id": "CL", "country_code": "CL"},
            {"market_id": "CH", "country_code": "CH"},
            {"market_id": "MX", "country_code": "MX"},
            {"market_id": "ES", "country_code": "ES"},
        ]

        # Construir URL y headers de Shopify GraphQL.
        shop_url = os.environ.get("SHOPIFY_SHOP_URL", "").rstrip("/")
        shop_host = shop_url.replace("https://", "").replace("http://", "")
        gql_url = f"https://{shop_host}/admin/api/2025-01/graphql.json"
        gql_headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
        }

        # Construir query con alias p{idx}_{market_id} por cada (producto, mercado).
        # Con 5 productos x 4 mercados = 20 aliases — muy por debajo del limite
        # de Shopify (1000 puntos de complexity). Sin riesgo de throttling.
        alias_fragments = []
        for idx, rec in enumerate(products_needing_prices):
            pid = str(rec.get("id", ""))
            gid = f"gid://shopify/Product/{pid}"
            for market in ACTIVE_MARKETS:
                alias_fragments.append(
                    f'p{idx}_{market["market_id"]}: product(id: "{gid}") {{\n'
                    f'  contextualPricing(context: {{country: {market["country_code"]}}}) {{\n'
                    f'    priceRange {{ minVariantPrice {{ amount currencyCode }} }}\n'
                    f'  }}\n'
                    f'}}'
                )

        bulk_query = (
            "query GetLazyPrices {\n"
            + "\n".join(alias_fragments)
            + "\n}"
        )

        try:
            # asyncio.to_thread: la libreria requests es sincrona.
            # Se ejecuta en el thread pool sin bloquear el event loop,
            # permitiendo que Claude trabaje concurrentemente.
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    _req_lib.post, gql_url,
                    json={"query": bulk_query},
                    headers=gql_headers,
                    timeout=10  # presupuesto conservador: Claude tarda 1.2s
                ),
                timeout=11  # asyncio timeout ligeramente mayor que el de requests
            )
            response.raise_for_status()
            resp_data = response.json()

            if "errors" in resp_data:
                logger.warning(
                    "[lazy-price] GraphQL errors: %s",
                    [e.get("message") for e in resp_data["errors"]]
                )
                return  # Fallback a CLP_RATES — sin crash

            graph_data = resp_data.get("data", {})

            # Inyectar precios en rec["_lazy_prices"] por producto.
            # Escritura atomica por producto — segura con el Python GIL.
            for idx, rec in enumerate(products_needing_prices):
                lazy_prices = {}
                for market in ACTIVE_MARKETS:
                    mid = market["market_id"]
                    node = graph_data.get(f"p{idx}_{mid}")
                    if not node:
                        continue
                    min_price = (
                        node.get("contextualPricing", {})
                        .get("priceRange", {})
                        .get("minVariantPrice", {})
                    )
                    try:
                        amt = float(min_price.get("amount", "0"))
                    except (TypeError, ValueError):
                        amt = 0.0
                    cur = min_price.get("currencyCode", "")
                    if amt > 0 and cur:
                        lazy_prices[mid] = {"price": amt, "currency": cur}

                if lazy_prices:
                    rec["_lazy_prices"] = lazy_prices

            n_enriched = sum(1 for r in products_needing_prices if r.get("_lazy_prices"))
            logger.info(
                "⚡ [lazy-price] Pre-fetch completado: %d/%d productos con precios Shopify "
                "(%d mercados cada uno)",
                n_enriched, len(products_needing_prices), len(ACTIVE_MARKETS)
            )

        except asyncio.TimeoutError:
            # Timeout: Claude ya respondio y los precios no llegaron.
            # _format_price_for_market() usara CLP_RATES como fallback.
            # Sin impacto en la respuesta al usuario — solo en la precision del precio.
            logger.warning(
                "[lazy-price] Timeout (10s) pre-fetching prices. "
                "Falling back to CLP_RATES for this turn."
            )
        except Exception as e:
            # Error de red u otro: fallback silencioso a CLP_RATES.
            logger.warning("[lazy-price] Error pre-fetching prices: %s", e)

    async def _enrich_recommendations_lazy(
        self,
        recommendations: List[Dict],
        market_id: str
    ) -> None:
        """
        Enriquece con precios de Shopify los productos de este turno que
        aun no tienen market_prices, via una unica query GraphQL.

        Se llama ANTES de construir el prompt para Claude, dentro de
        _generate_claude_personalized_response() que ya es async.
        Como Claude tarda ~1.2s y esta query tarda ~200-300ms, el overhead
        neto en la latencia del usuario es cercano a cero.

        Estrategia de prioridades (igual que _format_price_for_market):
          1. Si el producto ya tiene market_prices en RAM (enriquecido en
             startup o en un turno anterior) → no se toca, cero trabajo.
          2. Si no tiene market_prices → consulta Shopify para ese producto
             y lo inyecta en memoria.
          3. Si Shopify falla → silencio, _format_price_for_market usara
             CLP_RATES como ultimo recurso.

        Args:
            recommendations: Lista de productos del turno (3-5 tipicamente).
            market_id:        Mercado actual (ej. "CH"). Se usa para logging.
        """
        if not self.shopify_client or not recommendations:
            return

        # Identificar cuales productos necesitan enriquecimiento.
        # Un producto necesita enriquecimiento si no tiene market_prices
        # o si le falta el mercado actual — ambos casos se resuelven con
        # una sola query que devuelve los 4 mercados de una vez.
        products_to_enrich = [
            rec for rec in recommendations
            if not rec.get("market_prices")
        ]

        if not products_to_enrich:
            logger.debug(
                "[lazy-price] Todos los productos ya tienen market_prices — "
                "sin query a Shopify necesaria."
            )
            return

        product_ids = [
            str(rec.get("id", ""))
            for rec in products_to_enrich
            if rec.get("id")
        ]

        if not product_ids:
            return

        # ── PARTE C (Sprint lazy-price 21/05/2026): Redis lookup antes de Shopify ──────────
        # Reduce llamadas a Shopify: productos con hit en Redis (< 1ms) no van a Shopify.
        # Comparte el cache con el outfit endpoint y con otras instancias de Cloud Run.
        # Key: "price:{shopify_product_id}" → JSON con precios de los 4 mercados.
        # API Redis en este archivo: redis_client.set(key, value, ttl=3600)
        #   ← usa ttl= (no ex=) porque es RedisService enterprise, no cliente raw.
        redis_client = self.redis_service or self.redis
        ids_for_shopify = []  # productos que NO tienen cache en Redis

        if redis_client:
            for pid in product_ids:
                redis_hit = False
                try:
                    cached_raw = await redis_client.get(f"price:{pid}")
                    if cached_raw:
                        price_all_markets = json.loads(cached_raw)
                        # Inyectar en el rec correspondiente por product_id
                        for rec in products_to_enrich:
                            if str(rec.get("id", "")) == pid:
                                rec["market_prices"] = price_all_markets
                                redis_hit = True
                                logger.debug(
                                    "[lazy-price] lazy_price_redis_hit product_id=%s",
                                    pid
                                )
                                break
                except Exception:
                    pass  # Redis error no critico — continuar a Shopify
                if not redis_hit:
                    ids_for_shopify.append(pid)
        else:
            # Redis no disponible — todos los productos van a Shopify
            ids_for_shopify = list(product_ids)

        if not ids_for_shopify:
            logger.info(
                "[lazy-price] %d/%d productos cargados desde Redis. Sin query a Shopify.",
                len(product_ids), len(product_ids)
            )
            return

        logger.info(
            "[lazy-price] Consultando Shopify para %d producto(s) sin market_prices "
            "(mercado actual: %s)...",
            len(ids_for_shopify), market_id
        )

        t0 = __import__("time").time()

        # ── PARTE A (Sprint lazy-price 21/05/2026): Timeout en la llamada a Shopify ───────
        # Sin timeout: SSL retries de Shopify bloqueaban hasta 12s, agotando el
        # budget de personalizacion (8s). LAZY_PRICE_TIMEOUT_S configurable via env.
        # 5s es suficiente para Shopify en condiciones normales; los SSL retries
        # exceden ese umbral, por lo que el fallback a CLP_RATES se activa solo
        # cuando Shopify tiene problemas reales.
        lazy_price_timeout = float(os.environ.get("LAZY_PRICE_TIMEOUT_S", "5.0"))
        try:
            price_map = await asyncio.wait_for(
                self.shopify_client.get_prices_for_products(ids_for_shopify),
                timeout=lazy_price_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[lazy-price] Timeout (%.0fs) consultando Shopify para %d producto(s). "
                "_format_price_for_market usara CLP_RATES fallback.",
                lazy_price_timeout, len(ids_for_shopify)
            )
            return

        elapsed_ms = (__import__("time").time() - t0) * 1000

        if not price_map:
            logger.warning(
                "[lazy-price] Shopify no devolvio precios — "
                "_format_price_for_market usara CLP_RATES fallback."
            )
            return

        # Inyectar market_prices en los objetos en memoria Y persistir en Redis.
        # Los builders sincrónicos encontraran market_prices en Prioridad 1.
        enriched_count = 0
        for rec in products_to_enrich:
            pid = str(rec.get("id", ""))
            if pid in price_map and price_map[pid]:
                rec["market_prices"] = price_map[pid]
                enriched_count += 1

                # ── PARTE B (Sprint lazy-price 21/05/2026): Escribir en Redis ────────────
                # TTL 1h: suficiente para trafico diario sin datos stale.
                # Webhook products/update invalida el cache cuando Shopify cambia
                # el precio (Fase 3 del plan lazy-price).
                # Comparte el mismo key que lee el outfit endpoint (Parte D).
                if redis_client:
                    try:
                        await redis_client.set(
                            f"price:{pid}",
                            json.dumps(price_map[pid]),
                            ttl=3600
                        )
                    except Exception:
                        pass  # Redis write failure es no-critico

        logger.info(
            "[lazy-price] %d/%d productos enriquecidos con precios Shopify en %.0fms.",
            enriched_count, len(ids_for_shopify), elapsed_ms
        )

    def _detect_user_language(self, text: str) -> str:
        """Detecta el idioma del texto del usuario usando heuristicas de caracteres.

        Objetivo: determinar en que idioma responder, no clasificacion academica.
        Cubre los idiomas relevantes para los mercados activos:
          CL / MX / ES -> espanol
          CH            -> aleman, frances, italiano (segun lo que escriba el usuario)
          Internacional -> ingles, portugues

        Tecnica: caracteres unicode diacriticos + palabras de alta frecuencia.
        Sin dependencias externas, latencia < 1ms, determinista.

        Args:
            text: Query del usuario (puede ser corta, ej. "cinturones")

        Returns:
            Codigo de idioma BCP-47 de 2 letras: "es", "de", "fr", "it", "en", "pt".
            Default "es" si el texto es muy corto o ambiguo (mercado principal).
        """
        if not text or len(text.strip()) < 3:
            # Texto demasiado corto para detectar — fallback al espanol
            # (mercado principal AI-Shoppings: CL, MX, ES)
            return "es"

        text_lower = text.lower().strip()

        # --- Palabras funcionales de alta frecuencia por idioma ---
        # Usamos articulos, preposiciones y pronombres porque aparecen incluso
        # en queries cortas ("muestrame los vestidos", "zeige mir Kleider").
        # No usamos palabras de contenido (varían por dominio).
        LANG_KEYWORDS = {
            "es": [
                "el", "la", "los", "las", "un", "una", "de", "del",
                "en", "con", "para", "por", "que", "es", "son",
                "me", "mi", "te", "se", "hay", "mas", "como",
                "muestrame", "quiero", "busco", "necesito", "tienes",
                "puedes", "tiene", "donde", "cuando", "precio",
                "aceptan", "envio", "talla", "color",
            ],
            "de": [
                "der", "die", "das", "ein", "eine", "ist", "sind",
                "ich", "mir", "mich", "du", "sie", "wir", "ihr",
                "mit", "von", "fur", "bei", "auf", "zeig", "zeige",
                "bitte", "haben", "suche", "preis", "grosse", "farbe",
                "welche", "gibt", "wie", "was", "wo",
            ],
            "fr": [
                "le", "la", "les", "un", "une", "des", "du",
                "je", "tu", "il", "elle", "nous", "vous",
                "est", "sont", "avec", "pour", "sur", "dans",
                "montrez", "montrer", "cherche", "prix", "taille",
                "quoi", "quel", "quelle", "avez",
            ],
            "it": [
                "il", "la", "lo", "gli", "le", "un", "una",
                "di", "del", "della", "da", "per", "con",
                "sono", "ho", "hai", "vorrei", "cercando",
                "prezzo", "taglia", "colore", "dove", "quando",
                "mostrami", "mostra",
            ],
            "pt": [
                "o", "a", "os", "as", "um", "uma",
                "de", "do", "da", "em", "com", "para", "por",
                "eu", "voce", "ele", "ela", "nos",
                "tem", "sao", "esta", "preciso", "quero",
                "mostrar", "preco", "tamanho", "cor",
            ],
            "en": [
                "the", "a", "an", "is", "are", "was", "were",
                "i", "you", "he", "she", "we", "they",
                "have", "has", "do", "does", "show", "me",
                "price", "size", "color", "where", "when", "how",
                "what", "which", "can", "please", "want",
            ],
        }

        # Tokenizar (dividir por espacios y signos de puntuacion comunes)
        import re
        tokens = set(re.split(r'[\s,.:;!?\u00bf\u00a1]+', text_lower))
        tokens.discard("")  # eliminar tokens vacios

        # Contar coincidencias por idioma
        scores = {}
        for lang, keywords in LANG_KEYWORDS.items():
            scores[lang] = sum(1 for kw in keywords if kw in tokens)

        best_lang = max(scores, key=scores.get)
        best_score = scores[best_lang]

        # Si ningun idioma tiene coincidencias claras (query de una sola palabra
        # sin articulos, ej. "cinturones"), usamos espanol como fallback.
        if best_score == 0:
            return "es"

        # Desempate: si espanol y otro idioma empatan, preferimos espanol
        # (mercado principal). Esto evita falsos positivos en palabras
        # compartidas entre idiomas romanicos.
        if best_score == scores.get("es", 0) and best_lang != "es":
            return "es"

        return best_lang


    def _build_tier_upsell_instruction(
            self,
            customer_profile: Optional[Dict],
            product_ctx: Optional[Dict],
            ref_price_clp: float,
            preferred_categories: List[str],
            market_currency: str,
        ) -> str:
            """
            Genera instruccion de upsell especifica cruzando LTV tier x rango de precio.

            Retorna string vacio si:
            - No hay customer_profile (usuario anonimo) -> sin cambio en el prompt
            - No hay product_ctx (no esta en una PDP)  -> sin cambio en el prompt

            Bandas de precio CLP:
            bajo:   < 60.000 CLP  (~60 USD)
            medio:  60.000 - 120.000 CLP
            alto:   > 120.000 CLP

            Matriz tier x precio:
            new   + bajo   -> add-on pequeno + incentivo envio gratis
            new   + medio  -> complemento mismo rango, popular
            new   + alto   -> reforzar calidad, cerrar primera compra
            returning + bajo  -> cross-sell categoria adyacente
            returning + medio -> alternativa mejor misma coleccion
            returning + alto  -> alternativa premium o version especial
            loyal + bajo   -> cross-sell categoria inexplorada
            loyal + medio  -> item que completa el look del estilo habitual
            loyal + alto   -> item de coleccion que combina con sus preferidas
            vip   + bajo   -> add-on exclusivo o edicion limitada
            vip   + medio  -> version premium del mismo producto
            vip   + alto   -> novedad exclusiva, pre-order, o pieza especial

            Args:
                customer_profile:      Dict con ltv_tier, preferred_categories, etc.
                product_ctx:           Dict con title, product_type, collections, tags.
                ref_price_clp:         Precio de referencia en CLP (del primer recomendado).
                preferred_categories:  Categorias preferidas del cliente (max 3).
                market_currency:       Moneda del mercado activo (ej. "CLP", "CHF").

            Returns:
                str: Instruccion para Claude (vacia si no aplica).
            """
            if not customer_profile or not product_ctx:
                return ""

            ltv_tier = customer_profile.get("ltv_tier", "new")

            # Clasificar rango de precio en CLP
            if ref_price_clp < 60_000:
                price_range = "bajo"
            elif ref_price_clp <= 120_000:
                price_range = "medio"
            else:
                price_range = "alto"

            # Datos del producto actual para personalizar la instruccion
            product_name = product_ctx.get("title", "este producto")[:50]
            product_type = product_ctx.get("product_type", "")
            collections  = product_ctx.get("collections", [])
            collection_str = collections[0] if collections else ""
            cats_str = ", ".join(preferred_categories[:2]) if preferred_categories else ""

            # Matriz de instrucciones (12 combinaciones tier x precio)
            INSTRUCTIONS = {
                ("new", "bajo"): (
                    f"Cliente nuevo. El producto actual ({product_name}) es accesible. "
                    f"Sugiere un complemento pequeno (accesorios, basicos) que sume valor "
                    f"sin aumentar mucho el ticket. "
                    f"Menciona sutilmente si hay umbral de envio gratis cerca."
                ),
                ("new", "medio"): (
                    f"Cliente nuevo explorando {product_type or 'la tienda'}. "
                    f"Presenta el producto con confianza como eleccion popular. "
                    f"Si hay un complemento natural de la misma coleccion, menciónalo brevemente."
                ),
                ("new", "alto"): (
                    f"Cliente nuevo considerando un producto premium ({product_name}). "
                    f"Refuerza la calidad y el valor. No presiones con upsell: "
                    f"el objetivo es cerrar esta primera compra con confianza."
                ),
                ("returning", "bajo"): (
                    f"Cliente recurrente que conoce la tienda. "
                    + (f"Afinidad con: {cats_str}. " if cats_str else "")
                    + f"Sugiere explorar una categoria adyacente que aun no ha probado, "
                    f"a precio similar o menor."
                ),
                ("returning", "medio"): (
                    f"Cliente recurrente viendo {product_name}. "
                    + (f"Coleccion: {collection_str}. " if collection_str else "")
                    + f"Menciona si hay una alternativa de mayor valor en la misma coleccion."
                ),
                ("returning", "alto"): (
                    f"Cliente recurrente considerando producto premium. "
                    f"Puede mencionar que ya conoce la calidad de la marca. "
                    f"Sugiere alternativa premium o version especial si existe."
                ),
                ("loyal", "bajo"): (
                    f"Cliente fiel con historial en {cats_str or 'la tienda'}. "
                    f"Este producto es ideal para sugerir cross-sell "
                    f"hacia una categoria que aun no ha explorado."
                ),
                ("loyal", "medio"): (
                    f"Cliente fiel viendo {product_name}. "
                    + (f"Estilo habitual: {cats_str}. " if cats_str else "")
                    + f"Sugiere el item que completa el look coherente con su estilo. "
                    f"Tono cercano, como recomendacion personal."
                ),
                ("loyal", "alto"): (
                    f"Cliente fiel eligiendo pieza premium. "
                    + (f"Coleccion favorita: {collection_str}. " if collection_str else "")
                    + f"Sugiere item complementario de la misma coleccion que encaje "
                    f"con sus preferencias."
                ),
                ("vip", "bajo"): (
                    f"Cliente VIP viendo producto de entrada. "
                    f"Sugiere si existe version exclusiva, edicion limitada o add-on premium "
                    f"que eleve la experiencia. Tono exclusivo, no generico."
                ),
                ("vip", "medio"): (
                    f"Cliente VIP viendo {product_name}. "
                    f"Presenta la version premium o de mayor valor de este producto si existe. "
                    f"Trato exclusivo: este cliente valora lo mejor de cada coleccion."
                ),
                ("vip", "alto"): (
                    f"Cliente VIP eligiendo pieza de alto valor. "
                    + (f"Coleccion: {collection_str}. " if collection_str else "")
                    + f"Sugiere novedad exclusiva, pre-order o pieza especial. "
                    f"Tono de asesor personal de moda, no de vendedor."
                ),
            }

            key = (ltv_tier, price_range)
            instruction = INSTRUCTIONS.get(key, "")

            if not instruction:
                # Tier desconocido — no modificar el prompt
                return ""

            logger.info(
                "tier_upsell_instruction_built ltv_tier=%s price_range=%s price_clp=%.0f currency=%s",
                ltv_tier, price_range, ref_price_clp, market_currency,
            )

            return (
                f"\nPerfil cliente ({ltv_tier.upper()}, producto {price_range} en {market_currency}):\n"
                f"{instruction}\n"
                f"Integra esta orientacion de forma natural en la respuesta, "
                f"sin mencionar el perfil explicitamente.\n"
            )

    def _build_advanced_personalization_prompt(
        self,
        context: PersonalizationContext,
        personalization_result: Dict[str, Any],
        user_language: str = "",
        ctx_ref_price_clp: float = 0.0,
    ) -> str:
        """Construye prompt de personalizacion para Claude.

        FIX (22/03/2026): Prompt reducido de ~1800 tokens a ~400 tokens.
        El prompt original incluia historial completo serializado como JSON,
        diccionarios de preferencias vacios, sensibilidad de precio,
        indicadores de urgencia vacios y 6 instrucciones detalladas que
        duplicaban el system prompt. Con Haiku eso generaba ~3-4s solo de
        prefill. El prompt reducido mantiene la informacion util (mercado,
        idioma, tono, productos) y elimina el ruido.
        """
        mcp_context = context.mcp_context
        market_config = context.market_config

        # Solo las 3 mejores recomendaciones con datos minimos.
        #
        # OPCION A (28/03/2026): Precio para el prompt de Claude.
        #
        # Los productos ahora llevan un campo market_prices poblado por
        # ShopifyIntegration.get_products_with_shopify_prices() durante el
        # startup. Estructura:
        #   product["market_prices"] = {
        #     "CL": {"price": 160000.0, "currency": "CLP"},
        #     "CH": {"price": 159.0,    "currency": "CHF"},
        #     "MX": {"price": 3200.0,   "currency": "MXN"},
        #     "US": {"price": 166.4,    "currency": "USD"}
        #   }
        #
        # Prioridad de lectura:
        #   1. market_prices[market_id]  <- Opcion A: precio Shopify autorizado
        #   2. market_prices["CL"]       <- fallback al precio nativo CLP
        #   3. Conversion manual hardcodeada <- ultimo recurso (deuda tecnica)
        #
        # El precio que Claude menciona coincidira exactamente con el que
        # muestra ProductCard porque ambos vienen de la misma fuente Shopify.
        # REFACTOR (29/03/2026): Funcion local _get_price_for_prompt eliminada.
        # Usar self._format_price_for_market() que centraliza la logica de las
        # 3 prioridades y el WARNING del fallback. Ver docstring del metodo.

        # market_id del contexto actual (ej. "CL", "CH", "MX", "US")
        current_market_id = mcp_context.current_market_id if hasattr(mcp_context, 'current_market_id') else "CL"

        top_recs = personalization_result["recommendations"][:3]
        recs_summary = ", ".join(
            f"{rec.get('title', 'Producto')[:40]} "
            f"({self._format_price_for_market(rec, current_market_id, market_config.currency)})"
            for rec in top_recs
        ) or "productos seleccionados para ti"

        # Ultima query del usuario (contexto conversacional minimo)
        # last_query = (
        #     mcp_context.turns[-1].user_query[:80]
        #     if mcp_context.turns
        #     else "busqueda general"
        # )
        if mcp_context.turns:
            # F-07 (Opcion A): Historial estructurado de los ultimos 3 turns.
            # Sustituye la concatenacion plana anterior que perdia la estructura
            # temporal y las respuestas del asistente.
            #
            # Cada linea le indica a Claude:
            #   - En que turno estamos (contexto de progresion)
            #   - Que pidio el usuario (query real, no minuscula)
            #   - Que productos ya se mostraron (para no repetirlos ni ignorarlos)
            #
            # Los titulos de productos se truncan a 35 chars para mantener el
            # prompt compacto. Si un turn no tiene recomendaciones (ej. saludo
            # o respuesta informacional) simplemente no se listan productos.
            #
            # Nota: ai_response NO se incluye porque:
            #   1. Puede ser largo y consumir tokens innecesarios con Haiku
            #   2. Los titulos de productos ya capturan el contexto relevante
            #   3. La Opcion B (multi-turn nativo de Claude) es el lugar correcto
            #      para pasar ai_response cuando se implemente en el futuro.
            history_lines = []
            for turn in mcp_context.turns[-3:]:
                # Obtener titulos de productos recomendados en este turno.
                # recommendations_provided guarda product_ids (strings numericos).
                # Para el historial del prompt usamos los IDs directamente porque
                # no tenemos acceso al catalogo desde este metodo; el contexto
                # "te mostré 3 productos" ya es util para Claude aunque no tenga
                # los titulos completos. Si en el futuro se quiere enriquecer con
                # titulos, se puede hacer un lookup en tfidf_recommender.product_data.
                rec_ids = turn.recommendations_provided
                if rec_ids:
                    # Mostrar hasta 3 IDs para mantener el prompt compacto
                    sample = rec_ids[:3]
                    rec_str = f"{len(rec_ids)} producto(s) mostrado(s)"
                else:
                    rec_str = "sin productos (respuesta informacional)"

                history_lines.append(
                    f"  Turno {turn.turn_number}: '{turn.user_query}' → {rec_str}"
                )

            last_query = "\n".join(history_lines)
        else:
            last_query = "(primera consulta del usuario)"
            logger.warning("No conversation turns found in context; using default query text.")
        
        tone = market_config.localization.get(
            "cultural_preferences", {}
        ).get("communication_style", "profesional")

        # FIX (31/03/2026 - BUG-LANG-01): Usar idioma del usuario, no del mercado.
        # market_config.language es el idioma geografico ("de" para CH).
        # user_language es el idioma real de la query del usuario.
        # Si no se propaga user_language (llamadas legacy), fallback al geografico.
        language = user_language if user_language else market_config.language

        # ── F-04: Contexto de perfil de cliente ──────────────────────────────
        # Se lee desde mcp_context.customer_profile (Dict o None).
        # Si es None (usuario anonimo) no se añade nada al prompt — sin impacto
        # en tokens ni en comportamiento para sesiones no identificadas.
        customer_profile = getattr(mcp_context, "customer_profile", None)
        product_ctx      = getattr(mcp_context, "current_product_context", None)
        top_recs         = personalization_result["recommendations"][:3]

        # F-01 FIX (28/05/2026 — price_clp=10): Precio de referencia para el tier de upsell.
        #
        # ANTES: precio de top_recs[0] — incorrecto tras diversificacion:
        # el primer rec puede ser accesorio barato (ej. 10 CLP) → tier "bajo" erroneo.
        #
        # AHORA: precio del producto que el usuario ESTA VIENDO (ctx_ref_price_clp),
        # inyectado por _generate_claude_personalized_response() via lazy-price.
        # Fuente: market_prices["CL"]["price"] del producto actual (Shopify-autorizado).
        # Fallback: top_recs[0] si ctx_ref_price_clp no esta disponible
        # (ej. homepage, search, o timeout de Shopify).
        ref_price_clp: float = 0.0
        if ctx_ref_price_clp > 0:
            # Prioridad 1: precio Shopify del producto actual (fuente autoritativa)
            ref_price_clp = ctx_ref_price_clp
        elif top_recs:
            # Prioridad 2: fallback al primer recomendado (sin product_ctx)
            first_rec = top_recs[0]
            mp = first_rec.get("market_prices") or {}
            if "CL" in mp:
                try:
                    ref_price_clp = float(mp["CL"].get("price", 0))
                except (TypeError, ValueError):
                    ref_price_clp = 0.0
            elif first_rec.get("price"):
                try:
                    ref_price_clp = float(first_rec["price"])
                except (TypeError, ValueError):
                    ref_price_clp = 0.0

        # Instruccion de upsell cruzada: tier + rango de precio + categorias preferidas.
        # Retorna string vacio si no hay perfil de cliente, preservando el
        # comportamiento actual para usuarios anonimos (sin cambios en el prompt).
        tier_upsell_instruction = self._build_tier_upsell_instruction(
            customer_profile=customer_profile,
            product_ctx=product_ctx,
            ref_price_clp=ref_price_clp,
            preferred_categories=(
                customer_profile.get("preferred_categories", []) if customer_profile else []
            ),
            market_currency=market_config.currency,
        )

         # ── F-01: Contexto del producto actual (upsell contextual) ─────────────────
         # Construir lineas descriptivas del producto actual para el prompt
        upsell_context_line = ""
        if product_ctx:
            ctx_parts = [f"Producto actual: {product_ctx['title']}"]
            if product_ctx.get("product_type"):
                ctx_parts.append(f"Categor\u00eda: {product_ctx['product_type']}")
            if product_ctx.get("collections"):
                ctx_parts.append(f"Colecci\u00f3n: {', '.join(product_ctx['collections'][:2])}")
            if product_ctx.get("tags"):
                ctx_parts.append(f"Atributos: {', '.join(product_ctx['tags'][:5])}")
            if product_ctx.get("variants_count", 0) > 1:
                ctx_parts.append(f"Variantes disponibles: {product_ctx['variants_count']}")
            upsell_context_line = "\n".join(ctx_parts)
            logger.info(
                "F-01 upsell tier_instruction_active=%s ltv_tier=%s price_clp=%.0f",
                bool(tier_upsell_instruction),
                customer_profile.get("ltv_tier", "anon") if customer_profile else "anon",
                ref_price_clp,
            )

        # Build prompt con instruccion cruzada tier x producto
        # Si tier_upsell_instruction esta disponible (cliente identificado viendo un
        # producto), se usa en lugar de la instruccion generica de upsell.
        # Si no hay perfil ni producto, el prompt funciona igual que antes.
        prompt = (
            f"Como experto en personalizacion de e-commerce, genera una respuesta "
            f"conversacional personalizada.\n"
            f"Responde en {language} con tono {tone} en 2 o 3 oraciones maximo.\n"
            f"No inicies con frases como 'Basandome en tu busqueda...'\n"
            f"Especialidad: Personalizacion comportamental\n"
        )

        if tier_upsell_instruction:
            # Instruccion especifica tier x producto (cliente identificado)
            prompt += tier_upsell_instruction
        elif upsell_context_line:
            # Sin perfil de cliente: instruccion generica de upsell
            prompt += (
                f"\nContexto del producto que el usuario esta viendo:\n{upsell_context_line}\n"
                "Si es natural en la conversacion, sugiere complementos o alternativas "
                "de mayor valor de la misma coleccion o categoria. "
                "No menciones el upsell de forma forzada, solo si enriquece la respuesta.\n"
            )

        # ── F-02: Contexto de tallas del cliente (11/04/2026) ────────────────────
        # Se lee desde mcp_context.size_profile (SizeProfile o None).
        # Solo se annade al prompt si el perfil existe, tiene datos suficientes
        # (confidence >= 0.4) y hay variantes de producto disponibles para
        # comparar. Sin estos dos datos, la sugerencia seria vaga y perdera
        # confianza del usuario.
        #
        # Ejemplo de bloque generado (usuario con talla M en vestidos):
        #   Perfil de tallas: el cliente suele pedir talla M en VESTIDOS
        #   (basado en 4 pedidos, confianza: 75%).
        #   Tallas disponibles del producto actual: XS, S, M, L.
        #   Orienta la respuesta mencionando que la M le quedara bien,
        #   sin hacer promesas absolutas.
        size_profile = getattr(mcp_context, "size_profile", None)
        if size_profile and size_profile.has_data() and product_ctx:
            # Determinar la talla recomendada: buscar por categoria del producto
            # actual primero, luego usar la talla global mas frecuente como fallback.
            product_type_upper = (product_ctx.get("product_type") or "").upper().strip()

            # Intentar mapear product_type a un grupo de categoria de tallas
            # usando el mismo CATEGORY_GROUPS del servicio
            SIZE_GROUP_MAP = {
                "VESTIDOS LARGOS": "VESTIDOS", "VESTIDOS CORTOS": "VESTIDOS",
                "VESTIDOS MIDIS": "VESTIDOS", "NOVIAS LARGOS": "VESTIDOS",
                "NOVIAS CORTOS": "VESTIDOS", "NOVIAS MIDIS": "VESTIDOS",
                "ENTERITOS LARGOS": "ENTERITOS", "ENTERITOS CORTOS": "ENTERITOS",
                "TOPS": "TOPS", "BRALETTES": "TOPS",
                "FALDAS": "FALDAS", "PANTALONES": "PANTALONES", "LEGGINGS": "PANTALONES",
                "CONJUNTOS FALDAS": "CONJUNTOS", "CONJUNTOS PANTALONES": "CONJUNTOS",
            }
            size_group = SIZE_GROUP_MAP.get(product_type_upper, product_type_upper)

            # Talla recomendada: usa best_size_for_category() que verifica
            # confianza por categoria antes de recomendar.
            # FIX (12/04/2026): antes usaba size_by_category.get() directamente,
            # ignorando la confianza por categoria.
            recommended_size = (
                size_profile.best_size_for_category(size_group)
                or size_profile.best_size_for_category(product_type_upper)
                or (size_profile.most_common_size
                    if size_profile.confidence >= 0.4  # mismo umbral que MIN_CONFIDENCE_THRESHOLD
                    else None)
            )
            if recommended_size:
                # Confianza de la categoria especifica (mas precisa que la global)
                cat_confidence = (
                    size_profile.confidence_by_category.get(size_group)
                    or size_profile.confidence_by_category.get(product_type_upper)
                    or size_profile.confidence
                )
                confidence_pct = int(cat_confidence * 100)
                orders_n = size_profile.orders_analyzed
                category_label = size_group or product_type_upper or "productos"

                sizing_block = (
                    f"\nPerfil de tallas del cliente: suele pedir talla "
                    f"{recommended_size} en {category_label} "
                    f"(basado en {orders_n} pedido(s), confianza: {confidence_pct}%).\n"
                )
                logger.warning(f"recommended_size_prompt: {sizing_block}")
                # Si hay variantes de producto disponibles en product_ctx,
                # anadir las opciones para que Claude pueda comparar.
                # product_ctx no incluye las variantes en el dict actual (F-01
                # solo guarda variants_count). Si en el futuro se annade la
                # lista de variantes, se puede enriquecer este bloque.
                # Por ahora, orientamos a Claude a confirmar la disponibilidad
                # sin afirmar que la talla exacta esta en stock.
                sizing_block += (
                    f"Si la talla {recommended_size} esta disponible en este producto, "
                    f"mencionalo con confianza. Si no esta disponible, sugiere la talla "
                    f"mas cercana disponible sin hacer promesas absolutas.\n"
                    f"Integra esta orientacion de forma natural, sin citar el numero "
                    f"de pedidos ni el porcentaje de confianza explicitamente.\n"
                )
                prompt += sizing_block
                logger.info(
                    "F-02 sizing_context_added_to_prompt "
                    "customer_size=%s category=%s confidence=%d orders=%d",
                    recommended_size, category_label, confidence_pct, orders_n,
                )
        # ── Fin F-02 ─────────────────────────────────────────────────────────────────
        # ── F-05: Stock Alert en el prompt de personalización (13/04/2026) ────────
        # FIX (18/04/2026): El logger.warning anterior estaba FUERA del guard
        # 'if product_ctx', causando TypeError cuando product_ctx es None
        # (usuario en búsqueda general, no en PDP). Movido al interior.
        if product_ctx and product_ctx.get("stock_alert"):
            logger.warning(
                "F-05 stock_alert_detected alert=%s handle=%s",
                product_ctx["stock_alert"],
                product_ctx.get("handle", "?"),
            )
            
            try:
                from src.api.core.kb_contextualizer import _build_stock_alert_block
                _lang_key = (language or "es").split("-")[0].lower()
                stock_alert_block = _build_stock_alert_block(
                    product_context=product_ctx,
                    language=_lang_key,
                )
                if stock_alert_block:
                    prompt += stock_alert_block
                    logger.info(
                        "F-05 stock_alert_added_to_prompt alert=%s handle=%s",
                        product_ctx["stock_alert"],
                        product_ctx.get("handle", "?"),
                    )
            except Exception as _stock_e:
                logger.warning("F-05 stock_alert_block_failed (graceful degradation): %s", _stock_e)
        # ── Fin F-05 ─────────────────────────────────────────────────────────────

        # ── Solución B (UX): Mencionar producto en respuestas contextuales ───────
        # Cuando el usuario está en una página de producto y hace preguntas sobre
        # tallas, stock o material, el asistente debe mencionar el nombre del
        # producto para que el usuario sepa que la respuesta es específica a ese item.
        # Esto evita mostrar chips visuales adicionales manteniendo claridad.
        if product_ctx:
            prompt += (
                f"\nIMPORTANTE: El usuario está viendo el producto '{product_ctx['title']}'. "
                f"Cuando respondas sobre tallas, disponibilidad, material o características, "
                f"menciona el nombre del producto al inicio para que el usuario sepa que "
                f"estás hablando de este item específico. Ejemplo: 'El {product_ctx['title']}...'\n"
            )
        # ── Fin Solución B ───────────────────────────────────────────────────────

        prompt += (
            f"Historial conversacional (ultimos 3 turnos):\n{last_query}\n"
            f"Construir sobre la conversacion, manteniendo coherencia durante todo el flujo.\n"
            f"Moneda: {market_config.currency}\n"
            f"Productos recomendados: {recs_summary}\n\n"
            f"- Por que estos productos son ideales para su busqueda.\n"
            f"- Destaca el producto mas relevante con su precio.\n"
            f"Respuesta directa sin JSON:"
        )

        return prompt
    
    def _build_personalized_system_prompt(
        self,
        context: PersonalizationContext,
        user_language: str = ""
    ) -> str:
        """Construye system prompt para Claude.

        FIX (22/03/2026): Reducido de ~400 tokens a ~60 tokens.
        El system prompt original duplicaba instrucciones ya presentes en el
        user prompt (idioma, tono, mercado) y listaba 'capacidades' que Claude
        no necesita conocer para generar 2-3 oraciones de recomendacion.

        FIX (31/03/2026 — BUG-LANG-01): Idioma del sistema prompt.
        ANTES: se usaba market_config.language ("de" para CH) como instruccion
        de idioma a Claude. Claude obedecia y respondia en aleman aunque el
        usuario escribiera en espanol.
        AHORA: se usa user_language, detectado desde la query del usuario por
        _detect_user_language(). Si el usuario escribe en espanol, Claude
        responde en espanol. La instruccion es explicita y en primera posicion
        del system prompt para maximizar su peso en la respuesta de Claude.

        NOTA: Existe tambien _build_personalized_system_prompt en el path secundario
        (segunda version de _generate_claude_personalized_response que usa
        config.to_anthropic_params()) con un system prompt mas completo que incluye
        el estilo de conversacion del usuario. Ambas versiones son validas y se usan
        en diferentes paths de llamada.
        """
        market_config = context.market_config
        tone = market_config.localization.get(
            "cultural_preferences", {}
        ).get("communication_style", "profesional")

        # Determinar el idioma a usar:
        #   1. user_language detectado de la query del usuario (fuente primaria)
        #   2. market_config.language como fallback si user_language esta vacio
        # La instruccion va en PRIMERA LINEA del system prompt para maximizar
        # su peso — Claude da mas prioridad a instrucciones al inicio del prompt.
        effective_language = user_language if user_language else market_config.language

        # return (
        #     f"Responde siempre en {effective_language}. "
        #     f"Eres un asistente de compras para {market_config.name} con tono {tone}. "
        #     f"Respuestas cortas y directas, maximo 3 oraciones."
        # )
        return (
            # f"Eres un asistente de compras AI experto en personalización para el mercado {market_config.name} "
            f"Eres un asistente de compras AI experto en:"
            f"- marketing de moda, "
            f"- estilismo/imagen personal, "
            f"- diseño de moda. "
            f"Responde siempre en {effective_language} con tono {tone}. "
            # f"Especialidades: marketing de moda, estilismo/imagen personal, diseño de moda.\n"
            # f"Usa elementos culturales apropiados para {market_config.id}.\n"


            # f"Dominio cultural: {market_config.localization.get("cultural_preferences", {})}.\n"
            f"Tu objetivo es crear experiencias conversacionales que se sientan únicas para cada usuario, optimizando para conversión y satisfacción.\n"

            f"Respuestas cortas y directas, 2 oraciones, maximo 3."       
        )
    
    # === MÉTODOS DE ANÁLISIS Y CÁLCULO ===
    
    def _calculate_behavioral_score(self, recommendation: Dict, patterns: Dict) -> float:
        """Calcula score de recomendación basado en patrones comportamentales."""
        try:
            base_score = 0.5
            
            # Factor por categoría de interés
            rec_category = recommendation.get("category", "").lower()
            category_interest = patterns.get("category_interactions", {}).get(rec_category, 0)
            category_factor = min(category_interest / 10.0, 0.4)  # Max 0.4 bonus
            
            # Factor por rango de precio preferido
            rec_price = recommendation.get("price", 0)
            price_preferences = patterns.get("price_preferences", {})
            price_factor = self._calculate_price_preference_factor(rec_price, price_preferences)
            
            # Factor por hora del día / temporal
            temporal_factor = patterns.get("temporal_preferences", {}).get("current_hour_factor", 0.1)
            
            final_score = base_score + category_factor + price_factor + temporal_factor
            return min(final_score, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating behavioral score: {e}")
            return 0.5
    
    def _apply_cultural_adaptation(self, recommendation: Dict, cultural_prefs: Dict) -> Dict:
        """Aplica adaptación cultural a una recomendación."""
        adaptations = {}
        
        try:
            # Adaptación de comunicación
            comm_style = cultural_prefs.get("communication_style", "standard")
            if comm_style == "formal":
                adaptations["description_tone"] = "formal"
                adaptations["presentation_style"] = "detailed"
            elif comm_style == "warm":
                adaptations["description_tone"] = "friendly"
                adaptations["presentation_style"] = "personal"
            elif comm_style == "direct":
                adaptations["description_tone"] = "concise"
                adaptations["presentation_style"] = "feature-focused"
            
            # Adaptación de elementos visuales/presentación
            if "visual_preferences" in cultural_prefs:
                adaptations.update(cultural_prefs["visual_preferences"])
            
            return adaptations
            
        except Exception as e:
            logger.error(f"Error applying cultural adaptation: {e}")
            return {}
    
    def _calculate_contextual_relevance(
        self, 
        recommendation: Dict, 
        intent: str, 
        stage: ConversationStage
    ) -> float:
        """Calcula relevancia contextual de una recomendación."""
        try:
            base_score = 0.5
            
            # Factor por intención
            intent_factor = 0.0
            if intent == "search" and "search_keywords" in recommendation:
                intent_factor = 0.3
            elif intent == "purchase" and recommendation.get("availability", True):
                intent_factor = 0.4
            elif intent == "compare" and "comparison_features" in recommendation:
                intent_factor = 0.3
            
            # Factor por etapa conversacional
            stage_factor = 0.0
            if stage == ConversationStage.EXPLORING:
                stage_factor = 0.2 if recommendation.get("category_breadth", False) else 0.1
            elif stage == ConversationStage.DECIDING:
                stage_factor = 0.3 if recommendation.get("detailed_specs", False) else 0.1
            elif stage == ConversationStage.TRANSACTING:
                stage_factor = 0.4 if recommendation.get("purchase_ready", True) else 0.0
            
            return min(base_score + intent_factor + stage_factor, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating contextual relevance: {e}")
            return 0.5
    
    async def _predict_future_intents(self, context: PersonalizationContext) -> Dict[str, float]:
        """Predice intenciones futuras del usuario usando ML simple."""
        try:
            mcp_context = context.mcp_context
            profile = context.personalization_profile
            
            # Análisis de patrones de intención históricos
            intent_history = [turn["intent"] for turn in mcp_context.intent_history]
            
            # Predicciones simples basadas en patrones
            predictions = {}
            
            # Si ha estado explorando, probable que compare pronto
            if intent_history[-2:].count("search") >= 2:
                predictions["compare"] = 0.7
                predictions["purchase"] = 0.3
            
            # Si ha estado comparando, probable que compre
            elif intent_history[-2:].count("compare") >= 1:
                predictions["purchase"] = 0.8
                predictions["question"] = 0.4
            
            # Si propensión de compra es alta
            elif profile.purchase_propensity > 0.7:
                predictions["purchase"] = 0.6
                predictions["compare"] = 0.4
            
            # Default
            else:
                predictions = {
                    "search": 0.4,
                    "recommend": 0.5,
                    "compare": 0.3,
                    "purchase": 0.2
                }
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error predicting future intents: {e}")
            return {"recommend": 0.5, "search": 0.3}
    
    def _calculate_predictive_score(
        self, 
        recommendation: Dict, 
        future_predictions: Dict[str, float]
    ) -> float:
        """Calcula score predictivo basado en intenciones futuras."""
        try:
            # Mapear características de recomendación a intenciones
            rec_intent_alignment = {}
            
            if recommendation.get("detailed_specs", False):
                rec_intent_alignment["compare"] = 0.8
            if recommendation.get("purchase_ready", True):
                rec_intent_alignment["purchase"] = 0.9
            if recommendation.get("category_breadth", False):
                rec_intent_alignment["search"] = 0.7
            
            # Calcular score basado en alineación con predicciones
            weighted_score = 0.0
            total_weight = 0.0
            
            for intent, probability in future_predictions.items():
                if intent in rec_intent_alignment:
                    weighted_score += probability * rec_intent_alignment[intent]
                    total_weight += probability
            
            if total_weight > 0:
                return weighted_score / total_weight
            else:
                return 0.5
                
        except Exception as e:
            logger.error(f"Error calculating predictive score: {e}")
            return 0.5
    
    async def _analyze_real_time_signals(self, mcp_context: MCPConversationContext) -> Dict[str, Any]:
        """Analiza señales en tiempo real de la conversación."""
        signals = {}
        
        try:
            # Análisis de velocidad de conversación
            if len(mcp_context.turns) >= 2:
                time_between_turns = []
                for i in range(1, len(mcp_context.turns)):
                    time_diff = mcp_context.turns[i].timestamp - mcp_context.turns[i-1].timestamp
                    time_between_turns.append(time_diff)
                
                signals["avg_response_time"] = np.mean(time_between_turns)
                signals["conversation_pace"] = "fast" if np.mean(time_between_turns) < 30 else "normal"
            
            # Análisis de longitud de mensajes
            message_lengths = [len(turn.user_query) for turn in mcp_context.turns]
            if message_lengths:
                signals["avg_message_length"] = np.mean(message_lengths)
                signals["engagement_level"] = "high" if np.mean(message_lengths) > 50 else "normal"
            
            # Análisis de palabras clave de urgencia
            urgency_keywords = ["urgente", "rápido", "ahora", "hoy", "inmediato", "urgent", "fast", "now"]
            recent_messages = [turn.user_query.lower() for turn in mcp_context.turns[-3:]]
            
            urgency_count = sum(
                1 for message in recent_messages 
                for keyword in urgency_keywords 
                if keyword in message
            )
            signals["urgency_level"] = urgency_count / max(len(recent_messages), 1)
            
            return signals
            
        except Exception as e:
            logger.error(f"Error analyzing real-time signals: {e}")
            return {}
    
    def _calculate_conversation_momentum(self, mcp_context: MCPConversationContext) -> float:
        """Calcula el momentum actual de la conversación."""
        try:
            if len(mcp_context.turns) < 2:
                return 0.5
            
            # Factores que influyen en momentum
            factors = []
            
            # Factor de frecuencia de turnos
            recent_turns = mcp_context.turns[-5:]  # Últimos 5 turnos
            if len(recent_turns) >= 2:
                time_span = recent_turns[-1].timestamp - recent_turns[0].timestamp
                turn_frequency = len(recent_turns) / max(time_span / 60, 1)  # turnos por minuto
                frequency_factor = min(turn_frequency / 2.0, 1.0)  # Normalizar
                factors.append(frequency_factor)
            
            # Factor de confianza en intenciones
            if mcp_context.intent_history:
                recent_confidences = [turn["confidence"] for turn in mcp_context.intent_history[-3:]]
                confidence_factor = np.mean(recent_confidences)
                factors.append(confidence_factor)
            
            # Factor de engagement score
            factors.append(mcp_context.engagement_score)
            
            # Promedio de factores
            if factors:
                return np.mean(factors)
            else:
                return 0.5
                
        except Exception as e:
            logger.error(f"Error calculating conversation momentum: {e}")
            return 0.5
    
    def _detect_urgency_indicators(self, mcp_context: MCPConversationContext) -> List[str]:
        """Detecta indicadores de urgencia en la conversación."""
        indicators = []
        
        try:
            recent_messages = [turn.user_query.lower() for turn in mcp_context.turns[-3:]]
            all_recent_text = " ".join(recent_messages)
            
            # Palabras clave de urgencia temporal
            if any(word in all_recent_text for word in ["hoy", "ahora", "rápido", "urgente", "inmediato"]):
                indicators.append("temporal_urgency")
            
            # Patrones de decisión
            if any(word in all_recent_text for word in ["decidir", "comprar", "necesito", "quiero"]):
                indicators.append("decision_ready")
            
            # Indicadores de precio/descuento
            if any(word in all_recent_text for word in ["descuento", "oferta", "precio", "barato", "económico"]):
                indicators.append("price_sensitive")
            
            # Repetición de consultas similares
            if len(set(recent_messages)) < len(recent_messages) * 0.7:
                indicators.append("repeated_inquiry")
            
            # Alta frecuencia de interacción
            if len(mcp_context.turns) >= 5 and mcp_context.conversation_velocity > 3:
                indicators.append("high_engagement")
            
            return indicators
            
        except Exception as e:
            logger.error(f"Error detecting urgency indicators: {e}")
            return []
    
    # === MÉTODOS DE ACTUALIZACIÓN DE PERFIL ===
    
    def _update_behavioral_patterns(self, profile: PersonalizationProfile, mcp_context: MCPConversationContext):
        """Actualiza patrones de comportamiento en el perfil."""
        try:
            patterns = profile.behavioral_patterns
            
            # Actualizar interacciones por categoría
            if "category_interactions" not in patterns:
                patterns["category_interactions"] = {}
            
            # Analizar productos mencionados en conversación
            for turn in mcp_context.turns[-3:]:  # Últimos 3 turnos
                for entity in turn.intent_entities:
                    if entity in patterns["category_interactions"]:
                        patterns["category_interactions"][entity] += 1
                    else:
                        patterns["category_interactions"][entity] = 1
            
            # Actualizar preferencias temporales
            current_hour = datetime.now().hour
            if "temporal_preferences" not in patterns:
                patterns["temporal_preferences"] = {}
            
            patterns["temporal_preferences"][f"hour_{current_hour}"] = \
                patterns["temporal_preferences"].get(f"hour_{current_hour}", 0) + 1
            
        except Exception as e:
            logger.error(f"Error updating behavioral patterns: {e}")
    
    def _update_category_affinities(self, profile: PersonalizationProfile, result: Dict[str, Any]):
        """Actualiza afinidades de categoría basado en recomendaciones aceptadas."""
        try:
            # Incrementar afinidad por categorías en recomendaciones top
            top_recommendations = result.get("recommendations", [])[:3]
            
            for rec in top_recommendations:
                category = rec.get("category", "").lower()
                if category:
                    current_affinity = profile.category_affinities.get(category, 0.0)
                    # Incremento basado en score de la recomendación
                    score_bonus = rec.get("hybrid_score", rec.get("score", 0.5))
                    new_affinity = min(current_affinity + (score_bonus * 0.1), 1.0)
                    profile.category_affinities[category] = new_affinity
            
        except Exception as e:
            logger.error(f"Error updating category affinities: {e}")
    
    def _update_conversation_style(self, profile: PersonalizationProfile, mcp_context: MCPConversationContext):
        """Actualiza el estilo conversacional detectado."""
        try:
            # Analizar longitud promedio de mensajes
            if mcp_context.turns:
                avg_length = np.mean([len(turn.user_query) for turn in mcp_context.turns])
                
                if avg_length > 100:
                    profile.conversation_style = "detailed"
                elif avg_length < 30:
                    profile.conversation_style = "concise"
                elif mcp_context.conversation_velocity > 2:
                    profile.conversation_style = "fast_paced"
                else:
                    profile.conversation_style = "standard"
            
        except Exception as e:
            logger.error(f"Error updating conversation style: {e}")
    
    def _update_purchase_propensity(self, profile: PersonalizationProfile, mcp_context: MCPConversationContext):
        """Actualiza la propensión de compra del usuario."""
        try:
            # Factores que indican propensión de compra
            purchase_indicators = 0
            
            # Analizar intenciones recientes
            recent_intents = [turn["intent"] for turn in mcp_context.intent_history[-5:]]
            if "purchase" in recent_intents:
                purchase_indicators += 0.3
            if "compare" in recent_intents:
                purchase_indicators += 0.2
            
            # Analizar stage conversacional
            if mcp_context.conversation_stage.value in ["deciding", "transacting"]:
                purchase_indicators += 0.2
            
            # Analizar engagement
            if mcp_context.engagement_score > 0.7:
                purchase_indicators += 0.1
            
            # Actualizar propensión (promedio móvil)
            profile.purchase_propensity = min(
                (profile.purchase_propensity * 0.7) + (purchase_indicators * 0.3), 1.0
            )
            
        except Exception as e:
            logger.error(f"Error updating purchase propensity: {e}")
    
    def _update_cross_market_insights(self, profile: PersonalizationProfile, mcp_context: MCPConversationContext):
        """Actualiza insights cross-market del usuario."""
        try:
            market_id = mcp_context.current_market_id
            
            if "market_behaviors" not in profile.cross_market_insights:
                profile.cross_market_insights["market_behaviors"] = {}
            
            market_behavior = profile.cross_market_insights["market_behaviors"].get(market_id, {})
            
            # Actualizar métricas del mercado
            market_behavior["total_sessions"] = market_behavior.get("total_sessions", 0) + 1
            market_behavior["avg_turns_per_session"] = (
                (market_behavior.get("avg_turns_per_session", 0) * (market_behavior["total_sessions"] - 1) +
                 len(mcp_context.turns)) / market_behavior["total_sessions"]
            )
            market_behavior["last_activity"] = time.time()
            
            profile.cross_market_insights["market_behaviors"][market_id] = market_behavior
            
        except Exception as e:
            logger.error(f"Error updating cross-market insights: {e}")
    
    # === MÉTODOS DE FALLBACK Y UTILIDADES ===
    
    async def _fallback_personalized_response(
        self,
        mcp_context: MCPConversationContext,
        recommendations: List[Dict]
    ) -> Dict[str, Any]:
        """Respuesta de fallback cuando falla la personalización avanzada."""
        return {
            "personalized_response": {
                "response": "Te ayudo a encontrar exactamente lo que buscas. ¿Qué tipo de producto te interesa hoy?",
                "tone_adaptation": "standard",
                "cultural_context": {},
                "personalization_elements": [],
                "engagement_hooks": []
            },
            "personalized_recommendations": recommendations[:5],
            "personalization_metadata": {
                "strategy_used": "fallback",
                "personalization_score": 0.3,
                "cultural_adaptation": {},
                "behavioral_insights": {},
                "market_optimization": {},
                "processing_time_ms": 0
            },
            "conversation_enhancement": {
                "tone_adaptation": "standard",
                "cultural_context": {},
                "personalization_elements": [],
                "engagement_hooks": []
            }
        }
    
    def _calculate_price_preference_factor(self, price: float, preferences: Dict) -> float:
        """Calcula factor de preferencia basado en precio."""
        try:
            # Rango de precios preferido del usuario
            preferred_min = preferences.get("preferred_min", 0)
            preferred_max = preferences.get("preferred_max", 1000)
            
            if preferred_min <= price <= preferred_max:
                return 0.3  # Precio en rango preferido
            elif price < preferred_min:
                return 0.1  # Demasiado barato (posible calidad baja)
            else:
                # Calcular penalización por precio alto
                excess_ratio = (price - preferred_max) / preferred_max
                return max(0.0, 0.2 - (excess_ratio * 0.1))
                
        except Exception as e:
            logger.error(f"Error calculating price preference factor: {e}")
            return 0.1
    
    def _get_score_distribution(self, recommendations: List[Dict]) -> Dict[str, float]:
        """Obtiene distribución de scores de recomendaciones."""
        try:
            if not recommendations:
                return {}
            
            scores = [rec.get("behavioral_score", 0.5) for rec in recommendations]
            return {
                "min": min(scores),
                "max": max(scores),
                "mean": np.mean(scores),
                "std": np.std(scores)
            }
        except Exception as e:
            logger.error(f"Error getting score distribution: {e}")
            return {}
    
    async def _record_personalization_analytics(
        self,
        mcp_context: MCPConversationContext,
        strategy: PersonalizationStrategy,
        processing_time: float
    ):
        """Registra analytics de personalización."""
        try:
            analytics_event = {
                "event_type": "personalization_generated",
                "user_id": mcp_context.user_id,
                "session_id": mcp_context.session_id,
                "market_id": mcp_context.current_market_id,
                "strategy_used": strategy.value,
                "processing_time_ms": processing_time,
                "conversation_stage": mcp_context.conversation_stage.value,
                "total_turns": len(mcp_context.turns),
                "timestamp": time.time()
            }
            
            # ✅ ENTERPRISE FIX (17/03/2026): Usar redis_service si está disponible,
            # fallback a redis (legacy). self.redis es None cuando el engine fue
            # creado via ServiceFactory — causa el error del log:
            # "Error recording personalization analytics: 'NoneType' object has no attribute 'set'"
            redis_client = self.redis_service or self.redis
            if not redis_client:
                logger.warning("Redis not available - skipping personalization analytics recording")
                return

            # Guardar en Redis para analytics posteriores
            analytics_key = f"mcp:analytics:personalization:{mcp_context.session_id}:{int(time.time())}"
            await redis_client.set(
                analytics_key,
                json.dumps(analytics_event),
                ttl=7 * 24 * 3600  # 7 días; RedisService usa ttl= (no ex=)
            )
            
        except Exception as e:
            logger.error(f"Error recording personalization analytics: {e}")
    
    # === MÉTODOS DE OPTIMIZACIÓN Y MARKET-SPECIFIC ===
    
    def _apply_market_specific_scoring(
        self,
        recommendations: List[Dict],
        market_config: MarketConfig,
        user_profile: Dict[str, Any]
    ) -> List[Dict]:
        """Aplica scoring específico del mercado a las recomendaciones."""
        try:
            scoring_weights = market_config.scoring_weights
            
            for rec in recommendations:
                market_score = 0.0
                
                # Factor precio
                price_weight = scoring_weights.get("price", 0.3)
                price_factor = self._calculate_market_price_factor(
                    rec.get("price", 0), market_config, user_profile
                )
                market_score += price_weight * price_factor
                
                # Factor marca
                brand_weight = scoring_weights.get("brand", 0.3)
                brand_factor = self._calculate_brand_factor(
                    rec.get("brand", ""), market_config, user_profile
                )
                market_score += brand_weight * brand_factor
                
                # Factor reviews/reputación
                reviews_weight = scoring_weights.get("reviews", 0.4)
                reviews_factor = rec.get("rating", 3.5) / 5.0  # Normalizar a 0-1
                market_score += reviews_weight * reviews_factor
                
                rec["market_score"] = market_score
                
            return recommendations
            
        except Exception as e:
            logger.error(f"Error applying market specific scoring: {e}")
            return recommendations
    
    def _adjust_prices_for_market(
        self,
        recommendations: List[Dict],
        market_config: MarketConfig
    ) -> List[Dict]:
        """Ajusta precios considerando impuestos y configuración del mercado."""
        try:
            tax_rate = market_config.tax_rate
            currency = market_config.currency
            
            for rec in recommendations:
                base_price = rec.get("price", 0)
                
                # Aplicar impuestos
                final_price = base_price * (1 + tax_rate)
                
                # Actualizar precio y moneda
                rec["market_price"] = round(final_price, 2)
                rec["currency"] = currency
                rec["tax_included"] = True
                rec["tax_rate"] = tax_rate
                
                # Calcular envío gratuito si aplica
                free_shipping_threshold = market_config.shipping_config.get("free_shipping_threshold", 0)
                rec["free_shipping"] = final_price >= free_shipping_threshold
                
            return recommendations
            
        except Exception as e:
            logger.error(f"Error adjusting prices for market: {e}")
            return recommendations
    
    async def _filter_by_market_availability(
        self,
        recommendations: List[Dict],
        market_id: str
    ) -> List[Dict]:
        """Filtra recomendaciones por disponibilidad en el mercado específico."""
        try:
            available_recommendations = []
            
            for rec in recommendations:
                # Verificar disponibilidad (esto se integraría con sistema real de inventario)
                product_id = rec.get("id")
                is_available = await self._check_product_availability(product_id, market_id)
                
                if is_available:
                    rec["market_availability"] = True
                    available_recommendations.append(rec)
                else:
                    rec["market_availability"] = False
                    # Opcional: incluir productos no disponibles con nota
                    if len(available_recommendations) < 3:  # Si necesitamos más opciones
                        rec["availability_note"] = f"No disponible en {market_id}"
                        available_recommendations.append(rec)
            
            return available_recommendations
            
        except Exception as e:
            logger.error(f"Error filtering by market availability: {e}")
            return recommendations
    
    async def _check_product_availability(self, product_id: str, market_id: str) -> bool:
        """Verifica disponibilidad de producto en mercado específico."""
        try:
            # ✅ ENTERPRISE FIX (17/03/2026): Usar redis_service si está disponible,
            # fallback a redis (legacy). self.redis es None cuando el engine fue
            # creado via ServiceFactory.
            redis_client = self.redis_service or self.redis
            if not redis_client:
                # Sin Redis no bloqueamos el flujo — asumimos disponible
                return True

            # Verificar en caché primero
            cache_key = f"availability:{market_id}:{product_id}"
            cached_availability = await redis_client.get(cache_key)

            if cached_availability is not None:
                return json.loads(cached_availability)

            # En implementación real, esto consultaría Shopify Markets/MCP
            # Por ahora, simulamos disponibilidad alta
            availability = True  # 90% de productos disponibles por defecto

            # Cachear resultado por 1 hora; RedisService usa ttl= (no ex=)
            await redis_client.set(cache_key, json.dumps(availability), ttl=3600)

            return availability
            
        except Exception as e:
            logger.error(f"Error checking product availability: {e}")
            return True  # Fallback: asumir disponible
    
    def _apply_cultural_preferences(
        self,
        recommendations: List[Dict],
        market_config: MarketConfig,
        user_profile: Dict[str, Any]
    ) -> List[Dict]:
        """Aplica preferencias culturales específicas del mercado."""
        try:
            cultural_prefs = market_config.localization.get("cultural_preferences", {})
            
            for rec in recommendations:
                # Adaptaciones específicas por mercado
                if market_config.id == "ES":
                    # España: énfasis en calidad y marca europea
                    if "european" in rec.get("origin", "").lower():
                        rec["cultural_boost"] = 0.2
                    rec["presentation_style"] = "elegant"
                    
                elif market_config.id == "MX":
                    # México: énfasis en valor y familia
                    if rec.get("price", 0) < 100:  # Productos asequibles
                        rec["cultural_boost"] = 0.15
                    rec["presentation_style"] = "family_oriented"
                    
                elif market_config.id == "US":
                    # Estados Unidos: énfasis en innovación y conveniencia
                    if "innovative" in rec.get("features", []):
                        rec["cultural_boost"] = 0.1
                    rec["presentation_style"] = "feature_focused"
                
                # Aplicar boost cultural al score
                current_score = rec.get("market_score", 0.5)
                cultural_boost = rec.get("cultural_boost", 0.0)
                rec["market_score"] = min(current_score + cultural_boost, 1.0)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error applying cultural preferences: {e}")
            return recommendations
    
    def _reorder_by_market_relevance(
        self,
        recommendations: List[Dict],
        market_config: MarketConfig,
        user_profile: Dict[str, Any]
    ) -> List[Dict]:
        """Reordena recomendaciones por relevancia específica del mercado."""
        try:
            # Combinar todos los scores para ordenamiento final
            for rec in recommendations:
                final_score = 0.0
                
                # Score base de recomendación
                base_score = rec.get("score", rec.get("hybrid_score", 0.5))
                final_score += base_score * 0.4
                
                # Score específico del mercado
                market_score = rec.get("market_score", 0.5)
                final_score += market_score * 0.3
                
                # Disponibilidad (factor crítico)
                availability_factor = 1.0 if rec.get("market_availability", True) else 0.3
                final_score *= availability_factor
                
                # Factor de envío gratuito
                if rec.get("free_shipping", False):
                    final_score += 0.1
                
                rec["final_market_score"] = final_score
            
            # Ordenar por score final
            recommendations.sort(key=lambda x: x.get("final_market_score", 0), reverse=True)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error reordering by market relevance: {e}")
            return recommendations
    
    # === MÉTODOS DE ANÁLISIS AVANZADO ===
    
    async def _get_user_historical_sessions(
        self,
        user_id: str,
        market_id: str,
        lookback_days: int
    ) -> List[Dict]:
        """Obtiene sesiones históricas del usuario para análisis."""
        try:
            # Buscar sesiones en Redis usando patrón
            cutoff_time = time.time() - (lookback_days * 24 * 3600)
            sessions = []
            
            # ✅ ENTERPRISE FIX (17/03/2026): Usar redis_service si está disponible,
            # fallback a redis (legacy). self.redis es None cuando el engine fue
            # creado via ServiceFactory.
            redis_client_sessions = self.redis_service or self.redis
            if not redis_client_sessions:
                logger.warning("Redis not available - returning empty session history")
                return []

            # En implementación real, esto buscaría en base de datos de sesiones
            # Por ahora, simulamos con datos de ejemplo
            session_keys = await redis_client_sessions.keys(f"mcp:conversation:{user_id}:*")

            for key in session_keys:
                session_data = await redis_client_sessions.get(key)
                if session_data:
                    session = json.loads(session_data)
                    if (session.get("created_at", 0) > cutoff_time and 
                        session.get("current_market_id") == market_id):
                        sessions.append(session)
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting user historical sessions: {e}")
            return []
    
    def _analyze_conversation_patterns(self, user_sessions: List[Dict]) -> Dict[str, Any]:
        """Analiza patrones conversacionales del usuario."""
        try:
            if not user_sessions:
                return {}
            
            # Métricas agregadas
            total_turns = sum(len(session.get("turns", [])) for session in user_sessions)
            total_sessions = len(user_sessions)
            
            # Patrones de intención
            all_intents = []
            for session in user_sessions:
                for turn in session.get("intent_history", []):
                    all_intents.append(turn.get("intent", "unknown"))
            
            intent_distribution = {}
            for intent in all_intents:
                intent_distribution[intent] = intent_distribution.get(intent, 0) + 1
            
            # Normalizar distribución
            total_intents = len(all_intents)
            if total_intents > 0:
                intent_distribution = {
                    k: v / total_intents for k, v in intent_distribution.items()
                }
            
            # Patrones temporales
            session_hours = [
                datetime.fromtimestamp(session.get("created_at", 0)).hour 
                for session in user_sessions
            ]
            
            preferred_hours = {}
            for hour in session_hours:
                preferred_hours[hour] = preferred_hours.get(hour, 0) + 1
            
            return {
                "avg_turns_per_session": total_turns / max(total_sessions, 1),
                "total_sessions_analyzed": total_sessions,
                "intent_distribution": intent_distribution,
                "preferred_interaction_hours": preferred_hours,
                "conversation_length_trend": self._calculate_length_trend(user_sessions),
                "engagement_evolution": self._calculate_engagement_evolution(user_sessions)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing conversation patterns: {e}")
            return {}
    
    def _analyze_intent_evolution(self, user_sessions: List[Dict]) -> Dict[str, Any]:
        """Analiza cómo han evolucionado las intenciones del usuario."""
        try:
            if not user_sessions:
                return {}
            
            # Ordenar sesiones por fecha
            sorted_sessions = sorted(user_sessions, key=lambda x: x.get("created_at", 0))
            
            # Extraer secuencia de intenciones por sesión
            intent_sequences = []
            for session in sorted_sessions:
                session_intents = [
                    turn.get("intent", "unknown") 
                    for turn in session.get("intent_history", [])
                ]
                if session_intents:
                    intent_sequences.append(session_intents)
            
            # Analizar patrones de transición
            transitions = {}
            for sequence in intent_sequences:
                for i in range(len(sequence) - 1):
                    from_intent = sequence[i]
                    to_intent = sequence[i + 1]
                    transition_key = f"{from_intent}->{to_intent}"
                    transitions[transition_key] = transitions.get(transition_key, 0) + 1
            
            # Encontrar intenciones dominantes por período
            early_sessions = sorted_sessions[:len(sorted_sessions)//2] if len(sorted_sessions) > 2 else sorted_sessions
            recent_sessions = sorted_sessions[len(sorted_sessions)//2:] if len(sorted_sessions) > 2 else sorted_sessions
            
            def get_dominant_intent(sessions):
                intents = []
                for session in sessions:
                    for turn in session.get("intent_history", []):
                        intents.append(turn.get("intent", "unknown"))
                
                intent_counts = {}
                for intent in intents:
                    intent_counts[intent] = intent_counts.get(intent, 0) + 1
                
                return max(intent_counts, key=intent_counts.get) if intent_counts else "unknown"
            
            early_dominant = get_dominant_intent(early_sessions)
            recent_dominant = get_dominant_intent(recent_sessions)
            
            return {
                "intent_transitions": transitions,
                "evolution_pattern": "stable" if early_dominant == recent_dominant else "evolving",
                "early_period_dominant": early_dominant,
                "recent_period_dominant": recent_dominant,
                "transition_frequency": len(transitions),
                "most_common_transition": max(transitions, key=transitions.get) if transitions else None
            }
            
        except Exception as e:
            logger.error(f"Error analyzing intent evolution: {e}")
            return {}
    
    def _calculate_engagement_metrics(self, user_sessions: List[Dict]) -> Dict[str, Any]:
        """Calcula métricas de engagement del usuario."""
        try:
            if not user_sessions:
                return {}
            
            # Métricas básicas
            total_sessions = len(user_sessions)
            total_turns = sum(len(session.get("turns", [])) for session in user_sessions)
            
            # Duración promedio de sesiones
            session_durations = []
            for session in user_sessions:
                turns = session.get("turns", [])
                if len(turns) >= 2:
                    duration = turns[-1].get("timestamp", 0) - turns[0].get("timestamp", 0)
                    session_durations.append(duration)
            
            avg_session_duration = np.mean(session_durations) if session_durations else 0
            
            # Engagement scores promedio
            engagement_scores = [
                session.get("engagement_score", 0.5) for session in user_sessions
            ]
            avg_engagement = np.mean(engagement_scores)
            
            # Tendencia de engagement
            if len(engagement_scores) >= 3:
                early_engagement = np.mean(engagement_scores[:len(engagement_scores)//2])
                recent_engagement = np.mean(engagement_scores[len(engagement_scores)//2:])
                engagement_trend = "improving" if recent_engagement > early_engagement else "declining"
            else:
                engagement_trend = "stable"
            
            # Métricas de conversión (simuladas)
            conversion_events = sum(
                len(session.get("conversion_events", [])) for session in user_sessions
            )
            
            return {
                "total_sessions": total_sessions,
                "avg_turns_per_session": total_turns / max(total_sessions, 1),
                "avg_session_duration_minutes": avg_session_duration / 60,
                "avg_engagement_score": avg_engagement,
                "engagement_trend": engagement_trend,
                "conversion_events": conversion_events,
                "conversion_rate": conversion_events / max(total_sessions, 1),
                "session_completion_rate": len(session_durations) / max(total_sessions, 1)
            }
            
        except Exception as e:
            logger.error(f"Error calculating engagement metrics: {e}")
            return {}
    
    async def _identify_personalization_opportunities(
        self,
        user_sessions: List[Dict],
        conversation_patterns: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identifica oportunidades específicas de personalización."""
        try:
            opportunities = []
            
            # Oportunidad 1: Optimización de horarios
            preferred_hours = conversation_patterns.get("preferred_interaction_hours", {})
            if preferred_hours:
                top_hour = max(preferred_hours, key=preferred_hours.get)
                opportunities.append({
                    "type": "temporal_optimization",
                    "description": f"Usuario más activo a las {top_hour}:00",
                    "recommendation": f"Enviar ofertas personalizadas alrededor de las {top_hour}:00",
                    "priority": "medium",
                    "impact_estimate": 0.15
                })
            
            # Oportunidad 2: Mejora de intenciones
            intent_dist = conversation_patterns.get("intent_distribution", {})
            if "search" in intent_dist and intent_dist["search"] > 0.4:
                opportunities.append({
                    "type": "search_optimization",
                    "description": "Usuario realiza muchas búsquedas",
                    "recommendation": "Mejorar sugerencias de búsqueda y filtros",
                    "priority": "high",
                    "impact_estimate": 0.25
                })
            
            # Oportunidad 3: Duración de sesiones
            avg_duration = conversation_patterns.get("avg_session_duration_minutes", 0)
            if avg_duration < 2:
                opportunities.append({
                    "type": "engagement_improvement",
                    "description": "Sesiones muy cortas",
                    "recommendation": "Implementar preguntas de engagement temprano",
                    "priority": "high",
                    "impact_estimate": 0.30
                })
            
            # Oportunidad 4: Análisis de abandono
            completion_rate = conversation_patterns.get("session_completion_rate", 1.0)
            if completion_rate < 0.7:
                opportunities.append({
                    "type": "abandonment_reduction",
                    "description": "Alta tasa de abandono de sesiones",
                    "recommendation": "Simplificar flujo conversacional inicial",
                    "priority": "critical",
                    "impact_estimate": 0.40
                })
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error identifying personalization opportunities: {e}")
            return []
    
    async def _generate_predictive_insights(
        self,
        user_id: str,
        market_id: str,
        user_sessions: List[Dict]
    ) -> Dict[str, Any]:
        """Genera insights predictivos usando análisis de patrones."""
        try:
            if not self.enable_ml_predictions or not user_sessions:
                return {}
            
            # Predicción de próxima intención
            recent_intents = []
            for session in user_sessions[-3:]:  # Últimas 3 sesiones
                for turn in session.get("intent_history", []):
                    recent_intents.append(turn.get("intent", "unknown"))
            
            intent_predictions = self._predict_next_intent(recent_intents)
            
            # Predicción de timing óptimo
            optimal_timing = self._predict_optimal_interaction_time(user_sessions)
            
            # Predicción de categorías de interés
            category_predictions = self._predict_category_interests(user_sessions)
            
            # Predicción de propensión de compra
            purchase_probability = self._predict_purchase_probability(user_sessions)
            
            return {
                "next_intent_predictions": intent_predictions,
                "optimal_interaction_timing": optimal_timing,
                "predicted_category_interests": category_predictions,
                "purchase_probability_score": purchase_probability,
                "prediction_confidence": 0.75,
                "model_version": "v1.0_basic_patterns",
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating predictive insights: {e}")
            return {}
    
    def _generate_journey_recommendations(
        self,
        conversation_patterns: Dict[str, Any],
        engagement_metrics: Dict[str, Any],
        predictive_insights: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Genera recomendaciones basadas en análisis del journey."""
        recommendations = []
        
        try:
            # Recomendación basada en engagement
            avg_engagement = engagement_metrics.get("avg_engagement_score", 0.5)
            if avg_engagement < 0.6:
                recommendations.append({
                    "category": "engagement_improvement",
                    "title": "Mejorar Engagement Conversacional",
                    "description": "Implementar elementos más interactivos en las conversaciones",
                    "actions": [
                        "Añadir preguntas de seguimiento personalizadas",
                        "Incluir elementos visuales en recomendaciones",
                        "Implementar gamificación sutil"
                    ],
                    "priority": "high",
                    "estimated_impact": 0.25
                })
            
            # Recomendación basada en intenciones
            intent_dist = conversation_patterns.get("intent_distribution", {})
            dominant_intent = max(intent_dist, key=intent_dist.get) if intent_dist else "search"
            
            if dominant_intent == "search":
                recommendations.append({
                    "category": "search_optimization",
                    "title": "Optimizar Experiencia de Búsqueda",
                    "description": "Mejorar capacidades de búsqueda conversacional",
                    "actions": [
                        "Implementar búsqueda semántica avanzada",
                        "Añadir filtros conversacionales inteligentes",
                        "Mejorar sugerencias de productos relacionados"
                    ],
                    "priority": "medium",
                    "estimated_impact": 0.20
                })
            
            # Recomendación basada en predicciones
            if predictive_insights.get("purchase_probability_score", 0) > 0.7:
                recommendations.append({
                    "category": "conversion_optimization",
                    "title": "Optimizar para Conversión",
                    "description": "Usuario muestra alta propensión de compra",
                    "actions": [
                        "Priorizar ofertas personalizadas",
                        "Simplificar proceso de checkout",
                        "Implementar urgencia sutil en recomendaciones"
                    ],
                    "priority": "critical",
                    "estimated_impact": 0.35
                })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating journey recommendations: {e}")
            return []
    
    # === MÉTODOS AUXILIARES DE PREDICCIÓN ===
    
    def _predict_next_intent(self, recent_intents: List[str]) -> Dict[str, float]:
        """Predice próxima intención basada en patrones históricos."""
        if not recent_intents:
            return {"search": 0.4, "recommend": 0.6}
        
        # Patrones de transición simples
        last_intent = recent_intents[-1]
        
        transition_probabilities = {
            "search": {"compare": 0.4, "recommend": 0.3, "search": 0.3},
            "compare": {"purchase": 0.5, "question": 0.3, "search": 0.2},
            "recommend": {"purchase": 0.4, "compare": 0.3, "search": 0.3},
            "question": {"recommend": 0.5, "search": 0.3, "compare": 0.2},
            "purchase": {"search": 0.6, "recommend": 0.4}
        }
        
        return transition_probabilities.get(last_intent, {"search": 0.4, "recommend": 0.6})
    
    def _predict_optimal_interaction_time(self, user_sessions: List[Dict]) -> Dict[str, Any]:
        """Predice el momento óptimo para interactuar con el usuario."""
        try:
            # Analizar patrones de actividad
            activity_hours = []
            for session in user_sessions:
                created_at = session.get("created_at", 0)
                hour = datetime.fromtimestamp(created_at).hour
                activity_hours.append(hour)
            
            if not activity_hours:
                return {"optimal_hour": 14, "confidence": 0.3}  # Default 2 PM
            
            # Encontrar hora más común
            hour_counts = {}
            for hour in activity_hours:
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
            
            optimal_hour = max(hour_counts, key=hour_counts.get)
            confidence = hour_counts[optimal_hour] / len(activity_hours)
            
            return {
                "optimal_hour": optimal_hour,
                "confidence": confidence,
                "activity_distribution": hour_counts
            }
            
        except Exception as e:
            logger.error(f"Error predicting optimal interaction time: {e}")
            return {"optimal_hour": 14, "confidence": 0.3}
    
    def _predict_category_interests(self, user_sessions: List[Dict]) -> Dict[str, float]:
        """Predice categorías de interés futuras del usuario."""
        try:
            # Extraer entidades/categorías mencionadas
            all_entities = []
            for session in user_sessions:
                for turn in session.get("turns", []):
                    all_entities.extend(turn.get("intent_entities", []))
            
            if not all_entities:
                return {}
            
            # Contar frecuencias
            entity_counts = {}
            for entity in all_entities:
                entity_counts[entity] = entity_counts.get(entity, 0) + 1
            
            # Normalizar y predecir interés futuro
            total_entities = len(all_entities)
            predictions = {}
            for entity, count in entity_counts.items():
                interest_score = count / total_entities
                # Boost para categorías recientes
                if entity in all_entities[-10:]:  # Últimas 10 entidades
                    interest_score *= 1.2
                
                predictions[entity] = min(interest_score, 1.0)
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error predicting category interests: {e}")
            return {}
    
    def _predict_purchase_probability(self, user_sessions: List[Dict]) -> float:
        """Predice probabilidad de compra en próximas sesiones."""
        try:
            if not user_sessions:
                return 0.3
            
            # Factores que indican propensión de compra
            factors = []
            
            # Factor 1: Intenciones de compra recientes
            recent_intents = []
            for session in user_sessions[-2:]:  # Últimas 2 sesiones
                for turn in session.get("intent_history", []):
                    recent_intents.append(turn.get("intent", "unknown"))
            
            purchase_intent_ratio = recent_intents.count("purchase") / max(len(recent_intents), 1)
            factors.append(purchase_intent_ratio)
            
            # Factor 2: Progresión en embudo
            compare_intent_ratio = recent_intents.count("compare") / max(len(recent_intents), 1)
            factors.append(compare_intent_ratio * 0.7)  # Ponderado menor
            
            # Factor 3: Engagement promedio
            avg_engagement = np.mean([
                session.get("engagement_score", 0.5) for session in user_sessions[-3:]
            ])
            factors.append(avg_engagement)
            
            # Factor 4: Frecuencia de sesiones (indica interés)
            if len(user_sessions) >= 2:
                time_span = user_sessions[-1].get("created_at", 0) - user_sessions[0].get("created_at", 1)
                session_frequency = len(user_sessions) / max(time_span / (24 * 3600), 1)  # sesiones por día
                frequency_factor = min(session_frequency / 2.0, 0.5)  # Normalizar
                factors.append(frequency_factor)
            
            # Promedio ponderado
            if factors:
                return min(np.mean(factors), 1.0)
            else:
                return 0.3
                
        except Exception as e:
            logger.error(f"Error predicting purchase probability: {e}")
            return 0.3
    
    def _calculate_length_trend(self, user_sessions: List[Dict]) -> str:
        """Calcula tendencia de longitud de conversaciones."""
        try:
            if len(user_sessions) < 3:
                return "insufficient_data"
            
            # Calcular longitud de cada sesión
            session_lengths = [len(session.get("turns", [])) for session in user_sessions]
            
            # Comparar primera mitad vs segunda mitad
            mid_point = len(session_lengths) // 2
            early_avg = np.mean(session_lengths[:mid_point])
            recent_avg = np.mean(session_lengths[mid_point:])
            
            if recent_avg > early_avg * 1.2:
                return "increasing"
            elif recent_avg < early_avg * 0.8:
                return "decreasing"
            else:
                return "stable"
                
        except Exception as e:
            logger.error(f"Error calculating length trend: {e}")
            return "unknown"
    
    def _calculate_engagement_evolution(self, user_sessions: List[Dict]) -> Dict[str, float]:
        """Calcula evolución del engagement a lo largo del tiempo."""
        try:
            if len(user_sessions) < 2:
                return {"trend": "insufficient_data", "change_rate": 0.0}
            
            # Extraer scores de engagement por sesión
            engagement_scores = [
                session.get("engagement_score", 0.5) for session in user_sessions
            ]
            
            # Calcular tendencia
            early_engagement = np.mean(engagement_scores[:len(engagement_scores)//2])
            recent_engagement = np.mean(engagement_scores[len(engagement_scores)//2:])
            
            change_rate = (recent_engagement - early_engagement) / early_engagement if early_engagement > 0 else 0
            
            if change_rate > 0.1:
                trend = "improving"
            elif change_rate < -0.1:
                trend = "declining"
            else:
                trend = "stable"
            
            return {
                "trend": trend,
                "change_rate": change_rate,
                "early_avg": early_engagement,
                "recent_avg": recent_engagement
            }
            
        except Exception as e:
            logger.error(f"Error calculating engagement evolution: {e}")
            return {"trend": "unknown", "change_rate": 0.0}
    
    def _calculate_market_price_factor(
        self,
        price: float,
        market_config: MarketConfig,
        user_profile: Dict[str, Any]
    ) -> float:
        """Calcula factor de precio específico para el mercado."""
        try:
            # Rangos de precio típicos por mercado
            market_price_ranges = {
                "US": {"low": 0, "medium": 100, "high": 500},
                "ES": {"low": 0, "medium": 80, "high": 400}, 
                "MX": {"low": 0, "medium": 50, "high": 200}
            }
            
            ranges = market_price_ranges.get(market_config.id, market_price_ranges["US"])
            
            # Calcular factor basado en rango de precio
            if price <= ranges["low"]:
                return 0.3  # Muy barato, posible baja calidad
            elif price <= ranges["medium"]:
                return 1.0  # Precio óptimo para el mercado
            elif price <= ranges["high"]:
                return 0.7  # Precio alto pero aceptable
            else:
                return 0.4  # Muy caro para el mercado
                
        except Exception as e:
            logger.error(f"Error calculating market price factor: {e}")
            return 0.5
    
    def _calculate_brand_factor(
        self,
        brand: str,
        market_config: MarketConfig,
        user_profile: Dict[str, Any]
    ) -> float:
        """Calcula factor de marca específico para el mercado."""
        try:
            # Marcas populares por mercado (simulado)
            market_brand_preferences = {
                "US": ["apple", "nike", "amazon", "google"],
                "ES": ["zara", "mango", "seat", "telefonica"],
                "MX": ["telcel", "pemex", "corona", "bimbo"]
            }
            
            preferred_brands = market_brand_preferences.get(market_config.id, [])
            brand_lower = brand.lower()
            
            # Factor base
            if brand_lower in preferred_brands:
                return 0.9  # Marca popular en el mercado
            elif brand:  # Tiene marca pero no es local
                return 0.6  # Marca internacional
            else:
                return 0.4  # Sin marca conocida
                
        except Exception as e:
            logger.error(f"Error calculating brand factor: {e}")
            return 0.5
    
    def _determine_personalization_tier(self, context: PersonalizationContext) -> str:
        """Determina el tier de personalización basado en el contexto."""
        if context.personalization_profile.purchase_propensity > 0.8:
            return "premium"
        elif context.personalization_profile.purchase_propensity > 0.5:
            return "standard"
        else:
            return "basic"

    def _build_personalized_user_prompt(
        self,
        context: PersonalizationContext,
        personalized_result: Dict[str, Any]
    ) -> str:
        """Construye prompt del usuario con contexto personalizado.

        FIX (28/03/2026 - Opcion A): El precio ahora se lee desde market_prices
        en lugar de rec.get('price'), que solo contenia el valor CLP crudo.
        market_prices es poblado por ShopifyIntegration.get_products_with_shopify_prices()
        durante el startup con precios autorizados por Shopify para cada mercado.

        Misma logica que _build_advanced_personalization_prompt._get_price_for_prompt().
        Mantener sincronizados si se cambia la logica de formato de precios.
        """
        recommendations = personalized_result.get("recommendations", [])
        market_id = context.mcp_context.current_market_id
        market_currency = context.market_config.currency

        # REFACTOR (30/03/2026): Funcion local _format_price() eliminada.
        # Ahora usa self._format_price_for_market() que centraliza la logica
        # de las 3 prioridades y el WARNING del fallback en un unico lugar.
        # Ver docstring de _format_price_for_market() para detalle completo.

        prompt = f"Usuario consulta: {context.mcp_context.current_query}\n\n"

        if recommendations:
            prompt += "Recomendaciones personalizadas disponibles:\n"
            for i, rec in enumerate(recommendations[:3], 1):
                price_str = self._format_price_for_market(rec, market_id, market_currency)
                prompt += f"{i}. {rec.get('title', 'Producto')} - {price_str}\n"
            prompt += "\n"

        prompt += "Responde de manera personalizada y util, incluyendo las recomendaciones si son relevantes."

        return prompt

    def _calculate_personalization_level(self, context: PersonalizationContext) -> float:
        """Calcula el nivel de personalización aplicado."""
        factors = [
            len(context.personalization_profile.category_affinities) * 0.1,
            context.personalization_profile.purchase_propensity * 0.3,
            len(context.real_time_signals) * 0.05,
            context.conversation_momentum * 0.2
        ]
        return min(sum(factors), 1.0)

    def _evaluate_response_quality(self, response_text: str) -> float:
        """Evalúa la calidad de la respuesta generada."""
        # Evaluación básica de calidad
        quality_score = 0.5  # Base score
        
        if len(response_text) > 50:
            quality_score += 0.2
        if any(word in response_text.lower() for word in ["recomiendo", "sugiero", "perfecto"]):
            quality_score += 0.2
        if response_text.count('.') >= 2:  # Múltiples oraciones
            quality_score += 0.1
        
        return min(quality_score, 1.0)

    def _generate_fallback_response(self, context: PersonalizationContext) -> str:
        """Genera respuesta de fallback cuando Claude falla."""
        market_id = context.market_config.market_id
        
        fallback_responses = {
            "US": "I'm here to help you find the perfect products. Let me assist you with your shopping needs.",
            "ES": "Estoy aquí para ayudarte a encontrar los productos perfectos. Permíteme asistirte con tus necesidades de compra.",
            "MX": "¡Hola! Estoy aquí para ayudarte a encontrar exactamente lo que buscas. ¿En qué te puedo ayudar?"
        }
        
        return fallback_responses.get(market_id, fallback_responses["US"])

    async def _generate_claude_personalized_response_v2(
        self,
        personalization_context: PersonalizationContext,
        personalized_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Genera respuesta conversacional personalizada usando Claude con configuración centralizada.
        
        Esta es la versión secundaria que usa config.to_anthropic_params() y devuelve
        un dict con métricas adicionales (model_used, tokens_used, cost_estimate, etc.).
        Se usa en el path de personalización avanzada cuando se necesitan esas métricas.

        NOTA: La versión principal es _generate_claude_personalized_response() que devuelve
        str puro (FIX 27/03/2026). Esta versión (_v2) es complementaria y devuelve el dict
        completo para casos donde se requieren las métricas de respuesta.
        
        Args:
            personalization_context: Contexto de personalización
            personalized_result: Resultado de personalización previo
            
        Returns:
            Dict con respuesta y métricas de la llamada Claude
        """
        try:
            # 🚀 REFACTORIZADO: Usar configuración centralizada Claude
            call_context = {
                "user_id": personalization_context.mcp_context.user_id,
                "market_id": personalization_context.market_config.market_id,
                "personalization_tier": self._determine_personalization_tier(personalization_context)
            }
            
            config = self.claude_config.get_model_config(call_context)
            
            # Construir prompts personalizados
            system_prompt = self._build_personalized_system_prompt(personalization_context)
            user_prompt = self._build_personalized_user_prompt(
                personalization_context, 
                personalized_result
            )
            
            # Log de diagnóstico para monitorear el tamaño del prompt en producción.
            # Buscar 'mcp_prompt_size' en GCP Logs Explorer para confirmar que los tokens
            # de INPUT están dentro del rango esperado (system ~80t, user ~60t = ~140t total).
            logger.info(
                f"🎯 Generating personalized Claude response with {config.model_name} | "
                f"mcp_prompt_size: system={len(system_prompt)}chars user={len(user_prompt)}chars"
            )
            
            # CORRECCIÓN (21/03/2026): el system prompt va en el parámetro `system=`
            # de la API de Anthropic — NO en messages[] con role="system".
            # Poner role="system" en messages[] es inválido para la API de Anthropic
            # (a diferencia de OpenAI). El SDK puede silenciosamente rechazarlo o
            # tratarlo como un mensaje de usuario, causando comportamiento inesperado
            # y potencialmente re-intentos internos que añaden latencia.
            # Referencia: https://docs.anthropic.com/en/api/messages
            response = await self.claude.messages.create(
                **config.to_anthropic_params(),
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Calcular métricas
            tokens_used = response.usage.output_tokens if hasattr(response, 'usage') else 0
            cost_estimate = (tokens_used * config.cost_per_1k_tokens / 1000) if tokens_used > 0 else 0
            
            return {
                "conversational_response": response.content[0].text,
                "model_used": config.model_name,  # ✅ Siempre correcto desde configuración
                "model_tier": self.claude_config.claude_model_tier.value,
                "tokens_used": tokens_used,
                "cost_estimate": cost_estimate,
                "personalization_level": self._calculate_personalization_level(personalization_context),
                "cultural_adaptation": personalized_result.get("cultural_adaptation", {}),
                "response_quality_score": self._evaluate_response_quality(response.content[0].text)
            }
            
        except Exception as e:
            logger.error(f"Error generating Claude personalized response v2: {e}")
            
            # Fallback response
            return {
                "conversational_response": self._generate_fallback_response(personalization_context),
                "model_used": None,
                "model_tier": self.claude_config.claude_model_tier.value,
                "tokens_used": 0,
                "cost_estimate": 0,
                "error": str(e),
                "fallback_used": True
            }


# === CLASE AUXILIAR PARA ANÁLISIS DE INSIGHTS ===

class PersonalizationInsightsAnalyzer:
    """
    Analizador especializado para extraer insights profundos
    de datos de personalización y generar recomendaciones accionables.
    """

    def __init__(self, redis_client=None, redis_service=None):
        """
        Initialize PersonalizationInsightsAnalyzer with enterprise Redis support.

        Args:
            redis_client: Legacy raw Redis client (puede ser None).
            redis_service: RedisService enterprise (preferido). Si ambos son None,
                           los métodos de análisis devolverán datos vacíos gracefully.
        """
        # ✅ ENTERPRISE FIX (17/03/2026): soportar redis_service (enterprise)
        # además del redis_client legacy.  self.redis podría ser None si la clase
        # se instancia sin argumentos — todos los métodos deben usar el patrón
        # `redis_client = self.redis_service or self.redis` antes de llamar a Redis.
        self.redis_service = redis_service
        self.redis = redis_client  # Legacy compatibility — puede ser None
        
    async def generate_comprehensive_user_report(
        self,
        user_id: str,
        market_id: str,
        analysis_depth: str = "standard"
    ) -> Dict[str, Any]:
        """
        Genera reporte comprehensivo del usuario con insights accionables.
        
        Args:
            user_id: ID del usuario
            market_id: Mercado a analizar
            analysis_depth: "basic", "standard", "deep"
            
        Returns:
            Reporte completo con insights y recomendaciones
        """
        try:
            report = {
                "user_id": user_id,
                "market_id": market_id,
                "analysis_depth": analysis_depth,
                "generated_at": datetime.utcnow().isoformat(),
                "report_sections": {}
            }
            
            # Sección 1: Perfil de comportamiento
            if analysis_depth in ["standard", "deep"]:
                behavioral_profile = await self._analyze_behavioral_profile(user_id, market_id)
                report["report_sections"]["behavioral_profile"] = behavioral_profile
            
            # Sección 2: Análisis de conversaciones
            conversation_analysis = await self._analyze_conversation_effectiveness(user_id, market_id)
            report["report_sections"]["conversation_analysis"] = conversation_analysis
            
            # Sección 3: Recomendaciones de optimización
            optimization_recs = await self._generate_optimization_recommendations(user_id, market_id)
            report["report_sections"]["optimization_recommendations"] = optimization_recs
            
            # Sección 4: Análisis predictivo (solo para análisis profundo)
            if analysis_depth == "deep":
                predictive_analysis = await self._perform_deep_predictive_analysis(user_id, market_id)
                report["report_sections"]["predictive_analysis"] = predictive_analysis
            
            # Sección 5: Resumen ejecutivo
            executive_summary = self._generate_executive_summary(report["report_sections"])
            report["executive_summary"] = executive_summary
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating comprehensive user report: {e}")
            return {"error": str(e), "user_id": user_id}
    
    async def _analyze_behavioral_profile(self, user_id: str, market_id: str) -> Dict[str, Any]:
        """Analiza el perfil comportamental detallado del usuario."""
        try:
            # ✅ ENTERPRISE: Usar redis_service si está disponible, fallback a redis
            redis_client = self.redis_service or self.redis
            if not redis_client:
                return {"status": "no_redis", "message": "Redis no disponible"}

            # Obtener datos históricos del usuario
            profile_key = f"mcp:personalization:profile:{user_id}"
            profile_data = await redis_client.get(profile_key)
            
            if not profile_data:
                return {"status": "no_data", "message": "Perfil no encontrado"}
            
            profile = json.loads(profile_data)
            
            # Análisis de patrones comportamentales
            behavioral_patterns = profile.get("behavioral_patterns", {})
            
            analysis = {
                "interaction_style": self._classify_interaction_style(behavioral_patterns),
                "purchase_behavior": self._analyze_purchase_behavior(profile),
                "category_preferences": self._analyze_category_preferences(profile),
                "temporal_patterns": self._analyze_temporal_patterns(behavioral_patterns),
                "engagement_characteristics": self._analyze_engagement_characteristics(profile),
                "market_adaptation": self._analyze_market_adaptation(profile, market_id)
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing behavioral profile: {e}")
            return {"error": str(e)}
    
    async def _analyze_conversation_effectiveness(self, user_id: str, market_id: str) -> Dict[str, Any]:
        """Analiza la efectividad de las conversaciones del usuario."""
        try:
            # ✅ ENTERPRISE: Usar redis_service si está disponible, fallback a redis
            redis_client = self.redis_service or self.redis
            if not redis_client:
                return {"status": "no_redis", "message": "Redis no disponible"}

            # Buscar sesiones conversacionales
            session_keys = await redis_client.keys(f"mcp:conversation:*{user_id}*")

            if not session_keys:
                return {"status": "no_conversations", "message": "No hay conversaciones registradas"}

            # Métricas de efectividad
            total_sessions = len(session_keys)
            successful_sessions = 0
            avg_satisfaction = 0.0

            for key in session_keys:
                session_data = await redis_client.get(key)
                if session_data:
                    session = json.loads(session_data)
                    if session.get("current_market_id") == market_id:
                        # Análizar efectividad de la sesión
                        effectiveness_score = self._calculate_session_effectiveness(session)
                        if effectiveness_score > 0.7:
                            successful_sessions += 1
                        avg_satisfaction += effectiveness_score
            
            if total_sessions > 0:
                avg_satisfaction /= total_sessions
            
            analysis = {
                "total_sessions_analyzed": total_sessions,
                "success_rate": successful_sessions / max(total_sessions, 1),
                "avg_satisfaction_score": avg_satisfaction,
                "conversation_quality_metrics": {
                    "clarity_score": self._calculate_clarity_score(session_keys),
                    "relevance_score": self._calculate_relevance_score(session_keys),
                    "completion_rate": successful_sessions / max(total_sessions, 1)
                },
                "improvement_areas": self._identify_conversation_improvement_areas(session_keys)
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing conversation effectiveness: {e}")
            return {"error": str(e)}
    
    async def _generate_optimization_recommendations(self, user_id: str, market_id: str) -> List[Dict[str, Any]]:
        """Genera recomendaciones específicas de optimización."""
        try:
            recommendations = []
            
            # ✅ ENTERPRISE: Usar redis_service si está disponible, fallback a redis
            redis_client = self.redis_service or self.redis
            if not redis_client:
                return []

            # Obtener perfil y sesiones para análisis
            profile_key = f"mcp:personalization:profile:{user_id}"
            profile_data = await redis_client.get(profile_key)
            
            if profile_data:
                profile = json.loads(profile_data)
                
                # Recomendación 1: Optimización de timing
                temporal_patterns = profile.get("behavioral_patterns", {}).get("temporal_preferences", {})
                if temporal_patterns:
                    peak_hour = max(temporal_patterns, key=temporal_patterns.get)
                    recommendations.append({
                        "category": "timing_optimization",
                        "title": "Optimizar Horario de Interacción",
                        "description": f"Usuario más activo a las {peak_hour.replace('hour_', '')}:00",
                        "action_items": [
                            f"Programar notificaciones para las {peak_hour.replace('hour_', '')}:00",
                            "Ajustar disponibilidad de soporte en horario pico",
                            "Lanzar ofertas especiales en horario óptimo"
                        ],
                        "priority": "medium",
                        "estimated_impact": 0.20,
                        "implementation_difficulty": "low"
                    })
                
                # Recomendación 2: Personalización de categorías
                category_affinities = profile.get("category_affinities", {})
                if category_affinities:
                    top_category = max(category_affinities, key=category_affinities.get)
                    recommendations.append({
                        "category": "content_personalization",
                        "title": "Personalizar Contenido por Categoría",
                        "description": f"Alta afinidad por {top_category}",
                        "action_items": [
                            f"Priorizar productos de {top_category} en recomendaciones",
                            f"Crear contenido especializado sobre {top_category}",
                            f"Configurar alertas de nuevos productos en {top_category}"
                        ],
                        "priority": "high",
                        "estimated_impact": 0.35,
                        "implementation_difficulty": "medium"
                    })
                
                # Recomendación 3: Optimización de propensión de compra
                purchase_propensity = profile.get("purchase_propensity", 0.5)
                if purchase_propensity < 0.6:
                    recommendations.append({
                        "category": "conversion_optimization",
                        "title": "Mejorar Propensión de Compra",
                        "description": f"Propensión actual: {purchase_propensity:.2f}",
                        "action_items": [
                            "Implementar pruebas sociales más efectivas",
                            "Ofrecer garantías extendidas",
                            "Simplificar proceso de checkout",
                            "Añadir elementos de urgencia apropiados"
                        ],
                        "priority": "critical",
                        "estimated_impact": 0.45,
                        "implementation_difficulty": "high"
                    })
                elif purchase_propensity > 0.8:
                    recommendations.append({
                        "category": "upselling_optimization",
                        "title": "Optimizar para Upselling",
                        "description": f"Alta propensión de compra: {purchase_propensity:.2f}",
                        "action_items": [
                            "Mostrar productos premium/complementarios",
                            "Implementar bundles personalizados",
                            "Ofrecer upgrades relevantes",
                            "Activar programas de lealtad"
                        ],
                        "priority": "high",
                        "estimated_impact": 0.30,
                        "implementation_difficulty": "medium"
                    })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating optimization recommendations: {e}")
            return []
    
    async def _perform_deep_predictive_analysis(self, user_id: str, market_id: str) -> Dict[str, Any]:
        """Realiza análisis predictivo profundo del comportamiento del usuario."""
        try:
            # ✅ ENTERPRISE: Usar redis_service si está disponible, fallback a redis
            redis_client = self.redis_service or self.redis
            if not redis_client:
                return {"status": "no_redis"}

            # Obtener datos históricos extensos
            profile_key = f"mcp:personalization:profile:{user_id}"
            profile_data = await redis_client.get(profile_key)
            
            if not profile_data:
                return {"status": "insufficient_data"}
            
            profile = json.loads(profile_data)
            
            # Análisis predictivo avanzado
            predictive_insights = {
                "lifecycle_stage": self._predict_customer_lifecycle_stage(profile),
                "churn_probability": self._calculate_churn_probability(profile),
                "lifetime_value_prediction": self._predict_customer_lifetime_value(profile, market_id),
                "next_purchase_prediction": self._predict_next_purchase_timing(profile),
                "category_expansion_opportunities": self._predict_category_expansion(profile),
                "price_sensitivity_evolution": self._predict_price_sensitivity_changes(profile),
                "seasonal_behavior_patterns": self._analyze_seasonal_patterns(profile),
                "cross_market_potential": self._analyze_cross_market_potential(profile, market_id)
            }
            
            return predictive_insights
            
        except Exception as e:
            logger.error(f"Error performing deep predictive analysis: {e}")
            return {"error": str(e)}
    
    def _generate_executive_summary(self, report_sections: Dict[str, Any]) -> Dict[str, Any]:
        """Genera resumen ejecutivo del reporte de usuario."""
        try:
            summary = {
                "key_insights": [],
                "critical_actions": [],
                "business_impact": {},
                "risk_factors": [],
                "opportunities": []
            }
            
            # Extraer insights clave de cada sección
            if "behavioral_profile" in report_sections:
                behavioral = report_sections["behavioral_profile"]
                if behavioral.get("interaction_style"):
                    summary["key_insights"].append(
                        f"Estilo de interacción: {behavioral['interaction_style']}"
                    )
            
            if "conversation_analysis" in report_sections:
                conv_analysis = report_sections["conversation_analysis"]
                success_rate = conv_analysis.get("success_rate", 0)
                if success_rate < 0.7:
                    summary["critical_actions"].append(
                        "Mejorar efectividad conversacional"
                    )
                    summary["risk_factors"].append(
                        f"Baja tasa de éxito conversacional: {success_rate:.2f}"
                    )
                else:
                    summary["opportunities"].append(
                        "Alta efectividad conversacional - expandir estrategias"
                    )
            
            if "optimization_recommendations" in report_sections:
                recs = report_sections["optimization_recommendations"]
                high_priority_recs = [r for r in recs if r.get("priority") == "critical"]
                for rec in high_priority_recs:
                    summary["critical_actions"].append(rec["title"])
            
            if "predictive_analysis" in report_sections:
                predictive = report_sections["predictive_analysis"]
                churn_prob = predictive.get("churn_probability", 0)
                if churn_prob > 0.7:
                    summary["risk_factors"].append(
                        f"Alta probabilidad de churn: {churn_prob:.2f}"
                    )
                
                ltv = predictive.get("lifetime_value_prediction", {})
                if ltv.get("predicted_value", 0) > 1000:
                    summary["opportunities"].append(
                        f"Alto valor de vida del cliente: ${ltv.get('predicted_value', 0):.2f}"
                    )
            
            # Calcular impacto de negocio estimado
            total_impact = 0
            if "optimization_recommendations" in report_sections:
                for rec in report_sections["optimization_recommendations"]:
                    total_impact += rec.get("estimated_impact", 0)
            
            summary["business_impact"] = {
                "estimated_conversion_improvement": f"{total_impact:.1%}",
                "priority_level": "high" if len(summary["critical_actions"]) > 0 else "medium",
                "implementation_timeline": "2-4 weeks" if total_impact > 0.5 else "1-2 weeks"
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating executive summary: {e}")
            return {"error": str(e)}
    
    # === MÉTODOS AUXILIARES DE ANÁLISIS ===
    
    def _classify_interaction_style(self, behavioral_patterns: Dict) -> str:
        """Clasifica el estilo de interacción del usuario."""
        interaction_data = behavioral_patterns.get("category_interactions", {})
        temporal_data = behavioral_patterns.get("temporal_preferences", {})
        
        if not interaction_data:
            return "insufficient_data"
        
        # Análisis de frecuencia de interacciones
        total_interactions = sum(interaction_data.values())
        diversity_score = len(interaction_data) / max(total_interactions, 1)
        
        if diversity_score > 0.3:
            return "explorer"  # Usuario que explora muchas categorías
        elif total_interactions > 20:
            return "engaged"   # Usuario muy activo
        elif len(temporal_data) > 5:
            return "consistent" # Usuario con patrones regulares
        else:
            return "casual"    # Usuario casual
    
    def _analyze_purchase_behavior(self, profile: Dict) -> Dict[str, Any]:
        """Analiza el comportamiento de compra del usuario."""
        purchase_propensity = profile.get("purchase_propensity", 0.5)
        price_sensitivity = profile.get("price_sensitivity_curve", {})
        
        behavior_analysis = {
            "propensity_level": "high" if purchase_propensity > 0.7 else "medium" if purchase_propensity > 0.4 else "low",
            "price_sensitivity_profile": self._classify_price_sensitivity(price_sensitivity),
            "decision_making_style": "quick" if purchase_propensity > 0.8 else "deliberate",
            "risk_tolerance": "high" if purchase_propensity > 0.7 else "moderate"
        }
        
        return behavior_analysis
    
    def _analyze_category_preferences(self, profile: Dict) -> Dict[str, Any]:
        """Analiza las preferencias de categoría del usuario."""
        category_affinities = profile.get("category_affinities", {})
        
        if not category_affinities:
            return {"status": "no_preferences_detected"}
        
        # Categorizar preferencias
        sorted_categories = sorted(category_affinities.items(), key=lambda x: x[1], reverse=True)
        
        analysis = {
            "primary_interests": sorted_categories[:3],
            "interest_diversity": len(category_affinities),
            "specialization_level": "specialist" if len(sorted_categories) <= 3 else "generalist",
            "emerging_interests": [cat for cat, score in sorted_categories if 0.1 <= score <= 0.3]
        }
        
        return analysis
    
    def _analyze_temporal_patterns(self, behavioral_patterns: Dict) -> Dict[str, Any]:
        """Analiza patrones temporales de interacción."""
        temporal_prefs = behavioral_patterns.get("temporal_preferences", {})
        
        if not temporal_prefs:
            return {"status": "no_temporal_data"}
        
        peak_hour = max(temporal_prefs, key=temporal_prefs.get) if temporal_prefs else None
        
        return {
            "peak_activity_hour": peak_hour.replace("hour_", "") if peak_hour else None,
            "total_time_slots_active": len(temporal_prefs),
            "activity_distribution": temporal_prefs
        }
    
    def _analyze_engagement_characteristics(self, profile: Dict) -> Dict[str, Any]:
        """Analiza las características de engagement del usuario."""
        return {
            "conversation_style": profile.get("conversation_style", "standard"),
            "purchase_propensity": profile.get("purchase_propensity", 0.5),
            "category_diversity": len(profile.get("category_affinities", {})),
            "cross_market_presence": len(profile.get("cross_market_insights", {}).get("market_behaviors", {}))
        }
    
    def _analyze_market_adaptation(self, profile: Dict, market_id: str) -> Dict[str, Any]:
        """Analiza la adaptación del usuario al mercado específico."""
        market_behaviors = profile.get("cross_market_insights", {}).get("market_behaviors", {})
        market_data = market_behaviors.get(market_id, {})
        
        return {
            "sessions_in_market": market_data.get("total_sessions", 0),
            "avg_turns_in_market": market_data.get("avg_turns_per_session", 0),
            "last_activity": market_data.get("last_activity", 0),
            "market_engagement_level": "high" if market_data.get("total_sessions", 0) > 5 else "low"
        }
    
    def _classify_price_sensitivity(self, price_curve: Dict) -> str:
        """Clasifica el perfil de sensibilidad al precio."""
        if not price_curve:
            return "unknown"
        
        high_sensitivity = price_curve.get("high", 0.5)
        medium_sensitivity = price_curve.get("medium", 0.5)
        low_sensitivity = price_curve.get("low", 0.5)
        
        if high_sensitivity > 0.7:
            return "price_conscious"
        elif low_sensitivity > 0.6:
            return "value_seeker"
        elif medium_sensitivity > 0.6:
            return "balanced"
        else:
            return "premium_oriented"
    
    def _calculate_session_effectiveness(self, session: Dict) -> float:
        """Calcula la efectividad de una sesión conversacional."""
        try:
            effectiveness_factors = []
            
            # Factor 1: Duración apropiada
            turns = session.get("turns", [])
            if len(turns) >= 3:  # Conversación sustancial
                effectiveness_factors.append(0.3)
            
            # Factor 2: Engagement score
            engagement = session.get("engagement_score", 0.5)
            effectiveness_factors.append(engagement * 0.4)
            
            # Factor 3: Resolución de intención
            intent_history = session.get("intent_history", [])
            if intent_history and intent_history[-1].get("confidence", 0) > 0.7:
                effectiveness_factors.append(0.3)
            
            return sum(effectiveness_factors)
            
        except Exception as e:
            logger.error(f"Error calculating session effectiveness: {e}")
            return 0.5
    
    def _calculate_clarity_score(self, session_keys: List) -> float:
        """Calcula score de claridad de conversaciones (simplificado)."""
        # En implementación real, analizaría la claridad de las respuestas
        return 0.75  # Placeholder
    
    def _calculate_relevance_score(self, session_keys: List) -> float:
        """Calcula score de relevancia de conversaciones (simplificado)."""
        # En implementación real, analizaría la relevancia de las recomendaciones
        return 0.80  # Placeholder
    
    def _identify_conversation_improvement_areas(self, session_keys: List) -> List[str]:
        """Identifica áreas de mejora en conversaciones (simplificado)."""
        # En implementación real, analizaría patrones de bajo rendimiento
        return ["Mejorar claridad de respuestas", "Aumentar relevancia de recomendaciones"]
    
    def _predict_customer_lifecycle_stage(self, profile: Dict) -> str:
        """Predice la etapa del ciclo de vida del cliente."""
        purchase_propensity = profile.get("purchase_propensity", 0.5)
        behavioral_patterns = profile.get("behavioral_patterns", {})
        category_diversity = len(profile.get("category_affinities", {}))
        
        if purchase_propensity < 0.3 and category_diversity <= 2:
            return "awareness"
        elif purchase_propensity < 0.6 and category_diversity <= 4:
            return "consideration"
        elif purchase_propensity >= 0.6:
            return "purchase_ready"
        else:
            return "evaluation"
    
    def _calculate_churn_probability(self, profile: Dict) -> float:
        """Calcula la probabilidad de churn del usuario."""
        try:
            # Factores de riesgo de churn
            risk_factors = []
            
            # Factor 1: Baja propensión de compra
            purchase_propensity = profile.get("purchase_propensity", 0.5)
            if purchase_propensity < 0.3:
                risk_factors.append(0.4)
            
            # Factor 2: Actividad decreciente
            last_updated = profile.get("last_updated", 0)
            days_since_update = (time.time() - last_updated) / (24 * 3600)
            if days_since_update > 30:
                risk_factors.append(0.3)
            
            # Factor 3: Bajo engagement en categorías
            category_affinities = profile.get("category_affinities", {})
            avg_affinity = np.mean(list(category_affinities.values())) if category_affinities else 0
            if avg_affinity < 0.3:
                risk_factors.append(0.3)
            
            return min(sum(risk_factors), 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating churn probability: {e}")
            return 0.5
    
    def _predict_customer_lifetime_value(self, profile: Dict, market_id: str) -> Dict[str, Any]:
        """Predice el valor de vida del cliente."""
        try:
            # Factores base para CLV
            purchase_propensity = profile.get("purchase_propensity", 0.5)
            category_diversity = len(profile.get("category_affinities", {}))
            
            # Valores base por mercado
            market_base_values = {
                "US": 500,
                "ES": 350, 
                "MX": 200
            }
            
            base_value = market_base_values.get(market_id, 300)
            
            # Multiplicadores
            propensity_multiplier = 1 + purchase_propensity
            diversity_multiplier = 1 + (category_diversity * 0.1)
            
            predicted_value = base_value * propensity_multiplier * diversity_multiplier
            
            return {
                "predicted_value": round(predicted_value, 2),
                "confidence": 0.7,
                "contributing_factors": {
                    "purchase_propensity": purchase_propensity,
                    "category_diversity": category_diversity,
                    "market_base": base_value
                }
            }
            
        except Exception as e:
            logger.error(f"Error predicting customer lifetime value: {e}")
            return {"predicted_value": 0, "confidence": 0.0}
    
    def _predict_next_purchase_timing(self, profile: Dict) -> Dict[str, Any]:
        """Predice el timing de la próxima compra (simplificado)."""
        purchase_propensity = profile.get("purchase_propensity", 0.5)
        
        if purchase_propensity > 0.8:
            days_estimate = 3
            confidence = 0.8
        elif purchase_propensity > 0.6:
            days_estimate = 7
            confidence = 0.65
        elif purchase_propensity > 0.4:
            days_estimate = 14
            confidence = 0.5
        else:
            days_estimate = 30
            confidence = 0.3
        
        return {
            "estimated_days_to_purchase": days_estimate,
            "confidence": confidence,
            "trigger_factors": ["engagement_increase", "category_browsing"]
        }
    
    def _predict_category_expansion(self, profile: Dict) -> List[str]:
        """Predice categorías de expansión potencial."""
        category_affinities = profile.get("category_affinities", {})
        
        if not category_affinities:
            return []
        
        # Categorías con afinidad media (candidatas a expansión)
        expansion_candidates = [
            cat for cat, score in category_affinities.items()
            if 0.2 <= score <= 0.5
        ]
        
        return expansion_candidates[:3]  # Top 3 candidatos
    
    def _predict_price_sensitivity_changes(self, profile: Dict) -> Dict[str, Any]:
        """Predice cambios en sensibilidad al precio."""
        current_sensitivity = profile.get("price_sensitivity_curve", {})
        purchase_propensity = profile.get("purchase_propensity", 0.5)
        
        # Usuarios con alta propensión tienden a ser menos sensibles al precio
        predicted_direction = "decreasing" if purchase_propensity > 0.7 else "stable"
        
        return {
            "current_profile": self._classify_price_sensitivity(current_sensitivity),
            "predicted_direction": predicted_direction,
            "confidence": 0.6
        }
    
    def _analyze_seasonal_patterns(self, profile: Dict) -> Dict[str, Any]:
        """Analiza patrones estacionales del usuario (simplificado)."""
        temporal_patterns = profile.get("temporal_patterns", {})
        
        return {
            "seasonal_data_available": bool(temporal_patterns),
            "peak_seasons": temporal_patterns.get("peak_seasons", []),
            "activity_consistency": "high" if len(temporal_patterns) > 3 else "low"
        }
    
    def _analyze_cross_market_potential(self, profile: Dict, current_market_id: str) -> Dict[str, Any]:
        """Analiza el potencial de expansión cross-market."""
        cross_market_data = profile.get("cross_market_insights", {}).get("market_behaviors", {})
        
        markets_active = list(cross_market_data.keys())
        markets_potential = [m for m in ["US", "ES", "MX", "CL"] 
                            if m not in markets_active and m != current_market_id]
        
        return {
            "currently_active_markets": markets_active,
            "potential_expansion_markets": markets_potential[:2],
            "cross_market_score": len(markets_active) / 4  # 4 mercados totales
        }
    
    def _classify_price_sensitivity(self, price_curve: Dict) -> str:
        """Clasifica el perfil de sensibilidad al precio."""
        if not price_curve:
            return "unknown"
        
        high_sensitivity = price_curve.get("high", 0.5)
        medium_sensitivity = price_curve.get("medium", 0.5)
        low_sensitivity = price_curve.get("low", 0.5)
        
        if high_sensitivity > 0.7:
            return "price_conscious"
        elif low_sensitivity > 0.6:
            return "value_seeker"
        elif medium_sensitivity > 0.6:
            return "balanced"
        else:
            return "premium_oriented"


# === FACTORY REFACTORIZADO ===

async def create_mcp_personalization_engine(
    anthropic_api_key: str,
    conversation_manager: OptimizedConversationAIManager = None,
    state_manager: MCPConversationStateManager = None,
    redis_client=None,  # Legacy compatibility parameter
    profile_ttl: int = 604800,
    enable_ml_predictions: bool = True,
    **kwargs
) -> Optional[MCPPersonalizationEngine]:
    """
    ✅ ENTERPRISE FACTORY: Create MCPPersonalizationEngine with enterprise architecture
    
    Uses ServiceFactory for orchestration and business logic.
    
    Args:
        anthropic_api_key: API key de Anthropic
        conversation_manager: Gestor de conversaciones optimizado
        state_manager: Gestor de estado conversacional MCP
        redis_client: Legacy compatibility (unused in enterprise mode)
        profile_ttl: TTL para perfiles de personalización
        enable_ml_predictions: Habilitar predicciones ML
        **kwargs: Argumentos adicionales de configuración
        
    Returns:
        Instancia configurada de MCPPersonalizationEngine
    """
    try:
        # ✅ FIX: Import ServiceFactory in function scope to avoid circular import
        from src.api.factories.service_factory import ServiceFactory
        
        # ✅ ENTERPRISE: Use ServiceFactory for orchestration
        redis_service = await ServiceFactory.get_redis_service()
        
        # Health check antes de crear engine
        health = await redis_service.health_check()
        if health['status'] != 'healthy':
            logger.warning("Redis unhealthy - creating engine with limited functionality")
        
        # anthropic_client = Anthropic(api_key=anthropic_api_key)
        anthropic_client = AsyncAnthropic(api_key=anthropic_api_key)
        
        # Obtener shopify_client para resolucion lazy de precios.
        # init_shopify() devuelve la instancia singleton ya creada en startup
        # (no hace ninguna conexion extra — es solo un getter).
        from src.api.core.store import init_shopify
        shopify_client = init_shopify()

        engine = MCPPersonalizationEngine(
            redis_service=redis_service,  # Use SERVICE for orchestration
            anthropic_client=anthropic_client,
            conversation_manager=conversation_manager,
            state_manager=state_manager,
            profile_ttl=profile_ttl,
            enable_ml_predictions=enable_ml_predictions,
            shopify_client=shopify_client,  # Para resolucion lazy de precios
            **kwargs
        )
        
        logger.info("🚀 MCPPersonalizationEngine created successfully with centralized configuration")
        return engine
        
    except Exception as e:
        logger.error(f"Error creating MCPPersonalizationEngine: {e}")
        raise


# === EJEMPLO DE USO E INTEGRACIÓN ===

"""
# Ejemplo de integración en el pipeline principal

async def integrate_personalization_engine():
    # 1. Inicializar dependencias
    redis_client = None  # RedisClient()
    conversation_manager = OptimizedConversationAIManager(...)
    state_manager = MCPConversationStateManager(...)
    
    # 2. Crear motor de personalización
    personalization_engine = create_mcp_personalization_engine(
        redis_client=redis_client,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        conversation_manager=conversation_manager,
        state_manager=state_manager,
        enable_ml_predictions=True
    )
    
    # 3. Ejemplo de uso en endpoint de recomendaciones
    @app.post("/v1/mcp/personalized-recommendations")
    async def get_personalized_recommendations(
        user_id: str,
        message: str,
        market_id: str = "US"
    ):
        # Obtener contexto conversacional
        mcp_context = await state_manager.load_conversation_state(session_id)
        
        if not mcp_context:
            mcp_context = await state_manager.create_conversation_context(
                session_id=f"session_{user_id}_{int(time.time())}",
                user_id=user_id,
                initial_query=message,
                market_context={"market_id": market_id},
                user_agent=request.headers.get("User-Agent", "unknown")
            )
        
        # Obtener recomendaciones base
        base_recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=10
        )
        
        # Aplicar personalización avanzada
        personalized_result = await personalization_engine.generate_personalized_response(
            mcp_context=mcp_context,
            recommendations=base_recommendations,
            strategy=PersonalizationStrategy.HYBRID
        )
        
        return personalized_result

# 4. Análisis de usuario para insights
async def analyze_user_journey():
    insights_analyzer = PersonalizationInsightsAnalyzer(redis_client)
    
    user_report = await insights_analyzer.generate_comprehensive_user_report(
        user_id="user_123",
        market_id="ES",
        analysis_depth="deep"
    )
    
    return user_report
"""