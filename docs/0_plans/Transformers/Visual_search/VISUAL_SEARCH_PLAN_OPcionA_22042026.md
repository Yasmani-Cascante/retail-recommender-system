# Plan de Implementación — Visual Search Opción A
## `Marqo/marqo-fashionSigLIP` + FAISS dentro del embedding-service existente

**Fecha:** 22/04/2026  
**Estimación total:** 2–3 días de trabajo efectivo  
**Riesgo:** Bajo — feature flag `VISUAL_SEARCH_ENABLED=false` por defecto, zero impact en producción hasta activación  
**Stack nuevo:** `open-clip-torch` + `faiss-cpu` + `Pillow` + `httpx` (ya en requisitos del monolito)

---

## Arquitectura del sistema resultante

```
[USUARIO SUBE FOTO — nuevo flujo]
ChatWidget → cámara icon → file input → File()
    ↓ POST /v1/mcp/visual-search (multipart/form-data)
Monolito: visual_search_router.py
    ↓ LFM2VisualSearchClient.search_by_image(bytes)
    ↓ POST /v1/embed/search-image  (bytes)
embedding-service: FashionSigLIPRetriever.search_by_image()
    → encode_image() ~300-500ms CPU
    → FAISS IndexFlatIP search ~<1ms
    ↓ product_ids[]
Monolito: fetch products from tfidf_recommender.id_index
    → market price enrichment lazy (ya existe)
    ↓ ConversationResponse (mismo formato que /v1/mcp/conversation)
Frontend: renderiza ProductCard[] igual que siempre

[INDEXACIÓN — se lanza tras deploy]
POST /v1/embed/index-images
embedding-service: FashionSigLIPRetriever.build_image_index()
    → descarga imágenes desde Shopify CDN (httpx)
    → encode_image(batch=16) ~25 min para 3062 imgs en CPU
    → FAISS IndexFlatIP.add() + guardado en /tmp/visual-index/
```

**Memoria (2GiB Cloud Run):**
- ColBERT-350M: ~700 MB  
- fashionSigLIP fp16: ~400 MB  
- FAISS index: 3062 × 768 × 4 bytes ≈ 9 MB  
- Total: **~1.11 GB de 2 GB** ✅  
- Upgrade a 4GiB recomendado para margen operativo

---

## FASE 1 — Prerrequisitos y verificación (30 min, sin código)

### Paso 1.1 — Verificar estado actual del embedding-service

```bash
# Confirmar que el servicio está corriendo
curl https://<COLBERT_SERVICE_URL>/health

# Respuesta esperada:
# {"status":"ok","model":"LFM2-ColBERT-350M","index_size":3062}
```

### Paso 1.2 — Confirmar que los productos tienen `image_url`

```python
# Ejecutar localmente contra el pickle del catálogo
import pickle
with open('data/tfidf_model.pkl', 'rb') as f:
    data = pickle.load(f)

products = data.get('product_data', [])
with_images = [p for p in products if p.get('image_url')]
print(f"Productos con image_url: {len(with_images)}/{len(products)}")
# Esperado: ~3000/3062 (algunos pueden tener image_url vacío)
```

### Paso 1.3 — Decidir upgrade de RAM

| Escenario | Acción |
|---|---|
| Si se hace upgrade a 4GiB ahora | Actualizar `deploy.sh` a `--memory 4Gi` |
| Si se mantiene en 2GiB (suficiente según cálculo) | Sin cambio, añadir nota de monitorización |

**Recomendación:** hacer el upgrade. Coste ~$10/mes, elimina riesgo de OOM durante indexación.

---

## FASE 2 — Backend: embedding-service (Día 1, ~4h)

### Paso 2.1 — Crear `visual_retriever.py` (archivo nuevo)

**Ruta:** `src/api/services/embedding-service/visual_retriever.py`

**Responsabilidades:**
- Cargar `Marqo/marqo-fashionSigLIP` usando `open_clip`
- Construir y persistir un índice FAISS `IndexFlatIP` en `/tmp/visual-index/`
- Cargar el índice desde disco si existe al arrancar (evitar re-indexación tras restart)
- Exponer `build_image_index(products)` y `search_by_image(image_bytes, top_k)`

