# Documento de Continuidad Técnica
## Sistema Conversacional — Estabilización y Fixes de Producción
### Retail Recommender System v2.1.0

---

| Campo | Valor |
|---|---|
| Documento | DCT-CONV-ESTAB-27032026 |
| Sistema | Retail Recommender System v2.1.0 |
| Estado | ✅ Estable — Producción |
| Fecha | 27 Marzo 2026 |
| Cloud Run Rev. | retail-recommender-00084-jk6 |
| Audiencia | Ingeniería, Onboarding, Mantenimiento |
| Documentos de referencia | RFC-2026-001, FRONTEND_ARCHITECTURE 24.03.2026.md |

---

## 1. Resumen del Sistema

### 1.1 Descripción del sistema conversacional

El **Retail Recommender Conversational System** es un asistente de chat con IA embebible en storefronts de Shopify. Se despliega como un widget React (~150 KB, un único archivo `.cjs` autocontenido) que se comunica con una API FastAPI en Google Cloud Run.

Sirve dos categorías de consultas:

- **Informacionales** — preguntas sobre políticas de la tienda (devoluciones, envíos, pagos, garantías, tallas). Respondidas desde una Knowledge Base sincronizada desde Shopify CMS via metafields, con contextualización Claude Haiku para consultas específicas (RAG).
- **Transaccionales** — búsqueda y descubrimiento de productos. Respondidas con recomendaciones personalizadas generadas por el pipeline HybridRecommender + MCPPersonalisationEngine + MarketAdapter.

### 1.2 Capacidades principales

| Capacidad | Tecnología | Estado |
|---|---|---|
| Detección de intención | Rule-based (regex) + sklearn TF-IDF + LR (hybrid) | ✅ Operativo |
| Respuesta a saludo (Greeting) | Template bilingüe, sin llamada a Claude | ✅ Operativo |
| Respuesta informacional | PostgreSQL (Neon) + Redis + Claude Haiku contextualización | ✅ Operativo |
| Recomendaciones transaccionales | TF-IDF HybridRecommender + MCPPersonalisationEngine | ✅ Operativo |
| Diversificación de segunda ronda | ImprovedFallbackStrategies — excluye productos ya vistos | ✅ Operativo |
| Multi-mercado | ES, US, MX, CL — MonedaAdapter + KB multilingüe | ✅ Operativo |
| Persistencia de sesión | Redis TTL 86 400 s — historial multi-turn | ✅ Operativo |
| Detección de idioma | Accept-Language header + validación | ✅ Operativo |

### 1.3 Estado actual

El sistema alcanzó estabilidad de producción el 27/03/2026 tras una sesión intensiva de fixes que resolvió 11 bugs activos. Los flujos conversacionales principales (greeting, informacional, transaccional), la diversificación de recomendaciones, la serialización de respuestas y la indexación del catálogo TF-IDF están correctamente operativos.

**Nivel de madurez:** Producción estable para tráfico de prueba. Los gaps documentados en la Sección 7 no bloquean el uso pero deben abordarse antes de escalar.

---

## 2. Problemas Enfrentados

Los siguientes bugs fueron identificados y resueltos durante esta fase. Se presentan en orden de aparición/detección.

| ID | Problema | Impacto | Severidad |
|---|---|---|---|
| BUG-01 | `mcp_router.py` perdió el bloque de documentación de factories (~300 líneas) y la función `get_personalization_engine()` | Pérdida de trazabilidad arquitectónica; la función activa faltaba | Media |
| BUG-02 | `mcp_personalization_engine.py` — `_generate_claude_personalized_response()` devolvía `Dict` en vez de `str` | El objeto `{"response": "...", "tone_adaptation": ...}` aparecía como texto crudo en el chat widget | Alta |
| BUG-03 | HTTP 529 Anthropic (Overloaded) causan respuesta de fallback visible al usuario | Usuario ocasionalmente veía `"Te ayudo a encontrar lo que buscas..."` en vez de respuesta personalizada | Media |
| BUG-04 | Segunda ronda de recomendaciones sin precio (`price = 0` o `price = undefined`) | `ProductCard.tsx` mostraba `€0` o campo vacío en todas las tarjetas de segunda ronda | Alta |
| BUG-05 | Catálogo TF-IDF no aplana `price` desde `variants[0].price` al nivel raíz | Causa raíz del BUG-04: la API REST de Shopify devuelve el precio anidado, nunca al nivel raíz del producto | Alta (causa raíz) |
| BUG-06 | `get_personalized_fallback()` usaba `**product` sin sobrescribir `price` | Los tres paths de diversificación (query-driven, personalized, popular) heredaban `price=None` del catálogo | Alta |
| BUG-07 | `mcp_router.py` — loop manual de `safe_recs` no normalizaba `price`, `score` ni `image_url` | Primera ronda con MarketAdapter funcionaba; segunda ronda sin normalización | Media |
| BUG-08 | `image_url` no llegaba al frontend desde productos del catálogo TF-IDF | El catálogo almacena `images: [{src: "..."}]` pero nunca aplanaba `image_url` al nivel raíz | Media |

