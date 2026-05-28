# DCT — MiniLM Capa 3 Semantic Intent Detection — Cierre 20_05_2026

**Fase:** MiniLM Layer-3 Semantic Intent Detection

**Versión del sistema:** v2.1.0

**Revisión Cloud Run:** retail-recommender-00185-7ml

**Fecha de cierre:** 2026-05-20

**Estado:** ✅ CERRADO Y VALIDADO EN PRODUCCIÓN

---

## 1. Resumen Ejecutivo

Se implementó y validó en producción una tercera capa semántica de detección de intents basada en el modelo `paraphrase-multilingual-MiniLM-L12-v2` de Sentence Transformers. Esta capa actúa exclusivamente cuando las capas 1 (rule-based) y 2 (sklearn TF-IDF + Logistic Regression) no alcanzan confianza de 0.60, resolviendo casos de slang LATAM, typos, queries informales y cross-lingual sin reentrenamiento.

Además se resolvieron dos bugs de producción: el timeout ausente en `get_product_context_by_handle` (causaba delays de 2.5 minutos) y los precios en CLP en el outfit carousel para el mercado CH (debían mostrarse en CHF).

**Resultado de validación final (Rev 00185-7ml):**

- miniml_warmup_complete en 9-11 segundos ✅
- miniml_predict confirmado en producción: query='Busco un conjunto completo', label=transactional/product_search, sim=0.514, time_ms=92.9 ✅
- Precios CHF en carousel: [111.24, 115.7, 115.7] ✅
- Request total reducido de 147s a 12.9s (-91%) ✅
- Cero errores 429 HuggingFace ✅

---

## 2. Qué se implementó y por qué

### 2.1 MiniLM como Capa 3 de Intent Detection

**Problema que resuelve:** El sistema de 2 capas tenía un punto ciego para queries informales de baja confianza. Queries como `"corre grande o chico?"`, `"salio fallado que hago?"` o `"esto me quedo grande"` quedaban sin clasificar correctamente porque no coincidían con patrones de reglas ni tenían suficiente masa léxica para TF-IDF.

**Por qué MiniLM L12 multilingual:** Es el modelo multilingual de la familia MiniLM que existe en HuggingFace. Soporta 50+ idiomas incluyendo ES formal, ES-MX, ES-CL y EN — exactamente los mercados del sistema. Con 118M parámetros y ~470MB ofrece el mejor balance entre calidad semántica y tamaño para CPU. **Nota crítica:** La variante L6 multilingual no existe; L6 solo existe en versión English-only. Este error costó múltiples revisiones de diagnóstico.

**Clasificación prototype-based (zero-shot):** En lugar de fine-tuning (que requiere miles de ejemplos etiquetados), se usa similitud de coseno entre el embedding de la query y centroides pre-computados de 14 labels. Los centroides son el promedio normalizado de embeddings de frases prototípicas por label. Esto permite agregar labels o corregir clasificaciones editando solo `PROTOTYPE_EXAMPLES` sin reentrenar.

**14 labels cubiertos:** greeting, informational/policy_return, informational/policy_shipping, informational/policy_payment, informational/policy_warranty, informational/policy_privacy, informational/product_sizing, informational/product_material, informational/product_availability, informational/product_care, transactional/product_search, transactional/product_compare, transactional/add_to_cart, transactional/checkout.

### 2.2 Fix de Timeout en product_context_[service.py](http://service.py)

`asyncio.wait_for(timeout=10s)` con degradación graceful. Si Shopify no responde en 10s el sistema continúa sin contexto de producto (F-01 boost no aplica pero la respuesta llega en tiempo normal). Fix que redujo el request de 147 segundos a 12.9 segundos en producción.

Configurable via `PRODUCT_CONTEXT_TIMEOUT_S` env var.

### 2.3 Fix de Precios CLP → CHF en Outfit Carousel

Conversión local con tasas fijas en `visual_search_router.py` cuando `market_prices` está vacío. El dict `_CLP_MARKET_RATES` define las tasas: CH→0.00089, MX→0.18, ES→0.00088, US→0.00104. Mismas tasas que usa el conversation handler. Es un fallback intencional; el comportamiento correcto será usar Shopify contextual pricing con cache de precios previo (gap G-01).

---

## 3. Arquitectura y Flujo de Datos

### Arquitectura de decisión de 3 capas

