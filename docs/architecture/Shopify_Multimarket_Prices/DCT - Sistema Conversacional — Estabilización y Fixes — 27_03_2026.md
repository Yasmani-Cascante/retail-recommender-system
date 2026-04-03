# DCT — Sistema Conversacional — Estabilización y Fixes — 27_03_2026

# Documento de Continuidad Técnica

## Sistema Conversacional — Estabilización y Fixes de Producción

### Retail Recommender System v2.1.0

---

| Campo | Valor |
| --- | --- |
| Documento | DCT-CONV-ESTAB-27032026 |
| Sistema | Retail Recommender System v2.1.0 |
| Estado | ✅ Estable — Producción |
| Fecha | 27 Marzo 2026 |
| Cloud Run Rev. | retail-recommender-00084-jk6 |
| Audiencia | Ingeniería, Onboarding, Mantenimiento |
| Refs. | RFC-2026-001, FRONTEND_ARCHITECTURE 24.03.2026 |

---

## 🚀 Prompt de continuidad — pegar en nueva sesión

```
Contexto: Retail Recommender System v2.1.0 en Cloud Run (retail-recommender-lzf2y6pspa-uc.a.run.app).

Última sesión (27/03/2026): Sesión intensiva de diagnóstico y fixes del sistema conversacional.
Se resolvieron 8 bugs activos. El sistema está estable y funcional.

El modelo TF-IDF fue regenerado (data/tfidf_model.pkl eliminado y reconstruido).
Todos los productos muestran datos completos incluyendo precio e imagen.

Lee el DCT "Sistema Conversacional — Estabilización y Fixes — 27_03_2026" en Notion
para el contexto completo antes de continuar.
```

---

## 1. Resumen del sistema

### 1.1 Descripción

El **Retail Recommender Conversational System** es un asistente de chat con IA embebible en storefronts de Shopify. Se despliega como un widget React (~150 KB, un único archivo `.cjs` autocontenido) que se comunica con una API FastAPI en Google Cloud Run.

Sirve dos categorías de consultas:

- **Informacionales** — preguntas sobre políticas de la tienda (devoluciones, envíos, pagos, garantías, tallas). Respondidas desde una Knowledge Base sincronizada desde Shopify CMS via metafields, con contextualización Claude Haiku para consultas específicas (RAG).
- **Transaccionales** — búsqueda y descubrimiento de productos. Respondidas con recomendaciones personalizadas generadas por el pipeline HybridRecommender + MCPPersonalisationEngine + MarketAdapter.

### 1.2 Capacidades principales

| Capacidad | Tecnología | Estado |
| --- | --- | --- |
| Detección de intención | Rule-based (regex) + sklearn TF-IDF + LR (hybrid) | ✅ Operativo |
| Respuesta a saludo | Template bilingüe, sin llamada a Claude | ✅ Operativo |
| Respuesta informacional | PostgreSQL (Neon) + Redis + Claude Haiku RAG | ✅ Operativo |
| Recomendaciones transaccionales | TF-IDF HybridRecommender + MCPPersonalisationEngine | ✅ Operativo |
| Diversificación segunda ronda | ImprovedFallbackStrategies — excluye productos vistos | ✅ Operativo |
| Multi-mercado | ES, US, MX, CL — MarketAdapter + KB multilingüe | ✅ Operativo |
| Persistencia de sesión | Redis TTL 86 400 s — historial multi-turn | ✅ Operativo |
| Detección de idioma | Accept-Language header + validación | ✅ Operativo |

### 1.3 Estado actual

El sistema alcanzó **estabilidad de producción el 27/03/2026** tras una sesión intensiva de fixes que resolvió 8 bugs activos. Los flujos principales (greeting, informacional, transaccional), la diversificación de recomendaciones, la serialización de respuestas y la indexación del catálogo TF-IDF están correctamente operativos.

> **Nivel de madurez:** Producción estable para tráfico de prueba. Los gaps documentados en la Sección 7 no bloquean el uso pero deben abordarse antes de escalar.
> 

---

## 2. Problemas enfrentados

