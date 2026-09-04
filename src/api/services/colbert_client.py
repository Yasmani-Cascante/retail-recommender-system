# src/api/services/colbert_client.py
"""
Cliente HTTP para el embedding-service (ColBERT + FashionSigLIP).

El monolito llama a este cliente para:
  - Búsqueda semántica textual: search(query) — ColBERT
  - Búsqueda visual: search_by_image(image_bytes) — fashionSigLIP + FAISS
  - Indexación: index_catalog(products) / index_images(products)
  - Indexación incremental: index_images_incremental(new_products)

Características:
  - Circuit-breakers INDEPENDIENTES para texto y visual (30/04/2026)
  - Autenticación IAM service-to-service (01/05/2026)
  - Timeout conservador para búsqueda visual (8s vs 5s para texto)

──────────────────────────────────────────────────────────────────
AUTENTICACIÓN IAM SERVICE-TO-SERVICE (01/05/2026)
──────────────────────────────────────────────────────────────────
El embedding-service corre con --no-allow-unauthenticated.
Este cliente añade automáticamente el header:
  Authorization: Bearer <google-id-token>

Cómo funciona en Cloud Run:
  - En el monolito (Cloud Run): el metadata server de GCP devuelve el
    ID token de la SA del monolito (178362262166-compute@developer...).
    No se necesitan credenciales explícitas — ADC lo resuelve solo.
  - En local: necesita GOOGLE_APPLICATION_CREDENTIALS o ADC configurado
    (gcloud auth application-default login). Si ninguno está disponible,
    el cliente falla silenciosamente con WARNING y sigue sin auth.
  - Para desarrollo sin GCP: poner EMBEDDING_AUTH_DISABLED=true en .env.

El token tiene TTL de 1h. Lo cacheamos y lo renovamos 5 minutos antes
de que expire para evitar requests con token caducado.

Permisos IAM necesarios (ejecutar una sola vez):
  Método A — gcloud:
    gcloud run services add-iam-policy-binding retail-embedding-service \\
      --region us-central1 --project retail-recommendations-449216 \\
      --member "serviceAccount:178362262166-compute@developer.gserviceaccount.com" \\
      --role "roles/run.invoker"

  Método B — Terraform (si se usa):
    resource "google_cloud_run_service_iam_member" "monolith_invoker" {
      service  = "retail-embedding-service"
      location = "us-central1"
      role     = "roles/run.invoker"
      member   = "serviceAccount:178362262166-compute@developer.gserviceaccount.com"
    }

──────────────────────────────────────────────────────────────────
CONTENT-TYPE Y HTTPX (fix 30/04/2026)
──────────────────────────────────────────────────────────────────
El cliente NO establece Content-Type en los headers base.
POR QUÉ: este cliente hace dos tipos de requests incompatibles:
  - JSON: search(), index_catalog(), index_images(), index_images_incremental()
    → Requieren Content-Type: application/json
  - Multipart: search_by_image()
    → Requieren Content-Type: multipart/form-data; boundary=<hash>
    → httpx genera el boundary automáticamente cuando hay files=
    → PERO solo si el cliente base NO fuerza application/json

Cada método JSON declara explícitamente Content-Type.
search_by_image() no declara ninguno → httpx genera multipart/form-data.

──────────────────────────────────────────────────────────────────
CIRCUIT-BREAKERS SEPARADOS (01/05/2026)
──────────────────────────────────────────────────────────────────
Un fallo de search_by_image() NO abre el circuito de search() (texto)
y viceversa. Dominios completamente independientes.
"""
import os
import asyncio
import logging
import time
from typing import List, Optional

import httpx

log = logging.getLogger(__name__)