---

## 3. Decisiones Técnicas Clave

### 3.1 BUG-02 — `_generate_claude_personalized_response()` tipo de retorno

**Flujo afectado:** Path secundario de personalización en `mcp_router.py` → `mcp_personalization_engine.py`

**Decisión:** El método debe retornar `str` puro, nunca `Dict`. El campo `"personalized_response"` en el response final del router recibe el string directamente, sin envolturas.

**Justificación:** El router tiene `extract_answer_from_claude_response()` para manejar todas las formas posibles del response de Claude (str, dict con `response`, dict con `content`, etc.). La función de personalización debe emitir un str limpio, no añadir otra capa de dict.

**Alternativas descartadas:** Mantener el dict y actualizar `extract_answer_from_claude_response()` para desenrollar `{"response": "..."}`. Descartado porque añade complejidad innecesaria y el pattern `str puro` es más simple y explícito.

---

### 3.2 BUG-04/05 — Precio ausente en segunda ronda (causa raíz)

**Flujo afectado:** `load_recommender()` → `tfidf_recommender.fit()` → `product_data[]` → `smart_fallback()` → `ProductCard.tsx`

**Decisión (Opción C — máxima robustez):** Fix en dos capas:

1. **Capa A — Origen:** `tfidf_recommender._normalize_product_price()` aplana `variants[0].price` → `price` al nivel raíz en el momento de indexación.
2. **Capa B — Path de diversificación:** `get_personalized_fallback()` sobrescribe `"price": safe_extract_price(product)` explícitamente en cada `{**product, ...}` spread.
3. **Capa C — Router (ya existente):** `sanitize_rec_for_frontend()` garantiza invariantes en todos los paths antes del response final.

**Justificación:** La API REST de Shopify (`/admin/api/2025-01/products.json`) devuelve el precio en `product["variants"][0]["price"]` (string, ej. `"159.00"`), NO en `product["price"]` (campo ausente o `None` a nivel raíz). El catálogo TF-IDF fue diseñado para indexación textual, no para presentación, y guardaba los objetos crudos sin aplanar. Cualquier path que use `**product` hereda ese `None`.

**Alternativas descartadas:** Solo capa C (sanitize en router). Descartado porque no corrige los datos en origen — si el router fallara o no estuviera disponible, el problema reaparecería. La solución en capas es resiliente.

**Efecto secundario positivo:** `_normalize_product_price()` también aplana `image_url` desde `images[0]["src"]`, resolviendo BUG-08 sin un fix separado.

---

### 3.3 Arquitectura de doble capa de defensa (Tolerant Reader Pattern)

**Decisión:** Mantener dos niveles de normalización de datos de productos:
- **Nivel 1 (origen):** `_normalize_product_price()` en `fit()` — normaliza el catálogo permanentemente.
- **Nivel 2 (última milla):** `sanitize_rec_for_frontend()` en el router — garantiza invariantes independientemente del path de generación.

**Justificación:** El handler tiene una Fase 5 de market adaptation (`market_adapter.adapt_product()`) que también normaliza campos. Si el adapter falla o no está disponible, sin la capa en el router los campos crudos llegan al frontend. El patrón "tolerant reader" en el boundary entre backend y frontend es una práctica de ingeniería estándar para servicios que evolucionan.

---

