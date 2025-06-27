# src/recommenders/mcp_aware_recommender.py
"""
MCPAwareRecommender - Recomendador que integra MCP para personalización en tiempo real

EVOLUCIÓN del HybridRecommender actual hacia MCP-awareness con:
- Personalización basada en intención conversacional
- Context-aware recommendations
- Market-specific adaptations  
- Fallback strategies robusto
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import random

from .hybrid import HybridRecommender
from ..api.mcp.client.mcp_client_enhanced import MCPClientEnhanced
from ..api.mcp.user_events.user_event_store import UserEventStore

logger = logging.getLogger(__name__)

class MCPAwareRecommender:
    """
    Recomendador que integra MCP para personalización en tiempo real
    EVOLUCIÓN del HybridRecommender actual hacia MCP-awareness
    """
    
    def __init__(
        self, 
        base_recommender: HybridRecommender, 
        mcp_client: Optional[MCPClientEnhanced] = None, 
        user_event_store: Optional[UserEventStore] = None
    ):
        """
        Inicializa el recomendador MCP-aware
        
        Args:
            base_recommender: Recomendador híbrido existente (reutilizar sistema actual)
            mcp_client: Cliente MCP para capacidades conversacionales
            user_event_store: Almacenamiento de eventos para personalización
        """
        self.base_recommender = base_recommender  # Reutilizar sistema actual ✅
        self.mcp_client = mcp_client  # Nueva capacidad MCP ✅
        self.user_event_store = user_event_store  # Nueva personalización ✅
        
        # Configuración de personalización
        self.personalization_config = {
            "intent_weight": 0.4,           # Peso de la intención conversacional
            "history_weight": 0.35,         # Peso del historial de usuario
            "seasonal_weight": 0.25,        # Peso del contexto temporal/estacional
            "min_confidence_threshold": 0.3, # Confianza mínima para usar intent
            "max_personalization_boost": 2.0 # Boost máximo por personalización
        }
        
        # Métricas de rendimiento
        self.metrics = {
            "total_requests": 0,
            "personalized_requests": 0,
            "mcp_successful": 0,
            "mcp_fallback": 0,
            "avg_personalization_score": 0.0,
            "cache_efficiency": 0.0
        }
        
        logger.info("MCPAwareRecommender inicializado")
        logger.info(f"Base recommender: {type(base_recommender).__name__}")
        logger.info(f"MCP client: {'Disponible' if mcp_client else 'No disponible'}")
        logger.info(f"Event store: {'Disponible' if user_event_store else 'No disponible'}")
    
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        conversation_context: Optional[dict] = None,
        n_recommendations: int = 5,
        market_id: Optional[str] = None,
        **kwargs
    ) -> List[Dict]:
        """
        Recomendaciones MCP-aware con personalización en tiempo real
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            conversation_context: Contexto conversacional MCP
            n_recommendations: Número de recomendaciones
            market_id: ID del mercado específico
            **kwargs: Argumentos adicionales
            
        Returns:
            Lista de recomendaciones personalizadas
        """
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        logger.info(f"MCPAware request: user={user_id}, product={product_id}, market={market_id}")
        
        try:
            # 1. Capturar contexto conversacional MCP
            intent = None
            if conversation_context and self.mcp_client:
                try:
                    intent = await self.mcp_client.extract_intent(conversation_context)
                    
                    # Registrar intención si tenemos event store
                    if self.user_event_store and intent:
                        await self.user_event_store.record_conversation_intent(user_id, intent)
                    
                    self.metrics["mcp_successful"] += 1
                    logger.debug(f"Intent extracted: {intent.get('type', 'unknown')} (confidence: {intent.get('confidence', 0)})")
                    
                except Exception as e:
                    logger.warning(f"Error extracting intent: {e}")
                    self.metrics["mcp_fallback"] += 1
                    intent = self._create_fallback_intent(conversation_context)
            
            # 2. Obtener perfil de usuario en tiempo real
            user_profile = None
            if self.user_event_store:
                try:
                    user_profile = await self.user_event_store.get_user_profile(user_id)
                    logger.debug(f"User profile loaded: {user_profile.get('total_events', 0)} events")
                except Exception as e:
                    logger.warning(f"Error loading user profile: {e}")
                    user_profile = self._create_fallback_profile(user_id)
            
            # 3. Usar base_recommender para obtener candidatos
            base_recs = await self.base_recommender.get_recommendations(
                user_id=user_id, 
                product_id=product_id, 
                n_recommendations=n_recommendations,
                **kwargs
            )
            
            logger.info(f"Base recommender returned {len(base_recs)} recommendations")
            
            # 4. Aplicar personalización MCP-aware
            personalized_recs = await self._apply_mcp_personalization(
                base_recs, 
                user_profile, 
                intent,
                market_id,
                conversation_context
            )
            
            # 5. Registrar métricas
            processing_time = (time.time() - start_time) * 1000
            personalization_applied = bool(intent or user_profile)
            
            if personalization_applied:
                self.metrics["personalized_requests"] += 1
            
            # 6. Enriquecer con metadata MCP
            enriched_recs = self._enrich_with_mcp_metadata(
                personalized_recs,
                intent,
                user_profile,
                processing_time,
                market_id
            )
            
            logger.info(f"MCP recommendations completed: {len(enriched_recs)} items in {processing_time:.1f}ms")
            
            return enriched_recs
            
        except Exception as e:
            logger.error(f"Error in MCP-aware recommendations: {e}")
            # Fallback al sistema base en caso de error
            return await self.base_recommender.get_recommendations(
                user_id=user_id,
                product_id=product_id,
                n_recommendations=n_recommendations,
                **kwargs
            )
    
    async def _apply_mcp_personalization(
        self,
        base_recs: List[Dict],
        user_profile: Optional[Dict],
        intent: Optional[Dict],
        market_id: Optional[str] = None,
        conversation_context: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Algoritmo específico de personalización MCP-aware
        
        Combina:
        - Intent conversacional (40% peso)
        - Historial de comportamiento (35% peso)
        - Contexto temporal/estacional (25% peso)
        """
        if not base_recs:
            return base_recs
        
        logger.debug("Applying MCP personalization...")
        
        # Extraer pesos de configuración
        intent_weight = self.personalization_config["intent_weight"]
        history_weight = self.personalization_config["history_weight"]
        seasonal_weight = self.personalization_config["seasonal_weight"]
        
        # Calcular boost factors
        intent_boost = self._calculate_intent_boost(intent)
        user_preferences = self._extract_user_preferences(user_profile)
        seasonal_boost = self._calculate_seasonal_relevance(market_id)
        
        personalized_recs = []
        
        for rec in base_recs:
            # Score base del recomendador existente
            base_score = rec.get("final_score", rec.get("score", rec.get("similarity_score", 0.5)))
            
            # 1. Boost por intent conversacional (40%)
            intent_score = self._calculate_intent_score(rec, intent, intent_boost)
            
            # 2. Boost por historial de usuario (35%)
            history_score = self._calculate_history_score(rec, user_preferences)
            
            # 3. Contexto temporal/estacional (25%)
            seasonal_score = self._calculate_seasonal_score(rec, seasonal_boost)
            
            # Combinar scores con ponderación
            personalized_score = (
                base_score * 0.3 +  # Score base reducido para dar espacio a personalización
                intent_score * intent_weight +
                history_score * history_weight +
                seasonal_score * seasonal_weight
            )
            
            # Aplicar boost máximo
            max_boost = self.personalization_config["max_personalization_boost"]
            final_score = min(personalized_score, base_score * max_boost)
            
            # Crear recomendación personalizada
            personalized_rec = rec.copy()
            personalized_rec.update({
                "personalized_score": final_score,
                "base_score": base_score,
                "personalization_factors": {
                    "intent_boost": intent_score,
                    "history_boost": history_score,
                    "seasonal_boost": seasonal_score,
                    "total_boost": final_score / base_score if base_score > 0 else 1.0
                },
                "personalization_applied": True
            })
            
            personalized_recs.append(personalized_rec)
        
        # Ordenar por score personalizado
        personalized_recs.sort(key=lambda x: x["personalized_score"], reverse=True)
        
        # Actualizar métrica de personalización promedio
        if personalized_recs:
            avg_boost = sum(r["personalization_factors"]["total_boost"] for r in personalized_recs) / len(personalized_recs)
            self.metrics["avg_personalization_score"] = (
                self.metrics["avg_personalization_score"] * 0.8 + avg_boost * 0.2
            )
        
        logger.debug(f"Personalization applied to {len(personalized_recs)} recommendations")
        return personalized_recs
    
    def _calculate_intent_boost(self, intent: Optional[Dict]) -> Dict[str, float]:
        """Calcula boost factors basado en intención conversacional"""
        if not intent:
            return {"multiplier": 1.0, "confidence": 0.0}
        
        intent_type = intent.get("type", "general")
        confidence = intent.get("confidence", 0.5)
        
        # Solo aplicar boost si confianza es suficiente
        if confidence < self.personalization_config["min_confidence_threshold"]:
            return {"multiplier": 1.0, "confidence": confidence}
        
        # Multiplicadores por tipo de intención
        intent_multipliers = {
            "high_purchase_intent": 1.8,
            "purchase_intent": 1.5,
            "comparison_shopping": 1.3,
            "search": 1.2,
            "recommendation": 1.4,
            "price_inquiry": 1.1,
            "browsing": 1.0,
            "general": 1.0
        }
        
        multiplier = intent_multipliers.get(intent_type, 1.0)
        
        # Ajustar por confianza
        adjusted_multiplier = 1.0 + (multiplier - 1.0) * confidence
        
        return {
            "multiplier": adjusted_multiplier,
            "confidence": confidence,
            "type": intent_type
        }
    
    def _extract_user_preferences(self, user_profile: Optional[Dict]) -> Dict[str, Any]:
        """Extrae preferencias del perfil de usuario"""
        if not user_profile:
            return {"category_affinity": {}, "search_patterns": [], "activity_level": "new"}
        
        return {
            "category_affinity": user_profile.get("category_affinity", {}),
            "search_patterns": user_profile.get("search_patterns", []),
            "activity_level": self._determine_activity_level(user_profile),
            "intent_patterns": user_profile.get("intent_history", [])
        }
    
    def _calculate_seasonal_relevance(self, market_id: Optional[str] = None) -> Dict[str, float]:
        """Calcula relevancia estacional/temporal"""
        current_month = datetime.now().month
        
        # Factores estacionales básicos
        seasonal_factors = {
            "summer_boost": 1.2 if current_month in [6, 7, 8] else 1.0,
            "winter_boost": 1.2 if current_month in [12, 1, 2] else 1.0,
            "holiday_boost": 1.3 if current_month in [11, 12] else 1.0,
            "spring_boost": 1.1 if current_month in [3, 4, 5] else 1.0
        }
        
        # Ajustes por mercado
        if market_id:
            if market_id in ["ES", "FR", "IT"]:  # Europa
                seasonal_factors["summer_boost"] *= 1.1
            elif market_id in ["AU", "NZ"]:  # Hemisferio sur
                # Invertir estaciones
                seasonal_factors["summer_boost"], seasonal_factors["winter_boost"] = \
                    seasonal_factors["winter_boost"], seasonal_factors["summer_boost"]
        
        return seasonal_factors
    
    def _calculate_intent_score(self, rec: Dict, intent: Optional[Dict], intent_boost: Dict) -> float:
        """Calcula score basado en intención"""
        if not intent or intent_boost["multiplier"] == 1.0:
            return 0.5  # Score neutro
        
        base_score = rec.get("final_score", rec.get("score", 0.5))
        
        # Boost adicional si la categoría del producto coincide con intención
        category = rec.get("category", "").lower()
        query = intent.get("query", "").lower()
        
        category_match = 1.0
        if category and query:
            # Coincidencia simple de palabras clave
            if any(word in query for word in category.split()):
                category_match = 1.2
        
        return base_score * intent_boost["multiplier"] * category_match
    
    def _calculate_history_score(self, rec: Dict, user_preferences: Dict) -> float:
        """Calcula score basado en historial de usuario"""
        category_affinity = user_preferences.get("category_affinity", {})
        activity_level = user_preferences.get("activity_level", "new")
        
        # Score base
        base_score = rec.get("final_score", rec.get("score", 0.5))
        
        # Boost por afinidad de categoría
        category = rec.get("category", "")
        category_boost = category_affinity.get(category, 0.5)
        
        # Boost por nivel de actividad
        activity_multipliers = {
            "high": 1.3,
            "medium": 1.1,
            "low": 1.0,
            "new": 0.9
        }
        
        activity_multiplier = activity_multipliers.get(activity_level, 1.0)
        
        return base_score * (1 + category_boost) * activity_multiplier
    
    def _calculate_seasonal_score(self, rec: Dict, seasonal_boost: Dict) -> float:
        """Calcula score basado en contexto estacional"""
        base_score = rec.get("final_score", rec.get("score", 0.5))
        category = rec.get("category", "").lower()
        
        # Aplicar boost estacional según categoría
        boost = 1.0
        
        if "swimwear" in category or "beach" in category:
            boost = seasonal_boost.get("summer_boost", 1.0)
        elif "coat" in category or "jacket" in category:
            boost = seasonal_boost.get("winter_boost", 1.0)
        elif "gift" in category or "decoration" in category:
            boost = seasonal_boost.get("holiday_boost", 1.0)
        
        return base_score * boost
    
    def _determine_activity_level(self, user_profile: Dict) -> str:
        """Determina nivel de actividad del usuario"""
        total_events = user_profile.get("total_events", 0)
        session_count = user_profile.get("session_count", 0)
        
        if total_events >= 50 and session_count >= 10:
            return "high"
        elif total_events >= 20 and session_count >= 5:
            return "medium"
        elif total_events >= 5:
            return "low"
        else:
            return "new"
    
    def _create_fallback_intent(self, conversation_context: Optional[Dict]) -> Dict:
        """Crea intención de fallback cuando MCP falla"""
        if not conversation_context:
            return {"type": "general", "confidence": 0.3, "source": "fallback"}
        
        query = conversation_context.get("query", "").lower()
        
        # Análisis básico de palabras clave
        if any(word in query for word in ["comprar", "buy", "purchase"]):
            return {"type": "purchase_intent", "confidence": 0.6, "source": "fallback"}
        elif any(word in query for word in ["buscar", "search", "find"]):
            return {"type": "search", "confidence": 0.7, "source": "fallback"}
        elif any(word in query for word in ["recomendar", "recommend", "suggest"]):
            return {"type": "recommendation", "confidence": 0.8, "source": "fallback"}
        else:
            return {"type": "general", "confidence": 0.4, "source": "fallback"}
    
    def _create_fallback_profile(self, user_id: str) -> Dict:
        """Crea perfil de fallback cuando event store falla"""
        return {
            "user_id": user_id,
            "total_events": 0,
            "last_activity": datetime.utcnow().isoformat(),
            "intent_history": [],
            "category_affinity": {},
            "search_patterns": [],
            "session_count": 0,
            "market_preferences": {},
            "source": "fallback"
        }
    
    def _enrich_with_mcp_metadata(
        self,
        recommendations: List[Dict],
        intent: Optional[Dict],
        user_profile: Optional[Dict],
        processing_time: float,
        market_id: Optional[str]
    ) -> List[Dict]:
        """Enriquece recomendaciones con metadata MCP"""
        
        for rec in recommendations:
            rec["mcp_metadata"] = {
                "intent_detected": intent.get("type") if intent else None,
                "intent_confidence": intent.get("confidence") if intent else None,
                "user_activity_level": user_profile.get("total_events", 0) if user_profile else 0,
                "personalization_applied": rec.get("personalization_applied", False),
                "market_id": market_id,
                "processing_time_ms": processing_time,
                "recommendation_source": "mcp_aware_hybrid"
            }
            
            # Añadir explicación de la recomendación
            rec["explanation"] = self._generate_recommendation_explanation(rec, intent, user_profile)
        
        return recommendations
    
    def _generate_recommendation_explanation(
        self,
        rec: Dict,
        intent: Optional[Dict],
        user_profile: Optional[Dict]
    ) -> str:
        """Genera explicación de por qué se recomendó este producto"""
        reasons = []
        
        # Razón por intención
        if intent and intent.get("confidence", 0) > 0.5:
            intent_type = intent.get("type", "general")
            if intent_type == "search":
                reasons.append("matches your search query")
            elif intent_type == "purchase_intent":
                reasons.append("high purchase likelihood")
            elif intent_type == "recommendation":
                reasons.append("recommended based on your request")
        
        # Razón por historial
        if user_profile and user_profile.get("category_affinity"):
            category = rec.get("category", "")
            if category in user_profile["category_affinity"]:
                reasons.append(f"you've shown interest in {category}")
        
        # Razón por personalización
        if rec.get("personalization_applied"):
            boost = rec.get("personalization_factors", {}).get("total_boost", 1.0)
            if boost > 1.2:
                reasons.append("highly personalized for you")
        
        # Razón por score alto
        score = rec.get("personalized_score", rec.get("final_score", 0))
        if score > 0.8:
            reasons.append("high relevance score")
        
        if not reasons:
            return "recommended based on product similarity"
        
        return "Recommended because " + " and ".join(reasons[:2])
    
    async def record_user_event(
        self,
        user_id: str,
        event_type: str,
        product_id: Optional[str] = None,
        purchase_amount: Optional[float] = None,
        session_id: Optional[str] = None,
        market_id: Optional[str] = None
    ) -> Dict:
        """
        Registra eventos de usuario para mejorar recomendaciones futuras
        Compatibilidad con base_recommender + funcionalidad MCP
        """
        try:
            # 1. Registrar en el sistema base (Google Retail API)
            base_result = await self.base_recommender.record_user_event(
                user_id=user_id,
                event_type=event_type,
                product_id=product_id,
                purchase_amount=purchase_amount
            )
            
            # 2. Registrar en el event store MCP si está disponible
            if self.user_event_store:
                event_data = {
                    "event_type": event_type,
                    "product_id": product_id,
                    "purchase_amount": purchase_amount,
                    "session_id": session_id,
                    "market_id": market_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                mcp_result = await self.user_event_store.record_mcp_event(user_id, event_data)
                
                if mcp_result:
                    base_result["mcp_recorded"] = True
                    base_result["event_store"] = "success"
                else:
                    base_result["mcp_recorded"] = False
                    base_result["event_store"] = "failed"
            
            return base_result
            
        except Exception as e:
            logger.error(f"Error recording user event in MCP-aware recommender: {e}")
            return {
                "status": "error",
                "error": str(e),
                "user_id": user_id,
                "event_type": event_type
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas del recomendador MCP-aware"""
        base_metrics = {}
        if hasattr(self.base_recommender, 'get_metrics'):
            base_metrics = self.base_recommender.get_metrics()
        
        mcp_client_metrics = {}
        if self.mcp_client:
            mcp_client_metrics = self.mcp_client.get_metrics()
        
        event_store_stats = {}
        if self.user_event_store:
            # Esta llamada es async, pero para métricas sync podemos usar el último conocido
            event_store_stats = {"status": "available"}
        
        personalization_rate = 0.0
        if self.metrics["total_requests"] > 0:
            personalization_rate = self.metrics["personalized_requests"] / self.metrics["total_requests"]
        
        mcp_success_rate = 0.0
        mcp_total = self.metrics["mcp_successful"] + self.metrics["mcp_fallback"]
        if mcp_total > 0:
            mcp_success_rate = self.metrics["mcp_successful"] / mcp_total
        
        return {
            "mcp_aware_metrics": {
                **self.metrics,
                "personalization_rate": personalization_rate,
                "mcp_success_rate": mcp_success_rate
            },
            "base_recommender": base_metrics,
            "mcp_client": mcp_client_metrics,
            "event_store": event_store_stats,
            "configuration": self.personalization_config
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check del recomendador MCP-aware"""
        health_status = {
            "status": "healthy",
            "components": {}
        }
        
        # Check base recommender
        try:
            if hasattr(self.base_recommender, 'health_check'):
                base_health = await self.base_recommender.health_check()
                health_status["components"]["base_recommender"] = base_health
            else:
                health_status["components"]["base_recommender"] = {"status": "unknown"}
        except Exception as e:
            health_status["components"]["base_recommender"] = {"status": "error", "error": str(e)}
            health_status["status"] = "degraded"
        
        # Check MCP client
        if self.mcp_client:
            try:
                mcp_health = await self.mcp_client.health_check()
                health_status["components"]["mcp_client"] = mcp_health
            except Exception as e:
                health_status["components"]["mcp_client"] = {"status": "error", "error": str(e)}
                health_status["status"] = "degraded"
        else:
            health_status["components"]["mcp_client"] = {"status": "not_configured"}
        
        # Check event store
        if self.user_event_store:
            try:
                event_store_stats = await self.user_event_store.get_stats()
                health_status["components"]["event_store"] = {
                    "status": "healthy",
                    "stats": event_store_stats
                }
            except Exception as e:
                health_status["components"]["event_store"] = {"status": "error", "error": str(e)}
                health_status["status"] = "degraded"
        else:
            health_status["components"]["event_store"] = {"status": "not_configured"}
        
        return health_status