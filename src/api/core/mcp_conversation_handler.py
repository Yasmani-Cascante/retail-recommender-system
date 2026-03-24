"""
MCP Conversation Handler - Implementación con Parallel Processing
==================================================================

Implementación optimizada de la arquitectura MCP con procesamiento paralelo:
1. HybridRecommender.get_recommendations() → recomendaciones base
2. MCPPersonalizationEngine.generate_personalized_response() → personalización
3. Market adaptation → adaptación final
4. ✅ NUEVO: Procesamiento paralelo con parallel_processor para eliminar timeouts

Esta implementación resuelve:
- 'MCPPersonalizationEngine' object has no attribute 'get_recommendations'
- ⏰ MCP personalization timeout warnings
- Performance issues con ejecución secuencial

Author: Senior Architecture Team
Version: 2.0.0 - Parallel Processing Implementation
Date: 2025-09-01
"""

import os
import time
import logging
import asyncio
import inspect
from typing import Dict, List, Optional, Any, Callable

# ✅ NUEVO: Import parallel processor
from src.api.core.parallel_processor import (
    ParallelTask, 
    parallel_processor,
    execute_mcp_operations_parallel
)

# FIX (24/03/2026): Import hybrid_detector dentro de función para evitar
# que un ImportError de nivel-módulo silenciosamente rompa el handler completo.
# El import original en nivel-módulo hacía que cualquier fallo de sklearn/joblib
# durante el cold start corrompiera todo el módulo sin log visible.
# Ahora se importa lazy dentro del bloque try de intent detection.

logger = logging.getLogger(__name__)