| ID | Problema | Impacto | Severidad |
| --- | --- | --- | --- |
| BUG-01 | `mcp_router.py` perdió bloque de documentación de factories (~300 líneas) y función `get_personalization_engine()` | Pérdida de trazabilidad arquitectónica; función activa faltante | Media |
| BUG-02 | `_generate_claude_personalized_response()` devolvía `Dict` en vez de `str` | Dict `{"response": "...", "tone_adaptation": ...}` visible como texto crudo en el chat widget | Alta |
| BUG-03 | HTTP 529 Anthropic (Overloaded) causaban respuesta de fallback visible | Usuario veía `"Te ayudo a encontrar lo que buscas..."` en vez de respuesta personalizada | Media |
| BUG-04 | Segunda ronda de recomendaciones sin precio (`price = 0`) | `ProductCard.tsx` mostraba `€0` en todas las tarjetas de segunda ronda | Alta |
| BUG-05 | Catálogo TF-IDF no aplana `price` desde `variants[0].price` al nivel raíz | Causa raíz de BUG-04: REST API de Shopify devuelve el precio anidado, nunca al nivel raíz | Alta (causa raíz) |
| BUG-06 | `get_personalized_fallback()` usaba `**product` sin sobrescribir `price` | Prioridades 1 y 2 de diversificación heredaban `price=None` del catálogo crudo | Alta |
| BUG-07 | Loop manual `safe_recs` en el router no normalizaba `price`, `score` ni `image_url` | Primera ronda funcionaba; segunda ronda sin normalización completa | Media |
| BUG-08 | `image_url` no llegaba al frontend desde productos del catálogo TF-IDF | El catálogo almacena `images: [{src: "..."}]` pero nunca aplanaba `image_url` al nivel raíz | Media |

---

## 3. Decisiones técnicas clave

### 3.1 BUG-02 — Tipo de retorno `str` en `_generate_claude_personalized_response()`

**Flujo afectado:** Path secundario de personalización en `mcp_router.py` → `mcp_personalization_engine.py`

**Decisión:** El método debe retornar `str` puro, nunca `Dict`.

**Justificación:** El router tiene `extract_answer_from_claude_response()` para manejar todas las formas posibles del response de Claude. La función de personalización debe emitir un str limpio, no añadir otra capa de dict. `conversation_enhancement` usa safe defaults porque el string ya no lleva esas claves.

**Alternativa descartada:** Mantener el dict y actualizar `extract_answer_from_claude_response()` para desenrollar. Añadiría complejidad innecesaria.

---

### 3.2 BUG-04/05 — Precio ausente en segunda ronda (causa raíz + solución)

**Flujo afectado:** `load_recommender()` → `tfidf_recommender.fit()` → `product_data[]` → `smart_fallback()` → `ProductCard.tsx`

**Causa raíz:** La API REST de Shopify (`/admin/api/2025-01/products.json`) devuelve el precio en `product["variants"][0]["price"]` (string, ej. `"159.00"`), **NO** en `product["price"]` (campo ausente o `None` a nivel raíz). El catálogo TF-IDF guardaba los objetos crudos sin aplanar. Cualquier path que use `**product` hereda ese `None`.

**Decisión — Opción C (máxima robustez), tres capas:**

- **Capa A — Origen:** `tfidf_recommender._normalize_product_price()` aplana `variants[0].price` → `price` al indexar
- **Capa B — Path de diversificación:** `get_personalized_fallback()` sobrescribe `"price": safe_extract_price(product)` explícitamente
- **Capa C — Router:** `sanitize_rec_for_frontend()` garantiza invariantes en todos los paths

**Alternativa descartada:** Solo capa C. No corrige los datos en origen — si el router fallara, el problema reaparecería.

**Efecto secundario positivo:** `_normalize_product_price()` también aplana `image_url` desde `images[0]["src"]`, resolviendo BUG-08.

---

### 3.3 Tolerant Reader Pattern en el boundary del router

**Decisión:** Mantener dos niveles de normalización:

- **Nivel 1 (origen):** `_normalize_product_price()` en `fit()` — normaliza el catálogo permanentemente
- **Nivel 2 (última milla):** `sanitize_rec_for_frontend()` en el router — garantiza invariantes independientemente del path

**Justificación:** Si el MarketAdapter falla o no está disponible, sin la capa en el router los campos crudos llegan al frontend. El patrón "tolerant reader" en el boundary backend-frontend es estándar para servicios que evolucionan.

---

### 3.4 BUG-03 — HTTP 529 Anthropic

