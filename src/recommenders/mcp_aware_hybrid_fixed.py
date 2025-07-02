# src/recommenders/mcp_aware_hybrid_fixed.py
"""
CORRECCIÓN CRÍTICA: MCPAwareHybridRecommender con interfaz compatible.

Esta corrección resuelve el error de incompatibilidad de interfaz entre
el sistema MCP y el recomendador híbrido base.
"""

import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class MCPAwareHybridRecommenderFixed:
    """
    🔧 VERSIÓN CORREGIDA: Recomendador híbrido con capacidades MCP.
    
    CORRECCIONES APLICADAS:
    1. Interfaz compatible con HybridRecommenderWithExclusion
    2. Manejo robusto de parámetros MCP opcionales
    3. Fallbacks garantizados para todos los escenarios
    4. Validación de datos mejorada
    """
    
    def __init__(
        self,
        base_recommender,
        mcp_client=None,
        market_manager=None,
        market_cache=None
    ):
        """
        Inicializar recomendador MCP-aware corregido.
        
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
            "cache_hits": 0,
            "interface_corrections": 0  # Nueva métrica
        }
        
        # Verificar disponibilidad de componentes
        self.mcp_available = mcp_client is not None
        self.market_aware = market_manager is not None and market_cache is not None
        
        logger.info(f"MCPAwareHybridRecommenderFixed inicializado:")
        logger.info(f"  - MCP disponible: {self.mcp_available}")
        logger.info(f"  - Market-aware: {self.market_aware}")
        logger.info(f"  - Base recommender: {type(base_recommender).__name__}")
    
    async def get_recommendations(
        self, 
        user_id: str = "anonymous",
        product_id: Optional[str] = None,
        n_recommendations: int = 5,
        **kwargs  # 🔧 CORRECCIÓN CRÍTICA: Usar **kwargs para capturar parámetros adicionales
    ) -> Dict[str, Any]:
        """
        🔧 CORRECCIÓN CRÍTICA: Obtener recomendaciones con interfaz compatible.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto base (opcional)
            n_recommendations: Número de recomendaciones
            **kwargs: Parámetros adicionales MCP (opcionales)
            
        Returns:
            Dict con recomendaciones y metadata MCP
        """
        self.metrics["total_requests"] += 1
        start_time = time.time()
        
        # 🔧 CORRECCIÓN: Extraer parámetros MCP de kwargs de forma segura
        market_id = kwargs.get('market_id', 'default')
        conversation_context = kwargs.get('conversation_context', {})
        include_conversation_response = kwargs.get('include_conversation_response', False)
        
        # Incrementar métrica de corrección de interfaz
        if kwargs:
            self.metrics["interface_corrections"] += 1
            logger.info(f"Corrigiendo interfaz MCP: {len(kwargs)} parámetros adicionales manejados")
        
        # Extraer query del contexto de conversación si está disponible
        query_text = None
        if isinstance(conversation_context, dict):
            query_text = conversation_context.get('query', None)
        
        # Asegurar que query_text es string o None
        if query_text and not isinstance(query_text, str):
            query_text = str(query_text)
        
        try:
            logger.info(f"Procesando request MCP corregido: user={user_id}, market={market_id}, product={product_id}, query={query_text}")
            
            # 🔧 CORRECCIÓN CRÍTICA: Llamar al base_recommender SOLO con parámetros compatibles
            logger.info("Llamando base_recommender con interfaz compatible...")
            base_recommendations = await self.base_recommender.get_recommendations(
                user_id=user_id,
                product_id=product_id,
                n_recommendations=n_recommendations
                # ❌ NO pasar: include_conversation_response, conversation_context, market_id
            )
            
            logger.info(f"Base recommender respondió con {len(base_recommendations)} recomendaciones")
            
            # Si no hay recomendaciones y tenemos query, intentar búsqueda por texto
            if not base_recommendations and query_text and hasattr(self.base_recommender, 'content_recommender'):
                logger.info(f"Intentando búsqueda por texto para: {query_text}")
                try:
                    if hasattr(self.base_recommender.content_recommender, 'search_products'):
                        search_results = await self.base_recommender.content_recommender.search_products(
                            query_text, n_recommendations
                        )
                        if search_results:
                            logger.info(f"Búsqueda por texto exitosa: {len(search_results)} resultados")
                            for result in search_results:
                                result["source"] = "text_search_corrected"
                            base_recommendations = search_results
                except Exception as search_e:
                    logger.error(f"Error en búsqueda por texto: {search_e}")
            
            # Fallback garantizado si no hay recomendaciones
            if not base_recommendations:
                base_recommendations = await self._guaranteed_fallback(
                    user_id, n_recommendations, "no_base_recommendations"
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
            
            if include_conversation_response and self.mcp_available and self.mcp_client:
                try:
                    self.metrics["mcp_requests"] += 1
                    ai_response = self._generate_corrected_ai_response(
                        adapted_recommendations, market_id, user_id, query_text
                    )
                    conversation_session = f"mcp_session_corrected_{user_id}_{int(time.time())}"
                    logger.info(f"Respuesta conversacional generada (corregida) para usuario {user_id}")
                except Exception as e:
                    logger.warning(f"Error procesando conversación MCP: {e}")
            
            # 4. Formatear respuesta MCP
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Validar y normalizar recomendaciones
            validated_recommendations = self._validate_recommendations(adapted_recommendations)
            
            # Convertir a formato MCP
            mcp_recommendations = self._convert_to_mcp_format(
                validated_recommendations, market_context
            )
            
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
                    "source": "mcp_aware_hybrid_corrected",
                    "interface_corrections_applied": self.metrics["interface_corrections"]
                }
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error en MCPAwareHybridRecommenderFixed: {e}")
            # Fallback completamente robusto
            return await self._complete_error_fallback(user_id, n_recommendations, str(e))
    
    def _generate_corrected_ai_response(
        self, 
        recommendations: List[Dict], 
        market_id: str, 
        user_id: str, 
        query_text: Optional[str] = None
    ) -> str:
        """
        Generar respuesta conversacional corregida y contextual.
        """
        if not recommendations:
            if query_text:
                return f"I apologize, but I couldn't find any products matching your search for '{query_text}'. Could you try a different search term or browse our categories?"
            else:
                return "I'm sorry, but I couldn't find any recommendations for you at the moment. Please try again or contact support if this issue persists."
        
        total = len(recommendations)
        
        # Personalizar por cantidad de resultados
        if total == 1:
            top_product = recommendations[0].get("title", "product")
            if query_text:
                return f"I found one great match for '{query_text}': {top_product}. This product seems perfect for what you're looking for!"
            else:
                return f"I have a perfect recommendation for you: {top_product}. Based on your preferences, this should be exactly what you need."
        
        elif total <= 3:
            top_product = recommendations[0].get("title", "product")
            if query_text:
                return f"I found {total} excellent options for '{query_text}'. The top choice is '{top_product}', which I think you'll love. Would you like to see more details about any of these?"
            else:
                return f"I've selected {total} personalized recommendations for you. '{top_product}' stands out as my top choice. Each of these has been carefully selected based on your preferences."
        
        else:
            top_product = recommendations[0].get("title", "product")
            if query_text:
                return f"Great news! I found {total} products matching '{query_text}'. My top recommendation is '{top_product}'. I've arranged these by relevance to help you find exactly what you need."
            else:
                return f"I've curated {total} personalized recommendations for you. Leading the list is '{top_product}', which I believe perfectly matches your style and preferences. Take a look and see what catches your eye!"
    
    def _validate_recommendations(self, recommendations: List[Dict]) -> List[Dict]:
        """
        Validar y normalizar recomendaciones de forma robusta.
        """
        validated = []
        for i, rec in enumerate(recommendations):
            try:
                validated_rec = {
                    "id": str(rec.get("id", f"unknown_{i}") or f"unknown_{i}"),
                    "title": str(rec.get("title", "Producto") or "Producto"),
                    "description": str(rec.get("description", "") or ""),
                    "price": float(rec.get("price", 0.0) or 0.0),
                    "score": float(rec.get("score", 0.5) or 0.5),
                    "source": str(rec.get("source", "validated") or "validated"),
                    "category": str(rec.get("category", "") or ""),
                    "images": list(rec.get("images", []) or [])
                }
                validated.append(validated_rec)
            except Exception as e:
                logger.warning(f"Error validando recomendación {i}: {e}")
                # Crear recomendación de emergencia
                validated.append({
                    "id": f"emergency_{i}",
                    "title": "Producto No Disponible",
                    "description": "Error al procesar información del producto",
                    "price": 0.0,
                    "score": 0.1,
                    "source": "validation_error",
                    "category": "Error",
                    "images": []
                })
        
        return validated
    
    def _convert_to_mcp_format(
        self, 
        recommendations: List[Dict], 
        market_context: Dict
    ) -> List[Dict]:
        """
        Convertir recomendaciones a formato MCP de forma robusta.
        """
        mcp_recommendations = []
        
        for rec in recommendations:
            try:
                mcp_rec = {
                    "product": {
                        "id": rec["id"],
                        "title": rec["title"],
                        "description": rec["description"],
                        "localized_title": rec["title"],  # Por ahora igual
                        "localized_description": rec["description"],  # Por ahora igual
                        "market_price": rec["price"],
                        "currency": market_context.get("currency", "USD"),
                        "images": rec["images"]
                    },
                    "market_score": rec["score"],
                    "viability_score": 0.8,  # Por defecto
                    "reason": "Based on your preferences and market analysis",
                    "metadata": {
                        "market_adapted": bool(self.market_aware),
                        "mcp_processed": bool(self.mcp_available),
                        "source": rec["source"],
                        "validation_passed": True
                    }
                }
                mcp_recommendations.append(mcp_rec)
                
            except Exception as e:
                logger.error(f"Error convirtiendo a formato MCP: {e}")
                # Crear producto MCP de emergencia
                mcp_recommendations.append({
                    "product": {
                        "id": "error_product",
                        "title": "Producto No Disponible",
                        "description": "Error al procesar",
                        "localized_title": "Producto No Disponible",
                        "localized_description": "Error al procesar",
                        "market_price": 0.0,
                        "currency": "USD",
                        "images": []
                    },
                    "market_score": 0.1,
                    "viability_score": 0.1,
                    "reason": "Error en procesamiento",
                    "metadata": {
                        "market_adapted": False,
                        "mcp_processed": False,
                        "source": "conversion_error",
                        "validation_passed": False
                    }
                })
        
        return mcp_recommendations
    
    async def _guaranteed_fallback(
        self, 
        user_id: str, 
        n_recommendations: int, 
        reason: str
    ) -> List[Dict]:
        """
        Fallback garantizado que siempre devuelve productos.
        """
        logger.info(f"Aplicando fallback garantizado para {user_id} - razón: {reason}")
        
        try:
            # Intentar obtener productos del catálogo local
            if (hasattr(self.base_recommender, 'content_recommender') and 
                hasattr(self.base_recommender.content_recommender, 'product_data') and
                self.base_recommender.content_recommender.product_data):
                
                import random
                all_products = self.base_recommender.content_recommender.product_data
                num_sample = min(n_recommendations, len(all_products))
                random_products = random.sample(all_products, num_sample)
                
                fallback_recs = []
                for product in random_products:
                    fallback_recs.append({
                        "id": str(product.get('id', '')),
                        "title": product.get('title', 'Producto'),
                        "description": product.get('body_html', ''),
                        "price": 0.0,
                        "score": 0.5,
                        "source": f"guaranteed_fallback_{reason}"
                    })
                
                logger.info(f"Fallback garantizado: {len(fallback_recs)} productos del catálogo")
                return fallback_recs
        
        except Exception as e:
            logger.error(f"Error en fallback del catálogo: {e}")
        
        # Fallback de emergencia - productos estáticos
        emergency_products = [
            {
                "id": "emergency1",
                "title": "Camisa Azul Clásica",
                "description": "Camisa azul de alta calidad con corte clásico.",
                "price": 29.99,
                "score": 0.5,
                "source": f"emergency_fallback_{reason}"
            },
            {
                "id": "emergency2", 
                "title": "Pantalones Negros Slim Fit",
                "description": "Pantalones negros de corte slim fit para ocasiones formales.",
                "price": 39.99,
                "score": 0.5,
                "source": f"emergency_fallback_{reason}"
            },
            {
                "id": "emergency3",
                "title": "Zapatos de Cuero Marrón",
                "description": "Zapatos clásicos de cuero en color marrón.",
                "price": 59.99,
                "score": 0.5,
                "source": f"emergency_fallback_{reason}"
            }
        ]
        
        selected = emergency_products[:n_recommendations]
        logger.info(f"Fallback de emergencia: {len(selected)} productos estáticos")
        return selected
    
    async def _complete_error_fallback(
        self, 
        user_id: str, 
        n_recommendations: int, 
        error_msg: str
    ) -> Dict[str, Any]:
        """
        Fallback completo cuando todo falla.
        """
        logger.error(f"Activando fallback completo para {user_id}: {error_msg}")
        
        # Obtener productos de emergencia
        emergency_recs = await self._guaranteed_fallback(user_id, n_recommendations, "complete_error")
        
        # Convertir a formato MCP mínimo
        mcp_recs = []
        for rec in emergency_recs:
            mcp_recs.append({
                "product": {
                    "id": rec["id"],
                    "title": rec["title"],
                    "description": rec["description"],
                    "localized_title": rec["title"],
                    "localized_description": rec["description"],
                    "market_price": rec["price"],
                    "currency": "USD",
                    "images": []
                },
                "market_score": rec["score"],
                "viability_score": 0.5,
                "reason": "Fallback recommendation due to system error",
                "metadata": {
                    "market_adapted": False,
                    "mcp_processed": False,
                    "source": "complete_error_fallback",
                    "error_recovery": True
                }
            })
        
        return {
            "recommendations": mcp_recs,
            "ai_response": "I apologize for the technical difficulty. Here are some products you might like.",
            "conversation_session": f"error_session_{int(time.time())}",
            "market_context": {},
            "metadata": {
                "error_fallback": True,
                "error": error_msg,
                "source": "complete_error_recovery",
                "total_recommendations": len(mcp_recs)
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        🔧 MÉTODO AÑADIDO: Verificar el estado del recomendador MCP-aware.
        
        Returns:
            Dict con información de estado completa
        """
        try:
            # Verificar estado del recomendador base
            base_status = {"status": "unknown", "components": {}}
            
            if self.base_recommender:
                try:
                    if hasattr(self.base_recommender, 'health_check'):
                        # Verificar si el health_check del base es async
                        import inspect
                        if inspect.iscoroutinefunction(self.base_recommender.health_check):
                            base_status = await self.base_recommender.health_check()
                        else:
                            base_status = self.base_recommender.health_check()
                    else:
                        # Crear health check básico para el base recommender
                        base_status = {
                            "status": "operational",
                            "type": type(self.base_recommender).__name__,
                            "message": "Base recommender available"
                        }
                except Exception as e:
                    base_status = {
                        "status": "error",
                        "error": str(e),
                        "type": type(self.base_recommender).__name__
                    }
            else:
                base_status = {
                    "status": "unavailable",
                    "message": "Base recommender not initialized"
                }
            
            # Verificar componentes MCP
            mcp_components = {}
            
            # Cliente MCP
            if self.mcp_client:
                try:
                    if hasattr(self.mcp_client, 'get_metrics'):
                        # get_metrics probablemente es síncrono
                        try:
                            client_metrics = self.mcp_client.get_metrics()
                            mcp_components["mcp_client"] = {
                                "status": "operational",
                                "type": type(self.mcp_client).__name__,
                                "metrics": client_metrics if isinstance(client_metrics, dict) else {}
                            }
                        except Exception as client_error:
                            mcp_components["mcp_client"] = {
                                "status": "error",
                                "error": str(client_error),
                                "type": type(self.mcp_client).__name__
                            }
                    else:
                        mcp_components["mcp_client"] = {
                            "status": "operational",
                            "type": type(self.mcp_client).__name__,
                            "message": "Client available but no metrics method"
                        }
                except Exception as e:
                    mcp_components["mcp_client"] = {
                        "status": "error",
                        "error": str(e)
                    }
            else:
                mcp_components["mcp_client"] = {
                    "status": "unavailable",
                    "message": "MCP client not initialized"
                }
            
            # Market Manager
            if self.market_manager:
                try:
                    mcp_components["market_manager"] = {
                        "status": "operational",
                        "type": type(self.market_manager).__name__,
                        "message": "Market manager available"
                    }
                except Exception as e:
                    mcp_components["market_manager"] = {
                        "status": "error",
                        "error": str(e)
                    }
            else:
                mcp_components["market_manager"] = {
                    "status": "unavailable",
                    "message": "Market manager not initialized"
                }
            
            # Market Cache
            if self.market_cache:
                try:
                    mcp_components["market_cache"] = {
                        "status": "operational",
                        "type": type(self.market_cache).__name__,
                        "message": "Market cache available"
                    }
                except Exception as e:
                    mcp_components["market_cache"] = {
                        "status": "error",
                        "error": str(e)
                    }
            else:
                mcp_components["market_cache"] = {
                    "status": "unavailable",
                    "message": "Market cache not initialized"
                }
            
            # Determinar estado general del MCP
            component_statuses = [comp.get("status") for comp in mcp_components.values()]
            base_recommender_status = base_status.get("status", "unknown")
            
            if base_recommender_status == "operational" and any(status == "operational" for status in component_statuses):
                overall_status = "operational"
            elif base_recommender_status == "operational":
                overall_status = "degraded"  # Base funciona pero componentes MCP no
            elif "error" in component_statuses or base_recommender_status == "error":
                overall_status = "error"
            else:
                overall_status = "unavailable"
            
            # Obtener métricas (síncrono)
            metrics = self.get_metrics()
            
            return {
                "status": overall_status,
                "components": {
                    "base_recommender": base_status,
                    "mcp_components": mcp_components
                },
                "metrics": metrics,
                "capabilities": {
                    "mcp_available": self.mcp_available,
                    "market_aware": self.market_aware,
                    "cache_available": self.market_cache is not None
                },
                "timestamp": datetime.utcnow().isoformat(),
                "version": "mcp_aware_hybrid_fixed"
            }
            
        except Exception as e:
            logger.error(f"Error en health_check de MCPAwareHybridRecommenderFixed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.utcnow().isoformat(),
                "version": "mcp_aware_hybrid_fixed"
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Obtener métricas del recomendador MCP corregido.
        """
        return {
            **self.metrics,
            "mcp_usage_ratio": self.metrics["mcp_requests"] / max(self.metrics["total_requests"], 1),
            "market_adaptation_ratio": self.metrics["market_adaptations"] / max(self.metrics["total_requests"], 1),
            "interface_correction_ratio": self.metrics["interface_corrections"] / max(self.metrics["total_requests"], 1),
            "capabilities": {
                "mcp_available": self.mcp_available,
                "market_aware": self.market_aware,
                "cache_available": self.market_cache is not None
            },
            "timestamp": datetime.utcnow().isoformat(),
            "status": "corrected_and_operational"
        }
    
    async def record_user_event(self, user_id: str, event_type: str, product_id: Optional[str] = None, **kwargs) -> Dict:
        """
        Registrar evento de usuario (delegado al recomendador base).
        """
        return await self.base_recommender.record_user_event(user_id, event_type, product_id, **kwargs)