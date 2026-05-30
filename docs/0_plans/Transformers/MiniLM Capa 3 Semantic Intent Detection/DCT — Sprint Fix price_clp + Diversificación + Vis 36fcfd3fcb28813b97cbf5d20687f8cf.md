# DCT — Sprint Fix price_clp + Diversificación + Visual Search Prices — 29/05/2026

# Estado del sistema al cierre

Sesión de bugfix. Tres tareas pendientes del sprint anterior resueltas y validadas en local. Sistema estable, sin regresiones detectadas en 10 turns de prueba con 72 productos excluidos.

---

## Tarea 1 — Fix price_clp=10 en upsell F-01 ✅

### Síntoma

```
F-01 upsell tier_instruction_active=False ltv_tier=anon price_clp=10
```

El campo `ref_price_clp` para el tier de upsell leía el precio del **primer producto recomendado** (`top_recs[0]`). Tras diversificación, `top_recs[0]` podía ser un accesorio barato o un producto sin precios CL configurados en Shopify → `price_clp=10` aunque el producto visto valiera ~112 CHF (~112.000 CLP).

### Root cause

`_build_advanced_personalization_prompt()` calculaba `ref_price_clp` desde `top_recs[0]["market_prices"]["CL"]["price"]`. La fuente correcta semánticamente es el producto que el usuario **está viendo** (`product_ctx`), no el primero recomendado.

`ProductContextService` no incluye precio por diseño. El precio correcto viene de Shopify lazy-price vía `get_prices_for_products()`.

### Fix aplicado

**Patrón:** Piggybacking sobre `_enrich_recommendations_lazy()` — el producto actual se añade como holder dict `{"id": product_ctx["id"]}` al batch existente. Cero HTTP calls adicionales si ya está en Redis; si no, se batchea con los recs en el mismo GraphQL a Shopify.

**Archivos modificados:** `src/api/mcp/engines/mcp_personalization_engine.py`

**5 edits:**

1. Bloque lazy-price: añadir `_ctx_price_holder` al batch de enriquecimiento
2. Extraer `_ctx_ref_price_clp` del holder tras el enriquecimiento
3. LFM path: pasar `ctx_ref_price_clp=_ctx_ref_price_clp` a `_build_advanced_personalization_prompt()`
4. Claude path: ídem
5. `_build_advanced_personalization_prompt()`: nueva firma + lógica de prioridades

**Lógica de prioridades:**

- Prioridad 1: `ctx_ref_price_clp > 0` → precio Shopify del producto actual
- Prioridad 2: fallback a `top_recs[0]` cuando no hay `product_ctx` (homepage, search)

**Principio arquitectónico respetado:** Shopify como fuente autoritativa; conversión interna solo como fallback.

### Validación

```
# Antes:
F-01 ctx_product_price_clp=10 ...
F-01 upsell ... price_clp=10

# Después:
F-01 ctx_product_price_clp=48990 product_id=9978494124341 (fuente: Shopify lazy-price)
F-01 upsell ... price_clp=48990
F-01 ctx_product_price_clp=124000 product_id=9978758037813 (fuente: Shopify lazy-price)
F-01 upsell ... price_clp=124000
```

✅ Validado en local con múltiples productos y mercado CH.

---

## Tarea 2 — Diversificación con categorías irrelevantes ✅

### Síntoma

Turns 2+ en página de producto mostraban categorías irrelevantes (SNOWBOARD, Hydrogen eliminados del catálogo; VESTIDOS LARGOS aparecían en queries de vestidos cortos).

### Root causes (3 independientes)

**C1:** `user_events` construido desde `current_product_context.collections` incluía títulos de colecciones Shopify ("Novedades") que no matchean ningún `product_type` → `preferred_categories` tenía solo 1 categoría útil → top-up random de toda la catalog.

**C2:** Top-up en PRIORIDAD 2 rellenaba slots con `random.sample(all_available)` cuando la categoría preferida se agotaba → accesorios de 0.01 CHF.

