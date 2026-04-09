# DCT — F-01: Upsell Contextual — Implementación Completada
**Fecha de cierre:** 06/04/2026  
**Estado:** ✅ Completado y validado en local  
**Versión del sistema:** Retail Recommender System v2.1.0  
**Deploy activo:** `retail-recommender-lzf2y6pspa-uc.a.run.app`

---

## 1. Resumen ejecutivo

F-01 implementa **upsell contextual basado en el producto que el usuario está viendo**. Cuando el usuario navega en una página de producto de Shopify (`/products/{handle}`) y abre el chat, el sistema enriquece automáticamente el contexto de la conversación con los metadatos del producto: título, categoría, colecciones, tags y variantes disponibles.

Este contexto se inyecta en el prompt de Claude, que puede sugerir productos complementarios de forma natural y relevante. Además, el motor TF-IDF ahora recibe el ID numérico correcto del producto para calcular similitud de contenido real, activando las recomendaciones basadas en similitud en lugar de diversificación aleatoria.

**ROI estimado según análisis estratégico (`Shopify_ROI_Strategy_2026`):**  
`+€300–900/día` de revenue incremental. Benchmark: 10–30% de visitantes en página de producto interactúan con sugerencias contextuales.

---

## 2. Qué se implementó

### 2.1 Flujo end-to-end

1. El usuario navega a `/products/vestido-corto-emma-champagne` en Shopify
2. El widget extrae el handle de la URL (`extractProductId()` en `api.ts`)
3. Cada mensaje del chat envía `widget_context.product_id = "vestido-corto-emma-champagne"`
4. El router extrae el handle de `widget_context` (no del campo raíz del body)
5. `ProductContextService` resuelve el handle → ID numérico + metadata completa
6. El contexto se inyecta en `mcp_context.current_product_context`
7. `MCPPersonalizationEngine` incluye el contexto en el prompt de Claude
8. El TF-IDF recibe el ID numérico para recomendaciones por similitud real

### 2.2 Capacidades nuevas aportadas al sistema

| Antes de F-01 | Después de F-01 |
|---|---|
| El chat no sabía qué producto miraba el usuario | El chat conoce título, categoría, colecciones y atributos del producto actual |
| TF-IDF recibía el handle como string → 0 recomendaciones por contenido | TF-IDF recibe ID numérico → 8 recomendaciones por similitud de contenido |
| Claude generaba respuestas genéricas de catálogo | Claude puede sugerir complementos contextuales ("este vestido combina con...") |
| `product_id` llegaba siempre `None` al handler | `product_id` fluye correctamente desde URL → widget → router → handler |
| Collections siempre `[]` (endpoint REST 404) | Collections resueltas via GraphQL (custom + smart) |
| Session perdida en cada recarga de página | Session persistida en `localStorage` con TTL 24h |

---

## 3. Componentes del sistema

### 3.1 Archivos nuevos creados

#### `src/api/mcp_services/product_context/service.py`
Servicio de dominio que encapsula el ciclo completo de enriquecimiento de contexto de producto.

- **Clase:** `ProductContextService(shopify_client, redis_service)`
- **Método principal:** `get_product_context(handle, market_id) → Dict | None`
- **Cache key:** `mcp:product:context:{handle}:{market_id}` — TTL 300s (5 min)
- **Degradación graceful:** cualquier fallo retorna `None`; el chat sigue funcionando sin contexto de upsell
- **Patrón:** idéntico a `CustomerProfileService` en `src/api/mcp_services/customer/service.py`
  - Usa `structlog` para logging estructurado
  - Usa `redis_service.get_json()` / `set_json()` (contrato RedisService enterprise)
  - Instanciado como singleton via `ServiceFactory`

#### `src/api/mcp_services/product_context/__init__.py`
Módulo vacío para hacer el paquete importable.

---

### 3.2 Archivos modificados

#### `src/api/integrations/shopify_client.py`
**Método añadido:** `get_product_context_by_handle(handle: str) → dict | None`

Implementa el fetch en dos pasos:

**Paso 1 — Producto por handle:**
```
GET /products.json?handle={handle}&fields=id,title,product_type,tags,vendor,variants,handle
```
Resuelve el problema fundamental: el widget entrega un handle (slug) pero el sistema necesita el ID numérico de Shopify. Este endpoint acepta ambos y retorna el producto completo.

**Paso 2 — Colecciones via GraphQL:**
```graphql
query GetProductCollections($id: ID!) {
  product(id: $id) {
    collections(first: 5) {
      nodes { title }
    }
  }
}
```
Retorna títulos directamente sin distinguir entre custom y smart collections, en una sola llamada HTTP. Usa el mismo cliente GraphQL ya establecido para `get_prices_for_products()`.

