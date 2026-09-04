# src/api/routers/visual_search_router.py
"""
Visual Search Router — Búsqueda de productos por imagen.

Endpoints:
  POST /v1/mcp/visual-search
    Búsqueda visual principal. Recibe imagen, devuelve productos similares.

  POST /v1/mcp/visual-search/index
    Ops: lanza re-indexación COMPLETA del catálogo (~30 min).

  POST /v1/mcp/visual-search/index/update
    Ops: lanza indexación INCREMENTAL de productos nuevos.

Feature flag: VISUAL_SEARCH_ENABLED=false (default)
  Activar: gcloud run services update retail-recommender
           --set-env-vars VISUAL_SEARCH_ENABLED=true

──────────────────────────────────────────────────────────────────
SINGLETON DEL CLIENTE (fix 02/05/2026)
──────────────────────────────────────────────────────────────────
LFM2ColBERTClient se inicializa UNA SOLA VEZ a nivel de módulo.

POR QUÉ es crítico:
  El cliente gestiona:
    - Caché del ID token IAM (renovación automática cada 59min)
    - Circuit-breakers (texto / visual) con contadores de fallos
    - Estado del httpx.AsyncClient (pool de conexiones TCP)

  Si el cliente se instancia en cada request (patrón anterior):
    1. El ID token se solicita al metadata server en CADA búsqueda
       (+50-200ms de latencia innecesaria por request)
    2. El circuit-breaker se reinicia en cada request
       (nunca llega a abrir aunque haya 10 fallos seguidos)
    3. El pool TCP de httpx nunca reutiliza conexiones
       (overhead de handshake TLS en cada request)

  Con singleton:
    1. El token se renueva solo cuando expira (cada 59min, en background)
    2. El circuit-breaker acumula fallos correctamente entre requests
    3. Las conexiones TCP al embedding-service se reutilizan

  El singleton se inicializa en la primera llamada a _get_colbert_client()
  (lazy initialization) para evitar problemas si COLBERT_SERVICE_URL no
  está configurado cuando se importa el módulo.
"""

import os
import time
import logging
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.security_auth import get_api_key

logger = structlog.get_logger(__name__)
router  = APIRouter()

# ── Singleton del cliente ─────────────────────────────────────────────────────
# None hasta la primera llamada a _get_colbert_client().
# Una vez inicializado, se reutiliza en todas las requests del proceso.
_colbert_client_singleton = None

# PROBLEMA 2 FIX (30/06/2026): singletons de UnifiedLLMClient para
# _generate_visual_search_message().
#
# Por que: antes se instanciaba UnifiedLLMClient dentro de la funcion en
# CADA llamada. Cada instancia nueva crea un httpx.AsyncClient propio --
# sin reutilizacion de conexiones TCP entre requests. El coste de
# TCP connect + TLS handshake con OpenRouter es de ~3-4s en frio, lo que
# dejaba sin margen al timeout de 4.0s para la inferencia LLM real.
#
# Evidencia directa de los logs (30/06/2026):
#   warmup LFM con timeout=14.0s -> OK en 8.9s (cold, margen suficiente)
#   T3/T5/T6 con timeout=4.0s   -> FAIL en 4.7s (cold, timeout agotado
#                                   antes de recibir ninguna respuesta)
#   T7 con timeout=4.0s         -> OK en 1.1s (conexion ya establecida)
#
# Con singleton: la conexion TCP+TLS se establece una sola vez (primera
# llamada) y se reutiliza en todas las siguientes -- exactamente el mismo
# patron que _colbert_client_singleton para el embedding-service.
# PATRON (01/07/2026): para LFM visual search reutiliza engine._lfm_client
# (el cliente del MCP engine, ya caliente por el warmup de startup PASO 8.5c
# y los pings de keep-alive cada 300s -- ver main_unified_redis.py).
# Para GPT-4o-mini si se mantiene un singleton dedicado porque el engine
# no usa GPT directamente. El singleton se inicializa y calienta en lifespan
# via warmup_vs_gpt4o_singleton() (PASO 8.5e).
_vs_gpt4o_client = None  # UnifiedLLMClient(GPT-4o-mini) -- singleton


# ── Feature flag ──────────────────────────────────────────────────────────────
def _visual_search_enabled() -> bool:
    return os.environ.get('VISUAL_SEARCH_ENABLED', 'false').lower() == 'true'


# ── Response models ───────────────────────────────────────────────────────────
class VisualSearchResponse(BaseModel):
    recommendations: List[dict]
    query_type: str = 'visual_search'
    total_found: int
    latency_ms: float
    visual_index_size: int = 0
    # FIX (27/06/2026): mensaje opcional generado por LLM describiendo los
    # productos encontrados. None si la generacion fallo/esta deshabilitada --
    # el frontend cae a su plantilla estatica de respaldo en ese caso. Ver
    # _generate_visual_search_message() para el detalle completo.
    message: Optional[str] = None


# ── Singleton helper ──────────────────────────────────────────────────────────

