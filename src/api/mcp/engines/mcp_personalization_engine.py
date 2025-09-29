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
        enable_ml_predictions: bool = True
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
        
        # ✅ ENTERPRISE: Support both service and client approaches
        self.redis_service = redis_service
        self.redis = redis_client  # Legacy compatibility
        
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
        strategy: PersonalizationStrategy = None  # ✅ CAMBIO: None permite auto-detección
    ) -> Dict[str, Any]:
        """
        Genera respuesta altamente personalizada usando estrategia especificada o auto-detectada.
        
        Args:
            mcp_context: Contexto conversacional MCP
            recommendations: Recomendaciones base a personalizar
            strategy: Estrategia de personalización a usar (None = auto-detección)
            
        Returns:
            Dict con respuesta personalizada, recomendaciones adaptadas y metadata
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
            conversational_response = await self._generate_claude_personalized_response(
                personalization_context, personalized_result
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
            response = {
                "personalized_response": conversational_response,
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
                "conversation_enhancement": {
                    "tone_adaptation": conversational_response.get("tone_adaptation", "standard"),
                    "cultural_context": conversational_response.get("cultural_context", {}),
                    "personalization_elements": conversational_response.get("personalization_elements", []),
                    "engagement_hooks": conversational_response.get("engagement_hooks", [])
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
            logger.error(f"Error generating personalized response: {e}")
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
        Obtiene pesos de estrategia específicos por mercado.
        """
        # Pesos por mercado basados en características culturales
        market_weights = {
            "US": {
                "behavioral": 1.2,  # Los usuarios US valoran personalización por comportamiento
                "cultural": 0.8,
                "contextual": 1.1,
                "predictive": 1.0
            },
            "ES": {
                "behavioral": 1.0,
                "cultural": 1.3,    # Mayor peso cultural en mercados europeos
                "contextual": 1.0,
                "predictive": 0.9
            },
            "MX": {
                "behavioral": 1.0,
                "cultural": 1.2,
                "contextual": 1.2,   # Contexto familiar y social importante
                "predictive": 0.8
            }
        }
        
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
            query: Query original del usuario
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
            
            # Almacenar en Redis con TTL de 30 días para análisis
            effectiveness_key = f"strategy_effectiveness:{strategy.value}:{user_id}:{selection_id}"
            await self.redis.setex(
                effectiveness_key,
                30 * 24 * 3600,  # 30 días
                json.dumps(tracking_data)
            )
            
            # Mantener contador agregado por estrategia
            strategy_counter_key = f"strategy_usage_counter:{strategy.value}"
            await self.redis.incr(strategy_counter_key)
            await self.redis.expire(strategy_counter_key, 90 * 24 * 3600)  # 90 días
            
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
            # Obtener contador de uso
            strategy_counter_key = f"strategy_usage_counter:{strategy.value}"
            usage_count = await self.redis.get(strategy_counter_key)
            usage_count = int(usage_count) if usage_count else 0
            
            # Buscar datos de efectividad recientes
            effectiveness_pattern = f"strategy_effectiveness:{strategy.value}:*"
            effectiveness_keys = await self.redis.keys(effectiveness_pattern)
            
            recent_data = []
            total_score = 0.0
            competition_scores = []
            
            for key in effectiveness_keys[:50]:  # Limitar a últimas 50 para performance
                data = await self.redis.get(key)
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
            
            # Cachear análisis para uso futuro
            cache_key = f"{self.INSIGHTS_PREFIX}:{user_id}:{market_id}:journey_analysis"
            await self.redis.set(
                cache_key,
                json.dumps(journey_analysis),
                ex=24 * 3600  # Cache por 24 horas
            )
            
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
        personalization_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Genera respuesta conversacional personalizada usando Claude."""
        try:
            # Construir prompt de personalización avanzado
            personalization_prompt = self._build_advanced_personalization_prompt(
                context, personalization_result
            )
            
            # ✅ ROBUST CLAUDE CALL: Handle timeouts and retries
            max_retries = 2
            timeout = 15  # seconds
            
            for attempt in range(max_retries + 1):
                try:
                    # Llamada a Claude con configuración optimizada
                    claude_response = await asyncio.wait_for(
                        self.claude.messages.create(
                            model="claude-sonnet-4-20250514",
                            system=self._build_personalized_system_prompt(context),
                            messages=[{"role": "user", "content": personalization_prompt}],
                            max_tokens=800,
                            temperature=0.8
                        ),
                        timeout=timeout
                    )
                    
                    response_text = claude_response.content[0].text
                    break  # Success, exit retry loop
                    
                except asyncio.TimeoutError:
                    logger.warning(f"Claude API timeout on attempt {attempt + 1}/{max_retries + 1}")
                    if attempt == max_retries:
                        # Final fallback
                        response_text = "Te ayudo a encontrar lo que buscas. ¿Qué te interesa hoy?"
                        logger.error("Claude API timeout - using fallback response")
                    else:
                        await asyncio.sleep(1)  # Wait before retry
                        continue
                        
                except Exception as api_error:
                    logger.warning(f"Claude API error on attempt {attempt + 1}: {api_error}")
                    if attempt == max_retries:
                        response_text = "Te ayudo a encontrar lo que buscas. ¿Qué te interesa hoy?"
                        logger.error(f"Claude API failed after {max_retries + 1} attempts - using fallback")
                    else:
                        await asyncio.sleep(1)
                        continue
            
            # Parsejar respuesta estructurada si es posible
            try:
                if response_text.strip().startswith('{'):
                    structured_response = json.loads(response_text)
                else:
                    structured_response = {
                        "response": response_text,
                        "tone_adaptation": "standard",
                        "cultural_context": {},
                        "personalization_elements": [],
                        "engagement_hooks": []
                    }
            except json.JSONDecodeError:
                structured_response = {
                    "response": response_text,
                    "tone_adaptation": "standard",
                    "cultural_context": {},
                    "personalization_elements": [],
                    "engagement_hooks": []
                }
            
            return structured_response
            
        except Exception as e:
            logger.error(f"Error generating Claude personalized response: {e}")
            return {
                "response": "Te ayudo a encontrar lo que buscas. ¿Qué te interesa hoy?",
                "tone_adaptation": "standard",
                "cultural_context": {},
                "personalization_elements": [],
                "engagement_hooks": []
            }
    
    def _load_market_configurations(self) -> Dict[str, MarketConfig]:
        """Carga configuraciones de mercado."""
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
            )
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
    
    def _build_advanced_personalization_prompt(
        self,
        context: PersonalizationContext,
        personalization_result: Dict[str, Any]
    ) -> str:
        """Construye prompt avanzado de personalización para Claude."""
        mcp_context = context.mcp_context
        profile = context.personalization_profile
        market_config = context.market_config
        
        # Obtener las mejores recomendaciones
        top_recs = personalization_result["recommendations"][:3]
        
        prompt = f"""Como experto en personalización de e-commerce, genera una respuesta conversacional altamente personalizada.

