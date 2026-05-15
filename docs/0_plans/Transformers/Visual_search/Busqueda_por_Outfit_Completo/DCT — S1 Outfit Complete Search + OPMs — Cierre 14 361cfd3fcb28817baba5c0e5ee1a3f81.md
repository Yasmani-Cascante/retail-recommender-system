# DCT — S1 Outfit Complete Search + OPMs — Cierre 14/05/2026

# DCT — S1 Outfit Complete Search + OPMs — Cierre 14/05/2026

> **Sesión:** 12–14 mayo 2026
> 

> **Sistema:** Retail Recommender v2.1.0 — [ai-shoppings.myshopify.com](http://ai-shoppings.myshopify.com)
> 

> **Stack:** FastAPI (monolito) + embedding-service + FashionSigLIP + FAISS + React widget
> 

> **GCP:** retail-recommendations-449216 / us-central1
> 

---

## Estado al inicio de la sesión

La sesión anterior dejó pendientes:

- OPM-1 (visual index sync job) implementado pero no validado en producción
- S1 Outfit Search: arquitectura definida, fases 1–3 sin implementar
- Bug `for+range` con adaptive batch producía 6080 entradas (2×3056) en FAISS

---

## Trabajo completado

### OPM-1 — Visual Index Incremental Sync Job ✅

**Archivo:** `src/api/services/visual_index_sync_job.py`  

**Integrado en:** `src/api/main_unified_redis.py` (PASO 10.6 del lifespan)

- Job background que arranca con `initial_delay=120s` y corre cada 6h
- Envía el catálogo completo (3056 productos con imagen) al embedding-service
- El embedding-service filtra los ya indexados y solo procesa los nuevos
- **Validado en producción:** `opm1_visual_sync_cycle_completed elapsed_ms=193` ✅
- **Razón del intervalo 6h:** cobertura sin solapamiento con el rebuild semanal (Cloud Scheduler lunes 02:00). Para moda, un webhook fallido corregido en 6h es aceptable.

### OPM-2 — Cloud Scheduler weekly rebuild ✅

- Scheduler configurado: `visual-search-weekly-rebuild` lunes 02:00 Europe/Madrid

### OPM-3 — `_graphql_query_with_retry` en shopify_kb_client ✅

- Corregido `AttributeError` por método inexistente
- Validado: 12 páginas KB sincronizadas en ES + EN sin errores

### OPM-5 — Entry point único ✅

- Eliminados `main_*.py` obsoletos; único entry point: `main_unified_redis.py`

---

## S1 Outfit Complete Search — FASES 1–4 COMPLETADAS

### Arquitectura implementada

```
Usuario foto outfit
  → POST /v1/mcp/visual-search/outfit  (monolito, X-API-Key)
  → colbert_client.search_outfit_by_image()
  → POST /v1/embed/search-outfit  (embedding-service, IAM auth)
  → FashionSigLIP encode_image (UNA VEZ) + text_embed_cache[categoria]
  → Composite query = normalize(α×img + (1-α)×text) por categoría
  → FAISS search_pool=150 + filtro category_map
  → {dress:[pid1,pid2], top:[pid3], accessory:[pid4], ...}
  → Monolito resuelve IDs → productos con precios de mercado
  → Widget: panel horizontal de columnas por categoría
```

### FASE 1 — Embedding-service ✅

**Archivos modificados:**

- `src/api/services/embedding-service/visual_retriever.py`
- `src/api/services/embedding-service/main.py`
- `src/api/services/embedding-service/Dockerfile`

**Cambios clave:**

1. `self._tokenizer` en `__init__` (FashionSigLIP tokenizer)
2. `self._text_embed_cache: Dict[str, np.ndarray] = {}` en `__init__` (defensivo)
3. `self._category_map: List[str]` paralelo a `_id_map`
4. `SHOPIFY_TYPE_TO_OUTFIT_CATEGORY` — 28 tipos reales del catálogo → 9 categorías (99.1% cobertura)
5. `CATEGORY_TEXT_PROMPTS` — 9 prompts bilingüe ES+EN para FashionSigLIP
6. `search_outfit_by_image()` — Composite Embedding por categoría + text_embed_cache
7. Nuevo endpoint `POST /v1/embed/search-outfit`
8. Persistencia `category_map.json` en disco y GCS

**Bugs críticos corregidos:**

| Bug | Root cause | Fix |
| --- | --- | --- |
| FAISS 6080 entradas (2×3056) | `for range(0, N, step)` con adaptive batch: step fijo en 16, slice usa 32 → solapamiento | `while` loop con `step = current_batch_size` antes de cambio adaptativo |
| category_map vacío en startup | No se descargaba de GCS en primera carga | Añadido download de `category_map.json` en `_download_from_gcs()` |

**Distribución de categorías después del rebuild (13/05/2026):**

```
dress:     1429 (46.8%)
accessory:  648 (21.2%)
top:        317 (10.4%)
enterito:   129  (4.2%)
lingerie:   115  (3.8%)
outerwear:  109  (3.6%)
bag:         73  (2.4%)
conjunto:    73  (2.4%)
bottom:      69  (2.3%)
shoes:       66  (2.2%)
─────────────────────────
Mapeados: 3028/3056 (99.1%)
```

### FASE 2 — Monolith API Layer ✅

**Archivos modificados:**

- `src/api/services/colbert_client.py`
- `src/api/routers/visual_search_router.py`
- `src/api/main_unified_redis.py`

**Cambios en colbert_[client.py](http://client.py):**

- `search_outfit_by_image()` — POST multipart al embedding-service
- `_auth_headers()` con `asyncio.wait_for(timeout=10s)` — evita bloqueo de 135s en primer request

**Cambios en visual_search_[router.py](http://router.py):**

- `POST /v1/mcp/visual-search/outfit` — acepta imagen + market_id + top_k + alpha
- Fix estructura anidada: el embedding-service devuelve `{"outfit": {...}}` (Pydantic); el router extrae `raw_outfit['outfit']`
- `outfit_resolving_products` log con `id_index_size` y `categories` para diagnóstico

**Cambios en main_unified_[redis.py](http://redis.py) (PASO 10.6):**

- Inicialización del colbert_client singleton + prefetch IAM token en startup
- **Resultado:** token cacheado en < 1 segundo en startup, eliminando delay de 135s en primer request

**Bugs corregidos en FASE 2:**

| Bug | Síntoma | Fix |
| --- | --- | --- |
| `outfit: {}` vacío | `raw_outfit.items()` veía `category='outfit'`, `product_ids=dict` → no es lista → skip | `if 'outfit' in raw_outfit: categories_to_resolve = raw_outfit['outfit']` |
| `_auth_headers()` bloqueado 135s | Primer request = 135.4s de latencia en instancias AUTOSCALING | `asyncio.wait_for(run_in_executor(...), timeout=10.0)` |
| Primera request siempre lenta | Singleton lazy-init + token no cacheado | PASO 10.6: prefetch token en lifespan |

### FASE 3 — Rebuild y Validación ✅

**Resultado del rebuild limpio (13/05/2026):**

```
Done: 3056 indexed, 0 skipped, 0 failed
categories: 3028/3056 mapped (99.1%)
FAISS: 9.0MB (vs 17.8MB antes del fix while loop)
elapsed: 1731s (~29 min, vs 3304s antes del fix)
```

**Tests de validación:**

```
TEST A (health):  visual_index_size=3056 ✅  category_map_size=3028 ✅  outfit_search_ready=True ✅
TEST B (monolito): HTTP 200, 2120ms → 467ms (después de texto cacheado) ✅
TEST C (embedding): HTTP 200, 1121ms → 343ms (después de texto cacheado) ✅

Productos reales encontrados:
  [dress]     Vestido Largo Leandra Gasa Rosado    — 150.000 CLP
  [enterito]  Enterito Inés Café                   — 138.990 CLP
  [top]       Crop Top Andrea Manga Globo Rosado   —  42.990 CLP
  [accessory] AROS MAXI HOJAS PLATEADO             —  10.990 CLP
```

### FASE 4 — Frontend ✅

**Archivos modificados:**

- `src/frontend/src/types/widget.ts`
- `src/frontend/src/services/api.ts`
- `src/frontend/src/components/MessageInput.tsx`
- `src/frontend/src/components/ChatWidget.tsx`
- `src/frontend/src/components/MessageList.tsx`

**Cambios:**

- Tipo `OutfitResult` y `OutfitProduct` en `widget.ts`
- `api.searchOutfitByImage()` → `POST /v1/mcp/visual-search/outfit`
- Botón 👗 "Completar outfit" en `MessageInput` (visible cuando `visualSearchEnabled=true`)
- `handleOutfitSearch()` en `ChatWidget` con `isOutfitSearching` independiente de `isVisualSearching`
- `OutfitCategoryColumn` + `OutfitPanel` en `MessageList` — scroll horizontal con columnas por categoría
- Productos clicables → navegan a `/products/{handle}` en Shopify

---

## Optimización de latencia — Text Embedding Cache ✅

**Problema:** `encode_text()` se llamaba en cada request por categoría → 9 × 150ms = 1350ms extra.

**Fix:** pre-computar los 9 prompts en `warmup()` → `self._text_embed_cache`.

**Resultado medido en producción (14/05/2026):**

```
BEFORE: ~2000ms (9 cats × 150ms texto + 400ms imagen)
AFTER:   ~355ms avg (0ms texto cacheado + ~355ms imagen)
MEJORA:  ×5.6 (5.6× más rápido)

Latencias reales (3 consultas, mercado CH):
  Búsqueda 1: embed=376ms, total=467ms  (4 categorías)
  Búsqueda 2: embed=347ms, total=415ms  (5 categorías)
  Búsqueda 3: embed=343ms, total=397ms  (7 categorías)
  PROMEDIO:   embed=355ms, total=427ms
```

---

## Problemas identificados y gaps

### 1. Shoes nunca aparece (root cause documentado) ⚠️

**Observación:** `shoes` no aparece en ninguna de las 3 búsquedas.

**Root cause:** `search_pool=40` demasiado pequeño para categorías raras.

```
shoes: 66 productos = 2.2% del catálogo
E[zapatos en pool=40] = 40 × 0.022 = 0.86 < 1 → nunca se encuentra
```

**Fix aplicado:** `search_pool: int = 40` → `search_pool: int = 150`

```
E[zapatos en pool=150] = 150 × 0.022 = 3.3 → ≥ 2 zapatos con alta probabilidad
Impacto en latencia: microsegundos (FAISS O(n·d), n=3056 es pequeño)
```

### 2. Dress/enterito dominan los resultados ⚠️

**Observación:** Con alpha=0.7, imágenes de vestidos retornan muchos vestidos en todas las categorías.

**Explicación:** Con 70% de peso de imagen y 30% de texto, el composite query sigue siendo parecido a un vestido para cualquier categoría.

**Calibración en curso:** Usuario probando alpha=0.5 (igual peso imagen/texto). A menor alpha, más influencia del texto de categoría → mayor diversidad por prenda.

**Recomendación:** alpha=0.5 para producción inicial.

### 3. Frontend mostraba max 2 productos (corregido) ✅

**Problema:** `OutfitCategoryColumn` tenía `products.slice(0, 2)` hardcoded.

**Fix:** Cambiado a `products.slice(0, 3)` para alinear con `top_k_per_category=3` del ChatWidget.

---

## Resultados de producción (14/05/2026)

**3 búsquedas exitosas, mercado CH:**

| Consulta | Categorías encontradas | Productos | Latencia total |
| --- | --- | --- | --- |
| Imagen 1 (66KB) | dress, enterito, bag, accessory | 5 | 467ms |
| Imagen 2 (53KB) | dress, enterito, top, bag, accessory | 7 | 415ms |
| Imagen 3 (282KB) | dress, enterito, top, bottom, conjunto, bag, accessory | 11 | 397ms |

**outfit_mode:** `composite_category_filtered` en todos los casos ✅  

**category_map_size:** 3028 en todos los casos ✅  

**Errores:** 0 en ambos servicios ✅

---

## Validación del Plan de Implementación

| Fase | Criterio | Estado |
| --- | --- | --- |
| FASE 1 | Tokenizador + category_map + search_outfit_by_image | ✅ Completado |
| FASE 2 | colbert_client + /v1/mcp/visual-search/outfit | ✅ Completado |
| FASE 3 | Rebuild limpio + validación con productos reales | ✅ Completado |
| FASE 4 | Frontend: botón outfit + panel categorizado | ✅ Completado |
| OPM-1 | Visual index sync job 6h | ✅ Completado y validado |
| OPM-2 | Cloud Scheduler semanal | ✅ Completado |
| OPM-3 | shopify_kb_client graphql retry | ✅ Completado |
| OPM-5 | Entry point único | ✅ Completado |
| Latencia | < 3000ms total | ✅ 427ms promedio |
| Cobertura | > 95% productos con categoría | ✅ 99.1% |

**PLAN DE IMPLEMENTACIÓN: COMPLETADO ✅**

---

## Pendientes para próximas sesiones

1. **Deploy** embedding-service con:
    - `search_pool=150` (fix shoes)
    - `text_embed_cache` (ya en producción)
2. **Deploy** frontend con:
    - `slice(0, 3)` (fix 3 productos por categoría)
    - Botón outfit 👗 visible en producción
3. **F-01 Contextual Upsell** (próxima feature planeada)
4. **Fix pendiente desde sesión anterior:** `hybrid_detector.py` — TRANSACTIONAL intent misclassificado como INFORMATIONAL cuando `matched_patterns` existe pero `rule confidence < 0.80`. Fix documentado pero no aplicado.
5. **Considerar** S2 (búsqueda de artículos similares al outfit en lugar de complementarios) si el uso de S1 lo justifica.

---

## Archivos clave modificados en esta sesión

```
src/api/services/embedding-service/
  visual_retriever.py          ← S1 completo (category_map, search_outfit, text_cache)
  main.py                      ← endpoint /v1/embed/search-outfit
  Dockerfile                   ← tokenizer pre-download fix

src/api/services/
  colbert_client.py            ← search_outfit_by_image() + auth timeout fix
  visual_index_sync_job.py     ← OPM-1

src/api/routers/
  visual_search_router.py      ← POST /v1/mcp/visual-search/outfit + nested fix

src/api/
  main_unified_redis.py        ← PASO 10.6 (IAM prefetch) + OPM-1 integration

src/frontend/src/
  types/widget.ts              ← OutfitResult, OutfitProduct, Message.outfitResult
  services/api.ts              ← searchOutfitByImage()
  components/MessageInput.tsx  ← botón 👗 + onOutfitSearch prop
  components/ChatWidget.tsx    ← handleOutfitSearch + isOutfitSearching
  components/MessageList.tsx   ← OutfitCategoryColumn + OutfitPanel

docs/0_plans/Transformers/Visual_search/Busqueda_por_Outfit_Completo/
  Plan de Implementación_12052026.md
```

---

## Deploy commands finales

```bash
# embedding-service (search_pool=150 + text_embed_cache)
cd src\api\services\embedding-service
gcloud run deploy retail-embedding-service --source . \
  --region us-central1 --project retail-recommendations-449216 \
  --memory 4Gi --cpu 2 --min-instances 1 --max-instances 1 \
  --timeout 300 --no-allow-unauthenticated --no-cpu-throttling \
  --set-env-vars VISUAL_INDEX_BUCKET=retail-recommendations-449216-visual-index
cd ..\..\..\..

# Monolito (ya tiene todos los cambios)
gcloud run deploy retail-recommender --source . \
  --region us-central1 --project retail-recommendations-449216

# Frontend — build + deploy a Shopify theme
cd src\frontend && npm run build
```

---

> **Nota técnica — Regla de diseño search_pool:**
> 

> `search_pool_min = ceil(top_k / freq_categoría_más_rara)`
> 

> Para shoes: `ceil(3 / 0.022) = 137` → usamos 150 como margen de seguridad.
> 

> Si se añaden nuevas categorías raras al catálogo, revisar esta fórmula.
>