```python
# src/api/services/embedding-service/visual_retriever.py
"""
FashionSigLIPRetriever — búsqueda visual por similitud de imagen.

Modelo:  Marqo/marqo-fashionSigLIP (203M params, ViT-B-16-SigLIP base)
Índice:  FAISS IndexFlatIP (cosine via L2-normalize + inner product)
Storage: /tmp/visual-index/  (persiste en disco mientras el contenedor vive)

Benchmarks (Marqo, Apache 2.0):
  +57% Recall@1 vs FashionCLIP 2.0 en 7 datasets de moda
  Latencia CPU: ~300-500ms por query (ViT-B encode)
  FAISS search sobre 3062 vectores: <1ms

Coexistencia con ColBERT:
  Este retriever vive en el mismo proceso que LFM2ColBERTRetriever.
  RAM estimada: ~700MB (ColBERT) + ~400MB (fashionSigLIP) ≈ 1.1GB total.
  Compatible con Cloud Run 2GiB (se recomienda 4GiB para margen).
"""

import asyncio
import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

# Directorio donde se persisten el índice FAISS y el mapa id→posición.
# /tmp es efímero en Cloud Run pero persiste mientras el contenedor está vivo
# (min-instances=1 garantiza que no se reinicia innecesariamente).
VISUAL_INDEX_PATH = Path('/tmp/visual-index')
FAISS_INDEX_FILE = VISUAL_INDEX_PATH / 'image_index.faiss'
ID_MAP_FILE = VISUAL_INDEX_PATH / 'id_map.json'


class FashionSigLIPRetriever:
    """
    Retriever de similitud visual usando marqo-fashionSigLIP + FAISS.

    Patrón de uso:
        1. Al arrancar el servicio: __init__() + warmup() + try_load_from_disk()
        2. Tras el catalog sync del monolito: build_image_index(products)
        3. En cada query visual del usuario: search_by_image(image_bytes, top_k)
    """

    def __init__(self):
        """
        Carga el modelo marqo-fashionSigLIP desde el caché de HuggingFace/OpenCLIP.
        El modelo se pre-descarga durante el docker build — no hay descarga en runtime.
        """
        import open_clip

        log.info('Loading Marqo/marqo-fashionSigLIP...')
        t0 = time.time()

        # open_clip.create_model_and_transforms devuelve (model, preprocess_train, preprocess_val).
        # Usamos preprocess_val (sin augmentations) para inferencia.
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            'hf-hub:Marqo/marqo-fashionSigLIP'
        )
        self._model.eval()  # modo inferencia: desactiva dropout, BN en modo eval

        # Dimensión del embedding de imagen (768 para ViT-B-16-SigLIP base)
        self._embed_dim: int = self._model.visual.output_dim

        # Estado del índice FAISS
        self._faiss_index = None          # faiss.IndexFlatIP — None hasta build_image_index()
        self._id_map: List[str] = []      # position i → product_id

        log.info(
            'FashionSigLIP loaded in %.1fs | embed_dim=%d',
            time.time() - t0, self._embed_dim
        )

    async def warmup(self):
        """
        Ejecuta un forward pass dummy para JIT-compilar el grafo de PyTorch.
        Evita que el primer request real pague el overhead de compilación (~2s extra).
        """
        log.info('Running FashionSigLIP warmup...')
        loop = asyncio.get_running_loop()

        def _warmup():
            # Imagen dummy: 3×224×224 tensor de ceros
            dummy = Image.new('RGB', (224, 224))
            tensor = self._preprocess(dummy).unsqueeze(0)  # [1, 3, 224, 224]
            import torch
            with torch.no_grad():
                self._model.encode_image(tensor)

        await loop.run_in_executor(None, _warmup)
        log.info('FashionSigLIP warmup complete')

    def try_load_from_disk(self) -> bool:
        """
        Intenta cargar el índice FAISS desde disco.
        Si existe (contenedor reiniciado sin re-indexar), lo carga directamente.
        Returns True si se cargó, False si no existe.

        Esto permite que un contenedor reiniciado (por OOM, deploy, etc.) sirva
        búsquedas visuales sin necesidad de una nueva llamada a /v1/embed/index-images.
        """
        if not FAISS_INDEX_FILE.exists() or not ID_MAP_FILE.exists():
            log.info(
                'No visual index on disk — call POST /v1/embed/index-images to build it'
            )
            return False

        try:
            import faiss
            log.info('Loading visual index from disk...')
            self._faiss_index = faiss.read_index(str(FAISS_INDEX_FILE))
            with open(ID_MAP_FILE) as f:
                self._id_map = json.load(f)
            log.info(
                'Visual index loaded from disk: %d products, dim=%d',
                len(self._id_map), self._embed_dim
            )
            return True
        except Exception as e:
            log.warning('Failed to load visual index from disk: %s', e)
            return False

    async def build_image_index(
        self,
        products: List[Dict],
        batch_size: int = 16,
    ) -> Tuple[int, int]:
        """
        Descarga imágenes del catálogo desde Shopify CDN y construye el índice FAISS.

        Args:
            products: Lista de dicts [{id, title, image_url, ...}]
            batch_size: Número de imágenes a encodear por batch (16 es seguro en CPU 1vCPU)

        Returns:
            Tuple (indexed_count, skipped_count)

        Diseñado para correr en background (POST /v1/embed/index-images no bloquea).
        ~25 min para 3062 productos en Cloud Run 1vCPU.
        """
        import faiss
        import httpx
        import torch

        loop = asyncio.get_running_loop()
        VISUAL_INDEX_PATH.mkdir(parents=True, exist_ok=True)

        # Filtrar productos que tienen image_url
        products_with_images = [
            p for p in products
            if p.get('image_url') and str(p.get('image_url', '')).startswith('http')
        ]
        total = len(products_with_images)
        skipped = len(products) - total

        log.info(
            '[visual-index] Starting indexation: %d products with image_url '
            '(%d skipped, no URL)',
            total, skipped
        )

        all_embeddings: List[np.ndarray] = []
        all_ids: List[str] = []
        indexed_count = 0
        failed_count = 0

        # Procesar en batches para controlar memoria y permitir logging de progreso
        for batch_start in range(0, total, batch_size):
            batch = products_with_images[batch_start: batch_start + batch_size]

            # Descargar imágenes del batch de forma concurrente (async I/O)
            images_in_batch: List[Tuple[str, Image.Image]] = []
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                for p in batch:
                    product_id = str(p.get('id', ''))
                    image_url = p['image_url']
                    try:
                        resp = await client.get(image_url)
                        resp.raise_for_status()
                        img = Image.open(io.BytesIO(resp.content)).convert('RGB')
                        images_in_batch.append((product_id, img))
                    except Exception as e:
                        log.debug(
                            '[visual-index] Failed to download %s: %s',
                            image_url, e
                        )
                        failed_count += 1

            if not images_in_batch:
                continue

            # Encodear en thread pool (bloquea CPU, no queremos bloquear event loop)
            def _encode_batch(imgs_with_ids: List[Tuple[str, Image.Image]]):
                """
                Encodea un batch de imágenes PIL y devuelve embeddings L2-normalized.
                L2-normalize es necesario para que IndexFlatIP compute cosine similarity.
                """
                import torch, faiss as _faiss

                ids = [pid for pid, _ in imgs_with_ids]
                tensors = torch.stack([
                    self._preprocess(img) for _, img in imgs_with_ids
                ])  # [B, 3, 224, 224]

                with torch.no_grad():
                    embeds = self._model.encode_image(tensors)  # [B, 768]
                    # L2-normalize: convierte inner product en cosine similarity
                    embeds = embeds / embeds.norm(dim=-1, keepdim=True)

                return ids, embeds.float().cpu().numpy()

            batch_ids, batch_embeds = await loop.run_in_executor(
                None, _encode_batch, images_in_batch
            )
            all_embeddings.append(batch_embeds)
            all_ids.extend(batch_ids)
            indexed_count += len(batch_ids)

            # Log de progreso cada 5 batches
            if (batch_start // batch_size) % 5 == 0:
                log.info(
                    '[visual-index] Progress: %d/%d products (%.0f%%)',
                    indexed_count, total, 100 * indexed_count / total
                )

        if not all_embeddings:
            log.error('[visual-index] No embeddings generated — check image URLs')
            return 0, skipped + failed_count

        # Construir índice FAISS
        def _build_faiss(embeddings: np.ndarray, ids: List[str]):
            """
            IndexFlatIP: búsqueda exacta por inner product.
            Con embeddings L2-normalized, inner product == cosine similarity.
            Para 3062 productos, la búsqueda exhaustiva es trivial (<1ms).
            """
            import faiss as _faiss

            dim = embeddings.shape[1]
            index = _faiss.IndexFlatIP(dim)  # exact cosine similarity
            index.add(embeddings)            # adds all vectors at once
            return index, ids

        all_matrix = np.vstack(all_embeddings).astype(np.float32)
        faiss_index, id_map = await loop.run_in_executor(
            None, _build_faiss, all_matrix, all_ids
        )

        # Persistir a disco para sobrevivir reinicios del contenedor
        import faiss
        faiss.write_index(faiss_index, str(FAISS_INDEX_FILE))
        with open(ID_MAP_FILE, 'w') as f:
            json.dump(id_map, f)

        # Actualizar estado en memoria
        self._faiss_index = faiss_index
        self._id_map = id_map

        log.info(
            '[visual-index] Done: %d indexed, %d skipped (no URL), %d failed (download)',
            indexed_count, skipped, failed_count
        )
        return indexed_count, skipped + failed_count

    async def search_by_image(
        self,
        image_bytes: bytes,
        top_k: int = 8,
    ) -> List[str]:
        """
        Encodea la imagen del usuario y busca los productos más similares.

        Args:
            image_bytes: bytes de la imagen (JPEG/PNG/WebP)
            top_k: número de product_ids a devolver

        Returns:
            Lista de product_ids ordenados por similitud descendente.
            Lista vacía si el índice no está construido.

        Latencia warm (CPU 1vCPU): ~300-500ms total (encode + <1ms FAISS)
        """
        if self._faiss_index is None:
            log.warning(
                'Visual index not built — returning empty. '
                'Call POST /v1/embed/index-images first.'
            )
            return []

        loop = asyncio.get_running_loop()

        def _encode_and_search(img_bytes: bytes) -> List[str]:
            """
            Encode + FAISS search en thread pool.
            Los dos pasos van juntos para minimizar el tiempo total:
            no tiene sentido liberar el event loop entre encode y search
            porque el search (<1ms) es despreciable.
            """
            import torch, faiss as _faiss

            # Decodificar imagen desde bytes
            img = Image.open(io.BytesIO(img_bytes)).convert('RGB')

            # Encodear con fashionSigLIP
            tensor = self._preprocess(img).unsqueeze(0)  # [1, 3, 224, 224]
            with torch.no_grad():
                embed = self._model.encode_image(tensor)  # [1, 768]
                embed = embed / embed.norm(dim=-1, keepdim=True)  # L2-normalize

            query = embed.float().cpu().numpy()  # [1, 768]

            # FAISS search: encuentra los top_k vectores más similares
            distances, indices = self._faiss_index.search(query, top_k)
            # distances[0]: scores de similitud coseno en [0, 1]
            # indices[0]: posiciones en el índice FAISS

            return [
                self._id_map[idx]
                for idx in indices[0]
                if 0 <= idx < len(self._id_map)
            ]

        return await loop.run_in_executor(None, _encode_and_search, image_bytes)

    def index_size(self) -> int:
        """Número de productos en el índice visual. 0 si no está construido."""
        return len(self._id_map)
```

