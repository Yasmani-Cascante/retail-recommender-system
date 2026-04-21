# src/api/services/colbert_client.py
"""
Cliente HTTP para el LFM2-ColBERT embedding microservice.
El monolito llama a este cliente cuando LFM_COLBERT_ENABLED=true.
"""
import os, httpx, asyncio, logging
from typing import List, Optional
 
log = logging.getLogger(__name__)
 
class LFM2ColBERTClient:
    """
    Thin HTTP client para el embedding-service.
    Incluye timeout, retry y circuit-breaker básico.
    """
 
    def __init__(self):
        base_url = os.environ.get('COLBERT_SERVICE_URL', '')
        if not base_url:
            raise ValueError('COLBERT_SERVICE_URL env var not set')
        # httpx.AsyncClient con timeout ajustado a latencia esperada (~30ms warm)
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(5.0),   # 5s incluye startup si hay cold start
            headers={'Content-Type': 'application/json'}
        )
        self._consecutive_failures = 0
        self._circuit_open = False
 
    async def search(self, query: str, top_k: int = 10) -> Optional[List[str]]:
        """
        Busca productos semánticamente.
        Returns: lista de product IDs, o None si falla (caller usa fallback TF-IDF).
        """
        if self._circuit_open:
            log.debug('ColBERT circuit open — skipping')
            return None
 
        try:
            resp = await self._http.post(
                '/v1/embed/search',
                json={'query': query, 'top_k': top_k}
            )
            resp.raise_for_status()
            data = resp.json()
            self._consecutive_failures = 0   # reset on success
            log.debug('ColBERT search: %d results in %.1fms',
                      len(data['product_ids']), data['latency_ms'])
            return data['product_ids']
        except Exception as e:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self._circuit_open = True
                log.error('ColBERT circuit OPEN after 3 failures: %s', e)
                # asyncio.get_running_loop() — API correcta en Python 3.10+.
                # call_later programa el reset del circuit breaker sin bloquear.
                asyncio.get_running_loop().call_later(
                    60, setattr, self, '_circuit_open', False
                )
            log.warning('ColBERT search failed (attempt %d): %s',
                        self._consecutive_failures, e)
            return None   # Fallback a TF-IDF en el caller
 
    async def index_catalog(self, products: List[dict]) -> bool:
        """
        Llama al endpoint de indexación después de un catalog sync.
        Llamar desde: ShopifyKBSyncService después de sincronizar productos.
        """
        try:
            resp = await self._http.post(
                '/v1/embed/index',
                json={'products': products},
                timeout=120.0   # Indexar 3000 productos toma ~10s
            )
            resp.raise_for_status()
            data = resp.json()
            log.info('ColBERT re-indexed: %d products in %.1fms',
                     data['indexed'], data['latency_ms'])
            return True
        except Exception as e:
            log.error('ColBERT index failed: %s', e, exc_info=True)
            return False
