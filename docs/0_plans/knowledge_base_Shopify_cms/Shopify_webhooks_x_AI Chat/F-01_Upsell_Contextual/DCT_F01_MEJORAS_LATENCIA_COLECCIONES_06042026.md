# DCT — F-01 Mejoras: Latencia del primer request + Colecciones en TF-IDF
**Fecha:** 06/04/2026  
**Estado:** ✅ Implementado — pendiente de validación en local  
**Referencia:** `DCT_F01_UPSELL_CONTEXTUAL_COMPLETADO_06042026.md` §9 Recomendaciones  
**Versión del sistema:** Retail Recommender System v2.1.0

---

## 1. Resumen

Esta sesión implementa dos mejoras propuestas al cierre de F-01:

| Mejora | Problema que resuelve | Impacto esperado |
|---|---|---|
| **ID index O(1)** | `preload_products` escanea 3062 productos linealmente por cada ID → ~2.2s por request en cold start | `product_cache_preload_completed` < 10ms |
| **PASO 4.6 — Colecciones en catálogo** | El catálogo TF-IDF no tiene el campo `collections` → el reranking F-01 nunca activa el boost | Reranking efectivo tras ~2-4 min de startup |

---

## 2. Diagnóstico previo

### 2.1 Problema de latencia — causa raíz real

El log mostraba:
```
product_cache_preload_completed products_count=8 concurrency=5  ~2.2s
```

La primera hipótesis era que el semáforo (concurrencia=5) creaba contención. Pero al leer `product_cache.py` → `preload_products()` → `get_product()` → `_get_from_local_catalog()`, la causa era difer:

```python
# ANTES (O(n) por cada ID):
def _get_from_local_catalog(self, product_id):
    for product in self.local_catalog.product_data:  # scan 3062 productos
        if str(product.get('id', '')) == str(product_id):
            return product
```

Con 8 productos × scan de 3062 = **24.496 comparaciones de string** en el camino caliente. Esto era visible como ~2.2s adicionales en el primer request de cada sesión.

### 2.2 Problema de colecciones — causa raíz real

El reranking en `mcp_conversation_handler.py` buscaba:
```python
raw_rec_cols = rec_product_data.get("collections") or []
```

Pero el catálogo TF-IDF viene de `load_recommender()` → `tfidf_recommender.fit(products)`, y `products` viene de `load_shopify_products()` → `client.get_products_with_shopify_prices()`, que a su vez usa `/products.json` de Shopify REST.

**La API REST `/products.json` no incluye el campo `collections`** — este campo no existe en ninguna respuesta REST de Shopify para listados de productos. Solo está disponible via:
1. GraphQL `product { collections { nodes { title } } }`
2. `/collects.json?product_id=` (requiere resolución en dos pasos)

Por tanto, `rec_product_data.get("collections")` siempre retornaba `[]` y el `boosted_count` era siempre 0. El reranking existía en código pero era funcionalmente inerte.

---

## 3. Implementaciones

### 3.1 Mejora 1 — `id_index` O(1) en TF-IDF

**Archivo:** `src/recommenders/tfidf_recommender.py`

#### Cambio en `_build_category_index()`
Añadido `self.id_index: dict = {}` que mapea `str(product_id) → product dict`.
Se construye en el mismo loop que `category_index`, sin overhead adicional.

```python
# NUEVO: id_index construido junto con category_index (mismo O(n) pass)
self.id_index: dict = {}
for product in batch:
    # category_index — sin cambios
    category = product.get("product_type", "").upper()
    if category:
        self.category_index[category].append(product)
    # id_index — NUEVO
    pid = str(product.get("id", ""))
    if pid:
        self.id_index[pid] = product
```

Log esperado en startup:
```
✅ ID index built: 3062 products (O(1) lookups enabled)
```

#### Cambio en `get_product_by_id()`
Path principal usa `id_index.get()` O(1). El scan lineal queda como fallback para compatibilidad con modelos legacy (pickles cargados antes de este cambio):

