
## Plan de Implementación: Búsqueda por Outfit Completo (Nivel 2)

---

### Hallazgos clave de la investigación

**1. FashionSigLIP ya soporta texto — no necesitamos ningún modelo adicional.**

FashionSigLIP fue entrenado con Generalised Contrastive Learning (GCL) sobre no solo descripciones de texto, sino también categorías, estilos, colores, materiales y palabras clave para proporcionar resultados de búsqueda altamente relevantes en moda. El modelo que ya tienes cargado en RAM (700MB) puede hacer zero-shot classification por categoría con solo llamar a `model.encode_text()`. El `visual_retriever.py` actual solo usa `encode_image()`, ignorando esta capacidad.

**2. El patrón correcto es Composite Embedding, no segmentación.**

Los embeddings de texto e imagen se fusionan en un único embedding de query que combina información de ambas modalidades. Esta técnica — combinar el embedding de la imagen del outfit con el embedding del texto de la categoría buscada — es el estándar para búsqueda fashion multi-modal. Se aplica en FAISS con una sola operación vectorial.

**3. FAISS IndexFlatIP necesita metadata externa para filtrar por categoría.**

El `IndexFlatIP` actual no tiene metadatos adjuntos a los vectores. La solución es un `category_map` paralelo al `id_map` existente, con filtrado post-búsqueda en Python. Con menos de 100,000 vectores, IndexFlatIP es completamente viable — y el filtrado post-búsqueda sobre 3,056 resultados es <1ms.

---

### Arquitectura de la solución

```
Usuario sube foto de outfit
           │
           ▼
POST /v1/mcp/visual-search/outfit  (nuevo endpoint)
           │
           ▼
visual_search_router.py
  → colbert_client.search_outfit_by_image(image_bytes, market_id)
           │
           ▼
embedding-service: POST /v1/embed/search-outfit  (nuevo endpoint)
           │
           ├─ Step 1: Encode image → image_embed  (~400ms, ya cached en warmup)
           │
           ├─ Por cada categoría objetivo:
           │    text_embed = encode_text("a [category]")  (~15ms, muy rápido)
           │    composite  = normalize(0.7 × image_embed + 0.3 × text_embed)
           │    candidates = faiss.search(composite, top_k=30)
           │    filtered   = [id for id in candidates if category_map[id] == category]
           │    resultado[category] = filtered[:top_n]
           │
           └─ Return {"top": [...ids], "bottom": [...ids], "shoes": [...ids], ...}
                    latency: ~500ms total
           │
           ▼
visual_search_router.py
  → Resolver IDs → productos completos (tfidf_recommender.id_index)
  → Aplicar precios de mercado
  → Return outfit estructurado
```

**Latencia estimada:**
| Componente | Tiempo |
|---|---|
| Image encode (FashionSigLIP ViT-B-16) | ~400ms (igual que búsqueda normal) |
| Text encode × 5 categorías | ~15ms × 5 = 75ms |
| FAISS search × 5 | <1ms × 5 = 5ms |
| **Total p50 estimado** | **~480ms** (vs 435ms actual) |

---

### Fases de implementación

```
FASE 1  Embedding-service         [~4h]
FASE 2  Monolith (API layer)      [~3h]
FASE 3  Rebuild + Validación      [~1h]
FASE 4  Frontend                  [~2h]
```

---

### FASE 1 — Embedding-service

**Archivos a modificar:** `visual_retriever.py`, `main.py`

#### F1.1 — Agregar tokenizer y category_map

En `visual_retriever.py`, el `__init__` actual solo carga el modelo de imagen. Añadir:

```python
# En __init__, justo después de cargar el modelo:
import open_clip as _open_clip
self._tokenizer = _open_clip.get_tokenizer('hf-hub:Marqo/marqo-fashionSigLIP')

# Nuevo atributo paralelo a _id_map:
# Para cada posición i en el índice FAISS:
#   _id_map[i]       = product_id (ya existe)
#   _category_map[i] = product_type de Shopify (nuevo)
self._category_map: List[str] = []
```

**Por qué `_category_map` en lugar de un dict:**
La posición en FAISS es el índice de lista. Usar `_category_map[i]` es O(1) y se alinea perfectamente con el `_id_map[i]` existente. Sin overhead adicional.

#### F1.2 — Persistencia del category_map

```python
# Nuevas constantes:
CATEGORY_MAP_FILE = VISUAL_INDEX_PATH / 'category_map.json'
GCS_CATEGORY_MAP  = f'{GCS_PREFIX}/category_map.json'

# En _save_to_disk():  añadir escritura de category_map.json
# En _load_local_index(): añadir lectura (con fallback a [] si no existe)
# En _upload_to_gcs():  añadir upload de category_map.json
# En _download_from_gcs(): añadir download de category_map.json
```

