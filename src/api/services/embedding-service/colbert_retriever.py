# services/embedding-service/colbert_retriever.py
"""
LFM2ColBERTRetriever — wrapper sobre pylate + LFM2-ColBERT-350M

Arquitectura del índice:
  - Los embeddings de documentos se pre-calculan y se guardan en disco
    (PLAID index) en /tmp/colbert-index/
  - El índice persiste mientras el contenedor esté vivo (min=1 garantiza esto)
  - Si el contenedor se reinicia, se necesita re-indexar (POST /v1/embed/index)
  - El monolito debe llamar a /v1/embed/index después de cada catalog sync
"""
import asyncio
import logging
from typing import List
from pathlib import Path

log = logging.getLogger(__name__)
INDEX_PATH = Path('/tmp/colbert-index')


class LFM2ColBERTRetriever:

    def __init__(self):
        from pylate import models
        log.info('Loading LFM2-ColBERT-350M from HuggingFace...')
        self.model = models.ColBERT(
            model_name_or_path='LiquidAI/LFM2-ColBERT-350M'
        )
        # eos_token como pad_token — requerido por LFM2-ColBERT
        self.model.tokenizer.pad_token = self.model.tokenizer.eos_token
        self._index = None
        self._indexed_count = 0

    async def warmup(self):
        """Pre-calcula un forward pass dummy para JIT-compilar el grafo."""
        log.info('Running ColBERT warmup...')
        # get_running_loop() es la API correcta dentro de una coroutine activa.
        # get_event_loop() esta deprecado en Python 3.10+ cuando se llama desde
        # dentro de una coroutine y emite DeprecationWarning en FastAPI.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self.model.encode(['warmup query'], is_query=True),
        )
        log.info('ColBERT warmup complete')

    async def build_index(self, products: list) -> int:
        """
        Construye el PLAID index con los productos del catálogo.
        Combina title + description + tags para richer semantic signal.
        Diseñado para correr en background, no bloquea el event loop.
        """
        from pylate import indexes
        loop = asyncio.get_running_loop()

        doc_ids = [str(p['id']) for p in products]
        doc_texts = [
            f"{p.get('title', '')} {p.get('description', '')} {' '.join(p.get('tags', []))}"
            for p in products
        ]

        def _build():
            embeddings = self.model.encode(
                doc_texts,
                batch_size=32,
                is_query=False,
                show_progress_bar=True,
            )
            INDEX_PATH.mkdir(parents=True, exist_ok=True)
            idx = indexes.PLAID(
                index_folder=str(INDEX_PATH),
                index_name='catalog',
                override=True,
            )
            idx.add_documents(
                documents_ids=doc_ids,
                documents_embeddings=embeddings,
            )
            return idx, len(products)

        self._index, self._indexed_count = await loop.run_in_executor(None, _build)
        log.info('PLAID index built: %d products', self._indexed_count)
        return self._indexed_count

    async def search(self, query: str, top_k: int = 10) -> List[str]:
        """
        Encode query y busca en el PLAID index.
        Cross-lingual: query en ES funciona con productos en EN.
        Latencia warm: ~20-40ms en CPU.
        """
        if self._index is None:
            log.warning('ColBERT index not built — returning empty results')
            return []

        from pylate import retrieve
        loop = asyncio.get_running_loop()

        def _search():
            q_emb = self.model.encode([query], is_query=True)
            retriever = retrieve.ColBERT(index=self._index)
            results = retriever.retrieve(
                queries_embeddings=q_emb,
                top_k=top_k,
            )
            return [r['id'] for r in results[0]]

        return await loop.run_in_executor(None, _search)

    def index_size(self) -> int:
        return self._indexed_count