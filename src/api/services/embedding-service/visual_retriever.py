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
  12/05/2026 — S1 Outfit Search: category_map paralelo al id_map para
               filtrado por categoría de prenda. Tokenizador FashionSigLIP
               para búsqueda guiada por texto. search_outfit_by_image()
               usando Composite Embedding por categoría.
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

# ── S1: Persistencia del category_map ─────────────────────────────────────────
# Paralelo a id_map: almacena la categoría de outfit de cada vector FAISS.
# Permite filtrar resultados por tipo de prenda en search_outfit_by_image().
# Backward compatible: si el archivo no existe (índice antiguo), _category_map = []
# y search_outfit_by_image() opera en modo degradado sin filtro de categoría.
CATEGORY_MAP_FILE = VISUAL_INDEX_PATH / 'category_map.json'

# ── Persistencia en GCS (duradera — survives deploys y reinicios) ─────────────
GCS_BUCKET        = os.environ.get('VISUAL_INDEX_BUCKET', '')
GCS_PREFIX        = 'visual-index'
GCS_CATEGORY_MAP  = f'{GCS_PREFIX}/category_map.json'

# ── Batch size adaptativo — límites ───────────────────────────────────────────
BATCH_SIZE_MIN     = 4    # Mínimo: protege contra 429 con imágenes muy grandes
BATCH_SIZE_MAX     = 32   # Máximo: límite de conexiones simultáneas al CDN
BATCH_FAST_TARGET_S = 1.0  # < 1s/imagen → aumentar batch_size
BATCH_SLOW_TARGET_S = 3.0  # > 3s/imagen → reducir batch_size

# ── S1: Mapeo product_type Shopify → categoría de outfit ──────────────────────
#
# Construido a partir de las colecciones reales de ai-shoppings.myshopify.com
# (verificado en Shopify Admin > Products > Collections, 12/05/2026).
#
# Categorías de outfit:
#   dress     → vestidos (todas las longitudes, incluyendo novias)
#   enterito  → monos/enteritos (jumpsuits)
#   top       → tops y bralettes sueltos
#   bottom    → faldas y pantalones sueltos
#   conjunto  → sets coordinados de 2 piezas
#   shoes     → calzado
#   outerwear → capas, kimonos, tapados
#   accessory → complementos (brazaletes, aromas, alas de novia, etc.)
#   lingerie  → lencería, reductores, calzones (excluida del outfit search por defecto)
#
# Los product_type desconocidos reciben "" (cadena vacía) → no aparecen en
# búsquedas de outfit, pero sí en búsquedas visuales normales.
SHOPIFY_TYPE_TO_OUTFIT_CATEGORY: Dict[str, str] = {
    # ── Vestidos ──────────────────────────────────────────────────────────────
    "VESTIDOS CORTOS":            "dress",
    "VESTIDOS LARGOS":            "dress",
    "VESTIDOS MIDIS":             "dress",
    # ── Novias (vestidos de novia — también categoría dress) ──────────────────
    "NOVIAS CORTOS":              "dress",
    "NOVIAS LARGOS":              "dress",
    "NOVIAS MIDIS":               "dress",
    # ── Enteritos / Jumpsuits ─────────────────────────────────────────────────
    "ENTERITOS CORTOS":           "enterito",
    "ENTERITOS LARGOS":           "enterito",
    "NOVIAS ENTERITOS":           "enterito",
    # ── Tops ─────────────────────────────────────────────────────────────────
    "TOPS":                       "top",
    "BRALETTES":                  "top",
    # ── Bottoms ───────────────────────────────────────────────────────────────
    "FALDAS":                     "bottom",
    "PANTALONES":                 "bottom",
    # ── Conjuntos de 2 piezas ─────────────────────────────────────────────────
    "CONJUNTOS FALDAS":           "conjunto",
    "CONJUNTOS PANTALONES":       "conjunto",
    "NOVIAS CONJUNTOS FALDAS":    "conjunto",
    "NOVIAS CONJUNTOS PANTALONES":"conjunto",
    # ── Calzado ───────────────────────────────────────────────────────────────
    "ZAPATOS":                    "shoes",
    # ── Outerwear ─────────────────────────────────────────────────────────────
    "CAPAS BORDADAS":             "outerwear",
    "CAPAS GASA":                 "outerwear",
    "KIMONOS":                    "outerwear",
    # ── Accesorios ────────────────────────────────────────────────────────────
    # NOTA: Datos reales usan plural ('BRAZALETES') y formas alternativas.
    # Mapeamos ambas variantes para robustez ante cambios de nomenclatura.
    "BRAZALETE":                  "accessory",   # singular (1 producto)
    "BRAZALETES":                 "accessory",   # plural   (36 productos) ← FIX typo
    "ALAS DE NOVIA":              "accessory",
    "AROMAS":                     "accessory",
    "AROS":                       "accessory",   # pendientes/aretes (524 productos)
    "COLLARES":                   "accessory",   # necklaces         (22 productos)
    "CINTURONES":                 "accessory",   # belts             (22 productos)
    "TOCADOS":                    "accessory",   # headpieces        (41 productos)
    "CARTERAS":                   "bag",          # handbags          (72 productos)
    "CLUTCH":                     "bag",          # clutch bags       (1 producto)
    # ── Outerwear adicional ───────────────────────────────────────────────────
    "CHAQUETAS":                  "outerwear",   # jackets           (6 productos)
    # ── Bottoms adicionales ───────────────────────────────────────────────────
    "LEGGINGS":                   "bottom",      # leggings          (6 productos)
    # ── Lencería (excluida del outfit search por defecto) ─────────────────────
    "LENCERIA":                   "lingerie",
    "LENCERÍA":                   "lingerie",
    "REDUCTORES":                 "lingerie",
    "CALZONES":                   "lingerie",
    "PIJAMAS":                    "lingerie",    # pajamas           (7 productos)
    # ── Ignorados (sin categoría de outfit significativa) ─────────────────────
    # SNOWBOARD (14), PACK (4), '' (9) → product_type vacío o irrelevante
}