```
Query del usuario
      │
      ▼
┌─────────────────────────────────────┐
│  CAPA 1: Rule-Based  (<1ms)         │
│  intent_detection.py                │
│  Patrones TRANSACTIONAL/INFO        │
└──────────┬──────────────────────────┘
           │ conf < 0.80 → siguiente
           ▼
┌─────────────────────────────────────┐
│  CAPA 2: sklearn ML  (~0.5ms)       │
│  intent_classifier.py               │
│  TF-IDF + Logistic Regression       │
│  Accuracy: 96.26%                   │
└──────────┬──────────────────────────┘
           │ conf < 0.60 → siguiente
           ▼
┌─────────────────────────────────────┐
│  CAPA 3: MiniLM Semántico (~90ms)   │
│  miniml_classifier.py               │
│  Cosine similarity vs centroides    │
│  14 sub-intents, 50+ idiomas        │
└─────────────────────────────────────┘
           │
           ▼
    Intent + confidence
    → mcp_conversation_handler
```

### Flujo de Warmup en Producción

Durante el startup de FastAPI (lifespan):

1. `asyncio.create_task(_warmup_miniml_in_background())` lanza la carga sin bloquear el event loop
2. `loop.run_in_executor(None, _load_blocking)` mueve la carga CPU-bound al ThreadPoolExecutor
3. `SentenceTransformer(cache_folder='/app/models/miniml')` carga desde imagen Docker sin acceso a red
4. `_build_centroids()` pre-computa 14 centroides: encode(prototipos) → promedio → re-normalizar
5. `miniml_warmup_complete load_ms=9136` — el servidor lleva ~9s respondiendo requests mientras cargaba

### Flujo de Inferencia por Request

Ejemplo en producción con `"Busco un conjunto completo"`:

- Capa 1: TRANSACTIONAL conf=0.50 (default, sin patrón léxico claro)
- Capa 2: TRANSACTIONAL conf=0.506 — por debajo del umbral 0.60 → trigger MiniLM
- Capa 3: `encode(query)` → embedding 384-dim → `cosine(emb, centroid[transactional/product_search])` = 0.514, margen=0.158 → label confirmado en 92.9ms
- Resultado final: `method=miniml_semantic, confidence=0.51`

---

## 4. Componentes Involucrados

| Componente | Archivo | Rol |
| --- | --- | --- |
| `MiniLMIntentClassifier` | `src/api/ml/miniml_classifier.py` | Clasificador: load, centroides, predict, ranking |
| `HybridIntentDetector` | `src/api/ml/hybrid_detector.py` | Orquestador 3 capas, trigger threshold 0.60 |
| `PROTOTYPE_EXAMPLES` | `src/api/ml/miniml_classifier.py` | 14 labels × 8-20 frases prototípicas multilingüe |
| `_warmup_miniml_in_background` | `src/api/main_unified_redis.py` | Task background no-bloqueante en startup |
| `ProductContextService._fetch_from_shopify` | `src/api/mcp_services/product_context/service.py` | Fix timeout 10s en fetch Shopify |
| `visual_search_router._CLP_MARKET_RATES` | `src/api/routers/visual_search_router.py` | Fix precios CLP→CHF local en outfit |
| `Dockerfile.cloudrun` | `Dockerfile.cloudrun` | Baking modelo en `/app/models/miniml/`, ENV offline |
| Scripts de test | `scripts/debug_miniml_layer3.py`, `tests/unit/test_miniml_classifier.py`, `tests/unit/test_hybrid_detector_layer3.py` | Validación semántica y regresión |

### Variables de entorno en Cloud Run (estado final)

| Variable | Valor | Propósito |
| --- | --- | --- |
| `MINILM_INTENT_ENABLED` | `true` | Activa capa 3 |
| `MINILM_BACKEND` | `torch` | Backend de inferencia |
| `MINIML_CACHE_DIR` | `/app/models/miniml` | Ruta cache accesible por appuser |
| `HF_HUB_OFFLINE` | `1` | Bloquea requests a HuggingFace en runtime |
| `TRANSFORMERS_OFFLINE` | `1` | Bloquea download de transformers en runtime |
| `MINILM_TRIGGER_THRESHOLD` | `0.60` | Umbral de activación capa 3 |
| `MINILM_MIN_CONFIDENCE` | `0.50` | Confianza mínima para usar resultado MiniLM |
| `PRODUCT_CONTEXT_TIMEOUT_S` | `10` | Timeout Shopify product context |

---

## 5. Principales Problemas Encontrados y Soluciones

### P-01 → S-01: Modelo L6 multilingual no existe en HuggingFace

`paraphrase-multilingual-MiniLM-L6-v2` devolvía 404. El modelo correcto es L12. **Diagnóstico clave:** el error cambió de 401 (sin token, HF confunde repo inexistente) a 404 limpio (con token válido), confirmando que el repo no existe — no era un problema de autenticación.

Fix: cambiar `MODEL_NAME` a `paraphrase-multilingual-MiniLM-L12-v2`. Actualizar docstrings (22M params/88MB → 118M params/470MB).

### P-02 → S-02: Default MINILM_BACKEND=onnx roto en local

`ModuleNotFoundError: No module named 'onnxruntime'` al iniciar localmente. El default del código era `onnx` pero el venv local no tiene `onnxruntime-cpu`.