def _get_colbert_client():
    """
    Devuelve la instancia singleton de LFM2ColBERTClient.

    Inicialización lazy: el cliente se crea en la primera llamada, no al
    importar el módulo. Esto es importante porque COLBERT_SERVICE_URL puede
    no estar disponible en tiempo de import (Cloud Run inyecta env vars después
    de arrancar el proceso).

    Thread safety: FastAPI usa un único event loop asyncio. La inicialización
    del singleton ocurre en un coroutine de FastAPI, no en un thread separado,
    así que no hay race conditions.
    """
    global _colbert_client_singleton
    if _colbert_client_singleton is None:
        try:
            from src.api.services.colbert_client import LFM2ColBERTClient
            _colbert_client_singleton = LFM2ColBERTClient()
            logger.info('colbert_client_singleton_initialized',
                        url=os.environ.get('COLBERT_SERVICE_URL', 'not-set'))
        except ValueError as e:
            logger.error('colbert_client_init_failed', error=str(e))
            raise HTTPException(
                status_code=503,
                detail='Visual search service unavailable (COLBERT_SERVICE_URL not set)'
            )
    return _colbert_client_singleton


# FIX (01/07/2026): _get_vs_lfm_client() eliminado.
# Visual search ahora obtiene engine._lfm_client via ServiceFactory,
# que ya esta caliente por el warmup de startup (PASO 8.5c) y los
# pings de keep-alive cada 300s. Ver _generate_visual_search_message().


def _get_vs_gpt4o_client():
    """
    Devuelve el singleton de UnifiedLLMClient para GPT-4o-mini (visual search).
    Mismo razonamiento que _get_vs_lfm_client(). Devuelve None si el fallback
    no esta habilitado.
    """
    global _vs_gpt4o_client
    if _vs_gpt4o_client is None:
        if os.environ.get('GPT4O_MINI_FALLBACK_ENABLED', 'false').lower() != 'true':
            return None
        from src.api.core.llm_client import UnifiedLLMClient
        from src.api.core.claude_config import GPT4O_MINI_FALLBACK_CONFIG
        _vs_gpt4o_client = UnifiedLLMClient(
            provider=GPT4O_MINI_FALLBACK_CONFIG['provider'],
            model=GPT4O_MINI_FALLBACK_CONFIG['model'],
            max_tokens=120,
            temperature=GPT4O_MINI_FALLBACK_CONFIG['temperature'],
        )
        logger.info('vs_gpt4o_client_singleton_initialized',
                    model=GPT4O_MINI_FALLBACK_CONFIG['model'])
    return _vs_gpt4o_client


async def warmup_vs_gpt4o_singleton() -> None:
    """
    Pre-inicializa y calienta el singleton _vs_gpt4o_client de visual search.
    Llamado como fire-and-forget (asyncio.create_task) desde lifespan()
    en main_unified_redis.py (PASO 8.5e).

    Por que existe esta funcion:
      El MCP engine no usa GPT-4o-mini directamente -- es el fallback
      exclusivo de visual search. Sin este warmup, la primera visual search
      donde LFM falla crea un UnifiedLLMClient frio y puede tardar > 8s
      (el timeout configurado) solo en TCP+TLS+primera_inferencia.
      Con este warmup el singleton ya tiene conexion establecida con
      OpenRouter y la respuesta llega en < 2s.

    Delay de 14s:
      Se espera a que los warmups de LFM y GPT-4o-mini del engine (PASO
      8.5c/8.5d, cada uno con asyncio.sleep(8.0)) terminen. Inicializar
      _vs_gpt4o_client en paralelo estricto causaria dos llamadas concurrentes
      al mismo modelo en OpenRouter -- el delay evita esa contention.
    """
    import asyncio as _a

    try:
        await _a.sleep(14.0)  # esperar al fin de PASO 8.5d

        if os.environ.get('GPT4O_MINI_FALLBACK_ENABLED', 'false').lower() != 'true':
            logger.info('vs_gpt4o_singleton_warmup_skipped',
                        reason='GPT4O_MINI_FALLBACK_ENABLED != true')
            return

        vs_gpt4o = _get_vs_gpt4o_client()  # inicializa el singleton
        if vs_gpt4o is None:
            return

        logger.info('vs_gpt4o_singleton_warmup_started')
        resp = await _a.wait_for(
            vs_gpt4o.complete(
                'Eres un asistente de moda.',
                'Responde: OK',
            ),
            timeout=14.0,
        )
        logger.info('vs_gpt4o_singleton_warmup_complete', model=resp.model)

    except _a.TimeoutError:
        logger.warning('vs_gpt4o_singleton_warmup_timeout')
    except Exception as e:
        logger.warning('vs_gpt4o_singleton_warmup_error',
                       error=str(e) or repr(e),
                       error_type=type(e).__name__)


def _get_tfidf_recommender():
    from src.api.main_unified_redis import tfidf_recommender
    if not tfidf_recommender or not getattr(tfidf_recommender, 'id_index', None):
        logger.error('visual_search_catalog_not_loaded')
        raise HTTPException(status_code=503, detail='Product catalog not loaded')
    return tfidf_recommender