---

### Paso 2.2 — Modificar `main.py` (añadir retriever visual + endpoints)

**Cambios:**
1. Importar y cargar `FashionSigLIPRetriever` en el lifespan (después de ColBERT warmup)
2. Intentar cargar índice desde disco al startup
3. Añadir `POST /v1/embed/index-images`
4. Añadir `POST /v1/embed/search-image`
5. Actualizar `/health` para incluir `visual_index_size`

```python
# En el lifespan — después de ColBERT warmup:

from visual_retriever import FashionSigLIPRetriever
visual_retriever = FashionSigLIPRetriever()
await visual_retriever.warmup()
visual_retriever.try_load_from_disk()  # No-op si no existe el índice
log.info('Visual retriever ready (index_size=%d)', visual_retriever.index_size())

# ── Nuevos Pydantic models ────────────────────────────────────────
class IndexImagesRequest(BaseModel):
    products: List[dict]   # [{id, title, image_url, ...}]
    batch_size: int = 16   # configurable para ajustar velocidad vs CPU

class SearchImageResponse(BaseModel):
    product_ids: List[str]
    latency_ms: float
    index_size: int

# ── GET /health — actualizar ─────────────────────────────────────
@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'models': {
            'colbert': 'LFM2-ColBERT-350M',
            'visual': 'Marqo/marqo-fashionSigLIP',
        },
        'index_size': colbert_retriever.index_size() if colbert_retriever else 0,
        'visual_index_size': visual_retriever.index_size() if visual_retriever else 0,
    }

# ── POST /v1/embed/index-images ───────────────────────────────────
@app.post('/v1/embed/index-images')
async def build_image_index(req: IndexImagesRequest, background_tasks: BackgroundTasks):
    """
    Lanza la indexación de imágenes como background task.
    No bloquea: devuelve inmediatamente con 202 Accepted.
    ~25 minutos para 3062 productos en CPU 1vCPU.

    Llamar desde el monolito tras catalog sync o al hacer deploy inicial.
    """
    if not visual_retriever:
        raise HTTPException(503, 'Visual retriever not ready')

    async def _run_indexation():
        t0 = time.time()
        indexed, skipped = await visual_retriever.build_image_index(
            req.products,
            batch_size=req.batch_size,
        )
        log.info(
            '[visual-index] Indexation complete: indexed=%d skipped=%d elapsed=%.0fs',
            indexed, skipped, time.time() - t0
        )

    background_tasks.add_task(_run_indexation)
    return {
        'status': 'accepted',
        'message': f'Indexing {len(req.products)} products in background',
        'products_submitted': len(req.products),
    }

# ── POST /v1/embed/search-image ───────────────────────────────────
@app.post('/v1/embed/search-image', response_model=SearchImageResponse)
async def search_by_image(
    file: UploadFile = File(...),
    top_k: int = Form(default=8),
):
    """
    Busca productos similares a la imagen subida por el usuario.
    Acepta JPEG, PNG, WebP. Tamaño máximo recomendado: 5MB.
    Latencia warm: ~300-500ms en CPU.
    """
    if not visual_retriever:
        raise HTTPException(503, 'Visual retriever not ready')
    if visual_retriever.index_size() == 0:
        raise HTTPException(503, 'Visual index not built. Call /v1/embed/index-images first.')

    # Validar Content-Type básico
    if file.content_type and not file.content_type.startswith('image/'):
        raise HTTPException(400, f'Expected image file, got {file.content_type}')

    t0 = time.time()
    image_bytes = await file.read()

    if not image_bytes:
        raise HTTPException(400, 'Empty file')

    product_ids = await visual_retriever.search_by_image(image_bytes, top_k=top_k)

    return SearchImageResponse(
        product_ids=product_ids,
        latency_ms=round((time.time() - t0) * 1000, 1),
        index_size=visual_retriever.index_size(),
    )
```