class LFM2ColBERTClient:
    """
    Thin HTTP client para el embedding-service.
    Incluye autenticación IAM, timeout, retry y circuit-breaker por dominio.
    """

    def __init__(self):
        base_url = os.environ.get('COLBERT_SERVICE_URL', '')
        if not base_url:
            raise ValueError('COLBERT_SERVICE_URL env var not set')

        # URL base sin trailing slash — usada como audience del ID token IAM.
        # El audience debe ser exactamente la URL del servicio Cloud Run.
        self._base_url = base_url.rstrip('/')

        # ── SIN Content-Type en headers base ──────────────────────────────────
        # Cada método declara su propio Content-Type.
        # El Authorization header se añade por método vía _auth_headers().
        # No se añade en el cliente base porque el token es asíncrono y el
        # constructor es síncrono.
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(5.0),   # default; se sobreescribe por método
        )

        # ── Autenticación IAM — caché del ID token ────────────────────────────
        # El token de Google Cloud ID tiene TTL de 1h.
        # Se carga lazy en el primer request y se renueva 5 min antes de expirar.
        # _token_expires_at = 0.0 fuerza la carga en el primer uso.
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

        # Flag para deshabilitar auth (útil en desarrollo local sin ADC)
        # EMBEDDING_AUTH_DISABLED=true → no añade Authorization header
        self._auth_disabled: bool = (
            os.environ.get('EMBEDDING_AUTH_DISABLED', 'false').lower() == 'true'
        )
        if self._auth_disabled:
            log.info('ColBERT client: IAM auth DISABLED (EMBEDDING_AUTH_DISABLED=true)')

        # ── Circuit-breakers INDEPENDIENTES ───────────────────────────────────
        # Texto (search, index_catalog, index_images)
        self._text_failures: int = 0
        self._text_circuit_open: bool = False

        # Visual (search_by_image, index_images, index_images_incremental)
        self._visual_failures: int = 0
        self._visual_circuit_open: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # AUTENTICACIÓN IAM — obtención y cacheo del ID token
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_id_token_sync(self) -> Optional[str]:
        """
        Obtiene el ID token firmado por Google para la SA del monolito.
        Llamado sincrónicamente desde run_in_executor para no bloquear asyncio.

        En Cloud Run:
          ADC usa el metadata server GCE (http://metadata.google.internal).
          No se necesita ninguna credencial explícita.

        En desarrollo local:
          Requiere GOOGLE_APPLICATION_CREDENTIALS o 'gcloud auth app-default login'.
          Si no está configurado, devuelve None y el cliente funciona sin auth.

        Por qué fetch_id_token y no access_token:
          Cloud Run IAM verifica ID tokens (JWT firmados por Google con audience
          específico), NO access tokens de OAuth2. Los access tokens son para
          APIs de Google (Sheets, Storage, etc.), no para Cloud Run services.
        """
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.id_token import fetch_id_token
            return fetch_id_token(Request(), self._base_url)
        except Exception as e:
            # Non-fatal: si no hay ADC, logueamos pero no crasheamos.
            # En Cloud Run, esto NUNCA debería ocurrir (metadata server siempre disponible).
            # En local sin ADC, el request al embedding-service fallará con 403,
            # que el circuit-breaker capturará como un fallo normal.
            log.warning(
                'ColBERT IAM: no se pudo obtener ID token (ADC no disponible): %s. '
                'Requests al embedding-service irán sin Authorization header.',
                e
            )
            return None

    async def _auth_headers(self) -> dict:
        """
        Devuelve el header Authorization con el ID token actual.
        Renueva el token si faltan menos de 5 minutos para que expire.

        FIX (13/05/2026): Añadido asyncio.wait_for(timeout=10s) en la
        obtención del token. Sin este timeout, _fetch_id_token_sync() puede
        bloquear el event loop por hasta 135 segundos en el PRIMER request
        a un singleton recién creado (observado en producción 13/05/2026).

        Causa probable: google-auth intenta múltiples estrategias de autenticación
        antes de llegar al metadata server de GCP, cada una con su propio timeout.
        El timeout de 10s garantiza que el primer request nunca se bloquea > 10s.

        Si el token no se obtiene en 10s, el request procede SIN Authorization.
        El embedding-service retornará 403, que el circuit-breaker captura.
        En el segundo request (token ya cacheado), funciona instantáneamente.
        """
        if self._auth_disabled:
            return {}

        # Renovar si el token expira en menos de 5 minutos (o nunca se ha obtenido)
        if time.monotonic() >= self._token_expires_at - 300:
            loop = asyncio.get_running_loop()
            try:
                # FIX: timeout de 10s para evitar el bloqueo de 135s en primer request
                token = await asyncio.wait_for(
                    loop.run_in_executor(None, self._fetch_id_token_sync),
                    timeout=10.0
                )
                if token:
                    self._cached_token    = token
                    self._token_expires_at = time.monotonic() + 3540
                    log.debug('ColBERT IAM: ID token renovado (expira en ~59min)')
                else:
                    self._cached_token    = None
                    self._token_expires_at = time.monotonic() + 60
                    return {}
            except asyncio.TimeoutError:
                # La obtención del token tarda > 10s.
                # Logueamos WARNING y continuamos sin auth para no bloquear el request.
                # El embedding-service retornará 403 → circuit-breaker lo captura.
                # En el siguiente ciclo (60s) se reintenta.
                log.warning(
                    'ColBERT IAM: token fetch timeout (>10s) — proceeding without auth. '
                    'Retry in 60s. Check GCP metadata server availability.'
                )
                self._cached_token    = None
                self._token_expires_at = time.monotonic() + 60
                return {}

        if self._cached_token:
            return {'Authorization': f'Bearer {self._cached_token}'}
        return {}

    # ─────────────────────────────────────────────────────────────────────────
    # CIRCUIT BREAKERS
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_text_failure(self, e: Exception) -> None:
        self._text_failures += 1
        log.warning('Embedding text call failed (attempt %d): %s', self._text_failures, e)
        if self._text_failures >= 3:
            self._text_circuit_open = True
            log.error('ColBERT TEXT circuit OPEN. Visual search NOT affected. Recovering in 60s.')
            asyncio.get_running_loop().call_later(60, self._reset_text_circuit)

    def _reset_text_circuit(self) -> None:
        self._text_circuit_open = False
        self._text_failures = 0
        log.info('ColBERT TEXT circuit CLOSED — text search resumed')

    def _handle_visual_failure(self, e: Exception) -> None:
        self._visual_failures += 1
        log.warning('Embedding visual call failed (attempt %d): %s', self._visual_failures, e)
        if self._visual_failures >= 3:
            self._visual_circuit_open = True
            log.error('ColBERT VISUAL circuit OPEN. Text search NOT affected. Recovering in 60s.')
            asyncio.get_running_loop().call_later(60, self._reset_visual_circuit)

    def _reset_visual_circuit(self) -> None:
        self._visual_circuit_open = False
        self._visual_failures = 0
        log.info('ColBERT VISUAL circuit CLOSED — visual search resumed')

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODOS DE NEGOCIO
    # ─────────────────────────────────────────────────────────────────────────

    async def search(self, query: str, top_k: int = 10) -> Optional[List[str]]:
        """
        Busca productos semánticamente por texto.
        Returns: lista de product IDs, o None si falla (caller usa fallback TF-IDF).
        """
        if self._text_circuit_open:
            log.debug('ColBERT TEXT circuit open — text search skipped')
            return None

        try:
            auth = await self._auth_headers()
            resp = await self._http.post(
                '/v1/embed/search',
                headers={**auth, 'Content-Type': 'application/json'},
                json={'query': query, 'top_k': top_k},
            )
            resp.raise_for_status()
            data = resp.json()
            self._text_failures = 0
            log.debug('ColBERT text search: %d results in %.1fms',
                      len(data['product_ids']), data['latency_ms'])
            return data['product_ids']
        except Exception as e:
            self._handle_text_failure(e)
            return None

    async def index_catalog(self, products: List[dict]) -> bool:
        """
        Llama al endpoint de indexación de texto (ColBERT) después de un catalog sync.
        """
        try:
            auth = await self._auth_headers()
            resp = await self._http.post(
                '/v1/embed/index',
                headers={**auth, 'Content-Type': 'application/json'},
                json={'products': products},
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            log.info('ColBERT re-indexed: %d products in %.1fms',
                     data['indexed'], data['latency_ms'])
            return True
        except Exception as e:
            log.error('ColBERT text index failed: %s', e, exc_info=True)
            return False

    async def search_by_product_id(
        self,
        product_id: str,
        top_k: int = 8,
    ) -> Optional[List[str]]:
        """
        Busca visualmente similares usando el vector FAISS existente del producto.

        Mas rapido que search_by_image (elimina fetch CDN ~200ms + encode ~435ms).
        Latencia tipica: ~50ms. Devuelve None si circuit breaker abierto,
        [] si el producto no esta en el indice FAISS todavia.
        """
        if self._visual_circuit_open:
            log.debug('ColBERT VISUAL circuit open — search_by_product_id skipped')
            return None
        try:
            auth = await self._auth_headers()
            resp = await self._http.get(
                '/v1/embed/search-by-id',
                headers=auth,
                params={'product_id': str(product_id), 'top_k': str(top_k)},
                timeout=8.0,
            )
            resp.raise_for_status()
            data = resp.json()
            self._visual_failures = 0
            log.info(
                'search_by_product_id: %d results in %.1fms for product_id=%s',
                len(data['product_ids']), data['latency_ms'], product_id,
            )
            return data['product_ids']
        except Exception as e:
            self._handle_visual_failure(e)
            return None

    async def search_by_product_id_with_text_boost(
        self,
        product_id: str,
        boost_text: str,
        alpha: float = 0.5,
        top_k: int = 8,
    ) -> Optional[List[str]]:
        """
        Igual que search_by_product_id_with_category_boost(), pero envia el
        texto de composite embedding YA RESUELTO (boost_text) en vez de una
        clave de categoria -- el embedding-service ya no necesita conocer
        taxonomia de ningun tenant (Fase 1b, 23/07/2026). El texto se
        resuelve del lado del monolito via product_taxonomy.py (unica
        fuente de verdad).

        Devuelve None si circuit breaker abierto, [] si el producto no esta
        en el indice FAISS todavia -- mismo contrato que search_by_product_id().
        """
        if self._visual_circuit_open:
            log.debug('ColBERT VISUAL circuit open — search_by_product_id_with_text_boost skipped')
            return None
        try:
            auth = await self._auth_headers()
            resp = await self._http.get(
                '/v1/embed/search-by-id-with-text-boost',
                headers=auth,
                params={
                    'product_id': str(product_id),
                    'boost_text': boost_text,
                    'alpha': str(alpha),
                    'top_k': str(top_k),
                },
                timeout=8.0,
            )
            resp.raise_for_status()
            data = resp.json()
            self._visual_failures = 0
            log.info(
                'search_by_product_id_with_text_boost: %d results in %.1fms '
                'for product_id=%s',
                len(data['product_ids']), data['latency_ms'], product_id,
            )
            return data['product_ids']
        except Exception as e:
            self._handle_visual_failure(e)
            return None

    async def search_by_product_id_with_multi_text_boost(
        self,
        product_id: str,
        boost_texts: List[str],
        alpha: float = 0.5,
        top_k: int = 8,
    ) -> Optional[List[List[str]]]:
        """
        Igual que search_by_product_id_with_text_boost(), pero batchea N
        textos de boost en UNA sola busqueda FAISS del lado del
        embedding-service, en vez de N llamadas HTTP separadas -- ver
        visual_retriever.search_by_product_id_with_multi_text_boost() para
        el razonamiento completo (Fase 1b Paso 3, 23/07/2026).

        POST con body JSON (no GET con query params) -- una lista de N
        textos no calza bien en query params.

        Devuelve None si circuit breaker abierto, [] si el producto no esta
        en el indice FAISS todavia o boost_texts esta vacio. Si tiene
        exito, devuelve una lista alineada 1:1 con boost_texts (results[i]
        corresponde a boost_texts[i]).
        """
        if self._visual_circuit_open:
            log.debug('ColBERT VISUAL circuit open — search_by_product_id_with_multi_text_boost skipped')
            return None
        if not boost_texts:
            return []
        try:
            auth = await self._auth_headers()
            resp = await self._http.post(
                '/v1/embed/search-by-id-with-multi-text-boost',
                headers=auth,
                json={
                    'product_id': str(product_id),
                    'boost_texts': boost_texts,
                    'alpha': alpha,
                    'top_k': top_k,
                },
                timeout=8.0,
            )
            resp.raise_for_status()
            data = resp.json()
            self._visual_failures = 0
            log.info(
                'search_by_product_id_with_multi_text_boost: %d/%d textos con '
                'resultados en %.1fms for product_id=%s',
                sum(1 for r in data['results'] if r), len(boost_texts),
                data['latency_ms'], product_id,
            )
            return data['results']
        except Exception as e:
            self._handle_visual_failure(e)
            return None

    async def search_by_image(
        self,
        image_bytes: bytes,
        top_k: int = 8,
    ) -> Optional[List[str]]:
        """
        Busca productos visualmente similares a la imagen proporcionada.

        Por qué NO se mezcla auth con Content-Type aquí:
          - El header Authorization se añade como dict separado via _auth_headers()
          - NO se añade Content-Type: httpx lo genera automáticamente como
            'multipart/form-data; boundary=<hash>' al detectar files=
          - Si se combinasen, el merge de dicts conservaría Content-Type de auth
            (que es {}), dejando que httpx genere el multipart correcto.
        """
        if self._visual_circuit_open:
            log.debug('ColBERT VISUAL circuit open — visual search skipped')
            return None

        try:
            auth = await self._auth_headers()
            # SIN Content-Type: httpx genera multipart/form-data automáticamente.
            # auth es {} o {'Authorization': 'Bearer <token>'} — no incluye Content-Type.
            resp = await self._http.post(
                '/v1/embed/search-image',
                headers=auth,  # solo Authorization (o {} si auth deshabilitado)
                files={'file': ('query.jpg', image_bytes, 'image/jpeg')},
                data={'top_k': str(top_k)},
                timeout=8.0,
            )
            resp.raise_for_status()
            data = resp.json()
            self._visual_failures = 0
            log.info(
                'Visual search: %d results in %.1fms (visual_index_size=%d)',
                len(data['product_ids']), data['latency_ms'],
                data.get('visual_index_size', 0)
            )
            return data['product_ids']
        except Exception as e:
            self._handle_visual_failure(e)
            return None

    async def index_images(self, products: List[dict]) -> bool:
        """
        Envía el catálogo COMPLETO al embedding-service para indexar imágenes.
        El embedding-service lanza la indexación como background task (~25 min).

        Para añadir solo productos nuevos sin reconstruir el índice completo,
        usar index_images_incremental() en su lugar.
        """
        try:
            auth = await self._auth_headers()
            resp = await self._http.post(
                '/v1/embed/index-images',
                headers={**auth, 'Content-Type': 'application/json'},
                json={'products': products, 'batch_size': 16, 'mode': 'full'},
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            log.info('Image indexation (full) accepted: %s', data.get('message', ''))
            return True
        except Exception as e:
            log.error('Image indexation request failed: %s', e, exc_info=True)
            return False

    async def index_images_incremental(self, new_products: List[dict]) -> bool:
        """
        Envía SOLO los productos nuevos al embedding-service para indexación incremental.
        El embedding-service filtra los IDs que ya están en el índice FAISS y solo
        procesa los que faltan. No reconstruye el índice completo.

        Cuándo usar:
          - Cuando se añaden productos nuevos al catálogo de Shopify
          - Cuando el catalog sync detecta nuevos image_urls
          - Para evitar los ~30 min de re-indexación completa por pocos cambios

        Limitación conocida:
          - No cubre productos ELIMINADOS (IndexFlatIP no tiene .remove())
          - No cubre productos con imagen CAMBIADA (misma ID, nueva image_url)
          - Para esos casos, usar index_images() (indexación completa)

        Args:
            new_products: lista [{id, title, image_url}] — solo los productos nuevos.
                          El embedding-service descarta los IDs ya en el índice.

        Returns:
            True si el embedding-service aceptó la petición.
            False si la petición falló o si el índice completo no existe aún
            (en ese caso, usar index_images() primero).
        """
        if self._visual_circuit_open:
            log.debug('ColBERT VISUAL circuit open — incremental index skipped')
            return False

        try:
            auth = await self._auth_headers()
            resp = await self._http.post(
                '/v1/embed/index-images',
                headers={**auth, 'Content-Type': 'application/json'},
                json={'products': new_products, 'batch_size': 16, 'mode': 'incremental'},
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get('status', '')
            if status == 'no_new_products':
                log.info(
                    'Incremental index: no new products to index '
                    '(all %d products already in index)',
                    len(new_products)
                )
            elif status == 'no_base_index':
                log.warning(
                    'Incremental index skipped: no base index exists. '
                    'Run full index first with index_images().'
                )
                return False
            else:
                log.info('Incremental image indexation accepted: %s', data.get('message', ''))
            return True
        except Exception as e:
            self._handle_visual_failure(e)
            log.error('Incremental image indexation request failed: %s', e, exc_info=True)
            return False

    async def search_outfit_by_image(
        self,
        image_bytes: bytes,
        target_categories: Optional[List[str]] = None,
        top_k_per_category: int = 3,
        alpha: float = 0.7,
    ) -> Optional[dict]:
        """
        S1 FASE 2 (13/05/2026): Búsqueda de outfit completo por imagen.

        Dado un outfit foto, devuelve product_ids para cada categoría solicitada
        usando Composite Embedding (alpha * image_embed + (1-alpha) * text_embed).

        El embedding-service aplica FashionSigLIP para:
          1. Encodear la imagen del outfit
          2. Encodear texto por categoría (dress/top/shoes/...)
          3. Combinar embeddings con factor alpha
          4. Buscar en FAISS y filtrar por category_map

        Por qué NO se mezcla auth con Content-Type:
          - Igual que search_by_image() — httpx genera multipart/form-data
            automáticamente cuando hay files=
          - auth es {} o {'Authorization': 'Bearer ...'} — sin Content-Type

        Args:
            image_bytes:          Bytes de la imagen del outfit (JPEG/PNG)
            target_categories:    Categorías a buscar. Default: dress, top, shoes, accessory
            top_k_per_category:   Máx productos por categoría en el resultado
            alpha:                Peso imagen vs texto (0.7 = 70% imagen, 30% texto)

        Returns:
            Dict con estructura:
              {
                "dress":      ["pid1", "pid2"],
                "top":        ["pid3"],
                "shoes":      ["pid4"],
                "outfit_mode": "composite_category_filtered" | "degraded_no_category_map",
                "latency_ms": 487.3,
                "category_map_size": 3028
              }
            None si el circuit-breaker visual está abierto o hay error de red.
        """
        if self._visual_circuit_open:
            log.debug('ColBERT VISUAL circuit open — outfit search skipped')
            return None

        if target_categories is None:
            target_categories = ["dress", "top", "shoes", "accessory"]

        try:
            import json as _json
            auth = await self._auth_headers()

            # SIN Content-Type: httpx genera multipart/form-data con boundary correcto.
            # Patrón idéntico a search_by_image() — ver comentario en su docstring.
            resp = await self._http.post(
                '/v1/embed/search-outfit',
                headers=auth,
                files={'file': ('outfit.jpg', image_bytes, 'image/jpeg')},
                data={
                    'categories':  _json.dumps(target_categories),
                    'top_k':       str(top_k_per_category),
                    'alpha':       str(alpha),
                },
                # Más generoso que search_by_image (8s): N categorías × encode_text
                # (~15ms cada una) + encode_image (~400ms) + N × FAISS search (<1ms)
                timeout=12.0,
            )
            resp.raise_for_status()
            data = resp.json()
            self._visual_failures = 0

            # Extraer métricas para logging sin contaminar el return
            outfit_mode  = data.get('outfit_mode', 'unknown')
            latency_ms   = data.get('latency_ms', 0)
            found_cats   = [k for k in data
                            if k not in ('outfit_mode', 'latency_ms',
                                         'visual_index_size', 'category_map_size')]
            log.info(
                'outfit_search_completed: mode=%s latency=%.0fms categories=%s cat_map=%d',
                outfit_mode, latency_ms, found_cats,
                data.get('category_map_size', 0)
            )
            return data

        except Exception as e:
            self._handle_visual_failure(e)
            log.error('Outfit search request failed: %s', e, exc_info=True)
            return None