**Backward compatibility:** Si `category_map.json` no existe (índice anterior al feature), `_category_map = []` y la búsqueda de outfit degrada al modo sin filtro de categoría. El sistema no crashea.

#### F1.3 — Modificar `build_image_index()` para capturar product_type

```python
# En _run_indexation(), al construir products_with_images:
products_with_images = [
    {
        'id':           str(p.get('id', '')),
        'image_url':    p.get('image_url', ''),
        'product_type': str(p.get('product_type', '')),  # ← NUEVO
    }
    for p in products
    if p.get('image_url') and str(p.get('image_url', '')).startswith('http')
]
# Y al construir all_ids → también capturar all_categories
```

#### F1.4 — Mapeo Shopify product_type → categorías de outfit

```python
# Constante a nivel de módulo (configurable):
# Mapea los product_type de Shopify del catálogo actual a categorías de outfit.
# IMPORTANTE: ajustar según los product_type reales del catálogo.
SHOPIFY_TYPE_TO_OUTFIT_CATEGORY: Dict[str, str] = {
    # Tops
    "Camisas":    "top",
    "Blusas":     "top",
    "Tops":       "top",
    "Camisetas":  "top",
    "Chaquetas":  "top",
    "Abrigos":    "top",
    "Suéteres":   "top",
    # Bottoms
    "Pantalones": "bottom",
    "Faldas":     "bottom",
    "Shorts":     "bottom",
    "Jeans":      "bottom",
    # Dresses
    "Vestidos":   "dress",
    "Monos":      "dress",
    # Shoes
    "Zapatos":    "shoes",
    "Sandalias":  "shoes",
    "Botas":      "shoes",
    "Tacones":    "shoes",
    # Bags & accessories
    "Bolsos":     "bag",
    "Carteras":   "bag",
    "Accesorios": "accessory",
    "Cinturones": "accessory",
}

# Prompts de texto para FashionSigLIP por categoría de outfit.
# Combinan español e inglés para aprovechar el entrenamiento multilingüe del modelo.
CATEGORY_TEXT_PROMPTS: Dict[str, str] = {
    "top":       "shirt blouse top jacket camiseta blusa chaqueta",
    "bottom":    "pants skirt jeans shorts pantalón falda",
    "dress":     "dress jumpsuit vestido mono",
    "shoes":     "shoes boots sandals heels zapatos botas sandalias",
    "bag":       "bag purse handbag bolso cartera",
    "accessory": "belt accessory jewelry cinturón accesorio",
}
```

**⚠️ Acción necesaria antes de implementar:** Verificar los `product_type` reales del catálogo:

```powershell
# Ejecutar para ver los product_type únicos en el TF-IDF
python -c "
import pickle, collections
data = pickle.load(open('data/tfidf_model.pkl', 'rb'))
types = collections.Counter(p.get('product_type','') for p in data.get('products', data) if isinstance(data, dict) or True)
for t, n in types.most_common():
    print(f'{n:4d}  {t!r}')
"
```

#### F1.5 — Nuevo método `search_outfit_by_image()`

