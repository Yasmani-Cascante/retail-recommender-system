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
    language: Optional[str] = "es",  # Idioma para KB y personalizacion
    customer_id: Optional[str] = None,  # F-04: ID del cliente Shopify logueado
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
        # F-07 / Paso 3 (06/04/2026): session_id siempre viene desde el router,
        # que a su vez lo toma de conversation.session_id (enviado por el widget).
        # El widget genera un session_id estable en el constructor de ConversationAPI
        # y lo envia en CADA request, lo actualiza al recibirlo en la respuesta.
        # Si no viene (curl de test sin session_id), se genera un fallback con
        # timestamp para que no colisionen sesiones de usuarios diferentes.
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

            # ── F-04: Lazy fetch del perfil de cliente (04/04/2026) ────────────────
            # customer_id llega desde mcp_router.py, que lo extrae de
            # widget_context["customer_id"] (inyectado por Shopify Liquid en
            # theme.liquid: data-customer-id="{{ customer.id }}").
            #
            # Flujo:
            #   customer_id presente  → CustomerProfileService.get_profile()
            #     cache hit  (~1ms)   → retorna perfil Redis
            #     cache miss (~300ms) → fetch Shopify REST + guarda en Redis
            #   customer_id ausente   → None (usuario anonimo, sin cambios)
            #
            # El perfil se guarda en mcp_context.customer_profile.
            # MCPPersonalizationEngine lo usa para adaptar el tono de Claude
            # segun el LTV tier (new/returning/loyal/vip) y las categorias
            # preferidas del cliente.
            if customer_id:
                try:
                    from src.api.factories.service_factory import ServiceFactory
                    _cps = await ServiceFactory.get_customer_profile_service()
                    _profile = await _cps.get_profile(str(customer_id))
                    if _profile:
                        mcp_context.customer_profile = _profile
                        # NOTA: Este archivo usa logging estandar (no structlog),
                        # por lo que los kwargs deben ir dentro del mensaje f-string.
                        # structlog acepta kwargs arbitrarios; logging.Logger._log() no.
                        logger.info(
                            f"customer_profile_injected "
                            f"customer_id={customer_id} "
                            f"ltv_tier={_profile.get('ltv_tier')} "
                            f"preferred_categories={_profile.get('preferred_categories', [])}"
                        )
                    else:
                        logger.info(
                            f"customer_profile_not_found customer_id={customer_id}"
                        )
                except Exception as _cp_err:
                    # Degradacion graceful: si falla el fetch, el chat sigue
                    # funcionando sin personalizacion de historial.
                    logger.warning(
                        f"F-04 customer profile fetch failed (graceful degradation): {_cp_err}"
                    )
            # ── Fin F-04 ─────────────────────────────────────────────────────

            # ── F-01: Lazy fetch del contexto del producto actual (04/04/2026) ─────
            # validated_product_id llega desde mcp_router.py, que lo extrae de
            # widget_context["product_id"]. extractProductId() en api.ts lo
            # obtiene del path /products/{handle} de la URL actual.
            #
            # El handle es un string slug (ej. "camisa-azul"), NO un ID numérico.
            # ProductContextService.get_product_context() resuelve esta
            # diferencia internamente con GET /products.json?handle=.
            #
            # Condición de activación:
            #   validated_product_id presente  → el usuario está en página de
            #                                    producto (page_type='product')
            #   page_type check NO es necesario aquí porque validated_product_id
            #   solo se popula cuando extractProductId() encuentra el slug en la
            #   URL, lo que solo ocurre en rutas /products/*.
            #
            # Flujo:
            #   cache hit  (~1ms)   → retorna dict Redis
            #   cache miss (~400ms) → 2x fetch Shopify REST + guarda en Redis
            #   fallo               → None (graceful degradation, chat sigue OK)
            #
            # El contexto se guarda en mcp_context.current_product_context.
            # MCPPersonalizationEngine lo usa para construir el prompt de upsell.

            # Yo: Validación adicional para debugging — log explícito del product_id recibido
            if validated_product_id:
                try:
                    from src.api.factories.service_factory import ServiceFactory
                    _pcs = await ServiceFactory.get_product_context_service()
          
                    if _pcs:
                        _product_ctx = await _pcs.get_product_context(
                            handle=validated_product_id,
                            market_id=market_id,
                        )

                        if _product_ctx:
                            mcp_context.current_product_context = _product_ctx
                            logger.info(
                                f"F-01 product_context_injected "
                                f"handle={validated_product_id} "
                                f"product_id={_product_ctx.get('id')} "
                                f"title='{_product_ctx.get('title')}' "
                                f"type='{_product_ctx.get('product_type')}' "
                                f"collections={_product_ctx.get('collections', [])}"
                            )
                        else:
                            logger.info(
                                f"F-01 product_context_not_found "
                                f"handle={validated_product_id}"
                            )
                    else:
                        logger.info(
                            "F-01 ProductContextService not available "
                            "(graceful degradation)"
                        )
                except Exception as _pce:
                # Degradacion graceful: si falla el fetch de producto,
                # el chat sigue funcionando sin contexto de upsell.
                    logger.warning(
                        f"F-01 product context fetch failed "
                        f"(graceful degradation): {_pce}"
                    )
            # ── Fin F-01 ──────────────────────────────────────────────────────────
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
            # FIX (24/03/2026 — SEGUNDA ITERACIÓN): get_settings() usa @lru_cache().
            # La instancia se congela durante el startup de FastAPI, antes de que
            # Cloud Run inyecte todos los secrets/env vars (incluido ENABLE_INTENT_DETECTION).
            # Resultado: @lru_cache devuelve enable_intent_detection=False aunque
            # os.environ contenga 'true' — confirmado en GCP Logs revision 00073-xhd:
            #   "enable_intent_detection=False (from settings, env raw='true')"
            #
            # SOLUCIÓN: Crear una instancia fresca de RecommenderSettings() en el
            # momento de cada request. Pydantic-settings lee os.environ en __init__,
            # garantizando que lee el valor actual del entorno, no el valor cacheado
            # del startup. Overhead: <1ms (la clase es ligera, sin I/O).
            #
            # ALTERNATIVA DESCARTADA: invalidar el cache con get_settings.cache_clear()
            # en el lifespan — más complejo y con side effects en otros módulos que
            # también usan get_settings(). La instancia local es el fix más seguro.

            # FIX (24/03/2026 — TERCERA ITERACIÓN): Diagnóstico demostró que
            # pydantic-settings v2 con case_sensitive=True NO resuelve correctamente
            # el alias env='ENABLE_INTENT_DETECTION' cuando el nombre del campo Python
            # es lowercase ('enable_intent_detection'). Con case_sensitive=True,
            # pydantic-settings busca literalmente 'enable_intent_detection' (lowercase)
            # en os.environ, pero Cloud Run inyecta 'ENABLE_INTENT_DETECTION' (uppercase).
            # El Field(env='ENABLE_INTENT_DETECTION') NO sobreescribe este comportamiento
            # de forma fiable en todas las versiones de pydantic-settings v2.
            #
            # EVIDENCIA (GCP Logs revision 00074-q2f, con RecommenderSettings() ya aplicado):
            #   "enable_intent_detection=False (from settings, env raw='true')"
            # → RecommenderSettings() (sin caché) también devuelve False.
            # → La causa NO era @lru_cache, era case_sensitive=True + mismatch de casing.
            #
            # SOLUCIÓN DEFINITIVA: Leer os.environ directamente, sin pasar por Pydantic.
            # os.environ es la fuente de verdad — no tiene problemas de case sensitivity.
            # Overhead: 0ms (acceso a dict en memoria).
            #
            # Para los demás parámetros (threshold, etc.) seguimos usando settings,
            # pero enable_intent_detection es el único flag que fallaba.
            intent_enabled = os.environ.get('ENABLE_INTENT_DETECTION', 'false').lower() in ('true', '1', 'yes')
            ml_intent_enabled = os.environ.get('ML_INTENT_ENABLED', 'false').lower() in ('true', '1', 'yes')

            # Leer el resto de settings normalmente para threshold y otros valores
            from src.api.core.config import get_settings
            settings = get_settings()

            # Log explícito del valor leído — visible en GCP Logs con LOG_LEVEL=INFO
            logger.info(f"🔍 INTENT DETECTION: enable_intent_detection={intent_enabled} "
                        f"(direct os.environ read, raw='{os.environ.get('ENABLE_INTENT_DETECTION', 'NOT_SET')}')")
            
            logger.info(f"🔍 ML INTENT DETECTION: ml_intent_enabled={ml_intent_enabled} "
                    f"(direct os.environ read, raw='{os.environ.get('ML_INTENT_ENABLED', 'NOT_SET')}')")
            
            if intent_enabled:
                # ✅ NUEVO: Verificar si ML está habilitado
                # ml_enabled = getattr(settings, 'ml_intent_enabled', False)
                # logger.info(f"🔍 ML INTENT ENABLED: ml_enabled={ml_enabled} "
                #             f"(from settings, raw='{getattr(settings, 'ml_intent_enabled', 'NOT_SET')}')")
                
                if ml_intent_enabled:
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
                            logger.info("✅ Knowledge Base answer found - checking for query specificity")

                            # ══════════════════════════════════════════════════════════════
                            # BUG #1 FIX (25/03/2026): Contextualise KB responses for
                            # queries that contain named entities or specific constraints.
                            #
                            # WHY: The KB stores one generic document per sub_intent.  Two
                            # queries that share sub_intent=policy_payment hit the SAME
                            # document regardless of specificity:
                            #   "¿Qué métodos de pago aceptan?"   → generic  → doc OK
                            #   "¿Puedo pagar con Mastercard?"     → specific → doc generic
                            # The second case needs Claude to answer the actual question
                            # ("does this store accept Mastercard?") using the document
                            # as a knowledge source, not just dump the whole document.
                            #
                            # HOW:
                            #   1. has_specific_entities() — rule-based regex check, <1ms,
                            #      returns True if the query names a brand/provider/metric.
                            #   2. If True → generate_contextual_answer() — Haiku call,
                            #      ~300-700ms, answers the specific question in 2-3 sentences.
                            #   3. If False or Claude fails → kb_answer.answer returned
                            #      verbatim (same as before, zero regressions).
                            #
                            # COST: ~$0.025/day (see kb_contextualizer.py module docstring).
                            # LATENCY: Only on specific queries (~20-30% of INFORMATIONAL).
                            # ══════════════════════════════════════════════════════════════
                            from src.api.core.kb_contextualizer import (
                                has_specific_entities,
                                generate_contextual_answer,
                            )

                            # Decide whether the query needs contextualisation
                            needs_contextualisation = has_specific_entities(
                                query=conversation_query,
                                sub_intent=intent_result.sub_intent,
                            )

                            if needs_contextualisation:
                                logger.info(
                                    "🎯 Query has specific entities — contextualising KB answer via Claude "
                                    "(sub_intent=%s, query='%s')",
                                    intent_result.sub_intent,
                                    conversation_query[:60],
                                )
                                # Try to get the Anthropic client from the warm MCP engine singleton
                                try:
                                    from src.api.factories.service_factory import ServiceFactory
                                    mcp_engine_for_kb = await ServiceFactory.get_mcp_recommender()
                                    anthropic_client_for_kb = getattr(mcp_engine_for_kb, 'claude', None) if mcp_engine_for_kb else None
                                except Exception:
                                    anthropic_client_for_kb = None

                                contextual_answer = await generate_contextual_answer(
                                    query=conversation_query,
                                    kb_document=kb_answer.answer,
                                    sub_intent=intent_result.sub_intent,
                                    language=language,
                                    anthropic_client=anthropic_client_for_kb,
                                )

                                if contextual_answer:
                                    # Claude generated a specific answer — use it
                                    final_answer = contextual_answer
                                    contextualised = True
                                    logger.info("✅ KB answer contextualised successfully")
                                else:
                                    # Claude failed or timed out — fall back to generic document
                                    final_answer = kb_answer.answer
                                    contextualised = False
                                    logger.warning(
                                        "⚠️ KB contextualisation failed — returning generic KB document"
                                    )
                            else:
                                # Generic query — return document directly (zero latency, zero cost)
                                final_answer = kb_answer.answer
                                contextualised = False
                                logger.info("📄 Generic query — returning KB document as-is")

                            return {
                                "type": "informational",
                                # answer   → always the primary text the frontend should display.
                                #            · Generic query:      full KB document.
                                #            · Specific query:     Claude's focused answer (2-3 sentences).
                                # ai_response → alias of answer (kept for backward compatibility).
                                # kb_document → always the full KB source document.
                                #               Present on both branches so the frontend can always
                                #               offer a "view full policy" option regardless of
                                #               whether contextualisation happened.
                                "answer": final_answer,
                                "ai_response": final_answer,
                                **({"kb_document": kb_answer.answer} if needs_contextualisation else {}),
                                "recommendations": [],  # NO products for informational queries
                                "metadata": {
                                    "intent_detection": {
                                        "primary_intent": intent_result.primary_intent,
                                        "sub_intent": intent_result.sub_intent,
                                        "confidence": intent_result.confidence,
                                        "reasoning": intent_result.reasoning,
                                        "matched_patterns": intent_result.matched_patterns,
                                        "method_used": getattr(hybrid_result, 'method_used', 'rule_based') if ml_intent_enabled else 'rule_based'
                                    },
                                    "knowledge_base_used": True,
                                    "kb_contextualised": contextualised,
                                    "kb_had_specific_entities": needs_contextualisation,
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
                    
                    # GREETING → Return warm conversational response, NO products
                    # FIX (25/03/2026 — BUG #3): "Hi!" / "Hola" were falling through
                    # to the TRANSACTIONAL default because greetings are not questions
                    # and the old code had no GREETING branch here. Result: the user
                    # received a dump of random products with no greeting at all.
                    #
                    # The _detect_greeting() in intent_detection.py already returns
                    # GREETING with confidence=0.95, which is above the threshold (0.7),
                    # so we land here. We return a short template response immediately
                    # (no Claude call → zero latency hit for a simple greeting).
                    # The template is bilingual: 'es' for Spanish markets, 'en' otherwise.
                    elif intent_result.primary_intent == IntentType.GREETING:
                        logger.info("👋 GREETING intent detected - returning conversational response (no products)")

                        # Bilingual greeting templates. No Claude call needed:
                        # the message is fixed, short, and market-appropriate.
                        # Normalise language code: 'en-US' → 'en', 'es-MX' → 'es'.
                        lang_key = (language or "es").split("-")[0].lower()
                        greeting_templates = {
                            "es": (
                                "¡Hola! Bienvenido/a a nuestra tienda. "
                                "¿En qué puedo ayudarte hoy? Puedo mostrarte productos, "
                                "o responder preguntas sobre envíos, pagos o devoluciones."
                            ),
                            "en": (
                                "Hello! Welcome to our store. "
                                "How can I help you today? I can show you products "
                                "or answer questions about shipping, payments, or returns."
                            ),
                        }
                        greeting_text = greeting_templates.get(lang_key, greeting_templates["es"])

                        logger.info("✅ GREETING response ready — returning early without products")
                        return {
                            "type": "greeting",
                            "answer": greeting_text,
                            "ai_response": greeting_text,
                            "recommendations": [],  # No products for a greeting
                            "metadata": {
                                "intent_detection": {
                                    "primary_intent": intent_result.primary_intent,
                                    "sub_intent": intent_result.sub_intent,
                                    "confidence": intent_result.confidence,
                                    "reasoning": intent_result.reasoning,
                                    "matched_patterns": intent_result.matched_patterns,
                                    "method_used": "rule_based",
                                },
                                "knowledge_base_used": False,
                                "processing_time_ms": (time.time() - start_time) * 1000,
                                "market_id": market_id,
                                "session_id": actual_session_id,
                            },
                        }

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
                    
                    # Standard recommendations (primera llamada o fallback).
                    #
                    # F-01 (06/04/2026): Resolucion de product_id para el TF-IDF.
                    # validated_product_id es el HANDLE (slug de URL, ej. "vestido-azul")
                    # que llega desde widget_context["product_id"] via extractProductId().
                    # El TF-IDF indexa productos por ID NUMERICO (ej. "9978786152757"),
                    # no por handle — por eso aparecia:
                    #   WARNING: Producto ID vestido-azul no encontrado
                    # y el TF-IDF devolvía 0 recomendaciones por contenido.
                    #
                    # Fix: si mcp_context ya tiene current_product_context (inyectado
                    # por F-01 unas lineas mas arriba), usamos su ID numerico.
                    # Si no, mantenemos validated_product_id como estaba (no regresion).
                    tfidf_product_id = validated_product_id  # default: handle o None
                    if (
                        mcp_context
                        and hasattr(mcp_context, "current_product_context")
                        and mcp_context.current_product_context
                        and mcp_context.current_product_context.get("id")
                    ):
                        tfidf_product_id = mcp_context.current_product_context["id"]
                        logger.info(
                            f"F-01 TF-IDF product_id resolved: "
                            f"handle={validated_product_id!r} → "
                            f"numeric_id={tfidf_product_id!r}"
                        )

                    recommendations = await main_unified_redis.hybrid_recommender.get_recommendations(
                        user_id=validated_user_id,
                        product_id=tfidf_product_id,
                        n_recommendations=n_recommendations,
                        user_query=conversation_query  # ✨ NUEVO: Permite detección de categoría desde query
                    )
                    logger.info(f"✅ Base recommendations obtained: {len(recommendations)} items")

                    # ── F-01 Mejora: Reranking por colección del producto actual ──────────────────
                    # Si el usuario está viendo un producto con colecciones conocidas
                    # (ej. ["Vestidos cortos", "Fiesta"]), subimos en el ranking
                    # los productos recomendados que también pertenecen a esas
                    # colecciones. Esto hace el upsell más coherente: primero
                    # aparecen productos de la misma colección, luego el resto.
                    #
                    # Diseño del boost:
                    #   - Leemos current_product_context.collections (ya inyectado por F-01)
                    #   - Para cada recomendación, buscamos su product_data en el
                    #     id_index del TF-IDF (O(1) tras la mejora de latencia)
                    #   - Si el producto tiene una colección en común con el producto
                    #     actual, añadimos COLLECTION_BOOST a su similarity_score
                    #   - Reordenamos por score final y retornamos
                    #
                    # COLLECTION_BOOST = 0.15: valor calibrado para que un producto
                    # con score 0.75 + boost (0.90) supere a uno con score 0.85 sin
                    # boost, pero sin que boost solo eleve productos muy irrelevantes
                    # (score < 0.5 + boost = 0.65 < umbral natural).
                    COLLECTION_BOOST = 0.15

                    if (
                        mcp_context
                        and hasattr(mcp_context, "current_product_context")
                        and mcp_context.current_product_context
                    ):
                        current_collections = set(
                            c.lower()
                            for c in mcp_context.current_product_context.get("collections", [])
                        )

                        if current_collections and recommendations:
                            tfidf_recommender = getattr(
                                main_unified_redis.hybrid_recommender,
                                "content_recommender", None
                            )

                            boosted_count = 0
                            for rec in recommendations:
                                rec_product_data = None

                                # Intentar leer product_data ya incluido en el dict
                                if rec.get("product_data"):
                                    rec_product_data = rec["product_data"]
                                # Fallback: buscar en id_index del TF-IDF (O(1))
                                elif tfidf_recommender and hasattr(tfidf_recommender, "id_index"):
                                    rec_product_data = tfidf_recommender.id_index.get(
                                        str(rec.get("id", ""))
                                    )

                                if rec_product_data:
                                    # Extraer las colecciones del producto recomendado.
                                    # En product_data del TF-IDF las colecciones pueden
                                    # venir como string CSV o lista (dependiendo del
                                    # enrichment del startup). Normalizamos ambos casos.
                                    raw_rec_cols = rec_product_data.get("collections") or []
                                    if isinstance(raw_rec_cols, str):
                                        raw_rec_cols = [
                                            c.strip()
                                            for c in raw_rec_cols.split(",")
                                            if c.strip()
                                        ]
                                    rec_collections = set(c.lower() for c in raw_rec_cols)

                                    if current_collections & rec_collections:  # intersección
                                        # Boost: añadir directamente al similarity_score
                                        old_score = rec.get("similarity_score", rec.get("score", 0.5))
                                        new_score = min(1.0, old_score + COLLECTION_BOOST)
                                        rec["similarity_score"] = new_score
                                        rec["score"] = new_score
                                        rec["collection_boosted"] = True
                                        boosted_count += 1

                            if boosted_count > 0:
                                # Reordenar por score actualizado
                                recommendations = sorted(
                                    recommendations,
                                    key=lambda r: r.get("similarity_score", r.get("score", 0)),
                                    reverse=True
                                )
                                logger.info(
                                    f"F-01 collection_boost applied: "
                                    f"{boosted_count}/{len(recommendations)} recs boosted "
                                    f"(collections={list(current_collections)[:3]})"
                                )
                    # ── Fin F-01 reranking por colección ──────────────────────────────────

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
                # FIX (25/03/2026 — BUG #2 COMPLETE): Inject the current query into mcp_context
                # HERE, before any cache check, so that BOTH the cache-miss path and the
                # cache-hit path operate on the right query.
                #
                # Previous placement: only inside the `else` (cache miss) branch.
                # Problem: on a cache HIT, mcp_context.current_query was never set,
                # so MCPPersonalizationEngine._determine_optimal_strategy() fell back to
                # mcp_context.turns[-1].user_query, which was the PREVIOUS turn's query.
                # Evidence (screenshot 25/03/2026): query="Cuales son los Metodos de Pagos"
                # returned a response referencing "Hi!" (the prior turn's query).
                if mcp_context is not None:
                    mcp_context.current_query = conversation_query  # type: ignore[attr-defined]
                    logger.info(f"🎯 BUG#2 FIX: current_query set on mcp_context BEFORE cache check: '{conversation_query[:50]}...'")

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

                    # F-07 FIX (04/04/2026): Extraer recommendation IDs en el path
                    # de cache HIT.
                    # PROBLEMA: Solo el path de cache MISS extraia los IDs y los
                    # guardaba en metadata["recommendation_ids"]. El path de cache HIT
                    # nunca lo hacia, por lo que el router recibia 0 IDs y los turns
                    # se guardaban vacios en Redis. Esto hacia que F-07 (historial
                    # multi-turno) nunca tuviera datos para construir el contexto.
                    # SOLUCION: Extraer los IDs aqui, exactamente igual que en el
                    # path de cache MISS.
                    if mcp_context:
                        cache_hit_rec_ids = [
                            rec.get('id')
                            for rec in final_response.get("recommendations", [])
                            if rec.get('id')
                        ]
                        final_response["metadata"]["recommendation_ids"] = cache_hit_rec_ids
                        final_response["metadata"]["session_context"] = {
                            "session_id": actual_session_id,
                            "total_turns_before": mcp_context.total_turns,
                            "next_turn_number": mcp_context.total_turns + 1,
                        }
                        logger.info(
                            f"✅ F-07 FIX: cache-hit path extracted "
                            f"{len(cache_hit_rec_ids)} recommendation IDs for router"
                        )
                    
                else:
                    # ✅ PASO 2: Cache miss - ejecutar personalización OPTIMIZADA
                    logger.info("🧠 Applying OPTIMIZED MCP personalization (cache miss)...")

                    # current_query already injected above (before cache check).
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