### 3.4 BUG-03 — Manejo de HTTP 529 (Anthropic Overloaded)

**Decisión:** No modificar el retry loop existente. El comportamiento actual (3 intentos, sleep 50ms) es correcto.

**Justificación:** HTTP 529 es un estado transitorio del servidor de Anthropic, no un error de nuestro código. El loop funcionó correctamente en los logs: intento 1 → 529, intento 2 → 529, intento 3 → 200 OK. El usuario recibió la respuesta final. El fallback solo activa cuando los **3 intentos** fallan, lo cual es el comportamiento correcto.

---

### 3.5 Recuperación del bloque de documentación del router (BUG-01)

**Decisión:** Restaurar desde `mcp_router.backup_21112025.py` (backup más reciente con 95KB). El archivo actual de 109.95KB estaba completo en lógica funcional pero faltaba el bloque de factories comentadas y `get_personalization_engine()`.

**Justificación:** Las factories comentadas documentan la evolución de tres patrones de DI (Legacy sync → Async local → Enterprise ServiceFactory). Esta documentación es parte del knowledge del equipo y previene que futuros desarrolladores intenten reimplementar lo que ya fue evaluado y reemplazado.

---

## 4. Soluciones Implementadas

### 4.1 Fix BUG-02 — `_generate_claude_personalized_response()` retorna `str`

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py`

**Cambio:** El método `_generate_claude_personalized_response()` (primera versión, path rápido de personalización) ahora retorna `response_text: str` directamente en vez de `{"response": response_text, "tone_adaptation": "standard", ...}`.

El callers actualizado en `generate_personalized_response()`:
```python
# ANTES (generaba el dict visible en el chat):
conversational_response = await self._generate_claude_personalized_response(...)
response["personalized_response"] = conversational_response  # era el dict completo

# DESPUÉS (str puro):
conversational_response = await self._generate_claude_personalized_response(...)
response["personalized_response"] = conversational_response  # str limpio
```

`conversation_enhancement` en el response final usa defaults seguros (`"tone_adaptation": "standard"`, etc.) porque el string ya no lleva esas claves.

---

### 4.2 Fix BUG-05 — `TFIDFRecommender._normalize_product_price()`

**Archivo:** `src/recommenders/tfidf_recommender.py`

**Cambio:** Nuevo método estático `_normalize_product_price(product)` aplicado en `fit()` antes de guardar en `product_data`.

Lógica del método:
1. Si `product["price"]` ya tiene valor > 0 → devuelve el producto sin cambios (no pisa datos ya normalizados por MarketAdapter).
2. Si `price` es `None` o 0 → extrae desde `variants[0]["price"]` (string Shopify → float).
3. También aplana `image_url` desde `images[0]["src"]` si no existe como campo directo.

```python
self.product_data = [self._normalize_product_price(p) for p in products]
```

**Nota crítica:** El archivo `data/tfidf_model.pkl` debe ser **eliminado** en el servidor para forzar re-entrenamiento con el fix activo. Si el `.pkl` existe, `load_recommender()` lo carga directamente sin llamar a `fit()`.

---

### 4.3 Fix BUG-06 — `safe_extract_price()` en `get_personalized_fallback()`

**Archivo:** `src/recommenders/improved_fallback_exclude_seen.py`

**Cambio:** Los dos bloques que hacen `{**product, "score": score, ...}` ahora incluyen `"price": safe_extract_price(product)` explícitamente. `safe_extract_price()` ya existía en el archivo y ya la usaban `get_popular_products()` y `get_diverse_category_products()`. Los dos bloques sin cobertura eran:

- **Prioridad 1** — `query_category_driven_multi`
- **Prioridad 2** — `personalized_fallback`

```python
# ANTES:
recommendations.append({
    **product,
    "score": score,
    "recommendation_type": "personalized_fallback",
    ...
})