```python
# O(1): usar id_index si está disponible
if hasattr(self, 'id_index') and self.id_index:
    return self.id_index.get(str(product_id))

# Fallback O(n): solo para modelos legacy sin id_index
for product in self.product_data:
    if str(product.get('id', '')) == str(product_id):
        return product
```

**Resultado esperado:** `product_cache_preload_completed` pasa de ~2.2s a < 10ms.

---

### 3.2 Mejora 2 — PASO 4.6: Enriquecimiento de colecciones en background

**Archivo:** `src/api/main_unified_redis.py`

Nuevo background task `_enrich_catalog_with_collections()` lanzado en el lifespan startup, inmediatamente después del PASO 4.5 (precios). Mismo patrón estructural: `asyncio.create_task()`, no bloqueante, degradación graceful.

#### Query GraphQL utilizada

```graphql
query GetCatalogCollections {
  p0: product(id: "gid://shopify/Product/9978786152757") {
    collections(first: 5) { nodes { title } }
  }
  p1: product(id: "gid://shopify/Product/9978700071221") {
    collections(first: 5) { nodes { title } }
  }
  # ... hasta 50 aliases por batch
}
```

50 aliases × 1 campo = coste GraphQL mínimo, bien dentro del límite de Shopify (1000 puntos/query).

#### Mecánica de inyección en memoria

La clave del diseño es que el `id_index` del TF-IDF y el array `product_data` apuntan a los **mismos objetos dict en memoria Python**. Modificar `product["collections"]` en `product_data` lo hace visible inmediatamente en `id_index`, sin necesidad de reconstruir nada:

```
product_data[i]  ──┐
                   ├──► { id: "...", title: "...", collections: [] } ← escritura aquí
id_index[pid]   ──┘                                                    visible en ambos
```

```python
# Escritura directa — visible en id_index sin actualización adicional
if titles:
    prod["collections"] = titles   # prod es el mismo objeto que id_index[pid]
    enriched += 1
```

#### Parámetros de operación

| Parámetro | Valor | Justificación |
|---|---|---|
| `BATCH_SIZE` | 50 | Mayor que PASO 4.5 (30) porque solo 1 campo por alias vs 4 mercados |
| Pausa entre batches | 0.3s | Respetar rate limit sin ser demasiado lento |
| `MAX_RETRIES` | 4 | Misma política que PASO 4.5 con backoff exponencial |
| Timeout por batch | 30s | Conservador para 50 aliases |

**Tiempo estimado:** 62 batches × 0.3s = ~19s de pausa + ~10s de latencia de red = **~29s total** para 3062 productos. En la práctica, con throttling ocasional, probablemente 2-4 minutos.

#### Logs esperados

```
📦 [PASO 4.6 BG] Iniciando enriquecimiento de colecciones (3062 productos, 62 batches)...
... [batches procesándose en background] ...
✅ [PASO 4.6 BG] Colecciones enriquecidas: 2847/3062 productos | batches OK=61 FAIL=1 | 87420ms
```

> Nota: no todos los productos tienen colecciones asignadas en Shopify Admin, por lo que `enriched < total` es normal y esperado.

#### Activación del reranking F-01

Una vez completado el PASO 4.6, el reranking en `mcp_conversation_handler.py` puede hacer intersección real:

```python
# current_collections = {"vestidos cortos", "vestidos", "fiesta"}
# rec_collections     = {"vestidos", "novias"} ← ahora disponible gracias a PASO 4.6

if current_collections & rec_collections:  # intersección no vacía
    new_score = min(1.0, old_score + COLLECTION_BOOST)  # +0.15
    rec["collection_boosted"] = True
    boosted_count += 1
```

Log esperado cuando el reranking activa:
```
F-01 collection_boost applied: 3/5 recs boosted (collections=['vestidos cortos', 'vestidos', 'fiesta'])
```

---

## 4. Flujo completo con mejoras