**Imports adicionales necesarios en `main.py`:**
```python
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
```

---

### Paso 2.3 — Actualizar `requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.8.2
pylate>=1.2.0
transformers>=4.55.0
# torch se instala separado en Dockerfile (versión CPU-only)

# ── Visual search (Opción A) ──────────────────────────────────────
open-clip-torch>=2.23.0    # para cargar Marqo/marqo-fashionSigLIP
faiss-cpu>=1.7.4           # ANN index exacto (IndexFlatIP)
Pillow>=10.0.0             # decodificación de imágenes
httpx>=0.27.0              # descarga de imágenes del CDN Shopify
numpy>=1.24.0              # operaciones de vectores
```

---

### Paso 2.4 — Actualizar `Dockerfile`

Añadir bloque de pre-descarga del modelo fashionSigLIP y la variable de entorno de timeout de HF:

```dockerfile
# ── DESPUÉS del bloque de pre-descarga de ColBERT, añadir: ────────

# Pre-descargar marqo-fashionSigLIP.
# El modelo (~400MB) se bake en la imagen junto con ColBERT (~350MB).
# open_clip descarga desde HuggingFace Hub en el primer uso si no está en caché.
RUN python << 'EOF'
import open_clip
import os

os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '300')
os.environ.setdefault('HF_HUB_ETAG_TIMEOUT', '60')

print('Pre-downloading Marqo/marqo-fashionSigLIP...')
model, _, preprocess = open_clip.create_model_and_transforms(
    'hf-hub:Marqo/marqo-fashionSigLIP'
)
print(f'FashionSigLIP pre-downloaded: embed_dim={model.visual.output_dim}')
EOF
```

**Impacto en el tamaño de imagen Docker:**
- Antes: ~900MB (torch CPU + ColBERT)
- Después: ~1.3GB (+ fashionSigLIP ~400MB)
- Build time: +3–5 min (un solo modelo adicional a descargar)

---

### Paso 2.5 — Actualizar `deploy.sh`

```bash
# Cambiar --memory 2Gi → --memory 4Gi
# Cambiar --min-instances 0 → --min-instances 1  (ya establecido para ColBERT)

gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --region $REGION \
  --project $PROJECT \
  --memory 4Gi \           # ← upgrade (era 2Gi)
  --cpu 2 \                # ← upgrade para indexación más rápida (era 1)
  --min-instances 1 \      # ← mantener siempre activo
  --max-instances 3 \
  --timeout 300 \          # ← 5 min (era 60s, insuficiente para indexar)
  --no-allow-unauthenticated \
  --ingress internal
```

**Coste del upgrade:** ~$20–30/mes adicionales (4GiB/2vCPU vs 2GiB/1vCPU con min=1).  
**Justificación:** la indexación de 3062 imágenes necesita >1 vCPU para ser viable en tiempo razonable, y 4GiB da margen de seguridad con los dos modelos cargados.

---

## FASE 3 — Backend: monolito (Día 1–2, ~3h)

### Paso 3.1 — Actualizar `colbert_client.py`

Añadir dos métodos al cliente existente:
- `search_by_image(image_bytes, top_k)` — busca por imagen
- `index_images(products)` — desencadena indexación de imágenes

```python
# En src/api/services/colbert_client.py
# Añadir al final de la clase LFM2ColBERTClient:

    async def search_by_image(
        self,
        image_bytes: bytes,
        top_k: int = 8
    ) -> Optional[List[str]]:
        """
        Busca productos visualmente similares a la imagen dada.

        Args:
            image_bytes: bytes de la imagen (JPEG / PNG / WebP)
            top_k: número máximo de resultados

        Returns:
            Lista de product_ids ordenados por similitud, o None si falla.
            None → el caller devuelve error 503 al usuario (sin silencio).

        Nota: el circuit-breaker de self._circuit_open cubre TAMBIÉN esta
        ruta, reutilizando la lógica existente. Si search() o index_catalog()
        fallan 3 veces seguidas, search_by_image también quedará bloqueado
        durante 60s.
        """
        if self._circuit_open:
            log.debug('ColBERT circuit open — visual search skipped')
            return None

        try:
            resp = await self._http.post(
                '/v1/embed/search-image',
                content=image_bytes,
                headers={'Content-Type': 'application/octet-stream'},
                params={'top_k': top_k},
                timeout=8.0,    # 500ms encode + margen generoso para CPU variable
            )
            resp.raise_for_status()
            data = resp.json()
            self._consecutive_failures = 0

            log.info(
                'Visual search: %d results in %.1fms (index_size=%d)',
                len(data['product_ids']), data['latency_ms'], data.get('index_size', 0)
            )
            return data['product_ids']

        except Exception as e:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self._circuit_open = True
                log.error('ColBERT circuit OPEN (visual search failure): %s', e)
                asyncio.get_running_loop().call_later(
                    60, setattr, self, '_circuit_open', False
                )
            log.warning(
                'Visual search failed (attempt %d): %s',
                self._consecutive_failures, e
            )
            return None

    async def index_images(self, products: List[dict]) -> bool:
        """
        Envía el catálogo al embedding-service para indexar imágenes.
        Es una operación de background en el embedding-service (~25 min).
        Devuelve True si el service aceptó la petición, False si falló.

        Llamar desde:
        - visual_search_router._trigger_image_indexation() al hacer deploy
        - ShopifyKBSyncService después de sincronizar productos (si se implementa)
        """
        try:
            resp = await self._http.post(
                '/v1/embed/index-images',
                json={'products': products, 'batch_size': 16},
                timeout=30.0,   # Solo espera el ACK (202), no la indexación completa
            )
            resp.raise_for_status()
            data = resp.json()
            log.info(
                'Image indexation accepted: %s',
                data.get('message', 'no message')
            )
            return True
        except Exception as e:
            log.error('Image indexation request failed: %s', e, exc_info=True)
            return False
