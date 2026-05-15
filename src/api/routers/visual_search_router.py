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


def _get_tfidf_recommender():
    from src.api.main_unified_redis import tfidf_recommender
    if not tfidf_recommender or not getattr(tfidf_recommender, 'id_index', None):
        logger.error('visual_search_catalog_not_loaded')
        raise HTTPException(status_code=503, detail='Product catalog not loaded')
    return tfidf_recommender


# ── Endpoint principal: búsqueda visual ───────────────────────────────────────

@router.post('/v1/mcp/visual-search', response_model=VisualSearchResponse)
async def visual_search(
    file: UploadFile = File(..., description='Imagen del producto (JPEG/PNG/WebP, max 5MB)'),
    market_id: str = Form(default='ES', description='Mercado para precios'),
    top_k: int = Form(default=8, description='Número máximo de resultados'),
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

    tfidf_recommender = _get_tfidf_recommender()
    resolved = []
    for pid in product_ids:
        product = tfidf_recommender.id_index.get(str(pid))
        if product:
            resolved.append({
                **product,
                'score': 1.0 - (len(resolved) * 0.05),
                'source': 'visual_search',
            })

    from src.api.routers.mcp_router import sanitize_rec_for_frontend
    sanitized  = [sanitize_rec_for_frontend(r) for r in resolved]
    elapsed_ms = round((time.time() - t_start) * 1000, 1)

    logger.info('visual_search_complete', market_id=market_id,
                found=len(sanitized), latency_ms=elapsed_ms)

    return VisualSearchResponse(
        recommendations=sanitized, total_found=len(sanitized), latency_ms=elapsed_ms,
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
            mkt = prod.get('market_prices', {}).get(market_id, {})
            cat_products.append({
                'product_id':   str(pid),
                'title':        prod.get('title', ''),
                'image_url':    prod.get('image_url', ''),
                'product_type': prod.get('product_type', ''),
                'handle':       prod.get('handle', ''),
                'price':        mkt.get('price') or prod.get('price'),
                'currency':     mkt.get('currency', 'CLP'),
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