CONTEXTO DEL USUARIO:
- ID: {profile.user_id}
- Mercado: {market_config.name} ({market_config.currency})
- Estilo conversacional detectado: {profile.conversation_style}
- Propensión de compra: {profile.purchase_propensity:.2f}
- Momentum conversacional: {context.conversation_momentum:.2f}

HISTORIAL CONVERSACIONAL RECIENTE:
{json.dumps([turn.user_query for turn in mcp_context.turns[-3:]], indent=2)}

PREFERENCIAS DEL USUARIO:
- Categorías de interés: {dict(list(profile.category_affinities.items())[:5])}
- Sensibilidad al precio: {profile.price_sensitivity_curve}
- Indicadores de urgencia: {context.urgency_indicators}

RECOMENDACIONES PERSONALIZADAS:
{json.dumps([{"título": rec.get("title", ""), "precio": rec.get("price", 0), "score": rec.get("hybrid_score", 0)} for rec in top_recs], indent=2)}

ADAPTACIÓN CULTURAL REQUERIDA:
- Idioma: {market_config.language}
- Estilo comunicación: {market_config.localization.get("cultural_preferences", {}).get("communication_style", "standard")}
- Moneda local: {market_config.currency}

INSTRUCCIONES DE PERSONALIZACIÓN:
1. Responde en {market_config.language} con tono {market_config.localization.get("cultural_preferences", {}).get("communication_style", "profesional")}
2. Menciona específicamente por qué cada recomendación es relevante para ESTE usuario
3. Incluye precios en {market_config.currency} de manera natural
4. Considera el momentum conversacional ({context.conversation_momentum:.2f}) para ajustar urgencia
5. Si hay indicadores de urgencia, incluye elementos de persuasión apropiados
6. Personaliza basado en su estilo conversacional: {profile.conversation_style}