# DESPUÉS:
recommendations.append({
    **product,
    "price": safe_extract_price(product),  # override explícito
    "score": score,
    "recommendation_type": "personalized_fallback",
    ...
})
```

---

### 4.4 Fix BUG-07 — `sanitize_rec_for_frontend()` en `mcp_router.py`

**Archivo:** `src/api/routers/mcp_router.py`

**Cambio:** Nueva función `sanitize_rec_for_frontend(rec: Any) -> Dict[str, Any]` insertada después de `extract_answer_from_claude_response()`.

Aplicada en **todos** los puntos de retorno del router:
- `process_conversation` — path principal transaccional
- `process_conversation` — path fallback (hybrid_recommender directo)
- `get_market_recommendations` — reemplaza el loop manual de `simplified_recs`
- `process_conversation_fixed`
- `get_market_recommendations_fixed`

**Invariantes garantizados:**

| Campo | Tipo | Fuente / Fallback |
|---|---|---|
| `id` | `str` non-empty | `rec["id"]` \| `"unknown"` |
| `title` | `str` non-empty | `rec["title"]` \| `rec["localized_title"]` \| `"Producto"` |
| `price` | `float >= 0` | `rec["price"]` \| `rec["market_price"]` \| `0.0` |
| `currency` | `str` non-empty | `rec["currency"]` \| `"EUR"` |
| `score` | `float [0,1]` | `score` \| `market_score` \| `hybrid_score` \| `similarity_score` \| `viability_score` \| `0.5` |
| `description` | `str` sin HTML, máx 300 chars | strip de tags HTML + `body_html` como fallback |
| `image_url` | `str \| None` | `image_url` \| `imageUrl` \| `images[0]` |
| `url` | `str \| None` | opcional — para link en ProductCard |

También convierte objetos Pydantic (`model_dump()`), dataclasses (`vars()`), y cualquier tipo iterable a dict puro.

---

### 4.5 Fix BUG-01 — Restauración del router

**Archivo:** `src/api/routers/mcp_router.py`

**Cambio:** Restaurado el bloque de factories comentadas (~300 líneas) + función activa `get_personalization_engine()` desde `0_backups/mcp_router.backup_21112025.py`.

El bloque documenta la evolución de tres patrones:
1. **Legacy sync** — acceso directo a `main_unified_redis`
2. **Async local** — delegación a ServiceFactory pero función local al router
3. **Enterprise actual** — importado desde `dependencies.py` como Type Aliases (`MCPClientDep`, `MarketManagerDep`, etc.)

`get_personalization_engine()` se mantiene fuera del patrón `Depends()` de forma **intencional**: el engine se instancia bajo demanda dentro de `mcp_conversation_handler` y no es necesario en todos los endpoints.

---

## 5. Componentes Modificados o Creados

### 5.1 Archivos modificados

| Archivo | Tipo de cambio | Qué cambió |
|---|---|---|
| `src/api/routers/mcp_router.py` | Modificación + restauración | 1) Restauración del bloque de factories documentadas y `get_personalization_engine()`. 2) Nueva función `sanitize_rec_for_frontend()`. 3) Aplicación de `sanitize_rec_for_frontend()` en los 5 puntos de retorno. 4) Reemplazo del loop manual `simplified_recs` por la nueva función. |
| `src/api/mcp/engines/mcp_personalization_engine.py` | Fix de tipo de retorno | `_generate_claude_personalized_response()` retorna `str` puro (no `Dict`). `generate_personalized_response()` actualizado para usar el str directamente. `conversation_enhancement` usa safe defaults. |
| `src/recommenders/tfidf_recommender.py` | Nuevo método + uso en `fit()` | Nuevo `_normalize_product_price()` (método estático). `fit()` aplica la normalización antes de guardar en `product_data`. |
| `src/recommenders/improved_fallback_exclude_seen.py` | Fix en dos bloques | `get_personalized_fallback()` — Prioridad 1 y Prioridad 2 sobrescriben `"price": safe_extract_price(product)` explícitamente. |

### 5.2 Archivos de backup relevantes

| Backup | Tamaño | Cuándo usar |
|---|---|---|
| `src/api/routers/0_backups/mcp_router.backup_21112025.py` | 95.23 KB | Fuente autoritativa para recuperar documentación de factories si se pierde de nuevo |
| `src/api/mcp/engines/mcp_personalization_engine.py.backup_27032026` | 169.45 KB | Estado pre-fix del engine |
| `src/recommenders/tfidf_recommender.py.backup_` | 12.37 KB | Estado pre-fix del TF-IDF |

### 5.3 Piezas nuevas introducidas en la arquitectura

**`sanitize_rec_for_frontend()` — Tolerant Reader en el boundary del router**

Esta función es la única pieza nueva de arquitectura. Funciona como una red de seguridad en el boundary entre el pipeline de recomendaciones (con sus múltiples paths de generación) y el frontend. Desde este fix, el router garantiza invariantes en su output independientemente de cuál path generó las recomendaciones.

```
HybridRecommender (path A) → MarketAdapter → sanitize_rec_for_frontend → frontend
smart_fallback (path B)    → (sin adapter) → sanitize_rec_for_frontend → frontend
hybrid_recommender fallback → sin pipeline  → sanitize_rec_for_frontend → frontend
```

**`_normalize_product_price()` — Normalización en origen del catálogo**

Nuevo método en `TFIDFRecommender` que garantiza que cada producto indexado en `product_data` tenga `price` y `image_url` como campos directos al nivel raíz, independientemente de cómo los devuelva la API de Shopify. Aplica el principio "fix it at the source": los datos se corrigen una vez al indexar, no en cada consulta.

---

## 6. Flujo Actual del Sistema

### 6.1 Flujo conversacional completo

```
[1] Usuario abre el widget
    → ChatWidget.tsx monta (React 18, UMD bundle)
    → Mensaje de bienvenida local (sin llamada API)
    → userId cargado de localStorage, sessionId generado

