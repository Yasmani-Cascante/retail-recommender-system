# services/embedding-service/main.py
"""
LFM2-ColBERT Embedding Service
================================
Microservicio FastAPI que expone el modelo LFM2-ColBERT-350M
para búsqueda semántica de productos.

Endpoints:
  POST /v1/embed/index   — indexar catálogo de productos
  POST /v1/embed/search  — buscar productos por query
  GET  /health           — health check
"""
import os
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

log = logging.getLogger(__name__)
colbert_retriever = None  # Singleton — se carga en startup


# ── Pydantic models ─────────────────────────────────────────────────

class IndexRequest(BaseModel):
    products: List[dict]  # [{id, title, description, tags}, ...]


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10


class SearchResponse(BaseModel):
    product_ids: List[str]
    latency_ms: float


# ── Startup / shutdown ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global colbert_retriever
    log.info('Loading LFM2-ColBERT-350M...')
    t0 = time.time()
    from colbert_retriever import LFM2ColBERTRetriever
    colbert_retriever = LFM2ColBERTRetriever()
    await colbert_retriever.warmup()
    log.info('ColBERT ready in %.1fs', time.time() - t0)
    yield
    log.info('Embedding service shutdown')


app = FastAPI(title='LFM2-ColBERT Embedding Service', lifespan=lifespan)


# ── Routes ──────────────────────────────────────────────────────────

@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'model': 'LFM2-ColBERT-350M',
        'index_size': colbert_retriever.index_size() if colbert_retriever else 0,
    }


@app.post('/v1/embed/index')
async def build_index(req: IndexRequest):
    """
    Recibe el catálogo de productos y construye el PLAID index.
    Se llama durante el KB sync / catalog update del monolito.
    Con 3000 productos: ~5-10 segundos.
    """
    if not colbert_retriever:
        raise HTTPException(503, 'Model not ready')
    t0 = time.time()
    count = await colbert_retriever.build_index(req.products)
    return {
        'indexed': count,
        'latency_ms': round((time.time() - t0) * 1000, 1),
    }


@app.post('/v1/embed/search', response_model=SearchResponse)
async def search(req: SearchRequest):
    """
    Busca los productos más relevantes para una query.
    Soporta queries en español, inglés, francés, alemán nativamente.
    Latencia warm: 20-40ms.
    """
    if not colbert_retriever:
        raise HTTPException(503, 'Model not ready')
    t0 = time.time()
    ids = await colbert_retriever.search(req.query, req.top_k)
    return SearchResponse(
        product_ids=ids,
        latency_ms=round((time.time() - t0) * 1000, 1))