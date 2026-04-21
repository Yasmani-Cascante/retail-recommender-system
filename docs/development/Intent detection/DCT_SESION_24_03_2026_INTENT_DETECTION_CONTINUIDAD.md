# Documento de Continuidad Técnica
## Sesión 24/03/2026 — Intent Detection Activation & Frontend Architecture

---

## ESTADO DEL SISTEMA AL CIERRE DE SESIÓN

**Revisión activa en Cloud Run:** `retail-recommender-00072-2n4`
**Cloud Run Service:** `retail-recommender` — `us-central1` — proyecto `retail-recommendations-449216`
**URL producción:** `https://retail-recommender-lzf2y6pspa-uc.a.run.app`

---

## TRABAJO REALIZADO EN ESTA SESIÓN

### 1. Fix ResponseValidationError HTTP 500 — COMPLETADO Y DESPLEGADO ✅

**Archivo:** `src/api/routers/mcp_router.py`

El handler retornaba objetos Pydantic/custom en el campo `recommendations` en lugar de `dict` puros. Pydantic v2 con `List[Dict[str, Any]]` los rechazaba. Fix aplicado: sanitizar `recommendations` antes del return con cascada `isinstance(dict)` → `model_dump()` → `vars()` → `dict()`.

```python
# FIX APLICADO (línea ~746 mcp_router.py)
safe_recs = []
for rec in recommendations:
    if isinstance(rec, dict):
        safe_recs.append(rec)
    elif hasattr(rec, 'model_dump'):
        safe_recs.append(rec.model_dump())
    elif hasattr(rec, '__dict__'):
        safe_recs.append(vars(rec))
    else:
        try:
            safe_recs.append(dict(rec))
        except Exception:
            logger.warning(f"Skipping non-serializable recommendation: {type(rec)}")
```

**Estado:** En producción, HTTP 200 confirmado.

### 2. Mejoras Frontend Widget — COMPLETADO Y DESPLEGADO ✅

**Archivos modificados:**
- `src/frontend/src/components/ChatWidget.tsx` — estilos inline (CSS Modules), header oscuro, animaciones
- `src/frontend/src/components/ChatBubble.tsx` — posición fixed correcta, sin `position: relative`
- `src/frontend/src/components/MessageList.tsx` — burbujas asimétricas estilo iMessage
- `src/frontend/src/components/MessageInput.tsx` — input minimalista con fondo gris
- `src/frontend/src/components/ProductCard.tsx` — imagen placeholder + flecha
- `src/frontend/src/styles/main.css` — solo keyframes `rrSlideUp` y `rrBounce`, sin Tailwind
- `src/frontend/vite.config.ts` — añadido `vite-plugin-css-injected-by-js` (CSS incrustado en bundle)
- `Dockerfile.cloudrun` — añadido `COPY models/ /app/models/`

**Problema crítico resuelto:** En producción (Shopify), el CSS no se aplicaba porque Vite en modo `lib` genera `style.css` separado que nunca se carga. Solución: `vite-plugin-css-injected-by-js` inyecta el CSS directamente en el bundle UMD.

**Dev local:** `cd src/frontend && npm run dev` → `http://localhost:5173` con página replica de AI-Shoppings y panel de dev con 3 modos (mock/local/production).

### 3. Intent Detection — TRABAJO EN PROGRESO ⚠️

**Estado:** Variables configuradas en Cloud Run, pero el bloque de intent detection en el handler no se ejecuta. Se identificaron 3 bugs que se silenciaban mutuamente.

#### Variables configuradas en Cloud Run (confirmadas en screenshot `00072-2n4`)
```
ENABLE_INTENT_DETECTION = true
INTENT_CONFIDENCE_THRESHOLD = 0.7
INTENT_DETECTION_LOGGING = true
ML_INTENT_ENABLED = false
```

#### 3 bugs identificados y CORREGIDOS localmente (pendiente deploy)

**Bug 1 — Import de nivel módulo silencioso:**
```python
# ANTES (línea 31 mcp_conversation_handler.py) — causa crash silencioso en cold start
from src.api.ml.hybrid_detector import get_hybrid_intent_detector

# DESPUÉS — import lazy dentro del try
# (movido al interior del bloque ML enabled)
from src.api.ml.hybrid_detector import get_hybrid_intent_detector
```