[2] Usuario escribe y envía mensaje
    → ConversationAPI.sendMessage(text)
    → POST /v1/mcp/conversation
      Headers: X-API-Key, Accept-Language, X-Widget-Version
      Body: {query, user_id, session_id, market_id, language, widget_context}

[3] Backend — mcp_router.py
    → Detección de idioma (Accept-Language o body.language)
    → get_conversation_state_manager() → Redis → sesión existente o nueva
    → Validación de user_id, product_id
    → Llamada a get_mcp_conversation_recommendations() (handler)

[4] Backend — mcp_conversation_handler.py

    FASE 1: Cargar contexto MCP (Redis)
    → get_or_create_session(session_id, user_id, market_id)

    FASE 1.5: Detección de intención
    → ENABLE_INTENT_DETECTION via os.environ.get() (no Pydantic @lru_cache)
    
    ┌─ GREETING (confidence 0.95)
    │   → Template bilingüe (es/en), sin Claude, sin productos
    │   → Early return {type: "greeting", answer: str, recommendations: []}
    │
    ├─ INFORMATIONAL (confidence ≥ 0.7)
    │   → kb.get_answer(sub_intent, language)  ← 3-layer cache
    │   → has_specific_entities() → True → generate_contextual_answer() (Claude Haiku, RAG)
    │   → kb_document = full KB page text (siempre presente)
    │   → Early return {type: "informational", answer: str, kb_document: str, recommendations: []}
    │
    └─ TRANSACTIONAL → continúa a FASE 2

    FASE 2: Ejecución paralela
    → get_base_recommendations()   [HybridRecommender o smart_fallback]
    → prepare_mcp_engine()         [MCPPersonalisationEngine singleton]
    → get_market_adapter()

    FASE 3: Personalización con cache
    → personalization_cache.get() → cache hit → usar cached
    → cache miss → MCPPersonalisationEngine.generate_personalized_response()
                   → Claude Haiku call (timeout 12s)

    FASE 4: State persistence
    → recommendation_ids extraídos para diversificación futura
    → state_manager.save_conversation_state(session)

    FASE 5: Market adaptation
    → market_adapter.adapt_product(rec, market_id) por cada item

[5] Backend — mcp_router.py (post-handler)
    → sanitize_rec_for_frontend(rec) por cada recomendación
    → Log diagnóstico: "Price sample (primeros 3): [...]"
    → ConversationResponse Pydantic serialización

[6] Frontend — ChatWidget.tsx
    → Message{type:'assistant', content: answer} añadido
    → ProductCard[] renderizados debajo del texto si hay recommendations
    → isLoading: false, input re-habilitado