```

---

### Paso 3.2 — Crear `visual_search_router.py` (archivo nuevo)

**Ruta:** `src/api/routers/visual_search_router.py`

Este router expone el endpoint que el widget llama. Maneja la imagen, obtiene product_ids del embedding-service, resuelve los productos desde el catálogo en memoria, y aplica market pricing.

```python
# src/api/routers/visual_search_router.py
"""
Visual Search Router — Búsqueda de productos por imagen.

Endpoint principal: POST /v1/mcp/visual-search
  - Recibe imagen como multipart/form-data
  - Llama al embedding-service → obtiene product_ids por similitud visual
  - Resuelve productos completos desde tfidf_recommender.id_index (ya en RAM)
  - Aplica market pricing lazy (mismo mecanismo que /v1/mcp/conversation)
  - Retorna lista de ProductRecommendation en el mismo formato que el chat

Feature flag: VISUAL_SEARCH_ENABLED=false (default)
  Cuando false: devuelve 503 con mensaje descriptivo.
  Cuando true: procesa normalmente.

Dependencias del monolito:
  - tfidf_recommender (global, ya cargado en startup)
  - colbert_client / LFM2ColBERTClient (vía ServiceFactory o global)
  - _enrich_recommendations_lazy (ya existe en mcp_personalization_engine)
"""

import os
import time
import logging

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from typing import List, Optional

from src.api.security_auth import get_api_key

logger = structlog.get_logger(__name__)
router = APIRouter()

# ── Feature flag ───────────────────────────────────────────────────────────────
# Leer directamente de os.environ (no lru_cache) — lección aprendida del 21/03.
def _visual_search_enabled() -> bool:
    return os.environ.get('VISUAL_SEARCH_ENABLED', 'false').lower() == 'true'


# ── Response model ─────────────────────────────────────────────────────────────
class VisualSearchResponse(BaseModel):
    """
    Misma forma que ConversationResponse.recommendations para que el frontend
    pueda reutilizar el mismo código de renderizado (ProductCard, etc.).
    """
    recommendations: List[dict]
    query_type: str = 'visual_search'
    total_found: int
    latency_ms: float
    visual_index_size: int = 0


# ── Endpoint ────────────────────────────────────────────────────────────────────
@router.post('/v1/mcp/visual-search', response_model=VisualSearchResponse)
async def visual_search(
    file: UploadFile = File(..., description='Imagen del producto (JPEG/PNG/WebP, max 5MB)'),
    market_id: str = Form(default='ES', description='Mercado para precios'),
    top_k: int = Form(default=8, description='Número máximo de resultados'),
    api_key: str = Depends(get_api_key),
):
    """
    Busca productos visualmente similares a la imagen subida.

    El usuario sube una foto de una prenda → el sistema devuelve los productos
    del catálogo más parecidos visualmente.

    Flujo:
        1. Validar imagen y feature flag
        2. Leer bytes de la imagen
        3. Llamar embedding-service → product_ids (fashionSigLIP + FAISS)
        4. Resolver producto completo desde tfidf_recommender.id_index
        5. Sanitizar y devolver en formato ProductRecommendation
    """
    t_start = time.time()

    # ── 1. Feature flag ────────────────────────────────────────────────────────
    if not _visual_search_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                'error': 'visual_search_disabled',
                'message': 'Visual search is not enabled. Set VISUAL_SEARCH_ENABLED=true.',
            }
        )

    # ── 2. Validar imagen ──────────────────────────────────────────────────────
    if file.content_type and not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail=f'Expected image file, got: {file.content_type}'
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail='Empty file')

    MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
    if len(image_bytes) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f'Image too large ({len(image_bytes)//1024}KB). Max 5MB.'
        )

    logger.info(
        'visual_search_request',
        market_id=market_id,
        image_size_kb=round(len(image_bytes) / 1024, 1),
        top_k=top_k,
        content_type=file.content_type,
    )

    # ── 3. Llamar embedding-service ────────────────────────────────────────────
    # Importar el cliente ColBERT (ya inicializado en hybrid_recommender)
    # Usamos la misma instancia global para no crear clientes redundantes.
    try:
        from src.api.services.colbert_client import LFM2ColBERTClient
        colbert_client = LFM2ColBERTClient()  # Usa COLBERT_SERVICE_URL del env
    except ValueError as e:
        logger.error('colbert_client_init_failed', error=str(e))
        raise HTTPException(
            status_code=503,
            detail='Visual search service unavailable (COLBERT_SERVICE_URL not set)'
        )

    product_ids = await colbert_client.search_by_image(image_bytes, top_k=top_k)

    if product_ids is None:
        # search_by_image devuelve None cuando el circuit está abierto o hay error
        logger.warning('visual_search_embedding_service_unavailable')
        raise HTTPException(
            status_code=503,
            detail='Visual search temporarily unavailable. Please try again.'
        )

    if not product_ids:
        # Índice no construido o sin resultados (no es un error)
        logger.warning('visual_search_no_results', market_id=market_id)
        return VisualSearchResponse(
            recommendations=[],
            total_found=0,
            latency_ms=round((time.time() - t_start) * 1000, 1),
        )

    # ── 4. Resolver productos desde el catálogo en RAM ─────────────────────────
    # tfidf_recommender es el global del monolito — siempre cargado en startup.
    # id_index es un dict {product_id_str: product_dict} construido en load_recommender().
    from src.api.main_unified_redis import tfidf_recommender  # noqa: PLC0415

    if not tfidf_recommender or not getattr(tfidf_recommender, 'id_index', None):
        logger.error('visual_search_catalog_not_loaded')
        raise HTTPException(status_code=503, detail='Product catalog not loaded')

    resolved = []
    for pid in product_ids:
        product = tfidf_recommender.id_index.get(str(pid))
        if product:
            resolved.append({
                **product,
                'score': 1.0 - (len(resolved) * 0.05),  # score decreciente por posición
                'source': 'visual_search',
            })

    # ── 5. Sanitizar con el mismo helper del mcp_router ───────────────────────
    from src.api.routers.mcp_router import sanitize_rec_for_frontend
    sanitized = [sanitize_rec_for_frontend(r) for r in resolved]

    elapsed_ms = round((time.time() - t_start) * 1000, 1)

    logger.info(
        'visual_search_complete',
        market_id=market_id,
        found=len(sanitized),
        latency_ms=elapsed_ms,
    )

    return VisualSearchResponse(
        recommendations=sanitized,
        total_found=len(sanitized),
        latency_ms=elapsed_ms,
    )


