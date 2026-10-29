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
import re
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


# ── F-08: Detector de intención de similitud visual ─────────────────────────
# Activa la búsqueda visual en Turn 1 cuando el usuario pide productos
# similares al producto que está viendo (product_ctx con image_url disponible).
# Diseño: regex simple y rápido (<0.1ms) — sin IO, sin dependencias externas.
_F08_VISUAL_SIMILARITY_RE = re.compile(
    # FIX (16/06/2026 — FR/DE/IT visual similarity): El patrón original
    # solo cubría ES/EN. La variante francesa "similaires" difiere de
    # "similares" ES en la posición 6 ('i' vs 'r'), por lo que NINGUNA
    # query FR activaba F-08A ni F-08C.
    # Consultas fallidas antes del fix:
    #   "Voir des produits similaires"           → False (Turn 16 → 0 recs)
    #   "Voir des articles similaires"           → False (Turn 10 → 0 recs)
    #   "Montrez-moi des produits similaires"    → False (smart_fallback en lugar de FAISS)
    # Cobertura del patrón corregido:
    #   similar(?:es)?  → ES/EN: similar, similares
    #   similaires?     → FR: similaire, similaires
    #   simil[ei]\w*    → IT: simile, simili (y variantes)
    #   parecido[sa]?   → ES: parecido, parecida, parecidos
    #   como\s+este/a   → ES
    #   like\s+this     → EN
    r'\b('
    r'similar(?:es)?'
    r'|similaires?'
    r'|simil[ei]\w*'
    r'|parecido[sa]?'
    r'|como\s+este'
    r'|como\s+esta'
    r'|like\s+this'
    r')',
    re.IGNORECASE,
)


def _is_visual_similarity_query(query: str) -> bool:
    """
    Devuelve True si la query expresa una petición de similitud visual.

    Usado por F-08 Fase A (Turn 1) y Fase C (Turn 2+) para decidir si
    activar la búsqueda FAISS/FashionSigLIP en lugar del smart_fallback.

    Patrones activadores (ES/EN/FR/IT):
      - "similar(es)"   → ES/EN: productos similares a este
      - "similaires?"   → FR: produits similaires / produit similaire
      - "simil[ei]"     → IT: simile, simili
      - "parecido(s/a)" → ES: parecidos a este
      - "como este/a"   → ES: como este producto
      - "like this"     → EN
    """
    if not query:
        return False
    return bool(_F08_VISUAL_SIMILARITY_RE.search(query))