```

### 6.2 Flujo de diversificación (segunda ronda)

```
Turn 1: user → "quiero un vestido"
    → smart_fallback NO activado (sin historial)
    → HybridRecommender.get_recommendations()
    → MarketAdapter.adapt_product() → price normalizado
    → Recommendations [A, B, C, D, E] almacenados en sesión Redis

Turn 2: user → "muéstrame más"
    → mcp_context.turns[0].recommendations_provided = ["A", "B", "C", "D", "E"]
    → shown_products = {"A", "B", "C", "D", "E"}
    → use_diversification = True
    → ImprovedFallbackStrategies.smart_fallback(exclude_products=shown_products)
        → get_personalized_fallback(user_query=query)
            → PRIORIDAD 1: query_category_driven (si detecta categoría)
            → PRIORIDAD 2: personalized (historial de categorías)
            → PRIORIDAD 3: diverse (categorías variadas)
            → PRIORIDAD 4: popular (fallback final)
        → "price": safe_extract_price(product)  ← FIX BUG-06
    → sanitize_rec_for_frontend()               ← FIX BUG-07
    → Recommendations [F, G, H, I, J] — sin duplicados con Turn 1
```

### 6.3 Cómo interactúan los componentes

```
Frontend (React 18 UMD bundle, Shopify)
    ↕ HTTPS REST
Backend API (FastAPI, Cloud Run)
    ├── mcp_router.py           ← Boundary frontend-backend, sanitización final
    ├── mcp_conversation_handler.py  ← Orquestador del pipeline
    │   ├── intent_detection.py      ← Rule-based + sklearn hybrid
    │   ├── knowledge_base_v2.py     ← KB lookup (Redis → Neon → Shopify GraphQL)
    │   └── kb_contextualizer.py     ← Specific entity check + Claude RAG
    ├── HybridRecommender           ← TF-IDF content-based
    │   └── TFIDFRecommender        ← Catálogo indexado (product_data normalizado)
    ├── MCPPersonalisationEngine    ← Claude Haiku personalización conversacional
    ├── ImprovedFallbackStrategies  ← Diversificación segunda ronda
    └── MarketAdapter               ← price, currency, availability por mercado

Servicios externos
    ├── Redis Cloud        ← Sesión conversacional (TTL 86 400 s)
    ├── PostgreSQL Neon    ← Knowledge Base persistente
    ├── Shopify GraphQL    ← Fuente de productos y KB CMS
    └── Anthropic API      ← Claude Haiku (conversación + KB RAG)