# ── Endpoint auxiliar: disparar indexación desde el exterior ───────────────────
@router.post('/v1/mcp/visual-search/index', include_in_schema=False)
async def trigger_visual_indexation(api_key: str = Depends(get_api_key)):
    """
    Endpoint de operaciones: desencadena la indexación de imágenes del catálogo.
    Solo disponible con API key. No expuesto en la documentación Swagger.
    
    Llamar manualmente después del primer deploy o cuando el índice está vacío.
    La indexación corre en background en el embedding-service (~25 min).
    """
    from src.api.main_unified_redis import tfidf_recommender
    from src.api.services.colbert_client import LFM2ColBERTClient

    if not tfidf_recommender or not getattr(tfidf_recommender, 'product_data', None):
        raise HTTPException(503, 'Product catalog not loaded')

    try:
        client = LFM2ColBERTClient()
    except ValueError as e:
        raise HTTPException(503, str(e))

    # Enviar el catálogo al embedding-service
    # Solo enviamos los campos necesarios para la indexación visual
    products_for_indexation = [
        {
            'id': str(p.get('id', '')),
            'title': p.get('title', ''),
            'image_url': p.get('image_url', ''),
        }
        for p in tfidf_recommender.product_data
        if p.get('image_url')
    ]

    accepted = await client.index_images(products_for_indexation)
    if not accepted:
        raise HTTPException(503, 'Failed to trigger image indexation')

    return {
        'status': 'accepted',
        'products_submitted': len(products_for_indexation),
        'message': 'Image indexation started in background (~25 min for 3062 products)',
    }
```

---

### Paso 3.3 — Registrar el router en `main_unified_redis.py`

**Cambios mínimos en 3 lugares del archivo:**

**1. Imports (cerca del bloque de imports de routers):**
```python
# Añadir después de los imports de routers existentes:
try:
    from src.api.routers.visual_search_router import router as visual_search_router
    VISUAL_SEARCH_AVAILABLE = True
    logger.info('✅ Visual search router loaded')
except ImportError as e:
    VISUAL_SEARCH_AVAILABLE = False
    logger.warning('⚠️ Visual search router not available: %s', e)
```

**2. Registro del router (en la sección de `app.include_router()`):**
```python
# Después de los include_router() existentes:
if VISUAL_SEARCH_AVAILABLE:
    app.include_router(visual_search_router)
    logger.info('✅ Visual search router registered')
```

**3. Variable de entorno en el startup log (opcional, para debugging):**
```python
# En el bloque de logging de startup:
_visual_enabled = os.environ.get('VISUAL_SEARCH_ENABLED', 'false')
logger.info('🔍 VISUAL_SEARCH_ENABLED=%s', _visual_enabled)
```

**4. Añadir la env var en Cloud Run (con flag OFF por defecto):**
```bash
gcloud run services update retail-recommender \
  --region us-central1 \
  --project retail-recommendations-449216 \
  --set-env-vars VISUAL_SEARCH_ENABLED=false
```

---

## FASE 4 — Frontend (Día 2, ~3h)

### Paso 4.1 — Actualizar `api.ts`

Añadir el método `searchByImage` a la clase `ConversationAPI`:

```typescript
// En src/frontend/src/services/api.ts
// Añadir dentro de la clase ConversationAPI, después de sendMessage():

  /**
   * searchByImage — búsqueda visual por similitud de imagen.
   *
   * Envía la imagen al backend → embedding-service → FAISS → product_ids.
   * Devuelve las recomendaciones en el mismo formato que sendMessage().
   *
   * @param imageFile - File del input[type=file] del usuario
   * @param marketId  - Mercado para precios (default: config.marketId)
   * @param topK      - Número máximo de resultados (default: 8)
   */
  async searchByImage(
    imageFile: File,
    marketId?: string,
    topK: number = 8
  ): Promise<ProductRecommendation[]> {
    const formData = new FormData();
    formData.append('file', imageFile);
    formData.append('market_id', marketId ?? this.config.marketId ?? 'ES');
    formData.append('top_k', String(topK));

    const response = await fetch(`${this.config.apiUrl}/v1/mcp/visual-search`, {
      method: 'POST',
      headers: {
        // NO poner Content-Type con multipart — fetch lo añade automáticamente con boundary
        'X-API-Key': this.config.apiKey,
      },
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const detail = (errorData as Record<string, unknown>).detail;
      const errorMsg =
        typeof detail === 'object' && detail !== null
          ? (detail as Record<string, unknown>).message as string
          : String(detail ?? `HTTP ${response.status}`);
      throw new Error(errorMsg);
    }

    const data = (await response.json()) as {
      recommendations: unknown[];
      total_found: number;
      latency_ms: number;
    };

    return (data.recommendations ?? []).map(r =>
      normalizeRecommendation(r as Record<string, unknown>)
    );
  }
```

---

### Paso 4.2 — Actualizar `MessageInput.tsx`

Añadir el botón de cámara con un `<input type="file">` oculto.

**Props nuevas:**
```typescript
interface MessageInputProps {
  onSendMessage: (message: string) => void;
  onImageUpload?: (file: File) => void;   // ← nueva prop
  disabled?: boolean;
  placeholder?: string;
  visualSearchEnabled?: boolean;          // ← nueva prop (default false)
}
```

**Cambios en el JSX:**
```tsx
// Dentro del <div className={styles.inputRow}> — antes del botón enviar:

{visualSearchEnabled && (
  <>
    {/* Input file oculto — se activa con el botón cámara */}
    <input
      ref={fileInputRef}
      type="file"
      accept="image/jpeg,image/png,image/webp"
      style={{ display: 'none' }}
      onChange={handleFileChange}
      aria-hidden="true"
    />
    <button
      type="button"
      className={`${styles.iconBtn} ${styles.cameraBtn}`}
      onClick={() => fileInputRef.current?.click()}
      disabled={disabled}
      title="Buscar por imagen"
      aria-label="Buscar productos por imagen"
    >
      {/* Icono cámara inline SVG — sin dependencia de librería */}
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" strokeWidth="2" strokeLinecap="round"
           strokeLinejoin="round">
        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
        <circle cx="12" cy="13" r="4"/>
      </svg>
    </button>
  </>
)}
```

**Handler para el file input:**
```typescript
const fileInputRef = useRef<HTMLInputElement>(null);

const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0];
  if (!file) return;

  // Resetear el input para permitir subir la misma imagen dos veces
  e.target.value = '';

  // Validar tamaño en el cliente (5MB)
  if (file.size > 5 * 1024 * 1024) {
    // TODO: mostrar error al usuario (pendiente manejo de errores en ChatWidget)
    console.warn('Image too large (>5MB)');
    return;
  }

  onImageUpload?.(file);
};
```

---

### Paso 4.3 — Actualizar `MessageInput.module.css`

Añadir estilos para el botón de cámara (mínimo, coherente con el botón de enviar):

```css
/* Botón icono genérico (compartido: cámara, futura voz, etc.) */
.iconBtn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #999;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: color 0.15s, background 0.15s;
}

.iconBtn:hover:not(:disabled) {
  color: #444;
  background: #f0f0f0;
}