**Decisión:** No modificar el retry loop existente (3 intentos, sleep 50ms).

**Justificación:** HTTP 529 es un estado transitorio de Anthropic. El loop funcionó correctamente: intento 1 → 529, intento 2 → 529, intento 3 → 200 OK. El fallback solo activa cuando los 3 intentos fallan.

---

## 4. Soluciones implementadas

### 4.1 Fix BUG-02 — `_generate_claude_personalized_response()` retorna `str`

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py`

```python
# ANTES (dict visible en el chat):
return {
    "response": response_text,
    "tone_adaptation": "standard",
    ...
}

# DESPUÉS (str puro):
return response_text
```

---

### 4.2 Fix BUG-05 — `TFIDFRecommender._normalize_product_price()`

**Archivo:** `src/recommenders/tfidf_recommender.py`

Nuevo método estático aplicado en `fit()` antes de guardar en `product_data`:

```python
self.product_data = [self._normalize_product_price(p) for p in products]
```

Lógica del método:

1. Si `product["price"]` ya tiene valor > 0 → devuelve sin cambios (no pisa datos del MarketAdapter)
2. Si `price` es `None` o 0 → extrae desde `variants[0]["price"]` (string Shopify → float)
3. Aplana `image_url` desde `images[0]["src"]` si no existe como campo directo

> ⚠️ **Nota crítica:** `data/tfidf_model.pkl` debe ser eliminado antes del deploy para forzar re-entrenamiento con el fix activo. Si el `.pkl` existe, `load_recommender()` lo carga directamente sin llamar a `fit()`.
> 

---

### 4.3 Fix BUG-06 — `safe_extract_price()` en `get_personalized_fallback()`

**Archivo:** `src/recommenders/improved_fallback_exclude_seen.py`

`safe_extract_price()` ya existía en el archivo (usada en `get_popular_products()` y `get_diverse_category_products()`). Los dos bloques sin cobertura eran Prioridad 1 y Prioridad 2:

```python
# ANTES:
recommendations.append({
    **product,
    "score": score,
    "recommendation_type": "personalized_fallback",
})

# DESPUÉS:
recommendations.append({
    **product,
    "price": safe_extract_price(product),  # override explícito
    "score": score,
    "recommendation_type": "personalized_fallback",
})
```

---

### 4.4 Fix BUG-07 — `sanitize_rec_for_frontend()` en `mcp_router.py`

**Archivo:** `src/api/routers/mcp_router.py`

Nueva función aplicada en los **5 puntos de retorno** del router.

**Invariantes garantizados:**

| Campo | Tipo | Fuente / Fallback |
| --- | --- | --- |
| `id` | `str` non-empty | `rec["id"]` o `"unknown"` |
| `title` | `str` non-empty | `title` o `localized_title` o `"Producto"` |
| `price` | `float >= 0` | `price` o `market_price` o `0.0` |
| `currency` | `str` non-empty | `currency` o `"EUR"` |
| `score` | `float [0,1]` | múltiples fuentes con fallback `0.5` |
| `description` | `str` sin HTML | strip HTML + `body_html` como fallback |
| `image_url` | `str` o `None` | `image_url` o `imageUrl` o `images[0]` |
| `url` | `str` o `None` | opcional — para link en ProductCard |

También convierte objetos Pydantic (`model_dump()`), dataclasses (`vars()`), y cualquier tipo iterable a dict puro.

---

### 4.5 Fix BUG-01 — Restauración de `mcp_router.py`

**Archivo:** `src/api/routers/mcp_router.py`

Restaurado desde `0_backups/mcp_router.backup_21112025.py`:

- Bloque de factories comentadas (~300 líneas) que documenta la evolución de 3 patrones de DI
- Función activa `get_personalization_engine()` (fuera de `Depends()` intencionalmente)

---

## 5. Componentes modificados

| Archivo | Tipo | Cambios |
| --- | --- | --- |
| `src/api/routers/mcp_router.py` | Restauración + modificación | Factories documentadas + `get_personalization_engine()` restauradas. Nueva `sanitize_rec_for_frontend()`. Aplicada en 5 puntos de retorno. |
| `src/api/mcp/engines/mcp_personalization_engine.py` | Fix tipo retorno | `_generate_claude_personalized_response()` retorna `str` puro. |
| `src/recommenders/tfidf_recommender.py` | Nuevo método | `_normalize_product_price()`  • aplicado en `fit()`. |
| `src/recommenders/improved_fallback_exclude_seen.py` | Fix en 2 bloques | `safe_extract_price()` en Prioridad 1 y Prioridad 2 de `get_personalized_fallback()`. |

### Backups relevantes

| Backup | Tamaño | Cuándo usar |
| --- | --- | --- |
| `src/api/routers/0_backups/mcp_router.backup_21112025.py` | 95.23 KB | Recuperar documentación factories si se pierde |
| `src/api/mcp/engines/mcp_personalization_engine.py.backup_27032026` | 169.45 KB | Estado pre-fix del engine |
| `src/recommenders/tfidf_recommender.py.backup_` | 12.37 KB | Estado pre-fix del TF-IDF |

### Piezas nuevas en la arquitectura

**`sanitize_rec_for_frontend()` — Tolerant Reader en el boundary del router**

Red de seguridad en el boundary backend-frontend. El router garantiza invariantes independientemente de cuál path generó las recomendaciones:

```
HybridRecommender (path A) → MarketAdapter → sanitize_rec_for_frontend → frontend
smart_fallback (path B)    → (sin adapter) → sanitize_rec_for_frontend → frontend
hybrid_recommender fallback → sin pipeline  → sanitize_rec_for_frontend → frontend
```

**`_normalize_product_price()` — Normalización en origen del catálogo**

Método estático en `TFIDFRecommender` que aplana `price` e `image_url` al nivel raíz en el momento de indexación. Principio "fix it at the source".

---

## 6. Flujo actual del sistema

### 6.1 Flujo conversacional completo

```
[1] Usuario abre el widget
    → ChatWidget.tsx monta (React 18, UMD bundle)
    → Bienvenida local (sin llamada API)
    → userId de localStorage, sessionId generado