# ── Mensaje generado por LLM (FIX 27/06/2026) ─────────────────────────────────
async def _generate_visual_search_message(recommendations: List[dict], language: str) -> Optional[str]:
    """
    Genera un mensaje breve y persuasivo describiendo los productos
    encontrados por busqueda visual, usando el mismo cliente LLM y los
    mismos modelos que el resto de la conversacion (LFM2-24B primario via
    OpenRouter, GPT-4o-mini de respaldo -- ver UnifiedLLMClient en
    src/api/core/llm_client.py y LFM_MCP_CONFIG / GPT4O_MINI_FALLBACK_CONFIG
    en src/api/core/claude_config.py).

    DECISION DE PRODUCTO (27/06/2026): este endpoint (busqueda por similitud
    visual) antes no generaba ningun texto -- el frontend mostraba una
    plantilla fija ("Encontre N productos similares:") identica en cada
    busqueda, sin mencionar que se encontro. A diferencia del outfit
    (resultado estructurado por categoria, donde una plantilla mejorada
    basta -- ver describeOutfitCategories en ChatWidget.tsx), la busqueda
    por similitud es un momento de descubrimiento/venta donde una frase
    generada que conecte los productos encontrados aporta mas valor
    comercial. Yasmani decidio pagar el costo de latencia/tokens aqui
    especificamente por ese motivo.

    Presupuesto de tiempo MAS CORTO que el flujo conversacional principal
    (4.0s LFM / 3.0s GPT-4o-mini, contra 10.0s/8.0s en
    mcp_personalization_engine.py) -- este endpoint se diseno para ser
    rapido, y la generacion de mensaje no debe comprometer eso. Si ambos
    modelos fallan, no estan habilitados, o no hay API key configurada,
    devuelve None -- el endpoint NUNCA se rompe por esto; el frontend cae
    a su plantilla estatica de respaldo (comportamiento previo, intacto).

    Args:
        recommendations: productos ya sanitizados (title, price, currency).
        language: 'es', 'en', 'fr', 'it' o 'de' -- determina el idioma del
            mensaje generado. Cualquier otro valor cae a espanol por defecto.

    Returns:
        Optional[str]: el mensaje generado, o None si no se pudo generar.
    """
    if not recommendations:
        return None

    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        return None

    titles = [
        f"{r.get('title', 'Producto')} ({r.get('currency', '')} {r.get('price', '')})"
        for r in recommendations[:5]
    ]
    products_text = '; '.join(titles)

    # FIX (28/06/2026): el mercado suizo (CH) requiere tambien fr/it/de, no
    # solo es/en -- antes cualquier idioma distinto de 'en' caia a espanol
    # por defecto sin importar el idioma real del navegador del usuario.
    # _VS_PROMPTS cubre los 5 idiomas que maneja el sistema (mismos que
    # navigator.language puede devolver para un usuario en Suiza: fr-CH,
    # de-CH, it-CH, adicional a es/en de los otros mercados).
    _VS_PROMPTS = {
        'es': (
            'Eres un asistente de compras de moda. Dada una lista de productos '
            'encontrados por busqueda de similitud visual, escribe UNA frase breve, '
            'calida y persuasiva (maximo 2 lineas) destacando 1-2 productos por '
            'nombre. Nunca inventes detalles que no esten en la lista. '
            'Responde solo en espanol.',
            'Productos encontrados: {products}',
        ),
        'en': (
            'You are a fashion shopping assistant. Given a list of products found '
            'via visual similarity search, write ONE short, warm, persuasive sentence '
            '(max 2 lines) highlighting 1-2 standout items by name. '
            'Never invent details not in the list. Respond in English only.',
            'Products found: {products}',
        ),
        'fr': (
            "Tu es un assistant shopping mode. A partir d'une liste de produits "
            'trouves par recherche de similarite visuelle, ecris UNE phrase courte, '
            'chaleureuse et persuasive (maximum 2 lignes) en mettant en avant 1 ou 2 '
            "articles par leur nom. N'invente jamais de details absents de la liste. "
            'Reponds uniquement en francais.',
            'Produits trouves : {products}',
        ),
        'it': (
            'Sei un assistente di shopping di moda. Data una lista di prodotti '
            'trovati tramite ricerca di similarita visiva, scrivi UNA frase breve, '
            'calorosa e persuasiva (massimo 2 righe) evidenziando 1-2 articoli per '
            'nome. Non inventare mai dettagli non presenti nella lista. '
            'Rispondi solo in italiano.',
            'Prodotti trovati: {products}',
        ),
        'de': (
            'Du bist ein Mode-Shopping-Assistent. Schreibe anhand einer Liste von '
            'Produkten, die durch visuelle Aehnlichkeitssuche gefunden wurden, EINEN '
            'kurzen, warmen und ueberzeugenden Satz (maximal 2 Zeilen), der 1-2 '
            'herausragende Artikel namentlich hervorhebt. Erfinde niemals Details, '
            'die nicht in der Liste stehen. Antworte ausschliesslich auf Deutsch.',
            'Gefundene Produkte: {products}',
        ),
    }

    system_prompt, _user_template = _VS_PROMPTS.get(language, _VS_PROMPTS['es'])
    user_prompt = _user_template.format(products=products_text)

    import asyncio as _asyncio_vsm

    # FIX (01/07/2026): para LFM reutilizamos engine._lfm_client.
    #
    # Por que: engine._lfm_client es el mismo cliente que calientan el
    # warmup de startup (PASO 8.5c en main_unified_redis.py) y los pings
    # de keep-alive cada 300s. Al compartirlo, la primera visual search
    # del proceso encuentra la conexion a OpenRouter ya establecida y el
    # modelo LFM ya cargado en la GPU -- en vez de un cold-start de 10-30s
    # que hace que el timeout de 10s falle (comportamiento observado en
    # logs del 01/07/2026, T4 y T6: 20s de latencia total).
    #
    # httpx.AsyncClient es async-safe: multiples coroutines pueden usar el
    # mismo cliente simultaneamente sin race conditions.
    #
    # Fallback: si ServiceFactory no esta disponible (ej. tests unitarios),
    # se usa un UnifiedLLMClient efimero -- mismo comportamiento pre-fix.
    lfm_client = None
    try:
        from src.api.factories.service_factory import ServiceFactory
        _vs_engine = await ServiceFactory.get_mcp_recommender()
        if (_vs_engine
                and hasattr(_vs_engine, '_lfm_mcp_enabled')
                and _vs_engine._lfm_mcp_enabled
                and hasattr(_vs_engine, '_lfm_client')
                and _vs_engine._lfm_client):
            lfm_client = _vs_engine._lfm_client
    except Exception as _e:
        logger.warning('vs_lfm_engine_client_unavailable',
                       error=str(_e) or repr(_e))

    if lfm_client is not None:
        try:
            resp = await _asyncio_vsm.wait_for(
                lfm_client.complete(system_prompt, user_prompt),
                timeout=10.0,
            )
            logger.info('visual_search_message_lfm_ok', model=resp.model)
            return resp.content
        except Exception as e:
            logger.warning('visual_search_message_lfm_failed',
                           error=str(e) or repr(e),
                           error_type=type(e).__name__)

    # GPT-4o-mini: usa el singleton _vs_gpt4o_client, pre-calentado en
    # lifespan por warmup_vs_gpt4o_singleton() (PASO 8.5e).
    gpt4o_client = _get_vs_gpt4o_client()
    if gpt4o_client is not None:
        try:
            resp = await _asyncio_vsm.wait_for(
                gpt4o_client.complete(system_prompt, user_prompt),
                timeout=8.0,
            )
            logger.info('visual_search_message_gpt4o_mini_ok', model=resp.model)
            return resp.content
        except Exception as e:
            logger.warning('visual_search_message_gpt4o_mini_failed',
                           error=str(e) or repr(e),
                           error_type=type(e).__name__)

    return None


