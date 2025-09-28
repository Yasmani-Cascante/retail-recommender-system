"""
MCP Conversation Handler - Implementación centralizada de la Opción A
====================================================================

Implementación correcta de la arquitectura MCP:
1. HybridRecommender.get_recommendations() → recomendaciones base
2. MCPPersonalizationEngine.generate_personalized_response() → personalización
3. Market adaptation → adaptación final

Esta implementación resuelve el error:
'MCPPersonalizationEngine' object has no attribute 'get_recommendations'

Author: Senior Architecture Team
Version: 1.0.0 - Option A Implementation
Date: 2025-08-30
"""

import os
import time
import logging
import asyncio
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


async def get_mcp_conversation_recommendations(
    validated_user_id: str,
    validated_product_id: Optional[str],
    conversation_query: str,
    market_id: str,
    n_recommendations: int = 5,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    ✅ ARQUITECTURA CORRECTA: HybridRecommender + MCPPersonalizationEngine
    
    Implementación optimizada que sigue el patrón arquitectónico correcto:
    1. Obtiene recomendaciones base con HybridRecommender
    2. Las personaliza con MCPPersonalizationEngine 
    3. Aplica adaptación de mercado
    4. Retorna respuesta estructurada
    
    Args:
        validated_user_id: ID de usuario validado
        validated_product_id: ID de producto opcional
        conversation_query: Query de conversación del usuario
        market_id: ID del mercado (US, ES, MX, etc.)
        n_recommendations: Número de recomendaciones a obtener
        session_id: ID de sesión opcional
        
    Returns:
        Dict con recommendations, ai_response y metadata
    """
    start_time = time.time()
    logger.info(f"🚀 Starting MCP conversation flow: user={validated_user_id}, query='{conversation_query[:50]}...'")
    
    try:
        # ===== PASO 1: Obtener recomendaciones base =====
        base_recommendations = []
        base_recommender_available = False
        
        try:
            from src.api import main_unified_redis
            if hasattr(main_unified_redis, 'hybrid_recommender') and main_unified_redis.hybrid_recommender:
                base_recommendations = await asyncio.wait_for(
                    main_unified_redis.hybrid_recommender.get_recommendations(
                        user_id=validated_user_id,
                        product_id=validated_product_id,
                        n_recommendations=n_recommendations
                    ),
                    timeout=5.0  # Timeout específico para recomendaciones base
                )
                base_recommender_available = True
                logger.info(f"✅ Base recommendations obtained: {len(base_recommendations)} items")
            else:
                logger.warning("❌ HybridRecommender not available in main_unified_redis")
        except asyncio.TimeoutError:
            logger.warning("⏰ HybridRecommender timeout - proceeding without base recommendations")
        except Exception as e:
            logger.error(f"❌ Error getting base recommendations: {e}")

        # ===== PASO 2: Crear contexto MCP =====
        mcp_context = None
        try:
            from src.api.mcp.conversation_state_manager import (
                MCPConversationContext, ConversationStage, IntentEvolution
            )
            
            # Crear contexto con campos REALES de MCPConversationContext
            mcp_context = MCPConversationContext(
                session_id=session_id or f"temp_{validated_user_id}_{int(time.time())}",
                user_id=validated_user_id,
                created_at=time.time(),
                last_updated=time.time(),
                conversation_stage=ConversationStage.EXPLORING,
                total_turns=1,
                turns=[],  # Lista vacía por ahora
                intent_history=[],  # Lista vacía por ahora
                primary_intent="product_recommendation",
                intent_evolution_pattern=IntentEvolution.STABLE,
                market_preferences={},  # Dict vacío por ahora
                avg_response_time=1.0,
                conversation_velocity=1.0,
                engagement_score=0.7,
                user_agent="mcp_api_client",
                initial_market_id=market_id,
                current_market_id=market_id,
                device_type="desktop"  # ✅ FIX: Campo faltante que causaba el error
            )
            logger.info("✅ MCP context created successfully")
        except ImportError as e:
            logger.error(f"❌ Cannot import MCP context classes: {e}")
        except Exception as e:
            logger.error(f"❌ Error creating MCP context: {e}")

        # ===== PASO 3: Obtener instancia de MCPPersonalizationEngine =====
        # ✅ CORRECTO: Usar ServiceFactory apropiadamente (sin circular imports ya resueltos)
        mcp_engine = None
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        
        if anthropic_api_key:
            try:
                from src.api.mcp.engines.mcp_personalization_engine import MCPPersonalizationEngine
                from anthropic import AsyncAnthropic
                
                # Create Anthropic client
                anthropic_client = AsyncAnthropic(api_key=anthropic_api_key)
                
                # ✅ FIXED: Import ServiceFactory in function scope (proper lazy import)
                redis_service = None
                try:
                    # Import at function level to avoid any potential import issues
                    from src.api.factories.service_factory import ServiceFactory
                    redis_service = await ServiceFactory.get_redis_service()
                    logger.info("✅ ServiceFactory imported successfully - Redis available")
                except ImportError as ie:
                    logger.warning(f"⚠️ ServiceFactory import failed: {ie} - continuing without Redis")
                except Exception as re:
                    logger.warning(f"⚠️ Redis service unavailable: {re} - continuing without Redis")
                
                # Create engine with proper Redis service (if available)
                mcp_engine = MCPPersonalizationEngine(
                    anthropic_client=anthropic_client,
                    redis_service=redis_service,  # ✅ Use actual Redis service
                    profile_ttl=604800,
                    enable_ml_predictions=bool(redis_service)  # Enable ML if Redis available
                )
                
                if redis_service:
                    logger.info("✅ MCPPersonalizationEngine created with full Redis functionality")
                else:
                    logger.info("✅ MCPPersonalizationEngine created with basic functionality (no Redis)")
                
            except Exception as e:
                logger.warning(f"⚠️ Error creating MCPPersonalizationEngine: {e}")
                mcp_engine = None
        else:
            logger.warning("⚠️ ANTHROPIC_API_KEY not found - personalization disabled")

        # ===== PASO 4: Aplicar personalización =====
        final_response = {
            "recommendations": base_recommendations,
            "ai_response": f"I found {len(base_recommendations)} recommendations for your query: '{conversation_query}'",
            "metadata": {
                "personalization_applied": False,
                "base_recommender_available": base_recommender_available,
                "mcp_engine_available": mcp_engine is not None,
                "market_id": market_id,
                "processing_time_ms": (time.time() - start_time) * 1000
            }
        }

        if mcp_engine and mcp_context and base_recommendations:
            try:
                # Intentar personalización con timeout
                personalization_result = await asyncio.wait_for(
                    mcp_engine.generate_personalized_response(
                        mcp_context=mcp_context,
                        recommendations=base_recommendations
                    ),
                    timeout=7.0  # Timeout para personalización
                )
                
                # Actualizar respuesta con datos personalizados
                final_response.update({
                    "recommendations": personalization_result.get("personalized_recommendations", base_recommendations),
                    "ai_response": personalization_result.get("personalized_response", final_response["ai_response"]),
                    "metadata": {
                        **final_response["metadata"],
                        "personalization_applied": True,
                        "strategy_used": personalization_result.get("personalization_metadata", {}).get("strategy_used", "hybrid"),
                        "personalization_score": personalization_result.get("personalization_metadata", {}).get("personalization_score", 0.0)
                    }
                })
                
                logger.info("✅ MCP personalization completed successfully")
                
            except asyncio.TimeoutError:
                logger.warning("⏰ MCP personalization timeout - using base recommendations")
                final_response["metadata"]["personalization_timeout"] = True
            except AttributeError as e:
                logger.error(f"❌ Method not found in MCPPersonalizationEngine: {e}")
                final_response["metadata"]["personalization_error"] = "method_not_found"
                
                # Try alternative method names as fallback
                try:
                    if hasattr(mcp_engine, '_generate_claude_personalized_response'):
                        logger.info("🔄 Trying alternative method _generate_claude_personalized_response")
                        # This would require different parameters, but we try as fallback
                        alt_result = await asyncio.wait_for(
                            mcp_engine._generate_claude_personalized_response(
                                personalization_context=None,  # Would need proper context
                                personalized_result={"recommendations": base_recommendations}
                            ),
                            timeout=5.0
                        )
                        final_response["ai_response"] = alt_result.get("conversational_response", final_response["ai_response"])
                        final_response["metadata"]["personalization_applied"] = True
                        final_response["metadata"]["personalization_method"] = "alternative_claude_method"
                        logger.info("✅ Alternative personalization method succeeded")
                except Exception as alt_e:
                    logger.warning(f"⚠️ Alternative personalization method also failed: {alt_e}")
                    
            except Exception as e:
                logger.error(f"❌ Error in MCP personalization: {e}")
                final_response["metadata"]["personalization_error"] = str(e)[:100]
        else:
            missing_components = []
            if not mcp_engine: missing_components.append("mcp_engine")
            if not mcp_context: missing_components.append("mcp_context") 
            if not base_recommendations: missing_components.append("base_recommendations")
            
            logger.warning(f"⚠️ Skipping personalization - missing: {', '.join(missing_components)}")
            final_response["metadata"]["missing_components"] = missing_components

        # ===== PASO 5: Aplicar adaptación de mercado =====
        if final_response["recommendations"]:
            try:
                from src.core.market.adapter import get_market_adapter
                adapter = get_market_adapter()
                
                adapted_recommendations = []
                for rec in final_response["recommendations"]:
                    try:
                        adapted_rec = await adapter.adapt_product(rec, market_id)
                        adapted_recommendations.append(adapted_rec)
                    except Exception as e:
                        logger.warning(f"⚠️ Market adaptation failed for product {rec.get('id', 'unknown')}: {e}")
                        adapted_recommendations.append(rec)  # Use original if adaptation fails
                
                final_response["recommendations"] = adapted_recommendations
                final_response["metadata"]["market_adaptation_applied"] = True
                logger.info(f"✅ Market adaptation applied to {len(adapted_recommendations)} recommendations")
                
            except ImportError:
                logger.warning("⚠️ Market adapter not available - skipping market adaptation")
                final_response["metadata"]["market_adaptation_available"] = False
            except Exception as e:
                logger.warning(f"⚠️ Market adaptation error: {e}")
                final_response["metadata"]["market_adaptation_error"] = str(e)[:100]

        final_processing_time = (time.time() - start_time) * 1000
        final_response["metadata"]["processing_time_ms"] = final_processing_time
        
        logger.info(f"✅ MCP conversation flow completed in {final_processing_time:.2f}ms")
        return final_response

    except Exception as e:
        logger.error(f"❌ Critical error in MCP conversation flow: {e}")
        
        # Emergency fallback
        return {
            "recommendations": [],
            "ai_response": f"I apologize, but I encountered an error processing your request: '{conversation_query}'. Please try again.",
            "metadata": {
                "error": str(e)[:200],
                "fallback_used": "emergency",
                "processing_time_ms": (time.time() - start_time) * 1000,
                "market_id": market_id
            }
        }


async def get_mcp_market_recommendations(
    product_id: str,
    market_id: str,
    user_id: str,
    n_recommendations: int = 5
) -> Dict[str, Any]:
    """
    Función auxiliar para el endpoint de recomendaciones por mercado.
    Usa el mismo flujo arquitectónico correcto.
    
    Args:
        product_id: ID del producto base
        market_id: ID del mercado
        user_id: ID del usuario
        n_recommendations: Número de recomendaciones
        
    Returns:
        Dict con recomendaciones adaptadas al mercado
    """
    return await get_mcp_conversation_recommendations(
        validated_user_id=user_id,
        validated_product_id=product_id,
        conversation_query=f"Show me products similar to {product_id}",
        market_id=market_id,
        n_recommendations=n_recommendations,
        session_id=f"market_rec_{user_id}_{int(time.time())}"
    )


# ===== FUNCIONES DE UTILIDAD =====

def validate_mcp_dependencies() -> Dict[str, Any]:
    """
    Valida que todas las dependencias MCP estén disponibles.
    Útil para health checks y debugging.
    
    Returns:
        Dict con el estado de cada dependencia
    """
    dependencies_status = {
        "hybrid_recommender": False,
        "mcp_context_classes": False,
        "mcp_personalization_engine": False,
        "market_adapter": False,
        "anthropic_api_key": False
    }
    
    try:
        from src.api import main_unified_redis
        dependencies_status["hybrid_recommender"] = hasattr(main_unified_redis, 'hybrid_recommender')
    except Exception:
        pass
    
    try:
        from src.api.mcp.conversation_state_manager import MCPConversationContext
        dependencies_status["mcp_context_classes"] = True
    except Exception:
        pass
    
    try:
        from src.api.mcp.engines.mcp_personalization_engine import MCPPersonalizationEngine
        dependencies_status["mcp_personalization_engine"] = True
    except Exception:
        pass
    
    try:
        from src.core.market.adapter import get_market_adapter
        dependencies_status["market_adapter"] = True
    except Exception:
        pass
    
    dependencies_status["anthropic_api_key"] = bool(os.getenv("ANTHROPIC_API_KEY"))
    
    return {
        "dependencies": dependencies_status,
        "overall_health": all(dependencies_status.values()),
        "critical_missing": [k for k, v in dependencies_status.items() if not v],
        "timestamp": time.time()
    }


def get_architecture_info() -> Dict[str, Any]:
    """
    Información sobre la implementación de la arquitectura MCP.
    
    Returns:
        Dict con información arquitectónica
    """
    return {
        "architecture_version": "option_a_implemented",
        "implementation_date": "2025-08-30",
        "pattern": "HybridRecommender → MCPPersonalizationEngine → MarketAdapter",
        "resolved_issue": "MCPPersonalizationEngine get_recommendations() method not found",
        "components": {
            "base_recommendations": "HybridRecommender.get_recommendations()",
            "personalization": "MCPPersonalizationEngine.generate_personalized_response()", 
            "market_adaptation": "MarketAdapter.adapt_product()",
            "fallbacks": "Multiple levels with graceful degradation"
        },
        "timeouts": {
            "base_recommendations": "5s",
            "personalization": "7s",
            "total_target": "<12s"
        }
    }