**Retorno normalizado:**
```python
{
    "id":             "9978786152757",
    "handle":         "vestido-corto-emma-champagne",
    "title":          "VESTIDO CORTO EMMA CHAMPAGNE",
    "product_type":   "VESTIDOS CORTOS",
    "tags":           ["BEIGE", "BLANCO", "CHAMPAGNE", "FIESTA", "IVORY", ...],
    "collections":    ["Vestidos cortos", "Vestidos", "Fiesta"],
    "vendor":         "NOVIAS",
    "variants_count": 4,
}
```

---

#### `src/api/factories/service_factory.py`
**Añadido:**
- Atributos de clase: `_product_context_service`, `_product_context_lock`, `_customer_profile_service`, `_customer_profile_lock`
- Método `get_product_context_service()` — double-checked locking, import en runtime para evitar circulares
- Método `get_customer_profile_service()` — resuelve el import incorrecto que tenía F-04 (apuntaba a una clase inexistente; ahora importa desde `src.api.mcp_services.customer.service`)
- Convenience functions al final del módulo

---

#### `src/api/core/mcp_conversation_handler.py`

**Bloque F-01 añadido** (después del bloque F-04, antes de Intent Detection):

```python
if validated_product_id:
    _pcs = await ServiceFactory.get_product_context_service()
    if _pcs:
        _product_ctx = await _pcs.get_product_context(
            handle=validated_product_id,
            market_id=market_id,
        )
        if _product_ctx:
            mcp_context.current_product_context = _product_ctx
```

**Fix TF-IDF product_id** (en `get_base_recommendations()`):

```python
# Resolver ID numérico desde mcp_context si está disponible
tfidf_product_id = validated_product_id  # default: handle o None
if (mcp_context and mcp_context.current_product_context
        and mcp_context.current_product_context.get("id")):
    tfidf_product_id = mcp_context.current_product_context["id"]

recommendations = await hybrid_recommender.get_recommendations(
    product_id=tfidf_product_id,  # ahora recibe "9978786152757" en lugar de "vestido-..."
    ...
)
```

---

#### `src/api/routers/mcp_router.py`

**Fix extracción de `product_id`** — el bug raíz de F-01:

```python
# Antes: solo leía conversation.product_id (campo raíz, siempre None)
validated_product_id = conversation.product_id  # ← siempre None

# Ahora: lee también de widget_context donde el widget lo envía realmente
_widget_ctx_early = conversation.widget_context or {}
_widget_product_id = (
    _widget_ctx_early.get("product_id")
    or _widget_ctx_early.get("productId")
    or None
)
validated_product_id = conversation.product_id or _widget_product_id
```

---

#### `src/api/mcp/engines/mcp_personalization_engine.py`

**Sección de upsell contextual añadida** en `_build_advanced_personalization_prompt()`:

```python
product_ctx = getattr(mcp_context, "current_product_context", None)
upsell_context_line = ""
if product_ctx:
    ctx_parts = [f"Producto actual: {product_ctx['title']}"]
    if product_ctx.get("product_type"):
        ctx_parts.append(f"Categoría: {product_ctx['product_type']}")
    if product_ctx.get("collections"):
        ctx_parts.append(f"Colección: {', '.join(product_ctx['collections'][:2])}")
    if product_ctx.get("tags"):
        ctx_parts.append(f"Atributos: {', '.join(product_ctx['tags'][:5])}")
    if product_ctx.get("variants_count", 0) > 1:
        ctx_parts.append(f"Variantes disponibles: {product_ctx['variants_count']}")
    upsell_context_line = "\n".join(ctx_parts)

if upsell_context_line:
    prompt += (
        f"\nContexto del producto que el usuario está viendo:\n{upsell_context_line}\n"
        "Si es natural en la conversación, sugiere complementos o alternativas "
        "de mayor valor de la misma colección o categoría. "
        "No menciones el upsell de forma forzada — solo si enriquece la respuesta.\n"
    )
```

---

#### `src/frontend/src/services/api.ts`

**Session persistence** (F-07 / Paso 3):

- `generateSessionId()` ahora persiste en `localStorage` con TTL 24h
- `syncSessionFromBackend()` método nuevo: actualiza `this.sessionId` Y `localStorage` con el valor canónico del servidor
- La sincronización usa `syncSessionFromBackend()` en lugar de asignación directa

---

## 4. Diagrama del flujo F-01