# ── Endpoint principal: búsqueda visual ───────────────────────────────────────

@router.post('/v1/mcp/visual-search', response_model=VisualSearchResponse)
async def visual_search(
    file: UploadFile = File(..., description='Imagen del producto (JPEG/PNG/WebP, max 5MB)'),
    market_id: str = Form(default='ES', description='Mercado para precios'),
    top_k: int = Form(default=8, description='Número máximo de resultados'),
    language: str = Form(default='es', description="Idioma del mensaje generado: 'es', 'en', 'fr', 'it' o 'de'"),
    api_key: str = Depends(get_api_key),
):
    """
    Busca productos visualmente similares a la imagen subida.

    Flujo:
        1. Validar flag y archivo
        2. Llamar embedding-service → product_ids (fashionSigLIP + FAISS)
        3. Resolver productos completos desde tfidf_recommender.id_index
        4. Sanitizar y devolver en formato ProductRecommendation
    """
    t_start = time.time()

    if not _visual_search_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                'error': 'visual_search_disabled',
                'message': 'Visual search is not enabled. Set VISUAL_SEARCH_ENABLED=true.',
            }
        )

    if file.content_type and not file.content_type.startswith('image/'):
        raise HTTPException(400, detail=f'Expected image file, got: {file.content_type}')

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, 'Empty file')
    if len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(413, detail=f'Image too large ({len(image_bytes)//1024}KB). Max 5MB.')

    logger.info('visual_search_request', market_id=market_id,
                image_size_kb=round(len(image_bytes) / 1024, 1), top_k=top_k)

    # Usa el singleton — el token IAM se cachea entre requests
    colbert_client = _get_colbert_client()
    product_ids    = await colbert_client.search_by_image(image_bytes, top_k=top_k)

    if product_ids is None:
        raise HTTPException(503, detail='Visual search temporarily unavailable. Please try again.')

    if not product_ids:
        return VisualSearchResponse(recommendations=[], total_found=0,
                                    latency_ms=round((time.time() - t_start) * 1000, 1))

    # ── Market price resolution (mismo patron que /outfit — Mayo 2026) ────────
    # FIX (28/05/2026): El endpoint /v1/mcp/visual-search recibía market_id
    # pero lo ignoraba: devolvía precios CLP con símbolo € (default de
    # sanitize_rec_for_frontend). Ahora aplica el mismo flujo de 3 fases
    # que el endpoint /outfit: Redis → Shopify → CLP_RATES fallback.
    import json as _json_vs
    import asyncio as _asyncio

    # Tasas de conversión CLP → moneda del mercado (fallback si Shopify no responde).
    # Fuente: logs de producción 2026-05-18. Coincidir con las de /outfit.
    _VS_CLP_RATES: dict = {
        'CL': {'rate': 1.0,     'currency': 'CLP'},
        'CH': {'rate': 0.00089, 'currency': 'CHF'},   # verificado en produccion
        'MX': {'rate': 0.18,    'currency': 'MXN'},
        'ES': {'rate': 0.00088, 'currency': 'EUR'},
        'US': {'rate': 0.00104, 'currency': 'USD'},
    }

    # Obtener Redis y Shopify (singleton httpx — pool TCP ya caliente).
    _vs_redis   = None
    _vs_shopify = None
    try:
        from src.api.factories.service_factory import ServiceFactory
        _vs_redis = await ServiceFactory.get_redis_service()
    except Exception:
        pass
    try:
        from src.api.integrations.shopify_client import ShopifyIntegration
        import os as _os_vs
        _vs_shopify = ShopifyIntegration(
            shop_url=_os_vs.environ.get('SHOPIFY_SHOP_URL', ''),
            access_token=_os_vs.environ.get('SHOPIFY_ACCESS_TOKEN', ''),
        )
    except Exception:
        pass

    # Fase 1: Redis lookup — comparte cache 'price:{pid}' con /outfit y lazy-price.
    _all_vs_pids: list       = [str(pid) for pid in product_ids]
    _vs_redis_prices: dict   = {}   # pid -> {market_id: {price, currency}}
    _ids_for_shopify_vs: list = []

    if _vs_redis:
        for _pid in _all_vs_pids:
            try:
                _raw = await _vs_redis.get(f'price:{_pid}')
                if _raw:
                    _vs_redis_prices[_pid] = _json_vs.loads(_raw)
                    continue
            except Exception:
                pass
            _ids_for_shopify_vs.append(_pid)
    else:
        _ids_for_shopify_vs = list(_all_vs_pids)

    # Fase 2: Shopify para productos sin precio en Redis (warm pool ~300-600ms).
    # Timeout 5s: si Shopify no responde, se usa CLP_RATES como fallback.
    _vs_shopify_prices: dict = {}
    if _ids_for_shopify_vs and _vs_shopify:
        try:
            _vs_shopify_prices = await _asyncio.wait_for(
                _vs_shopify.get_prices_for_products(_ids_for_shopify_vs),
                timeout=5.0,
            )
            # Escribir en Redis para próximos requests (TTL 1h, comparte key con /outfit)
            if _vs_redis and _vs_shopify_prices:
                for _pid, _price_by_mkt in _vs_shopify_prices.items():
                    try:
                        await _vs_redis.set(
                            f'price:{_pid}',
                            _json_vs.dumps(_price_by_mkt),
                            ttl=3600,
                        )
                    except Exception:
                        pass
                logger.info(
                    'visual_search_prices_from_shopify',
                    products=len(_vs_shopify_prices),
                    market_id=market_id,
                    cached_in_redis=bool(_vs_redis),
                )
        except _asyncio.TimeoutError:
            logger.warning(
                'visual_search_shopify_timeout',
                timeout_s=5.0,
                fallback='CLP_RATES',
            )
        except Exception as _vs_e:
            logger.warning('visual_search_shopify_error', error=str(_vs_e))

    # Fase 3: Resolver productos con precio de mercado correcto.
    # Prioridades (misma jerarquía que /outfit):
    #   1. market_prices pre-computado en catálogo (startup Shopify bulk)
    #   2. Redis cache   (~1ms, escrito por lazy-price y por esta Fase 2)
    #   3. Shopify directo (obtenido en Fase 2, pool warm)
    #   4. CLP_RATES   (fallback si todo lo anterior falla)
    tfidf_recommender = _get_tfidf_recommender()
    resolved = []
    for pid in product_ids:
        prod = tfidf_recommender.id_index.get(str(pid))
        if prod:
            _spid = str(pid)
            mkt = prod.get('market_prices', {}).get(market_id, {})
            if mkt:
                # Prioridad 1: precio pre-computado en el catálogo
                price    = mkt.get('price') or prod.get('price')
                currency = mkt.get('currency', 'CLP')
            else:
                _redis_p  = _vs_redis_prices.get(_spid, {}).get(market_id)
                _shopify_p = _vs_shopify_prices.get(_spid, {}).get(market_id)
                _real_price = _redis_p or _shopify_p

                if _real_price:
                    # Prioridad 2/3: precio real de Shopify (Redis o directo)
                    price    = _real_price.get('price', 0)
                    currency = _real_price.get('currency', 'CLP')
                else:
                    # Prioridad 4: conversión local CLP → mercado
                    _mkt_cfg = _VS_CLP_RATES.get(market_id, _VS_CLP_RATES['CL'])
                    price    = round(float(prod.get('price') or 0) * _mkt_cfg['rate'], 2)
                    currency = _mkt_cfg['currency']

            resolved.append({
                **prod,
                'price':    price,     # override precio CLP del catálogo
                'currency': currency,  # garantiza moneda correcta en sanitize_rec_for_frontend
                'score':    1.0 - (len(resolved) * 0.05),
                'source':   'visual_search',
            })

    from src.api.routers.mcp_router import sanitize_rec_for_frontend
    sanitized  = [sanitize_rec_for_frontend(r) for r in resolved]

    # FIX (27/06/2026): generar mensaje descriptivo via LLM -- ver
    # _generate_visual_search_message() para el razonamiento completo.
    # Esto corre DESPUES de resolver precios (necesita title+price+currency
    # reales para el prompt) y ANTES de medir latency_ms final, asi que el
    # costo de esta llamada queda reflejado honestamente en latency_ms.
    _vs_message = await _generate_visual_search_message(sanitized, language)

    elapsed_ms = round((time.time() - t_start) * 1000, 1)

    logger.info('visual_search_complete', market_id=market_id,
                found=len(sanitized), latency_ms=elapsed_ms,
                message_generated=bool(_vs_message))

    return VisualSearchResponse(
        recommendations=sanitized, total_found=len(sanitized), latency_ms=elapsed_ms,
        message=_vs_message,
    )