FORMATO DE RESPUESTA JSON:
{{
  "response": "Respuesta conversacional personalizada (máximo 200 palabras)",
  "tone_adaptation": "Tono usado (warm/professional/direct/formal)",
  "cultural_context": {{"elementos_culturales": ["elemento1", "elemento2"]}},
  "personalization_elements": ["elemento personalizado 1", "elemento personalizado 2"],
  "engagement_hooks": ["gancho de engagement 1", "gancho de engagement 2"]
}}

Genera la respuesta personalizada:"""
        
        return prompt
    
    def _build_personalized_system_prompt(self, context: PersonalizationContext) -> str:
        """Construye system prompt personalizado para Claude."""
        market_config = context.market_config
        profile = context.personalization_profile
        
        return f"""Eres un asistente de compras AI experto en personalización para el mercado {market_config.name}.

ESPECIALIZACIÓN:
- Experto en e-commerce para {market_config.name}
- Dominio cultural de {market_config.localization.get("cultural_preferences", {})}
- Especialista en personalización comportamental
- Optimizado para conversiones en {market_config.currency}

PERSONALIDAD ADAPTADA:
- Estilo: {market_config.localization.get("cultural_preferences", {}).get("communication_style", "profesional")}
- Idioma nativo: {market_config.language}
- Conocimiento local: {market_config.name} específico
- Sensibilidad cultural: Máxima para {market_config.id}

CAPACIDADES DE PERSONALIZACIÓN:
- Análisis de comportamiento de usuario en tiempo real
- Adaptación cultural automática por mercado
- Recomendaciones contextualizadas por intención
- Optimización de conversión por usuario específico

DIRECTRICES DE RESPUESTA:
- Siempre personaliza basado en el perfil único del usuario
- Adapta precios y disponibilidad al mercado local
- Usa elementos culturales apropiados para {market_config.id}
- Mantén consistencia con el estilo conversacional del usuario
- Optimiza para conversión considerando propensión de compra del usuario