```
Usuario en /products/vestido-corto-emma-champagne
         │
         ▼
[Widget React] extractProductId()
  window.location.pathname → "vestido-corto-emma-champagne"
         │
         ▼
[api.ts sendMessage()] widget_context.product_id = "vestido-corto-emma-champagne"
         │  POST /v1/mcp/conversation
         ▼
[mcp_router.py]
  _widget_ctx_early = conversation.widget_context
  validated_product_id = widget_ctx.get("product_id")
  → "vestido-corto-emma-champagne"
         │
         ▼
[mcp_conversation_handler.py — Bloque F-01]
  ProductContextService.get_product_context(handle="vestido-corto-emma-champagne")
         │
    ┌────┴────────────────────────────┐
    │ Redis cache hit? (~1ms)         │ Redis cache miss (~600ms)
    │        ▼                        │        ▼
    │  retorna dict cacheado          │  ShopifyIntegration.get_product_context_by_handle()
    │                                 │    ├─ GET /products.json?handle= → id numérico
    │                                 │    └─ GraphQL collections(first:5) → títulos
    │                                 │        ▼
    │                                 │  Redis.set_json(key, context, ttl=300)
    └────────────┬────────────────────┘
                 ▼
  mcp_context.current_product_context = {
      id: "9978786152757",
      title: "VESTIDO CORTO EMMA CHAMPAGNE",
      product_type: "VESTIDOS CORTOS",
      collections: ["Vestidos cortos", "Vestidos", "Fiesta"],
      tags: ["BEIGE", "BLANCO", "CHAMPAGNE", ...],
      variants_count: 4
  }
         │
    ┌────┴─────────────────────────────────────────┐
    │ Rama 1: TF-IDF                               │ Rama 2: Prompt Claude
    │ tfidf_product_id = context["id"]             │ _build_advanced_personalization_prompt()
    │ → "9978786152757"                            │ incluye upsell_context_line:
    │ hybrid_recommender.get_recommendations()     │   "Producto actual: VESTIDO CORTO..."
    │ → 8 recomendaciones por similitud de contenido│   "Colección: Vestidos cortos, Vestidos"
    └────────────────────────────────────────────── ┘
         │
         ▼
[MCPPersonalizationEngine]
  genera respuesta con contexto de upsell
         │
         ▼
[Market Adaptation → Frontend]
  5 productos recomendados con precios en CLP
```

---

## 5. Problemas encontrados y soluciones implementadas

### Problema 1 — `product_id` nunca llegaba al handler

**Síntoma:** `validated_product_id` siempre era `None` aunque el usuario estuviera en una página de producto.

**Causa raíz:** El router leía `conversation.product_id` (campo raíz del body), pero el widget envía el handle dentro de `widget_context.product_id`. El campo raíz nunca se populaba desde el frontend.

**Solución:** Leer también `_widget_ctx_early.get("product_id")` y combinarlo con el campo raíz usando `or`. Sin cambios en el frontend.

---

### Problema 2 — Handle vs ID numérico en el TF-IDF

**Síntoma:** `WARNING: Producto ID vestido-corto-emma-champagne no encontrado` → 0 recomendaciones por contenido, fallback a diversificación aleatoria.

**Causa raíz:** El TF-IDF indexa productos por ID numérico (`9978786152757`), no por handle. El bloque F-01 ya resolvía el ID numérico, pero no se usaba para el recommender.

**Solución:** Antes de llamar al TF-IDF, leer `mcp_context.current_product_context["id"]` si está disponible y usar ese valor como `product_id`. Sin regresión: si no hay contexto, se mantiene el comportamiento anterior.

---

### Problema 3 — Endpoint de colecciones retornaba 404

**Síntoma:** `404 Client Error: Not Found for url: .../collections.json?product_id=...`

**Causa raíz:** `/collections.json?product_id=` no existe en la API 2025-01 de Shopify.

**Primera solución intentada:** `/collects.json?product_id=` + resolución de títulos via `/custom_collections/{id}.json` y `/smart_collections/{id}.json`.

**Segundo problema:** La resolución de títulos fallaba silenciosamente para smart collections — el código intentaba custom primero (404 para smart), luego smart, pero si algún paso fallaba sin log visible, `collections` quedaba `[]`.

**Solución definitiva — GraphQL:** Una sola query con variables tipadas que retorna títulos directamente sin distinguir tipo de colección. Consistente con el cliente GraphQL ya existente para precios. Resultado en logs: `Collections resolved via GraphQL product_id=...: ['Vestidos cortos', 'Vestidos', 'Fiesta']`.

**Justificación:** GraphQL es el enfoque correcto para la API 2025-01. El Admin GraphQL API no tiene restricciones en el campo `collections` del tipo `Product` — retorna todas las colecciones asignadas (custom y smart) en una sola llamada. Menos código, menos puntos de fallo, más robusto.