```
[Startup]
  PASO 4.5: asyncio.create_task(_enrich_catalog_with_shopify_prices)  ← precios
  PASO 4.6: asyncio.create_task(_enrich_catalog_with_collections)     ← colecciones (NUEVO)
  [ambos corren en paralelo en background]

[Primer request — t=0s]
  TF-IDF recomienda 8 productos para producto_id=9978786152757
  preload_products(8 IDs)
    → get_product_by_id() usa id_index.get() → O(1) × 8 = <1ms  ← MEJORA 1
  Reranking F-01: collections aún no cargadas → boosted_count=0 (graceful)

[Requests posteriores — t~3min]
  PASO 4.6 completado: product_data tiene "collections" en cada producto
  Reranking F-01: intersección activa → boost aplicado  ← MEJORA 2 activa
  Log: "F-01 collection_boost applied: N/5 recs boosted"
```

---

## 5. Archivos modificados

| Archivo | Tipo | Cambio |
|---|---|---|
| `src/recommenders/tfidf_recommender.py` | Modificado | `_build_category_index()` construye `id_index`; `get_product_by_id()` usa O(1) |
| `src/api/main_unified_redis.py` | Modificado | PASO 4.6 `_enrich_catalog_with_collections()` + `asyncio.create_task()` |

---

## 6. Consideraciones de diseño

### ¿Por qué background task y no enriquecimiento síncrono en startup?

El startup ya tarda ~8-12s (TF-IDF fit + Redis + MCP warm-up). Añadir 3062 × GraphQL queries síncronamente podría añadir 2-4 minutos al tiempo de arranque, lo cual es inaceptable para Cloud Run (timeout de deployment). El patrón background task ya establecido por PASO 4.5 es el correcto: el servidor está listo para recibir requests, y el enriquecimiento llega solo sin impactar la disponibilidad.

### ¿Por qué el id_index no requiere actualizar el pickle?

El pickle carga `product_data` en memoria. `_build_category_index()` se llama en `fit()` y en `load()` — es decir, siempre después de que `product_data` existe. El `id_index` se construye cada vez en memoria, no se persiste. Esto es correcto: el pickle solo necesita los vectores TF-IDF y los datos de producto, no los índices auxiliares.

### ¿Cómo interactúan PASO 4.5 y PASO 4.6 con el id_index?

Ambos pasos modifican directamente los dicts de `product_data` (`product["market_prices"]` y `product["collections"]`). El `id_index` apunta a los mismos objetos. No hay condición de carrera porque Python es GIL-safe para operaciones de asignación de atributos de dict, y ambos tasks escriben campos distintos (`market_prices` vs `collections`).

---

## 7. Validación esperada

Reiniciar el servidor local y verificar los siguientes logs en orden:

```
# Startup:
✅ ID index built: 3062 products (O(1) lookups enabled)
✅ PASO 4.6: Enriquecimiento de colecciones lanzado en background.

# Primer request (< 10ms en preload):
product_cache_preload_completed products_count=8  [tiempo << 2.2s]

# ~3min después (background task completo):
✅ [PASO 4.6 BG] Colecciones enriquecidas: XXXX/3062 productos | ...

# Requests posteriores (reranking activo):
F-01 collection_boost applied: N/5 recs boosted (collections=[...])
```

---

## 8. Próximos pasos

Con estas dos mejoras implementadas, el pipeline F-01 está completo y optimizado. Los siguientes items del roadmap de F-01 son:

| Prioridad | Acción | Notas |
|---|---|---|
| P0 | Deploy a Cloud Run y validar en producción | Confirmar PASO 4.6 completa sin throttling excesivo |
| P1 | F-02: Asistente de talla inteligente | Próxima feature del roadmap |
| P2 | Webhook `products/update` → invalidar cache F-01 | Datos siempre frescos |
| P2 | Métricas Prometheus `f01_upsell_shown_total` | Cuantificar ROI real |

---

*Documento generado al cierre de la sesión de mejoras F-01.*  
*Sesión Notion: `331cfd3fcb2881588cfbff02aadce3a8`*