async def get_mcp_conversation_recommendations(
    validated_user_id: str,
    validated_product_id: Optional[str],
    conversation_query: str,
    market_id: str,
    n_recommendations: int = 5,
    session_id: Optional[str] = None,
    language: Optional[str] = "es"  # ✅ NUEVO: Idioma para KB y personalización
) -> Dict[str, Any]:
    """
    ✅ ARQUITECTURA PARALELA: HybridRecommender + MCPPersonalizationEngine + ParallelProcessor
    
    Implementación optimizada que usa procesamiento paralelo para eliminar timeouts:
    1. Ejecuta operaciones independientes en paralelo
    2. Reduce tiempo total de 6-9s a 2-3s 
    3. Mantiene toda la funcionalidad existente
    4. Agrega métricas de performance
    
    Args:
        validated_user_id: ID de usuario validado
        validated_product_id: ID de producto opcional
        conversation_query: Query de conversación del usuario
        market_id: ID del mercado (US, ES, MX, etc.)
        n_recommendations: Número de recomendaciones a obtener
        session_id: ID de sesión opcional
        
    Returns:
        Dict con recommendations, ai_response y metadata (incluyendo parallel metrics)
    """
    start_time = time.time()
    diversification_flag = False  # ✅ CRITICAL: Track if diversification was actually applied
    logger.info(f"🚀 Starting PARALLEL MCP conversation flow: user={validated_user_id}, query='{conversation_query[:50]}...'")
    
    # ✅ NUEVO: Log crítico para debugging
    logger.info(f"🌐 Handler received language: {language} (will be used for KB and personalization)")
    
    logger.info(f"🚀 Starting PARALLEL MCP conversation flow...")

    try:
        # ===== FASE 1: OBTENER ESTADO CONVERSACIONAL REAL =====
        # ✅ NUEVO: Obtener contexto conversacional real existente
        mcp_context = None
        actual_session_id = session_id or f"session_{validated_user_id}_{int(time.time())}"
        
        try:
            from src.api.mcp.conversation_state_manager import (
                MCPConversationContext, ConversationStage, IntentEvolution
            )
            
            # Intentar cargar contexto existente primero
            try:
                # from src.api.factories.service_factory import ServiceFactory
                # state_manager = await ServiceFactory.get_conversation_state_manager()
                from src.api.mcp.conversation_state_manager import get_conversation_state_manager
                state_manager = await get_conversation_state_manager()
                
                # Cargar o crear sesión conversacional
                mcp_context = await state_manager.get_or_create_session(
                    session_id=actual_session_id,
                    user_id=validated_user_id,
                    market_id=market_id
                )
                
                logger.info(f"✅ MCP context loaded: session={actual_session_id}, turns={mcp_context.total_turns}")
                
            except Exception as state_e:
                logger.warning(f"⚠️ Could not load conversation state, creating temporary: {state_e}")
                
                # Fallback: crear contexto temporal
                mcp_context = MCPConversationContext(
                    session_id=actual_session_id,
                    user_id=validated_user_id,
                    created_at=time.time(),
                    last_updated=time.time(),
                    conversation_stage=ConversationStage.EXPLORING,
                    total_turns=1,
                    turns=[],
                    intent_history=[],
                    primary_intent="product_recommendation",
                    intent_evolution_pattern=IntentEvolution.STABLE,
                    market_preferences={},
                    avg_response_time=1.0,
                    conversation_velocity=1.0,
                    engagement_score=0.7,
                    user_agent="mcp_api_client",
                    initial_market_id=market_id,
                    current_market_id=market_id,
                    device_type="desktop"
                )
                
            logger.info("✅ MCP context created successfully")
        except Exception as e:
            logger.error(f"❌ Error creating MCP context: {e}")

        # ═══════════════════════════════════════════════════════════════
        # ✨ NUEVO: FASE 1.5 - INTENT DETECTION
        # ═══════════════════════════════════════════════════════════════
        
        intent_result = None
        intent_enabled = False

        # FIX (24/03/2026): Diagnóstico explícito al entrar en el bloque.
        # Sin estos logs era imposible saber si el bloque se ejecutaba o si
        # era silenciado por el except. El logger.debug anterior era invisible
        # con LOG_LEVEL=INFO en producción.
        logger.info("🔍 INTENT DETECTION BLOCK: Evaluating...")
        
        try:
            from src.api.core.config import get_settings

            # FIX (24/03/2026): get_settings() usa @lru_cache. Si hay error de
            # Pydantic al arrancar (case_sensitive=True + variable faltante),
            # el caché queda con valores por defecto y enable_intent_detection=False.
            # Forzar re-lectura del env directamente como backup de diagnóstico.
            settings = get_settings()
            intent_enabled = settings.enable_intent_detection

            # Log explícito del valor leído — visible en GCP Logs con LOG_LEVEL=INFO
            logger.info(f"🔍 INTENT DETECTION: enable_intent_detection={intent_enabled} "
                        f"(from settings, env raw='{os.environ.get('ENABLE_INTENT_DETECTION', 'NOT_SET')}')")
            
            if intent_enabled:
                # ✅ NUEVO: Verificar si ML está habilitado
                ml_enabled = getattr(settings, 'ml_intent_enabled', False)
                
                if ml_enabled:
                    # ✅ HÍBRIDO: Usar detector ML + rule-based
                    logger.info(f"🎯 ML Intent Detection ENABLED - analyzing query: '{conversation_query[:50]}...'")
                    
                    try:
                        # FIX (24/03/2026): Import lazy para evitar que
                        # sklearn/joblib falle en import-time y silencie el handler.
                        from src.api.ml.hybrid_detector import get_hybrid_intent_detector
                        hybrid_detector = get_hybrid_intent_detector()
                        
                        # Detectar intent con híbrido (async)
                        hybrid_result = await hybrid_detector.detect(conversation_query, user_id=validated_user_id)
                        
                        # Convertir a formato estándar
                        from src.api.core.intent_detection import IntentDetectionResult
                        intent_result = hybrid_result.to_intent_detection_result()
                        
                        logger.info(f"   Detected Intent: {intent_result.primary_intent} "
                                   f"(method: {hybrid_result.method_used}, "
                                   f"confidence: {hybrid_result.confidence:.2f}, "
                                   f"time: {hybrid_result.total_time_ms:.1f}ms)")
                        
                    except Exception as ml_e:
                        logger.warning(f"⚠️ ML intent detection failed, falling back to rule-based: {ml_e}")
                        # Fallback a rule-based
                        from src.api.core.intent_detection import detect_intent
                        intent_result = detect_intent(conversation_query)
                        
                else:
                    # ✅ RULE-BASED SOLO (comportamiento original)
                    from src.api.core.intent_detection import detect_intent
                    logger.info(f"🎯 Intent Detection ENABLED (rule-based only) - analyzing query: '{conversation_query[:50]}...'")
                    intent_result = detect_intent(conversation_query)
                
                logger.info(f"   Detected Intent: {intent_result.primary_intent} "
                           f"(confidence: {intent_result.confidence:.2f})")
                logger.info(f"   Reasoning: {intent_result.reasoning}")
                
                # Check if confidence meets threshold
                if intent_result.confidence >= settings.intent_confidence_threshold:
                    
                    # INFORMATIONAL QUERY → Return knowledge base answer
                    from src.api.core.intent_types import IntentType
                    if intent_result.primary_intent == IntentType.INFORMATIONAL:
                        logger.info("📚 INFORMATIONAL intent detected - using Knowledge Base v2")
                        
                        from src.api.core.intent_types import InformationalSubIntent
                        
                        # ✅ FIX: Resolve Knowledge Base instance robustly (app.state, module aliases, fallback)
                        from src.api import main_unified_redis

                        kb_answer = None
                        kb_obj = None

                        try:
                            # Prefer app.state (lifespan-initialized) values
                            if hasattr(main_unified_redis, 'app') and getattr(main_unified_redis, 'app').state:
                                kb_obj = getattr(main_unified_redis.app.state, 'knowledge_base_v2', None) or getattr(main_unified_redis.app.state, 'knowledge_base', None)

                            # Fall back to module-level aliases if not set on app.state
                            if not kb_obj:
                                kb_obj = getattr(main_unified_redis, 'knowledge_base_v2', None) or getattr(main_unified_redis, 'knowledge_base', None)

                        except Exception as resolve_e:
                            logger.warning(f"⚠️ Error resolving KB from main_unified_redis: {resolve_e}")

                        # Final fallback: try hardcoded KB singleton
                        if not kb_obj:
                            try:
                                from src.api.core.knowledge_base import get_knowledge_base
                                kb_obj = get_knowledge_base()
                                logger.info("ℹ️ Using hardcoded fallback KB via get_knowledge_base()")
                            except Exception as fallback_e:
                                logger.debug(f"Fallback hardcoded KB not available: {fallback_e}")

                        if kb_obj:
                            try:
                                maybe_result = kb_obj.get_answer(
                                    sub_intent=InformationalSubIntent(intent_result.sub_intent),
                                    language=language,
                                    category=None
                                )
                                # Support both async and sync implementations
                                if asyncio.iscoroutine(maybe_result) or inspect.isawaitable(maybe_result):
                                    kb_answer = await maybe_result
                                else:
                                    kb_answer = maybe_result

                                logger.info(f"✅ KB query completed for language={language}")
                            except Exception as kb_e:
                                logger.error(f"❌ KB error: {kb_e}", exc_info=True)
                        else:
                            logger.warning("⚠️ No Knowledge Base instance available to query")
                        
                        if kb_answer:
                            logger.info("✅ Knowledge Base answer found - returning informational response")
                            
                            return {
                                "type": "informational",
                                "answer": kb_answer.answer,
                                "ai_response": kb_answer.answer, 
                                "recommendations": [],  # NO products for informational queries
                                "metadata": {
                                    "intent_detection": {
                                        "primary_intent": intent_result.primary_intent,
                                        "sub_intent": intent_result.sub_intent,
                                        "confidence": intent_result.confidence,
                                        "reasoning": intent_result.reasoning,
                                        "matched_patterns": intent_result.matched_patterns,
                                        "method_used": getattr(hybrid_result, 'method_used', 'rule_based') if ml_enabled else 'rule_based'
                                    },
                                    "knowledge_base_used": True,
                                    "sources": kb_answer.sources,
                                    "related_links": kb_answer.related_links,
                                    "processing_time_ms": (time.time() - start_time) * 1000,
                                    "market_id": market_id,
                                    "session_id": actual_session_id
                                }
                            }
                        else:
                            logger.warning("⚠️ No knowledge base answer found - falling back to products")
                            # Continue to product recommendations (fallback)
                    
                    # TRANSACTIONAL QUERY → Continue normal flow
                    else:
                        logger.info("🛍️ TRANSACTIONAL intent detected - continuing with product recommendations")
                        # Continue normal flow (no early return)
                
                else:
                    logger.info(f"⚠️ Intent confidence {intent_result.confidence:.2f} below threshold "
                        f"{settings.intent_confidence_threshold} - defaulting to products")
                        # Continue normal flow (low confidence)
            
            else:
                # FIX: era logger.debug — invisible con LOG_LEVEL=INFO en producción.
                logger.info("ℹ️ Intent Detection is DISABLED in settings (enable_intent_detection=False)")
        
        except ImportError as e:
            # exc_info=True añade el stack trace completo al log — esencial para debug
            logger.warning(f"⚠️ Intent Detection modules not available: {e}", exc_info=True)
        except Exception as e:
            # FIX: exc_info=True añade stack trace. Sin esto el error era invisible.
            logger.error(f"❌ Intent Detection error: {e} - falling back to products", exc_info=True)


        # ===== FASE 2: CREAR FUNCIONES WRAPPER PARA PARALLEL PROCESSING =====
        
        # ✅ CRITICAL FIX: Refresh context BEFORE parallel processing to ensure latest state
        if mcp_context and hasattr(mcp_context, 'session_id'):
            try:
                from src.api.mcp.conversation_state_manager import get_conversation_state_manager
                state_manager = await get_conversation_state_manager()
                fresh_context = await state_manager.load_conversation_state(mcp_context.session_id)
                if fresh_context and fresh_context.total_turns > mcp_context.total_turns:
                    mcp_context = fresh_context  # Update with fresher context
                    logger.info(f"🔄 Context refreshed: now has {mcp_context.total_turns} turns")
            except Exception as e:
                logger.warning(f"⚠️ Could not refresh context: {e}")
        
        async def get_base_recommendations() -> List[Dict[str, Any]]:
            """Wrapper function para obtener recomendaciones base con diversificación"""
            try:
                # ✅ NUEVO: Verificar si necesitamos diversificación basada en estado conversacional
                shown_products = set()
                use_diversification = False
                
                if mcp_context and mcp_context.total_turns > 0:
                    # ✅ DEBUGGING: Logging detallado del contexto conversacional
                    logger.info(f"🔍 DEBUG: MCP Context Investigation")
                    logger.info(f"    Session ID: {mcp_context.session_id}")
                    logger.info(f"    Total turns: {mcp_context.total_turns}")
                    logger.info(f"    Turns list length: {len(mcp_context.turns)}")
                    
                    # ✅ DEBUGGING: Investigar cada turn individualmente
                    for i, turn in enumerate(mcp_context.turns):
                        logger.info(f"🔍 DEBUG: Turn {i+1} Investigation:")
                        logger.info(f"    Turn type: {type(turn)}")
                        logger.info(f"    Turn attributes available: {hasattr(turn, 'recommendations_provided')}")
                        
                        if hasattr(turn, 'recommendations_provided'):
                            recs = turn.recommendations_provided
                            logger.info(f"    recommendations_provided type: {type(recs)}")
                            logger.info(f"    recommendations_provided value: {recs}")
                            logger.info(f"    recommendations_provided length: {len(recs) if recs else 'None/Empty'}")
                            
                            if recs:
                                logger.info(f"    First 3 recommendation IDs: {recs[:3]}")
                                shown_products.update(recs)
                        else:
                            logger.warning(f"    ❌ Turn {i+1} missing recommendations_provided attribute")
                        
                        # ✅ DEBUGGING: Otros atributos relevantes para contexto
                        if hasattr(turn, 'user_query'):
                            logger.info(f"    user_query: {turn.user_query}")
                        if hasattr(turn, 'turn_number'):
                            logger.info(f"    turn_number: {turn.turn_number}")
                    
                    use_diversification = len(shown_products) > 0
                    logger.info(f"🔄 FINAL RESULT: Diversification needed: {use_diversification}")
                    logger.info(f"🔄 FINAL RESULT: shown_products count: {len(shown_products)}")
                    logger.info(f"🔄 FINAL RESULT: shown_products IDs: {list(shown_products)[:5]}...")  # Primeros 5
                    
                    # ✅ CRITICAL: Set flag for later use in metadata
                    nonlocal diversification_flag
                    diversification_flag = use_diversification
                
                # Obtener recomendaciones del hybrid recommender
                from src.api import main_unified_redis
                if hasattr(main_unified_redis, 'hybrid_recommender') and main_unified_redis.hybrid_recommender:
                    
                    if use_diversification:
                        # ✅ NUEVO: Usar fallback inteligente con exclusión de productos ya vistos
                        try:
                            # from src.recommenders.improved_fallback_exclude_seen import ImprovedFallbackStrategies
                            from src.recommenders.improved_fallback_exclude_seen import (
                                ImprovedFallbackStrategies, 
                                extract_categories_from_query, 
                                get_concrete_categories
                            )
                            # Obtener todos los productos disponibles
                            all_products = main_unified_redis.hybrid_recommender.content_recommender.product_data
                            
                            # ═══════════════════════════════════════════════════════════════
                            # ✨ FIX #1: POBLAR user_events DESDE MCP CONTEXT
                            # ═══════════════════════════════════════════════════════════════
                            user_events = []
                            
                            if mcp_context and mcp_context.total_turns > 0:
                                logger.info(f"🔄 FIX #1: Building user_events from {mcp_context.total_turns} MCP turns")
                                
                                available_categories = get_concrete_categories()
                        
                                for turn_idx, turn in enumerate(mcp_context.turns):
                                    try:
                                        # Extraer query del usuario de este turn
                                        if hasattr(turn, 'user_query') and turn.user_query:
                                            # Detectar TODAS las categorías de este turn (puede devolver múltiples)
                                            inferred_categories = extract_categories_from_query(
                                                turn.user_query, 
                                                available_categories
                                            )
                                            
                                            # Si se detectaron categorías, crear un evento por cada una
                                            if inferred_categories:
                                                for inferred_category in inferred_categories:
                                                    # Crear pseudo-evento para esta categoría
                                                    user_events.append({
                                                        "productId": None,  # No hay producto específico
                                                        "product_info": {
                                                            "product_type": inferred_category,
                                                            "source_query": turn.user_query[:50]  # Snippet para debugging
                                                        },
                                                        "eventType": "view",  # Tipo genérico
                                                        "source": "mcp_context_turn",
                                                        "turn_number": turn_idx + 1
                                                    })
                                                    
                                                    logger.debug(f"   Turn {turn_idx + 1}: '{turn.user_query[:30]}...' → Category: {inferred_category}")
                                            else:
                                                logger.debug(f"   Turn {turn_idx + 1}: No category detected in '{turn.user_query[:30]}...'")
                                    
                                    except Exception as turn_e:
                                        logger.warning(f"⚠️ Error processing turn {turn_idx + 1} for user_events: {turn_e}")
                                        continue
                                
                                logger.info(f"✅ FIX #1: Generated {len(user_events)} user_events from MCP history")
                                if user_events:
                                    categories_found = [evt["product_info"]["product_type"] for evt in user_events]
                                    logger.info(f"   Historical categories: {categories_found}")
                            else:
                                logger.debug("   No MCP context available, user_events remains empty")
                            
                            # ✨ MEJORADO: Pasar query del usuario Y user_events poblado
                            recommendations = await ImprovedFallbackStrategies.smart_fallback(
                                user_id=validated_user_id,
                                products=all_products,
                                user_events=user_events,  # ✅ FIX #1: Ahora poblado
                                n=n_recommendations,
                                exclude_products=shown_products,
                                user_query=conversation_query  # ✨ Query awareness (mayor prioridad)
                            )
                            
                            logger.info(f"✅ Diversified recommendations obtained: {len(recommendations)} items")
                            logger.info(f"   Context used: {len(user_events)} historical events, excluded {len(shown_products)} seen products")
                            return recommendations
                            
                        except Exception as div_e:
                            logger.warning(f"⚠️ Diversification failed, using standard recommendations: {div_e}")
                            # Fallback to standard recommendations
                    
                    # Standard recommendations (primera llamada o fallback)
                    recommendations = await main_unified_redis.hybrid_recommender.get_recommendations(
                        user_id=validated_user_id,
                        product_id=validated_product_id,
                        n_recommendations=n_recommendations,
                        user_query=conversation_query  # ✨ NUEVO: Permite detección de categoría desde query
                    )
                    logger.info(f"✅ Base recommendations obtained: {len(recommendations)} items")
                    return recommendations
                else:
                    logger.warning("❌ HybridRecommender not available")
                    return []
            except Exception as e:
                logger.error(f"❌ Error getting base recommendations: {e}")
                return []

        async def prepare_mcp_engine() -> Optional[Any]:
            """
            Obtiene el MCPPersonalizationEngine singleton via ServiceFactory.

            Usar el singleton es crítico por dos razones:
            1. El cliente AsyncAnthropic ya tiene la conexión TCP/TLS a api.anthropic.com
               establecida (warm), eliminando el 'Connection error on attempt 1' que
               ocurre cuando se crea un cliente nuevo por cada request.
            2. Evita instanciar objetos pesados (~50ms de overhead) en el hot path.
            """
            try:
                from src.api.factories.service_factory import ServiceFactory
                # get_mcp_recommender() retorna el singleton con cliente Anthropic ya warm.
                # Si no existe aún, lo crea una sola vez y lo reutiliza en adelante.
                mcp_engine = await ServiceFactory.get_mcp_recommender()
                if mcp_engine is not None:
                    logger.info("✅ MCPPersonalizationEngine singleton obtained (warm client)")
                else:
                    logger.warning("⚠️ MCPPersonalizationEngine singleton returned None")
                return mcp_engine
            except Exception as e:
                logger.error(f"❌ Error obtaining MCPPersonalizationEngine singleton: {e}")
                return None

        async def get_market_adapter():
            """Wrapper function para obtener market adapter"""
            try:
                from src.core.market.adapter import get_market_adapter
                adapter = get_market_adapter()
                logger.info("✅ Market adapter obtained successfully")
                return adapter
            except ImportError:
                logger.warning("⚠️ Market adapter not available")
                return None
            except Exception as e:
                logger.warning(f"⚠️ Market adapter error: {e}")
                return None

        # ===== FASE 3: EJECUCIÓN PARALELA DE OPERACIONES INDEPENDIENTES =====
        logger.info("🔄 Executing parallel operations...")
        
        # Ejecutar las 3 operaciones principales en paralelo
        parallel_result = await execute_mcp_operations_parallel(
            mcp_call=get_base_recommendations,
            personalization_call=prepare_mcp_engine,  
            market_context_call=get_market_adapter,
            intent_analysis_call=None  # No needed for this flow
        )
        
        # Extraer resultados del procesamiento paralelo
        base_recommendations = []
        mcp_engine = None
        market_adapter = None
        
        parallel_results = parallel_result.get("results", {})
        parallel_metrics = {
            "execution_time_ms": parallel_result.get("execution_time_ms", 0),
            "parallel_efficiency": parallel_result.get("parallel_efficiency", 0),
            "timestamp": parallel_result.get("timestamp", time.time())
        }
        
        # Procesar resultado de recomendaciones base
        if "mcp_recommendations" in parallel_results:
            rec_result = parallel_results["mcp_recommendations"]
            if rec_result.get("success", False):
                base_recommendations = rec_result.get("result", [])
                logger.info(f"✅ Parallel: Base recommendations retrieved ({len(base_recommendations)} items)")
            else:
                logger.warning(f"⚠️ Parallel: Base recommendations failed: {rec_result.get('error', 'unknown')}")

        # Procesar resultado de MCP engine
        if "personalization" in parallel_results:
            pers_result = parallel_results["personalization"]
            if pers_result.get("success", False):
                mcp_engine = pers_result.get("result")
                logger.info("✅ Parallel: MCP engine prepared successfully")
            else:
                logger.warning(f"⚠️ Parallel: MCP engine preparation failed: {pers_result.get('error', 'unknown')}")

        # Procesar resultado de market adapter
        if "market_context" in parallel_results:
            market_result = parallel_results["market_context"]
            if market_result.get("success", False):
                market_adapter = market_result.get("result")
                logger.info("✅ Parallel: Market adapter prepared successfully")
            else:
                logger.warning(f"⚠️ Parallel: Market adapter preparation failed: {market_result.get('error', 'unknown')}")

        # ===== FASE 4: PERSONALIZACIÓN CON CACHE INTELIGENTE =====
        final_response = {
            "recommendations": base_recommendations,
            "ai_response": f"I found {len(base_recommendations)} recommendations for your query: '{conversation_query}'",
            "metadata": {
                "personalization_applied": False,
                "base_recommendations_count": len(base_recommendations),
                "mcp_engine_available": mcp_engine is not None,
                "market_adapter_available": market_adapter is not None,
                "market_id": market_id,
                "parallel_processing": parallel_metrics,
                "processing_time_ms": (time.time() - start_time) * 1000,
                "diversification_applied": diversification_flag  # ✅ CORRECTED: Use actual diversification flag
            }
        }

        # ✅ NUEVA OPTIMIZACIÓN: Cache inteligente para personalización via ServiceFactory
        if mcp_engine and mcp_context and base_recommendations:
            try:
                # ✅ FIX LEGACY MODE: Usar ServiceFactory para obtener cache configurado correctamente
                from src.api.factories.service_factory import ServiceFactory
                
                # ✅ CRITICAL: Obtener PersonalizationCache desde ServiceFactory
                # Esto garantiza que DiversityAwareCache tenga acceso al local_catalog
                personalization_cache = await ServiceFactory.get_personalization_cache()
                
                # Preparar contexto de cache con información conversacional
                # ✅ CORRECCIÓN 3: Incluir turn number y shown products para diversificación
                cache_context = {
                    "market_id": market_id,
                    "user_segment": "standard",  # Podría mejorarse con segmentación real
                    "product_categories": ["general"],  # Mantener estable para cache hits
                    "turn_number": mcp_context.total_turns + 1 if mcp_context else 1,  # ✅ NUEVO: Próximo turn
                    "shown_products": []  # ✅ NUEVO: Productos ya mostrados
                }
                
                # ✅ MEJORA: Extracción más eficiente de productos ya mostrados
                if mcp_context and mcp_context.total_turns > 0:
                    shown_products = []
                    for turn in mcp_context.turns[-3:]:  # Solo últimos 3 turns para eficiencia
                        if hasattr(turn, 'recommendations_provided') and turn.recommendations_provided:
                            shown_products.extend(turn.recommendations_provided)
                    cache_context["shown_products"] = shown_products
                
                # ✅ PASO 1: Intentar obtener desde cache
                logger.info("🔍 Checking personalization cache...")
                cached_personalization = await personalization_cache.get_cached_personalization(
                    user_id=validated_user_id,
                    query=conversation_query,
                    context=cache_context,
                    similarity_threshold=0.8
                )
                
                if cached_personalization:
                    logger.info("⚡ Using cached personalization - avoiding Claude API call")
                    
                    # ✅ NUEVO: Si es cache hit pero follow-up request, verificar si necesitamos diversificación
                    recommendations_to_use = cached_personalization.get("personalized_recommendations", base_recommendations)
                    
                    if mcp_context and mcp_context.total_turns > 1:
                        # Es una request de follow-up, pero tenemos cache hit
                        # Verificar si las recomendaciones cacheadas son diferentes a las ya mostradas
                        shown_product_ids = set()
                        for turn in mcp_context.turns:
                            if hasattr(turn, 'recommendations_provided') and turn.recommendations_provided:
                                shown_product_ids.update(turn.recommendations_provided)
                        
                        current_rec_ids = set(rec.get('id') for rec in recommendations_to_use if rec.get('id'))
                        overlap = len(shown_product_ids.intersection(current_rec_ids))
                        
                        if overlap > len(current_rec_ids) * 0.7:  # Si hay más de 70% de overlap
                            logger.info(f"🔄 Cache hit but high overlap ({overlap}/{len(current_rec_ids)}), using diversified recommendations")
                            recommendations_to_use = base_recommendations  # Usar las ya diversificadas
                    
                    # Usar respuesta cacheada (posiblemente con recomendaciones diversificadas)
                    final_response.update({
                        "recommendations": recommendations_to_use,
                        "ai_response": cached_personalization.get("personalized_response", final_response["ai_response"]),
                        "metadata": {
                            **final_response["metadata"],
                            "personalization_applied": True,
                            "strategy_used": cached_personalization.get("personalization_metadata", {}).get("strategy_used", "cached"),
                            "personalization_score": cached_personalization.get("personalization_metadata", {}).get("personalization_score", 0.9),
                            "cache_hit": True,
                            "cache_age_seconds": cached_personalization.get("personalization_metadata", {}).get("cache_age_seconds", 0),
                            "diversification_applied": diversification_flag  # ✅ CORRECTED: Use actual diversification flag
                        }
                    })
                    
                    logger.info("✅ Cache personalization completed successfully")
                    
                else:
                    # ✅ PASO 2: Cache miss - ejecutar personalización OPTIMIZADA
                    logger.info("🧠 Applying OPTIMIZED MCP personalization (cache miss)...")
                    
                    # Personalización directa via MCPPersonalizationEngine.
                    # (claude_optimization.py fue removido — mcp_engine es el camino correcto)
                    #
                    # HISTORIAL DE TIMEOUTS:
                    # - 1.5s: optimizer deprecado — demasiado agresivo
                    # - 3.0s: calibrado para Sonnet ~1.6-1.7s (dashboards GCP)
                    #         → pero genera timeouts constantes en primera request
                    #           post-startup y en smoke tests (observado 20/03/2026)
                    # - 8.0s: valor actual
                    #
                    # POR QUÉ 8s:
                    # Los logs de producción muestran que keep-alive #2 tarda 2196ms
                    # (primera llamada post-startup) y #3 tarda 1201ms (estado caliente).
                    # generate_personalized_response hace UNA llamada a Claude con un
                    # prompt complejo (contexto + recomendaciones + historial).
                    # En el peor caso razonable (primera request, conexión semi-fría,
                    # contención de CPU durante arranque): ~4-5s.
                    # 8s cubre ese peor caso con margen sin comprometer UX — el
                    # timeout del handler HTTP de Cloud Run es 300s, por lo que 8s
                    # no causa problemas a nivel de plataforma.
                    personalization_result = await asyncio.wait_for(
                        mcp_engine.generate_personalized_response(
                            mcp_context=mcp_context,
                            recommendations=base_recommendations
                        ),
                        timeout=12.0  # ← aumentado de 8.0s (21/03/2026): los logs muestran
                                       # que Claude API tarda ~7.5s incluso con Haiku en condiciones
                                       # normales (warm TCP). Con 8.0s el margen era 0.5s — la primera
                                       # request sistemáticamente se agotaba. 12s da margen real.
                    )
                    
                    # Actualizar respuesta con datos personalizados
                    final_response.update({
                        "recommendations": personalization_result.get("personalized_recommendations", base_recommendations),
                        "ai_response": personalization_result.get("personalized_response", final_response["ai_response"]),
                        "metadata": {
                            **final_response["metadata"],
                            "personalization_applied": True,
                            "strategy_used": personalization_result.get("personalization_metadata", {}).get("strategy_used", "hybrid"),
                            "personalization_score": personalization_result.get("personalization_metadata", {}).get("personalization_score", 0.0),
                            "cache_hit": False,
                            "diversification_applied": diversification_flag  # ✅ CORRECTED: Use actual diversification flag
                        }
                    })
                    
                    # ✅ PHASE 2 FIX: NO crear ConversationTurn aquí - delegado al router
                    # Los recommendation IDs se retornarán en metadata para el router
                    if mcp_context:
                        try:
                            # Solo extraer IDs - el router creará el turn único
                            new_recommendation_ids = [rec.get('id') for rec in final_response["recommendations"] if rec.get('id')]
                            
                            # ✅ CRÍTICO: Agregar recommendation_ids a metadata para el router
                            final_response["metadata"]["recommendation_ids"] = new_recommendation_ids
                            final_response["metadata"]["session_context"] = {
                                "session_id": actual_session_id,
                                "total_turns_before": mcp_context.total_turns,
                                "next_turn_number": mcp_context.total_turns + 1
                            }
                            
                            logger.info(f"✅ Handler prepared {len(new_recommendation_ids)} recommendation IDs for router state management")
                            
                        except Exception as state_prep_e:
                            logger.warning(f"⚠️ Failed to prepare recommendation IDs for router: {state_prep_e}")
                            final_response["metadata"]["recommendation_ids"] = []
                    
                    # ✅ PASO 3: Cachear resultado para futuras requests
                    await personalization_cache.cache_personalization_response(
                        user_id=validated_user_id,
                        query=conversation_query,
                        context=cache_context,
                        response=personalization_result,
                        ttl=300  # 5 minutos
                    )
                    
                    logger.info("✅ MCP personalization completed and cached successfully")
                    
            except asyncio.TimeoutError:
                logger.warning("⏰ MCP personalization timeout (8.0s) - using base recommendations")
                # NOTA: Si este mensaje aparece en logs, significa que generate_personalized_response
                # tardó más de 8s. El ParallelTask de mcp_recommendations tiene timeout=10s
                # y el de personalization=5s. Si cualquiera de ellos expira antes, este
                # bloque NO se ejecuta — en ese caso ver logs de parallel_processor.
                final_response["metadata"]["personalization_timeout"] = True
                final_response["metadata"]["timeout_reason"] = "Claude API call exceeded 8.0s limit"
                final_response["metadata"]["optimization_attempted"] = True
            except Exception as e:
                logger.error(f"❌ Error in MCP personalization: {e}")
                final_response["metadata"]["personalization_error"] = str(e)[:100]

        # ===== FASE 5: APLICAR ADAPTACIÓN DE MERCADO =====
        if market_adapter and final_response["recommendations"]:
            try:
                logger.info("🌍 Applying market adaptation...")
                adapted_recommendations = []
                for rec in final_response["recommendations"]:
                    try:
                        adapted_rec = await market_adapter.adapt_product(rec, market_id)
                        adapted_recommendations.append(adapted_rec)
                    except Exception as e:
                        logger.warning(f"⚠️ Market adaptation failed for product {rec.get('id', 'unknown')}: {e}")
                        adapted_recommendations.append(rec)  # Use original if adaptation fails
                
                final_response["recommendations"] = adapted_recommendations
                final_response["metadata"]["market_adaptation_applied"] = True
                logger.info(f"✅ Market adaptation applied to {len(adapted_recommendations)} recommendations")
                
            except Exception as e:
                logger.warning(f"⚠️ Market adaptation error: {e}")
                final_response["metadata"]["market_adaptation_error"] = str(e)[:100]

        # ===== FINALIZACIÓN =====
        final_processing_time = (time.time() - start_time) * 1000
        final_response["metadata"]["processing_time_ms"] = final_processing_time
        
        # Calcular mejora de performance vs procesamiento secuencial
        estimated_sequential_time = (
            5000 +  # Base recommendations: ~5s
            4000 +  # MCP engine preparation: ~4s
            1000    # Market adapter: ~1s
        )  # Total secuencial estimado: ~10s
        
        time_saved = max(0, estimated_sequential_time - final_processing_time)
        performance_improvement = (time_saved / estimated_sequential_time) * 100 if estimated_sequential_time > 0 else 0
        
        final_response["metadata"]["performance_metrics"] = {
            "estimated_sequential_time_ms": estimated_sequential_time,
            "actual_parallel_time_ms": final_processing_time,
            "time_saved_ms": time_saved,
            "performance_improvement_percent": performance_improvement
        }
        
        logger.info(f"✅ PARALLEL MCP conversation flow completed in {final_processing_time:.2f}ms")
        logger.info(f"📊 Performance improvement: {performance_improvement:.1f}% ({time_saved:.0f}ms saved)")
        return final_response

    except Exception as e:
        logger.error(f"❌ Critical error in parallel MCP conversation flow: {e}")
        
        # Emergency fallback
        return {
            "recommendations": [],
            "ai_response": f"I apologize, but I encountered an error processing your request: '{conversation_query}'. Please try again.",
            "metadata": {
                "error": str(e)[:200],
                "fallback_used": "emergency",
                "processing_time_ms": (time.time() - start_time) * 1000,
                "market_id": market_id,
                "parallel_processing_attempted": True
            }
        }