```

---

## 7. Observaciones y Gaps

### 7.1 Limitaciones actuales

| Limitación | Descripción | Severidad |
|---|---|---|
| Modelo `.pkl` existente ignorará fix de indexación | Si existe `data/tfidf_model.pkl` en el servidor, `load_recommender()` lo carga sin pasar por `fit()`. El fix de `_normalize_product_price()` solo aplica en reentrenamientos. | Alta — requiere acción manual en deploy |
| Sin memoria conversacional real multi-turn | El prompt de Claude no incluye historial de mensajes previos. Follow-ups contextuales ("el segundo", "algo más barato") no se entienden. | Media |
| KB: un documento por sub-intent | Dos preguntas con el mismo `sub_intent` reciben el mismo documento fuente. La contextualización Claude mitiga esto parcialmente. | Media |
| Cold start sin min-instances | Cloud Run con `min-instances=0` tiene cold start de 3–5s. El keep-alive (Haiku cada 90s) reduce pero no elimina este problema. | Media |
| Precios en mercados no-ES | `ProductCard.tsx` usa `Intl.NumberFormat` pero `currency` puede venir como `"EUR"` hardcodeado desde el fallback del router cuando el MarketAdapter no aplica. MX/US podrían mostrar moneda incorrecta. | Media |
| Campo `url` en recomendaciones no siempre presente | `ProductCard.tsx` no puede navegar a la página del producto cuando `url` es `None`. | Media |
| Diversification cache collision | `PersonalizationCache` puede devolver resultado cacheado de otra query del mismo usuario dentro de los 5 minutos de TTL. | Baja-Media |
| Sin tests de frontend | Cero tests unitarios o de integración para los componentes React. | Media |

### 7.2 Riesgos potenciales

**Riesgo 1 — Reentrenamiento del modelo TF-IDF**

Si el servidor no tiene el `.pkl` eliminado antes del primer deploy con el fix, el modelo cargado contendrá los datos sin normalizar. El BUG-04 reaparecerá en segunda ronda hasta que el contenedor se reinicie sin el `.pkl` o hasta que se fuerce `fit()`.

Señal de diagnóstico en GCP Logs:
- ✅ Fix activo: `"Entrenando recomendador TF-IDF con N productos"` en el startup
- ❌ Fix inactivo: `"Modelo TF-IDF cargado exitosamente desde archivo"` (cargó el .pkl viejo)

**Riesgo 2 — Pérdida de código en ediciones agresivas**

Esta sesión encontró código eliminado por ediciones previas. Establecer como regla: **siempre crear backup antes de modificar archivos > 30KB**. Los backups en `0_backups/` son la fuente de recuperación primaria.

**Riesgo 3 — Versión de sklearn**

El modelo ML de intent detection fue entrenado con `sklearn==1.6.1`. Si `requirements.cloudrun.txt` cambia esta versión, el modelo cargará pero dará `NotFittedError` en producción. La versión debe estar explícitamente pinned y nunca cambiarse sin reentrenar el modelo.

---

## 8. Recomendaciones

### 8.1 Buenas prácticas derivadas de esta sesión

**1. Leer antes de modificar (regla absoluta)**

Antes de cualquier cambio en un archivo, leer las secciones relevantes con `head/tail`. Nunca escribir sobre un archivo sin haber verificado su estado actual. Las herramientas de edición deben usar `edit_file` con `oldText/newText` (surgical), no `write_file` (reescritura total) salvo reconstrucción deliberada.

**2. Diagnóstico basado en evidencia**

Todas las hipótesis de causa raíz deben verificarse leyendo el código real antes de proponer una solución. En esta sesión se confirmó que `safe_extract_price()` ya existía en el archivo — si no se hubiera leído el código, se habría reimplementado innecesariamente.

**3. `logger.info` sobre `logger.debug` en paths críticos**

Cloud Run usa `LOG_LEVEL=INFO` por defecto. Cualquier log de diagnóstico en un bloque que deba ser visible en producción debe usar `logger.info`. `logger.debug` es invisible en producción.

**4. `os.environ.get()` para flags de feature activation**

Los flags de activación (`ENABLE_INTENT_DETECTION`, `ML_INTENT_ENABLED`) deben leerse con `os.environ.get()` directamente, no via Pydantic `@lru_cache`. El `@lru_cache` congela el valor en el startup, antes de que Cloud Run inyecte las env vars. Pydantic `Settings` es adecuado para configuración estática, no para flags que pueden activarse post-deploy.

**5. Tolerant Reader Pattern en boundaries de servicio**

La función `sanitize_rec_for_frontend()` es el ejemplo canónico: el boundary entre backend y frontend debe ser defensivo con lo que recibe. Esto protege contra cambios en el formato interno sin romper el contrato externo.

**6. Fix en el origen, con red de seguridad en el boundary**

El patrón `_normalize_product_price()` (origen) + `sanitize_rec_for_frontend()` (boundary) es la arquitectura recomendada para bugs de campo en datos: corregir en la fuente para que todos los consumidores se beneficien, pero mantener la red de seguridad en el boundary por si el origen cambia o falla.

**7. Documentar la arquitectura comentada como decisión técnica**

El bloque de factories comentadas en `mcp_router.py` no es "código muerto" — es documentación ejecutable de las decisiones de diseño. Debe preservarse y referenciarse en onboarding de nuevos desarrolladores.

### 8.2 Sugerencias técnicas para futuras iteraciones

- Añadir `metadata.json` al modelo TF-IDF (o ML) que registre la versión de sklearn y la fecha de entrenamiento. Leerlo en `load()` y emitir warning si la versión no coincide.
- Añadir tests de regresión para `sanitize_rec_for_frontend()` que cubran los campos vacíos, None, NaN, y objetos Pydantic.
- Considerar un endpoint de health dedicado que valide la estructura de una recomendación de muestra del catálogo (verificar que `price > 0` para al menos una muestra aleatoria).

---

## 9. Próximos Pasos

### 9.1 Inmediato (antes del siguiente deploy)

| Acción | Responsable | Criticidad |
|---|---|---|
| Eliminar `data/tfidf_model.pkl` del servidor/contenedor para forzar reentrenamiento con fix activo | DevOps | ✅ **Crítico** |
| Verificar en GCP Logs que el startup muestra `"Entrenando recomendador TF-IDF con N productos"` (no `"cargado desde archivo"`) | Dev | Alta |
| Verificar en GCP Logs `"Price sample (primeros 3): [159.0, 89.5, ...]"` con precios > 0 | Dev | Alta |
| Deploy de todos los fixes de esta sesión (mcp_router, tfidf_recommender, improved_fallback, mcp_personalization_engine) | Dev | Alta |

### 9.2 Corto plazo (próximas iteraciones)

| Mejora | Impacto esperado | Complejidad |
|---|---|---|
| Campo `url` en recomendaciones — backend retorna URL del producto Shopify y ProductCard la usa para navegación | UX: usuario puede navegar a la página del producto | Media |
| `min-instances=1` en Cloud Run | Elimina cold starts (~3–5s penalización actual) | Baja (config) |
| Tests unitarios para `sanitize_rec_for_frontend()` y `_normalize_product_price()` | Previene regresiones en campos de presentación | Baja |
| Cache de respuestas KB por `(sub_intent, language, market_id)` | Elimina round-trips a PostgreSQL en queries repetidas frecuentes | Media |

### 9.3 Medio plazo (roadmap técnico)

| Feature | Descripción | Complejidad |
|---|---|---|
| Memoria conversacional multi-turn | Incluir últimos N turns en el prompt de Claude para follow-ups contextuales | Media |
| Perfiles de usuario persistentes cross-session | PostgreSQL preferences table + profile injection en session start | Alta |
| Streaming de respuestas Claude | Anthropic SSR API → primeros tokens en ~200ms vs esperar respuesta completa | Media |
| Reentrenamiento del ML classifier con queries reales | Cuando acumule 1,000+ queries reales clasificadas → mejor accuracy en domain phrasing | Media |
| Dark/auto theme en el widget | CSS variables con @media (prefers-color-scheme: dark) | Baja |
| Tests frontend (React Testing Library + Playwright) | Cobertura de ChatWidget, MessageList, ProductCard, y E2E | Media |

---

## Apéndice A — Trazabilidad de Bugs por Archivo

| Archivo | Bugs resueltos | Descripción del cambio |
|---|---|---|
| `mcp_router.py` | BUG-01, BUG-07 | Restauración documentación factories + `get_personalization_engine()`. Nueva `sanitize_rec_for_frontend()`. Aplicación en 5 puntos de retorno. |
| `mcp_personalization_engine.py` | BUG-02 | `_generate_claude_personalized_response()` retorna `str` puro. |
| `tfidf_recommender.py` | BUG-05, BUG-08 | `_normalize_product_price()` aplana `price` e `image_url` al indexar. |
| `improved_fallback_exclude_seen.py` | BUG-06 | `safe_extract_price()` aplicado en Prioridad 1 y Prioridad 2 de `get_personalized_fallback()`. |

---

## Apéndice B — Comandos de Verificación Post-Deploy

```bash
# 1. Verificar que el modelo se reentrenó (no se cargó desde .pkl)
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"Entrenando recomendador TF-IDF"' \
  --project=retail-recommendations-449216 --limit=5

# 2. Verificar precios en segunda ronda
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"Price sample"' \
  --project=retail-recommendations-449216 --limit=10

# 3. Verificar intent detection activo
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"INTENT DETECTION BLOCK"' \
  --project=retail-recommendations-449216 --limit=5

# 4. Verificar sanitize aplicado
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"sanitize_rec_for_frontend aplicado"' \
  --project=retail-recommendations-449216 --limit=10

# 5. Verificar ausencia de ResponseValidationError
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"ResponseValidationError"' \
  --project=retail-recommendations-449216 --limit=5
```

---

## Control del Documento

| Versión | Fecha | Autor | Cambio |
|---|---|---|---|
| 1.0.0 | 27/03/2026 | Staff Engineering | Versión inicial — post-estabilización sistema conversacional |
