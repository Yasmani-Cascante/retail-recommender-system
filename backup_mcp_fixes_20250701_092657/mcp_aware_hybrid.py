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
    
    async def get_recommendations(
        self, 
        user_id: str = "anonymous",
        product_id: Optional[str] = None,
        n_recommendations: int = 5,
        market_id: str = "default",
        conversation_context: Optional[Dict] = None,
        include_conversation_response: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        🔧 CORRECCIÓN: Obtener recomendaciones con capacidades MCP usando parámetros keyword.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto base (opcional)
            n_recommendations: Número de recomendaciones
            market_id: ID del mercado
            conversation_context: Contexto conversacional (opcional)
            include_conversation_response: Incluir respuesta AI
            **kwargs: Parámetros adicionales
            
        Returns:
            Dict con recomendaciones y metadata MCP
        """
        self.metrics["total_requests"] += 1
        start_time = time.time()
        
        # 🔧 CORRECCIÓN: Usar parámetros directamente en lugar de extraer de request
        
        # Extraer query del contexto de conversación si está disponible
        query_text = None
        if conversation_context and isinstance(conversation_context, dict):
            query_text = conversation_context.get('query', None)
        
        # Asegurar que query_text es string o None
        if query_text and not isinstance(query_text, str):
            query_text = str(query_text)
        
        try:
            logger.info(f"Procesando request MCP: user={user_id}, market={market_id}, product={product_id}, query={query_text}")
            
            # 1. Obtener recomendaciones base
            base_recommendations = await self.base_recommender.get_recommendations(
                user_id=user_id,
                product_id=product_id,
                n_recommendations=n_recommendations
            )
            
            # Nuevo: Si no hay recomendaciones y tenemos query, intentar búsqueda por texto
            if not base_recommendations and query_text and hasattr(self.base_recommender, 'content_recommender'):
                logger.info(f"No se encontraron recomendaciones basadas en usuario/producto. Intentando búsqueda por texto: {query_text}")
                try:
                    # Asegurarnos de que el content_recommender esté cargado
                    if hasattr(self.base_recommender.content_recommender, 'loaded') and not self.base_recommender.content_recommender.loaded:
                        logger.warning("El content_recommender no está cargado. Intentando cargar modelo...")
                        await self.base_recommender.content_recommender.load()
                    
                    # Intentar búsqueda por texto
                    if hasattr(self.base_recommender.content_recommender, 'search_products'):
                        search_results = await self.base_recommender.content_recommender.search_products(
                            query_text, n_recommendations
                        )
                        if search_results:
                            logger.info(f"Búsqueda por texto exitosa: {len(search_results)} resultados")
                            # Marcar las recomendaciones como provenientes de búsqueda por texto
                            for result in search_results:
                                result["source"] = "text_search"
                            base_recommendations = search_results
                        else:
                            logger.warning(f"Búsqueda por texto sin resultados para: {query_text}")
                    else:
                        logger.warning("El content_recommender no tiene método search_products")
                except Exception as search_e:
                    logger.error(f"Error en búsqueda por texto: {search_e}")
            
            # Nuevo: Fallback garantizado - si todavía no hay recomendaciones, proporcionar productos aleatorios
            if not base_recommendations and hasattr(self.base_recommender, 'content_recommender'):
                import random
                logger.info("Aplicando fallback de productos aleatorios")
                
                # Verificar si tenemos product_data disponible
                if hasattr(self.base_recommender.content_recommender, 'product_data') and \
                   self.base_recommender.content_recommender.product_data:
                    # Obtener productos aleatorios del catálogo
                    all_products = self.base_recommender.content_recommender.product_data
                    if len(all_products) > 0:
                        num_sample = min(n_recommendations, len(all_products))
                        random_products = random.sample(all_products, num_sample)
                        
                        base_recommendations = []
                        for product in random_products:
                            base_recommendations.append({
                                "id": str(product.get('id', '')),
                                "title": product.get('title', 'Producto'),
                                "description": product.get('body_html', ''),
                                "price": 0.0,  # Se extraerá posteriormente de variantes
                                "score": 0.5,
                                "source": "catalog_random_fallback"  # Especificar que proviene de productos aleatorios del catálogo
                            })
                        
                        logger.info(f"Fallback aleatorio aplicó {len(base_recommendations)} productos")
                else:
                    # Fallback absoluto (productos de emergencia fijos) si no hay catálogo disponible
                    logger.warning("Catálogo no disponible, usando productos de emergencia")
                    emergency_products = [
                        {
                            "id": "emergency1",
                            "title": "Camisa Azul Clásica",
                            "description": "Camisa azul de alta calidad con corte clásico.",
                            "price": 29.99,
                            "score": 0.5,
                            "source": "static_emergency_products"  # Fuente específica para productos estáticos
                        },
                        {
                            "id": "emergency2",
                            "title": "Pantalones Negros Slim Fit",
                            "description": "Pantalones negros de corte slim fit para ocasiones formales.",
                            "price": 39.99,
                            "score": 0.5,
                            "source": "static_emergency_products"
                        },
                        {
                            "id": "emergency3",
                            "title": "Zapatos de Cuero Marrón",
                            "description": "Zapatos clásicos de cuero en color marrón.",
                            "price": 59.99,
                            "score": 0.5,
                            "source": "static_emergency_products"
                        }
                    ]
                    base_recommendations = emergency_products[:n_recommendations]
                    logger.info(f"Fallback de emergencia aplicó {len(base_recommendations)} productos estáticos")
            
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
            
            # 🔧 CORRECCIÓN: Validar y normalizar recomendaciones antes de formatear
            try:
                from src.api.core.product_data_validator import ProductDataValidator
                
                # Validar cada recomendación
                validated_recommendations = []
                for rec in adapted_recommendations:
                    try:
                        validated_rec = ProductDataValidator.validate_recommendation_data(rec)
                        validated_recommendations.append(validated_rec)
                    except Exception as val_error:
                        logger.warning(f"Error validando recomendación: {val_error}")
                        # Usar recomendación original si la validación falla
                        validated_recommendations.append(rec)
                
                adapted_recommendations = validated_recommendations
                logger.info(f"Validadas {len(adapted_recommendations)} recomendaciones")
                
            except Exception as import_error:
                logger.warning(f"ProductDataValidator no disponible: {import_error}")
            
            # Convertir recomendaciones base a formato MCP
            mcp_recommendations = []
            for rec in adapted_recommendations:
                # Obtener la fuente de la recomendación
                source = rec.get("source", "mcp_aware_hybrid")
                
                # 🔧 CORRECCIÓN: Conversion MCP robusta con manejo de None
                mcp_rec = {
                    "product": {
                        "id": str(rec.get("id", "unknown") or "unknown"),
                        "title": str(rec.get("title", "Producto") or "Producto"),
                        "description": str(rec.get("description", "") or ""),
                        "localized_title": str(rec.get("localized_title", rec.get("title", "Producto")) or "Producto"),
                        "localized_description": str(rec.get("localized_description", rec.get("description", "")) or ""),
                        "market_price": float(rec.get("market_price", rec.get("price", 0.0)) or 0.0),
                        "currency": str(market_context.get("currency", "USD")),
                        "images": list(rec.get("images", []) or [])
                    },
                    "market_score": float(rec.get("market_score", rec.get("score", 0.5)) or 0.5),
                    "viability_score": float(rec.get("viability_score", 0.8) or 0.8),
                    "reason": str(rec.get("reason", "Based on your preferences") or "Based on your preferences"),
                    "metadata": {
                        "market_adapted": bool(self.market_aware),
                        "mcp_processed": bool(self.mcp_available),
                        "source": str(source or "mcp_aware_hybrid")  # Usar la fuente específica de cada recomendación
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
            # Fallback a recomendaciones base - ahora user_id está garantizado que esté definido
            try:
                base_recommendations = await self.base_recommender.get_recommendations(
                    user_id=user_id,
                    product_id=product_id,
                    n_recommendations=n_recommendations
                )
            except Exception as inner_e:
                logger.error(f"Error en fallback de recomendaciones: {inner_e}")
                base_recommendations = []  # Lista vacía si falla el fallback
            
            # Nuevo: Intentar con fallback garantizado si no hay recomendaciones en caso de error
            if not base_recommendations and hasattr(self.base_recommender, 'content_recommender'):
                import random
                logger.info("Aplicando fallback de emergencia (error) con productos aleatorios")
                
                # Verificar si tenemos product_data disponible
                if hasattr(self.base_recommender.content_recommender, 'product_data') and \
                   self.base_recommender.content_recommender.product_data:
                    # Obtener productos aleatorios del catálogo
                    all_products = self.base_recommender.content_recommender.product_data
                    if len(all_products) > 0:
                        num_sample = min(n_recommendations, len(all_products))
                        random_products = random.sample(all_products, num_sample)
                        
                        base_recommendations = []
                        for product in random_products:
                            base_recommendations.append({
                                "id": str(product.get('id', '')),
                                "title": product.get('title', 'Producto'),
                                "description": product.get('body_html', ''),
                                "price": 0.0,
                                "score": 0.5,
                                "source": "error_recovery_catalog"  # Fuente específica para productos de recuperación de error
                            })
                        
                        logger.info(f"Fallback de emergencia aplicó {len(base_recommendations)} productos")
                else:
                    # Fallback absoluto (productos de emergencia fijos) si no hay catálogo disponible
                    logger.warning("Catálogo no disponible en fallback de error, usando productos de emergencia estáticos")
                    emergency_products = [
                        {
                            "id": "emergency1",
                            "title": "Camisa Azul Clásica",
                            "description": "Camisa azul de alta calidad con corte clásico.",
                            "price": 29.99,
                            "score": 0.5,
                            "source": "error_recovery_products"
                        },
                        {
                            "id": "emergency2",
                            "title": "Pantalones Negros Slim Fit",
                            "description": "Pantalones negros de corte slim fit para ocasiones formales.",
                            "price": 39.99,
                            "score": 0.5,
                            "source": "error_recovery_products"
                        },
                        {
                            "id": "emergency3",
                            "title": "Zapatos de Cuero Marrón",
                            "description": "Zapatos clásicos de cuero en color marrón.",
                            "price": 59.99,
                            "score": 0.5,
                            "source": "error_recovery_products"
                        }
                    ]
                    base_recommendations = emergency_products[:n_recommendations]
                    logger.info(f"Fallback de emergencia estático aplicó {len(base_recommendations)} productos")
            
            # 🔧 CORRECCIÓN: Fallback robusto con manejo de None
            safe_recommendations = []
            for rec in base_recommendations:
                safe_rec = {
                    "product": {
                        "id": str(rec.get("id", "error_product") or "error_product"),
                        "title": str(rec.get("title", "Producto No Disponible") or "Producto No Disponible"),
                        "description": str(rec.get("description", "Error al procesar") or "Error al procesar"),
                        "market_price": float(rec.get("price", 0.0) or 0.0),
                        "currency": "USD"
                    },
                    "market_score": float(rec.get("score", 0.5) or 0.5),
                    "viability_score": 0.5,
                    "reason": "Fallback recommendation",
                    "metadata": {
                        "source": str(rec.get("source", "error_fallback") or "error_fallback"),
                        "error_recovery": True
                    }
                }
                safe_recommendations.append(safe_rec)
            
            return {
                "recommendations": safe_recommendations,
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