async def get_mcp_market_recommendations(
    product_id: str,
    market_id: str,
    user_id: str,
    n_recommendations: int = 5,
    session_id: Optional[str] = None,  # ✅ NUEVO parámetro
    language: Optional[str] = "es"
) -> Dict[str, Any]:
    """
    Función auxiliar para el endpoint de recomendaciones por mercado.
    Usa el mismo flujo arquitectónico paralelo.
    
    Obtiene recomendaciones de mercado con personalización MCP
    
    ✅ MEJORADO: Acepta session_id para contexto conversacional

    Args:
        product_id: ID del producto base
        market_id: ID del mercado
        user_id: ID del usuario
        n_recommendations: Número de recomendaciones
        session_id: ID de sesión para contexto conversacional (opcional)
        language: Idioma para respuestas (es, en, etc.)  # ✅ NUEVO
        
    Returns:
        Dict con recomendaciones adaptadas al mercado usando parallel processing
    """

    # ✅ USAR session_id si se provee, como por ejemplo desde mcp_router
    # if session_id:
    #     logger.info(f"Using provided session_id: {session_id}")
    # else:
    #     session_id = f"market_rec_{user_id}_{int(time.time())}"
    #     logger.info(f"Generated new session_id: {session_id}")

    return await get_mcp_conversation_recommendations(
        validated_user_id=user_id,
        validated_product_id=product_id,
        conversation_query=f"Show me products similar to {product_id}",
        market_id=market_id,
        n_recommendations=n_recommendations,
        session_id=session_id,
        language=language
    )