# ── Endpoint ops: indexación COMPLETA ────────────────────────────────────────

@router.post('/v1/mcp/visual-search/index', include_in_schema=True)
async def trigger_visual_indexation(api_key: str = Depends(get_api_key)):
    """
    Lanza re-indexación COMPLETA del catálogo de imágenes (~30 min).

    Usar cuando:
      - Primer deploy del embedding-service con fashionSigLIP
      - Hay productos eliminados del catálogo
      - Hay productos con imagen cambiada (mismo ID, nueva image_url)

    Para añadir solo productos nuevos: POST /v1/mcp/visual-search/index/update
    """
    tfidf_recommender = _get_tfidf_recommender()
    client = _get_colbert_client()

    products_for_indexation = [
        {
            'id':           str(p.get('id', '')),
            'title':        p.get('title', ''),
            'image_url':    p.get('image_url', ''),
            # S1: product_type necesario para construir el category_map de outfit search
            'product_type': p.get('product_type', ''),
        }
        for p in tfidf_recommender.product_data
        if p.get('image_url')
    ]

    accepted = await client.index_images(products_for_indexation)
    if not accepted:
        raise HTTPException(503, 'Failed to trigger image indexation')

    return {
        'status': 'accepted',
        'mode': 'full',
        'products_submitted': len(products_for_indexation),
        'message': f'Full image indexation started in background (~25 min for {len(products_for_indexation)} products).',
    }


