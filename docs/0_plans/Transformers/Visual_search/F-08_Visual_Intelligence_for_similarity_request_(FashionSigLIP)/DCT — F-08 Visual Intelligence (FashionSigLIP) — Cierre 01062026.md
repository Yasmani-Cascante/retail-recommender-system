# DCT — F-08 Visual Intelligence (FashionSigLIP) — Cierre 01/06/2026

F-08 implementado, desplegado y validado en producción (Cloud Run `retail-recommender-lzf2y6pspa-uc.a.run.app`). Las cuatro fases del plan están presentes en el codebase. Tres de ellas validadas explícitamente con logs de producción. Una (Fase C) con código correcto aplicado, sin test explícito en la sesión de cierre.

---

## Objetivo del Plan F-08

Aprovechar las capacidades de FashionSigLIP (Recall@1=100%, 3.055 productos indexados, p50=435ms) para que el flujo conversacional produzca recomendaciones **visualmente coherentes** con el producto que el usuario está viendo, siempre que se cumplan dos condiciones:

1. `product_ctx` disponible (usuario en página de producto)
2. Intent que implica similitud visual: `product_search` con patrón similar/parecido, o `outfit_completion`

---

## Fases implementadas

### Fase A — Similitud visual Turn 1 ✅ VALIDADO

**Trigger:** `use_diversification=False` (primer turn de sesión) + `_is_visual_similarity_query(query)` + `VISUAL_SEARCH_ENABLED=true` + `product_ctx.id`

**Flujo:**

1. Llamada al embedding-service `GET /v1/embed/search-by-id` (Fase A.5, ~50ms)
2. Fallback CDN si el producto no está en FAISS (~635ms)
3. Filtrado al mismo `product_type` del producto visto
4. Early-return con 8 recs visuales; fallback silencioso a TF-IDF si falla

**Evidencia en producción (01/06/2026 17:22:30):**

```
PRODUCTO:  vestido-de-fiesta-corto-cayetana-lentejuelas-bronce (VESTIDOS CORTOS)
RESULTADO: search_by_product_id: 30 results in 2.1ms
           F-08 visual_similarity: 8 productos (cat='VESTIDOS CORTOS', pool=30, filtered=17)
PRECIOS:   [86.0, 113.0, 89.0] CHF — vestidos cortos variados
LATENCIA:  2533ms total
```

**Nota sobre latencia:** 2.1ms indica producto ya en FAISS con vector warm. Primera ejecución en sesión fría fue de 47.2ms (31/05). Ambos son aceptables dentro del presupuesto de 12s.

---

### Fase A.5 — `search_by_product_id` (optimización de latencia) ✅ VALIDADO

**Qué resuelve:** Fase A original requería fetch CDN (~200ms) + encode FashionSigLIP (~435ms) = ~635ms por query. Fase A.5 reusa el vector FAISS ya almacenado del producto.

**Archivos modificados:**

- `src/api/services/embedding-service/visual_retriever.py`: método `search_by_product_id()` — usa `IndexFlatIP.reconstruct(pos)` para obtener el vector sin re-encode
- `src/api/services/embedding-service/main.py`: endpoint `GET /v1/embed/search-by-id` con response model `SearchImageResponse`
- `src/api/services/colbert_client.py`: método `search_by_product_id()` con circuit breaker y IAM auth
- `src/api/core/mcp_conversation_handler.py`: F-08 A ahora llama `search_by_product_id` como path primario; CDN fetch solo si retorna `[]` (producto no indexado aún)

**Latencias observadas:**

- Producto warm en FAISS: **2.1ms** ✅
- Primera ejecución cold (tras deploy embedding-service): **47.2ms** ✅
- CDN fallback (producto nuevo no indexado): ~635ms ✅

---

### Fase B — Outfit completion en el chat ✅ VALIDADO

**Trigger:** `sub_intent == OUTFIT_COMPLETION` + `VISUAL_SEARCH_ENABLED=true` + `product_ctx.id`

**Activa en cualquier turn** (no solo Turn 1). No depende de `use_diversification`.

**Archivos modificados:**

- `src/api/core/intent_types.py`: `OUTFIT_COMPLETION = "outfit_completion"` añadido al enum `TransactionalSubIntent`
- `src/api/core/intent_detection.py`: 7 patrones regex para outfit/complementar/combinar
- `src/api/core/mcp_conversation_handler.py`: bloque F-08 B — CDN image fetch → `search_outfit_by_image(alpha=0.5)` → interleave round-robin de categorías → early-return

**Flujo de outfit:**

1. Fetch imagen del producto desde CDN (image_url en `id_index`)
2. `POST /v1/embed/search-outfit` con `alpha=0.5` (igual peso imagen/texto)
3. `_b08_outfit.get('outfit', {})` para extraer categorías reales
4. Interleave: `[top_1, accessory_1, bag_1, top_2, ...]`
5. `outfit_category` en `product_data` para que LFM describa correctamente

