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

                                # GAP B FIX (11/07/2026): _B08_TYPE_TO_CAT (el diccionario
                                # que vivia aqui antes) usaba claves genericas en espanol
                                # ("accesorios", "bolsos", "calzado") que NUNCA calzaban con
                                # ningun product_type real de Shopify (los reales son "AROS",
                                # "CARTERAS", "ZAPATOS", etc. -- confirmado revisando cada
                                # clave contra el catalogo real). Efecto: _b08_own_cat quedaba
                                # "" (vacio) para casi cualquier producto ancla de accesorios,
                                # bolsos, zapatos o enteritos, y la exclusion de "no recomendar
                                # la propia categoria del producto ancla" nunca se aplicaba en
                                # esos casos -- ej. viendo un producto AROS, "completa el
                                # outfit" buscaba accesorios (bucket "accessory") sin
                                # excluirlo, aunque el ancla ya fuera un accesorio.
                                #
                                # Fix: eliminar el diccionario duplicado y mover aqui
                                # _B08_SHOPIFY_TO_OUTFIT_CAT (antes solo se definia mas abajo,
                                # para el narrowing de Hallazgo 2) como unica fuente de verdad
                                # -- ya esta alineado 1:1 con los product_type reales del
                                # catalogo, a diferencia del diccionario viejo.
                                _B08_SHOPIFY_TO_OUTFIT_CAT = {
                                    "AROS": "accessory", "COLLARES": "accessory",
                                    "BRAZALETES": "accessory", "BRAZALETE": "accessory",
                                    "CINTURONES": "accessory", "TOCADOS": "accessory",
                                    "ALAS DE NOVIA": "accessory",
                                    "CARTERAS": "bag", "CLUTCH": "bag",
                                    "VESTIDOS CORTOS": "dress", "VESTIDOS LARGOS": "dress",
                                    "VESTIDOS MIDIS": "dress",
                                    "ENTERITOS CORTOS": "enterito", "ENTERITOS LARGOS": "enterito",
                                    "TOPS": "top", "BRALETTES": "top",
                                    "PANTALONES": "bottom", "FALDAS": "bottom",
                                    "CAPAS BORDADAS": "outerwear", "CAPAS GASA": "outerwear",
                                    "KIMONOS": "outerwear",
                                    "ZAPATOS": "shoes",
                                    "CONJUNTOS FALDAS": "conjunto",
                                    "CONJUNTOS PANTALONES": "conjunto",
                                }
                                # _b08_ptype llega en minusculas (linea anterior) -- .upper()
                                # para calzar con las claves (mayusculas) del diccionario.
                                _b08_own_cat = _B08_SHOPIFY_TO_OUTFIT_CAT.get(_b08_ptype.upper(), "")

                                # GAP 2 FIX (13/07/2026): grupos de conflicto de "slot" de
                                # prenda. Antes solo se excluia _b08_own_cat (la categoria
                                # exacta del producto ancla), sin modelar que otras categorias
                                # ocupan el MISMO slot corporal y por tanto tampoco son
                                # complementarias. Confirmado con evidencia real de produccion
                                # (13/07/2026): ancla VESTIDOS CORTOS (dress) devolvia
                                # categories=['top','accessory','bag','enterito','outerwear'] --
                                # "top" y "enterito" son incompatibles con un vestido (prenda de
                                # cuerpo completo), no complementos.
                                #
                                # dress/enterito son prendas de cuerpo completo -- conflictan
                                # entre si y con "top" (no tiene sentido sugerir un top sobre/
                                # bajo un vestido o enterito). top/bottom se necesitan
                                # mutuamente pero no a dress/enterito (serian "otro outfit
                                # completo", no un complemento). accessory/bag/outerwear/shoes
                                # son compatibles con cualquier prenda base -- sin conflictos,
                                # no aparecen como llaves aqui.
                                #
                                # Se aplica de forma UNIVERSAL: tanto a la lista amplia por
                                # defecto como a la categoria detectada explicitamente por texto
                                # (ver _b08_mapped_cats mas abajo) -- decision de producto
                                # consciente (sesion 13/07/2026): la deteccion de categoria por
                                # texto ya tuvo falsos positivos por colision de keywords en
                                # esta misma sesion (ej. "outfit" disparando CONJUNTOS), asi que
                                # confiar ciegamente en una "peticion explicita" puede estar
                                # propagando un bug de deteccion en vez de una intencion real
                                # del usuario. Consistente con el principio de coherencia
                                # categorica estricta (strict_category=True) ya establecido en
                                # otras partes del sistema.
                                _B08_SLOT_CONFLICTS = {
                                    "dress":    {"top", "bottom", "enterito"},
                                    "enterito": {"top", "bottom", "dress"},
                                    "top":      {"dress", "enterito"},
                                    "bottom":   {"dress", "enterito"},
                                }
                                # FIX (14/07/2026): "accessory" y "bag" son buckets MULTI-TIPO
                                # -- varios product_type concretos de Shopify caen en el mismo
                                # bucket (AROS/COLLARES/BRAZALETES/CINTURONES/TOCADOS/ALAS DE
                                # NOVIA -> accessory; CARTERAS/CLUTCH -> bag). Auto-excluir el
                                # bucket ENTERO cuando el ancla es de ese bucket bloqueaba
                                # combinaciones legitimas entre tipos hermanos (ej. ancla AROS
                                # nunca podia sugerir un COLLAR; ancla CLUTCH nunca podia
                                # sugerir una CARTERA), ademas del bug ya confirmado en
                                # produccion (13/07/2026): ancla AROS + "que accesorios
                                # combinan" devolvia SOLO 'bag' (5 clutch, sin variedad),
                                # porque 'accessory' -- lo unico que el usuario pidio -- se
                                # auto-excluia por ser tambien la categoria del ancla.
                                #
                                # A diferencia de dress/enterito/top/bottom (una sola prenda de
                                # ese tipo por outfit), accessory y bag son inherentemente
                                # multi-item: aretes+collar+pulsera es un combo de estilismo
                                # normal, y una cartera+clutch son piezas intercambiables, no
                                # conflictivas. La exclusion del MISMO tipo concreto (ej. no
                                # mas AROS si el ancla ya es AROS, no mas CLUTCH si el ancla ya
                                # es CLUTCH) se maneja aparte, a nivel de producto individual,
                                # con _b08_is_same_type() mas abajo -- no a nivel de bucket.
                                _b08_excluded_cats = (
                                    _B08_SLOT_CONFLICTS.get(_b08_own_cat, set())
                                    | (set() if _b08_own_cat in {"accessory", "bag"} else {_b08_own_cat})
                                )

                                # HALLAZGO 2 FIX (06/07/2026): leer la categoria especifica
                                # que el usuario pidio en su consulta, en vez de siempre usar
                                # la lista fija de 6 categorias.
                                #
                                # Por que: _b08_target_cats era SIEMPRE la misma lista fija
                                # (menos la categoria propia del producto), sin importar si
                                # el usuario pidio "completa el outfit" (amplio) o "que
                                # accesorios combinan" (especifico). Confirmado con evidencia
                                # real (sesion 05/07/2026): "Que accesorios combinan con este
                                # vestido?" devolvio categories=['top','accessory','bag',
                                # 'enterito','outerwear'] -- 4 categorias que el usuario nunca
                                # pidio, mezcladas con los accesorios que si pidio.
                                #
                                # Mecanismo: reusa extract_categories_from_query() (ya usada
                                # en F-08C y en el bloque Standard recommendations) para
                                # detectar si el usuario menciono una categoria Shopify
                                # explicita (ej. "accesorios" -> expande via CATEGORY_KEYWORDS
                                # a AROS/COLLARES/BRAZALETES/etc). Si detecta algo, mapea esos
                                # tipos concretos a su bucket de outfit-category
                                # (accessory/bag/dress/top/enterito/outerwear/bottom) y usa
                                # SOLO esos como target_categories -- nunca la categoria
                                # propia del producto ancla. Si no detecta nada (consulta
                                # generica tipo "completa el outfit"), mantiene el
                                # comportamiento amplio actual sin cambios.
                                #
                                # Import lazy: mismo patron defensivo ya usado para
                                # get_parent_categories en F-08 Fase A (BUG-REFACTOR-1,
                                # 18/06/2026) -- extract_categories_from_query y
                                # get_concrete_categories estan importados arriba SOLO
                                # dentro del bloque "if use_diversification:" (Turn 2+).
                                # F-08B puede activarse en Turn 1 tambien (ver comentario de
                                # trigger arriba), donde esa rama nunca ejecuta -- sin este
                                # import lazy, usarlas aqui lanzaria UnboundLocalError.
                                # _B08_SHOPIFY_TO_OUTFIT_CAT ya quedo definido arriba (Gap B
                                # fix, 11/07/2026), junto con _b08_own_cat -- se reusa aqui tal
                                # cual para el narrowing de Hallazgo 2, sin redefinirlo.
                                _b08_query_target_cats = None
                                try:
                                    from src.recommenders.improved_fallback_exclude_seen import (
                                        extract_categories_from_query as _b08_extract_cats,
                                        get_concrete_categories as _b08_get_concrete_cats,
                                    )
                                    _b08_available_cats = _b08_get_concrete_cats()
                                    _b08_detected = _b08_extract_cats(
                                        conversation_query, _b08_available_cats
                                    )
                                    if _b08_detected:
                                        _b08_mapped_cats = {
                                            _B08_SHOPIFY_TO_OUTFIT_CAT[c.upper()]
                                            for c in _b08_detected
                                            if c.upper() in _B08_SHOPIFY_TO_OUTFIT_CAT
                                        }
                                        # GAP 2 FIX (13/07/2026): antes solo .discard(_b08_own_cat)
                                        # -- se cambia a resta de conjunto completa
                                        # (_b08_excluded_cats incluye _b08_own_cat + conflictos de
                                        # slot) para que una categoria detectada por texto que
                                        # sea incompatible con el ancla (ej. "top" detectado sobre
                                        # un vestido) tampoco pase, aplicando el mismo criterio
                                        # que a la lista amplia por defecto (ver comentario
                                        # completo junto a _B08_SLOT_CONFLICTS mas arriba).
                                        _b08_mapped_cats -= _b08_excluded_cats
                                        if _b08_mapped_cats:
                                            _b08_query_target_cats = list(_b08_mapped_cats)
                                            logger.info(
                                                f"F-08B query category detected: "
                                                f"{_b08_detected} -> {_b08_query_target_cats} "
                                                f"(narrowing target_categories)"
                                            )
                                except Exception as _b08_detect_err:
                                    logger.debug(
                                        f"F-08B category detection from query failed "
                                        f"(using default broad categories): {_b08_detect_err}"
                                    )

                                # GAP 2 FIX (13/07/2026): lista de candidatos ampliada de 6 a
                                # 8 categorias:
                                #   + "bottom" (pantalones/faldas) -- NUNCA se habia agregado
                                #     pese a estar probada y funcionando en el embedding-service
                                #     desde la implementacion original de S1 (13/05/2026):
                                #     CATEGORY_TEXT_PROMPTS la incluye, tiene 69 productos
                                #     mapeados (2.3% del catalogo). Confirmado en la
                                #     documentacion del proyecto -- era un olvido de
                                #     implementacion, no una limitacion tecnica. Sin esto,
                                #     ningun producto TOP recibia jamas una recomendacion de
                                #     pantalon/falda desde F-08B.
                                #   + "shoes" -- antes solo alcanzable via narrowing explicito
                                #     por texto ("que zapatos combinan"). No conflictua con
                                #     nada (slot independiente, "pies") y ya esta validado en
                                #     produccion (fix ZAPATOS->shoes, sesion 11/07/2026). Los 9
                                #     prompts de categoria ya estan precalculados en el warmup
                                #     del embedding-service (_text_embed_cache), asi que
                                #     agregarla no anade llamadas de encoding, solo una busqueda
                                #     FAISS adicional sobre vectores ya en cache.
                                #
                                # Deliberadamente FUERA de la lista por defecto (decision de
                                # producto, no limitacion tecnica):
                                #   - "conjunto": es un set de dos piezas vendido como unidad,
                                #     no un "complemento" -- mostrar conjuntos random en un
                                #     "completa el outfit" generico no tiene el mismo sentido
                                #     que sugerir zapatos/accesorios. Investigacion dedicada
                                #     pendiente (Gap 3, sesion 13/07/2026).
                                #   - "lingerie": mezclar ropa interior en sugerencias
                                #     genericas puede sentirse invasivo si el usuario no lo
                                #     pidio explicitamente. Ninguna de las dos aparece mapeada
                                #     como target en _B08_SHOPIFY_TO_OUTFIT_CAT, asi que ya
                                #     estaban excluidas por omision -- no requirio cambio
                                #     adicional de codigo.
                                _B08_FULL_CANDIDATE_CATS = [
                                    "dress", "top", "bottom", "accessory", "bag",
                                    "enterito", "outerwear", "shoes",
                                ]
                                _b08_target_cats = _b08_query_target_cats if _b08_query_target_cats else [
                                    c for c in _B08_FULL_CANDIDATE_CATS
                                    if c not in _b08_excluded_cats
                                ]

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
                                    for _b08_bt_bucket in list(_b08_outfit_cats.keys()):
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
                                # ANCLA), ignorando por completo si el usuario ya habia sido
                                # explicito sobre que categoria queria en su consulta. Confirmado
                                # en produccion (27/07/2026): ancla AROS + "con que vestidos
                                # combina mejor?" detectaba correctamente ['dress'] mas arriba en
                                # el flujo (log "F-08B query category detected"), pero F-08B.2 lo
                                # descartaba en silencio y devolvia solo accesorios (COLLARES,
                                # CLUTCH, CINTURONES) -- la peticion explicita del usuario nunca
                                # tuvo prioridad sobre el mapa de complemento del ancla.
                                #
                                # _b08_query_target_cats se computa mas arriba (bloque F-08 Fase
                                # B principal, dentro del gate VISUAL_SEARCH_ENABLED) -- puede no
                                # estar definida si ese bloque nunca corrio, de ahi el acceso
                                # seguro via locals().get() en vez de referenciar la variable
                                # directamente (evita UnboundLocalError/NameError).
                                _b08b2_query_cats = locals().get("_b08_query_target_cats")
                                if _b08b2_query_cats:
                                    # El usuario nombro una categoria explicita -- tiene prioridad
                                    # absoluta sobre el mapa de complemento del ancla. Se resuelve
                                    # a tipos Shopify reales via product_taxonomy.py (unica fuente
                                    # de verdad ya establecida en Fase 1b) en vez de mantener un
                                    # tercer mapa hardcodeado en paralelo.
                                    from src.recommenders.product_taxonomy import (
                                        types_in_outfit_slot as _b08b2_types_in_slot,
                                    )
                                    _complement_cats = [
                                        _t
                                        for _slot in _b08b2_query_cats
                                        for _t in _b08b2_types_in_slot(_slot)
                                        if _t != _outfit_product_type
                                    ]
                                    logger.info(
                                        f"F-08B.2 outfit_completion: categoria EXPLICITA de la "
                                        f"consulta {_b08b2_query_cats} tiene prioridad sobre el "
                                        f"mapa de complemento del ancla (type={_outfit_product_type!r}) "
                                        f"-- tipos resueltos: {_complement_cats}"
                                    )
                                else:
                                    # Sin categoria explicita en la consulta -- comportamiento
                                    # original sin cambios: mapa de complemento keyed por el tipo
                                    # del ancla.
                                    _OUTFIT_COMPLEMENT_MAP = {
                                        "KIMONOS":         ["AROS", "COLLARES", "CLUTCH", "CINTURONES", "BRAZALETES"],
                                        "TAPADOS":         ["AROS", "COLLARES", "CLUTCH", "CINTURONES", "BRAZALETES"],
                                        "VESTIDOS LARGOS": ["AROS", "COLLARES", "CLUTCH", "TOCADOS", "CINTURONES"],
                                        "VESTIDOS CORTOS": ["AROS", "CLUTCH", "CINTURONES", "BRAZALETES"],
                                        "VESTIDOS MIDIS":  ["AROS", "COLLARES", "CLUTCH", "TOCADOS"],
                                        "NOVIAS LARGOS":   ["TOCADOS", "CLUTCH", "AROS", "BRAZALETES"],
                                        "NOVIAS CORTOS":   ["TOCADOS", "AROS", "CLUTCH", "BRAZALETES"],
                                        "FALDAS":          ["TOPS", "AROS", "CINTURONES", "BRAZALETES"],
                                        "TOPS":            ["FALDAS", "AROS", "COLLARES", "CLUTCH"],
                                        "BLUSAS":          ["FALDAS", "AROS", "COLLARES", "CLUTCH"],
                                        "ENTERITOS LARGOS": ["CINTURONES", "AROS", "CLUTCH", "COLLARES"],
                                        "ENTERITOS CORTOS": ["CINTURONES", "AROS", "CLUTCH", "BRAZALETES"],
                                    }
                                    _complement_cats = [
                                        _c for _c in _OUTFIT_COMPLEMENT_MAP.get(
                                            _outfit_product_type,
                                            ["AROS", "COLLARES", "CLUTCH", "CINTURONES"],  # fallback genérico
                                        )
                                        if _c != _outfit_product_type
                                    ]
                                    # FIX (17/07/2026): _OUTFIT_COMPLEMENT_MAP solo tiene entradas
                                    # para tipos de PRENDA (KIMONOS, VESTIDOS*, TOPS, FALDAS, etc.)
                                    # -- nunca se agregaron entradas para tipos de ACCESORIO (AROS,
                                    # COLLARES, CLUTCH, CARTERAS, BRAZALETES, CINTURONES, TOCADOS).
                                    # Cuando el ancla es un accesorio, .get(_outfit_product_type, ...)
                                    # no encuentra clave y cae al fallback generico -- que incluye
                                    # literalmente "AROS", "COLLARES" y "CLUTCH" sin saber cual de
                                    # esos 3 es el propio ancla. Confirmado con evidencia real de
                                    # produccion + screenshot (16-17/07/2026): ancla AROS DANAE +
                                    # "que accesorios combinan con este?" -> F-08B.2 (activo porque
                                    # F-08B primario fallo con 413) devolvia
                                    # complement_cats=['AROS','COLLARES','CLUTCH','CINTURONES'],
                                    # resultando en 4 de 8 productos siendo mas Aros.
                                    # Este filtro cubre TANTO el fallback generico como cualquier
                                    # entrada especifica del mapa que en el futuro pudiera incluirse
                                    # a si misma por error -- misma defensa, un solo lugar.

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

                                    # pool visual: top_k=50 para tener margen tras filtrado
                                    if _c08_boost_text:
                                        _c08_visual_ids = await asyncio.wait_for(
                                            _c08_colbert.search_by_product_id_with_text_boost(
                                                _c08_pid,
                                                boost_text=_c08_boost_text,
                                                alpha=_c08_boost_alpha,
                                                top_k=50,
                                            ),
                                            timeout=3.0,
                                        )
                                        logger.info(
                                            f"F-08C: composite embedding boost activo "
                                            f"(type={_c08_ctx_type_upper_early}, alpha={_c08_boost_alpha})"
                                        )
                                    else:
                                        _c08_visual_ids = await asyncio.wait_for(
                                            _c08_colbert.search_by_product_id(_c08_pid, top_k=50),
                                            timeout=3.0,
                                        )

                                    if _c08_visual_ids and _c08_tfidf and hasattr(_c08_tfidf, "id_index"):
                                        # Categorias deseadas: intentar detectar desde el query
                                        # usando el catalogo completo de tipos (no un sample).
                                        # all_products esta disponible en este scope.
                                        _c08_all_types = set(
                                            p.get("product_type", "")
                                            for p in all_products if p.get("product_type")
                                        )
                                        _c08_query_cats = extract_categories_from_query(
                                            conversation_query,
                                            available_categories=_c08_all_types,
                                        ) or []

                                        # Fallback: si la query no menciona una categoria
                                        # explicita (ej. "similares a este"), usar la
                                        # categoria del producto actual como filtro.
                                        # Esto evita cross-category contamination (9 CHF
                                        # accessories en resultados de vestidos).
                                        #
                                        # FIX (16/06/2026 — F-08C accessory gap):
                                        # Usar solo el tipo exacto (_c08_ctx_type="AROS") resulta
                                        # en < 8 candidatos en el pool FAISS para categorias con
                                        # pocos productos (AROS, COLLARES, CLUTCH, etc.).
                                        # El pool FAISS de un AROS devuelve vecinos mixtos
                                        # (AROS + COLLARES + BRAZALETES + CLUTCH), todos
                                        # visualmente similares, pero el filtro strict solo
                                        # acepta "AROS" -> muy pocos pasan -> F-08C no activa.
                                        #
                                        # Solucion: expandir a los hermanos del mismo padre
                                        # para capturar todo el grupo categorial:
                                        #   AROS          -> ACCESSORIES -> [AROS, COLLARES, BRAZALETES, ...]
                                        #   VESTIDOS CORTOS -> VESTIDOS  -> [VESTIDOS CORTOS, LARGOS, MIDIS]
                                        # Mantiene coherencia semantica (todos son del mismo
                                        # "mundo visual") sin cruzar categorias no relacionadas.
                                        # HALLAZGO T8 FIX (06/07/2026): None por defecto -- solo
                                        # se setea dentro de la rama de expansion por contexto
                                        # (mas abajo), NUNCA en la rama de deteccion por texto
                                        # explicito. Usado para la particion estable del pool
                                        # justo antes de cortar a n_recommendations (ver mas
                                        # abajo, bloque de filtrado de _c08_candidates).
                                        _c08_anchor_type_for_ranking = None
                                        # FIX (18/07/2026): _c08_ctx_type se calcula ANTES del
                                        # if, porque ahora se necesita en dos ramas distintas
                                        # (antes solo se calculaba dentro de "if not
                                        # _c08_query_cats"). Ver razon completa mas abajo.
                                        _c08_ctx_type = mcp_context.current_product_context.get(
                                            "product_type", ""
                                        ) if mcp_context and getattr(
                                            mcp_context, "current_product_context", None
                                        ) else ""

                                        if not _c08_query_cats:
                                            if _c08_ctx_type:
                                                # HALLAZGO T8 FIX: guardar el tipo exacto para
                                                # priorizarlo luego en el ranking del pool -- solo
                                                # llegamos aqui cuando la categoria vino del
                                                # contexto del producto (no de texto explicito),
                                                # asi que priorizar el tipo del ancla es coherente
                                                # con la intencion del usuario ("similar a este").
                                                _c08_anchor_type_for_ranking = _c08_ctx_type.upper()
                                                try:
                                                    # get_parent_categories() ya importado arriba
                                                    # en la seccion de diversificacion.
                                                    _c08_parent_map = get_parent_categories()
                                                    # Buscar el grupo de hermanas del tipo actual.
                                                    # next() con default=None evita StopIteration.
                                                    _c08_siblings = next(
                                                        (
                                                            subs
                                                            for subs in _c08_parent_map.values()
                                                            if _c08_ctx_type.upper()
                                                            in [s.upper() for s in subs]
                                                        ),
                                                        None,
                                                    )
                                                    _c08_query_cats = (
                                                        _c08_siblings
                                                        if _c08_siblings
                                                        else [_c08_ctx_type]
                                                    )
                                                    if _c08_siblings:
                                                        logger.info(
                                                            f"F-08C category expansion: "
                                                            f"'{_c08_ctx_type}' -> {_c08_query_cats} "
                                                            f"({len(_c08_query_cats)} types from parent group)"
                                                        )
                                                except Exception as _c08_expand_err:
                                                    # Degradacion graceful: si falla la expansion,
                                                    # caer al tipo exacto (comportamiento anterior).
                                                    _c08_query_cats = [_c08_ctx_type]
                                                    logger.warning(
                                                        f"F-08C category expansion failed "
                                                        f"(using exact type): {_c08_expand_err}"
                                                    )
                                        elif _c08_ctx_type and _c08_ctx_type.upper() in [
                                            c.upper() for c in _c08_query_cats
                                        ]:
                                            # FIX (18/07/2026): _c08_query_cats SI vino de texto
                                            # explicito ("if not _c08_query_cats" de arriba dio
                                            # False), pero el propio tipo del ancla esta incluido
                                            # en ese conjunto detectado -- el usuario no esta
                                            # pidiendo algo DISTINTO a su propia categoria, solo
                                            # confirmando la familia amplia. Ejemplo real
                                            # confirmado en produccion (18/07/2026): "Muestrame
                                            # accesorios similares" sobre un Collar detecta por
                                            # texto ("accesorios") el MISMO grupo de 9 tipos
                                            # hermanos que la expansion por contexto habria
                                            # producido de todas formas si el texto no hubiera
                                            # dicho nada -- pero como _c08_query_cats ya no
                                            # estaba vacio, la rama de arriba nunca se ejecutaba
                                            # y _c08_anchor_type_for_ranking se quedaba en None,
                                            # dejando sin proteccion T8 exactamente el mismo
                                            # sintoma que T8 ya habia resuelto el 05/07/2026
                                            # (5 Aros + 2 Chocker + 1 Collar de un Collar ancla).
                                            #
                                            # Es seguro extender la proteccion aqui: si el ancla
                                            # es COLLARES y _c08_query_cats incluye COLLARES, el
                                            # usuario no esta excluyendo su propio tipo -- solo
                                            # cuando pide algo que EXCLUYE su propio tipo (ej.
                                            # "muestrame bolsos" viendo un Collar -- CARTERAS/
                                            # CLUTCH no incluye COLLARES) esta condicion da False
                                            # y _c08_anchor_type_for_ranking permanece None, sin
                                            # cambios respecto al comportamiento ya validado de
                                            # respetar una peticion explicita distinta.
                                            _c08_anchor_type_for_ranking = _c08_ctx_type.upper()

                                        # Filtrar pool: excluir vistos + filtrar por categoria
                                        _c08_candidates = [
                                            pid for pid in _c08_visual_ids
                                            if pid not in shown_products
                                            and pid != _c08_pid
                                            and (
                                                not _c08_query_cats
                                                or _c08_tfidf.id_index.get(str(pid), {})
                                                   .get("product_type", "").upper()
                                                   in [c.upper() for c in _c08_query_cats]
                                            )
                                        ]

                                        # DIAGNOSTIC LOG (13/07/2026): desglose exacto de
                                        # _c08_candidates por tipo, ANTES del sort de T8 y de
                                        # cualquier corte a n_recommendations.
                                        #
                                        # Por que: la pregunta real que responde este log es
                                        # "de los N candidatos de la familia Accesorios, cuantos
                                        # son EXACTAMENTE el tipo pedido (ej. COLLARES) vs
                                        # rellenados de hermanas (ej. AROS)?" -- sin esto, no
                                        # hay forma de confirmar con datos si un resultado como
                                        # "6 Collares + 2 Aros" viene de que el catalogo
                                        # realmente solo tenia 6 Collares visualmente cercanos,
                                        # o de otra causa. Ver DCT sesion 13/07/2026.
                                        #
                                        # Puramente aditivo: no cambia ningun comportamiento,
                                        # solo visibilidad.
                                        _c08_candidate_breakdown: dict = {}
                                        for _c08_bd_pid in _c08_candidates:
                                            _c08_bd_type = (
                                                _c08_tfidf.id_index.get(str(_c08_bd_pid), {})
                                                .get("product_type", "").upper()
                                            )
                                            _c08_candidate_breakdown[_c08_bd_type] = (
                                                _c08_candidate_breakdown.get(_c08_bd_type, 0) + 1
                                            )
                                        logger.info(
                                            f"F-08C candidate breakdown: {_c08_candidate_breakdown} "
                                            f"(anchor_type={_c08_anchor_type_for_ranking!r}, "
                                            f"total={len(_c08_candidates)})"
                                        )

                                        # HALLAZGO T8 FIX (06/07/2026): priorizar el tipo EXACTO
                                        # del producto ancla sobre sus hermanas dentro del
                                        # camino feliz (candidatos suficientes, sin necesidad
                                        # de relleno).
                                        #
                                        # Por que: _c08_candidates se ordenaba solo por score de
                                        # similitud visual devuelto por FAISS -- sin ningun peso
                                        # hacia el tipo exacto que el usuario esta viendo. Con
                                        # categorias hermanas de tamano muy distinto (AROS=524
                                        # productos vs COLLARES=22), es estadisticamente mucho
                                        # mas probable que los vecinos visuales mas cercanos sean
                                        # de la categoria grande, aunque el usuario haya pedido
                                        # "similar a" un producto de la categoria pequena.
                                        # Evidencia real (sesion 05/07/2026, T8): clic en "similar
                                        # a este" sobre un COLLAR devolvio 5 Aros, 2 Chocker, 1
                                        # Collar -- candidates=49 de pool=50 (camino feliz, sin
                                        # relleno), sin ningun peso hacia COLLARES especificamente.
                                        #
                                        # Alcance: SOLO aplica cuando _c08_query_cats vino de la
                                        # expansion por contexto (_c08_anchor_type_for_ranking
                                        # seteado mas arriba, solo dentro de la rama
                                        # "if not _c08_query_cats:"). Si el usuario pidio una
                                        # categoria explicita por texto (Turn 2+, ej. "muestrame
                                        # collares" viendo un producto AROS),
                                        # _c08_anchor_type_for_ranking permanece None -- no tiene
                                        # sentido priorizar el tipo del producto ancla en contra
                                        # de lo que el usuario pidio explicitamente.
                                        #
                                        # Mecanismo: particion estable (Python sort es stable) --
                                        # candidatos del tipo exacto primero (preservando su
                                        # orden interno por similitud), luego el resto de
                                        # categorias hermanas (tambien preservando su orden
                                        # interno). No es un re-ranking por score -- es una
                                        # partición en dos grupos que preserva la calidad de
                                        # similitud visual dentro de cada grupo.
                                        if _c08_anchor_type_for_ranking:
                                            _c08_candidates = sorted(
                                                _c08_candidates,
                                                key=lambda pid: 0 if (
                                                    _c08_tfidf.id_index.get(str(pid), {})
                                                    .get("product_type", "").upper()
                                                    == _c08_anchor_type_for_ranking
                                                ) else 1,
                                            )

                                        # FIX (16/06/2026 — observabilidad pool exhausto):
                                        # Cuando los candidatos visuales son insuficientes
                                        # (categoria pequena como CAPAS GASA, AROS) el bloque
                                        # caia silenciosamente a smart_fallback sin ningun log.
                                        # Esto hizo invisible el problema durante dias:
                                        # el sintoma era "productos aleatorios sin imagen"
                                        # pero el log no mostraba por que.
                                        # Con este logger.info el diagnostico es inmediato.
                                        #
                                        # FIX (17/06/2026 — caso limite 0 candidatos):
                                        # La condicion original "0 < len(...)" excluía el caso
                                        # MAS extremo: cuando el pool queda completamente vacio
                                        # tras filtrar (visto en Turn 4, sesion 17/06 12:39 PM —
                                        # CAPAS GASA con 24 shown_products). Ese turno NO generaba
                                        # ni "pool insuficiente" ni "visual_diversification" —
                                        # gap total de observabilidad justo en el peor escenario.
                                        # Cambiado a "0 <=" para cubrir tambien candidates=0.
                                        if 0 <= len(_c08_candidates) < n_recommendations:
                                            logger.info(
                                                f"F-08C pool insuficiente: {len(_c08_candidates)} candidatos "
                                                f"(necesarios={n_recommendations}, "
                                                f"cats={_c08_query_cats}, "
                                                f"shown={len(shown_products)}). "
                                                f"Categoria pequena o pool agotado. "
                                                f"Fallback a smart_fallback categorizado."
                                            )

                                        # Solo usar visual pool si tiene suficientes candidatos
                                        if len(_c08_candidates) >= n_recommendations:
                                            # FIX (26/07/2026, Caso 3): category_exhausted_info solo se
                                            # disparaba cuando el pool TOTAL (propio tipo + hermanos) era
                                            # insuficiente (rama de abajo, "Sprint Candidatos Parciales").
                                            # Aqui, en el camino feliz, puede pasar el mismo problema de
                                            # fondo con causa distinta: el pool total alcanza
                                            # (>= n_recommendations), pero el propio tipo del ancla dentro
                                            # de ese pool no alcanza. La particion T8 (06/07) ya prioriza
                                            # el tipo exacto primero, asi que si hay suficientes candidatos
                                            # del tipo propio, el corte final es 100% puro -- pero si no
                                            # los hay, el corte final termina mezclando tipos hermanos sin
                                            # que el LLM se entere. Confirmado en produccion (26/07/2026):
                                            # ancla BRAZALETES devolviendo mayoritariamente AROS en el
                                            # resultado final, LLM diciendo "complementa perfectamente" sin
                                            # aclarar la escasez real del tipo pedido.
                                            #
                                            # Deteccion: contar cuantos de los primeros n_recommendations
                                            # candidatos (ya particionados por T8, tipo propio primero) son
                                            # genuinamente del tipo del ancla. Si son menos que
                                            # n_recommendations, el corte final mezcla tipos -- señalizar
                                            # igual que la rama de relleno parcial, mismo formato de
                                            # mcp_context.category_exhausted_info (misma senal que ya
                                            # consume mcp_personalization_engine.py para pedirle al LLM
                                            # que no diga "complementa perfectamente").
                                            #
                                            # Alcance: solo cuando _c08_anchor_type_for_ranking esta seteado
                                            # -- misma condicion que gobierna la particion T8 en si (si el
                                            # usuario pidio una categoria explicita por texto, este marco de
                                            # "tipo propio" no aplica).
                                            if _c08_anchor_type_for_ranking:
                                                _c08_final_same_type_count = sum(
                                                    1 for pid in _c08_candidates[:n_recommendations]
                                                    if _c08_tfidf.id_index.get(str(pid), {})
                                                       .get("product_type", "").upper()
                                                       == _c08_anchor_type_for_ranking
                                                )
                                                if _c08_final_same_type_count < n_recommendations:
                                                    mcp_context.category_exhausted_info = {  # type: ignore[attr-defined]
                                                        "category": _c08_anchor_type_for_ranking,
                                                        "shown_count": _c08_final_same_type_count,
                                                        "total_count": n_recommendations,
                                                    }
                                                    logger.info(
                                                        f"F-08C category_exhausted (camino feliz, pool total "
                                                        f"suficiente pero tipo propio escaso): "
                                                        f"{_c08_final_same_type_count}/{n_recommendations} son "
                                                        f"{_c08_anchor_type_for_ranking!r}, el resto son tipos "
                                                        f"hermanos. LLM notificacion activada."
                                                    )

                                            _c08_recs = []
                                            for _c08_rank, _c08_vid in enumerate(
                                                _c08_candidates[:n_recommendations]
                                            ):
                                                _c08_vprod = _c08_tfidf.id_index.get(str(_c08_vid))
                                                if _c08_vprod:
                                                    _c08_recs.append(
                                                        normalize_recommendation_dict(
                                                            raw=_c08_vprod,
                                                            rank=_c08_rank,
                                                            score_start=1.0,
                                                            score_step=0.02,
                                                            source="visual_diversification_f08c",
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
                                                return _c08_recs

                                        # ── F-08C Sprint Candidatos Parciales + Relleno Categorizado (17/06/2026) ──
                                        # PROBLEMA RESUELTO: hasta este fix, cuando el pool visual quedaba
                                        # entre 1 y (n_recommendations - 1) candidatos, el bloque NO HACIA NADA
                                        # mas que loguear "pool insuficiente" (ver bloque de arriba) y caia al
                                        # smart_fallback() generico mas abajo en el flujo, que reconstruye las
                                        # n recomendaciones DESDE CERO -- descartando por completo la señal de
                                        # similitud visual ya calculada (la mas valiosa: viene rankeada por
                                        # cercania visual real, no por heuristica de categoria).
                                        # Evidencia: Turn 4 (0 candidatos) y Turn 5 (1 candidato) de la sesion
                                        # de validacion 17/06/2026 -- documentados en el DCT de cierre del
                                        # sprint CAPAS GASA.
                                        #
                                        # DISEÑO (acordado con Yasmani antes de implementar):
                                        #   1. Los candidatos visuales parciales se usan TAL CUAL estan --
                                        #      ya vienen rankeados por similitud real.
                                        #   2. El resto (n_recommendations - len(_c08_candidates)) se rellena
                                        #      llamando a smart_fallback(), anclado a las MISMAS categorias
                                        #      deseadas (_c08_query_cats) via user_events sinteticos -- mismo
                                        #      patron ya validado en produccion para F-08B.2
                                        #      (outfit_complement_f08b2, mas arriba en este mismo archivo).
                                        #   3. user_query=None es CRITICO al llamar a smart_fallback: si
                                        #      pasaramos conversation_query, PRIORIDAD 1 de
                                        #      get_personalized_fallback() volveria a llamar a
                                        #      extract_categories_from_query() sobre el texto crudo de la
                                        #      query, y podria detectar una categoria DISTINTA a
                                        #      _c08_query_cats (ej. si _c08_query_cats vino de la expansion a
                                        #      hermanas porque la query no nombraba categoria explicita, pero
                                        #      algun keyword ambiguo SI matchea otra categoria). Con
                                        #      user_query=None forzamos PRIORIDAD 2, que usa exclusivamente
                                        #      los user_events sinteticos que construimos aqui -- garantiza
                                        #      coherencia entre el filtro del pool visual y el relleno.
                                        #
                                        # PESO EXTRA al tipo exacto del producto actual:
                                        #   PRIORIDAD 2 en get_personalized_fallback() solo usa el TOP-3 de
                                        #   categorias por frecuencia. Para grupos con muchas categorias
                                        #   hermanas (ej. ACCESSORIES tiene 8: AROS, COLLARES, BRAZALETES,
                                        #   CLUTCH, CINTURONES, CARTERAS, TOCADOS, BRALETTES), solo 3 entrarian
                                        #   al reparto. Para garantizar que la categoria EXACTA del producto
                                        #   que el usuario esta viendo nunca quede fuera de ese top-3, le damos
                                        #   el doble de frecuencia que a sus hermanas (2 eventos en vez de 1).
                                        elif len(_c08_candidates) > 0:
                                            _c08_current_type = str(
                                                mcp_context.current_product_context.get("product_type", "")
                                            ).upper()

                                            # Construir user_events sinteticos: un evento por categoria
                                            # deseada, con peso extra (evento adicional) para el tipo exacto
                                            # del producto actual.
                                            _c08_fill_events = []
                                            for _c08_cat in _c08_query_cats:
                                                _c08_fill_events.append({
                                                    "productId": None,
                                                    "product_info": {
                                                        "product_type": _c08_cat,
                                                        "source": "f08c_partial_fill"
                                                    },
                                                    "eventType": "view",
                                                    "source": "f08c_partial_fill"
                                                })
                                                if _c08_cat.upper() == _c08_current_type:
                                                    _c08_fill_events.append({
                                                        "productId": None,
                                                        "product_info": {
                                                            "product_type": _c08_cat,
                                                            "source": "f08c_partial_fill_anchor_boost"
                                                        },
                                                        "eventType": "view",
                                                        "source": "f08c_partial_fill"
                                                    })

                                            _c08_needed = n_recommendations - len(_c08_candidates)

                                            # Exclusion ampliada: vistos en turnos previos + los candidatos
                                            # visuales que YA vamos a usar (para no duplicarlos en el relleno)
                                            # + el producto actual (por si acaso, igual que el filtro del pool).
                                            _c08_fill_exclude = (
                                                set(shown_products)
                                                | {str(pid) for pid in _c08_candidates}
                                                | {_c08_pid}
                                            )

                                            _c08_fill_raw = await ImprovedFallbackStrategies.smart_fallback(
                                                user_id=validated_user_id,
                                                products=all_products,
                                                user_events=_c08_fill_events,
                                                n=_c08_needed,
                                                exclude_products=_c08_fill_exclude,
                                                user_query=None,  # bypass PRIORIDAD 1 -- ver comentario arriba
                                                # DECISION DE PRODUCTO (18/06/2026): coherencia categorica
                                                # estricta. Antes, si la categoria preferida se agotaba,
                                                # get_personalized_fallback rellenaba silenciosamente con
                                                # productos de OTRAS categorias ("Top-up P2 broad") -- el
                                                # usuario recibia, p.ej., 4 CALZONES + 4 productos random sin
                                                # ninguna explicacion. Con strict_category=True, el fill NUNCA
                                                # mezcla categorias: devuelve menos de _c08_needed si la
                                                # categoria se agota, y el bloque de abajo detecta ese deficit
                                                # para notificar al usuario via el LLM en vez de ocultarlo.
                                                strict_category=True,
                                            )

                                            # Detectar agotamiento de categoria: si el relleno no alcanzo lo
                                            # necesario (porque strict_category=True bloqueo el broadening),
                                            # señalizar al LLM via mcp_context para que informe al usuario
                                            # de forma transparente en vez de simplemente entregar menos
                                            # productos sin explicacion alguna.
                                            if len(_c08_fill_raw) < _c08_needed:
                                                _c08_exhausted_cat = (
                                                    _c08_query_cats[0] if _c08_query_cats else "esta categoria"
                                                )
                                                _c08_shown_count = len(_c08_candidates) + len(_c08_fill_raw)
                                                mcp_context.category_exhausted_info = {  # type: ignore[attr-defined]
                                                    "category": _c08_exhausted_cat,
                                                    "shown_count": _c08_shown_count,
                                                    # F-08C con strict_category=True nunca mezcla categorias --
                                                    # total_count == shown_count siempre en este call site.
                                                    "total_count": _c08_shown_count,
                                                }
                                                logger.info(
                                                    f"F-08C category_exhausted: {len(_c08_candidates)} visual + "
                                                    f"{len(_c08_fill_raw)} fill = {_c08_shown_count} "
                                                    f"(de {n_recommendations} pedidos, categoria="
                                                    f"{_c08_exhausted_cat!r}). LLM notificacion activada."
                                                )

                                            # PASO 1: construir _c08_recs con los candidatos visuales parciales.
                                            _c08_recs = []
                                            for _c08_rank, _c08_vid in enumerate(_c08_candidates):
                                                _c08_vprod = _c08_tfidf.id_index.get(str(_c08_vid))
                                                if _c08_vprod:
                                                    _c08_recs.append(
                                                        normalize_recommendation_dict(
                                                            raw=_c08_vprod,
                                                            rank=_c08_rank,
                                                            score_start=1.0,
                                                            score_step=0.02,
                                                            source="visual_diversification_f08c",
                                                        )
                                                    )

                                            # PASO 2: normalizar la salida de smart_fallback al esquema visual
                                            # canonico usando normalize_recommendation_dict(), que unifica
                                            # la logica de los 4 bloques (F-08A, F-08C feliz, F-08C visual
                                            # parcial, F-08C relleno) en un unico lugar.
                                            # score_start arranca un escalon por debajo del ultimo candidato
                                            # visual para preservar el orden visual-primero en el resultado.
                                            _c08_fill_score_start = (
                                                round(_c08_recs[-1]["score"] - 0.05, 4)
                                                if _c08_recs else 0.90
                                            )
                                            for _c08_fill_rank, _c08_fill_prod in enumerate(_c08_fill_raw):
                                                _c08_recs.append(
                                                    normalize_recommendation_dict(
                                                        raw=_c08_fill_prod,
                                                        rank=_c08_fill_rank,
                                                        score_start=_c08_fill_score_start,
                                                        score_step=0.02,
                                                        source="categorized_fill_f08c",
                                                    )
                                                )

                                            if _c08_recs:
                                                logger.info(
                                                    f"F-08C visual_partial_plus_fill: "
                                                    f"{len(_c08_recs)} productos totales "
                                                    f"(visual={len(_c08_candidates)}, "
                                                    f"fill={len(_c08_fill_raw)}, "
                                                    f"needed_fill={_c08_needed}, "
                                                    f"cats={_c08_query_cats})"
                                                )
                                                return _c08_recs
                                        # Si len(_c08_candidates) == 0: no se hace nada -- cae a smart_fallback()
                                        # mas abajo en el flujo normal (comportamiento ya correcto desde el fix
                                        # de contaminacion de colecciones, Bug 3).

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
                            if _f08_boost_text:
                                _f08_visual_ids = await asyncio.wait_for(
                                    _f08_colbert.search_by_product_id_with_text_boost(
                                        _f08_pid,
                                        boost_text=_f08_boost_text,
                                        alpha=_f08_boost_alpha,
                                        top_k=30,
                                    ),
                                    timeout=3.0,
                                )
                                logger.info(
                                    f"F-08 Fase A: composite embedding boost activo "
                                    f"(type={_f08_ptype_upper_early}, alpha={_f08_boost_alpha})"
                                )
                            else:
                                _f08_visual_ids = await asyncio.wait_for(
                                    _f08_colbert.search_by_product_id(_f08_pid, top_k=30),
                                    timeout=3.0,
                                )

                            # Fallback CDN: solo si producto no está en índice FAISS
                            if not _f08_visual_ids:
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
                                    _f08_visual_ids = await asyncio.wait_for(
                                        _f08_colbert.search_by_image(_img_bytes, top_k=30),
                                        timeout=3.0,
                                    )

                            if _f08_visual_ids:
                                # Fase 3: filtrar a la categoria del producto visto.
                                # Excluir siempre el propio producto del resultado.
                                _f08_type_upper = _f08_ptype.upper()

                                # FIX (03/07/2026 -- propagacion del fix F-08C del 16/06/2026):
                                #
                                # Por que: el filtro original comparaba SOLO contra el tipo
                                # exacto (ej. "AROS"). Si el pool de 30 vecinos visuales tenia
                                # <3 productos de ese tipo exacto, el codigo abandonaba el
                                # filtro POR COMPLETO y usaba el pool crudo sin ninguna
                                # restriccion de categoria -- lo que permitia que categorias
                                # totalmente ajenas (ej. vestidos) dominaran el resultado de
                                # un producto de accesorios. Ver DCT sesion 03/07/2026: caso
                                # real "Aros Antonieta" (T3) devolvio 8 vestidos, 0 aros.
                                #
                                # Este mismo problema ya fue diagnosticado y arreglado para
                                # F-08C (Turn 2+) el 16/06/2026 usando expansion a categorias
                                # "hermanas" del mismo grupo padre (ej. AROS -> [AROS,
                                # COLLARES, BRAZALETES, CLUTCH, CINTURONES, CARTERAS,
                                # TOCADOS, BRALETTES]) en vez de abandonar el filtro. Ese fix
                                # nunca se aplico a F-08 Fase A (Turn 1) porque son dos
                                # bloques de codigo separados -- este parche cierra esa
                                # brecha, replicando EXACTAMENTE el mismo patron ya validado
                                # en produccion para F-08C.
                                #
                                # Alcance de este fix: SOLO la expansion a categorias
                                # hermanas. El mecanismo de relleno con smart_fallback
                                # restringido (sprint F-08C del 17/06/2026) NO se porta aqui
                                # -- si el pool expandido sigue siendo insuficiente, el
                                # codigo no retorna temprano y cae al fallback estandar
                                # (hybrid_recommender.get_recommendations), igual que hacia
                                # F-08C antes del sprint del 17/06. Evaluar el relleno
                                # restringido como fix adicional en una sesion futura si la
                                # expansion de categorias por si sola no es suficiente.
                                _f08_expanded_cats = [_f08_type_upper] if _f08_type_upper else []
                                if _f08_type_upper:
                                    try:
                                        # Import lazy: mismo patron defensivo que
                                        # normalize_recommendation_dict un poco mas arriba en
                                        # este mismo bloque (comentario BUG-REFACTOR-1,
                                        # 18/06/2026). get_parent_categories() esta importado
                                        # arriba SOLO dentro del bloque F-08C (Turn 2+, guardado
                                        # por "if use_diversification:") -- en Turn 1 esa rama
                                        # nunca ejecuta, y Python trata el nombre como local a
                                        # toda la funcion, no solo a esa rama. Sin este import
                                        # lazy, usar get_parent_categories() aqui lanzaria
                                        # UnboundLocalError exactamente igual que el bug ya
                                        # documentado y corregido para normalize_recommendation_dict.
                                        from src.recommenders.improved_fallback_exclude_seen import (
                                            get_parent_categories as _f08_get_parent_categories,
                                        )
                                        _f08_parent_map = _f08_get_parent_categories()
                                        _f08_siblings = next(
                                            (
                                                subs
                                                for subs in _f08_parent_map.values()
                                                if _f08_type_upper in [s.upper() for s in subs]
                                            ),
                                            None,
                                        )
                                        if _f08_siblings:
                                            _f08_expanded_cats = [s.upper() for s in _f08_siblings]
                                            logger.info(
                                                f"F-08 category expansion: "
                                                f"{_f08_type_upper!r} -> {_f08_expanded_cats} "
                                                f"({len(_f08_expanded_cats)} types from parent group)"
                                            )
                                    except Exception as _f08_expand_err:
                                        # Degradacion graceful: si falla la expansion, usar
                                        # el tipo exacto (comportamiento original, sin romper
                                        # nada si get_parent_categories() no esta disponible).
                                        _f08_expanded_cats = [_f08_type_upper] if _f08_type_upper else []
                                        logger.debug(
                                            f"F-08 category expansion failed "
                                            f"(using exact type): {_f08_expand_err}"
                                        )

                                _f08_same_cat = [
                                    pid for pid in _f08_visual_ids
                                    if str(pid) != _f08_pid
                                    and (
                                        not _f08_expanded_cats
                                        or _f08_tfidf.id_index.get(str(pid), {})
                                           .get("product_type", "").upper() in _f08_expanded_cats
                                    )
                                ]

                                # FIX (26/07/2026 -- gap de observabilidad, backlog identificado
                                # al cerrar Fase 1b): F-08C ya tenia este mismo log desde el
                                # 13/07/2026 ("F-08C candidate breakdown") -- F-08 Fase A nunca lo
                                # tuvo, pese a compartir la misma estructura de filtrado y
                                # particion T8. Sin esto, auditar un turno de F-08 Fase A (Turn 1)
                                # requeria inferir la composicion del pool cruzando IDs finales
                                # contra otras fuentes -- como se tuvo que hacer manualmente
                                # durante la validacion del 26/07/2026. Mismo formato exacto que
                                # F-08C para poder comparar directamente entre ambos caminos.
                                #
                                # Puramente aditivo: no cambia ningun comportamiento, solo
                                # visibilidad -- mismo criterio que el log analogo de F-08C.
                                _f08_candidate_breakdown: dict = {}
                                for _f08_bd_pid in _f08_same_cat:
                                    _f08_bd_type = (
                                        _f08_tfidf.id_index.get(str(_f08_bd_pid), {})
                                        .get("product_type", "").upper()
                                    )
                                    _f08_candidate_breakdown[_f08_bd_type] = (
                                        _f08_candidate_breakdown.get(_f08_bd_type, 0) + 1
                                    )
                                logger.info(
                                    f"F-08 candidate breakdown: {_f08_candidate_breakdown} "
                                    f"(anchor_type={_f08_type_upper!r}, "
                                    f"total={len(_f08_same_cat)})"
                                )

                                # HALLAZGO T8 FIX (18/07/2026 -- propagacion a F-08 Fase A del
                                # fix ya validado en F-08C el 06/07/2026): _f08_same_cat mezcla
                                # el tipo EXACTO del producto ancla con sus hermanos del mismo
                                # grupo padre, ordenados solo por similitud visual pura -- sin
                                # ningun peso hacia el tipo exacto. Con categorias hermanas de
                                # tamano muy distinto (AROS=524 productos vs COLLARES=22), es
                                # mucho mas probable que los vecinos visuales mas cercanos sean
                                # del tipo grande, aunque el usuario este viendo "similar a" un
                                # producto del tipo pequeno. Confirmado en produccion (18/07/2026,
                                # screenshot T2): "similar a" un Collar devolvio 5 Aros + 2
                                # Chocker + 1 Collar -- exactamente el mismo sintoma que T8 ya
                                # resolvio para F-08C el 06/07/2026, pero nunca se porto a este
                                # bloque (Turn 1) porque son dos caminos de codigo separados.
                                #
                                # Se reordena _f08_same_cat UNA SOLA VEZ aqui, antes de que lo
                                # consuman tanto el camino feliz (corte directo mas abajo) como
                                # el mecanismo de relleno restringido -- ambos heredan la mejora
                                # de orden automaticamente, sin tocar ninguno de los dos por
                                # separado.
                                #
                                # Mecanismo, en dos partes:
                                #   1. Particion tipo T8: el tipo EXACTO del ancla primero
                                #      (preservando su orden interno de similitud), el resto
                                #      (hermanas) despues.
                                #   2. NIVEL 1 (mismo mecanismo portado a F-08B el 18/07/2026):
                                #      dentro del "resto" (las hermanas), intercalar por subtipo
                                #      real en vez de dejar que la similitud visual pura decida
                                #      el orden -- evita que si hace falta rellenar con hermanas,
                                #      un solo hermano numeroso (tipicamente AROS) monopolice el
                                #      relleno a costa de otras hermanas mas escasas.
                                if _f08_type_upper and _f08_tfidf:
                                    _f08_own_type_items = [
                                        pid for pid in _f08_same_cat
                                        if _f08_tfidf.id_index.get(str(pid), {})
                                           .get("product_type", "").upper() == _f08_type_upper
                                    ]
                                    _f08_sibling_items = [
                                        pid for pid in _f08_same_cat
                                        if _f08_tfidf.id_index.get(str(pid), {})
                                           .get("product_type", "").upper() != _f08_type_upper
                                    ]

                                    def _f08_interleave_by_subtype(_f08_flat_pids):
                                        _f08_by_type: dict = {}
                                        for _f08_st_pid in _f08_flat_pids:
                                            _f08_st_type = (
                                                _f08_tfidf.id_index.get(str(_f08_st_pid), {})
                                                .get("product_type", "UNKNOWN").upper()
                                            )
                                            _f08_by_type.setdefault(_f08_st_type, []).append(_f08_st_pid)
                                        _f08_result = []
                                        while any(_f08_by_type.values()):
                                            for _f08_st_key, _f08_st_group in list(_f08_by_type.items()):
                                                if _f08_st_group:
                                                    _f08_result.append(_f08_st_group.pop(0))
                                                if not _f08_st_group:
                                                    del _f08_by_type[_f08_st_key]
                                        return _f08_result

                                    _f08_same_cat = (
                                        _f08_own_type_items
                                        + _f08_interleave_by_subtype(_f08_sibling_items)
                                    )

                                # HALLAZGO 1 / OPCION A FIX (03/07/2026 -- propagacion del
                                # sprint F-08C "Candidatos Parciales + Relleno Categorizado"
                                # del 17/06/2026 a F-08 Fase A):
                                #
                                # Por que: la expansion a categorias hermanas (fix anterior de
                                # esta misma sesion) evita mezclar con categorias totalmente
                                # ajenas (vestidos), pero NO garantiza llegar a n_recommendations
                                # items cuando incluso el pool expandido es escaso -- y la
                                # auditoria de Fase 0 (sesion 03/07/2026) confirmo que para
                                # varias categorias de accesorios (CARTERAS, parte de
                                # BRAZALETES) la galeria de fotos completa esta organizada
                                # alrededor de un vestido/outfit, sin ningun plano de detalle
                                # del accesorio -- es decir, la CALIDAD del embedding visual
                                # para esas categorias es estructuralmente limitada por la
                                # fotografia disponible, no por el codigo de filtrado. Por eso
                                # este relleno restringido -- que NO depende de la calidad del
                                # embedding, solo garantiza coherencia de categoria -- es la
                                # defensa mas robusta disponible hoy.
                                #
                                # DISEÑO: identico al ya validado en produccion para F-08C.
                                #   1. Candidatos visuales parciales se usan tal cual (ya
                                #      rankeados por similitud real).
                                #   2. El resto se rellena con smart_fallback(), anclado a las
                                #      MISMAS categorias hermanas (_f08_expanded_cats) via
                                #      user_events sinteticos -- nunca mezcla con categorias
                                #      ajenas.
                                #   3. user_query=None bypassa PRIORIDAD 1 de
                                #      get_personalized_fallback() (evita que re-detecte una
                                #      categoria distinta desde el texto crudo).
                                #   4. strict_category=True: coherencia categorica estricta --
                                #      si la categoria se agota, devuelve menos items en vez de
                                #      mezclar silenciosamente con categorias ajenas.
                                #   5. Peso extra (evento duplicado) al tipo EXACTO del producto
                                #      ancla, igual que F-08C, para que nunca quede fuera del
                                #      top-3 de PRIORIDAD 2 en grupos con muchas hermanas
                                #      (ej. ACCESSORIES tiene 8 categorias).
                                #
                                # shown_products en Fase A (Turn 1) es siempre set() vacio --
                                # inicializado incondicionalmente al inicio de
                                # get_base_recommendations(), antes del if use_diversification.
                                # No hace falta ninguna adaptacion para eso.
                                #
                                # all_products: a diferencia de shown_products, SI tiene el
                                # mismo riesgo de scoping ya documentado para
                                # get_parent_categories (BUG-REFACTOR-1) -- se asigna solo
                                # dentro de "if use_diversification:" (Turn 2+), que en Turn 1
                                # nunca ejecuta. Se obtiene aqui directamente de
                                # _f08_tfidf.product_data (mismo objeto subyacente).
                                if len(_f08_same_cat) >= n_recommendations:
                                    _f08_recs = []
                                    for _f08_rank, _f08_vid in enumerate(
                                        _f08_same_cat[:n_recommendations]
                                    ):
                                        _f08_vprod = _f08_tfidf.id_index.get(str(_f08_vid))
                                        if _f08_vprod:
                                            _f08_recs.append(
                                                normalize_recommendation_dict(
                                                    raw=_f08_vprod,
                                                    rank=_f08_rank,
                                                    score_start=1.0,
                                                    score_step=0.03,  # F-08A usa paso 0.03
                                                    source="visual_search_f08",
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
                                        return _f08_recs  # early-return: bypass TF-IDF

                                elif len(_f08_same_cat) > 0:
                                    try:
                                        from src.recommenders.improved_fallback_exclude_seen import (
                                            ImprovedFallbackStrategies as _f08_ImprovedFallbackStrategies,
                                        )

                                        _f08_all_products = _f08_tfidf.product_data

                                        _f08_fill_events = []
                                        for _f08_cat in _f08_expanded_cats:
                                            _f08_fill_events.append({
                                                "productId": None,
                                                "product_info": {
                                                    "product_type": _f08_cat,
                                                    "source": "f08a_partial_fill"
                                                },
                                                "eventType": "view",
                                                "source": "f08a_partial_fill"
                                            })
                                            if _f08_cat.upper() == _f08_type_upper:
                                                _f08_fill_events.append({
                                                    "productId": None,
                                                    "product_info": {
                                                        "product_type": _f08_cat,
                                                        "source": "f08a_partial_fill_anchor_boost"
                                                    },
                                                    "eventType": "view",
                                                    "source": "f08a_partial_fill"
                                                })

                                        _f08_needed = n_recommendations - len(_f08_same_cat)

                                        _f08_fill_exclude = (
                                            set(shown_products)
                                            | {str(pid) for pid in _f08_same_cat}
                                            | {_f08_pid}
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

                                        if len(_f08_fill_raw) < _f08_needed:
                                            _f08_exhausted_cat = (
                                                _f08_expanded_cats[0] if _f08_expanded_cats else "esta categoria"
                                            )
                                            _f08_shown_count = len(_f08_same_cat) + len(_f08_fill_raw)
                                            mcp_context.category_exhausted_info = {  # type: ignore[attr-defined]
                                                "category": _f08_exhausted_cat,
                                                "shown_count": _f08_shown_count,
                                                "total_count": _f08_shown_count,
                                            }
                                            logger.info(
                                                f"F-08 category_exhausted: {len(_f08_same_cat)} visual + "
                                                f"{len(_f08_fill_raw)} fill = {_f08_shown_count} "
                                                f"(de {n_recommendations} pedidos, categoria="
                                                f"{_f08_exhausted_cat!r}). LLM notificacion activada."
                                            )

                                        _f08_recs = []
                                        for _f08_rank, _f08_vid in enumerate(_f08_same_cat):
                                            _f08_vprod = _f08_tfidf.id_index.get(str(_f08_vid))
                                            if _f08_vprod:
                                                _f08_recs.append(
                                                    normalize_recommendation_dict(
                                                        raw=_f08_vprod,
                                                        rank=_f08_rank,
                                                        score_start=1.0,
                                                        score_step=0.03,
                                                        source="visual_search_f08",
                                                    )
                                                )

                                        _f08_fill_score_start = (
                                            round(_f08_recs[-1]["score"] - 0.05, 4)
                                            if _f08_recs else 0.90
                                        )
                                        for _f08_fill_rank, _f08_fill_prod in enumerate(_f08_fill_raw):
                                            _f08_recs.append(
                                                normalize_recommendation_dict(
                                                    raw=_f08_fill_prod,
                                                    rank=_f08_fill_rank,
                                                    score_start=_f08_fill_score_start,
                                                    score_step=0.02,
                                                    source="categorized_fill_f08a",
                                                )
                                            )

                                        if _f08_recs:
                                            logger.info(
                                                f"F-08 visual_partial_plus_fill: "
                                                f"{len(_f08_recs)} productos totales "
                                                f"(visual={len(_f08_same_cat)}, "
                                                f"fill={len(_f08_fill_raw)}, "
                                                f"needed_fill={_f08_needed}, "
                                                f"cats={_f08_expanded_cats})"
                                            )
                                            return _f08_recs

                                    except Exception as _f08_fill_err:
                                        logger.warning(
                                            f"F-08 partial_fill failed (using visual-only, "
                                            f"sin relleno): {_f08_fill_err}"
                                        )
                                        _f08_recs = []
                                        for _f08_rank, _f08_vid in enumerate(_f08_same_cat):
                                            _f08_vprod = _f08_tfidf.id_index.get(str(_f08_vid))
                                            if _f08_vprod:
                                                _f08_recs.append(
                                                    normalize_recommendation_dict(
                                                        raw=_f08_vprod,
                                                        rank=_f08_rank,
                                                        score_start=1.0,
                                                        score_step=0.03,
                                                        source="visual_search_f08",
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
                                            return _f08_recs

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