# ── S1: Prompts de texto por categoría para FashionSigLIP ─────────────────────
#
# FashionSigLIP fue entrenado con GCL (Generalised Contrastive Learning) sobre
# categorías, estilos y palabras clave de moda en múltiples idiomas.
# Combinar español + inglés mejora el recall en este catálogo hispanohablante.
#
# Estos prompts se usan en search_outfit_by_image() para crear el Composite
# Embedding: query = normalize(α × image_embed + (1-α) × text_embed(prompt)).
# El prompt "empuja" el query hacia la categoría deseada dentro del espacio
# vectorial compartido de FashionSigLIP.
CATEGORY_TEXT_PROMPTS: Dict[str, str] = {
    "dress":     "women dress vestido mujer largo corto midi elegante",
    "enterito":  "women jumpsuit enterito mono mujer completo",
    "top":       "women top blouse shirt bralette camiseta blusa mujer",
    "bottom":    "women skirt pants jeans falda pantalon leggings mujer",
    "conjunto":  "women two piece set conjunto dos piezas coordinado mujer",
    "shoes":     "women shoes heels sandals boots zapatos tacones sandalias mujer",
    "outerwear": "women cape kimono jacket chaqueta wrap capa kimono chaqueta mujer",
    "accessory": "women bracelet earring necklace belt jewelry tocado aros brazalete collar cinturon joyeria mujer",
    # Categoría bag añadida al mapear CARTERAS y CLUTCH (13/05/2026)
    "bag":       "women handbag purse clutch bag cartera bolso mujer",
}


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
    El semáforo se pasa como argumento explícito para eliminar el closure bug.
    """
    async with sem:
        try:
            resp = await client.get(image_url)
            resp.raise_for_status()
            img_full  = Image.open(io.BytesIO(resp.content)).convert('RGB')
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
        4. build_image_index_incremental(new)  — añadir solo productos nuevos
        5. search_by_image(image_bytes)        — query visual individual
        6. search_outfit_by_image(image_bytes) — S1: búsqueda de outfit completo

    Persistencia:
        - Nivel 1: /tmp/visual-index/  — rápido, mismo container
        - Nivel 2: GCS                 — durable, survives deploys y reinicios

    Archivos persistidos:
        image_index.faiss  — vectores FAISS
        id_map.json        — product_ids en orden de posición FAISS
        category_map.json  — S1: categoría de outfit en orden de posición FAISS
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

        # S1: Tokenizador para encode_text() en búsqueda de outfit.
        # FashionSigLIP comparte el espacio de embedding para imagen y texto
        # (entrenado con GCL), así que encode_text() es directamente comparable
        # con encode_image() sin adaptador adicional.
        self._tokenizer = open_clip.get_tokenizer('hf-hub:Marqo/marqo-fashionSigLIP')

        # Índice FAISS y mapas paralelos
        self._faiss_index                  = None
        self._id_map: List[str]            = []
        # S1: category_map[i] = categoría de outfit del producto en posición i.
        # Paralelo a _id_map: len(self._category_map) == len(self._id_map) siempre.
        # Vacío en índices construidos antes de S1 (backward compatible).
        self._category_map: List[str]      = []
        self._indexation_running: bool     = False

        # S1 LATENCIA: Caché de text embeddings pre-computados en warmup().
        # CATEGORY_TEXT_PROMPTS es estático — siempre produce el mismo vector.
        # Pre-computar en warmup() elimina N×150ms por request en outfit search.
        # Inicializado aquí como dict vacío (se llena en warmup).
        # Si warmup() no se llama, search_outfit_by_image() tiene fallback a encode_text().
        self._text_embed_cache: Dict[str, np.ndarray] = {}

        log.info('FashionSigLIP loaded in %.1fs | embed_dim=%d | tokenizer=ready',
                 time.time() - t0, self._embed_dim)

    async def warmup(self):
        log.info('Running FashionSigLIP warmup...')
        loop = asyncio.get_running_loop()
        def _warmup():
            import torch
            dummy  = Image.new('RGB', (224, 224))
            tensor = self._preprocess(dummy).unsqueeze(0)
            with torch.no_grad():
                self._model.encode_image(tensor)

            # ← NUEVO: Pre-encodear y cachear TODOS los text prompts
            # CATEGORY_TEXT_PROMPTS son estáticos — encodearlos UNA VEZ aquí
            # elimina 9×150ms = 1350ms de latencia por request
            self._text_embed_cache = {}
            for category, prompt in CATEGORY_TEXT_PROMPTS.items():
                tokens = self._tokenizer([prompt])
                with torch.no_grad():
                    embed = self._model.encode_text(tokens)
                    embed = embed / embed.norm(dim=-1, keepdim=True)
                self._text_embed_cache[category] = embed.float().cpu().numpy()
                
        await loop.run_in_executor(None, _warmup)
        log.info(
            'FashionSigLIP warmup complete | text_embed_cache: %d categories pre-computed %s',
            len(self._text_embed_cache),
            list(self._text_embed_cache.keys())
        )

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

            # Archivos a subir: faiss + id_map siempre; category_map si existe.
            files_to_upload = [
                (FAISS_INDEX_FILE, f'{GCS_PREFIX}/image_index.faiss'),
                (ID_MAP_FILE,      f'{GCS_PREFIX}/id_map.json'),
            ]
            if CATEGORY_MAP_FILE.exists():
                files_to_upload.append((CATEGORY_MAP_FILE, GCS_CATEGORY_MAP))

            for local_path, gcs_path in files_to_upload:
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

            # Archivos requeridos (sin category_map — puede no existir en índices viejos)
            required_files = [
                (f'{GCS_PREFIX}/image_index.faiss', FAISS_INDEX_FILE),
                (f'{GCS_PREFIX}/id_map.json',       ID_MAP_FILE),
            ]
            for gcs_path, _ in required_files:
                if not bucket.blob(gcs_path).exists():
                    log.info('[visual-index] GCS: archivo no encontrado: gs://%s/%s',
                             GCS_BUCKET, gcs_path)
                    return False

            VISUAL_INDEX_PATH.mkdir(parents=True, exist_ok=True)
            for gcs_path, local_path in required_files:
                bucket.blob(gcs_path).download_to_filename(str(local_path))
                log.info('[visual-index] GCS download: %s (%.1fMB)',
                         local_path.name, local_path.stat().st_size / 1024 / 1024)

            # S1: category_map es opcional — no bloquea si no existe en GCS
            # (índice construido antes de S1).
            category_blob = bucket.blob(GCS_CATEGORY_MAP)
            if category_blob.exists():
                category_blob.download_to_filename(str(CATEGORY_MAP_FILE))
                log.info('[visual-index] GCS download: category_map.json (S1 outfit search)')
            else:
                log.info('[visual-index] GCS: category_map.json no encontrado — '
                         'outfit search en modo degradado hasta próximo rebuild')

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

            # S1: Cargar category_map si existe (backward compatible).
            # Si no existe → _category_map = [] → outfit search en modo degradado.
            if CATEGORY_MAP_FILE.exists():
                with open(CATEGORY_MAP_FILE) as f:
                    self._category_map = json.load(f)
                log.info('[visual-index] Loaded from disk: %d products (category_map: %d entries)',
                         len(self._id_map), len(self._category_map))
            else:
                self._category_map = []
                log.info('[visual-index] Loaded from disk: %d products (no category_map — '
                         'outfit search degraded until rebuild)',
                         len(self._id_map))
            return True
        except Exception as e:
            log.warning('[visual-index] Failed to load local index: %s', e)
            self._faiss_index  = None
            self._id_map       = []
            self._category_map = []
            return False

    def _save_to_disk(self) -> None:
        """Persiste faiss + id_map + category_map en /tmp."""
        import faiss
        VISUAL_INDEX_PATH.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._faiss_index, str(FAISS_INDEX_FILE))

        with open(ID_MAP_FILE, 'w') as f:
            json.dump(self._id_map, f)

        # S1: Persistir category_map solo si tiene datos.
        # Si está vacío (índice viejo o rebuild sin product_type), no crear
        # el archivo para evitar confundir el estado.
        if self._category_map:
            with open(CATEGORY_MAP_FILE, 'w') as f:
                json.dump(self._category_map, f)
            log.info('[visual-index] Saved to disk: %d products, %d categorized',
                     len(self._id_map), len(self._category_map))
        else:
            log.info('[visual-index] Saved to disk: %d products (no category_map)',
                     len(self._id_map))

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
        S1: También construye el category_map a partir del campo product_type.

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

        S1: Captura product_type de cada producto y lo convierte a categoría
        de outfit usando SHOPIFY_TYPE_TO_OUTFIT_CATEGORY. El resultado se
        almacena en self._category_map en la misma posición que el producto
        en self._id_map.
        """
        import faiss
        import httpx

        loop = asyncio.get_running_loop()
        VISUAL_INDEX_PATH.mkdir(parents=True, exist_ok=True)

        # S1: Preservar product_type junto al producto para construir category_map.
        # Filtramos por image_url (misma lógica que antes) pero guardamos el dict completo.
        products_with_images = [
            p for p in products
            if p.get('image_url') and str(p.get('image_url', '')).startswith('http')
        ]
        total   = len(products_with_images)
        skipped = len(products) - total

        # ─── FIX (12/05/2026): Deduplicar por product_id antes de indexar ────────
        # PROBLEMA DIAGNOSTICADO: Si tfidf_recommender.product_data contiene
        # IDs duplicados (mismo producto dos veces), el índice FAISS queda con
        # 2N vectores en lugar de N. Las búsquedas siguen funcionando pero
        # el top-K se desperdicia con resultados duplicados del mismo producto.
        #
        # CAUSA PROBABLE: enriquecimiento en background (PASO 4.6 colecciones)
        # o la función load_shopify_products() con paginación incorrecta.
        #
        # FIX: Deduplicar preservando la primera ocurrencia de cada ID.
        # Defensivo y correcto aunque la fuente esté limpia (O(n) sobre set).
        seen_ids: set = set()
        products_unique: list = []
        for p in products_with_images:
            pid = str(p.get('id', ''))
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                products_unique.append(p)

        if len(products_unique) < len(products_with_images):
            log.warning(
                '[visual-index] Deduplicated: %d → %d products (removed %d duplicate IDs). '
                'Root cause: check tfidf_recommender.product_data for duplicate entries.',
                len(products_with_images), len(products_unique),
                len(products_with_images) - len(products_unique)
            )
            products_with_images = products_unique
            total = len(products_with_images)
        # ─── END FIX ──────────────────────────────────────────────────────────

        # S1: Verificar qué % de productos vienen con product_type
        products_with_type = sum(1 for p in products_with_images if p.get('product_type'))
        log.info('[visual-index] Starting: %d products with image_url (%d skipped) | '
                 'product_type present: %d/%d (%.0f%%)',
                 total, skipped, products_with_type, total,
                 100 * products_with_type / max(total, 1))

        all_embeddings: List[np.ndarray] = []
        all_ids: List[str]               = []
        all_categories: List[str]        = []  # S1: paralelo a all_ids
        indexed_count  = 0
        failed_count   = 0
        current_batch_size = batch_size

        # ─── FIX (12/05/2026): while loop en lugar de for+range ───────────────
        # BUG RAÍZ: range(0, total, current_batch_size) se materializa CON EL
        # batch_size INICIAL (16). Tras el primer batch, el batch size adaptativo
        # cambia a 32, pero el step del range sigue siendo 16.
        #
        # Resultado del bug:
        #   batch_start avanza de 16 en 16 (step del range)
        #   batch = products[batch_start : batch_start + 32] (nuevo batch_size)
        #   → 16 productos solapados entre batch N y batch N+1
        #   → Matemática: 16 + 189×32 + 16 = 6080 para 3056 productos únicos
        #
        # FIX: while loop donde batch_start avanza por el step ACTUAL en
        # cada iteración, garantizando que step y slice son siempre consistentes.
        batch_start = 0
        batch_num   = -1
        while batch_start < total:
            batch_num += 1
            # Capturar step ANTES de cualquier cambio adaptativo en esta iteración.
            # batch_start avanza por este step → sin solapamiento aunque cambie.
            step  = current_batch_size
            batch = products_with_images[batch_start: batch_start + step]
            batch_start += step  # avanzar consistentemente con el step capturado
        # ─── END FIX ──────────────────────────────────────────────────────────

            sem           = asyncio.Semaphore(current_batch_size)
            t_batch_start = time.monotonic()

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=60.0),
                limits=httpx.Limits(max_connections=current_batch_size),
            ) as client:
                tasks   = [
                    _download_one(client, str(p.get('id', '')), p['image_url'], sem)
                    for p in batch
                ]
                results = await asyncio.gather(*tasks)

            # ── Batch size adaptativo (SOLO primer batch) ─────────────────────
            if batch_num == 0 and len(batch) > 0:
                t_elapsed = time.monotonic() - t_batch_start
                ok_count  = sum(1 for r in results if r is not None)
                if ok_count > 0:
                    avg_s = t_elapsed / ok_count
                    old   = current_batch_size
                    if avg_s > BATCH_SLOW_TARGET_S:
                        current_batch_size = max(BATCH_SIZE_MIN, current_batch_size // 2)
                    elif avg_s < BATCH_FAST_TARGET_S:
                        current_batch_size = min(BATCH_SIZE_MAX, current_batch_size * 2)
                    if current_batch_size != old:
                        log.info('[visual-index] Adaptive batch: %.2fs/img → '
                                 'batch_size %d → %d (range [%d, %d])',
                                 avg_s, old, current_batch_size, BATCH_SIZE_MIN, BATCH_SIZE_MAX)
                    else:
                        log.info('[visual-index] Adaptive batch: %.2fs/img → '
                                 'batch_size=%d (sin cambio)', avg_s, current_batch_size)

            failed_count   += sum(1 for r in results if r is None)

            # S1: Construir mapa product_id → product_type para este batch.
            # Se necesita para asignar la categoría correcta después del encode.
            batch_id_to_type: Dict[str, str] = {
                str(p.get('id', '')): str(p.get('product_type', '')).upper().strip()
                for p in batch
            }

            images_in_batch = [r for r in results if r is not None]
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

            batch_ids, batch_embeds = await loop.run_in_executor(
                None, _encode_batch, images_in_batch
            )
            del images_in_batch

            # S1: Convertir product_type → categoría de outfit y acumular.
            batch_categories = [
                SHOPIFY_TYPE_TO_OUTFIT_CATEGORY.get(batch_id_to_type.get(pid, ''), '')
                for pid in batch_ids
            ]

            all_embeddings.append(batch_embeds)
            all_ids.extend(batch_ids)
            all_categories.extend(batch_categories)
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

        all_matrix             = np.vstack(all_embeddings).astype(np.float32)
        faiss_index, id_map    = await loop.run_in_executor(
            None, _build_faiss, all_matrix, all_ids
        )

        self._faiss_index  = faiss_index
        self._id_map       = id_map
        self._category_map = all_categories  # S1: guardar mapa de categorías

        # S1: Log de distribución de categorías para validación
        from collections import Counter
        cat_dist = Counter(c for c in all_categories if c)
        log.info('[visual-index] Category distribution: %s', dict(cat_dist.most_common()))

        self._save_to_disk()
        await loop.run_in_executor(None, self._upload_to_gcs)

        log.info('[visual-index] Done: %d indexed, %d skipped (no URL), %d failed (download) | '
                 'categories: %d/%d mapped',
                 indexed_count, skipped, failed_count,
                 sum(1 for c in all_categories if c), len(all_categories))
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
        S1: También extiende _category_map con las categorías de los nuevos productos.
        """
        if self._indexation_running:
            log.warning('[visual-index] Duplicate request — incremental job skipped.')
            return 'already_running', 0, 0

        if self._faiss_index is None or not self._id_map:
            log.warning(
                '[visual-index] Incremental index requested but no base index exists. '
                'Run build_image_index() first.'
            )
            return 'no_base_index', 0, 0

        existing_ids = set(self._id_map)
        actually_new = [
            p for p in new_products
            if str(p.get('id', '')) not in existing_ids
            and p.get('image_url')
            and str(p.get('image_url', '')).startswith('http')
        ]

        if not actually_new:
            already_present = sum(
                1 for p in new_products if str(p.get('id', '')) in existing_ids
            )
            log.info('[visual-index] Incremental: no new products '
                     '(%d submitted, %d already in index)',
                     len(new_products), already_present)
            return 'no_new_products', 0, already_present

        log.info('[visual-index] Incremental: %d new products to index '
                 '(%d already in index, %d submitted total)',
                 len(actually_new), len(new_products) - len(actually_new), len(new_products))

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
        """Descarga, encodea y añade productos nuevos al índice FAISS existente."""
        import httpx

        loop          = asyncio.get_running_loop()
        total         = len(new_products)
        indexed_count = 0
        failed_count  = 0
        new_embeddings: List[np.ndarray] = []
        new_ids: List[str]               = []
        new_categories: List[str]        = []  # S1

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

            # S1: Mapa product_id → product_type para este batch
            batch_id_to_type: Dict[str, str] = {
                str(p.get('id', '')): str(p.get('product_type', '')).upper().strip()
                for p in batch
            }

            failed_count   += sum(1 for r in results if r is None)
            images_in_batch = [r for r in results if r is not None]
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

            batch_ids, batch_embeds = await loop.run_in_executor(
                None, _encode_batch, images_in_batch
            )
            del images_in_batch

            # S1: Categorías para los nuevos productos
            batch_categories = [
                SHOPIFY_TYPE_TO_OUTFIT_CATEGORY.get(batch_id_to_type.get(pid, ''), '')
                for pid in batch_ids
            ]

            new_embeddings.append(batch_embeds)
            new_ids.extend(batch_ids)
            new_categories.extend(batch_categories)
            indexed_count += len(batch_ids)

            log.info('[visual-index] Incremental progress: %d/%d new products',
                     indexed_count, total)

            if batch_num > 0 and batch_num % 10 == 0:
                gc.collect()

        if not new_embeddings:
            log.warning('[visual-index] Incremental: no embeddings generated')
            return 0, failed_count

        new_matrix = np.vstack(new_embeddings).astype(np.float32)

        def _add_to_faiss(matrix, ids, categories):
            # FAISS IndexFlatIP es thread-safe para lecturas concurrentes con
            # add() atómico. _indexation_running=True previene dos add() simultáneos.
            self._faiss_index.add(matrix)
            self._id_map.extend(ids)
            # S1: Extender category_map si ya tiene datos.
            # Si _category_map está vacío (índice pre-S1), lo dejamos vacío
            # para no crear un mapa parcialmente poblado que generaría
            # falsos negativos en búsquedas de outfit.
            if self._category_map:
                self._category_map.extend(categories)

        await loop.run_in_executor(None, _add_to_faiss, new_matrix, new_ids, new_categories)

        self._save_to_disk()
        await loop.run_in_executor(None, self._upload_to_gcs)

        log.info('[visual-index] Incremental done: +%d products indexed, %d failed. '
                 'Total index size: %d',
                 indexed_count, failed_count, len(self._id_map))
        return indexed_count, failed_count

    # ─────────────────────────────────────────────────────────────────────────
    # SEARCH — búsqueda visual individual (existente, sin cambios)
    # ─────────────────────────────────────────────────────────────────────────

    async def search_by_image(self, image_bytes: bytes, top_k: int = 8) -> List[str]:
        """Encodea la imagen del usuario y busca los K productos más similares."""
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
    # S1: SEARCH — búsqueda de outfit completo (nuevo)
    # ─────────────────────────────────────────────────────────────────────────

    async def search_outfit_by_image(
        self,
        image_bytes: bytes,
        target_categories: List[str] = None,
        top_k_per_category: int      = 3,
        search_pool: int             = 150,   # FIX (14/05/2026): 40 → 150
        # DIAGNÓSTICO: Con search_pool=40, zapatos (2.2% del catálogo) nunca aparecían.
        # Matemática: E[zapatos en pool] = 40 × 0.022 = 0.86 < 1 → imposible encontrar.
        # Con 150: E[zapatos] = 150 × 0.022 = 3.3 → se encuentran con alta probabilidad.
        # Impacto en latencia: FAISS InnerProduct es O(n·d). 150 vs 40 añade
        # microsegundos sobre 3056 vectores × 768 dims. Negligible.
        alpha: float                 = 0.6,
    ) -> Dict[str, List[str]]:
        """
        Busca productos para cada categoría de un outfit a partir de una imagen.

        ESTRATEGIA — Composite Embedding por categoría:
        ──────────────────────────────────────────────────────────────────────
        Para cada categoría objetivo (ej. "dress", "shoes"):
          1. Encode la imagen → image_embed  (hecho UNA VEZ, reutilizado)
          2. Encode texto de la categoría → text_embed  (~15ms, muy rápido)
          3. Composite: query = normalize(α × image_embed + (1-α) × text_embed)
             El texto "empuja" el query hacia la categoría en el espacio vectorial
             compartido de FashionSigLIP (entrenado con GCL multimodal).
          4. FAISS search con top-K candidatos (search_pool)
          5. Filtrar por _category_map[idx] == categoría
          6. Devolver top-N IDs para esa categoría

        MODO DEGRADADO (category_map vacío):
        ──────────────────────────────────────────────────────────────────────
        Si _category_map está vacío (índice construido antes de S1), se
        devuelven los top candidatos sin filtro de categoría. La búsqueda
        sigue siendo útil (visualmente similar al outfit), pero sin garantía
        de que cada categoría tenga la prenda correcta.
        Para activar el modo completo: rebuild con POST /v1/embed/index-images.

        Args:
            image_bytes:         Foto del outfit del usuario (JPEG/PNG/WebP)
            target_categories:   Categorías a buscar. Default: dress, top, bottom, shoes
            top_k_per_category:  Máximo productos por categoría en el resultado
            search_pool:         Candidatos FAISS antes del filtro de categoría.
                                 Debe ser > total de productos en cada categoría / 2
                                 para evitar falsos "no encontrado".
            alpha:               Peso del embedding de imagen (0=solo texto, 1=solo imagen).
                                 0.7 = prioriza similitud visual, el texto guía la categoría.

        Returns:
            {
              "dress":      ["pid1", "pid2"],
              "shoes":      ["pid3"],
              "outfit_mode": "composite_category_filtered" | "degraded_no_category_map"
            }
        """
        if self._faiss_index is None:
            log.warning('[outfit-search] Visual index not built — returning empty.')
            return {"outfit_mode": "no_index"}

        if target_categories is None:
            target_categories = ["dress", "top", "bottom", "shoes"]

        has_category_map = bool(self._category_map)
        outfit_mode      = "composite_category_filtered" if has_category_map else "degraded_no_category_map"

        if not has_category_map:
            log.warning('[outfit-search] category_map empty — operating in degraded mode. '
                        'Run full rebuild to enable category filtering.')

        loop = asyncio.get_running_loop()

        def _encode_and_search_outfit(img_bytes, categories):
            import torch as _torch

            # ── Paso 1: Encode imagen UNA VEZ (reutilizado para todas las categorías) ──
            # Este es el paso lento (~400ms). Hacerlo una sola vez es crítico
            # para que la latencia total sea O(1) y no O(N_categorías).
            img    = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            tensor = self._preprocess(img).unsqueeze(0)
            with _torch.no_grad():
                image_embed = self._model.encode_image(tensor)
                image_embed = image_embed / image_embed.norm(dim=-1, keepdim=True)
            image_np = image_embed.float().cpu().numpy()  # shape (1, embed_dim)

            results = {}

            for category in categories:
                text_prompt = CATEGORY_TEXT_PROMPTS.get(category)
                if not text_prompt:
                    log.debug('[outfit-search] No text prompt for category: %s', category)
                    continue

                # ── Paso 2: Text embedding desde caché (pre-computado en warmup) ────────
                # CATEGORY_TEXT_PROMPTS son estáticos — siempre producen el mismo vector.
                # Pre-computados en warmup() una sola vez, eliminando N×150ms por request.
                # Impacto: 9 categorías × 150ms = 1350ms → 0ms (solo lookup de dict).
                #
                # Fallback a encode_text() si el caché no está poblado
                # (p.ej. warmup() no se llamó o falló — robusto ante reinicios parciales).
                cached_text_np = self._text_embed_cache.get(category)
                if cached_text_np is not None:
                    # Ruta rápida: lookup O(1), sin GPU/CPU inference
                    text_np = cached_text_np
                else:
                    # Ruta lenta: encode en tiempo real (fallback)
                    log.warning(
                        '[outfit-search] text_embed_cache MISS para category=%s '
                        '(caché vacío — warmup() no completado). Encodificando en tiempo real.',
                        category
                    )
                    tokens = self._tokenizer([text_prompt])
                    with _torch.no_grad():
                        text_embed = self._model.encode_text(tokens)
                        text_embed = text_embed / text_embed.norm(dim=-1, keepdim=True)
                    text_np = text_embed.float().cpu().numpy()

                # ── Paso 3: Composite query ────────────────────────────────────
                # Combinación lineal renormalizada.
                # α=0.7: el 70% del query viene de la imagen (similitud visual
                # al outfit), el 30% del texto de categoría (filtro semántico).
                #
                # ¿Por qué renormalizar?
                # FAISS IndexFlatIP usa inner product (equivalente a cosine
                # similarity con vectores normalizados). Si el composite no está
                # normalizado, los scores de FAISS serán inconsistentes entre
                # categorías con diferentes normas.
                composite = alpha * image_np + (1.0 - alpha) * text_np
                norm      = np.linalg.norm(composite, axis=-1, keepdims=True)
                composite = (composite / norm).astype(np.float32)

                # ── Paso 4: FAISS search con pool amplio ────────────────────────
                # search_pool > top_k_per_category para que haya candidatos
                # suficientes DESPUÉS del filtro de categoría.
                _, indices = self._faiss_index.search(composite, search_pool)

                # ── Paso 5: Filtrar por categoría ──────────────────────────────
                category_ids = []

                if has_category_map:
                    # Modo completo: filtrar por _category_map[idx] == categoría
                    for idx in indices[0]:
                        if 0 <= idx < len(self._id_map):
                            if self._category_map[idx] == category:
                                category_ids.append(self._id_map[idx])
                            if len(category_ids) >= top_k_per_category:
                                break
                else:
                    # Modo degradado: devolver top candidatos sin filtro
                    category_ids = [
                        self._id_map[idx]
                        for idx in indices[0]
                        if 0 <= idx < len(self._id_map)
                    ][:top_k_per_category]

                if category_ids:
                    results[category] = category_ids
                else:
                    log.debug('[outfit-search] No results for category "%s" '
                              '(pool=%d, category_map_size=%d)',
                              category, search_pool, len(self._category_map))

            results["outfit_mode"] = outfit_mode
            return results

        outfit_results = await loop.run_in_executor(
            None, _encode_and_search_outfit, image_bytes, target_categories
        )

        found_cats = [k for k in outfit_results if k != "outfit_mode"]
        log.info('[outfit-search] Complete: %d categories found=%s mode=%s',
                 len(found_cats), found_cats, outfit_mode)

        return outfit_results

    # ─────────────────────────────────────────────────────────────────────────
    # ESTADO (usados en /health y diagnóstico)
    # ─────────────────────────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        return self._faiss_index is not None and len(self._id_map) > 0

    def index_size(self) -> int:
        return len(self._id_map)

    def is_indexing(self) -> bool:
        return self._indexation_running

    def category_map_size(self) -> int:
        """S1: Número de productos con categoría de outfit asignada."""
        return sum(1 for c in self._category_map if c)
