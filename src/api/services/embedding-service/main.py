# services/embedding-service/main.py
"""
Embedding Service — búsqueda semántica + búsqueda visual
==========================================================
Microservicio FastAPI con dos capacidades independientes:

  [Texto — ColBERT, ya existente]
  POST /v1/embed/index         — indexar catálogo (PLAID index)
  POST /v1/embed/search        — buscar por query textual

  [Visual — fashionSigLIP + FAISS, añadido Opción A]
  POST /v1/embed/index-images  — indexar imágenes (full o incremental)
  POST /v1/embed/search-image  — buscar por imagen (multipart)

  GET  /health                 — estado de ambos modelos e índices

Cambios:
  01/05/2026 — IndexImagesRequest.mode: 'full' | 'incremental'
               El endpoint /v1/embed/index-images rutea al método correcto
               según el campo mode. El modo incremental añade solo los
               productos nuevos sin reconstruir el índice completo.

  01/05/2026 — Autenticación IAM: el servicio solo acepta requests con
               Authorization: Bearer <google-id-token> de la SA del monolito.
               Configurado en el deploy con --no-allow-unauthenticated.
               El header lo añade automáticamente colbert_client.py.
"""
import os
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import List, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger(__name__)

colbert_retriever = None
visual_retriever  = None


# ── Pydantic models ─────────────────────────────────────────────────────────

class IndexRequest(BaseModel):
    products: List[dict]


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10


class SearchResponse(BaseModel):
    product_ids: List[str]
    latency_ms: float


class IndexImagesRequest(BaseModel):
    """
    Solicitud de indexación de imágenes del catálogo.

    mode:
      'full'        — Reconstruye el índice completo desde cero (~25-30 min
                      para 3000+ productos). Usar en primer deploy y cuando
                      hay productos eliminados o imágenes cambiadas.

      'incremental' — Solo indexa productos nuevos (IDs no en el índice actual).
                      El índice base debe existir previamente.
                      Típico: <1 min para pocos productos nuevos.
                      Limitación: no elimina productos borrados del índice.
    """
    products:   List[dict]
    batch_size: int = 16
    mode:       Literal['full', 'incremental'] = 'full'


class SearchImageResponse(BaseModel):
    product_ids: List[str]
    latency_ms: float
    visual_index_size: int


# ── Startup / shutdown ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global colbert_retriever, visual_retriever

    log.info('[startup] Loading LFM2-ColBERT-350M...')
    t0 = time.time()
    try:
        from colbert_retriever import LFM2ColBERTRetriever
        colbert_retriever = LFM2ColBERTRetriever()
        await colbert_retriever.warmup()
        log.info('[startup] ColBERT ready in %.1fs', time.time() - t0)
    except Exception as e:
        log.error('[startup] FATAL: ColBERT failed: %s', e, exc_info=True)
        raise

    log.info('[startup] Loading Marqo/marqo-fashionSigLIP (HF_HUB_OFFLINE=%s)...',
             os.environ.get('HF_HUB_OFFLINE', 'not set'))
    t1 = time.time()
    try:
        from visual_retriever import FashionSigLIPRetriever
        visual_retriever = FashionSigLIPRetriever()
        await visual_retriever.warmup()
        loaded = visual_retriever.try_load_from_disk()
        log.info('[startup] FashionSigLIP ready in %.1fs | visual_index_size=%d (disk_loaded=%s)',
                 time.time() - t1, visual_retriever.index_size(), loaded)
    except Exception as e:
        log.error('[startup] WARNING: FashionSigLIP failed in %.1fs: %s',
                  time.time() - t1, e, exc_info=True)
        visual_retriever = None

    log.info('[startup] Embedding service ready. ColBERT=%s FashionSigLIP=%s',
             'OK' if colbert_retriever else 'FAILED',
             'OK' if visual_retriever else 'UNAVAILABLE')
    yield
    log.info('[shutdown] Embedding service shutdown')


app = FastAPI(
    title='Embedding Service — ColBERT + FashionSigLIP',
    lifespan=lifespan,
)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'models': {
            'colbert': 'LFM2-ColBERT-350M',
            'visual':  'Marqo/marqo-fashionSigLIP',
        },
        'index_size':           colbert_retriever.index_size() if colbert_retriever else 0,
        'visual_index_size':    visual_retriever.index_size() if visual_retriever else 0,
        'visual_index_ready':   visual_retriever.is_ready() if visual_retriever else False,
        # S1: category_map_size > 0 indica que el outfit search está listo
        'category_map_size':    visual_retriever.category_map_size() if visual_retriever else 0,
        'outfit_search_ready':  (visual_retriever.category_map_size() > 0) if visual_retriever else False,
    }