.iconBtn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Cámara — sin estilo adicional por ahora */
.cameraBtn {
  /* reservado para diferenciación futura */
}
```

---

### Paso 4.4 — Actualizar `ChatWidget.tsx`

**Cambios necesarios:**
1. Importar `useState` para el estado de carga visual
2. Añadir handler `handleImageUpload`
3. Pasar props nuevas a `MessageInput`

```typescript
// En src/frontend/src/components/ChatWidget.tsx

// 1. Añadir estado de carga visual (junto a los estados existentes):
const [isVisualSearching, setIsVisualSearching] = useState(false);

// 2. Handler para imagen subida:
const handleImageUpload = useCallback(async (file: File) => {
  if (isVisualSearching || conversationState.isLoading) return;

  setIsVisualSearching(true);

  // Mostrar mensaje del usuario con preview de la imagen
  const imagePreviewUrl = URL.createObjectURL(file);
  const userMessage: Message = {
    id: `msg_${Date.now()}`,
    type: 'user',
    content: '',                    // sin texto — el chip muestra la imagen
    timestamp: Date.now(),
    suggestionChip: {
      label: 'Buscar por imagen',
      image_url: imagePreviewUrl,
    },
  };
  addMessage(userMessage);          // addMessage ya existe en ChatWidget

  try {
    const recommendations = await api.searchByImage(
      file,
      config.marketId,
      8,
    );

    const assistantMessage: Message = {
      id: `msg_${Date.now()}_reply`,
      type: 'assistant',
      content: recommendations.length > 0
        ? `Encontré ${recommendations.length} productos similares:`
        : 'No encontré productos similares. Intenta con otra imagen.',
      timestamp: Date.now(),
      recommendations: recommendations.length > 0 ? recommendations : undefined,
    };
    addMessage(assistantMessage);

  } catch (error) {
    const errorMessage: Message = {
      id: `msg_${Date.now()}_err`,
      type: 'error',
      content: error instanceof Error
        ? error.message
        : 'Error en la búsqueda visual. Inténtalo de nuevo.',
      timestamp: Date.now(),
    };
    addMessage(errorMessage);
  } finally {
    setIsVisualSearching(false);
    URL.revokeObjectURL(imagePreviewUrl);  // liberar memoria
  }
}, [isVisualSearching, conversationState.isLoading, config.marketId, api]);

// 3. Pasar props a MessageInput (en el JSX):
<MessageInput
  onSendMessage={handleSendMessage}
  onImageUpload={handleImageUpload}            // ← nueva prop
  disabled={conversationState.isLoading || isVisualSearching}
  placeholder={getPlaceholder(uiLang)}
  visualSearchEnabled={true}                   // ← true cuando VISUAL_SEARCH_ENABLED=true en backend
/>
```

**Nota sobre `visualSearchEnabled`:** Para que el botón de cámara solo aparezca cuando el backend tiene el servicio activo, se puede hacer un fetch al `/health` del backend al inicializar el widget y comprobar si `visual_index_size > 0`. Alternativamente, mostrar el botón siempre y manejar el 503 con un mensaje de usuario. **La segunda opción es más simple en la primera iteración.**

---

## FASE 5 — Build, deploy y activación (Día 2–3)

### Secuencia de deploy — el orden importa

```
Paso 5.1: Deploy embedding-service (imagen nueva con fashionSigLIP)
    ↓
Paso 5.2: Disparar indexación de imágenes vía endpoint auxiliar
    ↓  (~25 min en background, no bloquea)
Paso 5.3: Build frontend (npm run build)
    ↓
Paso 5.4: Deploy monolito (con VISUAL_SEARCH_ENABLED=false)
    ↓
Paso 5.5: Smoke tests
    ↓
Paso 5.6: Activar flag (VISUAL_SEARCH_ENABLED=true)
    ↓
Paso 5.7: Deploy Shopify snippet actualizado
```

### Paso 5.1 — Deploy embedding-service

```bash
cd src/api/services/embedding-service

# Build local para verificar que la imagen compila correctamente:
docker build -t retail-embedding-service:test .

# Si el build es exitoso (verifica logs de pre-descarga):
./deploy.sh
```

**Verificar que arrancó correctamente:**
```bash
# Obtener URL del servicio
SERVICE_URL=$(gcloud run services describe retail-embedding-service \
  --region us-central1 \
  --project retail-recommendations-449216 \
  --format='value(status.url)')

# Health check
curl "$SERVICE_URL/health"
# Esperado: {"status":"ok","models":{...},"index_size":3062,"visual_index_size":0}
# visual_index_size=0 es correcto — el índice se construye en el paso siguiente
```

### Paso 5.2 — Disparar indexación de imágenes

```bash
# Trigger manual tras deploy (no bloquea — devuelve 202 Accepted)
curl -X POST "$SERVICE_URL/v1/embed/index-images" \
  -H "Content-Type: application/json" \
  -d '{"products": [...]}' # el catálogo completo con image_url

# Alternativa: usar el endpoint auxiliar del monolito (más cómodo)
# (disponible una vez desplegado el monolito con el nuevo router)
curl -X POST "https://retail-recommender-lzf2y6pspa-uc.a.run.app/v1/mcp/visual-search/index" \
  -H "X-API-Key: <api_key>"

# Monitorizar progreso en GCP Logs:
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=retail-embedding-service AND textPayload:visual-index" \
  --project retail-recommendations-449216 \
  --limit 20 \
  --format='value(textPayload)'

# Log de finalización esperado:
# [visual-index] Done: 3020 indexed, 42 skipped (no URL), 0 failed (download)
```

### Paso 5.3 — Build frontend

```bash
cd src/frontend
npm run build
# El UMD bundle se genera en dist/
```

### Paso 5.4 — Deploy monolito

```bash
gcloud run deploy retail-recommender \
  --source . \
  --region us-central1 \
  --project retail-recommendations-449216

# Añadir flag desactivado:
gcloud run services update retail-recommender \
  --region us-central1 \
  --set-env-vars VISUAL_SEARCH_ENABLED=false
```

### Paso 5.5 — Smoke tests

```bash
# 1. Health del monolito — verificar que el nuevo router está registrado
curl https://retail-recommender-lzf2y6pspa-uc.a.run.app/health

# 2. Visual search con flag OFF (debe dar 503)
curl -X POST https://retail-recommender-lzf2y6pspa-uc.a.run.app/v1/mcp/visual-search \
  -H "X-API-Key: <api_key>" \
  -F "file=@test_image.jpg" \
  -F "market_id=ES"
# Esperado: {"detail": {"error": "visual_search_disabled", ...}}

