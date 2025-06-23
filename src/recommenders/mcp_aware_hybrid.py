# src/recommenders/mcp_aware_hybrid.py
"""
MCP-Aware Hybrid Recommender - Implementación stub para Fase 2.
Esta implementación proporciona compatibilidad básica mientras se desarrolla la funcionalidad completa.
"""

import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class MCPAwareHybridRecommender:
    """
    Recomendador híbrido con capacidades MCP.
    Implementación stub para compatibilidad en Fase 2.
    """
    
    def __init__(
        self,
        base_recommender,
        mcp_client=None,
        market_manager=None,
        market_cache=None
    ):
        """
        Inicializar recomendador MCP-aware.
        
        Args:
            base_recommender: Recomendador híbrido base
            mcp_client: Cliente MCP (opcional)
            market_manager: Gestor de mercados (opcional)
            market_cache: Caché market-aware (opcional)
        """
        self.base_recommender = base_recommender
        self.mcp_client = mcp_client
        self.market_manager = market_manager
        self.market_cache = market_cache
        
        self.metrics = {
            "total_requests": 0,
            "mcp_requests": 0,
            "market_adaptations": 0,
            "cache_hits": 0
        }
        
        # Verificar disponibilidad de componentes
        self.mcp_available = mcp_client is not None
        self.market_aware = market_manager is not None and market_cache is not None
        
        logger.info(f"MCPAwareHybridRecommender inicializado:")
        logger.info(f"  - MCP disponible: {self.mcp_available}")
        logger.info(f"  - Market-aware: {self.market_aware}")
        logger.info(f"  - Base recommender: {type(base_recommender).__name__}")
    
    async def get_recommendations(self, request) -> Dict[str, Any]:
        """
        Obtener recomendaciones con capacidades MCP.
        
        Args:
            request: Objeto de request (puede ser dict o modelo Pydantic)
            
        Returns:
            Dict con recomendaciones y metadata MCP
        """
        self.metrics["total_requests"] += 1
        start_time = time.time()
        
        try:
            # Extraer parámetros del request (compatible con dict y objetos)
            user_id = getattr(request, 'user_id', request.get('user_id', 'anonymous'))
            product_id = getattr(request, 'product_id', request.get('product_id'))
            market_id = getattr(request, 'market_id', request.get('market_id', 'default'))
            n_recommendations = getattr(request, 'n_recommendations', request.get('n_recommendations', 5))
            include_conversation = getattr(request, 'include_conversation_response', request.get('include_conversation_response', False))
            
            logger.info(f"Procesando request MCP: user={user_id}, market={market_id}, product={product_id}")
            
            # 1. Obtener recomendaciones base
            base_recommendations = await self.base_recommender.get_recommendations(
                user_id=user_id,
                product_id=product_id,
                n_recommendations=n_recommendations
            )
            
            # 2. Aplicar adaptación de mercado si está disponible
            adapted_recommendations = base_recommendations
            market_context = {}
            
            if self.market_aware and self.market_manager:
                try:
                    self.metrics["market_adaptations"] += 1
                    adapted_recommendations = await self.market_manager.adapt_recommendations_for_market(
                        base_recommendations, market_id
                    )
                    market_context = await self.market_manager.get_market_config(market_id)
                    logger.info(f"Recomendaciones adaptadas para mercado {market_id}")
                except Exception as e:
                    logger.warning(f"Error adaptando para mercado {market_id}: {e}")
                    adapted_recommendations = base_recommendations
            
            # 3. Procesar conversación MCP si está disponible
            ai_response = None
            conversation_session = None
            
            if include_conversation and self.mcp_available and self.mcp_client:
                try:
                    self.metrics["mcp_requests"] += 1
                    
                    # En implementación completa, esto usaría el contexto real de conversación
                    # Por ahora, generamos una respuesta básica
                    ai_response = self._generate_basic_ai_response(
                        adapted_recommendations, market_id, user_id
                    )
                    conversation_session = f"mcp_session_{user_id}_{int(time.time())}"
                    
                    logger.info(f"Respuesta conversacional generada para usuario {user_id}")
                except Exception as e:
                    logger.warning(f"Error procesando conversación MCP: {e}")
            
            # 4. Formatear respuesta
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Convertir recomendaciones base a formato MCP
            mcp_recommendations = []
            for rec in adapted_recommendations:
                mcp_rec = {
                    "product": {
                        "id": rec.get("id"),
                        "title": rec.get("title"),
                        "description": rec.get("description", ""),
                        "localized_title": rec.get("localized_title", rec.get("title")),
                        "localized_description": rec.get("localized_description", rec.get("description", "")),
                        "market_price": rec.get("market_price", rec.get("price", 0.0)),
                        "currency": market_context.get("currency", "USD"),
                        "images": rec.get("images", [])
                    },
                    "market_score": rec.get("market_score", rec.get("score", 0.5)),
                    "viability_score": rec.get("viability_score", 0.8),
                    "reason": rec.get("reason", "Based on your preferences"),
                    "metadata": {
                        "market_adapted": self.market_aware,
                        "mcp_processed": self.mcp_available,
                        "source": "mcp_aware_hybrid"
                    }
                }
                mcp_recommendations.append(mcp_rec)
            
            response = {
                "recommendations": mcp_recommendations,
                "ai_response": ai_response,
                "conversation_session": conversation_session,
                "market_context": market_context,
                "metadata": {
                    "total_recommendations": len(mcp_recommendations),
                    "market_id": market_id,
                    "processing_time_ms": processing_time_ms,
                    "mcp_capabilities": {
                        "conversation": self.mcp_available,
                        "market_aware": self.market_aware,
                        "cache_enabled": self.market_cache is not None
                    },
                    "source": "mcp_aware_hybrid_stub"
                }
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error en MCPAwareHybridRecommender: {e}")
            # Fallback a recomendaciones base
            base_recommendations = await self.base_recommender.get_recommendations(
                user_id=user_id,
                product_id=product_id,
                n_recommendations=n_recommendations
            )
            
            return {
                "recommendations": [
                    {
                        "product": {
                            "id": rec.get("id"),
                            "title": rec.get("title"),
                            "description": rec.get("description", ""),
                            "market_price": rec.get("price", 0.0),
                            "currency": "USD"
                        },
                        "market_score": rec.get("score", 0.5),
                        "viability_score": 0.5,
                        "reason": "Fallback recommendation"
                    }
                    for rec in base_recommendations
                ],
                "ai_response": "I found some recommendations for you.",
                "conversation_session": None,
                "market_context": {},
                "metadata": {
                    "error_fallback": True,
                    "error": str(e),
                    "source": "fallback_hybrid"
                }
            }
    
    def _generate_basic_ai_response(self, recommendations: List[Dict], market_id: str, user_id: str) -> str:
        """
        Generar respuesta conversacional básica.
        En implementación completa, esto usaría Anthropic API.
        """
        if not recommendations:
            return "I couldn't find any recommendations that match your criteria at the moment."
        
        total = len(recommendations)
        top_product = recommendations[0].get("title", "product")
        
        market_names = {
            "US": "United States",
            "ES": "Spain", 
            "MX": "Mexico",
            "CL": "Chile",
            "default": "your region"
        }
        
        market_name = market_names.get(market_id, market_id)
        
        responses = [
            f"I found {total} great recommendations for you in {market_name}. The top pick is '{top_product}' which seems perfect for your needs.",
            f"Based on your preferences, I've selected {total} products available in {market_name}. '{top_product}' stands out as an excellent choice.",
            f"Here are {total} personalized recommendations for {market_name}. I especially recommend '{top_product}' - it's very popular in your area.",
        ]
        
        import random
        return random.choice(responses)
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Obtener métricas del recomendador MCP.
        
        Returns:
            Dict con métricas de uso
        """
        return {
            **self.metrics,
            "mcp_usage_ratio": self.metrics["mcp_requests"] / max(self.metrics["total_requests"], 1),
            "market_adaptation_ratio": self.metrics["market_adaptations"] / max(self.metrics["total_requests"], 1),
            "capabilities": {
                "mcp_available": self.mcp_available,
                "market_aware": self.market_aware,
                "cache_available": self.market_cache is not None
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def record_user_event(self, user_id: str, event_type: str, product_id: Optional[str] = None, **kwargs) -> Dict:
        """
        Registrar evento de usuario (delegado al recomendador base).
        """
        return await self.base_recommender.record_user_event(user_id, event_type, product_id, **kwargs)