---

### Problema 4 — `RedisService.set()` no acepta `ex=`

**Síntoma:** `RedisService.set() got an unexpected keyword argument 'ex'`

**Causa raíz:** `RedisService` es una capa de abstracción sobre aioredis con su propio contrato: `set(key, value, ttl=None)`. El parámetro `ex=` es de la API raw de aioredis, no de `RedisService`.

**Solución:** Usar `ttl=_CACHE_TTL_SECONDS` en lugar de `ex=`. Verificado leyendo el código real de `redis_service.py`.

---

### Problema 5 — Backoff exponencial inacceptable en resolución de títulos

**Síntoma (potencial):** El código anterior usaba `_make_request_with_retry` (backoff 2s, 4s, 8s) para los fetches de títulos de colecciones. Con 5 colecciones × 2 intentos: hasta 70s de latencia en el peor caso.

**Solución:** Migración completa a GraphQL elimina este problema. Una sola query, timeout de 5s, sin retry de backoff exponencial.

---

### Problema 6 — Session no persistía entre recargas de página

**Síntoma:** Cada recarga del widget generaba un `session_id` nuevo → el backend creaba una sesión nueva vacía → la memoria multi-turno (F-07) nunca acumulaba turns entre visitas.

**Causa raíz:** `generateSessionId()` generaba un ID nuevo en cada instancia de `ConversationAPI` (cada carga de página). No había persistencia en `localStorage`.

**Solución:** `generateSessionId()` ahora lee de `localStorage` primero; genera nuevo solo si no existe o el TTL de 24h expiró. `syncSessionFromBackend()` actualiza tanto `this.sessionId` como `localStorage` con el ID canónico del servidor.

---

## 6. Validación en logs — Request de prueba

**Logs confirmados en los dos requests de validación (06/04/2026 02:44–02:46):**

```
# Request 1 (cache miss, primer fetch):
Collections resolved via GraphQL product_id=9978786152757: ['Vestidos cortos', 'Vestidos', 'Fiesta']
[get_product_context_by_handle] OK: handle='vestido-corto-emma-champagne' id=9978786152757
    type='VESTIDOS CORTOS' tags=['BEIGE', 'BLANCO', 'CHAMPAGNE'] collections=['Vestidos cortos', 'Vestidos', 'Fiesta']
product_context_cached handle=vestido-corto-emma-champagne market_id=CL ttl=300
F-01 product_context_injected handle=vestido-corto-emma-champagne product_id=9978786152757
    title='VESTIDO CORTO EMMA CHAMPAGNE' type='VESTIDOS CORTOS'
    collections=['Vestidos cortos', 'Vestidos', 'Fiesta']
F-01 TF-IDF product_id resolved: handle='vestido-corto-emma-champagne' → numeric_id='9978786152757'
Obtenidas 8 recomendaciones basadas en contenido para producto 9978786152757  ← antes era 0

# Request 2 (cache hit, Redis):
F-01 product_context_injected ... collections=['Vestidos cortos', 'Vestidos', 'Fiesta']  ← desde cache
F-01 TF-IDF product_id resolved: handle=... → numeric_id='9978786152757'
Obtenidas 8 recomendaciones basadas en contenido para producto 9978786152757
⚡ Using cached personalization - avoiding Claude API call
✅ PARALLEL MCP conversation flow completed in 4180.50ms
```

---

## 7. Métricas de rendimiento observadas

| Métrica | Request 1 (cold) | Request 2 (warm) |
|---|---|---|
| Tiempo total | 8.174s | 4.180s |
| Product context (F-01) | ~600ms cache miss | ~295ms cache hit |
| TF-IDF recommendations | 8 por similitud | 8 por similitud |
| GraphQL colecciones | ~200ms | — (cacheado) |
| Claude API | Fallback (sin créditos dev) | Cache hit (sin llamada) |
| HTTP 200 OK | ✅ | ✅ |

> **Nota:** El tiempo elevado en Request 1 se explica por `product_cache_preload_completed` — carga inicial de 8 productos (~2.2s). En producción, el PASO 4.5 en background pre-enriquece el catálogo completo, por lo que este paso es instantáneo.

---

## 8. Estructura de archivos F-01