**Bug 2 — logger.debug invisible con LOG_LEVEL=INFO:**
```python
# ANTES
else:
    logger.debug("Intent Detection is DISABLED in settings")  # invisible en prod

# DESPUÉS
else:
    logger.info("ℹ️ Intent Detection is DISABLED in settings (enable_intent_detection=False)")
```

**Bug 3 — except sin exc_info (stack trace invisible):**
```python
# ANTES
except Exception as e:
    logger.error(f"❌ Intent Detection error: {e}")  # sin stack trace

# DESPUÉS
except Exception as e:
    logger.error(f"❌ Intent Detection error: {e}", exc_info=True)  # con stack trace completo
```

**Adicionalmente — logs de diagnóstico añadidos:**
```python
# NUEVO: visible siempre con INFO
logger.info("🔍 INTENT DETECTION BLOCK: Evaluating...")
logger.info(f"🔍 INTENT DETECTION: enable_intent_detection={intent_enabled} "
            f"(from settings, env raw='{os.environ.get('ENABLE_INTENT_DETECTION', 'NOT_SET')}')")
```

---

## PRÓXIMO PASO INMEDIATO

### Deploy pendiente (CRÍTICO — cambio ya aplicado en local)

```bash
cd C:\Users\yasma\Desktop\retail-recommender-system

gcloud run deploy retail-recommender \
  --source . \
  --region us-central1 \
  --project retail-recommendations-449216
```

**Después del deploy, verificar en GCP Logs:**

1. Buscar: `🔍 INTENT DETECTION BLOCK: Evaluating...`
   - Si aparece → el bloque se ejecuta correctamente
   - Si NO aparece → hay un problema más profundo en el flujo previo

2. Buscar: `🔍 INTENT DETECTION: enable_intent_detection=`
   - Si muestra `True` con `env raw='true'` → settings lee correctamente
   - Si muestra `False` con `env raw='true'` → bug de `@lru_cache` en Pydantic Settings

3. Si el paso 2 falla (False + env=true), solución alternativa:
```python
# En mcp_conversation_handler.py, reemplazar:
settings = get_settings()
# Por:
from src.api.core.config import RecommenderSettings
settings = RecommenderSettings()  # Sin caché — fuerza re-lectura
```

4. Buscar: `🎯 Intent Detection ENABLED (rule-based only)` — confirma que el bloque activa
5. Para query "Políticas de devoluciones?", verificar:
   - `📚 INFORMATIONAL intent detected - using Knowledge Base v2`
   - `✅ Knowledge Base answer found - returning informational response`
   - Respuesta sin `recommendations[]`

---

## ARQUITECTURA DE INTENT DETECTION — Estado completo

### Archivos del sistema (todos existen, todos funcionales en local)

```
src/api/core/
├── intent_detection.py      ← Rule-based detector (RuleBasedIntentDetector)
├── intent_types.py          ← Enums: IntentType, InformationalSubIntent, etc.
├── knowledge_base.py        ← KB hardcoded (fallback)
├── knowledge_base_v2.py     ← ShopifyKnowledgeBase (triple-layer cache: Redis → PostgreSQL → Shopify)
└── config.py                ← Feature flags: enable_intent_detection, ml_intent_enabled, etc.

src/api/ml/
├── hybrid_detector.py       ← HybridIntentDetector (rule-based + ML fallback)
├── intent_classifier.py     ← MLIntentClassifier (sklearn TF-IDF + Logistic Regression)
├── __init__.py
└── training_data/           ← Datasets de entrenamiento

models/intent_classifier/
├── model.pkl                ← Modelo serializado (24 KB) — accuracy 96.26%
├── vectorizer.pkl           ← TF-IDF vectorizer (106 KB)
└── metadata.json            ← Métricas de entrenamiento

src/api/core/mcp_conversation_handler.py
└── FASE 1.5 (Intent Detection) — integración completa, activada por feature flag
```

### Flujo cuando funciona correctamente