[2] Usuario envía mensaje
    → POST /v1/mcp/conversation
    → Headers: X-API-Key, Accept-Language
    → Body: {query, user_id, session_id, market_id, language, widget_context}

[3] mcp_router.py
    → Detección de idioma
    → get_conversation_state_manager() → Redis
    → get_mcp_conversation_recommendations()

[4] mcp_conversation_handler.py

    FASE 1: Cargar contexto MCP (Redis)
    FASE 1.5: Detección de intención
    → ENABLE_INTENT_DETECTION via os.environ.get() (no Pydantic @lru_cache)

    ┌─ GREETING (0.95)
    │   → Template bilingüe, sin Claude
    │   → Early return
    │
    ├─ INFORMATIONAL (≥ 0.7)
    │   → kb.get_answer() ← 3-layer cache (Redis → Neon → Shopify GraphQL)
    │   → has_specific_entities()? → Claude Haiku RAG (max_tokens=250)
    │   → Early return {answer, kb_document, recommendations: []}
    │
    └─ TRANSACTIONAL → continúa

    FASE 2: Ejecución paralela
    → HybridRecommender.get_recommendations() o smart_fallback()
    → MCPPersonalisationEngine (warm singleton)
    → MarketAdapter

    FASE 3: Personalización (cache 5min)
    → Claude Haiku (timeout 12s)

    FASE 4: State persistence (Redis)
    → recommendation_ids almacenados para diversificación futura

    FASE 5: Market adaptation
    → market_adapter.adapt_product() por cada item

[5] mcp_router.py (post-handler)
    → sanitize_rec_for_frontend() por cada recomendación   ← FIX
    → ConversationResponse Pydantic

[6] ChatWidget.tsx
    → Message{assistant} + ProductCard[]
```

### 6.2 Flujo de diversificación (segunda ronda)

```
Turn 1: "quiero un vestido"
→ HybridRecommender → MarketAdapter → [A, B, C, D, E] en Redis

Turn 2: "muéstrame más"
→ shown_products = {A, B, C, D, E}
→ ImprovedFallbackStrategies.smart_fallback(exclude=shown_products)
    → get_personalized_fallback(user_query=query)
        → P1: query_category_driven_multi
        → P2: personalized (historial)
        → P3: diverse (categorías variadas)
        → P4: popular (fallback final)
    → "price": safe_extract_price(product)   ← FIX BUG-06