async def get_mcp_conversation_recommendations(
    validated_user_id: str,
    validated_product_id: Optional[str],
    conversation_query: str,
    market_id: str,
    n_recommendations: int = 8,  # FIX (20/04/2026): 5 → 8 para consistencia con router
    session_id: Optional[str] = None,
    language: Optional[str] = "es",  # Idioma para KB y personalizacion
    customer_id: Optional[str] = None,  # F-04: ID del cliente Shopify logueado
    reset_category: Optional[str] = None,  # 16/10/2026: turno que viene de "ver X otra vez"
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

            # ── F-02: Lazy fetch del perfil de tallas del cliente (11/04/2026) ────
            # Solo activo cuando hay customer_id (usuario logueado) Y hay producto
            # actual (validated_product_id presente). Sin producto actual no hay
            # variantes que comparar, por lo que el perfil de tallas no tiene
            # utilidad inmediata.
            #
            # Flujo:
            #   cache hit  (~1ms)    -> SizeProfile desde Redis (TTL 24h)
            #   cache miss (~600ms)  -> GET /orders.json?customer_id=... (ultimo 10 ordenes)
            #                          Extrae tallas de variant.selected_options
            #                          Guarda en Redis
            #   fallo / sin datos    -> None (degradacion graceful, chat sigue OK)
            #
            # El perfil se guarda en mcp_context.size_profile.
            # MCPPersonalizationEngine lo usa en _build_sizing_context() para
            # enriquecer el prompt cuando el intent es product_sizing.
            if customer_id and validated_product_id:
                try:
                    from src.api.factories.service_factory import ServiceFactory
                    _sps = await ServiceFactory.get_size_profile_service()
                    if _sps:
                        _size_profile = await _sps.get_size_profile(str(customer_id))
                        if _size_profile and _size_profile.has_data():
                            mcp_context.size_profile = _size_profile
                            # Construir resumen de confidencias por categoria para el log
                            conf_summary = {
                                cat: f"{size}({int(_size_profile.confidence_by_category.get(cat, 0)*100)}%)"
                                for cat, size in _size_profile.size_by_category.items()
                            }
                            logger.info(
                                f"F-02 size_profile_injected "
                                f"customer_id={customer_id} "
                                f"most_common_size={_size_profile.most_common_size} "
                                f"confidence_global={_size_profile.confidence:.2f} "
                                f"orders_analyzed={_size_profile.orders_analyzed} "
                                f"by_category={conf_summary}"
                            )
                        else:
                            logger.info(
                                f"F-02 size_profile_empty_or_insufficient "
                                f"customer_id={customer_id}"
                            )
                    else:
                        logger.info(
                            "F-02 SizeProfileService not available (graceful degradation)"
                        )
                except Exception as _spe:
                    logger.warning(
                        f"F-02 size profile fetch failed (graceful degradation): {_spe}"
                    )
            # ── Fin F-02 ──────────────────────────────────────────────────────────
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
                    
                    # FIX (15/06/2026): _detected_method captura el método ANTES de
                    # convertir hybrid_result a intent_result. getattr(intent_result,
                    # 'method', '') siempre devuelve '' porque IntentDetectionResult
                    # no tiene el campo 'method'. Esto causaba que _is_multilang_informational
                    # fuera siempre False y el threshold permaneciera en 0.7.
                    _detected_method = ""  # default; sobreescrito si el path ML tiene éxito
                    
                    try:
                        # FIX (24/03/2026): Import lazy para evitar que
                        # sklearn/joblib falle en import-time y silencie el handler.
                        from src.api.ml.hybrid_detector import get_hybrid_intent_detector
                        hybrid_detector = get_hybrid_intent_detector()
                        
                        # Detectar intent con híbrido (async)
                        hybrid_result = await hybrid_detector.detect(conversation_query, user_id=validated_user_id)
                        
                        # Guardar método ANTES de convertir (to_intent_detection_result
                        # no transfiere 'method_used' a IntentDetectionResult)
                        _detected_method = hybrid_result.method_used
                        
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
                    _detected_method = "rule_based"  # FIX (15/06/2026): inicializar para scope uniforme
                
                logger.info(f"   Detected Intent: {intent_result.primary_intent} "
                           f"(confidence: {intent_result.confidence:.2f})")
                logger.info(f"   Reasoning: {intent_result.reasoning}")
                
                # FIX (10/04/2026): El threshold de 0.7 fue disenado para INFORMATIONAL.
                # Para TRANSACTIONAL el GUARD ya garantiza que el intent es correcto.
                #
                # FIX (12/06/2026 — multilang-CH): Threshold reducido para INFORMATIONAL
                # cuando el method es ml_fallback o miniml_semantic.
                # RAZON: Las reglas rule-based solo cubren ES/EN. Un usuario CH que escribe
                # en FR, DE o IT no tiene match en rule-based → default TRANSACTIONAL 0.50.
                # El ML y MiniLM detectan INFORMATIONAL (0.52) pero cae bajo el threshold
                # 0.70 → "defaulting to products". La baja confidence NO indica ambiguedad
                # real — indica ausencia de reglas para ese idioma.
                # Cuando rule_based falla (no pattern match) y ML+MiniLM coinciden en
                # INFORMATIONAL, threshold 0.5 es correcto y seguro.
                from src.api.core.intent_types import IntentType as _IntentType
                _is_multilang_informational = (
                    intent_result.primary_intent != _IntentType.TRANSACTIONAL
                    and _detected_method in ("ml_fallback", "miniml_semantic")
                )
                _effective_threshold = (
                    0.5
                    if intent_result.primary_intent == _IntentType.TRANSACTIONAL
                    or _is_multilang_informational
                    else settings.intent_confidence_threshold
                )
                if intent_result.confidence >= _effective_threshold:
                    
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
                                logger.warning(f"Fallback hardcoded KB not available: {fallback_e}")

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

                            # F-05 (14/04/2026 — REVISADO): Forzar contextualizacion para
                            # TODA query product_availability cuando hay product_context.
                            #
                            # RACIONAL DEL CAMBIO:
                            # La version anterior condicionaba a stock_alert != None,
                            # lo que causaba experiencia inconsistente:
                            #   - romper-olivia (stock=critical) → respuesta conversacional
                            #   - midi-vestido-emma (stock=None) → documento KB estatico
                            #
                            # El problema: el nivel de stock modifica el CONTENIDO de la
                            # respuesta, no si el usuario merece una respuesta conversacional.
                            # Un usuario preguntando "¿está disponible?" SIEMPRE merece
                            # una respuesta directa, sea cual sea el nivel de stock:
                            #   - stock=critical → "Solo quedan 1-2 tallas S y M"
                            #   - stock=low      → "Quedan pocas unidades en talla L"
                            #   - stock=None     → "Sí, está disponible en tallas XS, S, M, L"
                            #   - stock agotado  → "Lamentablemente está agotado, te muestro
                            #                      opciones similares"
                            #
                            # NUEVO COMPORTAMIENTO:
                            #   Si sub_intent == "product_availability" Y hay product_context
                            #   → needs_contextualisation = True (siempre)
                            #   → generate_contextual_answer() recibe product_context
                            #   → _build_stock_alert_block() inyecta la alerta si hay
                            #   → _build_availability_context_block() (nuevo) añade info
                            #     de variantes disponibles si no hay alerta de stock
                            #
                            # Degradacion graceful:
                            #   Si current_product_context es None (usuario no en pagina
                            #   de producto), la condicion es False y se devuelve el
                            #   documento KB sin cambios (sin regresion).
                            _pctx_for_f05 = getattr(mcp_context, "current_product_context", None)
                            if (
                                not needs_contextualisation
                                and intent_result.sub_intent == "product_availability"
                                and _pctx_for_f05  # usuario en pagina de producto
                            ):
                                needs_contextualisation = True
                                _stock_alert = _pctx_for_f05.get("stock_alert")
                                _handle = _pctx_for_f05.get("handle", "?")
                                logger.info(
                                    "F-05 forcing contextualisation for product_availability "
                                    "(stock_alert=%s handle=%s)",
                                    _stock_alert or "none",
                                    _handle,
                                )

                            # FIX (21/04/2026): Forzar contextualizacion para product_material
                            # cuando hay product_context. Similar a F-05 para availability.
                            #
                            # PROBLEMA: Queries como "¿De qué material está hecho?" no tienen
                            # entidades especificas ("algodon", "seda", etc.), por lo que
                            # has_specific_entities() devuelve False y se devuelve el
                            # documento KB completo sin procesar.
                            #
                            # SOLUCION: Cuando hay product_context (usuario en pagina de
                            # producto), forzar contextualizacion para dar respuestas
                            # personalizadas sobre el material del producto actual.
                            if (
                                not needs_contextualisation
                                and intent_result.sub_intent == "product_material"
                                and _pctx_for_f05  # usuario en pagina de producto
                            ):
                                needs_contextualisation = True
                                _handle = _pctx_for_f05.get("handle", "?")
                                logger.info(
                                    "F-MATERIAL forcing contextualisation for product_material "
                                    "(handle=%s)",
                                    _handle,
                                )

                            if needs_contextualisation or intent_result.sub_intent == "product_sizing":
                                logger.info(
                                    "🎯 Query has specific entities — contextualising KB answer "
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
                                    # contexto nuevo — ambos pueden ser None (degradación graceful):
                                    size_profile=getattr(mcp_context, "size_profile", None),
                                    product_context=getattr(mcp_context, "current_product_context", None),
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
        
                                # FIX (20/04/2026): Include kb_document for product_sizing even
                                # when needs_contextualisation=False (no named entities found).
                                # The sizing KB document contains the size chart; the frontend
                                # needs it to render the "Ver guía completa de tallas" button.
                                 # **({"kb_document": kb_answer.answer} if needs_contextualisation else {}),
                                **({
                                    "kb_document": kb_answer.answer
                                } if (
                                    needs_contextualisation
                                    or intent_result.sub_intent == "product_sizing"
                                ) else {}),
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

                # REINICIO POR CATEGORIA (16/10/2026).
                # {CATEGORIA: timestamp}. Un producto deja de contar como visto
                # si su categoria tiene una marca POSTERIOR al turno que lo
                # mostro. Ver MCPConversationContext.category_resets.
                _cat_resets = dict(getattr(mcp_context, "category_resets", {}) or {}) if mcp_context else {}

                def _tipo_de(_pid: str) -> str:
                    """
                    Categoria de un producto por su id.

                    El indice se obtiene con el MISMO patron que usan F-08C y
                    Fase A (content_recommender del hybrid_recommender). Ojo:
                    `tfidf_recommender` NO existe en este ambito -- solo mas
                    abajo, dentro de la personalizacion.

                    Devuelve "" si no se puede resolver, y entonces el producto
                    se trata como visto: ante la duda, no repetir.
                    """
                    if not _cat_resets:
                        return ""
                    try:
                        # Import LOCAL a proposito: `main_unified_redis` se importa
                        # mas abajo en esta misma funcion (~linea 981), DESPUES del
                        # bucle que llama a esto. Al ser una asignacion en el
                        # ambito de la funcion, Python lo trata como local y aqui
                        # daria UnboundLocalError. Importarlo aqui lo resuelve sin
                        # depender del orden de las lineas.
                        from src.api import main_unified_redis as _mur
                        _rec = getattr(
                            getattr(_mur, "hybrid_recommender", None),
                            "content_recommender", None,
                        )
                        _idx = getattr(_rec, "id_index", None) if _rec else None
                        if not _idx:
                            return ""
                        return str((_idx.get(str(_pid)) or {}).get("product_type", ""))
                    except Exception as _tipo_err:
                        # Se registra a proposito: un fallo mudo aqui dejaria el
                        # reinicio sin efecto y nadie lo notaria.
                        logger.warning(
                            "reinicio por categoria: no se pudo resolver el tipo de %s: %s",
                            _pid, _tipo_err,
                        )
                        return ""

                def _reiniciado(_pid: str, _turn_ts: float) -> bool:
                    """True si este producto quedo fuera por un reinicio posterior."""
                    if not _cat_resets:
                        return False
                    _t = _tipo_de(_pid).upper()
                    if not _t:
                        return False
                    _marca = _cat_resets.get(_t)
                    return bool(_marca and _turn_ts and _turn_ts < _marca)
                
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
                                # REINICIO POR CATEGORIA: los productos mostrados
                                # ANTES del reinicio de su categoria no cuentan.
                                _turn_ts = float(getattr(turn, "timestamp", 0) or 0)
                                _vigentes = [r for r in recs if not _reiniciado(str(r), _turn_ts)]
                                if len(_vigentes) != len(recs):
                                    logger.info(
                                        f"    reinicio por categoria: {len(recs) - len(_vigentes)} "
                                        f"productos de este turno vuelven a estar disponibles"
                                    )
                                shown_products.update(_vigentes)
                        else:
                            logger.warning(f"    ❌ Turn {i+1} missing recommendations_provided attribute")

                        # GAP B1 (13/10/2026): el ANCLA de cada turno tambien cuenta como
                        # visto. Hasta hoy `shown_products` solo recogia lo recomendado, asi
                        # que un producto que fue ancla volvia a ser elegible en cuanto el
                        # contexto se movia a otro producto -- y el sistema se lo recomendaba
                        # de vuelta al usuario que lo tenia abierto en pantalla.
                        #
                        # Reproducido en produccion ese mismo dia (sesion de pantalones):
                        #   T1 ancla Palazzo Silvia -> T2 ancla Palazzo Ariel y RECOMIENDA
                        #   Palazzo Silvia -> T4 el usuario acaba viendo Palazzo Silvia.
                        # Con 6 pantalones en catalogo era el unico que quedaba sin mostrar.
                        #
                        # getattr con default: los turnos persistidos ANTES de este cambio no
                        # tienen el campo, y deben seguir cargandose sin ruido.
                        _turn_anchor = getattr(turn, "anchor_product_id", None)
                        if _turn_anchor:
                            # El reinicio tambien libera las ANCLAS de esa categoria
                            # (decision de Yasmani, 16/10/2026): si se vuelven a
                            # mostrar los pantalones, el que estaba mirando tambien
                            # debe volver a estar disponible.
                            _anchor_ts = float(getattr(turn, "timestamp", 0) or 0)
                            if _reiniciado(str(_turn_anchor), _anchor_ts):
                                logger.info(
                                    f"    reinicio por categoria: ancla {_turn_anchor} "
                                    f"vuelve a estar disponible"
                                )
                            else:
                                shown_products.add(str(_turn_anchor))
                                logger.info(f"    anchor_product_id (B1): {_turn_anchor}")
                        
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
                    
                    # ── F-08 Fase B: Outfit Completion ────────────────────────────────
                    # Trigger: sub_intent == OUTFIT_COMPLETION + VISUAL_SEARCH_ENABLED
                    #          + product_ctx con id disponible.
                    # Llama a search_outfit_by_image con composite embedding (alpha=0.5)
                    # para encontrar prendas que complementen visualmente el producto.
                    # Resultado: lista interleaved de categorias outfit (top, acc, bolso...).
                    # Activa en cualquier turn (Turn 1 y Turn 2+) si las condiciones se cumplen.
                    # Fallback silencioso: cualquier error retoma el flujo normal.
                    _b08_sub_intent = getattr(intent_result, "sub_intent", "") if intent_result else ""
                    if (
                        _b08_sub_intent == "outfit_completion"
                        and os.environ.get("VISUAL_SEARCH_ENABLED", "false").lower() == "true"
                        and mcp_context
                        and getattr(mcp_context, "current_product_context", None)
                        and mcp_context.current_product_context.get("id")
                    ):
                        try:
                            from src.api.routers.visual_search_router import _get_colbert_client
                            _b08_colbert = _get_colbert_client()
                            _b08_tfidf   = getattr(
                                main_unified_redis.hybrid_recommender, "content_recommender", None,
                            )
                            _b08_pid   = str(mcp_context.current_product_context["id"])
                            _b08_ptype = mcp_context.current_product_context.get("product_type", "").lower()

                            # Obtener imagen del producto desde id_index
                            _b08_image_url = None
                            if _b08_tfidf and hasattr(_b08_tfidf, "id_index"):
                                _b08_prod = _b08_tfidf.id_index.get(_b08_pid)
                                if _b08_prod:
                                    _b08_image_url = _b08_prod.get("image_url")

                            if _b08_image_url:
                                import httpx as _httpx_b08
                                async with _httpx_b08.AsyncClient(timeout=4.0) as _http_b08:
                                    _img_r = await _http_b08.get(_b08_image_url)
                                    _img_r.raise_for_status()
                                    _img_bytes_b08 = _img_r.content

                                # FIX (28/09/2026): logica de resolucion de categorias
                                # objetivo extraida a un modulo puro y testeado -- ver
                                # src/recommenders/f08b_target_categories.py para el
                                # historial completo (conflictos de slot desde 13/07/2026,
                                # excepcion accessory/bag desde 14/07/2026, auto-referencia
                                # y especificidad desde 20-21/09/2026, "conjunto" integrado
                                # 27/09/2026). Extraido como segundo incremento de la red de
                                # seguridad de tests (primer incremento: F-08B.2,
                                # 25/09/2026) -- mismo comportamiento exacto de antes, ahora
                                # cubierto por tests/unit/test_f08b_target_categories.py
                                # (13 casos).
                                from src.recommenders.f08b_target_categories import (
                                    resolve_f08b_target_categories as _b08_resolve_target_cats,
                                )
                                try:
                                    from src.recommenders.improved_fallback_exclude_seen import (
                                        extract_categories_from_query as _b08_extract_cats,
                                        get_concrete_categories as _b08_get_concrete_cats,
                                    )
                                    from src.recommenders.product_taxonomy import (
                                        get_outfit_slot as _b08_get_outfit_slot,
                                        generic_suggestion_candidate_slots as _b08_generic_slots,
                                    )
                                    (
                                        _b08_target_cats,
                                        _b08_single_specific_type,
                                        _b08_was_explicit_request,
                                    ) = _b08_resolve_target_cats(
                                        conversation_query=conversation_query,
                                        anchor_product_type=_b08_ptype,
                                        extract_categories_fn=_b08_extract_cats,
                                        get_concrete_categories_fn=_b08_get_concrete_cats,
                                        get_outfit_slot_fn=_b08_get_outfit_slot,
                                        generic_suggestion_candidate_slots_fn=_b08_generic_slots,
                                    )
                                    if _b08_was_explicit_request:
                                        logger.info(
                                            f"F-08B query category detected -> "
                                            f"{_b08_target_cats} (narrowing target_categories)"
                                            + (
                                                f", tipo especifico: {_b08_single_specific_type}"
                                                if _b08_single_specific_type else ""
                                            )
                                        )
                                except Exception as _b08_resolve_err:
                                    logger.warning(
                                        f"F-08B target category resolution failed, usando "
                                        f"fallback generico: {_b08_resolve_err}"
                                    )
                                    from src.recommenders.product_taxonomy import (
                                        generic_suggestion_candidate_slots as _b08_generic_slots,
                                    )
                                    _b08_target_cats = list(_b08_generic_slots())
                                    _b08_single_specific_type = None

                                # GAP 1 FIX (13/07/2026): _b08_shown_ids = productos ya
                                # mostrados en la sesion (shown_products, calculado mas arriba
                                # en get_base_recommendations() -- ya esta en scope aqui, mismo
                                # nivel de funcion, sin necesidad de pasarlo como parametro).
                                # Confirmado con evidencia real de produccion (13/07/2026): dos
                                # consultas genericas seguidas ("combina con esto" + "completa
                                # el look") sobre el mismo producto devolvieron exactamente los
                                # mismos 8 productos, pese a que shown_products ya los tenia
                                # registrados ("Diversification needed: True", "shown_products
                                # count: 8" en el log) -- F-08B nunca consultaba esa
                                # informacion, solo excluia el producto ancla.
                                _b08_shown_ids = {str(p) for p in shown_products}

                                # Composite embedding: alpha=0.5 (imagen y texto con igual peso)
                                # Evita que vestidos dominen todas las categorias (issue S1).
                                # top_k_per_category: 3 -> 5 (GAP 1 FIX, 13/07/2026) -> 15 (17/07/2026):
                                # dar margen para filtrar productos ya mostrados sin vaciar categorias
                                # de golpe. Los 9 prompts de categoria ya estan precalculados en el
                                # warmup (_text_embed_cache) -- pedir top_k mas alto no agrega
                                # llamadas de encoding, solo mas resultados de una busqueda FAISS
                                # que de todas formas ya ocurre (<1ms independiente de k, ver
                                # docstring de search_outfit_by_image).
                                #
                                # FIX (17/07/2026): 5 resulto insuficiente cuando el ancla es un
                                # tipo que domina su propio bucket visualmente (ej. AROS dentro de
                                # "accessory"). _b08_is_same_type() excluye correctamente mas del
                                # mismo tipo, pero si los 5 candidatos crudos de "accessory" son en
                                # su mayoria del MISMO tipo que el ancla (altamente probable --
                                # otro Aros es lo visualmente mas parecido a un Aros), casi no
                                # sobrevive nada. Confirmado en produccion (16/07/2026): ancla AROS
                                # + "que accesorios combinan" -> 1 solo producto sobreviviente de
                                # 10 candidatos crudos (5 accessory + 5 bag), dos consultas
                                # seguidas devolviendo literalmente el mismo item repetido.
                                #
                                # Por que 15 es seguro: "accessory" es ~21.2% del catalogo (no una
                                # categoria rara) -- con el search_pool interno de 150 candidatos,
                                # ceil(15/0.212)~=71, bien dentro del presupuesto. Para categorias
                                # ya de por si escasas (bag/shoes/bottom, ~2.2-2.4%), 15 supera lo
                                # que el search_pool=150 puede ofrecer de forma fiable (ya ocurria
                                # esto tambien con top_k=5, solo que de forma menos visible) -- el
                                # servidor simplemente devuelve lo que tenga disponible sin
                                # romperse, y el relleno restringido de abajo sigue cubriendo el
                                # caso de escasez real. Validar con logs reales tras el proximo
                                # deploy si 15 es suficiente o si conviene diferenciar el top_k
                                # por categoria (accessory/dress mas alto, bag/shoes mas bajo).
                                _b08_outfit = await asyncio.wait_for(
                                    _b08_colbert.search_outfit_by_image(
                                        image_bytes=_img_bytes_b08,
                                        target_categories=_b08_target_cats,
                                        top_k_per_category=15,
                                        alpha=0.5,
                                    ),
                                    timeout=5.0,
                                )

                                if _b08_outfit:
                                    # Interleave round-robin por categoria:
                                    # [top_1, acc_1, bolso_1, top_2, acc_2, ...].
                                    # Preserva outfit_category en product_data para LFM.
                                    _b08_recs  = []
                                    # FIX: search_outfit_by_image devuelve el dict completo
                                    # {"outfit":{...}, "outfit_mode":"...", "latency_ms":473.0}
                                    # Los resultados reales estan bajo la clave "outfit".
                                    # Iterar .items() directamente causaba
                                    # 'float' object is not iterable al llegar a latency_ms.
                                    _b08_outfit_cats = _b08_outfit.get("outfit", {})

                                    # FIX (21/09/2026): si la deteccion fue un tipo concreto
                                    # especifico y unico (_b08_single_specific_type), filtrar los
                                    # candidatos de cada bucket a solo ese tipo exacto. El pool
                                    # crudo que devuelve search_outfit_by_image() viene mezclado
                                    # (todo el bucket sin distincion de tipo), asi que hay que
                                    # filtrarlo aqui, antes del interleaving/boost de mas abajo.
                                    if _b08_single_specific_type and _b08_tfidf:
                                        # FIX (21/09/2026, correccion): _b08_outfit_cats[bucket] es
                                        # una lista de IDs de producto, NO de diccionarios -- el
                                        # tipo real se resuelve via _b08_tfidf.id_index (mismo
                                        # patron ya usado por el diagnostico de mas abajo,
                                        # "F-08B candidate breakdown"). La primera version de este
                                        # fix llamaba .get() directo sobre el ID (un string) y
                                        # crasheaba con "'str' object has no attribute 'get'" en
                                        # el 100% de los casos -- confirmado en produccion
                                        # (21/09/2026) para 'accessory' Y 'shoes' por igual.
                                        _b08_outfit_cats = {
                                            _b08_bk: (
                                                [
                                                    _b08_pid for _b08_pid in _b08_cl
                                                    if _b08_tfidf.id_index.get(str(_b08_pid), {})
                                                    .get("product_type", "").upper()
                                                    == _b08_single_specific_type
                                                ] if isinstance(_b08_cl, list) else _b08_cl
                                            )
                                            for _b08_bk, _b08_cl in _b08_outfit_cats.items()
                                        }
                                        logger.info(
                                            f"F-08B outfit_completion: filtrando candidatos a tipo "
                                            f"especifico '{_b08_single_specific_type}' (pedido "
                                            f"explicito, sin expandir por bucket) -- "
                                            f"{sum(len(v) for v in _b08_outfit_cats.values() if isinstance(v, list))} "
                                            f"candidatos tras filtrar"
                                        )

                                    # FASE 1B PASO 4 (23/07/2026): complementa el pool generico de
                                    # arriba con candidatos dirigidos por tipo especifico, usando
                                    # product_taxonomy.py (Paso 1) + la busqueda multi-texto
                                    # batcheada (Paso 3). Resuelve "Gap C" (documentado 03/07/2026):
                                    # search_outfit_by_image() usa un solo prompt generico por
                                    # bucket -- si la vecindad visual del ancla esta dominada por su
                                    # propio tipo, el bucket completo puede volver homogeneo
                                    # (confirmado en produccion, T3 23/07/2026: 15/15 candidatos de
                                    # "accessory" eran AROS, incluso con top_k=15 y el filtro
                                    # _b08_is_same_type() de mas abajo -- si el pool crudo entero es
                                    # del mismo tipo, no queda nada que filtrar).
                                    #
                                    # Para cada bucket target con tipos de steering_text propio (hoy:
                                    # accessory, bag -- familia ACCESSORIES), pide un candidato
                                    # dirigido por cada tipo hermano (excluyendo el propio tipo del
                                    # ancla) usando alpha_complement (0.2 -- mayormente texto, Fase 0).
                                    # Agrupado por alpha (hoy: un solo grupo, los 9 tipos comparten
                                    # 0.2) para que UNA sola llamada batcheada cubra todos los tipos
                                    # de ese grupo -- ver product_taxonomy.get_alpha() si algun tipo
                                    # necesita un alpha_complement distinto en el futuro.
                                    #
                                    # Se AGREGA a _b08_outfit_cats[bucket] (no reemplaza) -- toda la
                                    # logica de abajo (mismo-tipo, interleave por subtipo, pools
                                    # fresh/full, interleave entre buckets) opera sin cambios sobre
                                    # la lista combinada.
                                    from src.recommenders.product_taxonomy import (
                                        types_in_outfit_slot as _b08_types_in_outfit_slot,
                                        get_steering_text as _b08_get_steering_text,
                                        get_alpha as _b08_get_alpha,
                                    )
                                    _b08_own_type_upper = _b08_ptype.upper() if _b08_ptype else ""
                                    _b08_boost_groups: dict = {}  # alpha -> [(bucket, tipo, texto), ...]
                                    for _b08_bt_bucket in ([] if _b08_single_specific_type else list(_b08_outfit_cats.keys())):
                                        for _b08_bt_type in _b08_types_in_outfit_slot(_b08_bt_bucket):
                                            if _b08_bt_type == _b08_own_type_upper:
                                                continue
                                            _b08_bt_text = _b08_get_steering_text(_b08_bt_type)
                                            if not _b08_bt_text:
                                                continue
                                            _b08_bt_alpha = _b08_get_alpha(_b08_bt_type, "complement") or 0.2
                                            _b08_boost_groups.setdefault(_b08_bt_alpha, []).append(
                                                (_b08_bt_bucket, _b08_bt_type, _b08_bt_text)
                                            )

                                    for _b08_grp_alpha, _b08_grp_items in _b08_boost_groups.items():
                                        try:
                                            _b08_grp_results = await asyncio.wait_for(
                                                _b08_colbert.search_by_product_id_with_multi_text_boost(
                                                    _b08_pid,
                                                    boost_texts=[i[2] for i in _b08_grp_items],
                                                    alpha=_b08_grp_alpha,
                                                    top_k=5,
                                                ),
                                                timeout=3.0,
                                            )
                                        except Exception as _b08_grp_err:
                                            logger.debug(f"F-08B Fase 1b boost grupo alpha={_b08_grp_alpha} fallo: {_b08_grp_err}")
                                            _b08_grp_results = None

                                        if _b08_grp_results:
                                            for (_b08_g_bucket, _b08_g_type, _b08_g_text), _b08_g_ids in zip(
                                                _b08_grp_items, _b08_grp_results
                                            ):
                                                if _b08_g_ids:
                                                    _b08_outfit_cats[_b08_g_bucket] = (
                                                        _b08_outfit_cats.get(_b08_g_bucket, []) + _b08_g_ids
                                                    )
                                            logger.info(
                                                f"F-08B Fase 1b: {len(_b08_grp_items)} tipos con boost "
                                                f"dirigido (alpha={_b08_grp_alpha}) agregados a "
                                                f"{sorted(set(i[0] for i in _b08_grp_items))}"
                                            )

                                    # DIAGNOSTIC LOG (18/07/2026): desglose por tipo real de los
                                    # candidatos CRUDOS de cada bucket, ANTES de cualquier filtro
                                    # (ancla, mismo-tipo, shown_products). Mismo patron ya usado
                                    # en F-08C ("candidate breakdown", 13/07/2026) para el
                                    # problema identico. Por que: sin esto no hay forma de
                                    # confirmar con datos si un resultado pobre en variedad (ej.
                                    # "8/8 Clutch" reportado en produccion 18/07/2026 para un
                                    # ancla AROS, screenshot T5) viene de que el pool crudo de
                                    # "accessory" ya estaba dominado por AROS desde el origen
                                    # (embedding-service), o de otra causa en el filtrado
                                    # posterior (_b08_is_same_type, _b08_shown_ids). Puramente
                                    # aditivo -- no cambia ningun comportamiento, solo
                                    # visibilidad para decidir el siguiente paso con datos reales
                                    # en vez de hipotesis.
                                    for _b08_diag_cat, _b08_diag_pids in _b08_outfit_cats.items():
                                        if not isinstance(_b08_diag_pids, list) or not _b08_diag_pids:
                                            continue
                                        _b08_diag_breakdown: dict = {}
                                        for _b08_diag_pid in _b08_diag_pids:
                                            _b08_diag_type = (
                                                _b08_tfidf.id_index.get(str(_b08_diag_pid), {})
                                                .get("product_type", "").upper()
                                                if _b08_tfidf else "UNKNOWN"
                                            )
                                            _b08_diag_breakdown[_b08_diag_type] = (
                                                _b08_diag_breakdown.get(_b08_diag_type, 0) + 1
                                            )
                                        logger.info(
                                            f"F-08B candidate breakdown: bucket={_b08_diag_cat!r} "
                                            f"{_b08_diag_breakdown} "
                                            f"(anchor_type={(_b08_ptype.upper() if _b08_ptype else None)!r}, "
                                            f"total={len(_b08_diag_pids)})"
                                        )

                                    # FIX (14/07/2026): _b08_is_same_type() -- complemento del
                                    # fix de arriba (accessory/bag ya no se auto-excluyen como
                                    # bucket completo). Sin esto, un ancla AROS buscando dentro
                                    # de 'accessory' podia devolver mas AROS (visualmente lo mas
                                    # cercano a si mismo), no variedad real. Se filtra por
                                    # product_type CONCRETO (no por bucket), reusando el mismo
                                    # patron ya establecido en F-08C para el problema identico
                                    # de expansion a categorias hermanas:
                                    #   _c08_tfidf.id_index.get(str(pid), {}).get("product_type", "").upper()
                                    # Se aplica de forma universal (no solo para accessory/bag)
                                    # -- costo marginal nulo (mismo id_index ya en memoria, ya
                                    # consultado para title/handle/image_url mas abajo) y sirve
                                    # de defensa adicional si en el futuro se deja de
                                    # auto-excluir algun otro bucket.
                                    def _b08_is_same_type(_b08_cand_pid):
                                        if not _b08_tfidf or not _b08_ptype:
                                            return False
                                        _b08_cand = _b08_tfidf.id_index.get(str(_b08_cand_pid), {})
                                        return (
                                            _b08_cand.get("product_type", "").upper()
                                            == _b08_ptype.upper()
                                        )

                                    # FIX (24/07/2026): _b08_belongs_to_bucket() -- complemento de
                                    # _b08_is_same_type(). search_outfit_by_image() (pool generico,
                                    # preexistente) a veces devuelve candidatos cuyo product_type
                                    # real no pertenece al bucket donde se los coloco -- confirmado
                                    # en produccion: ancla AROS + "que accesorios combinan" -> un
                                    # NOVIAS LARGOS (vestido) dentro del bucket "accessory",
                                    # sobreviviendo hasta el resultado final. _b08_is_same_type()
                                    # no lo detecta porque solo compara contra el tipo del ANCLA,
                                    # no contra el bucket declarado. Usa
                                    # product_taxonomy.get_outfit_slot() (misma fuente de verdad de
                                    # Fase 1b) para verificar que el tipo real del candidato
                                    # efectivamente pertenece al bucket -- si no, se descarta como
                                    # sangrado entre buckets. Fail-open (no bloquea) si el tipo del
                                    # candidato no esta catalogado en product_taxonomy.py -- evita
                                    # perder variedad legitima por cobertura incompleta de la
                                    # taxonomia; el patron establecido es agregar el tipo faltante
                                    # en cuanto se detecte con evidencia, no bloquear preventivamente.
                                    def _b08_belongs_to_bucket(_b08_cand_pid, _b08_cat):
                                        if not _b08_tfidf:
                                            return True
                                        _b08_cand = _b08_tfidf.id_index.get(str(_b08_cand_pid), {})
                                        _b08_cand_type = _b08_cand.get("product_type", "").upper()
                                        if not _b08_cand_type:
                                            return True
                                        from src.recommenders.product_taxonomy import (
                                            get_outfit_slot as _b08_get_outfit_slot,
                                        )
                                        _b08_cand_slot = _b08_get_outfit_slot(_b08_cand_type)
                                        if _b08_cand_slot is None:
                                            return True
                                        return _b08_cand_slot == _b08_cat

                                    # NIVEL 1 FIX (18/07/2026): variedad de subtipos dentro de un
                                    # mismo bucket. Antes de esto, dentro de un bucket como
                                    # "accessory" (que agrupa AROS/COLLARES/BRAZALETES/CINTURONES/
                                    # TOCADOS/ALAS DE NOVIA), el orden de los candidatos era pura
                                    # similitud visual devuelta por el embedding-service -- sin
                                    # ningun peso hacia asegurar variedad de subtipos. Igual que
                                    # F-08C (Hallazgo T8, mismo dia): cuando un subtipo domina
                                    # numericamente el catalogo o la vecindad visual (ej. AROS),
                                    # las primeras posiciones del bucket terminan monopolizadas
                                    # por ese subtipo, dejando poco o ningun lugar para
                                    # COLLARES/BRAZALETES/CINTURONES/TOCADOS aunque el usuario
                                    # pidio "accesorios" en general (T5, sesion 18/07/2026:
                                    # ancla Collar + "que accesorios combinan con esto?" -> solo
                                    # 2 subtipos distintos entre los 8 resultados).
                                    #
                                    # Mismo principio que la particion de F-08C (Hallazgo T8),
                                    # generalizado de "tipo exacto primero, resto despues" (2
                                    # grupos) a "round-robin entre TODOS los subtipos presentes"
                                    # (N grupos) -- agrupa por product_type real (mismo dato ya
                                    # en memoria via id_index, sin llamadas nuevas), preserva el
                                    # orden interno de similitud visual dentro de cada subtipo,
                                    # e intercala un item de cada subtipo por turno. No cambia
                                    # QUE productos entran al pool (eso lo decide el
                                    # embedding-service), solo el ORDEN en que se consumen --
                                    # por eso opera sobre _b08_pools_full antes de derivar
                                    # _b08_pools_fresh, para que la mejora de orden se propague a
                                    # ambas pasadas del interleaving por igual.
                                    def _b08_interleave_by_subtype(_b08_flat_pids):
                                        if not _b08_tfidf:
                                            return _b08_flat_pids
                                        _b08_by_type: dict = {}
                                        for _b08_st_pid in _b08_flat_pids:
                                            _b08_st_type = (
                                                _b08_tfidf.id_index.get(str(_b08_st_pid), {})
                                                .get("product_type", "UNKNOWN").upper()
                                            )
                                            _b08_by_type.setdefault(_b08_st_type, []).append(_b08_st_pid)
                                        _b08_result = []
                                        while any(_b08_by_type.values()):
                                            for _b08_st_key, _b08_st_group in list(_b08_by_type.items()):
                                                if _b08_st_group:
                                                    _b08_result.append(_b08_st_group.pop(0))
                                                if not _b08_st_group:
                                                    del _b08_by_type[_b08_st_key]
                                        return _b08_result

                                    # GAP 1 FIX (13/07/2026): search_outfit_by_image() no acepta
                                    # exclusion de IDs -- limitacion del embedding-service (es un
                                    # servicio Cloud Run separado, desplegado independientemente;
                                    # agregar exclude_ids ahi es un cambio de arquitectura de dos
                                    # servicios coordinados, evaluado y pospuesto deliberadamente
                                    # -- ver DCT de la sesion 13/07/2026). Se filtra del lado del
                                    # cliente con dos pools por categoria:
                                    #   _b08_pools_full:  excluye ancla + mismo product_type (14/07)
                                    #                      + intercalado por subtipo (18/07)
                                    #   _b08_pools_fresh: excluye ancla + mismo tipo + _b08_shown_ids
                                    # El interleaving prioriza "fresh" en la Pasada 1; solo si no
                                    # alcanza a completar n_recommendations, la Pasada 2 rellena
                                    # con "full" (repetir productos ya vistos es mejor que dejar
                                    # el carrusel con menos de n_recommendations items -- mismo
                                    # principio de "relleno restringido" ya usado en F-08 Fase A).
                                    _b08_pools_full = {
                                        cat: _b08_interleave_by_subtype([
                                            pid for pid in pids
                                            if str(pid) != _b08_pid
                                            and not _b08_is_same_type(pid)
                                            and _b08_belongs_to_bucket(pid, cat)
                                        ])
                                        for cat, pids in _b08_outfit_cats.items()
                                        if isinstance(pids, list) and pids
                                    }
                                    _b08_pools_fresh = {
                                        cat: [pid for pid in pids if str(pid) not in _b08_shown_ids]
                                        for cat, pids in _b08_pools_full.items()
                                    }

                                    def _b08_interleave(_b08_pools, _b08_recs_list, _b08_seen, _b08_rank_start):
                                        # Helper deliberado (a diferencia del estilo inline del
                                        # resto del archivo): la Pasada 1 (fresh) y la Pasada 2
                                        # (full) ejecutan EXACTAMENTE la misma logica de
                                        # round-robin + construccion de dict de producto: extraerla
                                        # evita mantener dos copias que puedan desincronizarse (el
                                        # mismo tipo de bug de "dos bloques gemelos" ya visto antes
                                        # en esta sesion con _B08_TYPE_TO_CAT). _b08_pools se
                                        # consume/vacia in-place (mismo comportamiento que el bucle
                                        # original); _b08_seen evita reagregar en la Pasada 2 un
                                        # producto que la Pasada 1 ya agrego.
                                        _b08_rank = _b08_rank_start
                                        while (
                                            len(_b08_recs_list) < n_recommendations
                                            and any(_b08_pools.values())
                                        ):
                                            for _b08_cat, _b08_pool in list(_b08_pools.items()):
                                                # BUG CRITICO CONFIRMADO (16/07/2026): la condicion
                                                # original "if not _b08_pool or len(...) >= n: break"
                                                # rompia el FOR-LOOP COMPLETO en cuanto encontraba
                                                # la PRIMERA categoria vacia en el orden del dict --
                                                # aunque otras categorias posteriores SI tuvieran
                                                # items pendientes, nunca se llegaba a procesarlas.
                                                # Como nada se popeaba ni se borraba de _b08_pools,
                                                # el WHILE exterior volvia a entrar con el dict
                                                # EXACTAMENTE IGUAL -> loop infinito real (100% CPU,
                                                # cero logs, cero excepcion) hasta que Cloud Run mata
                                                # la conexion a los 300s (visto en produccion como
                                                # 504 tras 5 minutos, revision 00260-sr9/00261-bml).
                                                # Reproducido de forma determinista y confirmado con
                                                # un test standalone (7 casos adversariales, uno de
                                                # ellos cuelga con el codigo viejo y termina con este
                                                # fix) -- ver DCT de la sesion 16/07/2026.
                                                #
                                                # Este patron de "break" ya existia en el codigo
                                                # ANTES de los fixes de Gap 1/Gap 2 de esta semana --
                                                # no lo introdujeron esos cambios. Pero excluir mas
                                                # productos (shown_products, mismo product_type) y
                                                # agregar categorias mas escasas (bottom/shoes, ~2.2-
                                                # 2.3% del catalogo) aumento mucho la probabilidad de
                                                # que una categoria termine vacia tras el filtrado --
                                                # convirtiendo un bug latente en algo reproducible en
                                                # conversaciones de varios turnos, exactamente el
                                                # escenario de las pruebas que lo confirmaron.
                                                #
                                                # FIX: separar las dos condiciones. "Ya complete
                                                # n_recommendations" SI debe cortar todo (break). Pero
                                                # "esta categoria puntual esta vacia" debe saltar a la
                                                # SIGUIENTE categoria (continue) sin abandonar el resto
                                                # del for-loop, y borrarla de _b08_pools para que el
                                                # while exterior no la vuelva a revisar en pasadas
                                                # futuras -- garantiza que el dict SIEMPRE se achica en
                                                # cada iteracion, por lo que el while termina siempre.
                                                if len(_b08_recs_list) >= n_recommendations:
                                                    break
                                                if not _b08_pool:
                                                    del _b08_pools[_b08_cat]
                                                    continue
                                                _b08_vid = str(_b08_pool.pop(0))
                                                if _b08_vid in _b08_seen:
                                                    if not _b08_pool:
                                                        del _b08_pools[_b08_cat]
                                                    continue
                                                _b08_vprod = (
                                                    _b08_tfidf.id_index.get(_b08_vid)
                                                    if _b08_tfidf else None
                                                )
                                                if _b08_vprod:
                                                    _b08_score = round(1.0 - _b08_rank * 0.04, 4)
                                                    _b08_recs_list.append({
                                                        "id":               _b08_vid,
                                                        "title":            _b08_vprod.get("title", ""),
                                                        "similarity_score": _b08_score,
                                                        "score":            _b08_score,
                                                        "handle":           _b08_vprod.get("handle", ""),
                                                        "image_url":        _b08_vprod.get("image_url"),
                                                        "product_data": {
                                                            **_b08_vprod,
                                                            # outfit_category expuesto para LFM:
                                                            # permite generar respuesta como
                                                            # "este top combina perfectamente..."
                                                            "outfit_category": _b08_cat,
                                                        },
                                                        "source": f"outfit_completion_f08_{_b08_cat}",
                                                    })
                                                    _b08_seen.add(_b08_vid)
                                                    _b08_rank += 1
                                                if not _b08_pool:
                                                    del _b08_pools[_b08_cat]
                                                    break
                                        return _b08_rank

                                    _b08_seen_ids = {_b08_pid}
                                    _b08_rank_after_fresh = _b08_interleave(
                                        _b08_pools_fresh, _b08_recs, _b08_seen_ids, 0
                                    )
                                    _b08_fresh_count = len(_b08_recs)

                                    if len(_b08_recs) < n_recommendations:
                                        _b08_interleave(
                                            _b08_pools_full, _b08_recs, _b08_seen_ids, _b08_rank_after_fresh
                                        )

                                    if _b08_recs:
                                        _b08_repeated_count = len(_b08_recs) - _b08_fresh_count
                                        logger.info(
                                            f"F-08B outfit_completion: {len(_b08_recs)} productos "
                                            f"(categories={list(_b08_outfit_cats.keys())}, "
                                            f"pid={_b08_pid!r}, frescos={_b08_fresh_count}, "
                                            f"repetidos_por_agotamiento={_b08_repeated_count})"
                                        )
                                        return _b08_recs
                                    else:
                                        # FIX (28/07/2026): antes, si _b08_recs terminaba vacio
                                        # (busqueda exitosa, sin timeout ni excepcion, pero cero
                                        # candidatos finales), el codigo caia en silencio total --
                                        # cero logs -- directo al siguiente mecanismo de fallback
                                        # mas abajo (F-08B.2). Diagnosticar esto requeria rastrear
                                        # el codigo linea por linea (ver caso real, 27/07/2026:
                                        # ancla AROS + "con que vestidos combina mejor?" ->
                                        # target_categories=['dress'] -> 0 productos -> cayo sin
                                        # aviso a F-08B.2, que ignora la categoria pedida). Este log
                                        # no cambia ningun comportamiento, solo hace visible POR QUE
                                        # no hubo resultados -- pool crudo vacio para las categorias
                                        # pedidas, o todo ya en shown_products (o ambos).
                                        logger.info(
                                            f"F-08B outfit_completion: 0 productos para "
                                            f"target_categories={_b08_target_cats}, "
                                            f"anchor_type={_b08_ptype!r}, pid={_b08_pid!r}, "
                                            f"shown_products_count={len(_b08_shown_ids)} -- "
                                            f"cayendo a mecanismo de fallback"
                                        )

                        except asyncio.TimeoutError:
                            logger.warning("F-08B outfit_completion timeout — fallback a flujo normal")
                        except Exception as _b08_err:
                            logger.warning(f"F-08B outfit_completion fallback: {_b08_err}")
                    # ── Fin F-08 Fase B ───────────────────────────────────────────────

                    if use_diversification:
                        # ✅ NUEVO: Usar fallback inteligente con exclusión de productos ya vistos
                        try:
                            # from src.recommenders.improved_fallback_exclude_seen import ImprovedFallbackStrategies
                            from src.recommenders.improved_fallback_exclude_seen import (
                                ImprovedFallbackStrategies,
                                extract_categories_from_query,
                                get_concrete_categories,
                                get_parent_categories,      # NUEVO: expansion a categorias hermanas
                                normalize_recommendation_dict,  # Refactor: esquema visual canonico
                            )
                            # Obtener todos los productos disponibles
                            all_products = main_unified_redis.hybrid_recommender.content_recommender.product_data
                            
                            # ═══════════════════════════════════════════════════════════════
                            # ✨ FIX #1 v2 (10/04/2026): Priorizar current_product_context
                            # sobre el historial para construir user_events.
                            #
                            # PROBLEMA ORIGINAL: FIX #1 iteraba TODOS los turns del
                            # historial y extraia categorias de sus user_queries. Si el
                            # usuario habia pedido vestidos en turnos anteriores, esas
                            # queries dominaban los user_events aunque el usuario estuviera
                            # actualmente en la pagina de unos aretes.
                            #
                            # EJEMPLO REAL (logs 10/04/2026):
                            #   - Producto actual: Aros Alana (type='AROS')
                            #   - Turn 7 historial: 'show me some dresses' → VESTIDOS
                            #   - Turn 9 historial: 'Muestrame vestidos similares' → VESTIDOS
                            #   - user_events resultantes: ['VESTIDOS LARGOS', 'VESTIDOS CORTOS', 'VESTIDOS MIDIS']
                            #   - Resultado: se recomendaban vestidos en pagina de aretes
                            #
                            # FIX: Si current_product_context esta disponible, construir
                            # user_events exclusivamente desde el producto actual.
                            # El historial de turns solo se usa cuando NO hay producto actual.
                            # ═══════════════════════════════════════════════════════════════
                            user_events = []
                            
                            # Verificar si hay contexto del producto actual (F-01)
                            _current_ctx = (
                                getattr(mcp_context, "current_product_context", None)
                                if mcp_context else None
                            )
                            
                            if _current_ctx:
                                # PATH PRINCIPAL: usar el producto que el usuario esta
                                # viendo ahora. Esto garantiza que las recomendaciones
                                # sean siempre relevantes al contexto actual.
                                _product_type = _current_ctx.get("product_type", "")
                                _collections = _current_ctx.get("collections", [])
                                
                                # FIX (16/06/2026 — coleccion-contamination):
                                # ANTES: se creaban eventos con los NOMBRES DE COLECCION
                                # Shopify ('Tapados', 'Capas', 'Fiesta') almacenados como
                                # product_type. Esto corrompía PRIORIDAD 2 en smart_fallback:
                                # preferred_categories=['Tapados','Capas','Fiesta'] no
                                # coinciden con product_types reales ('CAPAS BORDADAS',
                                # 'CAPAS GASA') → 0 matches → PRIORIDAD 3: 42 categorías
                                # aleatorias → productos sin imagen, precio 0.01 CHF.
                                #
                                # CAUSA: colecciones son metadata de organización Shopify
                                # (storefront), NO product_types del catálogo TF-IDF.
                                # PRIORIDAD 2 filtra por product_type — nombres de colección
                                # nunca coincidirán con valores reales del catálogo.
                                #
                                # FIX: almacenar SOLO el product_type real del producto actual.
                                # Los siblings (añadidos debajo) completan el conjunto de
                                # categorías para PRIORIDAD 2 (ej. CAPAS GASA + CAPAS BORDADAS).
                                if _product_type:
                                    user_events.append({
                                        "productId": _current_ctx.get("id"),
                                        "product_info": {
                                            "product_type": _product_type,
                                            "source": "current_product_context"
                                        },
                                        "eventType": "view",
                                        "source": "f01_product_context"
                                    })
                                
                                # FIX (28/05/2026 — diversificacion): Expansion a categorias hermanas.
                                # Cuando la categoria actual (ej. CONJUNTOS FALDAS) se agota por
                                # exclusiones en Turn 2+, las hermanas (ej. CONJUNTOS PANTALONES)
                                # actuan como siguiente preferencia en get_personalized_fallback
                                # PRIORIDAD 2 -- en lugar de accesorios baratos de otras familias.
                                # Sin queries externas: usa get_parent_categories() del mismo modulo.
                                try:
                                    parent_map = get_parent_categories()
                                    for _parent_name, _subcats in parent_map.items():
                                        if _product_type.upper() in [s.upper() for s in _subcats]:
                                            for _sibling in _subcats:
                                                if _sibling.upper() != _product_type.upper():
                                                    user_events.append({
                                                        "productId": None,
                                                        "product_info": {
                                                            "product_type": _sibling,
                                                            "source": "parent_category_expansion"
                                                        },
                                                        "eventType": "view",
                                                        "source": "f01_sibling_expansion"
                                                    })
                                            logger.info(
                                                f"FIX diversification: siblings of '{_product_type}' "
                                                f"under parent '{_parent_name}' added to user_events: {_subcats}"
                                            )
                                            break
                                except Exception as _sib_e:
                                    logger.warning(
                                        f"FIX diversification: sibling expansion failed (non-critical): {_sib_e}"
                                    )

                                logger.info(
                                    f"FIX #1 v2: user_events built from current_product_context "
                                    f"(type={_product_type!r}, collections={_collections}) "
                                    f"-- historial ignorado para evitar contaminacion de categorias"
                                )
                            
                            elif mcp_context and mcp_context.total_turns > 0:
                                # PATH FALLBACK: no hay producto actual (usuario en home o
                                # categoria), usar historial de turns como antes.
                                logger.info(f"FIX #1 v2: no current_product_context -- usando historial ({mcp_context.total_turns} turns)")
                                logger.info(f"🔄 FIX #1: Building user_events from {mcp_context.total_turns} MCP turns")
                                
                                available_categories = get_concrete_categories()
                        
                                for turn_idx, turn in enumerate(mcp_context.turns):
                                    try:
                                        if hasattr(turn, 'user_query') and turn.user_query:
                                            inferred_categories = extract_categories_from_query(
                                                turn.user_query, 
                                                available_categories
                                            )
                                            
                                            if inferred_categories:
                                                for inferred_category in inferred_categories:
                                                    user_events.append({
                                                        "productId": None,
                                                        "product_info": {
                                                            "product_type": inferred_category,
                                                            "source_query": turn.user_query[:50]
                                                        },
                                                        "eventType": "view",
                                                        "source": "mcp_context_turn",
                                                        "turn_number": turn_idx + 1
                                                    })
                                    except Exception as turn_e:
                                        logger.warning(f"FIX #1 v2: error en turn {turn_idx + 1}: {turn_e}")
                                        continue
                                
                                logger.info(f"FIX #1 v2: Generated {len(user_events)} user_events from turn history")
                                if user_events:
                                    categories_found = [evt["product_info"]["product_type"] for evt in user_events]
                                    logger.info(f"   Historical categories: {categories_found}")
                            else:
                                logger.info("FIX #1 v2: no context available, user_events remains empty")
                            
                            # ── F-08 Fase B.2: Outfit Completion — categorías complementarias ──
                            # Trigger: sub_intent=outfit_completion + current_product_context
                            # Activa cuando VISUAL_SEARCH_ENABLED=false (dev local) o cuando
                            # la Fase B (visual search) no pudo ejecutarse.
                            # Reemplaza user_events (que apuntan a KIMONOS/TAPADOS) con
                            # categorías COMPLEMENTARIAS (AROS, COLLARES, CLUTCH, etc.).
                            # Sin este fix: "quelque chose qui va avec ça" → más kimonos.
                            if (
                                _b08_sub_intent == "outfit_completion"
                                and _current_ctx
                                and user_events
                            ):
                                _outfit_product_type = _current_ctx.get("product_type", "").upper()

                                # FIX (28/07/2026): F-08B.2 siempre usaba su propio mapa
                                # hardcodeado (_OUTFIT_COMPLEMENT_MAP, keyed por el tipo del
                                # FIX (25/09/2026): logica de decision extraida a un modulo
                                # puro y testeado -- ver
                                # src/recommenders/f08b2_category_resolution.py para el
                                # historial completo (auto-referencia, sobre-expansion, el Fix 2
                                # original de Fase 1b, y el mapa _OUTFIT_COMPLEMENT_MAP sin
                                # cambios). Extraido como red de seguridad antes de la decision
                                # de unificacion de taxonomia (roadmap Fase 2, item 4: "tests
                                # automatizados antes de refactorizar nada grande") -- mismo
                                # comportamiento exacto de antes, ahora cubierto por
                                # tests/unit/test_f08b2_category_resolution.py (14 casos,
                                # incluyendo los reales de produccion del 20-24/09/2026).
                                from src.recommenders.f08b2_category_resolution import (
                                    resolve_f08b2_complement_types as _b08b2_resolve,
                                )
                                try:
                                    from src.recommenders.improved_fallback_exclude_seen import (
                                        extract_categories_from_query as _b08b2_extract_cats,
                                        get_concrete_categories as _b08b2_get_concrete_cats,
                                    )
                                    from src.recommenders.product_taxonomy import (
                                        get_outfit_slot as _b08b2_get_outfit_slot,
                                        types_in_outfit_slot as _b08b2_types_in_slot,
                                    )
                                    _complement_cats = _b08b2_resolve(
                                        conversation_query=conversation_query,
                                        outfit_product_type=_outfit_product_type,
                                        extract_categories_fn=_b08b2_extract_cats,
                                        get_concrete_categories_fn=_b08b2_get_concrete_cats,
                                        get_outfit_slot_fn=_b08b2_get_outfit_slot,
                                        types_in_outfit_slot_fn=_b08b2_types_in_slot,
                                    )
                                    logger.info(
                                        f"F-08B.2 outfit_completion: tipos resueltos para "
                                        f"type={_outfit_product_type!r} -- {_complement_cats}"
                                    )
                                except Exception as _b08b2_err:
                                    logger.warning(
                                        f"F-08B.2 category resolution failed, usando fallback "
                                        f"generico: {_b08b2_err}"
                                    )
                                    _complement_cats = [
                                        _c for _c in ["AROS", "COLLARES", "CLUTCH", "CINTURONES"]
                                        if _c != _outfit_product_type
                                    ]

                                user_events = [
                                    {
                                        "productId": None,
                                        "product_info": {
                                            "product_type": _cat,
                                            "source": "outfit_complement_f08b2"
                                        },
                                        "eventType": "view",
                                        "source": "outfit_complement"
                                    }
                                    for _cat in _complement_cats
                                ]
                                logger.info(
                                    f"F-08B.2 outfit_completion: overriding user_events "
                                    f"with complement categories for "
                                    f"type={_outfit_product_type!r}: {_complement_cats}"
                                )
                            # ── Fin F-08 Fase B.2 ───────────────────────────────────────────
                            
                            # ── F-08 Fase C: Diversificación visual coherente (Turn 2+) ────────
                            # Trigger: use_diversification=True + product_ctx + query similar
                            #          + VISUAL_SEARCH_ENABLED=true.
                            # Usa search_by_product_id (vector FAISS existente, ~50ms) para
                            # construir un pool visualmente coherente con el producto visto.
                            # Filtra el pool a las categorias deseadas por la query.
                            # Si hay suficientes resultados visuales (>= n_recs): early-return.
                            # Si no: cae al smart_fallback normal (comportamiento actual).
                            if (
                                os.environ.get("VISUAL_SEARCH_ENABLED", "false").lower() == "true"
                                and mcp_context
                                and getattr(mcp_context, "current_product_context", None)
                                and mcp_context.current_product_context.get("id")
                                and _is_visual_similarity_query(conversation_query)
                            ):
                                try:
                                    from src.api.routers.visual_search_router import _get_colbert_client
                                    _c08_colbert = _get_colbert_client()
                                    _c08_tfidf   = getattr(
                                        main_unified_redis.hybrid_recommender,
                                        "content_recommender", None,
                                    )
                                    _c08_pid = str(mcp_context.current_product_context["id"])

                                    # COMPOSITE EMBEDDING (Fase 1b, 23/07/2026): reemplaza el chequeo
                                    # de familia ACCESSORIES (get_parent_categories()) por
                                    # product_taxonomy.get_steering_text() -- unica fuente de verdad
                                    # de taxonomia (ver PLAN_Fase1b_Revision_Arquitectonica_23072026.md).
                                    # El texto se resuelve AQUI (monolito) y se envia ya resuelto
                                    # (boost_text) al embedding-service, que ya no conoce ningun tipo
                                    # de producto. alpha tambien viene de la taxonomia (por tipo, no
                                    # global) -- hoy 0.5 para todos los tipos (identico a Fase 3,
                                    # cero cambio de comportamiento), ya parametrizado por tipo para
                                    # ajuste futuro sin otro refactor. _c08_ctx_type (mas abajo) se
                                    # recalcula para la logica de prioridad de tipo (Hallazgo T8) --
                                    # calculo independiente, se deja intacto.
                                    from src.recommenders.product_taxonomy import (
                                        get_steering_text as _c08_get_steering_text,
                                        get_alpha as _c08_get_alpha,
                                    )
                                    _c08_ctx_type_upper_early = mcp_context.current_product_context.get("product_type", "").upper()
                                    _c08_boost_text  = _c08_get_steering_text(_c08_ctx_type_upper_early)
                                    _c08_boost_alpha = _c08_get_alpha(_c08_ctx_type_upper_early, "reinforce") or 0.5

                                    # Pool visual. NIVEL 1 (06/10/2026, gap E5): el presupuesto
                                    # de vecinos crece con lo ya mostrado, porque el filtro de
                                    # categoria y la exclusion de vistos se aplican DESPUES del
                                    # recorte top_k. Con 80 productos vistos, un pool fijo de 50
                                    # se consumia casi entero en cosas ya descartadas (evidencia:
                                    # sesion 05/10/2026, 3 supervivientes y ninguna CARTERAS,
                                    # teniendo el catalogo carteras sin mostrar).
                                    # Base 50 desde F08C_ROUTE.faiss_top_k; tope en
                                    # RECS_VISUAL_POOL_CAP. Import lazy: BUG-REFACTOR-1 (18/06).
                                    from src.recommenders.f08_similarity_resolution import (
                                        F08C_ROUTE as _c08_pool_route,
                                        visual_pool_size as _c08_visual_pool_size,
                                    )
                                    _c08_pool_base = _c08_visual_pool_size(_c08_pool_route, 0)
                                    _c08_top_k = _c08_visual_pool_size(
                                        _c08_pool_route, len(shown_products)
                                    )
                                    # El "base" del log es el EFECTIVO (que puede venir de
                                    # RECS_VISUAL_POOL_BASE), no el faiss_top_k de la ruta.
                                    # Hasta el 13/10 se imprimia el de la ruta y salian lineas
                                    # aritmeticamente falsas como "top_k=100 (base=30, shown=0)".
                                    if _c08_top_k != _c08_pool_base:
                                        logger.info(
                                            f"F-08C pool ampliado: top_k={_c08_top_k} "
                                            f"(base={_c08_pool_base}, "
                                            f"shown={len(shown_products)})"
                                        )
                                    # ── E5 nivel 2, paso 3 (26/10/2026): filtro DENTRO de la busqueda ──────
                                    # Con RECS_VISUAL_FILTER_IN_SEARCH activado, el pool visual se pide al
                                    # embedding-service YA FILTRADO (POST /v1/embed/search-filtered): los top_k
                                    # vecinos son los mejores de entre los ADMITIDOS (familia + alternativas,
                                    # sin vistos ni el ancla), no los top_k globales filtrados despues. Ver
                                    # SPEC_E5_Nivel2_Busqueda_Filtrada_17102026.md.
                                    #
                                    # Para filtrar ANTES de buscar hay que saber ANTES que admite el pool. Ese
                                    # calculo vivia dentro del bloque de abajo y se encapsula en
                                    # _c08_prepare_pool_request() con el MISMO codigo. Con el flag activado se
                                    # llama aqui; con el desactivado, dentro del bloque, en el mismo punto que
                                    # antes: mismo codigo y mismo orden de logs (extract_categories_from_query
                                    # escribe en INFO). Comprobado por la prueba diferencial
                                    # tests/characterization/equiv_harness_handler_e5.py.
                                    from src.recommenders.f08_similarity_resolution import (
                                        build_pool_request as _c08_build_pool_request,
                                        build_visual_filter as _c08_build_visual_filter,
                                        resolve_similarity_categories as _c08_resolve_categories,
                                        visual_filter_in_search_enabled as _c08_filter_in_search,
                                    )
                                    from src.recommenders.product_taxonomy import (
                                        get_alternative_types as _c08_alternative_types,
                                        get_similarity_family as _c08_similarity_family,
                                    )

                                    def _c08_type_of(pid):
                                        # Contrato type_of del modulo: product_type del indice
                                        # TF-IDF, o "" si el producto no esta / no tiene tipo.
                                        return _c08_tfidf.id_index.get(str(pid), {}).get("product_type", "")

                                    def _c08_prepare_pool_request():
                                        """Etapas 1a + 1b + peticion de pool (antes inline en el bloque, sin
                                        cambios). Devuelve (ctx_type, resolution, pool_req)."""
                                        # ETAPA 1a -- categorias desde el TEXTO de la query, contra el
                                        # catalogo completo de tipos (no un sample). Se queda en el
                                        # llamador porque depende de all_products de este scope.
                                        _all_types = set(
                                            p.get("product_type", "")
                                            for p in all_products if p.get("product_type")
                                        )
                                        _text_cats = extract_categories_from_query(
                                            conversation_query,
                                            available_categories=_all_types,
                                        ) or []
                                        # ETAPA 1b -- el texto manda; si no nombra categoria, expansion
                                        # por contexto a las hermanas del grupo padre del ancla
                                        # (F08C_ROUTE.use_query_categories=True).
                                        _ctx_type = mcp_context.current_product_context.get(
                                            "product_type", ""
                                        ) if mcp_context and getattr(
                                            mcp_context, "current_product_context", None
                                        ) else ""
                                        # _c08_pool_route ES F08C_ROUTE: el mismo objeto que _c08_route,
                                        # que se importa mas abajo, dentro del bloque.
                                        _resolution = _c08_resolve_categories(
                                            _c08_pool_route, _ctx_type, _text_cats, get_parent_categories,
                                        )
                                        _pool_req = _c08_build_pool_request(
                                            _resolution,
                                            _ctx_type,
                                            similarity_family_fn=_c08_similarity_family,
                                            alternative_types_fn=_c08_alternative_types,
                                        )
                                        return _ctx_type, _resolution, _pool_req

                                    _c08_filter_on = (
                                        _c08_filter_in_search()
                                        and _c08_tfidf is not None
                                        and hasattr(_c08_tfidf, "id_index")
                                    )
                                    _c08_prepared = _c08_prepare_pool_request() if _c08_filter_on else None
                                    # anchor_found separa "ancla no indexada" de "nada elegible" (hallazgo
                                    # F7): con el filtro, una lista vacia puede ser cualquiera de las dos.
                                    _c08_anchor_found = False
                                    if _c08_filter_on:
                                        # MISMO criterio que el filtro posterior de la etapa 2, mas abajo.
                                        _c08_vfilter = _c08_build_visual_filter(
                                            _c08_tfidf.id_index.keys(),
                                            _c08_prepared[2].pool_cats or _c08_prepared[1].categories,
                                            _c08_pid,
                                            _c08_type_of,
                                            shown_products,
                                        )
                                        _c08_fres = await asyncio.wait_for(
                                            _c08_colbert.search_filtered(
                                                _c08_pid,
                                                include_ids=(sorted(_c08_vfilter.include)
                                                             if _c08_vfilter.include is not None else None),
                                                exclude_ids=sorted(_c08_vfilter.exclude),
                                                top_k=_c08_top_k,
                                                boost_text=_c08_boost_text or None,
                                                alpha=_c08_boost_alpha,
                                            ),
                                            timeout=3.0,
                                        )
                                        # None = fallo o circuit breaker abierto: mismo efecto que hoy
                                        # (lista vacia, no se entra al bloque, smart_fallback).
                                        _c08_visual_raw = _c08_fres.pairs if _c08_fres is not None else None
                                        _c08_anchor_found = _c08_fres is not None and _c08_fres.anchor_found
                                        logger.info(
                                            f"F-08C E5 filtro en busqueda: "
                                            f"include={'all' if _c08_vfilter.include is None else len(_c08_vfilter.include)} "
                                            f"exclude={len(_c08_vfilter.exclude)} "
                                            f"eligible={_c08_fres.eligible_count if _c08_fres is not None else '-'} "
                                            f"devueltos={len(_c08_visual_raw or [])} "
                                            f"anchor_found={_c08_anchor_found}"
                                        )
                                        if _c08_boost_text:
                                            logger.info(
                                                f"F-08C: composite embedding boost activo "
                                                f"(type={_c08_ctx_type_upper_early}, alpha={_c08_boost_alpha})"
                                            )
                                    elif _c08_boost_text:
                                        _c08_visual_raw = await asyncio.wait_for(
                                            _c08_colbert.search_by_product_id_with_text_boost(
                                                _c08_pid,
                                                boost_text=_c08_boost_text,
                                                alpha=_c08_boost_alpha,
                                                top_k=_c08_top_k,
                                                with_scores=True,
                                            ),
                                            timeout=3.0,
                                        )
                                        logger.info(
                                            f"F-08C: composite embedding boost activo "
                                            f"(type={_c08_ctx_type_upper_early}, alpha={_c08_boost_alpha})"
                                        )
                                    else:
                                        _c08_visual_raw = await asyncio.wait_for(
                                            _c08_colbert.search_by_product_id(
                                                _c08_pid, top_k=_c08_top_k, with_scores=True
                                            ),
                                            timeout=3.0,
                                        )

                                    # with_scores=True (06/10/2026): el cliente devuelve pares
                                    # (product_id, score) donde score es la similitud COSENO real
                                    # que FAISS ya calculaba y el servicio descartaba. Puede venir
                                    # None por par si el embedding-service aun no esta desplegado
                                    # con el campo 'scores' -- los dos servicios se despliegan por
                                    # separado y esa degradacion es esperada.
                                    #
                                    # Se separa en:
                                    #   _c08_visual_ids  -> List[str], EXACTAMENTE como antes, para
                                    #                       que el filtrado, el breakdown y la
                                    #                       particion T8 sigan intactos.
                                    #   _c08_visual_meta -> pid -> (rank_en_el_pool, score), que es
                                    #                       lo que el contrato necesita para marcar
                                    #                       procedencia y parecido REAL por item.
                                    # El rango se toma del pool ORIGINAL (antes de filtrar), que es
                                    # lo que significa "posicion en el vecindario visual".
                                    _c08_visual_pairs = _c08_visual_raw or []
                                    _c08_visual_ids = [pid for pid, _ in _c08_visual_pairs]
                                    _c08_visual_meta = {
                                        str(pid): (rank, score)
                                        for rank, (pid, score) in enumerate(_c08_visual_pairs)
                                    }

                                    # E5 (26/10/2026): con el filtro en la busqueda, una lista vacia con
                                    # anchor_found=True significa "nada elegible" y debe recorrer el camino
                                    # vacio de abajo (contrato con exhausted), como hoy cuando el filtro
                                    # posterior lo descarta todo. Con el flag desactivado anchor_found es
                                    # False y la condicion es la de siempre.
                                    if (_c08_visual_ids or _c08_anchor_found) and _c08_tfidf and hasattr(_c08_tfidf, "id_index"):
                                        # REFACTOR (02/10/2026 -- paso 1, SIN cambio de comportamiento):
                                        # la logica de decision de este bloque (resolucion de categorias,
                                        # filtrado del pool, particion T8, camino feliz / relleno parcial
                                        # y senales de agotamiento) se extrajo a
                                        # src/recommenders/f08_similarity_resolution.py, compartido con
                                        # F-08 Fase A. El historial completo de fixes de este bloque
                                        # (16/06 accessory gap, 17/06 relleno restringido + caso limite 0
                                        # candidatos, 18/06 strict_category, 06/07 Hallazgo T8, 13/07
                                        # candidate breakdown, 18/07 ancla incluida en texto, 26/07 Caso 3)
                                        # vive ahora en los docstrings de ese modulo y en
                                        # DCT_Cierre_Sesion_01102026.md, Addendum A.
                                        #
                                        # Equivalencia verificada (02/10/2026): prueba diferencial del
                                        # bloque inline anterior contra este (retorno, logs, llamadas a
                                        # smart_fallback y category_exhausted_info) + oraculo
                                        # tests/characterization/equiv_harness_f08.py. Las divergencias
                                        # conocidas respecto a F-08 Fase A (sin intercalado NIVEL 1, etc.)
                                        # estan codificadas en F08C_ROUTE -- se corrigen en el paso 2.
                                        #
                                        # Logs: formato IDENTICO al anterior (consultas de Cloud Logging
                                        # existentes siguen funcionando).
                                        # Import lazy: mismo patron defensivo que BUG-REFACTOR-1 (18/06).
                                        from src.recommenders.f08_similarity_resolution import (
                                            F08C_ROUTE as _c08_route,
                                            POOL_HAPPY as _C08_POOL_HAPPY,
                                            POOL_PARTIAL as _C08_POOL_PARTIAL,
                                            build_fill_exclusion as _c08_build_fill_exclusion,
                                            build_partial_exhaustion_info as _c08_build_exhaustion_info,
                                            build_partial_fill_events as _c08_build_fill_events,
                                            candidate_breakdown as _c08_get_breakdown,
                                            classify_pool as _c08_classify_pool,
                                            fill_score_start as _c08_get_fill_score_start,
                                            filter_visual_candidates as _c08_filter_candidates,
                                            order_candidates as _c08_order_candidates,
                                        )

                                        # ETAPA 1a + 1b + peticion de pool: ahora en _c08_prepare_pool_request()
                                        # (definida antes de la busqueda, MISMO codigo). Con el filtro activado
                                        # ya se calculo alli; con el desactivado se calcula AQUI, en el mismo
                                        # punto que antes. _c08_type_of tambien se definio alli.
                                        if _c08_prepared is None:
                                            _c08_prepared = _c08_prepare_pool_request()
                                        _c08_ctx_type, _c08_resolution, _c08_pool_req = _c08_prepared
                                        _c08_query_cats = _c08_resolution.categories
                                        _c08_anchor_type_for_ranking = _c08_resolution.anchor_type_for_ranking
                                        if _c08_resolution.expansion_error is not None:
                                            logger.warning(
                                                f"F-08C category expansion failed "
                                                f"(using exact type): {_c08_resolution.expansion_error}"
                                            )
                                        elif _c08_resolution.source == "parent_group":
                                            pass  # el log vive mas abajo, tras calcular pool_cats

                                        # ── CONTRATO principal/alternatives (06/10/2026) ──────────
                                        # Ver SPEC_Contrato_Recomendaciones_06102026.md.
                                        #
                                        # QUE ES "LO PEDIDO" depende de la INTENCION, no de la
                                        # categoria (decision de producto, 06/10/2026). Aqui la
                                        # intencion la revela el origen de la resolucion:
                                        #
                                        #   query_text  -> el usuario NOMBRO categorias
                                        #                  ("muestrame bolsos"): lo pedido son esas.
                                        #   parent_group-> dijo "similar a este" y expandimos a las
                                        #                  9 hermanas SOLO para tener pool. Lo que
                                        #                  pidio es SU TIPO; las hermanas son
                                        #                  alternativas, no la respuesta.
                                        #   exact_type  -> igual, sin grupo padre.
                                        #   none        -> sin ancla ni texto: todo es principal.
                                        #
                                        # El caso parent_group es el que arregla el defecto E2
                                        # observado el 05/10/2026: pedidos "bolsos similares", un
                                        # Cinturon aparecia en posicion 5 por encima de un Clutch en
                                        # la 6, porque los candidatos visuales (cualquiera de las 9
                                        # hermanas) arrancaban en score 1.0 y el relleno de catalogo
                                        # -- que traia los bolsos de verdad -- empezaba mas abajo.
                                        # Con el contrato el bolso va en principal y el cinturon en
                                        # alternatives, y to_flat_list() concatena en ese orden: ya
                                        # no es una regla de ranking que algo pueda saltarse.
                                        # INTENT_* ya no se importan aqui (17/10/2026): la
                                        # intencion la decide build_pool_request(), mas abajo.
                                        from src.recommenders.recommendation_set import (
                                            ORIGIN_CATALOG as _C08_ORIGIN_CATALOG,
                                            ORIGIN_VISUAL as _C08_ORIGIN_VISUAL,
                                            RecommendationSet as _C08_RecommendationSet,
                                            RequestSpec as _C08_RequestSpec,
                                            tag_origin as _c08_tag_origin,
                                        )
                                        from src.recommenders.f08_similarity_resolution import (
                                            filter_fill_to_request as _c08_filter_fill,
                                            principal_first_enabled as _c08_principal_first,
                                            split_candidates_by_request as _c08_split_by_request,
                                        )

                                        # G2 (07/10/2026): "lo pedido" en similitud es la FAMILIA del
                                        # ancla, no su product_type exacto.
                                        #
                                        # Evidencia: 07/10/2026, pidiendo similares a un clutch, el
                                        # CLUTCH LEONOR aparecio en 4a posicion por debajo de dos pares
                                        # de aros -- porque en el catalogo CARTERAS y CLUTCH son tipos
                                        # distintos, aunque para quien compra sean el mismo bolso.
                                        # get_similarity_family() resuelve eso sin ensanchar a las 9
                                        # hermanas del grupo padre (que es lo que metia los aros).
                                        #
                                        # El ancla va PRIMERA en la lista: build_partial_exhaustion_info
                                        # etiqueta el agotamiento con categories[0], asi que esto cierra
                                        # de paso el bug A.3.a para esta ruta -- antes, con ancla
                                        # CAPAS GASA se reportaba "CAPAS BORDADAS".
                                        #
                                        # EXTRAIDO (17/10/2026, E5 nivel 2 paso 2): la intencion, lo
                                        # pedido y lo que admite el pool se calculaban aqui inline y
                                        # POR DUPLICADO con Fase A. Ahora los decide
                                        # build_pool_request() en f08_similarity_resolution.py --
                                        # mismas reglas, una sola copia. E5 nivel 2 necesita ademas
                                        # poder calcularlos ANTES de la busqueda FAISS, para filtrar
                                        # dentro de ella (SPEC_E5_Nivel2_Busqueda_Filtrada_17102026).
                                        # Equivalencia: tests/characterization/
                                        # equiv_harness_pool_request.py (20.000 casos por ruta,
                                        # copias literales del codigo que habia aqui, + mutantes).
                                        # Las variables conservan sus nombres: el resto del bloque no
                                        # cambia.
                                        # (paso 3, 26/10/2026) _c08_pool_req ya viene de
                                        # _c08_prepare_pool_request(), arriba.
                                        _c08_intent = _c08_pool_req.intent
                                        _c08_requested_ordered = _c08_pool_req.requested_ordered
                                        _c08_requested = _c08_pool_req.requested

                                        # Que puede entrar en el POOL (10/10/2026): lo pedido MAS
                                        # sus alternativas declaradas. Sustituye al grupo padre de
                                        # CATEGORY_KEYWORDS, que venia decidiendolo hasta hoy y
                                        # traia dos problemas:
                                        #   - En 17 de 36 tipos coincidia con la familia, asi que el
                                        #     bloque de alternativas era imposible y, al agotarse,
                                        #     el turno caia al fallback generico (10/10: ropa
                                        #     interior sin stock para una consulta de pantalones).
                                        #   - Cruzaba novia e invitada: un conjunto de invitada
                                        #     ofrecia conjuntos de NOVIA.
                                        # De paso, esto saca del camino de similitud la dependencia
                                        # del ORDEN de CATEGORY_KEYWORDS (contrato implicito
                                        # ACCESSORIES/JOYAS, gap B6).
                                        # Calculado por build_pool_request() (ver arriba).
                                        _c08_alt_types = _c08_pool_req.alt_types
                                        _c08_pool_cats = _c08_pool_req.pool_cats

                                        # El log de expansion se emite DESPUES de calcular
                                        # _c08_pool_cats (10/10/2026) para que describa lo que el
                                        # filtro usa de verdad. Hasta el 12/10 imprimia el grupo
                                        # padre, que ya no es el criterio: con ancla AROS decia 9
                                        # tipos cuando el filtro usaba 4. Un log que contradice al
                                        # codigo es el mismo problema que provoco el diagnostico
                                        # erroneo del 01/10 (Addendum A.1).
                                        if _c08_resolution.source == "parent_group":
                                            logger.info(
                                                f"F-08C pool admite: '{_c08_ctx_type}' -> "
                                                f"{_c08_pool_cats} (familia={_c08_requested_ordered}, "
                                                f"alternativas={_c08_alt_types})"
                                            )

                                        def _c08_item_type_of(_item):
                                            # El contrato recibe items ya normalizados; el tipo vive
                                            # en product_data (el dict crudo del catalogo).
                                            return (_item.get("product_data") or {}).get("product_type", "")

                                        def _c08_build_contract(_items, _exhausted):
                                            """
                                            Construye el RecommendationSet y lo deja en mcp_context.

                                            Centralizado para los DOS puntos de retorno de esta ruta:
                                            duplicar la construccion seria repetir el error que
                                            costo la divergencia F-08A/F-08C (Addendum A del DCT).

                                            FASE 1 de la migracion: se devuelve to_flat_list(), que
                                            tiene el mismo tipo y esquema de siempre. Ningun
                                            consumidor se entera; lo unico que cambia es el ORDEN.
                                            El objeto completo queda en mcp_context para que el
                                            motor de personalizacion (fase 2) y la API (fase 3) lo
                                            consuman sin volver a tocar esta ruta.
                                            """
                                            _rset = _C08_RecommendationSet.build(
                                                intent=_c08_intent,
                                                items=_items,
                                                request=_C08_RequestSpec(categories=_c08_requested),
                                                n_requested=n_recommendations,
                                                type_of=_c08_item_type_of,
                                                anchor_id=str(_c08_pid),
                                                anchor_type=_c08_ctx_type or None,
                                                route="f08c",
                                                exhausted=_exhausted,
                                            )
                                            mcp_context.recommendation_set = _rset  # type: ignore[attr-defined]
                                            logger.info(
                                                f"F-08C contrato: intent={_rset.intent} "
                                                f"principal={len(_rset.principal)}{_rset.principal.categories} "
                                                f"alternatives={len(_rset.alternatives)}"
                                                f"{_rset.alternatives.categories} "
                                                f"exhausted={_rset.principal.exhausted}"
                                            )
                                            return _rset.to_flat_list()

                                        def _c08_tag_visual(_rec):
                                            """Marca procedencia visual con su rango y parecido REAL."""
                                            _rank, _score = _c08_visual_meta.get(str(_rec.get("id")), (None, None))
                                            return _c08_tag_origin(
                                                _rec, _C08_ORIGIN_VISUAL,
                                                visual_rank=_rank, visual_score=_score,
                                            )

                                        # ETAPA 2 -- filtrar pool: excluir vistos + el propio ancla +
                                        # categorias no deseadas (orden de similitud preservado).
                                        # Desde el 10/10/2026 el criterio es _c08_pool_cats
                                        # (familia + alternativas declaradas), no el grupo padre.
                                        _c08_candidates = _c08_filter_candidates(
                                            _c08_visual_ids, _c08_pid,
                                            _c08_pool_cats or _c08_query_cats,
                                            _c08_type_of, shown_products,
                                        )
                                        # E5 (26/10/2026): con el filtro en la busqueda, este filtro se conserva
                                        # como DEFENSA y no deberia quitar nada. Si quita algo, el catalogo con
                                        # que se construyo el filtro y el que usa este paso divergen: se avisa.
                                        if _c08_filter_on and len(_c08_candidates) != len(_c08_visual_ids):
                                            logger.warning(
                                                f"F-08C E5 divergencia: el filtro posterior quito "
                                                f"{len(_c08_visual_ids) - len(_c08_candidates)} de "
                                                f"{len(_c08_visual_ids)} candidatos ya filtrados en la busqueda"
                                            )

                                        # DIAGNOSTIC LOG (13/07/2026): desglose por tipo ANTES de la
                                        # particion T8 y del corte a n_recommendations.
                                        _c08_candidate_breakdown = _c08_get_breakdown(_c08_candidates, _c08_type_of)
                                        logger.info(
                                            f"F-08C candidate breakdown: {_c08_candidate_breakdown} "
                                            f"(anchor_type={_c08_anchor_type_for_ranking!r}, "
                                            f"total={len(_c08_candidates)})"
                                        )

                                        # ETAPA 3 -- particion T8: tipo exacto del ancla primero (solo
                                        # si _c08_anchor_type_for_ranking esta seteado). Sin intercalado
                                        # por subtipo en esta ruta (F08C_ROUTE.interleave_siblings=False).
                                        _c08_candidates = _c08_order_candidates(
                                            _c08_route, _c08_candidates,
                                            _c08_anchor_type_for_ranking, _c08_type_of,
                                        )

                                        # Observabilidad pool insuficiente (16/06 + caso 0 del 17/06).
                                        if 0 <= len(_c08_candidates) < n_recommendations:
                                            logger.info(
                                                f"F-08C pool insuficiente: {len(_c08_candidates)} candidatos "
                                                f"(necesarios={n_recommendations}, "
                                                f"cats={_c08_query_cats}, "
                                                f"shown={len(shown_products)}). "
                                                f"Categoria pequena o pool agotado. "
                                                f"Fallback a smart_fallback categorizado."
                                            )

                                        # ETAPA 4 -- G1 (07/10/2026): la decision de ir al catalogo se
                                        # toma sobre LO PEDIDO, no sobre el total del pool.
                                        #
                                        # Antes: classify_pool(len(_c08_candidates), n). En el turno T9
                                        # del 07/10 habia 11 candidatos -- 1 CARTERAS y 10 joyas. Como
                                        # 11 >= 8, el sistema tomaba el camino feliz ("tengo de sobra"),
                                        # NUNCA preguntaba al catalogo, devolvia 1 bolso y 7 joyas, y
                                        # dejaba exhausted=False aunque no supiera nada del stock. El
                                        # boton de "ver <categoria> otra vez" -- cuya condicion es
                                        # exhausted==True -- no habria aparecido jamas.
                                        #
                                        # La pregunta estaba mal planteada: no es "tengo n candidatos?",
                                        # es "tengo n de lo que me pidieron?".
                                        #
                                        # Con el interruptor apagado (RECS_PRINCIPAL_FIRST=0) own son
                                        # TODOS los candidatos y other queda vacio: la clasificacion
                                        # vuelve a ser la de antes, byte por byte. Es la via de reversion
                                        # sin redesplegar la imagen.
                                        if _c08_principal_first():
                                            _c08_own, _c08_other = _c08_split_by_request(
                                                _c08_candidates, _c08_requested, _c08_type_of,
                                            )
                                        else:
                                            _c08_own, _c08_other = list(_c08_candidates), []
                                        _c08_pool_path = _c08_classify_pool(len(_c08_own), n_recommendations)
                                        logger.info(
                                            f"F-08C reparto: pedido={_c08_requested_ordered} "
                                            f"en_pool={len(_c08_own)} otros={len(_c08_other)} "
                                            f"camino={_c08_pool_path}"
                                        )

                                        if _c08_pool_path == _C08_POOL_HAPPY:
                                            # G1: aqui hay n o mas candidatos DE LO PEDIDO, asi que el
                                            # corte final es homogeneo por construccion. El aviso de
                                            # mezcla del 26/07 (Caso 3) ya no aplica: no hay mezcla que
                                            # reportar, y su informacion la lleva ahora la propia
                                            # estructura del contrato (principal / alternatives).
                                            _c08_recs = []
                                            for _c08_rank, _c08_vid in enumerate(
                                                _c08_own[:n_recommendations]
                                            ):
                                                _c08_vprod = _c08_tfidf.id_index.get(str(_c08_vid))
                                                if _c08_vprod:
                                                    _c08_recs.append(
                                                        _c08_tag_visual(
                                                            normalize_recommendation_dict(
                                                                raw=_c08_vprod,
                                                                rank=_c08_rank,
                                                                score_start=1.0,
                                                                score_step=_c08_route.visual_score_step,
                                                                source=_c08_route.visual_source,
                                                            )
                                                        )
                                                    )

                                            if _c08_recs:
                                                logger.info(
                                                    f"F-08C visual_diversification: "
                                                    f"{len(_c08_recs)} productos "
                                                    f"(pool={len(_c08_visual_ids)}, "
                                                    f"cats={_c08_query_cats}, "
                                                    f"candidates={len(_c08_candidates)})"
                                                )
                                                # exhausted=False: no se pregunto al catalogo porque no
                                                # hizo falta -- habia de sobra de lo pedido.
                                                return _c08_build_contract(_c08_recs, False)

                                        elif _c08_pool_path == _C08_POOL_PARTIAL:
                                            # Sprint 17/06/2026 + G1 (07/10/2026).
                                            #
                                            # Faltan productos DE LO PEDIDO, asi que se va al catalogo a
                                            # por mas -- ANTES de rellenar con hermanas del pool. Es el
                                            # "invertir la prioridad" discutido el 05/10/2026: un bolso
                                            # del catalogo vale mas que un cinturon visualmente parecido.
                                            #
                                            # El relleno pide la FAMILIA (_c08_requested_ordered), no el
                                            # grupo padre: pedir el grupo padre traeria aros que
                                            # acabarian en alternatives, desperdiciando la consulta.
                                            #
                                            # user_query=None es CRITICO: fuerza PRIORIDAD 2 (user_events
                                            # sinteticos) y evita que PRIORIDAD 1 re-detecte otra
                                            # categoria desde el texto crudo. Evento extra para el tipo
                                            # exacto del ancla (top-3 de PRIORIDAD 2).
                                            _c08_current_type = str(
                                                mcp_context.current_product_context.get("product_type", "")
                                            ).upper()
                                            _c08_fill_cats = (
                                                _c08_requested_ordered
                                                if (_c08_principal_first() and _c08_requested_ordered)
                                                else _c08_query_cats
                                            )
                                            _c08_fill_events = _c08_build_fill_events(
                                                _c08_route, _c08_fill_cats, _c08_current_type,
                                            )
                                            _c08_needed = n_recommendations - len(_c08_own)
                                            # Exclusion: vistos + TODOS los candidatos del pool (own y
                                            # otros) + ancla. Los "otros" tambien se excluyen porque
                                            # pueden acabar en alternatives: traerlos del catalogo seria
                                            # duplicarlos.
                                            _c08_fill_exclude = _c08_build_fill_exclusion(
                                                shown_products, _c08_candidates, _c08_pid,
                                            )

                                            _c08_fill_raw = await ImprovedFallbackStrategies.smart_fallback(
                                                user_id=validated_user_id,
                                                products=all_products,
                                                user_events=_c08_fill_events,
                                                n=_c08_needed,
                                                exclude_products=_c08_fill_exclude,
                                                user_query=None,  # bypass PRIORIDAD 1 -- ver comentario arriba
                                                # DECISION DE PRODUCTO (18/06/2026): coherencia categorica
                                                # estricta -- devuelve menos items antes que mezclar
                                                # categorias ajenas; el deficit se notifica al LLM abajo.
                                                strict_category=True,
                                            )

                                            # DEFENSA B2 (10/10/2026): smart_fallback puede devolver
                                            # productos de CUALQUIER categoria pese a
                                            # strict_category=True, porque get_personalized_fallback
                                            # cae a PRIORIDAD 3 ("diverse") cuando la categoria
                                            # preferida se queda en cero. Visto en T10 del 10/10:
                                            # "Preferred categories: ['CARTERAS','CLUTCH']" seguido de
                                            # "Generated 8 diverse recommendations" -- ni un bolso, y
                                            # entre ellos lenceria. Filtrar ANTES de contar es lo que
                                            # hace que el agotamiento se mida bien.
                                            _c08_fill_raw = _c08_filter_fill(
                                                _c08_fill_raw, _c08_requested
                                            )
                                            # La etiqueta sale de _c08_fill_cats[0], que con G2 es el
                                            # TIPO DEL ANCLA (va primero en _c08_requested_ordered) --
                                            # esto cierra el bug A.3.a para esta ruta: antes, con ancla
                                            # CAPAS GASA, se reportaba "CAPAS BORDADAS".
                                            _c08_exhaustion = _c08_build_exhaustion_info(
                                                _c08_fill_cats, len(_c08_own),
                                                len(_c08_fill_raw), _c08_needed,
                                            )
                                            if _c08_exhaustion is not None:
                                                mcp_context.category_exhausted_info = _c08_exhaustion  # type: ignore[attr-defined]
                                                logger.info(
                                                    f"F-08C category_exhausted: {len(_c08_own)} visual + "
                                                    f"{len(_c08_fill_raw)} fill = {_c08_exhaustion['shown_count']} "
                                                    f"(de {n_recommendations} pedidos, categoria="
                                                    f"{_c08_exhaustion['category']!r}). LLM notificacion activada."
                                                )

                                            # PASO 1: lo pedido que ya habia en el pool (ya rankeado).
                                            _c08_recs = []
                                            for _c08_rank, _c08_vid in enumerate(_c08_own):
                                                _c08_vprod = _c08_tfidf.id_index.get(str(_c08_vid))
                                                if _c08_vprod:
                                                    _c08_recs.append(
                                                        _c08_tag_visual(
                                                            normalize_recommendation_dict(
                                                                raw=_c08_vprod,
                                                                rank=_c08_rank,
                                                                score_start=1.0,
                                                                score_step=_c08_route.visual_score_step,
                                                                source=_c08_route.visual_source,
                                                            )
                                                        )
                                                    )

                                            # PASO 2: lo pedido traido del catalogo, un escalon por
                                            # debajo. origin=catalog: NO tiene vecindad visual medida,
                                            # asi que visual_rank y visual_score quedan a None. El widget
                                            # solo debe mostrar porcentaje donde visual_score exista --
                                            # es lo que impide repetir el "% match" inventado (E3).
                                            _c08_fill_score_start = _c08_get_fill_score_start(
                                                _c08_recs[-1]["score"] if _c08_recs else None
                                            )
                                            for _c08_fill_rank, _c08_fill_prod in enumerate(_c08_fill_raw):
                                                _c08_recs.append(
                                                    _c08_tag_origin(
                                                        normalize_recommendation_dict(
                                                            raw=_c08_fill_prod,
                                                            rank=_c08_fill_rank,
                                                            score_start=_c08_fill_score_start,
                                                            score_step=_c08_route.fill_score_step,
                                                            source=_c08_route.fill_source,
                                                        ),
                                                        _C08_ORIGIN_CATALOG,
                                                    )
                                                )

                                            # PASO 3 (G1): las hermanas del pool, como ALTERNATIVAS.
                                            # Van al final y el contrato las separa en su propio bloque,
                                            # asi que un cinturon visualmente parecido ya no puede
                                            # colocarse por encima de un bolso. El tope de alternativas
                                            # lo aplica RecommendationSet.build().
                                            _c08_alt_score_start = _c08_get_fill_score_start(
                                                _c08_recs[-1]["score"] if _c08_recs else None
                                            )
                                            for _c08_alt_rank, _c08_alt_id in enumerate(_c08_other):
                                                _c08_alt_prod = _c08_tfidf.id_index.get(str(_c08_alt_id))
                                                if _c08_alt_prod:
                                                    _c08_recs.append(
                                                        _c08_tag_visual(
                                                            normalize_recommendation_dict(
                                                                raw=_c08_alt_prod,
                                                                rank=_c08_alt_rank,
                                                                score_start=_c08_alt_score_start,
                                                                score_step=_c08_route.visual_score_step,
                                                                source=_c08_route.visual_source,
                                                            )
                                                        )
                                                    )

                                            if _c08_recs:
                                                logger.info(
                                                    f"F-08C visual_partial_plus_fill: "
                                                    f"{len(_c08_recs)} productos totales "
                                                    f"(visual={len(_c08_own)}, "
                                                    f"fill={len(_c08_fill_raw)}, "
                                                    f"alt={len(_c08_other)}, "
                                                    f"needed_fill={_c08_needed}, "
                                                    f"cats={_c08_fill_cats})"
                                                )
                                                # exhausted: aqui SI se pregunto al catalogo con
                                                # strict_category=True. Si devolvio menos de lo
                                                # necesario, el agotamiento esta respaldado.
                                                return _c08_build_contract(
                                                    _c08_recs, _c08_exhaustion is not None
                                                )
                                        elif _c08_principal_first() and _c08_requested:
                                            # CAMINO VACIO con G1 (08/10/2026) -- el agujero que dejo
                                            # el cableado del 07/10.
                                            #
                                            # Antes de G1, "vacio" significaba "el pool no trajo NADA",
                                            # algo rarisimo, y por eso esta rama solo caia al
                                            # smart_fallback generico. Con G1 significa otra cosa muy
                                            # distinta y mucho mas frecuente: "el pool trae candidatos
                                            # pero NINGUNO es de lo pedido".
                                            #
                                            # Evidencia (08/10/2026, T10-T12): con 8, 30 y 31
                                            # candidatos en el pool y cero bolsos, el turno se saltaba
                                            # el contrato entero. El usuario recibia 8 productos
                                            # mezclados sin bloques ni etiqueta, y exhausted no se
                                            # activaba NUNCA -- asi que ni el aviso ni el boton de
                                            # "ver <categoria> otra vez" podian aparecer jamas.
                                            # Ironia: sin G1 ese turno habria ido por el camino feliz
                                            # y SI habria construido el contrato. Al hacer la pregunta
                                            # mas exigente, la rama no cableada paso a activarse antes.
                                            #
                                            # Ahora hace lo mismo que el camino parcial: preguntar al
                                            # catalogo por la FAMILIA y, si tampoco hay, devolver
                                            # principal vacio + hermanas como alternativas, con
                                            # exhausted=True. Es el diseno acordado el 06/10: nunca
                                            # cero resultados, pero nunca relleno mudo.
                                            _c08_current_type = str(
                                                mcp_context.current_product_context.get("product_type", "")
                                            ).upper()
                                            _c08_fill_events = _c08_build_fill_events(
                                                _c08_route, _c08_requested_ordered, _c08_current_type,
                                            )
                                            _c08_fill_exclude = _c08_build_fill_exclusion(
                                                shown_products, _c08_candidates, _c08_pid,
                                            )
                                            _c08_fill_raw = await ImprovedFallbackStrategies.smart_fallback(
                                                user_id=validated_user_id,
                                                products=all_products,
                                                user_events=_c08_fill_events,
                                                n=n_recommendations,
                                                exclude_products=_c08_fill_exclude,
                                                user_query=None,  # bypass PRIORIDAD 1
                                                strict_category=True,
                                            )
                                            # DEFENSA B2 (10/10/2026) -- ver comentario en la rama
                                            # parcial. Aqui era CRITICO: sin filtrar, 8 productos de
                                            # categorias ajenas se contaban como "el catalogo si
                                            # tenia" y exhausted se quedaba en False, bloqueando el
                                            # aviso al usuario y el boton de reinicio.
                                            _c08_fill_raw = _c08_filter_fill(
                                                _c08_fill_raw, _c08_requested
                                            )

                                            # exhausted: se pregunto al catalogo por la familia con
                                            # strict_category=True y no dio para n. Aqui SI esta
                                            # respaldado -- es la senal que gobierna el aviso al
                                            # usuario y el boton de reinicio por categoria.
                                            _c08_empty_exhausted = len(_c08_fill_raw) < n_recommendations
                                            if _c08_empty_exhausted:
                                                _c08_exhaustion = _c08_build_exhaustion_info(
                                                    _c08_requested_ordered, 0,
                                                    len(_c08_fill_raw), n_recommendations,
                                                )
                                                if _c08_exhaustion is not None:
                                                    mcp_context.category_exhausted_info = _c08_exhaustion  # type: ignore[attr-defined]
                                                    logger.info(
                                                        f"F-08C category_exhausted (pool sin nada de lo "
                                                        f"pedido): 0 visual + {len(_c08_fill_raw)} fill "
                                                        f"(de {n_recommendations} pedidos, categoria="
                                                        f"{_c08_exhaustion['category']!r}). "
                                                        f"LLM notificacion activada."
                                                    )

                                            # Lo pedido que haya traido el catalogo va a principal.
                                            _c08_recs = []
                                            for _c08_fill_rank, _c08_fill_prod in enumerate(_c08_fill_raw):
                                                _c08_recs.append(
                                                    _c08_tag_origin(
                                                        normalize_recommendation_dict(
                                                            raw=_c08_fill_prod,
                                                            rank=_c08_fill_rank,
                                                            score_start=1.0,
                                                            score_step=_c08_route.fill_score_step,
                                                            source=_c08_route.fill_source,
                                                        ),
                                                        _C08_ORIGIN_CATALOG,
                                                    )
                                                )

                                            # Las hermanas del pool, como ALTERNATIVAS etiquetadas.
                                            _c08_alt_score_start = _c08_get_fill_score_start(
                                                _c08_recs[-1]["score"] if _c08_recs else None
                                            )
                                            for _c08_alt_rank, _c08_alt_id in enumerate(_c08_other):
                                                _c08_alt_prod = _c08_tfidf.id_index.get(str(_c08_alt_id))
                                                if _c08_alt_prod:
                                                    _c08_recs.append(
                                                        _c08_tag_visual(
                                                            normalize_recommendation_dict(
                                                                raw=_c08_alt_prod,
                                                                rank=_c08_alt_rank,
                                                                score_start=_c08_alt_score_start,
                                                                score_step=_c08_route.visual_score_step,
                                                                source=_c08_route.visual_source,
                                                            )
                                                        )
                                                    )

                                            # SIEMPRE se devuelve el contrato, aunque quede vacio
                                            # (10/10/2026). Antes aqui habia un `if _c08_recs:` y,
                                            # al no haber ni catalogo ni hermanas, el turno caia al
                                            # smart_fallback generico -- que ignora strict_category
                                            # y devuelve "diverse". Evidencia del 10/10, T3-T4 con
                                            # ancla PANTALONES: se recomendo ropa interior
                                            # reductora, ademas A CERO DE STOCK, a quien pedia
                                            # pantalones. Y se le habia dicho ya al LLM que la
                                            # categoria estaba agotada, asi que el mensaje y los
                                            # productos se contradecian.
                                            #
                                            # Devolver [] es correcto y es lo honesto: no hay nada
                                            # de lo pedido y no hay alternativas que ofrecer. El
                                            # motor recibe principal=0 / alternatives=0 /
                                            # exhausted=True y redacta una salida (ver el bloque de
                                            # hechos en mcp_personalization_engine.py). Verificado
                                            # que aguas abajo una lista vacia es segura: el unico
                                            # acceso posicional, top_recs[0], esta guardado por
                                            # `elif top_recs:`, y recs_summary sobre vacio da "".
                                            logger.info(
                                                f"F-08C pool_sin_lo_pedido: "
                                                f"{len(_c08_recs)} productos totales "
                                                f"(catalogo={len(_c08_fill_raw)}, "
                                                f"alt={len(_c08_other)}, "
                                                f"cats={_c08_requested_ordered})"
                                            )
                                            return _c08_build_contract(
                                                _c08_recs, _c08_empty_exhausted
                                            )
                                        # Si no queda NADA que ofrecer (ni catalogo ni hermanas), no se
                                        # hace nada -- cae a smart_fallback() mas abajo en el flujo
                                        # normal (comportamiento correcto desde el fix de
                                        # contaminacion de colecciones, Bug 3).

                                except asyncio.TimeoutError:
                                    # FIX (16/06/2026): elevado de logger.debug a logger.info
                                    # para visibilidad en producción.
                                    # El cold start del embedding service (min-instances=0)
                                    # provoca timeouts de 3s en la primera llamada tras idle.
                                    # El comportamiento es correcto (smart_fallback actua),
                                    # pero el silencio previo era un gap de observabilidad.
                                    logger.warning(
                                        "F-08C visual timeout (>3s) — embedding service probablemente frío. "
                                        "Fallback a smart_fallback. Próxima llamada será rápida (~1-2ms)."
                                    )
                                except Exception as _c08_err:
                                    logger.warning(f"F-08C visual fallback: {_c08_err}")
                            # ── Fin F-08 Fase C ───────────────────────────────────────

                            # ✨ MEJORADO: Pasar query del usuario Y user_events poblado
                            # F-08B.2: cuando outfit_completion activó el OUTFIT_COMPLEMENT_MAP,
                            # user_events ya tiene las categorías correctas (AROS/COLLARES/CLUTCH).
                            # Si pasamos user_query al smart_fallback, PRIORIDAD 1 detecta
                            # "robe" → VESTIDOS y sobreescribe esos user_events con vestidos.
                            # Fix: suprimir user_query para forzar PRIORIDAD 2 (usa user_events).
                            _outfit_complement_active = (
                                _b08_sub_intent == "outfit_completion"
                                and any(
                                    evt.get("product_info", {}).get("source") == "outfit_complement_f08b2"
                                    for evt in (user_events or [])
                                )
                            )
                            _smart_fallback_query = (
                                None  # PRIORIDAD 1 bypassed — PRIORIDAD 2 usa user_events (AROS/COLLARES/...)
                                if _outfit_complement_active
                                else conversation_query
                            )
                            if _outfit_complement_active:
                                logger.info(
                                    "F-08B.2 query suppressed: outfit_complement_f08b2 activo — "
                                    "PRIORIDAD 2 usará user_events de complement categories"
                                )

                            # DECISION DE PRODUCTO (19/06/2026) -- Caso B: extender coherencia
                            # categorica estricta tambien cuando F-08C no encuentra NINGUN
                            # candidato visual (0 candidatos) en una query de similitud.
                            # En ese caso _smart_fallback_query = conversation_query (la query
                            # real, ej. "similar a este"), que no nombra categoria explicita ->
                            # PRIORIDAD 1 no detecta nada -> cae a PRIORIDAD 2 con user_events
                            # (categoria del producto actual via contexto). Es EXACTAMENTE la
                            # misma rama ya protegida con strict_category en el relleno de
                            # F-08C -- aqui extendemos el mismo flag a este call site.
                            #
                            # EXTENSION (20/06/2026): ampliar tambien a queries de categoria
                            # directa en Turno 2+ ("muestrame mas pantalones"). Hallazgo real
                            # (Turno 3, sesion 20/06/2026): esa query NO es de similitud, asi
                            # que _is_visual_similarity_query devolvia False y este call site
                            # quedaba sin proteccion. A partir del Turno 2, las queries de
                            # categoria directa caen AQUI (no en "Standard recommendations",
                            # que solo corre en la primera consulta de la sesion) -- es el
                            # mismo problema del Caso A, pero por una puerta distinta.
                            # Import local con alias: el import agrupado de
                            # extract_categories_from_query mas arriba esta dentro del bloque
                            # F-08C (solo corre si la query es de similitud), asi que aqui
                            # reimportamos con alias para evitar el mismo UnboundLocalError
                            # de BUG-REFACTOR-1 (18/06/2026) -- mismo patron que el bloque
                            # "Standard recommendations" del Caso A.
                            try:
                                from src.recommenders.improved_fallback_exclude_seen import (
                                    extract_categories_from_query as _b_extract_categories,
                                    get_concrete_categories as _b_get_concrete_categories,
                                )
                                # FIX (22/06/2026): capturar la LISTA completa (no solo el
                                # booleano) para poder reutilizarla mas abajo en la deteccion
                                # de agotamiento -- ver BUG-CASEB-CATFALSEPOS.
                                _b_explicit_categories = _b_extract_categories(
                                    conversation_query, _b_get_concrete_categories()
                                )
                            except Exception as _b_cat_err:
                                logger.warning(f"Case B category detection failed: {_b_cat_err}")
                                _b_explicit_categories = []
                            _b_has_explicit_category = bool(_b_explicit_categories)
                            #
                            # IMPORTANTE: sigue sin aplicar a outfit_completion (combina
                            # categorias por diseno). Las busquedas de categoria directa SI
                            # quedan cubiertas ahora (antes solo similitud).
                            _strict_zero_candidates = (
                                not _outfit_complement_active
                                and (
                                    _is_visual_similarity_query(conversation_query)
                                    or _b_has_explicit_category
                                )
                            )

                            recommendations = await ImprovedFallbackStrategies.smart_fallback(
                                user_id=validated_user_id,
                                products=all_products,
                                user_events=user_events,  # ✅ FIX #1: Ahora poblado
                                n=n_recommendations,
                                exclude_products=shown_products,
                                user_query=_smart_fallback_query,  # None si outfit_complement activo
                                strict_category=_strict_zero_candidates,
                            )

                            # Detectar agotamiento de categoria (Caso B, Opcion 1 -- 20/06/2026):
                            # el chequeo original solo comparaba len(recommendations) <
                            # n_recommendations -- pero get_personalized_fallback tiene su PROPIO
                            # fallthrough interno a PRIORIDAD 3 (diverse) cuando las categorias
                            # preferidas quedan en CERO productos disponibles (no solo "pocos").
                            # Ese fallthrough vive DENTRO de la misma llamada, fuera del alcance
                            # de strict_category (que solo protege el top-up de PRIORIDAD 2 cuando
                            # personalized_products SI tiene algo). Resultado real observado
                            # (Turno 5, sesion 20/06/2026): con CALZONES totalmente agotado,
                            # smart_fallback devolvia 8 productos de "Standard diversification"
                            # (mezclados, sin relacion), pero como el conteo SI llegaba a
                            # n_recommendations, la condicion original nunca se activaba -- mismo
                            # punto ciego que tuvo el Caso A antes de la Opcion 1. Aplicamos aqui
                            # exactamente el mismo fix: comparar categorias presentes, no solo
                            # el conteo total.
                            # FIX (22/06/2026 -- BUG-CASEB-CATFALSEPOS): _zero_cand_categories
                            # se calculaba SOLO desde user_events (categoria ambiental/historica
                            # de turnos anteriores), incluso cuando la query ACTUAL nombraba una
                            # categoria EXPLICITA y DISTINTA que SI se encontro completa. Evidencia
                            # real (Turno 4, sesion 22/06/2026): query "Muestrame Calzones" encontro
                            # 8/8 CALZONES (Distribution plan: {'CALZONES': 8}, sin agotamiento),
                            # pero el chequeo comparaba contra ['PANTALONES'] (categoria historica
                            # de turnos anteriores, reconstruida via "FIX #1 v2: ... from turn
                            # history" porque no habia current_product_context) -- como ningun
                            # CALZON coincidia con "PANTALONES", el sistema reporto falsamente
                            # "0 de la categoria pedida + 8 de otras categorias, categoria=
                            # PANTALONES", y el LLM le dijo al usuario que no habia mas PANTALONES
                            # mientras le mostraba CALZONES.
                            # FIX: priorizar la categoria EXPLICITA de la query actual
                            # (_b_explicit_categories, ya detectada arriba) sobre la categoria
                            # historica/ambiental -- solo caer a la historica cuando la query NO
                            # nombra ninguna categoria explicita (ej. "similar a este").
                            _zero_cand_categories = _b_explicit_categories or list({
                                evt.get("product_info", {}).get("product_type", "")
                                for evt in (user_events or [])
                                if evt.get("product_info", {}).get("product_type")
                            })
                            if _strict_zero_candidates and _zero_cand_categories:
                                _zero_cand_cats_upper = {c.upper() for c in _zero_cand_categories}
                                _zero_cand_on_count = sum(
                                    1 for rec in recommendations
                                    if (rec.get("category") or rec.get("product_type", "")).upper()
                                    in _zero_cand_cats_upper
                                )
                                _zero_cand_off_count = len(recommendations) - _zero_cand_on_count

                                if _zero_cand_off_count > 0 or _zero_cand_on_count < n_recommendations:
                                    _zero_cand_cat = _zero_cand_categories[0]
                                    mcp_context.category_exhausted_info = {  # type: ignore[attr-defined]
                                        "category": _zero_cand_cat,
                                        "shown_count": _zero_cand_on_count,
                                        "total_count": len(recommendations),
                                    }
                                    logger.info(
                                        f"smart_fallback category_exhausted (Caso B): "
                                        f"{_zero_cand_on_count} de la categoria pedida + "
                                        f"{_zero_cand_off_count} de otras categorias "
                                        f"(total={len(recommendations)}/{n_recommendations}, "
                                        f"categoria={_zero_cand_cat!r}). LLM notificacion activada."
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

                    # ── F-08 Fase A + A.5: Similitud visual en Turn 1 ───────────────
                    # Trigger: VISUAL_SEARCH_ENABLED=true + patrón de similitud en query
                    #          + product_ctx con id disponible.
                    #
                    # A.5 (primario, ~50ms): search_by_product_id usa el vector FAISS
                    #   ya almacenado — sin fetch del CDN ni re-encode.
                    # A   (fallback, ~635ms): si el producto no está en el índice FAISS
                    #   (nuevo, no indexado aún), cae a CDN fetch + search_by_image.
                    #
                    # Fallback silencioso a TF-IDF: cualquier excepción o timeout.
                    if (
                        not use_diversification
                        and os.environ.get("VISUAL_SEARCH_ENABLED", "false").lower() == "true"
                        and mcp_context
                        and getattr(mcp_context, "current_product_context", None)
                        and mcp_context.current_product_context.get("id")
                        and _is_visual_similarity_query(conversation_query)
                    ):
                        try:
                            from src.api.routers.visual_search_router import _get_colbert_client
                            # FIX (18/06/2026 - BUG-REFACTOR-1): normalize_recommendation_dict
                            # se importaba SOLO dentro del bloque F-08C (Turn 2+). Python marca
                            # cualquier nombre importado en UNA rama de una funcion como variable
                            # local de TODA la funcion. Cuando F-08C no corre (Turn 1, sin
                            # current_product_context de sesion previa), la variable queda
                            # sin asignar y F-08A lanza UnboundLocalError al usarla.
                            # Resultado en produccion: F-08 visual_search fallback a TF-IDF
                            # en todos los Turn 1, perdiendo el ranking por similitud visual.
                            # FIX: importar aqui tambien, siguiendo el patron de imports lazy
                            # ya existente en este bloque. El modulo esta cacheado en sys.modules
                            # despues del primer import (en F-08C o aqui), asi que el segundo
                            # import es un dict lookup de microsegundos -- sin costo real.
                            from src.recommenders.improved_fallback_exclude_seen import normalize_recommendation_dict
                            _f08_colbert = _get_colbert_client()
                            _f08_tfidf   = getattr(
                                main_unified_redis.hybrid_recommender,
                                "content_recommender", None,
                            )
                            _f08_pid   = str(mcp_context.current_product_context["id"])
                            _f08_ptype = mcp_context.current_product_context.get("product_type", "")

                            # COMPOSITE EMBEDDING (Fase 1b, 23/07/2026): ver comentario identico en
                            # el bloque F-08C mas arriba en este archivo -- misma logica, ahora via
                            # product_taxonomy.py (unica fuente de verdad, reemplaza
                            # get_parent_categories() + SHOPIFY_TYPE_TEXT_PROMPTS). _f08_type_upper
                            # (mas abajo, ~linea 2430) se recalcula para la expansion a hermanas --
                            # calculo independiente, se deja intacto.
                            from src.recommenders.product_taxonomy import (
                                get_steering_text as _f08_get_steering_text,
                                get_alpha as _f08_get_alpha,
                            )
                            _f08_ptype_upper_early = _f08_ptype.upper() if _f08_ptype else ""
                            _f08_boost_text  = _f08_get_steering_text(_f08_ptype_upper_early)
                            _f08_boost_alpha = _f08_get_alpha(_f08_ptype_upper_early, "reinforce") or 0.5

                            # A.5: buscar por ID (usa vector FAISS existente, ~50ms)
                            # NIVEL 1 (06/10/2026, gap E5): mismo criterio que F-08C. En Turn 1
                            # shown_products esta siempre vacio, asi que esto devuelve el base
                            # (30) y el comportamiento NO cambia -- se cablea por simetria y para
                            # no depender de esa invariante.
                            from src.recommenders.f08_similarity_resolution import (
                                F08A_ROUTE as _f08_pool_route,
                                visual_pool_size as _f08_visual_pool_size,
                            )
                            _f08_pool_base = _f08_visual_pool_size(_f08_pool_route, 0)
                            _f08_top_k = _f08_visual_pool_size(
                                _f08_pool_route, len(shown_products)
                            )
                            # Base EFECTIVA, no la de la ruta -- ver el comentario en F-08C.
                            if _f08_top_k != _f08_pool_base:
                                logger.info(
                                    f"F-08 pool ampliado: top_k={_f08_top_k} "
                                    f"(base={_f08_pool_base}, "
                                    f"shown={len(shown_products)})"
                                )
                            # ── E5 nivel 2, paso 3 (26/10/2026): filtro DENTRO de la busqueda ──────
                            # Mismo esquema que en F-08C (ver el comentario de alli): el calculo de
                            # que admite el pool se encapsula en _f08_prepare_pool_request() con el
                            # MISMO codigo; con el flag activado se llama aqui, con el desactivado
                            # dentro del bloque, en el mismo punto que antes.
                            from src.recommenders.f08_similarity_resolution import (
                                build_pool_request as _f08_build_pool_request,
                                build_visual_filter as _f08_build_visual_filter,
                                resolve_similarity_categories as _f08_resolve_categories,
                                visual_filter_in_search_enabled as _f08_filter_in_search,
                            )
                            from src.recommenders.product_taxonomy import (
                                get_alternative_types as _f08_alternative_types,
                                get_similarity_family as _f08_similarity_family,
                            )

                            def _f08_type_of(pid):
                                # Contrato type_of del modulo: product_type del indice
                                # TF-IDF, o "" si el producto no esta / no tiene tipo.
                                return _f08_tfidf.id_index.get(str(pid), {}).get("product_type", "")

                            def _f08_parent_categories_fn():
                                # El import va DENTRO de la funcion a proposito: el modulo la
                                # invoca dentro de su propio try/except, asi que un ImportError
                                # degrada al tipo exacto igual que antes, en vez de propagarse
                                # al except exterior y perder la busqueda visual entera.
                                # (En el bloque original el import estaba dentro del mismo try
                                # que la llamada -- se conserva esa semantica exacta.)
                                # Import lazy obligatorio ademas por BUG-REFACTOR-1 (18/06):
                                # get_parent_categories solo se importa arriba dentro de
                                # "if use_diversification:" (Turn 2+), rama que en Turn 1 nunca
                                # ejecuta -- Python trata el nombre como local a TODA la funcion
                                # y usarlo aqui sin este import daria UnboundLocalError.
                                from src.recommenders.improved_fallback_exclude_seen import (
                                    get_parent_categories as _f08_get_parent_categories,
                                )
                                return _f08_get_parent_categories()

                            def _f08_prepare_pool_request():
                                """Etapa 1 + peticion de pool (antes inline en el bloque, sin
                                cambios). Devuelve (resolution, pool_req)."""
                                # ETAPA 1 -- categorias deseadas. En Fase A las decide SOLO el
                                # ancla: F08A_ROUTE.use_query_categories=False, por eso se pasa
                                # None como categorias de texto (divergencia con F-08C, pendiente
                                # de decision de producto -- Addendum A.2).
                                # _f08_pool_route ES F08A_ROUTE: el mismo objeto que _f08_route,
                                # que se importa mas abajo, dentro del bloque.
                                _resolution = _f08_resolve_categories(
                                    _f08_pool_route, _f08_ptype, None, _f08_parent_categories_fn,
                                )
                                _pool_req = _f08_build_pool_request(
                                    _resolution,
                                    _f08_ptype,
                                    similarity_family_fn=_f08_similarity_family,
                                    alternative_types_fn=_f08_alternative_types,
                                )
                                return _resolution, _pool_req

                            _f08_filter_on = (
                                _f08_filter_in_search()
                                and _f08_tfidf is not None
                                and hasattr(_f08_tfidf, "id_index")
                            )
                            _f08_prepared = _f08_prepare_pool_request() if _f08_filter_on else None
                            # anchor_found separa "ancla no indexada" de "nada elegible" (hallazgo
                            # F7). En Fase A decide DOS cosas: el fallback por imagen y la entrada
                            # al bloque (ver ambos mas abajo).
                            _f08_anchor_found = False
                            if _f08_filter_on:
                                # MISMO criterio que el filtro posterior de la etapa 2, mas abajo.
                                _f08_vfilter = _f08_build_visual_filter(
                                    _f08_tfidf.id_index.keys(),
                                    _f08_prepared[1].pool_cats or _f08_prepared[0].categories,
                                    _f08_pid,
                                    _f08_type_of,
                                    shown_products,
                                )
                                _f08_fres = await asyncio.wait_for(
                                    _f08_colbert.search_filtered(
                                        _f08_pid,
                                        include_ids=(sorted(_f08_vfilter.include)
                                                     if _f08_vfilter.include is not None else None),
                                        exclude_ids=sorted(_f08_vfilter.exclude),
                                        top_k=_f08_top_k,
                                        boost_text=_f08_boost_text or None,
                                        alpha=_f08_boost_alpha,
                                    ),
                                    timeout=3.0,
                                )
                                # None = fallo o circuit breaker abierto: mismo efecto que hoy.
                                _f08_visual_raw = _f08_fres.pairs if _f08_fres is not None else None
                                _f08_anchor_found = _f08_fres is not None and _f08_fres.anchor_found
                                logger.info(
                                    f"F-08 Fase A E5 filtro en busqueda: "
                                    f"include={'all' if _f08_vfilter.include is None else len(_f08_vfilter.include)} "
                                    f"exclude={len(_f08_vfilter.exclude)} "
                                    f"eligible={_f08_fres.eligible_count if _f08_fres is not None else '-'} "
                                    f"devueltos={len(_f08_visual_raw or [])} "
                                    f"anchor_found={_f08_anchor_found}"
                                )
                                if _f08_boost_text:
                                    logger.info(
                                        f"F-08 Fase A: composite embedding boost activo "
                                        f"(type={_f08_ptype_upper_early}, alpha={_f08_boost_alpha})"
                                    )
                            elif _f08_boost_text:
                                _f08_visual_raw = await asyncio.wait_for(
                                    _f08_colbert.search_by_product_id_with_text_boost(
                                        _f08_pid,
                                        boost_text=_f08_boost_text,
                                        alpha=_f08_boost_alpha,
                                        top_k=_f08_top_k,
                                        with_scores=True,
                                    ),
                                    timeout=3.0,
                                )
                                logger.info(
                                    f"F-08 Fase A: composite embedding boost activo "
                                    f"(type={_f08_ptype_upper_early}, alpha={_f08_boost_alpha})"
                                )
                            else:
                                _f08_visual_raw = await asyncio.wait_for(
                                    _f08_colbert.search_by_product_id(
                                        _f08_pid, top_k=_f08_top_k, with_scores=True
                                    ),
                                    timeout=3.0,
                                )

                            # Fallback CDN: solo si producto no está en índice FAISS
                            # E5 (26/10/2026): con el filtro en la busqueda, una lista vacia con
                            # anchor_found=True significa "nada elegible", NO "ancla no indexada":
                            # no se descarga la imagen ni se repite la busqueda. Con el flag
                            # desactivado anchor_found es False y la condicion es la de siempre.
                            if not _f08_visual_raw and not _f08_anchor_found:
                                _f08_image_url = None
                                if _f08_tfidf and hasattr(_f08_tfidf, "id_index"):
                                    _f08_prod = _f08_tfidf.id_index.get(_f08_pid)
                                    if _f08_prod:
                                        _f08_image_url = _f08_prod.get("image_url")
                                if _f08_image_url:
                                    import httpx as _httpx_f08
                                    async with _httpx_f08.AsyncClient(timeout=3.0) as _http_f08:
                                        _img_resp = await _http_f08.get(_f08_image_url)
                                        _img_resp.raise_for_status()
                                        _img_bytes = _img_resp.content
                                    _f08_visual_raw = await asyncio.wait_for(
                                        _f08_colbert.search_by_image(
                                            _img_bytes, top_k=_f08_top_k, with_scores=True
                                        ),
                                        timeout=3.0,
                                    )

                            # with_scores=True (10/10/2026): el cliente devuelve pares
                            # (product_id, score) con la similitud COSENO real que FAISS ya
                            # calculaba y el servicio descartaba. El score puede venir None
                            # por par si el embedding-service aun no esta desplegado con el
                            # campo 'scores' -- los dos servicios se despliegan por separado
                            # y esa degradacion es esperada.
                            #
                            # Se separa en:
                            #   _f08_visual_ids  -> List[str], EXACTAMENTE como antes, para que
                            #                       el filtrado, el breakdown y la particion T8
                            #                       sigan intactos.
                            #   _f08_visual_meta -> pid -> (rank_en_el_pool, score), que es lo
                            #                       que el contrato necesita para marcar
                            #                       procedencia y parecido REAL por item.
                            # El rango se toma del pool ORIGINAL (antes de filtrar), que es lo
                            # que significa "posicion en el vecindario visual".
                            _f08_visual_pairs = _f08_visual_raw or []
                            _f08_visual_ids = [pid for pid, _ in _f08_visual_pairs]
                            _f08_visual_meta = {
                                str(pid): (rank, score)
                                for rank, (pid, score) in enumerate(_f08_visual_pairs)
                            }

                            # E5 (26/10/2026): tambien con anchor_found -- la rama "nada elegible"
                            # recorre el camino vacio de abajo (contrato con exhausted), como hoy
                            # cuando el filtro posterior lo descarta todo.
                            if _f08_visual_ids or _f08_anchor_found:
                                # REFACTOR (02/10/2026 -- paso 1b, SIN cambio de comportamiento):
                                # la logica de decision de este bloque (resolucion de categorias,
                                # filtrado del pool, particion T8 + intercalado NIVEL 1, camino
                                # feliz / relleno parcial y senal de agotamiento) se extrajo a
                                # src/recommenders/f08_similarity_resolution.py, compartido con
                                # F-08C (cableado el 02/10/2026, ver Addendum A.7 del DCT).
                                # El historial completo de fixes de este bloque (03/07 expansion a
                                # hermanas, 03/07 relleno restringido, 18/07 T8 + NIVEL 1, 26/07
                                # candidate breakdown) vive ahora en los docstrings de ese modulo y
                                # en DCT_Cierre_Sesion_01102026.md, Addendum A.
                                #
                                # Las divergencias de esta ruta frente a F-08C estan codificadas en
                                # F08A_ROUTE, no en el flujo: use_query_categories=False (Fase A
                                # nunca consulta el texto de la query) e interleave_siblings=True
                                # (NIVEL 1, que F-08C no tiene).
                                #
                                # Equivalencia verificada (02/10/2026): prueba diferencial del
                                # bloque inline anterior contra este (retorno, logs, llamadas a
                                # smart_fallback y category_exhausted_info).
                                #
                                # Logs: formato IDENTICO al anterior (las consultas de Cloud
                                # Logging existentes siguen funcionando).
                                # Import lazy: mismo patron defensivo que BUG-REFACTOR-1 (18/06).
                                from src.recommenders.f08_similarity_resolution import (
                                    F08A_ROUTE as _f08_route,
                                    POOL_HAPPY as _F08_POOL_HAPPY,
                                    POOL_PARTIAL as _F08_POOL_PARTIAL,
                                    build_fill_exclusion as _f08_build_fill_exclusion,
                                    build_partial_exhaustion_info as _f08_build_exhaustion_info,
                                    build_partial_fill_events as _f08_build_fill_events,
                                    candidate_breakdown as _f08_get_breakdown,
                                    classify_pool as _f08_classify_pool,
                                    fill_score_start as _f08_get_fill_score_start,
                                    filter_visual_candidates as _f08_filter_candidates,
                                    order_candidates as _f08_order_candidates,
                                )

                                _f08_type_upper = _f08_ptype.upper()

                                # _f08_type_of y _f08_parent_categories_fn: definidas antes de la busqueda
                                # (E5 nivel 2, paso 3), sin cambios.

                                # ETAPA 1 -- categorias deseadas. En Fase A las decide SOLO el
                                # ancla: F08A_ROUTE.use_query_categories=False, por eso se pasa
                                # None como categorias de texto (divergencia con F-08C, pendiente
                                # de decision de producto -- Addendum A.2).
                                # (paso 3, 26/10/2026) Resolucion + peticion de pool: en
                                # _f08_prepare_pool_request(), MISMO codigo. Con el filtro activado ya
                                # se calculo antes de buscar; con el desactivado se calcula AQUI.
                                if _f08_prepared is None:
                                    _f08_prepared = _f08_prepare_pool_request()
                                _f08_resolution, _f08_pool_req = _f08_prepared
                                _f08_expanded_cats = _f08_resolution.categories
                                if _f08_resolution.expansion_error is not None:
                                    logger.debug(
                                        f"F-08 category expansion failed "
                                        f"(using exact type): {_f08_resolution.expansion_error}"
                                    )
                                elif _f08_resolution.source == "parent_group":
                                    logger.info(
                                        f"F-08 category expansion: "
                                        f"{_f08_type_upper!r} -> {_f08_expanded_cats} "
                                        f"({len(_f08_expanded_cats)} types from parent group)"
                                    )

                                # ── CONTRATO + G1 + G2 en Fase A (10/10/2026, gap G3) ───────
                                # Se cablea igual que F-08C (Addendum A.7 y siguientes). Lo que
                                # cierra este cableado:
                                #   E2 -- el ranking invertido vivia aqui todavia: en Turn 1 una
                                #         hermana visualmente parecida podia superar a un bolso
                                #         traido del catalogo (evidencia del 07/10, T1).
                                #   B5 -- la etiqueta de agotamiento usaba _f08_expanded_cats[0],
                                #         el primer hermano. Con la familia ordenada con el ancla
                                #         primero pasa a ser el tipo correcto.
                                #
                                # En Fase A la intencion es SIEMPRE similitud: esta ruta nunca
                                # consulta el texto de la query (F08A_ROUTE.use_query_categories
                                # =False, gap B7 abierto como decision de producto). Por eso aqui
                                # no hay rama query_text, a diferencia de F-08C.
                                # INTENT_* ya no se importan aqui (17/10/2026): la
                                # intencion la decide build_pool_request(), mas abajo.
                                from src.recommenders.recommendation_set import (
                                    ORIGIN_CATALOG as _F08_ORIGIN_CATALOG,
                                    ORIGIN_VISUAL as _F08_ORIGIN_VISUAL,
                                    RecommendationSet as _F08_RecommendationSet,
                                    RequestSpec as _F08_RequestSpec,
                                    tag_origin as _f08_tag_origin,
                                )
                                from src.recommenders.f08_similarity_resolution import (
                                    filter_fill_to_request as _f08_filter_fill,
                                    principal_first_enabled as _f08_principal_first,
                                    split_candidates_by_request as _f08_split_by_request,
                                )

                                # EXTRAIDO (17/10/2026, E5 nivel 2 paso 2): ver el comentario
                                # equivalente en F-08C. Aqui la decision era `if _f08_type_upper:`;
                                # build_pool_request() decide por _f08_resolution.source, que en
                                # Fase A vale "none" si y solo si el tipo en mayusculas esta vacio
                                # (_resolve_anchor_only). Equivalencia comprobada por el oraculo
                                # tests/characterization/equiv_harness_pool_request.py.
                                # (paso 3, 26/10/2026) _f08_pool_req ya viene de
                                # _f08_prepare_pool_request(), arriba.
                                _f08_intent = _f08_pool_req.intent
                                _f08_requested_ordered = _f08_pool_req.requested_ordered
                                _f08_requested = _f08_pool_req.requested

                                # Que puede entrar en el POOL (10/10/2026): lo pedido MAS sus
                                # alternativas declaradas -- ver el comentario equivalente en
                                # F-08C. En Fase A el efecto es mayor todavia: es la ruta del
                                # TURNO 1 y, al no haber nada mostrado, el pool no se amplia con
                                # el nivel 1. Para un ancla PANTALONES el pool pasa de admitir
                                # solo PANTALONES a admitir tambien FALDAS y LEGGINGS.
                                # Calculado por build_pool_request() (ver arriba). A diferencia de
                                # F-08C, Fase A no necesita alt_types por separado: solo lo usaba
                                # para construir pool_cats (y su log de expansion no lo imprime).
                                _f08_pool_cats = _f08_pool_req.pool_cats

                                def _f08_item_type_of(_item):
                                    # El contrato recibe items ya normalizados; el tipo vive en
                                    # product_data (el dict crudo del catalogo).
                                    return (_item.get("product_data") or {}).get("product_type", "")

                                def _f08_build_contract(_items, _exhausted):
                                    """
                                    Construye el RecommendationSet y lo deja en mcp_context.

                                    Centralizado para los CUATRO puntos de retorno de esta ruta
                                    (feliz, parcial, vacio y relleno-fallido): duplicarlo seria
                                    repetir el error que costo la divergencia F-08A/F-08C.
                                    """
                                    _rset = _F08_RecommendationSet.build(
                                        intent=_f08_intent,
                                        items=_items,
                                        request=_F08_RequestSpec(categories=_f08_requested),
                                        n_requested=n_recommendations,
                                        type_of=_f08_item_type_of,
                                        anchor_id=str(_f08_pid),
                                        anchor_type=_f08_ptype or None,
                                        route="f08a",
                                        exhausted=_exhausted,
                                    )
                                    mcp_context.recommendation_set = _rset  # type: ignore[attr-defined]
                                    logger.info(
                                        f"F-08 contrato: intent={_rset.intent} "
                                        f"principal={len(_rset.principal)}{_rset.principal.categories} "
                                        f"alternatives={len(_rset.alternatives)}"
                                        f"{_rset.alternatives.categories} "
                                        f"exhausted={_rset.principal.exhausted}"
                                    )
                                    return _rset.to_flat_list()

                                def _f08_tag_visual(_rec):
                                    """Marca procedencia visual con su rango y parecido REAL."""
                                    _rank, _score = _f08_visual_meta.get(str(_rec.get("id")), (None, None))
                                    return _f08_tag_origin(
                                        _rec, _F08_ORIGIN_VISUAL,
                                        visual_rank=_rank, visual_score=_score,
                                    )

                                # ETAPA 2 -- filtrar el pool visual. shown_products en Turn 1 es
                                # siempre set() vacio (se inicializa incondicionalmente al entrar
                                # en get_base_recommendations), pero se pasa igualmente para no
                                # depender de esa invariante.
                                # Desde el 10/10/2026 el criterio es _f08_pool_cats (familia +
                                # alternativas declaradas), no el grupo padre.
                                _f08_same_cat = _f08_filter_candidates(
                                    _f08_visual_ids, _f08_pid,
                                    _f08_pool_cats or _f08_expanded_cats,
                                    _f08_type_of, shown_products,
                                )
                                # E5 (26/10/2026): DEFENSA; con el filtro en la busqueda no deberia
                                # quitar nada. Si quita algo, los catalogos divergen: se avisa.
                                # Solo si el pool VIENE de la busqueda filtrada (ancla indexada): el
                                # fallback por imagen no se filtra (limitacion conocida, spec 4.2) y
                                # ahi el filtro posterior SI debe quitar -- avisar seria una falsa
                                # alarma en cada turno por imagen (lo detecto la prueba diferencial).
                                if _f08_filter_on and _f08_anchor_found and len(_f08_same_cat) != len(_f08_visual_ids):
                                    logger.warning(
                                        f"F-08 Fase A E5 divergencia: el filtro posterior quito "
                                        f"{len(_f08_visual_ids) - len(_f08_same_cat)} de "
                                        f"{len(_f08_visual_ids)} candidatos ya filtrados en la busqueda"
                                    )

                                # DIAGNOSTIC LOG (26/07/2026): mismo formato exacto que el de
                                # F-08C, para poder comparar ambos caminos directamente.
                                _f08_candidate_breakdown = _f08_get_breakdown(_f08_same_cat, _f08_type_of)
                                logger.info(
                                    f"F-08 candidate breakdown: {_f08_candidate_breakdown} "
                                    f"(anchor_type={_f08_type_upper!r}, "
                                    f"total={len(_f08_same_cat)})"
                                )

                                # ETAPA 3 -- particion T8 (tipo exacto del ancla primero) +
                                # intercalado NIVEL 1 por subtipo dentro de las hermanas
                                # (F08A_ROUTE.interleave_siblings=True). El "and _f08_tfidf" del
                                # guard original se preserva anulando el ancla de ranking cuando
                                # no hay indice TF-IDF.
                                _f08_same_cat = _f08_order_candidates(
                                    _f08_route, _f08_same_cat,
                                    _f08_resolution.anchor_type_for_ranking if _f08_tfidf else None,
                                    _f08_type_of,
                                )

                                # ETAPA 4 -- G1 (10/10/2026): la decision de ir al catalogo se
                                # toma sobre LO PEDIDO, no sobre el total del pool. Ver el
                                # comentario equivalente en F-08C: en T9 del 07/10, 11 candidatos
                                # con 1 solo bolso se leian como "tengo de sobra" y el catalogo
                                # no se consultaba nunca.
                                # Con RECS_PRINCIPAL_FIRST=0, own son TODOS los candidatos y la
                                # clasificacion vuelve a ser la anterior.
                                if _f08_principal_first():
                                    _f08_own, _f08_other = _f08_split_by_request(
                                        _f08_same_cat, _f08_requested, _f08_type_of,
                                    )
                                else:
                                    _f08_own, _f08_other = list(_f08_same_cat), []
                                _f08_pool_path = _f08_classify_pool(len(_f08_own), n_recommendations)
                                logger.info(
                                    f"F-08 reparto: pedido={_f08_requested_ordered} "
                                    f"en_pool={len(_f08_own)} otros={len(_f08_other)} "
                                    f"camino={_f08_pool_path}"
                                )

                                if _f08_pool_path == _F08_POOL_HAPPY:
                                    # G1: hay n o mas candidatos DE LO PEDIDO, asi que el corte
                                    # es homogeneo por construccion. El aviso de mezcla del
                                    # 26/07 ya no aplica (y Fase A nunca lo emitio).
                                    _f08_recs = []
                                    for _f08_rank, _f08_vid in enumerate(
                                        _f08_own[:n_recommendations]
                                    ):
                                        _f08_vprod = _f08_tfidf.id_index.get(str(_f08_vid))
                                        if _f08_vprod:
                                            _f08_recs.append(
                                                _f08_tag_visual(
                                                    normalize_recommendation_dict(
                                                        raw=_f08_vprod,
                                                        rank=_f08_rank,
                                                        score_start=1.0,
                                                        score_step=_f08_route.visual_score_step,
                                                        source=_f08_route.visual_source,
                                                    )
                                                )
                                            )

                                    if _f08_recs:
                                        logger.info(
                                            f"F-08 visual_similarity: {len(_f08_recs)} productos "
                                            f"(cat={_f08_type_upper!r}, "
                                            f"expanded_cats={_f08_expanded_cats}, "
                                            f"pool={len(_f08_visual_ids)}, "
                                            f"filtered={len(_f08_same_cat)})"
                                        )
                                        # exhausted=False: no se pregunto al catalogo porque no
                                        # hizo falta -- habia de sobra de lo pedido.
                                        return _f08_build_contract(_f08_recs, False)

                                elif _f08_pool_path == _F08_POOL_PARTIAL:
                                    # Relleno restringido (03/07/2026, portado de F-08C 17/06):
                                    # candidatos visuales parciales TAL CUAL + smart_fallback
                                    # anclado a las MISMAS categorias hermanas.
                                    # user_query=None bypassa PRIORIDAD 1; strict_category=True
                                    # evita mezclar categorias ajenas; evento extra al tipo del
                                    # ancla para que no quede fuera del top-3 de PRIORIDAD 2.
                                    #
                                    # all_products tiene el mismo riesgo de scoping que
                                    # get_parent_categories (BUG-REFACTOR-1): se asigna solo dentro
                                    # de "if use_diversification:" (Turn 2+), que en Turn 1 nunca
                                    # ejecuta. Se obtiene aqui de _f08_tfidf.product_data.
                                    #
                                    # try/except propio: si el relleno falla, se devuelven los
                                    # candidatos visuales solos en vez de perder tambien la parte
                                    # visual ya calculada (divergencia con F-08C, que no lo tiene).
                                    try:
                                        from src.recommenders.improved_fallback_exclude_seen import (
                                            ImprovedFallbackStrategies as _f08_ImprovedFallbackStrategies,
                                        )

                                        _f08_all_products = _f08_tfidf.product_data

                                        _f08_fill_events = _f08_build_fill_events(
                                            _f08_route, _f08_requested_ordered or _f08_expanded_cats,
                                            _f08_type_upper,
                                        )
                                        _f08_needed = n_recommendations - len(_f08_own)
                                        _f08_fill_exclude = _f08_build_fill_exclusion(
                                            shown_products, _f08_same_cat, _f08_pid,
                                        )

                                        _f08_fill_raw = await _f08_ImprovedFallbackStrategies.smart_fallback(
                                            user_id=validated_user_id,
                                            products=_f08_all_products,
                                            user_events=_f08_fill_events,
                                            n=_f08_needed,
                                            exclude_products=_f08_fill_exclude,
                                            user_query=None,  # bypass PRIORIDAD 1 -- ver comentario arriba
                                            strict_category=True,
                                        )
                                        # DEFENSA B2 (10/10/2026): smart_fallback puede devolver
                                        # productos de CUALQUIER categoria pese a
                                        # strict_category=True (cae a PRIORIDAD 3 "diverse"
                                        # cuando la categoria preferida queda en cero). Filtrar
                                        # ANTES de contar es lo que hace que el agotamiento se
                                        # mida bien y que no entre lenceria entre las
                                        # alternativas de un bolso.
                                        _f08_fill_raw = _f08_filter_fill(
                                            _f08_fill_raw, _f08_requested
                                        )

                                        # Agotamiento: el relleno estricto no alcanzo lo
                                        # necesario. La etiqueta sale de
                                        # _f08_requested_ordered[0], que con G2 es el TIPO DEL
                                        # ANCLA -- cierra el bug A.3.a tambien en Fase A.
                                        _f08_exhaustion = _f08_build_exhaustion_info(
                                            _f08_requested_ordered or _f08_expanded_cats,
                                            len(_f08_own),
                                            len(_f08_fill_raw), _f08_needed,
                                        )
                                        if _f08_exhaustion is not None:
                                            mcp_context.category_exhausted_info = _f08_exhaustion  # type: ignore[attr-defined]
                                            logger.info(
                                                f"F-08 category_exhausted: {len(_f08_own)} visual + "
                                                f"{len(_f08_fill_raw)} fill = {_f08_exhaustion['shown_count']} "
                                                f"(de {n_recommendations} pedidos, categoria="
                                                f"{_f08_exhaustion['category']!r}). LLM notificacion activada."
                                            )

                                        # PASO 1: lo pedido que ya habia en el pool.
                                        _f08_recs = []
                                        for _f08_rank, _f08_vid in enumerate(_f08_own):
                                            _f08_vprod = _f08_tfidf.id_index.get(str(_f08_vid))
                                            if _f08_vprod:
                                                _f08_recs.append(
                                                    _f08_tag_visual(
                                                        normalize_recommendation_dict(
                                                            raw=_f08_vprod,
                                                            rank=_f08_rank,
                                                            score_start=1.0,
                                                            score_step=_f08_route.visual_score_step,
                                                            source=_f08_route.visual_source,
                                                        )
                                                    )
                                                )

                                        # PASO 2: lo pedido traido del catalogo. origin=catalog:
                                        # sin vecindad visual medida, asi que visual_score queda
                                        # a None y el widget no debe mostrar porcentaje (E3).
                                        _f08_fill_score_start = _f08_get_fill_score_start(
                                            _f08_recs[-1]["score"] if _f08_recs else None
                                        )
                                        for _f08_fill_rank, _f08_fill_prod in enumerate(_f08_fill_raw):
                                            _f08_recs.append(
                                                _f08_tag_origin(
                                                    normalize_recommendation_dict(
                                                        raw=_f08_fill_prod,
                                                        rank=_f08_fill_rank,
                                                        score_start=_f08_fill_score_start,
                                                        score_step=_f08_route.fill_score_step,
                                                        source=_f08_route.fill_source,
                                                    ),
                                                    _F08_ORIGIN_CATALOG,
                                                )
                                            )

                                        # PASO 3 (G1): las hermanas del pool, como ALTERNATIVAS.
                                        _f08_alt_score_start = _f08_get_fill_score_start(
                                            _f08_recs[-1]["score"] if _f08_recs else None
                                        )
                                        for _f08_alt_rank, _f08_alt_id in enumerate(_f08_other):
                                            _f08_alt_prod = _f08_tfidf.id_index.get(str(_f08_alt_id))
                                            if _f08_alt_prod:
                                                _f08_recs.append(
                                                    _f08_tag_visual(
                                                        normalize_recommendation_dict(
                                                            raw=_f08_alt_prod,
                                                            rank=_f08_alt_rank,
                                                            score_start=_f08_alt_score_start,
                                                            score_step=_f08_route.visual_score_step,
                                                            source=_f08_route.visual_source,
                                                        )
                                                    )
                                                )

                                        if _f08_recs:
                                            logger.info(
                                                f"F-08 visual_partial_plus_fill: "
                                                f"{len(_f08_recs)} productos totales "
                                                f"(visual={len(_f08_own)}, "
                                                f"fill={len(_f08_fill_raw)}, "
                                                f"alt={len(_f08_other)}, "
                                                f"needed_fill={_f08_needed}, "
                                                f"cats={_f08_requested_ordered})"
                                            )
                                            return _f08_build_contract(
                                                _f08_recs, _f08_exhaustion is not None
                                            )

                                    except Exception as _f08_fill_err:
                                        logger.warning(
                                            f"F-08 partial_fill failed (using visual-only, "
                                            f"sin relleno): {_f08_fill_err}"
                                        )
                                        # Degradacion: se devuelve lo visual sin relleno, pero
                                        # SI con contrato -- lo pedido primero y las hermanas
                                        # como alternativas. Antes se devolvia la lista plana y
                                        # una hermana podia quedar por encima de lo pedido.
                                        _f08_recs = []
                                        for _f08_rank, _f08_vid in enumerate(_f08_own + _f08_other):
                                            _f08_vprod = _f08_tfidf.id_index.get(str(_f08_vid))
                                            if _f08_vprod:
                                                _f08_recs.append(
                                                    _f08_tag_visual(
                                                        normalize_recommendation_dict(
                                                            raw=_f08_vprod,
                                                            rank=_f08_rank,
                                                            score_start=1.0,
                                                            score_step=_f08_route.visual_score_step,
                                                            source=_f08_route.visual_source,
                                                        )
                                                    )
                                                )
                                        if _f08_recs:
                                            logger.info(
                                                f"F-08 visual_similarity (fill failed, visual-only): "
                                                f"{len(_f08_recs)} productos "
                                                f"(cat={_f08_type_upper!r}, "
                                                f"expanded_cats={_f08_expanded_cats}, "
                                                f"pool={len(_f08_visual_ids)})"
                                            )
                                            # exhausted=False: el relleno fallo, no sabemos si el
                                            # catalogo tenia mas. Afirmarlo seria inventar.
                                            return _f08_build_contract(_f08_recs, False)

                                elif _f08_principal_first() and _f08_requested:
                                    # CAMINO VACIO (10/10/2026): el pool trae candidatos pero
                                    # NINGUNO es de lo pedido. Mismo tratamiento que en F-08C:
                                    # preguntar al catalogo por la familia y, si tampoco hay,
                                    # devolver principal vacio + hermanas como alternativas con
                                    # exhausted=True. Nunca cero resultados, pero nunca relleno
                                    # mudo.
                                    try:
                                        from src.recommenders.improved_fallback_exclude_seen import (
                                            ImprovedFallbackStrategies as _f08_IFS_empty,
                                        )
                                        _f08_fill_raw = await _f08_IFS_empty.smart_fallback(
                                            user_id=validated_user_id,
                                            products=_f08_tfidf.product_data,
                                            user_events=_f08_build_fill_events(
                                                _f08_route, _f08_requested_ordered, _f08_type_upper,
                                            ),
                                            n=n_recommendations,
                                            exclude_products=_f08_build_fill_exclusion(
                                                shown_products, _f08_same_cat, _f08_pid,
                                            ),
                                            user_query=None,
                                            strict_category=True,
                                        )
                                        _f08_fill_raw = _f08_filter_fill(
                                            _f08_fill_raw, _f08_requested
                                        )
                                    except Exception as _f08_empty_err:
                                        logger.warning(
                                            f"F-08 catalogo sin respuesta en camino vacio: "
                                            f"{_f08_empty_err}"
                                        )
                                        _f08_fill_raw = []

                                    _f08_empty_exhausted = len(_f08_fill_raw) < n_recommendations
                                    if _f08_empty_exhausted:
                                        _f08_exhaustion = _f08_build_exhaustion_info(
                                            _f08_requested_ordered, 0,
                                            len(_f08_fill_raw), n_recommendations,
                                        )
                                        if _f08_exhaustion is not None:
                                            mcp_context.category_exhausted_info = _f08_exhaustion  # type: ignore[attr-defined]
                                            logger.info(
                                                f"F-08 category_exhausted (pool sin nada de lo "
                                                f"pedido): 0 visual + {len(_f08_fill_raw)} fill "
                                                f"(de {n_recommendations} pedidos, categoria="
                                                f"{_f08_exhaustion['category']!r}). "
                                                f"LLM notificacion activada."
                                            )

                                    _f08_recs = []
                                    for _f08_fill_rank, _f08_fill_prod in enumerate(_f08_fill_raw):
                                        _f08_recs.append(
                                            _f08_tag_origin(
                                                normalize_recommendation_dict(
                                                    raw=_f08_fill_prod,
                                                    rank=_f08_fill_rank,
                                                    score_start=1.0,
                                                    score_step=_f08_route.fill_score_step,
                                                    source=_f08_route.fill_source,
                                                ),
                                                _F08_ORIGIN_CATALOG,
                                            )
                                        )
                                    _f08_alt_score_start = _f08_get_fill_score_start(
                                        _f08_recs[-1]["score"] if _f08_recs else None
                                    )
                                    for _f08_alt_rank, _f08_alt_id in enumerate(_f08_other):
                                        _f08_alt_prod = _f08_tfidf.id_index.get(str(_f08_alt_id))
                                        if _f08_alt_prod:
                                            _f08_recs.append(
                                                _f08_tag_visual(
                                                    normalize_recommendation_dict(
                                                        raw=_f08_alt_prod,
                                                        rank=_f08_alt_rank,
                                                        score_start=_f08_alt_score_start,
                                                        score_step=_f08_route.visual_score_step,
                                                        source=_f08_route.visual_source,
                                                    )
                                                )
                                            )

                                    # SIEMPRE se devuelve el contrato, aunque quede vacio
                                    # (10/10/2026) -- ver el comentario equivalente en F-08C.
                                    # Fase A es la ruta del TURNO 1, asi que aqui la fuga era
                                    # especialmente visible: el primer contacto del usuario con
                                    # una categoria agotada acababa en productos sin relacion.
                                    logger.info(
                                        f"F-08 pool_sin_lo_pedido: "
                                        f"{len(_f08_recs)} productos totales "
                                        f"(catalogo={len(_f08_fill_raw)}, "
                                        f"alt={len(_f08_other)}, "
                                        f"cats={_f08_requested_ordered})"
                                    )
                                    return _f08_build_contract(
                                        _f08_recs, _f08_empty_exhausted
                                    )

                                # Si len(_f08_same_cat) == 0: no se hace nada -- cae al
                                # fallback estandar (hybrid_recommender.get_recommendations)
                                # justo despues de este bloque -- mismo patron de seguridad
                                # que F-08C ("si 0: cae a smart_fallback()").

                        except asyncio.TimeoutError:
                            logger.warning("F-08 visual_search timeout (>3s) — fallback a TF-IDF")
                        except Exception as _f08_err:
                            logger.warning(f"F-08 visual_search fallback a TF-IDF: {_f08_err}")
                    # ── Fin F-08 Fase A+A.5 ──────────────────────────────────────────

                    recommendations = await main_unified_redis.hybrid_recommender.get_recommendations(
                        user_id=validated_user_id,
                        product_id=tfidf_product_id,
                        n_recommendations=n_recommendations,
                        user_query=conversation_query  # ✨ NUEVO: Permite detección de categoría desde query
                    )
                    logger.info(f"✅ Base recommendations obtained: {len(recommendations)} items")

                    # DECISION DE PRODUCTO (19/06/2026, Caso A): coherencia categorica estricta
                    # cuando el usuario nombra una categoria explicita ("muestrame calzones") y
                    # strict_category=True (ya aplicado en enhanced_hybrid_recommender.py /
                    # hybrid_recommender.py) bloqueo el relleno con otras categorias. Detectamos
                    # el deficit resultante y senalizamos al LLM, igual que en F-08C y el Caso B.
                    # Import local con alias: el import agrupado de extract_categories_from_query
                    # mas arriba esta dentro del bloque F-08C (Turn 2+), que no corre en este
                    # camino "Standard recommendations" (primera llamada) -- mismo patron de
                    # BUG-REFACTOR-1 (18/06/2026). El alias evita cualquier interaccion con el
                    # nombre usado en el bloque F-08C.
                    try:
                        from src.recommenders.improved_fallback_exclude_seen import (
                            extract_categories_from_query as _std_extract_categories,
                            get_concrete_categories as _std_get_concrete_categories,
                        )
                        _std_available_categories = _std_get_concrete_categories()
                        _std_query_categories = _std_extract_categories(
                            conversation_query, _std_available_categories
                        )
                    except Exception as _std_cat_err:
                        logger.warning(f"Standard recommendations category detection failed: {_std_cat_err}")
                        _std_query_categories = []

                    # DECISION DE PRODUCTO (19/06/2026, Opcion 1): la deteccion original
                    # solo comparaba len(recommendations) < n_recommendations -- pero
                    # enhanced_hybrid_recommender.py tiene su PROPIO mecanismo de relleno
                    # ("additional_recs", activado cuando faltan resultados tras filtrar
                    # interactuados) que completa hasta n llamando a
                    # get_diverse_category_products(), SIN pasar por strict_category.
                    # Resultado real observado en produccion: "muestrame pantalones" con
                    # PANTALONES agotado devolvia 8 productos (6 PANTALONES + 2 de otras
                    # categorias) sin avisar, porque el conteo final SI llegaba a
                    # n_recommendations -- la condicion original nunca se activaba.
                    #
                    # FIX: en vez de comparar solo el conteo total, comparamos las
                    # categorias presentes en el resultado final contra la categoria
                    # pedida. Notificamos si HAY items de otra categoria (sin importar
                    # si el conteo total alcanzo n) O si los items de la categoria
                    # pedida por si solos no alcanzan n. Revisamos tanto "category"
                    # (esquema de get_diverse_category_products / get_popular_products)
                    # como "product_type" (esquema de smart_sample_across_categories /
                    # get_personalized_fallback, que preservan el producto completo).
                    if _std_query_categories:
                        _std_query_cats_upper = {c.upper() for c in _std_query_categories}
                        _std_on_category_count = sum(
                            1 for rec in recommendations
                            if (rec.get("category") or rec.get("product_type", "")).upper()
                            in _std_query_cats_upper
                        )
                        _std_off_category_count = len(recommendations) - _std_on_category_count

                        if _std_off_category_count > 0 or _std_on_category_count < n_recommendations:
                            mcp_context.category_exhausted_info = {  # type: ignore[attr-defined]
                                "category": _std_query_categories[0],
                                "shown_count": _std_on_category_count,
                                # Caso A SI puede mezclar categorias (via el relleno de
                                # enhanced_hybrid_recommender.py) -- total_count puede ser
                                # mayor a shown_count. El prompt usa la diferencia para
                                # distinguir agotamiento parcial-sin-mezcla de
                                # parcial-con-mezcla de total-con-mezcla.
                                "total_count": len(recommendations),
                            }
                            logger.info(
                                f"Standard recommendations category_exhausted (Caso A): "
                                f"{_std_on_category_count} de la categoria pedida + "
                                f"{_std_off_category_count} de otras categorias "
                                f"(total={len(recommendations)}/{n_recommendations}, "
                                f"categoria={_std_query_categories[0]!r}). LLM notificacion activada."
                            )

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

        # FASE 4: PERSONALIZACION CON CACHE INTELIGENTE
        #
        # OJO con `ai_response`: es un MARCADOR que la personalizacion de abajo
        # sobrescribe. Si esa personalizacion no corre, este texto llega TAL
        # CUAL al usuario -- y eso paso el 15/10/2026, cuando con la categoria
        # agotada el chat respondio en ingles "I found 0 recommendations for
        # your query: '...'". Por eso ahora es un texto en espanol que se puede
        # leer sin verguenza si vuelve a aflorar.
        final_response = {
            "recommendations": base_recommendations,
            "ai_response": (
                "No he encontrado productos para esta búsqueda. "
                "¿Quieres que te muestre otra cosa?"
                if not base_recommendations
                else "Aquí tienes algunas opciones que pueden encajar."
            ),
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
        # FIX (15/10/2026): antes la condicion exigia `base_recommendations`, asi
        # que con CERO productos la personalizacion no corria y el marcador de
        # arriba llegaba intacto al usuario. Justo el caso que mas necesita una
        # buena redaccion: cuando no queda nada, el texto ES la respuesta.
        #
        # Ahora tambien corre cuando existe el contrato -- hay hechos que
        # comunicar (principal=0, alternatives=0, exhausted=True) y un prompt
        # preparado para ellos, que ademas ofrece una via para continuar.
        # Verificado que el motor tolera lista vacia: el unico acceso posicional
        # (top_recs[0]) esta guardado por `elif top_recs:` y recs_summary sobre
        # vacio da "".
        _has_contract = getattr(mcp_context, "recommendation_set", None) is not None if mcp_context else False

        # REINICIO POR CATEGORIA (16/10/2026): marcar el contexto para que el
        # redactor lo reconozca. Sin esto, el turno que viene de "ver X otra
        # vez" se redacta como si fuera la primera vez ("He encontrado tres
        # pantalones...") y el usuario ve productos repetidos sin explicacion:
        # parece un fallo, no una accion suya.
        if mcp_context is not None:
            mcp_context.category_reset_notice = (  # type: ignore[attr-defined]
                str(reset_category).strip().upper() if reset_category else None
            )

        if mcp_engine and mcp_context and (base_recommendations or _has_contract):
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
                    # - 8.0s: valor intermedio (el label en el except fue heredado)
                    # - 12.0s: valor actual (21/03/2026) — outer safety valve que cubre
                    #          el peor caso de Claude o LFM con margen real.
                    #
                    # POR QUÉ 12s:
                    # Claude API tarda ~7.5s en condiciones normales (warm TCP).
                    # LFM warm tarda ~440ms, pero el inner timeout de LFM (10s desde
                    # LFM start = ~10.6s desde este outer) actua como primera linea
                    # de defensa. El outer de 12s actua como safety valve externo
                    # por si el inner no dispara antes (ej. ruta solo-Claude sin LFM).
                    # Diagnostico confirmado 26/05/2026: warm flow = 1.973s (80.3% mejora).
                    personalization_result = await asyncio.wait_for(
                        mcp_engine.generate_personalized_response(
                            mcp_context=mcp_context,
                            recommendations=base_recommendations,
                            # FIX (19/04/2026 — BUG-LANG-MCP):
                            # El engine re-detectaba idioma desde la query con _detect_user_language(),
                            # que usa una lista de keywords limitada. Tokens como "i'm" (contraccion)
                            # no matchean el keyword "i" → score EN=0 → default "es".
                            # Ejemplo: "I'm looking for elegant dresses" → detectado como ES → respuesta en español.
                            #
                            # El router ya detecta correctamente con detect_language_from_text()
                            # que usa patrones regex mas robustos. Pasando el idioma aqui,
                            # el engine usa el resultado del router en lugar de re-detectar.
                            detected_language=language,
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
                logger.warning("⏰ MCP personalization timeout (12.0s) - using base recommendations")
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
        # FASE 3.1 (13/10/2026) -- los bloques del contrato viajan al widget.
        #
        # El router NO comparte el objeto de contexto con este handler (carga el
        # suyo a partir del session_id), asi que mcp_context.recommendation_set
        # no le llega por si solo: tiene que ir en la respuesta.
        #
        # Va como IDENTIFICADORES, no como productos: `recommendations` sigue
        # siendo la unica fuente de items, ya ordenada principal-y-luego-
        # alternativas. Duplicarlos crearia dos fuentes de verdad que pueden
        # divergir en silencio -- ver to_api_dict().
        #
        # None cuando el turno no construyo contrato (rutas de outfit, estandar,
        # o sin recomendaciones). El consumidor debe tratar None como "pinta la
        # lista plana como siempre": es lo que permite que el widget actual siga
        # funcionando sin cambios.
        _rset_api = None
        try:
            _rset_obj = getattr(mcp_context, "recommendation_set", None) if mcp_context else None
            if _rset_obj is not None:
                _rset_api = _rset_obj.to_api_dict()
                logger.info(
                    "recommendation_blocks expuestos: principal=%d alternatives=%d exhausted=%s",
                    len(_rset_api["principal"]["product_ids"]),
                    len(_rset_api["alternatives"]["product_ids"]),
                    _rset_api["principal"]["exhausted"],
                )
        except Exception as _rset_err:  # degradacion: nunca romper la respuesta
            logger.warning("recommendation_blocks no serializables: %s", _rset_err)
            _rset_api = None
        final_response["recommendation_blocks"] = _rset_api

        # GAP B1 — FIX DEL FIX (13/10/2026).
        #
        # El router venia guardando como ancla del turno su `validated_product_id`,
        # que es el HANDLE que manda el widget ("palazzo-silvia-negro"), no el id
        # numerico del producto. `shown_products` contiene ids numericos
        # ('9978565329205'), asi que el handle NUNCA coincidia y la exclusion no
        # surtia efecto -- aunque el log diera sensacion de funcionar.
        #
        # Visto en produccion el 13/10:
        #     First 3 recommendation IDs: ['9978594394421', ...]
        #     anchor_product_id (B1): palazzo-silvia-negro
        #
        # Error silencioso por naturaleza: ambos valores son str, set.add() acepta
        # cualquier cosa y `in` devuelve False sin avisar. Un conjunto de exclusion
        # con un elemento mal formado no falla: simplemente no excluye nada.
        #
        # Aqui se expone el id YA RESUELTO (el mismo que usa la busqueda visual),
        # para que el router guarde eso y no el handle. Si no hay contexto de
        # producto se deja None: sin id fiable es preferible no excluir nada a
        # excluir una cadena que no corresponde a ningun producto.
        _resolved_anchor = None
        try:
            _ctx_prod = getattr(mcp_context, "current_product_context", None) if mcp_context else None
            if _ctx_prod and _ctx_prod.get("id"):
                _resolved_anchor = str(_ctx_prod["id"])
        except Exception as _anchor_err:
            logger.warning("no se pudo resolver el ancla para B1: %s", _anchor_err)
        final_response["resolved_anchor_product_id"] = _resolved_anchor

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