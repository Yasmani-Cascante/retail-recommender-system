# src/recommenders/mcp_aware_hybrid.py
import asyncio
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.api.mcp.client.mcp_client import ShopifyMCPClient
from src.api.mcp.adapters.market_manager import MarketContextManager  
from src.cache.market_aware.market_cache import MarketAwareProductCache
from src.api.mcp.models.mcp_models import (
    ConversationContext, ExtractedIntent, MarketAwareRecommendation, 
    MCPRecommendationRequest, MCPRecommendationResponse, MarketProduct,
    IntentType, MarketID
)

logger = logging.getLogger(__name__)

class MCPAwareHybridRecommender:
    """
    Recomendador híbrido con capacidades MCP que integra:
    - Sistema de recomendaciones existente
    - Capacidades conversacionales MCP
    - Adaptación por mercado
    - Cache market-aware
    """
    
    def __init__(self, base_recommender, mcp_client: ShopifyMCPClient, 
                 market_manager: MarketContextManager, 
                 market_cache: MarketAwareProductCache):
        self.base_recommender = base_recommender
        self.mcp_client = mcp_client
        self.market_manager = market_manager
        self.market_cache = market_cache
        
        # Performance tracking
        self.metrics = {
            "total_requests": 0,
            "conversation_driven": 0,
            "market_adaptations": 0,
            "cache_hits": 0,
            "average_response_time": 0.0
        }
        
        logger.info("MCPAwareHybridRecommender initialized successfully")
        
    async def get_recommendations(self, 
                                  request: MCPRecommendationRequest) -> MCPRecommendationResponse:
        """
        Punto de entrada principal para recomendaciones MCP-aware
        """
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        try:
            # 1. Detect and validate market context
            market_context = await self._prepare_market_context(request)
            
            # 2. Process conversation intent if provided
            intent_context = None
            ai_response = None
            
            if request.conversation_context:
                self.metrics["conversation_driven"] += 1
                intent_context, ai_response = await self._process_conversation_intent(
                    request.conversation_context, market_context
                )
            
            # 3. Generate cache key for this request
            cache_key = self._generate_cache_key(request, intent_context)
            
            # 4. Try to get cached recommendations
            cached_recs = await self.market_cache.get_market_recommendations(
                user_id=request.user_id,
                context_hash=cache_key,
                market_id=request.market_id
            )
            
            if cached_recs:
                self.metrics["cache_hits"] += 1
                logger.info(f"✅ Cache hit for user {request.user_id} in market {request.market_id}")
                
                response = MCPRecommendationResponse(
                    recommendations=[MarketAwareRecommendation(**rec) for rec in cached_recs],
                    ai_response=ai_response,
                    metadata={
                        "source": "cache",
                        "market_id": request.market_id,
                        "cache_hit": True
                    },
                    market_context=market_context,
                    took_ms=(time.time() - start_time) * 1000
                )
                
                return response
            
            # 5. Get base recommendations from existing system
            base_recs = await self._get_base_recommendations(request, intent_context)
            
            # 6. Adapt recommendations for market
            market_adapted_recs = await self._adapt_recommendations_for_market(
                base_recs, request.market_id, intent_context
            )
            
            # 7. Apply intent-based filtering and scoring
            if intent_context:
                market_adapted_recs = await self._apply_intent_filtering(
                    market_adapted_recs, intent_context
                )
            
            # 8. Final ranking and selection
            final_recs = market_adapted_recs[:request.n_recommendations]
            
            # 9. Enrich with MCP metadata
            enriched_recs = await self._enrich_with_mcp_metadata(
                final_recs, request, intent_context, market_context
            )
            
            # 10. Cache the results
            await self.market_cache.set_market_recommendations(
                user_id=request.user_id,
                context_hash=cache_key,
                market_id=request.market_id,
                recommendations=[rec.dict() for rec in enriched_recs]
            )
            
            # 11. Track metrics and build response
            processing_time = (time.time() - start_time) * 1000
            self._update_performance_metrics(processing_time)
            
            response = MCPRecommendationResponse(
                recommendations=enriched_recs,
                ai_response=ai_response,
                metadata={
                    "source": "computed",
                    "market_id": request.market_id,
                    "intent_driven": intent_context is not None,
                    "cache_hit": False,
                    "total_base_recommendations": len(base_recs),
                    "market_adaptations": self.metrics["market_adaptations"]
                },
                market_context=market_context,
                conversation_session=request.session_id,
                took_ms=processing_time
            )
            
            logger.info(f"✅ Generated {len(enriched_recs)} MCP recommendations for user {request.user_id}")
            return response
            
        except Exception as e:
            logger.error(f"❌ Error in MCP recommendations: {str(e)}")
            
            # Return fallback response
            return MCPRecommendationResponse(
                recommendations=[],
                ai_response="I apologize, but I'm having trouble generating recommendations right now. Please try again.",
                metadata={"error": str(e), "source": "error_fallback"},
                took_ms=(time.time() - start_time) * 1000
            )
    
    async def _prepare_market_context(self, request: MCPRecommendationRequest) -> Dict[str, Any]:
        """Preparar y validar contexto de mercado"""
        try:
            market_config = await self.market_manager.get_market_config(request.market_id)
            
            return {
                "market_id": request.market_id,
                "currency": market_config.get("currency", "USD"),
                "language": market_config.get("language", "en"),
                "timezone": market_config.get("timezone", "UTC"),
                "business_rules": market_config.get("business_rules", {}),
                "cultural_preferences": market_config.get("localization", {}).get("cultural_preferences", {}),
                "peak_hours": market_config.get("peak_hours", {})
            }
        except Exception as e:
            logger.error(f"Error preparing market context: {e}")
            return {"market_id": request.market_id, "currency": "USD", "language": "en"}
    
    async def _process_conversation_intent(self, conversation_context: ConversationContext, 
                                           market_context: Dict) -> tuple[ExtractedIntent, str]:
        """Procesar contexto conversacional y extraer intención"""
        try:
            # Extract intent using MCP client
            intent_data = await self.mcp_client.process_conversation_intent(
                conversation_context.query, market_context
            )
            
            # Create structured intent
            intent = ExtractedIntent(
                primary_intent=IntentType(intent_data.get("type", "general")),
                confidence=intent_data.get("confidence", 0.7),
                category=intent_data.get("category"),
                budget_range=intent_data.get("budget_range"),
                specific_requirements=intent_data.get("requirements", []),
                urgency=intent_data.get("urgency", "normal"),
                context_keywords=intent_data.get("keywords", [])
            )
            
            # Generate conversational AI response
            ai_response = await self._generate_ai_response(conversation_context, intent, market_context)
            
            return intent, ai_response
            
        except Exception as e:
            logger.error(f"Error processing conversation intent: {e}")
            
            # Fallback intent
            fallback_intent = ExtractedIntent(
                primary_intent=IntentType.GENERAL,
                confidence=0.5
            )
            fallback_response = "I understand you're looking for recommendations. Let me help you find something great!"
            
            return fallback_intent, fallback_response
    
    async def _get_base_recommendations(self, request: MCPRecommendationRequest, 
                                        intent_context: Optional[ExtractedIntent]) -> List[Dict]:
        """Obtener recomendaciones base del sistema existente"""
        try:
            # Use existing hybrid recommender with expanded results for filtering
            base_recs = await self.base_recommender.get_recommendations(
                user_id=request.user_id,
                product_id=request.product_id,
                n_recommendations=request.n_recommendations * 2  # Get more for filtering
            )
            
            logger.info(f"Retrieved {len(base_recs)} base recommendations")
            return base_recs
            
        except Exception as e:
            logger.error(f"Error getting base recommendations: {e}")
            return []
    
    async def _adapt_recommendations_for_market(self, recommendations: List[Dict], 
                                                market_id: str,
                                                intent_context: Optional[ExtractedIntent]) -> List[MarketAwareRecommendation]:
        """Adaptar recomendaciones para mercado específico"""
        try:
            self.metrics["market_adaptations"] += 1
            
            adapted_recs = await self.market_manager.adapt_recommendations_for_market(
                recommendations, market_id
            )
            
            # Convert to MarketAwareRecommendation objects
            market_aware_recs = []
            for rec in adapted_recs:
                try:
                    # Create MarketProduct
                    market_product = MarketProduct(
                        id=rec.get("id", ""),
                        title=rec.get("title", ""),
                        localized_title=rec.get("localized_title"),
                        description=rec.get("description", ""),
                        base_price=rec.get("price", 0.0),
                        market_price=rec.get("market_price", rec.get("price", 0.0)),
                        currency=rec.get("currency", "USD"),
                        availability=True,  # Assume available unless specified
                        category=rec.get("category", ""),
                        images=rec.get("images", [])
                    )
                    
                    # Create MarketAwareRecommendation
                    market_rec = MarketAwareRecommendation(
                        product=market_product,
                        score=rec.get("score", 0.5),
                        market_score=rec.get("market_score", rec.get("score", 0.5)),
                        reason=rec.get("reason", "Based on your preferences"),
                        market_factors=rec.get("market_factors", {}),
                        viability_score=rec.get("viability_score", 0.8)
                    )
                    
                    market_aware_recs.append(market_rec)
                    
                except Exception as item_error:
                    logger.error(f"Error converting recommendation item: {item_error}")
                    continue
            
            logger.info(f"Adapted {len(market_aware_recs)} recommendations for market {market_id}")
            return market_aware_recs
            
        except Exception as e:
            logger.error(f"Error adapting recommendations for market: {e}")
            return []
    
    async def _apply_intent_filtering(self, recommendations: List[MarketAwareRecommendation], 
                                      intent: ExtractedIntent) -> List[MarketAwareRecommendation]:
        """Aplicar filtrado basado en intención conversacional"""
        try:
            filtered_recs = recommendations.copy()
            
            # Apply intent-specific logic
            if intent.primary_intent == IntentType.BUDGET_SEARCH and intent.budget_range:
                max_budget = intent.budget_range.get("max", float('inf'))
                filtered_recs = [
                    rec for rec in filtered_recs 
                    if rec.product.market_price <= max_budget
                ]
            
            elif intent.primary_intent == IntentType.GIFT_SEARCH:
                # Boost highly rated and popular items for gifts
                for rec in filtered_recs:
                    if rec.product.rating and rec.product.rating > 4.5:
                        rec.market_score *= 1.2
                    if rec.product.review_count > 100:
                        rec.market_score *= 1.1
            
            elif intent.primary_intent == IntentType.COMPARE:
                # For comparison intent, prioritize products in same category
                if intent.category:
                    category_bonus = 0.15
                    for rec in filtered_recs:
                        if rec.product.category and intent.category.lower() in rec.product.category.lower():
                            rec.market_score += category_bonus
            
            # Apply specific requirements filtering
            if intent.specific_requirements:
                for requirement in intent.specific_requirements:
                    req_lower = requirement.lower()
                    for rec in filtered_recs:
                        # Boost if title or description contains requirement
                        if (req_lower in rec.product.title.lower() or 
                            req_lower in rec.product.description.lower()):
                            rec.market_score *= 1.1
            
            # Apply urgency scoring
            if intent.urgency == "immediate":
                for rec in filtered_recs:
                    if rec.product.shipping_days <= 2:
                        rec.market_score *= 1.3
            
            # Re-sort by adjusted market score
            filtered_recs.sort(key=lambda x: x.market_score, reverse=True)
            
            logger.info(f"Applied intent filtering: {intent.primary_intent}, {len(filtered_recs)} results")
            return filtered_recs
            
        except Exception as e:
            logger.error(f"Error applying intent filtering: {e}")
            return recommendations
    
    async def _enrich_with_mcp_metadata(self, recommendations: List[MarketAwareRecommendation],
                                        request: MCPRecommendationRequest,
                                        intent_context: Optional[ExtractedIntent],
                                        market_context: Dict) -> List[MarketAwareRecommendation]:
        """Enriquecer recomendaciones con metadata MCP"""
        try:
            for rec in recommendations:
                # Add MCP-specific metadata
                rec.market_factors.update({
                    "mcp_processed": True,
                    "market_id": request.market_id,
                    "conversation_driven": intent_context is not None,
                    "intent_type": intent_context.primary_intent if intent_context else None,
                    "intent_confidence": intent_context.confidence if intent_context else None,
                    "cultural_adaptation": market_context.get("cultural_preferences", {}),
                    "processing_timestamp": datetime.utcnow().isoformat()
                })
                
                # Add cultural adaptation info if available
                if market_context.get("cultural_preferences"):
                    rec.cultural_adaptation = {
                        "market_preferences": market_context["cultural_preferences"],
                        "localized": bool(rec.product.localized_title),
                        "currency_adapted": True
                    }
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error enriching with MCP metadata: {e}")
            return recommendations
    
    async def _generate_ai_response(self, conversation_context: ConversationContext,
                                    intent: ExtractedIntent, market_context: Dict) -> str:
        """Generar respuesta conversacional usando AI"""
        try:
            # Create market-aware prompt
            prompt = f"""
            Context: E-commerce recommendation assistant for {market_context['market_id']} market
            User Query: "{conversation_context.query}"
            Detected Intent: {intent.primary_intent} (confidence: {intent.confidence})
            Market: {market_context['market_id']} - Currency: {market_context['currency']}
            
            Generate a helpful, conversational response that:
            1. Acknowledges their request
            2. Explains what you'll help them find
            3. Is appropriate for {market_context['language']} speakers
            4. Matches the cultural context of {market_context['market_id']}
            
            Keep it friendly, concise (2-3 sentences), and set appropriate expectations.
            """
            
            # Use Anthropic to generate response
            response = await self.mcp_client.anthropic.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            
            # Fallback responses by intent
            fallback_responses = {
                IntentType.PRODUCT_SEARCH: "I'll help you find exactly what you're looking for!",
                IntentType.RECOMMENDATION: "Let me show you some great options based on your preferences.",
                IntentType.COMPARE: "I'll help you compare these options to find the best choice.",
                IntentType.BUDGET_SEARCH: "I'll find great options within your budget.",
                IntentType.GIFT_SEARCH: "Let me help you find the perfect gift!",
                "default": "I understand what you need. Let me find some great recommendations for you!"
            }
            
            intent_type = intent.primary_intent if intent else "default"
            return fallback_responses.get(intent_type, fallback_responses["default"])
    
    def _generate_cache_key(self, request: MCPRecommendationRequest, 
                            intent_context: Optional[ExtractedIntent]) -> str:
        """Generar clave de cache única para esta petición"""
        import hashlib
        import json
        
        cache_data = {
            "user_id": request.user_id,
            "product_id": request.product_id,
            "market_id": request.market_id,
            "n_recommendations": request.n_recommendations
        }
        
        if intent_context:
            cache_data.update({
                "intent": intent_context.primary_intent,
                "category": intent_context.category,
                "requirements": sorted(intent_context.specific_requirements) if intent_context.specific_requirements else []
            })
        
        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_string.encode()).hexdigest()[:16]
    
    def _update_performance_metrics(self, processing_time_ms: float):
        """Actualizar métricas de performance"""
        # Update average response time
        current_avg = self.metrics["average_response_time"]
        total_requests = self.metrics["total_requests"]
        
        self.metrics["average_response_time"] = (
            (current_avg * (total_requests - 1) + processing_time_ms) / total_requests
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtener métricas del recomendador MCP"""
        return {
            **self.metrics,
            "cache_hit_ratio": self.metrics["cache_hits"] / max(self.metrics["total_requests"], 1),
            "conversation_ratio": self.metrics["conversation_driven"] / max(self.metrics["total_requests"], 1)
        }