# 3. Conversación normal sigue funcionando (no regresión)
curl -X POST https://retail-recommender-lzf2y6pspa-uc.a.run.app/v1/mcp/conversation \
  -H "X-API-Key: <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"query": "busco vestidos", "language": "es", "market_id": "ES"}'

# 4. Verificar índice visual ready en embedding-service
curl "$SERVICE_URL/health"
# Verificar: visual_index_size > 0
```

### Paso 5.6 — Activar el flag

**Solo cuando el índice visual esté construido (visual_index_size > 0):**

```bash
gcloud run services update retail-recommender \
  --region us-central1 \
  --project retail-recommendations-449216 \
  --set-env-vars VISUAL_SEARCH_ENABLED=true

# Verificar activación en logs:
# gcloud logging read ... | grep VISUAL_SEARCH_ENABLED
```

**Smoke test con flag activo:**
```bash
curl -X POST https://retail-recommender-lzf2y6pspa-uc.a.run.app/v1/mcp/visual-search \
  -H "X-API-Key: <api_key>" \
  -F "file=@vestido_test.jpg" \
  -F "market_id=ES" \
  -F "top_k=8"
# Esperado: {"recommendations": [...], "total_found": 8, "latency_ms": 450}
```

### Paso 5.7 — Deploy Shopify

Subir el nuevo bundle JS a los assets del tema y actualizar `theme.liquid` si es necesario.

---

## FASE 6 — Validación offline (antes de activar en producción)

### Script de self-similarity test

```python
# validate_visual_search.Fisuipy
# Ejecutar localmente con acceso al embedding-service

import httpx, asyncio, pickle, random, time

SERVICE_URL = "https://<COLBERT_SERVICE_URL>"
CATALOG_PATH = "data/tfidf_model.pkl"

async def validate_visual_search():
    with open(CATALOG_PATH, 'rb') as f:
        data = pickle.load(f)

    products = [p for p in data['product_data'] if p.get('image_url')]
    # Muestreo: 100 productos aleatorios para la validación offline
    sample = random.sample(products, min(100, len(products)))

    recall_1 = recall_5 = recall_10 = 0
    same_category_count = 0
    latencies = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, product in enumerate(sample):
            # Descargar la imagen del producto
            try:
                img_resp = await client.get(product['image_url'])
                img_resp.raise_for_status()
            except Exception as e:
                print(f"Skip {product['id']}: {e}")
                continue

            # Buscar por la imagen del producto en el índice
            t0 = time.time()
            resp = await client.post(
                f"{SERVICE_URL}/v1/embed/search-image",
                content=img_resp.content,
                headers={'Content-Type': 'image/jpeg'},
                params={'top_k': 10},
            )
            latency_ms = (time.time() - t0) * 1000
            latencies.append(latency_ms)

            result_ids = resp.json()['product_ids']
            pid = str(product['id'])

            if result_ids and result_ids[0] == pid:
                recall_1 += 1
            if pid in result_ids[:5]:
                recall_5 += 1
            if pid in result_ids[:10]:
                recall_10 += 1

            # Precisión intra-categoría (de los top-10, ¿cuántos son misma categoría?)
            product_cat = product.get('product_type', '')
            same_cat = sum(
                1 for rid in result_ids[:10]
                for p2 in products
                if str(p2['id']) == rid and p2.get('product_type') == product_cat
            )
            same_category_count += same_cat / max(len(result_ids[:10]), 1)

            if (i + 1) % 10 == 0:
                print(f"Progress: {i+1}/{len(sample)}")

    n = len(latencies)
    print(f"\n── Resultados sobre {n} productos ──")
    print(f"Recall@1:  {recall_1/n:.1%}  (umbral: >85%)")
    print(f"Recall@5:  {recall_5/n:.1%}  (umbral: >95%)")
    print(f"Recall@10: {recall_10/n:.1%}")
    print(f"Precisión intra-categoría (avg top-10): {same_category_count/n:.1%}  (umbral: >70%)")
    print(f"Latencia p50: {sorted(latencies)[n//2]:.0f}ms  (umbral: <500ms)")
    print(f"Latencia p95: {sorted(latencies)[int(n*0.95)]:.0f}ms  (umbral: <800ms)")

if __name__ == '__main__':
    asyncio.run(validate_visual_search())
```

**Criterio de pase:**
- Recall@1 > 85% → el modelo reconoce sus propias imágenes con fiabilidad
- Recall@5 > 95% → robustez ante variaciones de iluminación/encuadre
- Precisión intra-categoría > 70% → los resultados son del mismo tipo de prenda
- p50 < 500ms → latencia aceptable para búsqueda no-conversacional
- Si algún criterio falla: investigar antes de activar flag

---

## FASE 7 — Variables de entorno completas

| Variable | Valor default | Cuándo cambiar |
|---|---|---|
| `VISUAL_SEARCH_ENABLED` | `false` | `true` tras validación exitosa |
| `COLBERT_SERVICE_URL` | (ya configurado) | sin cambio |
| `LFM_COLBERT_ENABLED` | `false` | sin cambio |

**Rollback en 30 segundos:**
```bash
gcloud run services update retail-recommender \
  --set-env-vars VISUAL_SEARCH_ENABLED=false
```

---

## Resumen ejecutivo

| Fase | Qué hace | Tiempo est. | Archivos |
|---|---|---|---|
| 1 | Prerrequisitos y verificación | 30 min | — |
| 2 | embedding-service: visual_retriever + endpoints | 4h | `visual_retriever.py` (nuevo), `main.py`, `requirements.txt`, `Dockerfile`, `deploy.sh` |
| 3 | Monolito: client + router + registro | 3h | `colbert_client.py`, `visual_search_router.py` (nuevo), `main_unified_redis.py` |
| 4 | Frontend: botón cámara + handler + API | 3h | `api.ts`, `MessageInput.tsx`, `MessageInput.module.css`, `ChatWidget.tsx` |
| 5 | Build, deploy, smoke tests, activación | 2h | `deploy.sh` |
| 6 | Validación offline | 1h | `validate_visual_search.py` (nuevo) |

**Total: 2–3 días de trabajo efectivo**  
**Costo infraestructura adicional:** $20–30/mes (upgrade 4GiB/2vCPU del embedding-service)  
**Modelo adicional:** $0 (Apache 2.0, open weights)  
**Impacto en sistema existente durante implementación:** cero (VISUAL_SEARCH_ENABLED=false por defecto)

---

*Plan elaborado el 22/04/2026. Sistema base: Retail Recommender v2.1.0.*