# ── Endpoint ops: indexación INCREMENTAL ─────────────────────────────────────

@router.post('/v1/mcp/visual-search/index/update', include_in_schema=True)
async def trigger_incremental_indexation(api_key: str = Depends(get_api_key)):
    """
    Lanza indexación INCREMENTAL: solo añade productos nuevos al índice.

    El embedding-service detecta automáticamente qué IDs ya están en el
    índice FAISS y solo procesa los nuevos.

    Limitaciones:
      - NO elimina productos borrados (usar /index para eso)
      - NO actualiza productos con imagen cambiada (mismo ID, nueva URL)
      - Requiere que exista un índice base previo
    """
    tfidf_recommender = _get_tfidf_recommender()
    client = _get_colbert_client()

    all_products = [
        {
            'id':           str(p.get('id', '')),
            'title':        p.get('title', ''),
            'image_url':    p.get('image_url', ''),
            # S1: product_type necesario para category_map en indexación incremental
            'product_type': p.get('product_type', ''),
        }
        for p in tfidf_recommender.product_data
        if p.get('image_url')
    ]

    accepted = await client.index_images_incremental(all_products)
    if not accepted:
        raise HTTPException(
            503,
            detail='Incremental indexation unavailable. Run POST /v1/mcp/visual-search/index first.'
        )

    return {
        'status': 'accepted',
        'mode': 'incremental',
        'products_submitted': len(all_products),
        'message': 'Incremental indexation started. Only new products will be processed.',
    }


# ── S1 FASE 2 (13/05/2026): Búsqueda por outfit completo ──────────────────────────

