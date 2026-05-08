"""
visual_retriever.py — FashionSigLIP + FAISS visual search retriever.

Cambios relevantes:
  28/04/2026 — descargas paralelas con asyncio.gather + Semaphore.
  29/04/2026 — guard de jobs duplicados (_indexation_running).
               _download_one movida a nivel de MÓDULO (fuera de la clase y
               del for loop) para eliminar el closure bug que causaba que los
               jobs concurrentes compartieran el mismo Semaphore.
  29/04/2026 — GCS persistence: el índice FAISS se sube a GCS tras cada
               indexación y se descarga en startup si /tmp está vacío.
               Esto elimina el re-indexado de 30 min en cada deploy/restart.
  30/04/2026 — FIX OOM: pre-resize a 224×224 en _download_one.
               Las fotos Shopify (2000×2500px = 15MB decoded) causaban
               ~4107MB de RAM a los 51 batches (OOM a 27% del catálogo).
               Pre-resize reduce PIL memory de 240MB/batch → 2.4MB/batch.
               Añadido gc.collect() cada 10 batches para devolver memoria
               del allocator PyTorch CPU al OS entre ciclos.
  01/05/2026 — Batch size adaptativo: el batch_size inicial se ajusta
               automáticamente tras el primer batch según la velocidad de
               descarga observada. Evita 429 del CDN con imágenes grandes
               y aprovecha capacidad extra con imágenes pequeñas.
  01/05/2026 — Indexación incremental: build_image_index_incremental()
               añade solo productos nuevos al índice FAISS existente sin
               reconstruirlo. IndexFlatIP.add() es append-only.
"""
import asyncio
import gc
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

# ── Persistencia local (efímera — survives intra-container restarts) ──────────
VISUAL_INDEX_PATH = Path('/tmp/visual-index')
FAISS_INDEX_FILE  = VISUAL_INDEX_PATH / 'image_index.faiss'
ID_MAP_FILE       = VISUAL_INDEX_PATH / 'id_map.json'

# ── Persistencia en GCS (duradera — survives deploys y reinicios) ─────────────
GCS_BUCKET = os.environ.get('VISUAL_INDEX_BUCKET', '')
GCS_PREFIX = 'visual-index'

# ── Batch size adaptativo — límites ───────────────────────────────────────────
# El batch_size controla cuántas descargas de imagen van en paralelo.
# El CDN de Shopify puede throttlear con muchas conexiones simultáneas.
# Estos límites garantizan que el ajuste adaptativo sea seguro.
BATCH_SIZE_MIN = 4   # Mínimo: protege contra 429 con imágenes muy grandes
BATCH_SIZE_MAX = 32  # Máximo: límite de conexiones simultáneas al CDN

# Objetivos de velocidad para el ajuste adaptativo.
# Si el batch tarda <FAST_TARGET_S/imagen, se puede subir el batch_size.
# Si el batch tarda >SLOW_TARGET_S/imagen, se baja para evitar timeouts/429.
BATCH_FAST_TARGET_S = 1.0  # < 1s/imagen → aumentar batch_size
BATCH_SLOW_TARGET_S = 3.0  # > 3s/imagen → reducir batch_size


# ─────────────────────────────────────────────────────────────────────────────
# _download_one — función a nivel de MÓDULO (no inside class, no inside loop)
# ─────────────────────────────────────────────────────────────────────────────

async def _download_one(
    client,
    product_id: str,
    image_url: str,
    sem: asyncio.Semaphore,
) -> Optional[Tuple[str, "Image.Image"]]:
    """
    Descarga una imagen del CDN de Shopify y la pre-redimensiona a 224×224.

    PRE-RESIZE A 224×224: reduce el uso de RAM de ~15MB/imagen a ~0.15MB.
    El semáforo se pasa como argumento explícito para eliminar el closure bug
    (ver historial de cambios en el docstring del módulo).
    """
    async with sem:
        try:
            resp = await client.get(image_url)
            resp.raise_for_status()
            img_full = Image.open(io.BytesIO(resp.content)).convert('RGB')
            img_small = img_full.resize((224, 224), Image.Resampling.LANCZOS)
            del img_full
            return (product_id, img_small)
        except Exception as e:
            log.debug('[visual-index] Failed to download %s: %s', image_url, e)
            return None