```
src/
├── api/
│   ├── mcp_services/
│   │   └── product_context/          ← NUEVO
│   │       ├── __init__.py
│   │       └── service.py            ← ProductContextService
│   ├── integrations/
│   │   └── shopify_client.py         ← MODIFICADO: get_product_context_by_handle()
│   ├── factories/
│   │   └── service_factory.py        ← MODIFICADO: get_product_context_service()
│   ├── core/
│   │   └── mcp_conversation_handler.py  ← MODIFICADO: bloque F-01 + fix TF-IDF
│   ├── routers/
│   │   └── mcp_router.py             ← MODIFICADO: fix extracción product_id
│   └── mcp/
│       └── engines/
│           └── mcp_personalization_engine.py  ← MODIFICADO: sección upsell prompt
└── frontend/
    └── src/
        └── services/
            └── api.ts                ← MODIFICADO: session persistence localStorage
```

---

## 9. Recomendaciones y mejoras futuras

### 9.1 Corto plazo (próximo sprint)

**Compilar el widget frontend**  
Los cambios de `api.ts` (session persistence) aún no están empaquetados en `widget.umd.cjs`. Ejecutar:
```bash
cd src/frontend
npm run build:widget
```
Sin este paso, la persistencia de sesión solo existe en el código fuente, no en producción.

**Reducir latencia del primer request**  
`product_cache_preload_completed` tarda ~2.2s en el primer request de un turno. Considerar pre-cargar el caché de producto context durante el startup del servidor junto con el enrichment del catálogo, o reducir la concurrencia de `product_cache_preload`.

### 9.2 Medio plazo

**Webhook `products/update` para invalidar cache**  
Actualmente el TTL es de 5 minutos. Si un producto cambia de colección o tags en Shopify Admin, el sistema usará datos obsoletos hasta que expire. Registrar el webhook `products/update` e invocar `ProductContextService.invalidate(handle)` en el handler. Patrón ya implementado para `customers/update` (F-04).

**Mejorar prompt de upsell por LTV tier**  
Cuando F-04 (customer profile) y F-01 están activos simultáneamente, combinar ambos contextos de forma más explícita: clientes `vip` reciben sugerencias de gama alta de la colección; clientes `new` reciben complementos de precio similar. Actualmente ambos datos están en `mcp_context` pero el prompt no los cruza activamente.

**Añadir colecciones al filtro del TF-IDF**  
Con las colecciones disponibles en `current_product_context`, se puede filtrar las recomendaciones TF-IDF para priorizar productos de la misma colección (`Vestidos cortos`) antes que el catálogo general. Esto aumentaría la relevancia del upsell.

### 9.3 Largo plazo

**Métricas de conversión del upsell**  
Instrumentar un evento Prometheus `f01_upsell_shown_total` y `f01_upsell_clicked_total` para medir la tasa de interacción con recomendaciones contextuales vs. no contextuales. Permite cuantificar el ROI real de F-01.

**Activar `relatedProducts` en GraphQL (requiere Shopify Plus)**  
La API GraphQL Admin expone `product.relatedProducts` en planes Shopify Plus, que devuelve productos complementarios calculados por Shopify. Cuando el plan lo permita, este campo puede reemplazar al TF-IDF para la selección de candidatos.

---

## 10. Próximos pasos sugeridos

| Prioridad | Acción | Esfuerzo | Impacto |
|---|---|---|---|
| P0 | Compilar widget (`npm run build:widget`) | 5 min | Activa session persistence en prod |
| P0 | Deploy a Cloud Run y validar en producción real | 30 min | F-01 activo para usuarios reales |
| P1 | F-02: Asistente de talla inteligente | 1 sprint | Reducción devoluciones €1.500–2.800/mes |
| P1 | F-05: Alertas de stock bajo | 1 sprint | FOMO legítimo, +€300–500/día |
| P2 | Webhook `products/update` → invalidar cache F-01 | 2h | Datos siempre frescos |
| P2 | Métricas de conversión F-01 (Prometheus) | 4h | Cuantificar ROI real |
| P3 | Cruzar F-01 + F-04 en el prompt (LTV × colección) | 4h | Upsell más personalizado por tier |

---

## 11. Prerrequisitos y dependencias

- **No requiere** plan Shopify de pago adicional
- **No requiere** webhooks nuevos (F-01 usa la API REST + GraphQL ya autenticada)
- **No requiere** cambios en SSE/WebSocket
- **Funciona** para usuarios anónimos (sin `customer_id`)
- **Compatible** con todos los mercados activos (CL, CH, MX, ES)
- **Prerequisito cumplido** para F-02 (usa el mismo patrón de `mcp_context` enrichment)

---

*Documento generado al cierre de la sesión de implementación F-01.*  
*Sesión Notion: `331cfd3fcb2881588cfbff02aadce3a8`*  
*Referencia estratégica: `Shopify_ROI_Strategy_2026.md`*