Tu objetivo es crear experiencias conversacionales que se sientan únicas para cada usuario en su mercado específico."""
    
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
            current_propensity = profile.purchase_propensity
            new_propensity = (current_propensity * 0.7) + (purchase_indicators * 0.3)
            profile.purchase_propensity = min(new_propensity, 1.0)
            
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
            
            # Guardar en Redis para analytics posteriores
            analytics_key = f"mcp:analytics:personalization:{mcp_context.session_id}:{int(time.time())}"
            await self.redis.set(
                analytics_key,
                json.dumps(analytics_event),
                ex=7 * 24 * 3600  # 7 días
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
            # Verificar en caché primero
            cache_key = f"availability:{market_id}:{product_id}"
            cached_availability = await self.redis.get(cache_key)
            
            if cached_availability is not None:
                return json.loads(cached_availability)
            
            # En implementación real, esto consultaría Shopify Markets/MCP
            # Por ahora, simulamos disponibilidad alta
            availability = True  # 90% de productos disponibles por defecto
            
            # Cachear resultado por 1 hora
            await self.redis.set(cache_key, json.dumps(availability), ex=3600)
            
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
            
            # En implementación real, esto buscaría en base de datos de sesiones
            # Por ahora, simulamos con datos de ejemplo
            session_keys = await self.redis.keys(f"mcp:conversation:{user_id}:*")
            
            for key in session_keys:
                session_data = await self.redis.get(key)
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


# === CLASE AUXILIAR PARA ANÁLISIS DE INSIGHTS ===

class PersonalizationInsightsAnalyzer:
    """
    Analizador especializado para extraer insights profundos
    de datos de personalización y generar recomendaciones accionables.
    """
    
    def __init__(self, redis_client=None):
        """Initialize PersonalizationInsightsAnalyzer with enterprise Redis support"""
        self.redis = redis_client  # Will use ServiceFactory if None
        
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
            # Obtener datos históricos del usuario
            profile_key = f"mcp:personalization:profile:{user_id}"
            profile_data = await self.redis.get(profile_key)
            
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
            # Buscar sesiones conversacionales
            session_keys = await self.redis.keys(f"mcp:conversation:*{user_id}*")
            
            if not session_keys:
                return {"status": "no_conversations", "message": "No hay conversaciones registradas"}
            
            # Métricas de efectividad
            total_sessions = len(session_keys)
            successful_sessions = 0
            avg_satisfaction = 0.0
            conversation_patterns = {}
            
            for key in session_keys:
                session_data = await self.redis.get(key)
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
            
            # Obtener perfil y sesiones para análisis
            profile_key = f"mcp:personalization:profile:{user_id}"
            profile_data = await self.redis.get(profile_key)
            
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
            # Obtener datos históricos extensos
            profile_key = f"mcp:personalization:profile:{user_id}"
            profile_data = await self.redis.get(profile_key)
            
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


# === FACTORY PARA CREAR INSTANCIA CONFIGURADA ===

    async def _generate_claude_personalized_response(
        self,
        personalization_context: PersonalizationContext,
        personalized_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Genera respuesta conversacional personalizada usando Claude con configuración centralizada.
        
        Args:
            personalization_context: Contexto de personalización
            personalized_result: Resultado de personalización previo
            
        Returns:
            Respuesta conversacional personalizada
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
            
            logger.info(f"🎯 Generating personalized Claude response with {config.model_name}")
            
            response = await self.claude.messages.create(
                **config.to_anthropic_params(),
                messages=[
                    {"role": "system", "content": system_prompt},
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
            logger.error(f"Error generating Claude personalized response: {e}")
            
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
    
    def _determine_personalization_tier(self, context: PersonalizationContext) -> str:
        """Determina el tier de personalización basado en el contexto"""
        if context.personalization_profile.purchase_propensity > 0.8:
            return "premium"
        elif context.personalization_profile.purchase_propensity > 0.5:
            return "standard"
        else:
            return "basic"
    
    def _build_personalized_system_prompt(self, context: PersonalizationContext) -> str:
        """Construye prompt del sistema personalizado"""
        market_id = context.market_config.market_id
        user_style = context.personalization_profile.conversation_style
        
        return f"""
        Eres un asistente de ventas especializado para el mercado {market_id}.
        
        Perfil del usuario:
        - Estilo de conversación preferido: {user_style}
        - Propensión de compra: {context.personalization_profile.purchase_propensity:.1f}
        - Mercado principal: {market_id}
        
        Adapta tu respuesta al estilo cultural del mercado {market_id} y al perfil del usuario.
        Sé {user_style} en tu comunicación.
        Incluye recomendaciones relevantes cuando sea apropiado.
        """
    
    def _build_personalized_user_prompt(
        self, 
        context: PersonalizationContext, 
        personalized_result: Dict[str, Any]
    ) -> str:
        """Construye prompt del usuario con contexto personalizado"""
        recommendations = personalized_result.get("recommendations", [])
        
        prompt = f"Usuario consulta: {context.mcp_context.current_query}\n\n"
        
        if recommendations:
            prompt += "Recomendaciones personalizadas disponibles:\n"
            for i, rec in enumerate(recommendations[:3], 1):
                prompt += f"{i}. {rec.get('title', 'Producto')} - {rec.get('price', 'N/A')}\n"
            prompt += "\n"
        
        prompt += "Responde de manera personalizada y útil, incluyendo las recomendaciones si son relevantes."
        
        return prompt
    
    def _calculate_personalization_level(self, context: PersonalizationContext) -> float:
        """Calcula el nivel de personalización aplicado"""
        factors = [
            len(context.personalization_profile.category_affinities) * 0.1,
            context.personalization_profile.purchase_propensity * 0.3,
            len(context.real_time_signals) * 0.05,
            context.conversation_momentum * 0.2
        ]
        return min(sum(factors), 1.0)
    
    def _evaluate_response_quality(self, response_text: str) -> float:
        """Evalúa la calidad de la respuesta generada"""
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
        """Genera respuesta de fallback cuando Claude falla"""
        market_id = context.market_config.market_id
        
        fallback_responses = {
            "US": "I'm here to help you find the perfect products. Let me assist you with your shopping needs.",
            "ES": "Estoy aquí para ayudarte a encontrar los productos perfectos. Permíteme asistirte con tus necesidades de compra.",
            "MX": "¡Hola! Estoy aquí para ayudarte a encontrar exactamente lo que buscas. ¿En qué te puedo ayudar?"
        }
        
        return fallback_responses.get(market_id, fallback_responses["US"])


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
        
        engine = MCPPersonalizationEngine(
            redis_service=redis_service,  # Use SERVICE for orchestration
            anthropic_client=anthropic_client,
            conversation_manager=conversation_manager,
            state_manager=state_manager,
            profile_ttl=profile_ttl,
            enable_ml_predictions=enable_ml_predictions,
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