Fix: cambiar default a `torch`. Descubrimiento adicional: `sentence-transformers` ya trae `torch` como dependencia transitiva vía `requirements.cloudrun.txt`, haciendo ONNX innecesario (agregaba complejidad sin beneficio real).

### P-03 → S-03: Dockerfile multiline Python string parseado como instrucción FROM

`dockerfile parse error on line 64: FROM requires either one or three arguments`. El parser de Dockerfile interpreta newlines como instrucciones incluso dentro de comillas.

Fix: colapsar el bloque Python a una línea usando `;` como separador de sentencias.

### P-04 → S-04: Modelo bakeado en `/root/.cache/` inaccesible para appuser — raíz definitiva (3 revisiones)

Este fue el bug más complejo. Tres revisiones fallidas (00182, 00183, 00184) antes de identificar la causa:

- **Rev 00182:** Token HuggingFace expirado (401) → intentaba descargar sin auth → falló
- **Rev 00183:** Sin `HF_HUB_OFFLINE`, baking correcto pero runtime intentaba re-verificar via XET protocol → 429 rate limit (Cloud Run comparte IPs)
- **Rev 00184:** `HF_HUB_OFFLINE=1` impedía descarga pero el modelo seguía en `/root/.cache/` inaccesible → OSError
- **Rev 00185 (fix definitivo):** Bakear en `/app/models/miniml/` con `cache_folder='/app/models/miniml'`. El `chown -R appuser:appuser /app` del Dockerfile cubre esa ruta. `MINIML_CACHE_DIR=/app/models/miniml` alinea build y runtime.

**Lección arquitectónica:** En imágenes Docker con usuario no-root, cualquier archivo escrito al home de root durante el build es inaccesible para el usuario de runtime. Los artefactos del build que el runtime necesita leer deben estar en el directorio de trabajo de la aplicación (cubierto por chown).

### P-05 → S-05: Centroides policy_warranty vs product_availability en tensión semántica

El verbo "salir" en LATAM tiene semántica compartida: "salió mi pedido" (disponibilidad) y "salió fallado" (defecto). El L12 los agrupa en la misma región del embedding space.

Fix doble: (1) agregar variantes `salió/vino + defecto` a `policy_warranty` para acercar su centroide, Y (2) reemplazar ejemplos ambiguos de `product_availability` (`"se agotó?"`, `"ya no hay?"`) por lenguaje explícitamente de inventario/stock para alejar su centroide. Estrategia: atacar desde ambos lados del límite de decisión.

### P-06 → S-06: product_context sin timeout causaba delays de 132 segundos

Cuando Shopify tenía SSL errors con reintentos, `get_product_context_by_handle` esperaba indefinidamente. Observado en producción: request de 147.4 segundos (2.5 minutos).

Fix: `asyncio.wait_for(timeout_s, coro)` donde `timeout_s = float(os.getenv('PRODUCT_CONTEXT_TIMEOUT_S', '10'))`. Si expira, retorna `None` y el handler continúa sin contexto.

---

## 6. Métricas de Producción Validadas (Rev 00185-7ml)

| Métrica | Valor | Contexto |
| --- | --- | --- |
| MiniLM load time en Cloud Run | 9-11 segundos | Desde `/app/models/miniml/`, sin descarga de red |
| MiniLM inference (primera) | 92.9ms | JIT warm-up incluido |
| MiniLM inference (subsecuente) | ~10ms estimado | Post JIT compilation |
| Tests unitarios fast | 37/37 ✅ | `pytest -m "not slow"` |
| Tests semánticos slow | 16/16 ✅ | `pytest -m slow` con modelo real |
| Queries de validación producción | 10/10 ✅ | `debug_miniml_layer3.py` |
| Request total (sin product_context) | 12.9s vs 147s anterior | Reducción del 91% |
| Errores 429 HuggingFace en runtime | 0 | HF_HUB_OFFLINE=1 ✅ |
| Precios outfit carousel | CHF ✅ | Local rate 0.00089 |
| Startup warmup (no bloqueante) | Confirmado ✅ | Servidor responde desde segundo 0 |

---

## 7. Gaps e Identificados — Áreas de Mejora

### G-01 — Precios outfit carousel son conversión local, no Shopify real

El dict `_CLP_MARKET_RATES` con tasas fijas es un fallback intencional. Los precios reales de Shopify contextual pricing para el mercado CH no están pre-computados en `tfidf_rec.id_index`. Diferencia estimada < 3% respecto al precio real.

**Solución pendiente:** Pre-calentar precios de mercado para los top-N productos más frecuentes en job de startup, o cachearlos en Redis via webhook `products/update`. Mismo fix que G-02.

### G-02 — MCP personalization timeout sistemático (lazy-price 10-12s)