@app.post('/v1/embed/index')
async def build_index(req: IndexRequest):
    if not colbert_retriever:
        raise HTTPException(503, 'Model not ready')
    t0 = time.time()
    count = await colbert_retriever.build_index(req.products)
    return {'indexed': count, 'latency_ms': round((time.time() - t0) * 1000, 1)}


@app.post('/v1/embed/search', response_model=SearchResponse)
async def search(req: SearchRequest):
    if not colbert_retriever:
        raise HTTPException(503, 'ColBERT model not ready')
    t0 = time.time()
    ids = await colbert_retriever.search(req.query, req.top_k)
    return SearchResponse(product_ids=ids, latency_ms=round((time.time() - t0) * 1000, 1))


@app.post('/v1/embed/index-images')
async def build_image_index(
    req: IndexImagesRequest,
    background_tasks: BackgroundTasks,
):
    """
    Indexa imágenes del catálogo en modo full o incremental.

    modo='full' (default):
      Reconstruye el índice completo. Tarda ~25-30 min para 3000+ productos.
      Usar en: primer deploy, productos eliminados, imágenes cambiadas.

    modo='incremental':
      Solo indexa productos nuevos (IDs no presentes en el índice actual).
      Tarda proporcional a los nuevos productos (típico: <1 min para <50 prods).
      Requiere que exista un índice base (si no, devuelve status='no_base_index').
      Limitación: no elimina del índice los productos borrados del catálogo.
      Para eso, usar mode='full'.

    Ambos modos usan batch size adaptativo:
      El batch_size inicial se ajusta tras el primer batch según velocidad
      de descarga observada del CDN de Shopify.
    """
    if not visual_retriever:
        raise HTTPException(503, 'Visual retriever not ready')

    if visual_retriever.is_indexing():
        return {
            'status': 'already_running',
            'message': 'Indexation already in progress. Check GET /health.',
            'visual_index_size': visual_retriever.index_size(),
        }

    products_snapshot = list(req.products)
    batch_size        = req.batch_size
    mode              = req.mode

    # ── Validación específica del modo incremental ─────────────────────────
    if mode == 'incremental' and not visual_retriever.is_ready():
        return {
            'status': 'no_base_index',
            'message': (
                'Incremental indexation requires an existing base index. '
                'Run mode=full first.'
            ),
        }

    async def _run_full():
        t_start = time.time()
        try:
            indexed, failed = await visual_retriever.build_image_index(
                products_snapshot, batch_size=batch_size,
            )
            log.info('[visual-index] Job complete (full): indexed=%d failed=%d elapsed=%.0fs',
                     indexed, failed, time.time() - t_start)
        except Exception as e:
            log.error('[visual-index] Job failed (full) after %.0fs: %s',
                      time.time() - t_start, e, exc_info=True)

    async def _run_incremental():
        t_start = time.time()
        try:
            status, indexed, skipped = await visual_retriever.build_image_index_incremental(
                products_snapshot, batch_size=batch_size,
            )
            log.info('[visual-index] Job complete (incremental): status=%s indexed=%d skipped=%d elapsed=%.0fs',
                     status, indexed, skipped, time.time() - t_start)
        except Exception as e:
            log.error('[visual-index] Job failed (incremental) after %.0fs: %s',
                      time.time() - t_start, e, exc_info=True)

    if mode == 'full':
        background_tasks.add_task(_run_full)
    else:
        background_tasks.add_task(_run_incremental)

    products_with_url = sum(
        1 for p in products_snapshot
        if p.get('image_url') and str(p.get('image_url', '')).startswith('http')
    )
    return {
        'status': 'accepted',
        'mode': mode,
        'message': (
            f'{mode.capitalize()} indexation of {products_with_url} products '
            f'with image_url started in background.'
        ),
        'products_submitted':  len(products_snapshot),
        'products_with_image': products_with_url,
    }


# ── S1: Endpoint de búsqueda de outfit completo ──────────────────────────────

class OutfitSearchResponse(BaseModel):
    outfit:            dict   # {category: [product_id, ...]}
    outfit_mode:       str    # 'composite_category_filtered' | 'degraded_no_category_map'
    latency_ms:        float
    visual_index_size: int
    category_map_size: int