**Fix aplicado en esta sesión:** `'float' object is not iterable`

- Causa: `colbert_client.search_outfit_by_image()` devuelve el dict completo `{"outfit":{...}, "latency_ms":473.0, ...}`. El código original iteraba `.items()` y llegaba a `for pid in 473.0`.
- Fix: `_b08_outfit_cats = _b08_outfit.get("outfit", {})` + `isinstance(pids, list)` guard.

**Evidencia en producción (01/06/2026 17:23:20):**

```
INTENT:    outfit_completion (confidence 0.50, rule_based)
GUARD:     ML→INFORMATIONAL @0.888 bloqueado → TRANSACTIONAL mantenido
CDN:       GET .../44.jpg → 200 OK
EMBEDDING: POST /v1/embed/search-outfit → 200 OK · latency=468ms · mode=composite_category_filtered
RESULTADO: F-08B outfit_completion: 8 productos
PRECIOS:   [10.0, 9.0, 33.0] CHF — accesorios y tops (correcto para outfit)
LATENCIA:  3717ms total
```

**Issue cosmético pendiente:** el log de éxito imprime `list(_b08_outfit.keys())` (muestra `['outfit', 'outfit_mode', 'latency_ms', ...]`) en lugar de `list(_b08_outfit_cats.keys())` (mostraría las categorías reales como `['top', 'accessory']`). No afecta funcionalidad. Corregir en próxima sesión.

---

### Fase C — Diversificación visual coherente Turn 2+ ⚠️ CÓDIGO APLICADO, NO TESTEADO

**Trigger:** `use_diversification=True` + `_is_visual_similarity_query(query)` + `product_ctx.id` + `VISUAL_SEARCH_ENABLED=true`

**Qué resuelve:** Turn 2+ actualmente usa `random.sample()` dentro de la categoría. Fase C reemplaza ese pool con los vecinos visuales más cercanos del producto visto, filtrados a la categoría deseada.

**Fix aplicado en esta sesión:** `cats=[]` (categorías vacías)

- Causa original: sample de 200 keys de `id_index` no garantizaba tener todas las categorías.
- Fix: `_c08_all_types = set(p.get('product_type') for p in all_products)` (catálogo completo) + fallback a `mcp_context.current_product_context.get('product_type')`.

**Estado:** El código está en el handler en la rama correcta. No se ejecutó en la sesión de cierre porque los dos queries de prueba usaron Turn 1 (Fase A) y outfit_completion Turn 2 (Fase B). Validación pendiente en la próxima sesión con query Turn 2+ de similitud.

---

## Bugs resueltos en esta sesión

| Bug | Causa | Fix | Validado |
| --- | --- | --- | --- |
| Imágenes ausentes en F-08 A | `image_url` no expuesto al nivel raíz del rec dict — `sanitize_rec_for_frontend` no la encontraba | `"image_url": _f08_vprod.get("image_url")` al nivel raíz | ✅ |
| `'float' object is not iterable` en F-08 B | `colbert_client` devuelve dict completo incluyendo `"latency_ms": 473.0`; iteración directa de `.items()` llegaba al float | `_b08_outfit.get("outfit", {}).items()`  • `isinstance(pids, list)` | ✅ |
| `cats=[]` en F-08 C (cross-category contamination) | Sample de 200 productos para `available_categories` incompleto; categorías no encontradas → sin filtro | `all_products` completo + fallback a `product_ctx.product_type` | Código aplicado |

---

## Archivos modificados en esta sesión

| Archivo | Cambios |
| --- | --- |
| `src/api/services/embedding-service/visual_retriever.py` | `search_by_product_id()` — reconstruct FAISS vector, sin CDN ni re-encode |
| `src/api/services/embedding-service/main.py` | `Query` import + `GET /v1/embed/search-by-id` endpoint |
| `src/api/services/colbert_client.py` | `search_by_product_id()` con circuit breaker, IAM auth, logging |
| `src/api/core/intent_types.py` | `OUTFIT_COMPLETION = "outfit_completion"` en `TransactionalSubIntent` |
| `src/api/core/intent_detection.py` | 7 patrones regex `OUTFIT_COMPLETION` (combinar, outfit, completar, complementar...) |
| `src/api/core/mcp_conversation_handler.py` | F-08 A+A.5 (Turn 1), F-08 B (outfit, any turn), F-08 C (Turn 2+); fix float; fix cats=[] |

---

## Infraestructura — estado al cierre

- **Monolith** (`retail-recommender-lzf2y6pspa-uc.a.run.app`): desplegado con todos los cambios
- **Embedding-service** (`retail-embedding-service-178362262166.us-central1.run.app`): desplegado con `search_by_product_id` + `GET /v1/embed/search-by-id`
- **Circuit breaker visual**: threshold=3, timeout=60s — funcionando correctamente (se observó apertura y cierre automático en los tests)
- **FAISS index**: 3.055 productos, 99.1% cobertura de category_map, modo `composite_category_filtered` confirmado en producción
- **Claude API warm-up**: falló por créditos insuficientes — no bloquea, sistema funciona sobre LFM (OpenRouter) como ruta primaria