**C3 (sesión actual):** `extract_categories_from_query` expandía el padre VESTIDOS a todos los hijos con distribución equitativa 3:3:2 aunque el usuario pidiera "vestidos cortos" explícitamente.

**C4 (sesión actual):** En queries "similares a este", el producto actual no ancla las categorías detectadas → usuario en VESTIDOS CORTOS + "vestidos similares a este" → VESTIDOS LARGOS primero.

### Fixes aplicados

**Edit A** — `mcp_conversation_handler.py`:

- Import `get_parent_categories` desde `improved_fallback_exclude_seen`
- Expansión con categorías hermanas: cuando `product_type='VESTIDOS CORTOS'`, añadir eventos para `VESTIDOS LARGOS` y `VESTIDOS MIDIS` con `source='parent_category_expansion'`

**Edit B** — `improved_fallback_exclude_seen.py` (top-up afinado):

- Top-up PRIORIDAD 2: primero buscar en `preferred_remaining` (productos de las mismas categorías preferidas); solo ir broad si esas se agotan

**Edit C** — `improved_fallback_exclude_seen.py` (realizado manualmente por Yasmani):

- Eliminar `SNOWBOARD` de `CATEGORY_KEYWORDS`

**Change 1** — `extract_categories_from_query`: post-filter tras la detección. Cuando una subcategoría concreta es detectada con `specificity > 0.5` (keyword de 2+ palabras), suprimir las hermanas añadidas solo por expansión del padre (`specificity = 0.5`). Ejemplo: "vestidos cortos" → solo VESTIDOS CORTOS, no incluir VESTIDOS LARGOS.

**Change 2** — `get_personalized_fallback` PRIORIDAD 1: anclar al producto actual en queries con patrón `similar(?:es)?\s+a\s+(?:este|esta)`. Si `user_events` tiene categorías primarias (`source='current_product_context'`) presentes en `query_categories`, reducir `query_categories` a esas categorías.

**Archivos modificados:** `src/api/core/mcp_conversation_handler.py`, `src/recommenders/improved_fallback_exclude_seen.py`

### Validación (10 turns, 72 productos excluidos)

| Turn | Query | Categorías resultado | Fix |
| --- | --- | --- | --- |
| 2 | "Muéstrame productos similares" (en VESTIDOS LARGOS) | PRIORIDAD 2 → VESTIDOS LARGOS | Sin cambio ✅ |
| 3 | "Recoméndame similares a este" (en VESTIDOS LARGOS) | PRIORIDAD 2 → VESTIDOS LARGOS | Sin cambio ✅ |
| 8 | "Muestrame vestidos cortos" | `['VESTIDOS CORTOS']` 8:0:0 | Change 1 ✅ |
| 9 | "Recoméndame similares a este" (en VESTIDOS CORTOS) | PRIORIDAD 2 → VESTIDOS CORTOS | Sin cambio ✅ |
| 10 | "Muestrame vestidos **largos** similares a este" (en VESTIDOS CORTOS) | `['VESTIDOS LARGOS']` 8:0:0 | Change 1 filtra; Change 2 no ancla (correcto) ✅ |

### Nota: SNOWBOARD y Hydrogen

Ambas categorías fueron eliminadas del catálogo Shopify por Yasmani. SNOWBOARD también eliminado de `CATEGORY_KEYWORDS`. Hydrogen era product_type de productos de test, no una categoría en el dict.

---

## Tarea 3 — Fix precios en Visual Search ✅

### Síntoma

`/v1/mcp/visual-search` devolvía precios con símbolo `€` y valores CLP (ej. `74,990.00 €`) en mercado CH. El endpoint recibía `market_id` pero lo ignoraba completamente.

### Root cause

El endpoint resolvía productos desde `tfidf_rec.id_index` (precios CLP) y los pasaba directamente a `sanitize_rec_for_frontend`. Esta función usa `currency or "EUR"` como fallback → símbolo `€` con valor CLP.

### Fix aplicado

**Mismo patrón de 3 fases que `/v1/mcp/visual-search/outfit`** (implementado sesión anterior):