```python
async def search_outfit_by_image(
    self,
    image_bytes: bytes,
    target_categories: List[str] = None,
    top_k_per_category: int = 3,
    search_pool: int = 30,
    alpha: float = 0.7,
) -> Dict[str, List[str]]:
    """
    Busca productos para cada categoría de un outfit a partir de una imagen.

    Estrategia: Composite Embedding por categoría.
    Para cada categoría objetivo:
      1. Encoda la imagen → image_embed (hecho UNA SOLA VEZ, reutilizado)
      2. Encoda el texto de la categoría → text_embed  (~15ms)
      3. Combina: query = normalize(α × image_embed + (1-α) × text_embed)
      4. Busca FAISS con top-K candidatos
      5. Filtra por _category_map → solo productos de esa categoría
      6. Devuelve los top-N IDs para esa categoría

    Args:
        image_bytes:          Foto del outfit del usuario
        target_categories:    Categorías a buscar. Default: ["top","bottom","shoes"]
        top_k_per_category:   Máximo de productos por categoría en el resultado
        search_pool:          Candidatos a recuperar de FAISS antes de filtrar
        alpha:                Peso del embedding de imagen (0=solo texto, 1=solo imagen)

    Returns:
        {
            "top":    ["pid1", "pid2"],
            "bottom": ["pid3"],
            "shoes":  ["pid4", "pid5"],
            "outfit_mode": "composite_category_filtered"
        }
    """
    if self._faiss_index is None:
        log.warning('Visual index not built — returning empty outfit.')
        return {}

    if target_categories is None:
        target_categories = ["top", "bottom", "shoes"]

    loop = asyncio.get_running_loop()

    def _encode_and_search_outfit(img_bytes, categories):
        import torch as _torch

        # ── Paso 1: Encode image (UNA VEZ para todas las categorías) ─────
        img    = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        tensor = self._preprocess(img).unsqueeze(0)
        with _torch.no_grad():
            image_embed = self._model.encode_image(tensor)
            image_embed = image_embed / image_embed.norm(dim=-1, keepdim=True)
        image_np = image_embed.float().cpu().numpy()

        results = {}

        for category in categories:
            text_prompt = CATEGORY_TEXT_PROMPTS.get(category)
            if not text_prompt:
                continue

            # ── Paso 2: Encode texto de categoría (~15ms por categoría) ──
            tokens = self._tokenizer([text_prompt])
            with _torch.no_grad():
                text_embed = self._model.encode_text(tokens)
                text_embed = text_embed / text_embed.norm(dim=-1, keepdim=True)
            text_np = text_embed.float().cpu().numpy()

            # ── Paso 3: Composite query  ──────────────────────────────────
            # α × imagen + (1-α) × texto, renormalizado.
            # α=0.7: prioriza similitud visual del outfit, pero el texto
            # "empuja" el query hacia la subcategoría correcta.
            composite = alpha * image_np + (1 - alpha) * text_np
            norm = np.linalg.norm(composite, axis=-1, keepdims=True)
            composite = (composite / norm).astype(np.float32)

            # ── Paso 4: FAISS search con pool amplio ─────────────────────
            _, indices = self._faiss_index.search(composite, search_pool)

            # ── Paso 5: Filtrar por categoría ─────────────────────────────
            # Si _category_map está vacío (índice pre-feature), devolver
            # todos los candidatos sin filtrar (degraded mode).
            category_ids = []
            if self._category_map:
                for idx in indices[0]:
                    if 0 <= idx < len(self._id_map):
                        if self._category_map[idx] == category:
                            category_ids.append(self._id_map[idx])
                        if len(category_ids) >= top_k_per_category:
                            break
            else:
                # Degraded: sin category_map, devolver top candidatos sin filtro
                category_ids = [
                    self._id_map[idx]
                    for idx in indices[0]
                    if 0 <= idx < len(self._id_map)
                ][:top_k_per_category]

            results[category] = category_ids

        return results

    outfit_results = await loop.run_in_executor(
        None, _encode_and_search_outfit, image_bytes, target_categories
    )
    outfit_results["outfit_mode"] = (
        "composite_category_filtered" if self._category_map else "degraded_no_category_map"
    )
    return outfit_results
```

#### F1.6 — Nuevo endpoint en `main.py`

```python
class OutfitSearchRequest(BaseModel):
    target_categories: List[str] = ["top", "bottom", "shoes"]
    top_k_per_category: int = 3

@app.post('/v1/embed/search-outfit')
async def search_outfit(
    file: UploadFile = File(...),
    categories: str = Form('["top","bottom","shoes"]'),  # JSON string
):
    """
    Búsqueda de outfit completo por imagen.
    Para cada categoría objetivo, devuelve los product_ids más similares
    con filtrado por categoría de prenda.
    """
    if retriever is None or not retriever.is_ready():
        raise HTTPException(503, "Visual index not ready")

    import json as _json
    try:
        target_cats = _json.loads(categories)
    except Exception:
        target_cats = ["top", "bottom", "shoes"]

    img_bytes = await file.read()
    t0 = time.time()
    outfit = await retriever.search_outfit_by_image(img_bytes, target_cats)
    outfit["latency_ms"] = round((time.time() - t0) * 1000, 1)
    outfit["visual_index_size"] = retriever.index_size()
    return outfit
```

---

### FASE 2 — Monolith (API Layer)

**Archivos a modificar:** `colbert_client.py`, `visual_search_router.py`

#### F2.1 — `colbert_client.py`: nuevo método