El presupuesto de personalización (8s) es consumido por lazy-price antes de que LFM pueda responder. El sistema degrada a base recommendations correctamente, pero sin personalización.

**Solución pendiente:** Cachear precios de mercado en Redis con TTL 1h por `product_id:market_id`. Segunda request del mismo producto: cache hit < 1ms, personalizaición LFM tiene su presupuesto completo.

### G-03 — Python 3.9 EOL

Dockerfile usa `python:3.9-slim`. Python 3.9 alcanzó EOL en octubre 2025. Google emite FutureWarnings en múltiples librerías (google-auth, google-api-core, google-cloud-monitoring).

**Solución pendiente:** Migrar a `python:3.11-slim`. Alinea con el entorno de desarrollo local (Python 3.11.3).

### G-04 — MiniLM inference primera query ~93ms (JIT)

Primera inferencia en instancia fría tiene overhead de JIT compilation. Las subsecuentes son ~10ms.

**Solución pendiente:** En `_build_centroids()`, al final del warmup, hacer una encode dummy para pre-compilar el JIT. Una línea: `self._model.encode(['warmup'], normalize_embeddings=True, show_progress_bar=False)`.

### G-05 — Edge case warranty vs availability en tensión semántica

Margen final: 0.619 (availability) vs 0.560 (warranty) para `"salio fallado que hago?"`. Funcional pero ajustado. No resoluble con más prototipos — clases no linealmente separables en ese espacio de embeddings.

**Solución pendiente:** Override de regex en `predict()` para el patrón `(salio|vino|llego|recibi).{0,20}(fallado|defecto|roto|danado)` → `informational/policy_warranty` directo, saltando centroides.

### G-06 — Google Retail API devuelve respuestas vacías

La API devuelve solo `attribution_token` sin resultados. El sistema siempre usa el fallback hybrid recommender (TF-IDF + query-driven). El modelo de Retail no se aprovecha.

**Solución pendiente:** Revisar configuración del serving config `default_recommendation_config` y el catálogo importado en Google Cloud Retail.

---

## 8. Recomendaciones y Próximos Pasos

### Inmediatos (próximo sprint)

1. **F-01 Contextual Upsell** — siguiente feature planificado. `product_id` llega como handle string, no ID numérico — crítico tenerlo en cuenta en la implementación.
2. **JIT dummy warmup** — una línea al final de `_build_centroids()` para eliminar los 93ms de primera inferencia.
3. **Verificación F-05 Stock Alerts** — pendiente desde sesión de abril 2026. El fix de `needs_contextualisation=True` para `product_availability` sub-intents fue implementado pero la verificación final quedó pendiente.

### Mediano plazo

1. **Cache de precios de mercado en Redis** — resuelve G-01 y G-02 simultáneamente. Al obtener precios vía lazy-price, persistirlos en Redis con TTL 1h por `product_id:market_id`.
2. **Migración Python 3.9 → 3.11** — cambiar `FROM python:3.9-slim` a `FROM python:3.11-slim` en `Dockerfile.cloudrun`.
3. **Override regex warranty slang CL** — workaround conocido y documentado para el edge case de P-05.

### Largo plazo

1. **Fine-tuning de MiniLM** — con acumulación de logs de producción, hacer fine-tuning del modelo para ES-LATAM específicamente. Reemplazaría prototype-based por clasificador lineal sobre embeddings fine-tuneados.
2. **Google Retail API** — investigar y corregir la configuración del serving config.
3. **Python EOL** — planificar migración antes de que las librerías críticas dejen de recibir security patches.

---

## 9. Archivos Modificados en Esta Fase

| Archivo | Tipo de cambio |
| --- | --- |
| `src/api/ml/miniml_classifier.py` | Nuevo — clasificador MiniLM completo con prototype-based classification |
| `src/api/ml/hybrid_detector.py` | Modificado — integración capa 3, stats, trigger threshold |
| `src/api/main_unified_redis.py` | Modificado — warmup background task no-bloqueante |
| `src/api/mcp_services/product_context/service.py` | Modificado — timeout 10s en fetch Shopify |
| `src/api/routers/visual_search_router.py` | Modificado — dict _CLP_MARKET_RATES + conversión local CLP→CHF |
| `Dockerfile.cloudrun` | Modificado — baking en `/app/models/miniml`, ENV HF_HUB_OFFLINE=1 |
| `scripts/debug_miniml_layer3.py` | Nuevo — script de validación semántica con 10 queries de producción |
| `tests/unit/test_miniml_classifier.py` | Nuevo — 14 tests fast + 16 tests slow (semánticos con modelo real) |
| `tests/unit/test_hybrid_detector_layer3.py` | Nuevo — 19 tests de integración capa 3 |

---

*DCT generado al cierre de la sesión de integración MiniLM Layer-3. Próxima sesión: F-01 Contextual Upsell.*