# ===== FUNCIONES DE UTILIDAD =====

def validate_mcp_dependencies() -> Dict[str, Any]:
    """
    Valida que todas las dependencias MCP estén disponibles.
    Incluye validación de parallel_processor.
    
    Returns:
        Dict con el estado de cada dependencia
    """
    dependencies_status = {
        "hybrid_recommender": False,
        "mcp_context_classes": False,
        "mcp_personalization_engine": False,
        "market_adapter": False,
        "anthropic_api_key": False,
        "parallel_processor": False  # ✅ NUEVO
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
    
    try:
        from src.api.core.parallel_processor import parallel_processor
        dependencies_status["parallel_processor"] = True
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
    Información sobre la implementación de la arquitectura MCP con parallel processing.
    
    Returns:
        Dict con información arquitectónica actualizada
    """
    return {
        "architecture_version": "parallel_processing_implemented",
        "implementation_date": "2025-09-01",
        "pattern": "ParallelProcessor → HybridRecommender + MCPPersonalizationEngine → MarketAdapter",
        "resolved_issues": [
            "MCPPersonalizationEngine get_recommendations() method not found",
            "MCP personalization timeout warnings",
            "Sequential processing performance bottlenecks"
        ],
        "components": {
            "parallel_base_recommendations": "HybridRecommender.get_recommendations() [PARALLEL]",
            "parallel_engine_preparation": "MCPPersonalizationEngine setup [PARALLEL]", 
            "parallel_market_preparation": "MarketAdapter setup [PARALLEL]",
            "sequential_personalization": "MCPPersonalizationEngine.generate_personalized_response()",
            "sequential_market_adaptation": "MarketAdapter.adapt_product()",
            "fallbacks": "Multiple levels with graceful degradation"
        },
        "performance_targets": {
            "sequential_estimated": "~10s",
            "parallel_target": "2-3s",
            "improvement_goal": "60-70%",
            "personalization_timeout": "3s (reduced from 7s)"
        },
        "parallel_processor_integration": {
            "tasks_parallelized": 3,
            "priority_levels": 3,
            "timeout_management": "granular per task",
            "metrics_tracking": "execution_time, efficiency, time_saved"
        }
    }


async def get_parallel_processing_metrics() -> Dict[str, Any]:
    """
    ✅ NUEVO: Obtiene métricas específicas del parallel processing en MCP operations.
    
    Returns:
        Dict con métricas de performance del procesamiento paralelo
    """
    try:
        from src.api.core.parallel_processor import get_parallel_metrics
        base_metrics = get_parallel_metrics()
        
        return {
            "parallel_processor_metrics": base_metrics,
            "mcp_specific_info": {
                "operations_parallelized": [
                    "base_recommendations_fetch",
                    "mcp_engine_preparation", 
                    "market_adapter_preparation"
                ],
                "estimated_time_savings": "60-70% improvement",
                "timeout_prevention": "Reduces personalization timeouts significantly"
            },
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "error": f"Failed to get parallel metrics: {e}",
            "timestamp": time.time()
        }