---

## Gaps conocidos y deuda técnica

| Gap | Impacto | Prioridad |
| --- | --- | --- |
| F-08 C sin test explícito en producción | Bajo — código correcto, fallback a smart_fallback | Media — validar en próxima sesión |
| F-08 B log cosmético: `categories` muestra keys del dict completo | Cosmético — logs confusos para debugging | Baja |
| F-08 B muestra productos en grid plano (RECOMENDADO PARA TI), no en OutfitPanel carousel | UI/UX — el OutfitPanel ya existe en React (S1), requiere nuevo campo `outfit_result` en respuesta del router | Media — candidato para próximo sprint |
| Claude API credits | Warm-up falla en cold start — puede aumentar latencia primer request | Alta — recargar créditos |

---

## Para la próxima sesión

1. **Validar F-08 C en producción**: ejecutar una sesión con Turn 2+ con query "similares a este". Verificar log `F-08C visual_diversification: N productos (pool=50, cats=['VESTIDOS CORTOS'], candidates=M)` con `cats` ya no vacío.
2. **Corregir log F-08 B**: cambiar `list(_b08_outfit.keys())` a `list(_b08_outfit_cats.keys())` en el [logger.info](http://logger.info).
3. **Decisión sobre UI de outfit**: evaluar si usar el `OutfitPanel` existente para F-08 B requiere una nueva respuesta `outfit_result` del router — esto sería F-08 extensión.
4. **Recargar créditos Claude API**.

---

## Métricas de rendimiento en producción

| Métrica | Valor observado | Objetivo |
| --- | --- | --- |
| F-08 A Turn 1 latencia (FAISS warm) | **2.1ms** | <100ms ✅ |
| F-08 A Turn 1 latencia (FAISS cold) | **47.2ms** | <100ms ✅ |
| F-08 B outfit search latency | **468ms** / **473ms** | <1000ms ✅ |
| F-08 A total (incluyendo LFM) | **2533ms** | <5000ms ✅ |
| F-08 B total (incluyendo LFM) | **3717ms** | <5000ms ✅ |
| FAISS index coverage | **3.055 / 3.062 = 99.7%** | >95% ✅ |
| Category map coverage | **3.028 / 3.055 = 99.1%** | >95% ✅ |

*Rev: 01/06/2026 · Sistema v2.1.0*

---

## Validación final — 02/06/2026 (CIERRE DEFINITIVO)

4 turns ejecutados en una sesión limpia (0 turns previos). Cero errores, cero warnings F-08, cero fallbacks en toda la sesión.

### F-08 C — VALIDADO ✅

| Turn | Producto | cats detectados | Candidatos | Precios CHF | Latencia |
| --- | --- | --- | --- | --- | --- |
| Turn 2 | VESTIDO CORTO VICTORIA VERDE OSCURO | `['VESTIDOS CORTOS']` | 19/50 | [87, 89, 86] | 2463ms |
| Turn 3 | VESTIDO CORTO DOMINGA SATÍN VERDE | `['VESTIDOS LARGOS','VESTIDOS CORTOS','VESTIDOS MIDIS']` | 38/50 | [99, 69, 99] | 2310ms |

Turn 2: query sin categoría explícita → fallback a `product_ctx.product_type = 'VESTIDOS CORTOS'` ✅

Turn 3: query con "vestidos" (término padre) → expansión a todas las subcategorías de vestidos ✅

### Resumen final de las 4 fases

| Fase | Estado | Evidencia |
| --- | --- | --- |
| A — Visual similarity Turn 1 | ✅ VALIDADO | Mltiples sesiones. 2.0ms FAISS warm. cat='VESTIDOS CORTOS' filtered=10. |
| A.5 — search_by_product_id | ✅ VALIDADO | 1.5-2.0ms (warm), 47ms (cold). Zero 404 post-deploy. |
| B — Outfit completion | ✅ VALIDADO | outfit_completion intent, mode=composite_category_filtered, precios accesorios [36,9,19] CHF |
| C — Diversificación visual Turn 2+ | ✅ VALIDADO | cats correctos, candidatos coherentes, zero fallbacks |

**F-08 CERRADO. Todas las fases en producción y validadas.**

Deuda técnica menor restante:

- Log cosmético F-08B: cambiar `list(_b08_outfit.keys())` a `list(_b08_outfit_cats.keys())` (1 línea)
- Decisión de producto pendiente: cuando el usuario está en VESTIDOS CORTOS y pide "vestidos similares", devolver solo VESTIDOS CORTOS o todas las subcategorías de vestidos
- Claude API credits agotados (warm-up falla, no bloquea el sistema)