@app.post('/v1/embed/search-outfit', response_model=OutfitSearchResponse)
async def search_outfit(
    file:       UploadFile = File(..., description='Foto del outfit (JPEG/PNG/WebP, max 5MB)'),
    categories: str        = Form(
        default='["dress","top","bottom","shoes"]',
        description='JSON array con categorías objetivo'
    ),
    top_k:      int        = Form(default=3, description='Máx resultados por categoría'),
    alpha:      float      = Form(default=0.7, description='Peso imagen vs texto (0-1)'),
):
    """
    S1: Búsqueda de outfit completo.

    Dado un outfit, devuelve product_ids para cada categoría solicitada
    usando Composite Embedding: alpha × imagen + (1-alpha) × texto_categoría.

    Modo degradado: si category_map está vacío (índice pre-S1), devuelve
    candidatos sin filtro de categoría. Rebuild para activar modo completo.
    """
    if not visual_retriever:
        raise HTTPException(503, 'Visual retriever not ready')
    if not visual_retriever.is_ready():
        raise HTTPException(503, 'Visual index not built — call POST /v1/embed/index-images first')

    content_type = file.content_type or ''
    if content_type and not content_type.startswith('image/'):
        raise HTTPException(400, f'Expected image file, got: {content_type}')

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, 'Empty file')
    if len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(413, f'Image too large: {len(image_bytes)//1024}KB. Max 5MB.')

    import json as _json
    try:
        target_cats = _json.loads(categories)
        if not isinstance(target_cats, list):
            raise ValueError('categories must be a JSON array')
    except Exception:
        target_cats = ['dress', 'top', 'bottom', 'shoes']

    t0     = time.time()
    outfit = await visual_retriever.search_outfit_by_image(
        image_bytes,
        target_categories=target_cats,
        top_k_per_category=top_k,
        alpha=alpha,
    )

    outfit_mode = outfit.pop('outfit_mode', 'unknown')
    latency_ms  = round((time.time() - t0) * 1000, 1)

    log.info('outfit_search: categories=%s found=%s mode=%s latency=%.1fms',
             target_cats, list(outfit.keys()), outfit_mode, latency_ms)

    return OutfitSearchResponse(
        outfit=outfit,
        outfit_mode=outfit_mode,
        latency_ms=latency_ms,
        visual_index_size=visual_retriever.index_size(),
        category_map_size=visual_retriever.category_map_size(),
    )


@app.post('/v1/embed/search-image', response_model=SearchImageResponse)
async def search_by_image(
    file: UploadFile = File(..., description='Imagen JPEG/PNG/WebP (max 5MB)'),
    top_k: int = Form(default=8, description='Número máximo de resultados'),
):
    if not visual_retriever:
        raise HTTPException(503, 'Visual retriever not ready')
    if not visual_retriever.is_ready():
        raise HTTPException(503, 'Visual index not built. Call POST /v1/embed/index-images first.')

    content_type = file.content_type or ''
    if content_type and not content_type.startswith('image/'):
        raise HTTPException(400, detail=f'Expected image file, got: {content_type}')

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(400, 'Empty file')

    max_bytes = 5 * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise HTTPException(
            413,
            detail=f'Image too large: {len(image_bytes)//1024}KB. Maximum allowed: {max_bytes//1024//1024}MB.'
        )

    t0 = time.time()
    product_ids = await visual_retriever.search_by_image(image_bytes, top_k=top_k)
    latency_ms  = round((time.time() - t0) * 1000, 1)

    log.info('visual_search: found=%d top_k=%d latency=%.1fms size=%dKB',
             len(product_ids), top_k, latency_ms, len(image_bytes) // 1024)

    return SearchImageResponse(
        product_ids=product_ids,
        latency_ms=latency_ms,
        visual_index_size=visual_retriever.index_size(),
    )


@app.get('/v1/embed/search-by-id', response_model=SearchImageResponse)
async def search_by_product_id(
    product_id: str  = Query(..., description='Shopify product ID numerico'),
    top_k:      int  = Query(default=8, description='Numero maximo de resultados'),
):
    """
    Busca productos visualmente similares a uno ya indexado, usando su vector
    FAISS almacenado. Evita el fetch del CDN y el encode FashionSigLIP.

    Latencia tipica: ~50ms (vs ~635ms de search-image con CDN fetch).
    Devuelve [] si el product_id no esta en el indice (producto no indexado aun).
    El llamante debe usar /v1/embed/search-image como fallback en ese caso.
    """
    if not visual_retriever or not visual_retriever.is_ready():
        raise HTTPException(503, 'Visual index not ready')

    t0 = time.time()
    product_ids = await visual_retriever.search_by_product_id(product_id, top_k=top_k)
    latency_ms  = round((time.time() - t0) * 1000, 1)

    log.info('search_by_product_id: product_id=%s found=%d latency=%.1fms',
             product_id, len(product_ids), latency_ms)

    return SearchImageResponse(
        product_ids=product_ids,
        latency_ms=latency_ms,
        visual_index_size=visual_retriever.index_size(),
    )