→ sanitize_rec_for_frontend()                ← FIX BUG-07
→ [F, G, H, I, J] — sin duplicados
```

### 6.3 Mapa de componentes

```
Frontend (React 18 UMD, Shopify)
    ↕ HTTPS REST
Backend (FastAPI, Cloud Run)
    ├── mcp_router.py              ← Boundary + sanitización final
    ├── mcp_conversation_handler   ← Orquestador del pipeline
    │   ├── intent_detection.py    ← Rule-based + sklearn hybrid
    │   ├── knowledge_base_v2.py   ← KB lookup (Redis → Neon → GraphQL)
    │   └── kb_contextualizer.py   ← Entity check + Claude RAG
    ├── HybridRecommender
    │   └── TFIDFRecommender       ← product_data[] normalizado
    ├── MCPPersonalisationEngine   ← Claude Haiku
    ├── ImprovedFallbackStrategies ← Diversificación
    └── MarketAdapter              ← price, currency por mercado

Servicios externos
    ├── Redis Cloud        ← Sesión (TTL 86 400 s)
    ├── PostgreSQL Neon    ← KB persistente
    ├── Shopify GraphQL    ← Productos + KB CMS
    └── Anthropic API      ← Claude Haiku
```

---

## 7. Observaciones y gaps

### 7.1 Limitaciones actuales

| Limitación | Descripción | Severidad |
| --- | --- | --- |
| Modelo `.pkl` en disco | Si existe, `load_recommender()` lo carga sin pasar por `fit()`. El fix solo aplica en reentrenamientos. Requiere eliminar el `.pkl` antes del deploy. | Alta |
| Sin memoria multi-turn real | El prompt de Claude no incluye historial. Follow-ups contextuales ("el segundo", "algo más barato") no se entienden. | Media |
| KB: un doc por sub-intent | Dos preguntas con el mismo `sub_intent` reciben el mismo documento fuente. | Media |
| Cold start sin min-instances | Cloud Run min-instances=0 → cold start 3–5s. | Media |
| Precios en mercados no-ES | `currency` puede venir hardcodeado como `"EUR"` cuando MarketAdapter no aplica. | Media |
| Campo `url` ausente | `ProductCard.tsx` no puede navegar a la página del producto. | Media |
| Sin tests de frontend | Cero tests unitarios/integración para componentes React. | Media |

### 7.2 Riesgos potenciales

**Riesgo 1 — `.pkl` en el servidor**

Si no se elimina antes del deploy, el BUG-04 reaparecerá.

Señal en GCP Logs:

- ✅ Fix activo: `"Entrenando recomendador TF-IDF con N productos"` en startup
- ❌ Fix inactivo: `"Modelo TF-IDF cargado exitosamente desde archivo"`

**Riesgo 2 — Pérdida de código por ediciones agresivas**

Esta sesión encontró código eliminado por ediciones previas. Regla: crear backup antes de modificar archivos > 30KB.

**Riesgo 3 — Versión sklearn**

El ML classifier fue entrenado con `sklearn==1.6.1`. Si `requirements.cloudrun.txt` cambia esta versión, dará `NotFittedError` en producción.

---

## 8. Recomendaciones

### 8.1 Buenas prácticas derivadas

**1. Leer antes de modificar (regla absoluta)**

Siempre leer secciones relevantes antes de cualquier cambio. Usar `edit_file` con `oldText/newText` quirúrgico, no `write_file` (reescritura total).

**2. Diagnóstico basado en evidencia**

Verificar en código real antes de proponer una solución. En esta sesión se confirmó que `safe_extract_price()` ya existía — si no se hubiera leído el código, se habría reimplementado innecesariamente.

**3. `logger.info` sobre `logger.debug` en paths críticos**

Cloud Run usa `LOG_LEVEL=INFO`. Los `logger.debug` son invisibles en producción.

**4. `os.environ.get()` para flags de feature activation**

Los flags (`ENABLE_INTENT_DETECTION`, `ML_INTENT_ENABLED`) deben leerse con `os.environ.get()` directamente, no via Pydantic `@lru_cache`. El cache congela el valor antes de que Cloud Run inyecte las env vars.

**5. Tolerant Reader Pattern en boundaries de servicio**

`sanitize_rec_for_frontend()` es el ejemplo canónico: el boundary backend-frontend debe ser defensivo. Protege contra cambios en el formato interno sin romper el contrato externo.

**6. Fix en el origen + red de seguridad en el boundary**

`_normalize_product_price()` (origen) + `sanitize_rec_for_frontend()` (boundary) es el patrón recomendado: corregir en la fuente para que todos los consumidores se beneficien, y mantener la red de seguridad por si el origen cambia.

**7. Las factories comentadas son documentación, no código muerto**

El bloque de factories en `mcp_router.py` documenta las decisiones de diseño. Debe preservarse.

### 8.2 Sugerencias para futuras iteraciones

- Añadir `metadata.json` al modelo TF-IDF con versión de sklearn y fecha de entrenamiento. Leerlo en `load()` y emitir warning si la versión no coincide.
- Añadir tests de regresión para `sanitize_rec_for_frontend()` con campos vacíos, None, NaN y objetos Pydantic.
- Endpoint de health que valide `price > 0` para una muestra aleatoria del catálogo.

---

## 9. Próximos pasos

### 9.1 Inmediato (antes del siguiente deploy)

| Acción | Criticidad |
| --- | --- |
| ✅ Eliminar `data/tfidf_model.pkl` y verificar regeneración en local | Completado |
| Deploy de los fixes a Cloud Run | Alta |
| Verificar en GCP Logs: `"Entrenando recomendador TF-IDF"` (no `"cargado desde archivo"`) | Alta |
| Verificar `"Price sample (primeros 3): [159.0, ...]"` con precios > 0 | Alta |

### 9.2 Corto plazo

| Mejora | Impacto | Complejidad |
| --- | --- | --- |
| Campo `url` en recomendaciones | UX: navegar a página del producto | Media |
| `min-instances=1` en Cloud Run | Elimina cold starts | Baja |
| Tests unitarios para `sanitize_rec_for_frontend()` y `_normalize_product_price()` | Previene regresiones | Baja |
| Cache KB por `(sub_intent, language, market_id)` | Reduce round-trips a PostgreSQL | Media |

### 9.3 Medio plazo (roadmap)

| Feature | Complejidad |
| --- | --- |
| Memoria conversacional multi-turn (últimos N turns en prompt) | Media |
| Perfiles de usuario persistentes cross-session | Alta |
| Streaming de respuestas Claude | Media |
| Reentrenamiento ML classifier con queries reales (≥1,000) | Media |
| Dark/auto theme en el widget | Baja |
| Tests frontend (React Testing Library + Playwright) | Media |

---

## Apéndice A — Trazabilidad de bugs por archivo

| Archivo | Bugs | Descripción |
| --- | --- | --- |
| `mcp_router.py` | BUG-01, BUG-07 | Factories restauradas + `sanitize_rec_for_frontend()` en 5 puntos |
| `mcp_personalization_engine.py` | BUG-02 | Retorna `str` puro |
| `tfidf_recommender.py` | BUG-05, BUG-08 | `_normalize_product_price()` aplana `price` e `image_url` |
| `improved_fallback_exclude_seen.py` | BUG-06 | `safe_extract_price()` en P1 y P2 de `get_personalized_fallback()` |

---

## Apéndice B — Comandos de verificación post-deploy

```bash
# 1. Verificar reentrenamiento del modelo (no carga desde .pkl)
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"Entrenando recomendador TF-IDF"' \
  --project=retail-recommendations-449216 --limit=5

# 2. Verificar precios correctos
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"Price sample"' \
  --project=retail-recommendations-449216 --limit=10

# 3. Verificar intent detection activo
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"INTENT DETECTION BLOCK"' \
  --project=retail-recommendations-449216 --limit=5

# 4. Verificar ausencia de ResponseValidationError
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"ResponseValidationError"' \
  --project=retail-recommendations-449216 --limit=5
```

---

## Control del documento

| Versión | Fecha | Cambio |
| --- | --- | --- |
| 1.0.0 | 27/03/2026 | Versión inicial — post-estabilización sistema conversacional |

[DCT — Opcion A Shopify Prices Multi-Market — 28/03/2026](DCT%20%E2%80%94%20Opcion%20A%20Shopify%20Prices%20Multi-Market%20%E2%80%94%2028%2003%20331cfd3fcb288156b924cb1e63e3341c.md)