```python
async def search_outfit_by_image(
    self,
    image_bytes: bytes,
    target_categories: List[str] = None,
    top_k_per_category: int = 3,
) -> Optional[Dict]:
    """
    Busca productos para un outfit completo a partir de una imagen.
    Llama al endpoint /v1/embed/search-outfit del embedding-service.

    Returns: {category: [product_ids], latency_ms, outfit_mode}
    O None si el visual circuit-breaker está abierto o hay error.
    """
    if self._visual_circuit_open:
        log.debug('ColBERT VISUAL circuit open — outfit search skipped')
        return None

    if target_categories is None:
        target_categories = ["top", "bottom", "shoes"]

    try:
        import json
        auth = await self._auth_headers()
        resp = await self._http.post(
            '/v1/embed/search-outfit',
            headers=auth,
            files={'file': ('outfit.jpg', image_bytes, 'image/jpeg')},
            data={'categories': json.dumps(target_categories),
                  'top_k_per_category': str(top_k_per_category)},
            timeout=12.0,  # Más generoso que la búsqueda individual: N categorías
        )
        resp.raise_for_status()
        data = resp.json()
        self._visual_failures = 0
        log.info(
            'Outfit search: categories=%s latency=%.0fms mode=%s',
            list(data.keys()), data.get('latency_ms', 0), data.get('outfit_mode', '?')
        )
        return data
    except Exception as e:
        self._handle_visual_failure(e)
        return None
```

#### F2.2 — `visual_search_router.py`: nuevo endpoint

```python
@router.post('/v1/mcp/visual-search/outfit')
async def visual_search_outfit(
    file: UploadFile = File(...),
    market_id: str = Form('ES'),
    top_k_per_category: int = Form(3),
    api_key: str = Depends(get_api_key),
):
    """
    Búsqueda de outfit completo por imagen.

    Dado un outfit foto, devuelve sugerencias de productos para cada categoría
    (top, bottom, zapatos, etc.) usando FashionSigLIP con Composite Embedding.

    Response:
    {
        "outfit": {
            "top":    [{product_id, title, image_url, price, ...}],
            "bottom": [{...}],
            "shoes":  [{...}],
        },
        "outfit_mode": "composite_category_filtered",
        "latency_ms": 487.3,
        "market_id": "ES"
    }
    """
    if not _visual_search_enabled():
        raise HTTPException(503, "Visual search not enabled")

    colbert = _get_colbert_client()
    image_bytes = await file.read()
    t0 = time.time()

    # ── Buscar outfit en embedding-service ───────────────────────────────────
    raw_outfit = await colbert.search_outfit_by_image(
        image_bytes=image_bytes,
        target_categories=["top", "bottom", "shoes", "dress", "bag"],
        top_k_per_category=top_k_per_category,
    )

    if raw_outfit is None:
        raise HTTPException(503, "Visual search unavailable (circuit breaker open)")

    # ── Resolver IDs → productos completos ───────────────────────────────────
    # Importar tfidf_recommender desde el módulo principal
    from src.api.main_unified_redis import tfidf_recommender

    outfit_resolved = {}
    for category, product_ids in raw_outfit.items():
        if category in ("latency_ms", "outfit_mode", "visual_index_size"):
            continue
        if not product_ids:
            continue

        category_products = []
        for pid in product_ids:
            if tfidf_recommender and hasattr(tfidf_recommender, 'id_index'):
                product = tfidf_recommender.id_index.get(str(pid))
                if product:
                    # Aplicar precio de mercado
                    market_prices = product.get('market_prices', {})
                    market_price  = market_prices.get(market_id, {})
                    category_products.append({
                        "product_id":  str(pid),
                        "title":       product.get("title", ""),
                        "image_url":   product.get("image_url", ""),
                        "price":       market_price.get("price", product.get("price")),
                        "currency":    market_price.get("currency", "CLP"),
                        "product_type": product.get("product_type", ""),
                        "handle":      product.get("handle", ""),
                    })
        if category_products:
            outfit_resolved[category] = category_products

    total_latency = round((time.time() - t0) * 1000, 1)

    logger.info(
        "outfit_search_completed",
        categories_found=list(outfit_resolved.keys()),
        total_products=sum(len(v) for v in outfit_resolved.values()),
        outfit_mode=raw_outfit.get("outfit_mode", "unknown"),
        market_id=market_id,
        latency_ms=total_latency,
    )

    return {
        "outfit":      outfit_resolved,
        "outfit_mode": raw_outfit.get("outfit_mode", "unknown"),
        "latency_ms":  total_latency,
        "market_id":   market_id,
    }
```

---

### FASE 3 — Rebuild del índice y validación

Después del deploy, el `category_map` está vacío (índice anterior). Se necesita un rebuild completo para poblarlo:

```bash
# Full rebuild que ahora incluye product_type en cada producto
curl -X POST \
  -H "X-API-Key: 2fed9999056fab6dac5654238f0cae1c" \
  -H "Content-Type: application/json" \
  -d '{}' \
  https://retail-recommender-178362262166.us-central1.run.app/v1/mcp/visual-search/index

# Esperar ~30 min, luego validar que category_map tiene datos:
curl -s https://retail-embedding-service-178362262166.us-central1.run.app/health \
     -H "Authorization: Bearer $(gcloud auth print-identity-token)"
# → {"visual_index_size": 3056, "category_map_size": 3056, ...}
```

**Script de validación local:**

```python
# validate_outfit_search.py
import requests, base64
from pathlib import Path

MONOLITH = "https://retail-recommender-178362262166.us-central1.run.app"
API_KEY  = "2fed9999056fab6dac5654238f0cae1c"
TEST_IMG = "test_outfit.jpg"  # foto de outfit de prueba

with open(TEST_IMG, "rb") as f:
    resp = requests.post(
        f"{MONOLITH}/v1/mcp/visual-search/outfit",
        headers={"X-API-Key": API_KEY},
        files={"file": ("outfit.jpg", f, "image/jpeg")},
        data={"market_id": "ES", "top_k_per_category": "2"},
    )

data = resp.json()
print(f"Status: {resp.status_code}")
print(f"Outfit mode: {data.get('outfit_mode')}")
print(f"Latency: {data.get('latency_ms')}ms")
for category, products in data.get("outfit", {}).items():
    print(f"\n  {category}:")
    for p in products:
        print(f"    [{p['product_type']}] {p['title']} — {p['price']} {p['currency']}")

# Criterios de éxito:
# ✅ outfit_mode = "composite_category_filtered" (no "degraded")
# ✅ Al menos 2 categorías con resultados
# ✅ Products en "top" tienen product_type de tipo top
# ✅ Products en "bottom" tienen product_type de tipo bottom
# ✅ Latency < 800ms
```

---

### FASE 4 — Frontend

**Archivo a modificar:** `ChatWidget.tsx`

El widget ya tiene el botón de cámara para búsqueda visual individual. Se añade una opción de modo outfit:

```
[📷 Buscar prenda similar]  →  endpoint actual
[👗 Completar outfit]       →  nuevo endpoint /outfit
```

El resultado del outfit se renderiza como un carrusel horizontal por categoría, similar a cómo se muestran las recomendaciones actuales pero agrupadas.

---

### Resumen del plan por sesión de trabajo

| Sesión | Scope | Archivos | Tiempo estimado |
|---|---|---|---|
| **S1** | Investigar product_types reales del catálogo + F1.1 a F1.4 | `visual_retriever.py` | 2h |
| **S2** | F1.5, F1.6 (embed-service completo) + deploy | `visual_retriever.py`, `main.py` | 3h |
| **S3** | F2.1, F2.2 (monolith) + rebuild + validación | `colbert_client.py`, `visual_search_router.py` | 3h |
| **S4** | Frontend + tests E2E | `ChatWidget.tsx`, `api.ts` | 2h |

---

### Riesgo más alto: calibración de α

El parámetro `α=0.7` (peso imagen vs texto) no está calibrado para este catálogo específico. Si es demasiado alto, el filtro de texto no tiene suficiente influencia y los resultados no respetan la categoría. Si es demasiado bajo, la búsqueda prioriza la categoría sobre la similitud visual.

**Estrategia de calibración:** En la sesión de validación (S3), probar `α ∈ {0.5, 0.6, 0.7, 0.8}` con 5 fotos de outfit de prueba y medir el % de resultados por categoría correcta.

---

> 💡 **Oportunidad de aprendizaje — Composite Embedding vs. segmentación:** La alternativa obvia para outfit search sería usar un modelo de segmentación de objetos (YOLO, SAM) para detectar y recortar cada prenda antes de encodarla. Eso daría búsquedas de prenda exacta, pero añade un modelo adicional de ~100MB en RAM, latencia de ~200ms extra, y complejidad de mantenimiento. El Composite Embedding aprovecha algo más elegante: que FashionSigLIP ya "entiende" categorías de ropa en el espacio de embedding gracias a su entrenamiento GCL. El vector de texto "pantalón" ya codifica la semántica de categoría bottom-wear en el mismo espacio vectorial que las imágenes. Al combinar ambos vectores, le estamos diciendo al sistema: "búscame algo visualmente similar a este outfit, pero que específicamente sea del tipo bottom-wear". Es zero-shot, sin entrenamiento adicional, sin modelo extra.

¿Comenzamos con S1 en la próxima sesión? Lo primero sería verificar los `product_type` reales del catálogo para definir el mapeo de categorías correctamente.