```
Request → mcp_router.py → get_mcp_conversation_recommendations()
  ↓
FASE 1: Crear MCP context (Redis session)
  ↓
FASE 1.5: Intent Detection (si ENABLE_INTENT_DETECTION=true)
  ├─ Rule-based: detect_intent(query) → IntentDetectionResult
  ├─ Si confidence >= 0.7 Y intent == INFORMATIONAL:
  │   ├─ Obtener KB instance (app.state.knowledge_base_v2 → main_unified_redis → hardcoded fallback)
  │   ├─ kb.get_answer(sub_intent, language) → KnowledgeBaseAnswer
  │   └─ RETURN {answer, recommendations: [], metadata: {knowledge_base_used: true}}  ← early exit
  └─ Si TRANSACTIONAL o confidence < 0.7:
      └─ CONTINUAR → FASE 2 (recomendaciones de productos)
```

### Sub-intents disponibles (enum InformationalSubIntent)

| Valor | Descripción |
|---|---|
| `policy_return` | Devoluciones y cambios |
| `policy_shipping` | Envíos y entregas |
| `policy_payment` | Métodos de pago |
| `policy_warranty` | Garantías |
| `policy_privacy` | Política de privacidad |
| `product_material` | Materiales y tejidos |
| `product_sizing` | Guía de tallas |
| `product_care` | Cuidado de prendas |
| `product_availability` | Disponibilidad y stock |
| `account_orders` | Pedidos y cuenta |
| `account_modifications` | Modificaciones de pedido |
| `general_faq` | Preguntas generales |
| `unknown` | Sin clasificación específica |

**IMPORTANTE:** Los valores del enum deben coincidir exactamente con `sub_intent` en `kb_contents` PostgreSQL y metafields de Shopify CMS. Ver comentario en `intent_types.py`.

---

## OTROS ISSUES IDENTIFICADOS (prioridad media)

### Cache bug en personalization engine
La `diversity_cache_v2` cachea por `user_id` sin incluir la query. Requests dentro de los 5 minutos del mismo usuario obtienen el resultado cacheado de la query anterior. Fix recomendado: incluir hash de query en el cache key.

### Precio de productos en mercado ES
Precios retornados son muy bajos (0.01€, 0.8€, 3.45€) — probablemente conversión USD→EUR mal calibrada. No es crítico para funcionalidad pero afecta UX.

### CLAUDE_MAX_TOKENS secret (warning persistente)
```
⚠️ CLAUDE_MAX_TOKENS secret SOBREESCRIBE el valor del codigo: 300 → 200
```
El secret en Secret Manager fuerza 200 tokens. Para usar 300, eliminar o actualizar el secret `claude-max-tokens` en Cloud Run Secret Manager. Impacto: respuestas de Claude pueden ser más cortas de lo deseado.

---

## CONTEXTO GENERAL DEL SISTEMA

- **Proyecto:** Retail Recommender System v2.1.0
- **Infraestructura:** Google Cloud Run (auto-scale, min-instances=0)
- **Entry point:** `src/api/main_unified_redis.py`
- **Stack:** FastAPI + Redis + PostgreSQL (Neon) + Anthropic API (Haiku) + Shopify GraphQL
- **Mercados activos:** ES (principal en pruebas), US, MX, CL
- **Model activo:** `claude-3-haiku-20240307`, max_tokens=200, temperature=0.70

### Principios de trabajo establecidos (no violar)
1. Leer archivos reales antes de modificar — nunca asumir estructura
2. Evidence-based: toda conclusión basada en logs/código, nunca suposiciones
3. Un fix a la vez, validar antes del siguiente
4. `exc_info=True` en todos los `except` para errores no triviales
5. Logs de diagnóstico con `logger.info` (no `debug`) en bloques críticos
6. Preguntar antes de modificar código si hay dudas de impacto

---

## DOCUMENTOS DE REFERENCIA CREADOS EN ESTA SESIÓN

- `docs/development/frontend/FRONTEND_ARCHITECTURE.md` — Arquitectura completa del widget frontend
- Este documento (DCT de continuidad)

---

*Documento generado al cierre de sesión: 24/03/2026*
*Próximo paso: deploy + verificación de logs de intent detection*