class FashionSigLIPRetriever:
    """
    Retriever de similitud visual con marqo-fashionSigLIP + FAISS.

    Ciclo de vida:
        1. __init__() + warmup()               — startup
        2. try_load_from_disk()                — startup, carga desde /tmp o GCS
        3. build_image_index(products)         — primera indexación o re-indexación completa
        4. build_image_index_incremental(new)  — añadir solo productos nuevos (sin reconstruir)
        5. search_by_image(image_bytes)        — cada query visual del usuario

    Persistencia del índice FAISS:
        - Nivel 1: /tmp/visual-index/  — rápido, mismo container
        - Nivel 2: GCS                 — durable, survives deploys y reinicios
    """

    def __init__(self):
        import open_clip
        import torch

        log.info('Loading Marqo/marqo-fashionSigLIP...')
        t0 = time.time()
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            'hf-hub:Marqo/marqo-fashionSigLIP'
        )
        self._model.eval()
        with torch.no_grad():
            dummy = torch.zeros(1, 3, 224, 224)
            self._embed_dim: int = self._model.encode_image(dummy).shape[-1]

        self._faiss_index = None
        self._id_map: List[str] = []
        self._indexation_running: bool = False

        log.info('FashionSigLIP loaded in %.1fs | embed_dim=%d', time.time() - t0, self._embed_dim)

    async def warmup(self):
        log.info('Running FashionSigLIP warmup...')
        loop = asyncio.get_running_loop()
        def _warmup():
            import torch
            dummy = Image.new('RGB', (224, 224))
            tensor = self._preprocess(dummy).unsqueeze(0)
            with torch.no_grad():
                self._model.encode_image(tensor)
        await loop.run_in_executor(None, _warmup)
        log.info('FashionSigLIP warmup complete')

    # ─────────────────────────────────────────────────────────────────────────
    # GCS PERSISTENCE
    # ─────────────────────────────────────────────────────────────────────────

    def _upload_to_gcs(self) -> bool:
        if not GCS_BUCKET:
            log.info('[visual-index] VISUAL_INDEX_BUCKET no configurado — omitiendo upload GCS')
            return False
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET)
            for local_path, gcs_path in [
                (FAISS_INDEX_FILE, f'{GCS_PREFIX}/image_index.faiss'),
                (ID_MAP_FILE,      f'{GCS_PREFIX}/id_map.json'),
            ]:
                blob = bucket.blob(gcs_path)
                blob.upload_from_filename(str(local_path))
                log.info('[visual-index] GCS upload: %s → gs://%s/%s (%.1fMB)',
                         local_path.name, GCS_BUCKET, gcs_path,
                         local_path.stat().st_size / 1024 / 1024)
            log.info('[visual-index] GCS upload complete → gs://%s/%s/', GCS_BUCKET, GCS_PREFIX)
            return True
        except Exception as e:
            log.warning('[visual-index] GCS upload failed (non-fatal): %s', e, exc_info=True)
            return False

    def _download_from_gcs(self) -> bool:
        if not GCS_BUCKET:
            return False
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET)
            files = [
                (f'{GCS_PREFIX}/image_index.faiss', FAISS_INDEX_FILE),
                (f'{GCS_PREFIX}/id_map.json',       ID_MAP_FILE),
            ]
            for gcs_path, _ in files:
                if not bucket.blob(gcs_path).exists():
                    log.info('[visual-index] GCS: archivo no encontrado: gs://%s/%s',
                             GCS_BUCKET, gcs_path)
                    return False
            VISUAL_INDEX_PATH.mkdir(parents=True, exist_ok=True)
            for gcs_path, local_path in files:
                bucket.blob(gcs_path).download_to_filename(str(local_path))
                log.info('[visual-index] GCS download: %s (%.1fMB)',
                         local_path.name, local_path.stat().st_size / 1024 / 1024)
            log.info('[visual-index] GCS download complete')
            return True
        except Exception as e:
            log.warning('[visual-index] GCS download failed: %s', e, exc_info=True)
            return False

    def _load_local_index(self) -> bool:
        try:
            import faiss
            self._faiss_index = faiss.read_index(str(FAISS_INDEX_FILE))
            with open(ID_MAP_FILE) as f:
                self._id_map = json.load(f)
            log.info('[visual-index] Loaded from disk: %d products, dim=%d',
                     len(self._id_map), self._embed_dim)
            return True
        except Exception as e:
            log.warning('[visual-index] Failed to load local index: %s', e)
            self._faiss_index = None
            self._id_map = []
            return False

    def _save_to_disk(self) -> None:
        """Persiste el índice actual (faiss + id_map) en /tmp."""
        import faiss
        VISUAL_INDEX_PATH.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._faiss_index, str(FAISS_INDEX_FILE))
        with open(ID_MAP_FILE, 'w') as f:
            json.dump(self._id_map, f)
        log.info('[visual-index] Saved to local disk: /tmp/visual-index/')

    # ─────────────────────────────────────────────────────────────────────────
    # STARTUP
    # ─────────────────────────────────────────────────────────────────────────

    def try_load_from_disk(self) -> bool:
        if FAISS_INDEX_FILE.exists() and ID_MAP_FILE.exists():
            log.info('[visual-index] Found index on local disk — loading...')
            if self._load_local_index():
                return True
        if GCS_BUCKET:
            log.info('[visual-index] Local disk empty — trying GCS (bucket=%s)...', GCS_BUCKET)
            if self._download_from_gcs():
                if self._load_local_index():
                    return True
        log.info(
            '[visual-index] No hay índice disponible — '
            'llama POST /v1/embed/index-images para construirlo (~30 min)'
        )
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # FULL INDEXATION — reconstruye el índice completo
    # ─────────────────────────────────────────────────────────────────────────

    async def build_image_index(
        self,
        products: List[Dict],
        batch_size: int = 16,
    ) -> Tuple[int, int]:
        """
        Descarga imágenes del catálogo y construye el índice FAISS desde cero.
        Usa batch size adaptativo para ajustar la concurrencia según la velocidad
        observada en el primer batch.

        Returns: (indexed_count, skipped_or_failed_count)
        """
        if self._indexation_running:
            log.warning('[visual-index] Duplicate request ignored — job already running.')
            return 0, 0
        self._indexation_running = True
        log.info('[visual-index] Lock acquired — starting full indexation job')
        try:
            return await self._run_indexation(products, batch_size)
        finally:
            self._indexation_running = False
            log.info('[visual-index] Lock released')

    async def _run_indexation(
        self,
        products: List[Dict],
        batch_size: int,
    ) -> Tuple[int, int]:
        """
        Implementación interna de la indexación completa.

        ── BATCH SIZE ADAPTATIVO ─────────────────────────────────────────────
        El batch_size inicial (default 16) se ajusta tras el primer batch
        en función de la velocidad de descarga observada:

          Lento (>3s/imagen):  batch_size = max(4, batch_size // 2)
            → Reduce conexiones simultáneas para evitar 429 del CDN.
            → Típico con imágenes de alta resolución (3-11MB).

          Rápido (<1s/imagen): batch_size = min(32, batch_size * 2)
            → Aumenta concurrencia para aprovechar ancho de banda.
            → Típico con miniaturas optimizadas (<200KB).

          Normal (1-3s/imagen): sin cambio.

        El ajuste se hace UNA SOLA VEZ (tras el batch 0) para evitar
        oscilaciones. La velocidad del CDN de Shopify es estable entre
        batches del mismo job.
        """
        import faiss
        import httpx

        loop = asyncio.get_running_loop()
        VISUAL_INDEX_PATH.mkdir(parents=True, exist_ok=True)

        products_with_images = [
            p for p in products
            if p.get('image_url') and str(p.get('image_url', '')).startswith('http')
        ]
        total   = len(products_with_images)
        skipped = len(products) - total

        log.info('[visual-index] Starting: %d products with image_url (%d skipped, no URL)',
                 total, skipped)

        all_embeddings: List[np.ndarray] = []
        all_ids: List[str] = []
        indexed_count = 0
        failed_count  = 0
        current_batch_size = batch_size  # puede cambiar tras el primer batch

        for batch_start in range(0, total, current_batch_size):
            batch     = products_with_images[batch_start: batch_start + current_batch_size]
            batch_num = batch_start // current_batch_size

            sem = asyncio.Semaphore(current_batch_size)
            t_batch_start = time.monotonic()

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=60.0),
                limits=httpx.Limits(max_connections=current_batch_size),
            ) as client:
                tasks = [
                    _download_one(client, str(p.get('id', '')), p['image_url'], sem)
                    for p in batch
                ]
                results = await asyncio.gather(*tasks)

            # ── BATCH SIZE ADAPTATIVO — ajustar SOLO tras el primer batch ─────
            # Por qué solo el primer batch:
            #   La velocidad del CDN es estable durante un job. Medir el primer
            #   batch es suficiente para calibrar. Ajustes continuos añadirían
            #   complejidad sin beneficio real.
            if batch_num == 0 and len(batch) > 0:
                t_batch_elapsed = time.monotonic() - t_batch_start
                successful_downloads = sum(1 for r in results if r is not None)
                if successful_downloads > 0:
                    avg_s_per_img = t_batch_elapsed / successful_downloads
                    old_batch_size = current_batch_size
                    if avg_s_per_img > BATCH_SLOW_TARGET_S:
                        # Imágenes lentas — reducir concurrencia para evitar 429
                        current_batch_size = max(BATCH_SIZE_MIN, current_batch_size // 2)
                    elif avg_s_per_img < BATCH_FAST_TARGET_S:
                        # Imágenes rápidas — aumentar concurrencia para aprovechar BW
                        current_batch_size = min(BATCH_SIZE_MAX, current_batch_size * 2)
                    if current_batch_size != old_batch_size:
                        log.info(
                            '[visual-index] Adaptive batch: %.2fs/img → '
                            'batch_size %d → %d (range [%d, %d])',
                            avg_s_per_img, old_batch_size, current_batch_size,
                            BATCH_SIZE_MIN, BATCH_SIZE_MAX
                        )
                    else:
                        log.info(
                            '[visual-index] Adaptive batch: %.2fs/img → '
                            'batch_size=%d (sin cambio)',
                            avg_s_per_img, current_batch_size
                        )

            failed_count    += sum(1 for r in results if r is None)
            images_in_batch  = [r for r in results if r is not None]
            del results

            if not images_in_batch:
                del images_in_batch
                continue

            def _encode_batch(imgs_with_ids):
                import torch as _torch
                ids     = [pid for pid, _ in imgs_with_ids]
                tensors = _torch.stack([self._preprocess(img) for _, img in imgs_with_ids])
                with _torch.no_grad():
                    embeds = self._model.encode_image(tensors)
                    embeds = embeds / embeds.norm(dim=-1, keepdim=True)
                return ids, embeds.float().cpu().numpy()

            batch_ids, batch_embeds = await loop.run_in_executor(None, _encode_batch, images_in_batch)
            del images_in_batch

            all_embeddings.append(batch_embeds)
            all_ids.extend(batch_ids)
            indexed_count += len(batch_ids)

            if batch_num % 5 == 0:
                log.info('[visual-index] Progress: %d/%d products (%.0f%%)',
                         indexed_count, total, 100 * indexed_count / max(total, 1))

            if batch_num > 0 and batch_num % 10 == 0:
                gc.collect()

        if not all_embeddings:
            log.error('[visual-index] No embeddings generated — check image URLs')
            return 0, skipped + failed_count

        def _build_faiss(embeddings, ids):
            import faiss as _faiss
            index = _faiss.IndexFlatIP(embeddings.shape[1])
            index.add(embeddings)
            return index, ids

        all_matrix  = np.vstack(all_embeddings).astype(np.float32)
        faiss_index, id_map = await loop.run_in_executor(
            None, _build_faiss, all_matrix, all_ids
        )

        self._faiss_index = faiss_index
        self._id_map      = id_map

        self._save_to_disk()
        await loop.run_in_executor(None, self._upload_to_gcs)

        log.info('[visual-index] Done: %d indexed, %d skipped (no URL), %d failed (download)',
                 indexed_count, skipped, failed_count)
        return indexed_count, skipped + failed_count

    # ─────────────────────────────────────────────────────────────────────────
    # INCREMENTAL INDEXATION — añade solo productos nuevos
    # ─────────────────────────────────────────────────────────────────────────

    async def build_image_index_incremental(
        self,
        new_products: List[Dict],
        batch_size: int = 16,
    ) -> Tuple[str, int, int]:
        """
        Añade SOLO productos nuevos al índice FAISS existente sin reconstruirlo.

        Usa faiss.IndexFlatIP.add() que es append-only: añade vectores al final
        sin modificar los existentes. Esto permite indexar 10 productos nuevos
        en ~5s en lugar de los ~30min de una re-indexación completa.

        Limitaciones importantes (documentadas en DCT):
          1. Solo cubre productos NUEVOS (IDs no en self._id_map).
          2. Productos ELIMINADOS: el índice los mantiene (IndexFlatIP no tiene
             .remove()). Para limpiar eliminations, usar build_image_index().
          3. Productos con imagen CAMBIADA (misma ID, nueva image_url): el
             índice conserva el embedding antiguo. Para actualizar embeddings
             de productos existentes, usar build_image_index().

        Args:
            new_products: lista [{id, title, image_url, ...}]
                          El método filtra internamente los IDs ya presentes.
            batch_size:   imágenes por batch de descarga.

        Returns:
            Tuple (status, indexed_count, skipped_count) donde status es:
              'no_base_index'   — no hay índice previo, usar build_image_index()
              'no_new_products' — todos los IDs ya estaban en el índice
              'completed'       — indexación incremental completada
              'error'           — error durante la indexación
        """
        if self._indexation_running:
            log.warning('[visual-index] Duplicate request — incremental job skipped.')
            return 'already_running', 0, 0

        # Prerequisito: debe haber un índice base
        if self._faiss_index is None or not self._id_map:
            log.warning(
                '[visual-index] Incremental index requested but no base index exists. '
                'Run build_image_index() first.'
            )
            return 'no_base_index', 0, 0

        # Calcular qué productos son realmente nuevos
        existing_ids = set(self._id_map)
        actually_new = [
            p for p in new_products
            if str(p.get('id', '')) not in existing_ids
            and p.get('image_url')
            and str(p.get('image_url', '')).startswith('http')
        ]

        if not actually_new:
            already_present = len([
                p for p in new_products
                if str(p.get('id', '')) in existing_ids
            ])
            log.info(
                '[visual-index] Incremental: no new products '
                '(%d submitted, %d already in index)',
                len(new_products), already_present
            )
            return 'no_new_products', 0, already_present

        log.info(
            '[visual-index] Incremental: %d new products to index '
            '(%d already in index, %d submitted total)',
            len(actually_new),
            len(new_products) - len(actually_new),
            len(new_products)
        )

        self._indexation_running = True
        log.info('[visual-index] Lock acquired — starting incremental indexation')
        try:
            indexed, failed = await self._run_incremental_indexation(actually_new, batch_size)
            return 'completed', indexed, failed
        except Exception as e:
            log.error('[visual-index] Incremental indexation failed: %s', e, exc_info=True)
            return 'error', 0, len(actually_new)
        finally:
            self._indexation_running = False
            log.info('[visual-index] Lock released')

    async def _run_incremental_indexation(
        self,
        new_products: List[Dict],
        batch_size: int,
    ) -> Tuple[int, int]:
        """
        Descarga imágenes de los productos nuevos, genera embeddings y los
        añade al índice FAISS existente con .add().

        Por qué IndexFlatIP.add() es seguro para añadir:
          IndexFlatIP almacena vectores en un array contiguo en RAM. .add()
          extiende ese array con los nuevos vectores. Los vectores existentes
          no se modifican. La correspondencia entre posición de vector y
          product_id se mantiene añadiendo los nuevos IDs al final de self._id_map.
          La búsqueda con .search() sigue siendo correcta porque FAISS busca
          en todo el array (existentes + nuevos) y devuelve índices de posición
          que se traducen correctamente con el id_map actualizado.
        """
        import httpx

        loop = asyncio.get_running_loop()
        total = len(new_products)
        indexed_count = 0
        failed_count  = 0
        new_embeddings: List[np.ndarray] = []
        new_ids: List[str] = []

        for batch_start in range(0, total, batch_size):
            batch     = new_products[batch_start: batch_start + batch_size]
            batch_num = batch_start // batch_size
            sem       = asyncio.Semaphore(batch_size)

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=60.0),
                limits=httpx.Limits(max_connections=batch_size),
            ) as client:
                results = await asyncio.gather(*[
                    _download_one(client, str(p.get('id', '')), p['image_url'], sem)
                    for p in batch
                ])

            failed_count    += sum(1 for r in results if r is None)
            images_in_batch  = [r for r in results if r is not None]
            del results

            if not images_in_batch:
                del images_in_batch
                continue

            def _encode_batch(imgs_with_ids):
                import torch as _torch
                ids     = [pid for pid, _ in imgs_with_ids]
                tensors = _torch.stack([self._preprocess(img) for _, img in imgs_with_ids])
                with _torch.no_grad():
                    embeds = self._model.encode_image(tensors)
                    embeds = embeds / embeds.norm(dim=-1, keepdim=True)
                return ids, embeds.float().cpu().numpy()

            batch_ids, batch_embeds = await loop.run_in_executor(None, _encode_batch, images_in_batch)
            del images_in_batch

            new_embeddings.append(batch_embeds)
            new_ids.extend(batch_ids)
            indexed_count += len(batch_ids)

            log.info('[visual-index] Incremental progress: %d/%d new products', indexed_count, total)

            if batch_num > 0 and batch_num % 10 == 0:
                gc.collect()

        if not new_embeddings:
            log.warning('[visual-index] Incremental: no embeddings generated')
            return 0, failed_count

        # Añadir nuevos vectores al índice FAISS existente
        new_matrix = np.vstack(new_embeddings).astype(np.float32)

        def _add_to_faiss(matrix, ids):
            # NOTA: self._faiss_index se modifica en el thread pool.
            # Esto es seguro porque:
            #   1. self._indexation_running=True previene accesos concurrentes
            #   2. search_by_image() se ejecuta en otro run_in_executor y también
            #      lee self._faiss_index — pero FAISS IndexFlatIP es thread-safe
            #      para operaciones de lectura concurrentes con escritura si la
            #      escritura es atómica (add() con un solo batch).
            self._faiss_index.add(matrix)
            self._id_map.extend(ids)

        await loop.run_in_executor(None, _add_to_faiss, new_matrix, new_ids)

        # Persistir estado actualizado
        self._save_to_disk()
        await loop.run_in_executor(None, self._upload_to_gcs)

        log.info(
            '[visual-index] Incremental done: +%d products indexed, %d failed. '
            'Total index size: %d',
            indexed_count, failed_count, len(self._id_map)
        )
        return indexed_count, failed_count

    # ─────────────────────────────────────────────────────────────────────────
    # SEARCH
    # ─────────────────────────────────────────────────────────────────────────

    async def search_by_image(self, image_bytes: bytes, top_k: int = 8) -> List[str]:
        """
        Encodea la imagen del usuario y busca los K productos más similares.
        Latencia warm (CPU 2vCPU): ~300-500ms (encode ViT-B-16) + <1ms (FAISS).
        """
        if self._faiss_index is None:
            log.warning('Visual index not built — returning empty.')
            return []
        loop = asyncio.get_running_loop()
        def _encode_and_search(img_bytes):
            import torch as _torch
            img    = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            tensor = self._preprocess(img).unsqueeze(0)
            with _torch.no_grad():
                embed = self._model.encode_image(tensor)
                embed = embed / embed.norm(dim=-1, keepdim=True)
            query = embed.float().cpu().numpy()
            _, indices = self._faiss_index.search(query, top_k)
            return [
                self._id_map[idx]
                for idx in indices[0]
                if 0 <= idx < len(self._id_map)
            ]
        return await loop.run_in_executor(None, _encode_and_search, image_bytes)

    # ─────────────────────────────────────────────────────────────────────────
    # ESTADO (usados en /health)
    # ─────────────────────────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        return self._faiss_index is not None and len(self._id_map) > 0

    def index_size(self) -> int:
        return len(self._id_map)

    def is_indexing(self) -> bool:
        return self._indexation_running