- Fase 1: Redis lookup (`price:{pid}`) — cache compartida con `/outfit` y lazy-price (~1ms hit)
- Fase 2: `get_prices_for_products()` para cache misses (httpx warm pool, timeout 5s)
- Fase 3: Resolver con precio de mercado correcto inyectado en el dict antes de `sanitize_rec_for_frontend`

**Jerarquía de precios:**

1. `market_prices` pre-computado en catálogo
2. Redis cache
3. Shopify directo (Fase 2)
4. `_VS_CLP_RATES` fallback (conversión interna)

**Archivo modificado:** `src/api/routers/visual_search_router.py`

**Logs esperados tras próximo deploy:**

```
visual_search_prices_from_shopify products=8 market_id=CH cached_in_redis=true
"price": 66.75, "currency": "CHF"  # no más 74,990.00 €
```

---

## Análisis técnico: Similitud entre productos

### Estado actual por turn

| Turn | Mecanismo | Similitud textual | Similitud visual |
| --- | --- | --- | --- |
| Turn 1 | TF-IDF cosine (title + desc + tags + category) | ✅ | ❌ |
| Turn 2+ (diversificación) | `random.sample()` dentro de la categoría | ❌ | ❌ |
| `/v1/mcp/visual-search` | FashionSigLIP + FAISS | ❌ | ✅ (solo si usuario sube foto) |

**Gap crítico:** A partir del Turn 2, no existe ningún mecanismo de similitud. Los productos recomendados son aleatorios dentro de la categoría elegida.

### Oportunidad F-08 (conceptual, no en scope)

**Propuesta:** Usar FashionSigLIP para hacer Turn 2+ similarity-aware.

```
Flujo propuesto (Turn 2+):
  product_ctx.id → image_url (from id_index, O(1))
       ↓ async fetch CDN ~200ms
  image_bytes → colbert.search_by_image(top_k=50)
       ↓
  visual_ids ∩ desired_categories → recomendaciones
       ↓ fallback si visual search falla
  random.sample() (comportamiento actual)
```

**Responde a la pregunta:** ¿Puede el sistema recomendar vestidos largos similares a un vestido corto? → Con F-08: sí, usando embeddings visuales cross-categoría (FashionSigLIP captura estilo, paleta, ocasión independientemente de la categoría Shopify).

**Latencia añadida estimada:** 350-700ms paralelizable con product_ctx fetch.

**Prerequisito:** El FAISS index debe tener cobertura suficiente del catálogo (indexación incremental en curso).

---

## Estado de deuda técnica

| Item | Estado | Prioridad |
| --- | --- | --- |
| Validación completa MiniLM capa 3 (post HuggingFace token fix) | Pendiente | Media |
| Test F-05 stock alerts con fixes aplicados | Pendiente | Media |
| Visual Search pricing — validar en producción tras deploy | Pendiente próximo deploy | Alta |
| F-08 visual similarity en diversificación | Conceptual, no planificado | Baja |

---

## Archivos modificados en esta sesión

| Archivo | Cambios |
| --- | --- |
| `src/api/mcp/engines/mcp_personalization_engine.py` | 5 edits: ctx_price_holder piggybacking, ctx_ref_price_clp, firma y lógica de _build_advanced_personalization_prompt |
| `src/api/core/mcp_conversation_handler.py` | Import get_parent_categories, expansión de user_events con categorías hermanas |
| `src/recommenders/improved_fallback_exclude_seen.py` | Top-up afinado PRIORIDAD 2, post-filter en extract_categories_from_query, anchor en PRIORIDAD 1 |
| `src/api/routers/visual_search_router.py` | Market price resolution (3 fases) para /v1/mcp/visual-search |

---

## Para la próxima sesión

Deploy a Cloud Run (retail-recommendations-449216) con los cambios de esta sesión. Validar en producción:

1. `visual_search_prices_from_shopify` en logs GCP
2. `price_clp` correcto en el log de F-01 upsell
3. Price sample de turns 2+ sin valores < 10 CHF

*Rev: 00196-29d → 00197-29e*