@router.post('/v1/mcp/visual-search/outfit')
async def visual_search_outfit(
    file:               UploadFile = File(..., description='Foto del outfit (JPEG/PNG/WebP, max 5MB)'),
    market_id:          str        = Form(default='ES', description='Mercado: CL, CH, MX, ES'),
    top_k_per_category: int        = Form(default=3, description='Máx productos por categoría'),
    alpha:              float      = Form(default=0.7, description='Peso imagen vs texto (0.7 = 70% imagen)'),
    api_key:            str        = Depends(get_api_key),
):
    """
    Dado un outfit completo, devuelve productos similares para cada categoría de prenda.

    El sistema usa FashionSigLIP con Composite Embedding:
      query_categoria = normalize(alpha * image_embed + (1-alpha) * text_embed(categoria))

    Cada categoría usa el mismo embedding de imagen pero combinado con un
    texto diferente ('dress', 'top', 'shoes'...) para orientar la búsqueda.

    Respuesta:
      {
        "outfit": {
          "dress":     [{product_id, title, image_url, price, currency, ...}],
          "top":       [{...}],
          "shoes":     [{...}],
          "accessory": [{...}]
        },
        "outfit_mode":       "composite_category_filtered",
        "market_id":         "ES",
        "latency_ms":        487.3,
        "category_map_size": 3028
      }
    """
    t_start = time.time()

    # ─ Guard: feature flag ────────────────────────────────────────────────────
    if not _visual_search_enabled():
        raise HTTPException(
            status_code=503,
            detail={'error': 'visual_search_disabled',
                    'message': 'Set VISUAL_SEARCH_ENABLED=true to enable outfit search.'}
        )

    # ─ Guard: validar imagen ────────────────────────────────────────────────
    if file.content_type and not file.content_type.startswith('image/'):
        raise HTTPException(400, detail=f'Expected image, got: {file.content_type}')
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, 'Empty file')
    if len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(413, detail=f'Image too large ({len(image_bytes)//1024}KB). Max 5MB.')

    logger.info('outfit_search_request', market_id=market_id,
                image_size_kb=round(len(image_bytes)/1024, 1),
                top_k_per_category=top_k_per_category, alpha=alpha)

    # ─ Llamar al embedding-service ─────────────────────────────────────────────
    # Reutiliza el singleton del cliente (mismo circuit-breaker y token IAM
    # que visual_search). Todas las categorías del catálogo real de Shopify:
    ALL_OUTFIT_CATEGORIES = [
        "dress", "enterito", "top", "bottom",
        "conjunto", "shoes", "bag", "accessory", "outerwear"
    ]
    colbert    = _get_colbert_client()
    raw_outfit = await colbert.search_outfit_by_image(
        image_bytes=image_bytes,
        target_categories=ALL_OUTFIT_CATEGORIES,
        top_k_per_category=top_k_per_category,
        alpha=alpha,
    )

    if raw_outfit is None:
        raise HTTPException(503, detail='Outfit search unavailable (circuit breaker open).')

    # ─ Resolver IDs → productos completos con precio de mercado ────────────
    tfidf_rec = _get_tfidf_recommender()
    META_KEYS = {'outfit_mode', 'latency_ms', 'visual_index_size', 'category_map_size'}

    # Tasas de conversion CLP → moneda del mercado.
    # Deben coincidir con las usadas en mcp_conversation_handler.py.
    # Fuente: logs de produccion 2026-05-18: rate 0.00089 para CHF.
    # Se usan cuando market_prices no esta pre-computado en el catalogo
    # (tfidf_rec.id_index solo tiene precio base en CLP).
    _CLP_MARKET_RATES: dict = {
        'CL': {'rate': 1.0,     'currency': 'CLP'},
        'CH': {'rate': 0.00089, 'currency': 'CHF'},   # verificado en produccion
        'MX': {'rate': 0.18,    'currency': 'MXN'},
        'ES': {'rate': 0.00088, 'currency': 'EUR'},
        'US': {'rate': 0.00104, 'currency': 'USD'},   # 1/961 CLP/USD
    }

    # FIX (13/05/2026): El endpoint /v1/embed/search-outfit del embedding-service
    # retorna la respuesta envuelta en un campo 'outfit' por el modelo Pydantic
    # OutfitSearchResponse:
    #   {"outfit": {"dress": [...], "top": [...]}, "outfit_mode": ..., ...}
    #
    # El router esperaba categorías planas al nivel raíz:
    #   {"dress": [...], "top": [...], "outfit_mode": ..., ...}
    #
    # Bug: el loop ve category='outfit', product_ids=dict (no lista) → skip → outfit={}
    # Fix: extraer el dict anidado si existe; fallback a formato plano si no.
    if 'outfit' in raw_outfit and isinstance(raw_outfit.get('outfit'), dict):
        categories_to_resolve = raw_outfit['outfit']   # formato anidado (embedding-service actual)
    else:
        categories_to_resolve = {                       # formato plano (backward compat)
            k: v for k, v in raw_outfit.items() if k not in META_KEYS
        }

    logger.info(
        'outfit_resolving_products',
        categories=list(categories_to_resolve.keys()),
        raw_keys=list(raw_outfit.keys()),
        id_index_size=len(tfidf_rec.id_index),
    )

    # ── PARTE D (Sprint lazy-price 21/05/2026): Obtener Redis para lookup de precios ─────
    # Comparte el cache price:{product_id} que escribe _enrich_recommendations_lazy().
    # Si Redis falla o no está disponible, el fallback a CLP_RATES sigue activo.
    # La variable es local al request: sin estado compartido entre requests.
    import json as _json_vs
    import asyncio as _asyncio
    _outfit_redis = None
    _outfit_shopify = None
    try:
        from src.api.factories.service_factory import ServiceFactory
        _outfit_redis = await ServiceFactory.get_redis_service()
    except Exception:
        pass
    try:
        # ShopifyIntegration reutiliza el singleton httpx (_get_shopify_httpx_client),
        # por lo que crear una instancia aqui NO crea una nueva conexion TCP.
        # El pool TCP ya esta caliente de los requests de conversacion previos.
        from src.api.integrations.shopify_client import ShopifyIntegration
        import os as _os
        _outfit_shopify = ShopifyIntegration(
            shop_url=_os.environ.get("SHOPIFY_SHOP_URL", ""),
            access_token=_os.environ.get("SHOPIFY_ACCESS_TOKEN", ""),
        )
    except Exception:
        pass

    # ── FASE 1: Colectar todos los PIDs del outfit y verificar Redis ──────────────
    # Un solo recorrido para determinar que productos necesitan Shopify.
    _all_outfit_pids = []
    for _cat, _pids in categories_to_resolve.items():
        if isinstance(_pids, list):
            for _pid in _pids:
                _spid = str(_pid)
                if _spid not in _all_outfit_pids:
                    _all_outfit_pids.append(_spid)

    _outfit_redis_prices: dict = {}   # pid -> {market_id: {price, currency}}
    _ids_for_shopify: list = []

    if _outfit_redis:
        for _pid in _all_outfit_pids:
            try:
                _raw = await _outfit_redis.get(f'price:{_pid}')
                if _raw:
                    _outfit_redis_prices[_pid] = _json_vs.loads(_raw)
                    continue
            except Exception:
                pass
            _ids_for_shopify.append(_pid)
    else:
        _ids_for_shopify = list(_all_outfit_pids)

    # ── FASE 2: Shopify para los productos sin precio en Redis ────────────────────
    # httpx warm pool: ~300-600ms para todos los productos del outfit.
    # Timeout 5s: si Shopify no responde, se usa CLP_RATES como fallback.
    _outfit_shopify_prices: dict = {}
    if _ids_for_shopify and _outfit_shopify:
        try:
            _outfit_shopify_prices = await _asyncio.wait_for(
                _outfit_shopify.get_prices_for_products(_ids_for_shopify),
                timeout=5.0
            )
            # Escribir en Redis para proximos requests (TTL 1h)
            if _outfit_redis and _outfit_shopify_prices:
                for _pid, _price_by_mkt in _outfit_shopify_prices.items():
                    try:
                        await _outfit_redis.set(
                            f'price:{_pid}',
                            _json_vs.dumps(_price_by_mkt),
                            ttl=3600
                        )
                    except Exception:
                        pass
                logger.info(
                    'outfit_prices_from_shopify',
                    products=len(_outfit_shopify_prices),
                    market_id=market_id,
                    cached_in_redis=bool(_outfit_redis)
                )
        except _asyncio.TimeoutError:
            logger.warning('outfit_shopify_timeout', timeout_s=5.0,
                           fallback='CLP_RATES')
        except Exception as _e:
            logger.warning('outfit_shopify_error', error=str(_e))

    outfit_resolved: dict = {}
    for category, product_ids in categories_to_resolve.items():
        if not isinstance(product_ids, list) or not product_ids:
            continue

        cat_products = []
        for pid in product_ids:
            prod = tfidf_rec.id_index.get(str(pid))
            if not prod:
                logger.debug('outfit_product_not_found', pid=pid, category=category)
                continue
            # DESPUÉS — FIX Mayo 2026: conversión local CLP→mercado
            mkt = prod.get('market_prices', {}).get(market_id, {})

            # market_prices no está pre-computado en tfidf_rec.id_index.
            # El flujo de conversación lo obtiene via lazy-price (~10s de Shopify),
            # pero el outfit endpoint no puede asumir esa latencia.
            # Solución: conversión local CLP→mercado cuando mkt está vacío.
            if mkt:
                price    = mkt.get('price') or prod.get('price')
                currency = mkt.get('currency', 'CLP')
            else:
                # Prioridad 1: Redis cache (precio real de Shopify, < 1ms)
                _redis_price = _outfit_redis_prices.get(str(pid), {}).get(market_id)
                # Prioridad 2: Shopify directo (obtenido en Fase 2, warm pool)
                _shopify_price = _outfit_shopify_prices.get(str(pid), {}).get(market_id)
                _real_price = _redis_price or _shopify_price

                if _real_price:
                    price    = _real_price.get('price', 0)
                    currency = _real_price.get('currency', 'CLP')
                else:
                    # Prioridad 3: Conversión local (fallback si Shopify no respondió)
                    market_cfg = _CLP_MARKET_RATES.get(market_id, _CLP_MARKET_RATES['CL'])
                    base_clp   = float(prod.get('price') or 0)
                    price      = round(base_clp * market_cfg['rate'], 2)
                    currency   = market_cfg['currency']

            cat_products.append({
                'product_id':   str(pid),
                'title':        prod.get('title', ''),
                'image_url':    prod.get('image_url', ''),
                'product_type': prod.get('product_type', ''),
                'handle':       prod.get('handle', ''),
                'price':        price,
                'currency':     currency,
                'category':     category,
            })
        if cat_products:
            outfit_resolved[category] = cat_products

    # ─ Respuesta ────────────────────────────────────────────────────────────────────
    total_ms = round((time.time() - t_start) * 1000, 1)
    logger.info(
        'outfit_search_complete',
        market_id=market_id,
        categories_found=list(outfit_resolved.keys()),
        total_products=sum(len(v) for v in outfit_resolved.values()),
        outfit_mode=raw_outfit.get('outfit_mode', 'unknown'),
        total_latency_ms=total_ms,
    )
    return {
        'outfit':            outfit_resolved,
        'outfit_mode':       raw_outfit.get('outfit_mode', 'unknown'),
        'market_id':         market_id,
        'latency_ms':        total_ms,
        'category_map_size': raw_outfit.get('category_map_size', 0),
    }
