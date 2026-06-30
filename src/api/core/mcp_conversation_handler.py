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

                                # Excluir la categoria propia del producto visto.
                                # SHOPIFY_TYPE_TO_OUTFIT_CATEGORY mapping (subset relevante).
                                _B08_TYPE_TO_CAT = {
                                    "vestidos cortos": "dress", "vestidos largos": "dress",
                                    "vestidos midis":  "dress", "enteritos":       "enterito",
                                    "blusas":   "top",       "polos":    "top",
                                    "tops":     "top",       "accesorios": "accessory",
                                    "bolsos":   "bag",       "calzado":   "bottom",
                                    "pantalones": "bottom",  "faldas":   "bottom",
                                }
                                _b08_own_cat    = _B08_TYPE_TO_CAT.get(_b08_ptype, "")
                                _b08_target_cats = [
                                    c for c in ["dress", "top", "accessory", "bag",
                                                "enterito", "outerwear"]
                                    if c != _b08_own_cat
                                ]

                                # Composite embedding: alpha=0.5 (imagen y texto con igual peso)
                                # Evita que vestidos dominen todas las categorias (issue S1).
                                _b08_outfit = await asyncio.wait_for(
                                    _b08_colbert.search_outfit_by_image(
                                        image_bytes=_img_bytes_b08,
                                        target_categories=_b08_target_cats,
                                        top_k_per_category=3,
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
                                    _b08_pools = {
                                        cat: [pid for pid in pids if str(pid) != _b08_pid]
                                        for cat, pids in _b08_outfit_cats.items()
                                        if isinstance(pids, list) and pids
                                    }
                                    _b08_rank = 0
                                    while (
                                        len(_b08_recs) < n_recommendations
                                        and any(_b08_pools.values())
                                    ):
                                        for _b08_cat, _b08_pool in list(_b08_pools.items()):
                                            if not _b08_pool or len(_b08_recs) >= n_recommendations:
                                                break
                                            _b08_vid   = _b08_pool.pop(0)
                                            _b08_vprod = (
                                                _b08_tfidf.id_index.get(str(_b08_vid))
                                                if _b08_tfidf else None
                                            )
                                            if _b08_vprod:
                                                _b08_score = round(1.0 - _b08_rank * 0.04, 4)
                                                _b08_recs.append({
                                                    "id":               str(_b08_vid),
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
                                                _b08_rank += 1
                                            if not _b08_pool:
                                                del _b08_pools[_b08_cat]
                                                break

                                    if _b08_recs:
                                        logger.info(
                                            f"F-08B outfit_completion: {len(_b08_recs)} productos "
                                            f"(categories={list(_b08_outfit_cats.keys())}, "
                                            f"pid={_b08_pid!r})"
                                        )
                                        return _b08_recs

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
                                _complement_cats = _OUTFIT_COMPLEMENT_MAP.get(
                                    _outfit_product_type,
                                    ["AROS", "COLLARES", "CLUTCH", "CINTURONES"],  # fallback genérico
                                )
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

                                    # pool visual: top_k=50 para tener margen tras filtrado
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
                                        if not _c08_query_cats:
                                            _c08_ctx_type = mcp_context.current_product_context.get(
                                                "product_type", ""
                                            ) if mcp_context and getattr(
                                                mcp_context, "current_product_context", None
                                            ) else ""
                                            if _c08_ctx_type:
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

                            # A.5: buscar por ID (usa vector FAISS existente, ~50ms)
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
                                # Fase 3: filtrar a la misma categoría del producto visto.
                                # Excluir siempre el propio producto del resultado.
                                _f08_type_upper = _f08_ptype.upper()
                                _f08_same_cat = [
                                    pid for pid in _f08_visual_ids
                                    if str(pid) != _f08_pid
                                    and (
                                        not _f08_ptype
                                        or _f08_tfidf.id_index.get(str(pid), {})
                                           .get("product_type", "").upper() == _f08_type_upper
                                    )
                                ]
                                # Si quedan menos de 3 del mismo tipo, usar pool sin filtro
                                _f08_ids_to_use = _f08_same_cat if len(_f08_same_cat) >= 3 else [
                                    pid for pid in _f08_visual_ids if str(pid) != _f08_pid
                                ]

                                # Fase 4: construir dicts compatibles con formato TF-IDF
                                _f08_recs = []
                                for _f08_rank, _f08_vid in enumerate(_f08_ids_to_use[:n_recommendations]):
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
                                        f"pool={len(_f08_visual_ids)}, "
                                        f"filtered={len(_f08_same_cat)})"
                                    )
                                    return _f08_recs  # early-return: bypass TF-IDF

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