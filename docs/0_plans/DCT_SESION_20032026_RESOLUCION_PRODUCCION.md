# DCT — Resolución de Problemas en Producción
## Retail Recommender System v2.1.0 — Sesión 20/03/2026

> **Tipo:** Documento de Continuidad Técnica (DCT) — Resumen de Sesión  
> **Estado al cierre:** ✅ Sistema completamente operacional en producción  
> **Score smoke tests:** 19/19 — 100%  
> **Revisión activa:** `retail-recommender-00061-rmx`  
> **Fecha:** 20 de Marzo de 2026

---

## 1. Resumen Ejecutivo

Esta sesión tuvo como objetivo diagnosticar y resolver un conjunto de errores críticos y de latencia que afectaban al sistema en producción tras los deploys recientes que incorporaron las fases M3 (GCP Cloud Monitoring), el warm-up de Claude API (PASO 8.5/8.6) y otras mejoras acumuladas.

Al inicio de la sesión, el sistema presentaba tres problemas activos en producción:

1. **Error `httpcore.LocalProtocolError`** por un carácter `\r\n` en el secret `ANTHROPIC_API_KEY` en Secret Manager, que impedía toda llamada a Claude API.
2. **Timeouts constantes en el endpoint MCP** (`⏰ MCP personalization timeout`) causados por `max_tokens=2000` en la configuración de Claude, que implicaba tiempos de generación de 8–65 segundos imposibles de cubrir con ningún timeout razonable.
3. **Timeouts adicionales en el Parallel Processor** por valores demasiado bajos en las tareas `mcp_recommendations` y `personalization`, independientes del timeout de `asyncio.wait_for`.

Al cierre de la sesión, los tres problemas están resueltos. El smoke test M3 alcanzó **19/19 checks (100%)** y el endpoint MCP respondió en **314ms** en la segunda ejecución gracias al cache de personalización.

---

## 2. Problemas Enfrentados

### Problema 1 — `httpcore.LocalProtocolError`: API key con `\r\n` al final

**Síntoma observado en logs de producción:**

```
httpcore.LocalProtocolError: Illegal header value
b'sk-ant-api03-...\r\n'
```

El error aparecía en los logs del keep-alive (PASO 8.6) y en cada intento de llamada a Claude API, enmascarado como `anthropic.APIConnectionError: Connection error.` — el mismo error genérico que existía antes de la sesión anterior, lo que dificultó su diagnóstico inicial.

**Causa raíz:** El secret `anthropic-api-key` en Google Cloud Secret Manager fue creado desde un entorno Windows (o con un editor que añade newline al guardar), por lo que el valor almacenado incluía `\r\n` al final. Cuando GCP inyecta ese valor como variable de entorno y Python lo lee con `os.getenv("ANTHROPIC_API_KEY")`, obtiene la key con `\r\n` al final. httpx rechaza enviar ese valor como cabecera HTTP porque `\r\n` es el delimitador de fin de cabecera en el protocolo HTTP/1.1 — su presencia dentro del valor constituye una inyección de cabecera potencialmente maliciosa.

**Impacto:** 100% de las llamadas a Claude API fallaban. El keep-alive (PASO 8.6) y el warm-up (PASO 8.5) también fallaban. La personalización MCP nunca llegaba a ejecutarse.

---

### Problema 2 — `⏰ MCP personalization timeout`: `max_tokens` demasiado alto

**Síntoma observado en logs de producción:**

```json
{"event": "⏰ MCP personalization timeout (8.0s) - using base recommendations",
 "processing_time_ms": 8097.05}
```

El error apareció consistentemente en las 5 ejecuciones de smoke test registradas durante la sesión (a las 11:40, 11:42, 11:43, 11:47, 11:48 y posteriormente).

**Causa raíz:** La configuración centralizada de Claude en `claude_config.py` definía `max_tokens=2000` para el modelo Sonnet. A una velocidad de generación de ~30–50 tokens/segundo, generar hasta 2.000 tokens implica entre 40 y 65 segundos de tiempo de respuesta. Ningún timeout de 3s, 8s, o incluso 30s puede ganar a eso en el peor caso.

Adicionalmente, el secret `CLAUDE_MAX_TOKENS` en Cloud Run Secret Manager sobreescribía silenciosamente el valor del código a través de la función `_apply_environment_overrides()` en `ClaudeConfigurationService`, con un valor de `2000`. Este mecanismo de override existía pero no tenía logging suficiente para hacerse visible.

**Impacto:** El endpoint MCP `/v1/mcp/recommendations/{product_id}` nunca devolvía respuestas personalizadas de Claude. Siempre caía al fallback de recomendaciones base.

---

### Problema 3 — Timeouts del Parallel Processor demasiado bajos

**Síntoma observado:** Persistencia del timeout incluso después de aumentar el `wait_for` de 3s a 8s, porque los `ParallelTask` del `parallel_processor.py` tenían sus propios timeouts independientes.

**Causa raíz:** En `execute_mcp_operations_parallel()` en `parallel_processor.py`, las tareas tenían:
- `ParallelTask("mcp_recommendations")` → `timeout=3.0s`
- `ParallelTask("personalization")` → `timeout=4.0s`

Estos timeouts actuaban en una capa previa al `asyncio.wait_for(timeout=8.0s)` del handler. Si cualquiera de los dos ParallelTask expiraba, devolvía `base_recommendations=[]` o `mcp_engine=None`, y la condición `if mcp_engine and mcp_context and base_recommendations` fallaba — el bloque del `wait_for` nunca se ejecutaba.

**Impacto:** Reforzaba el Problema 2, haciendo que el timeout ocurriera incluso antes de que Claude tuviera oportunidad de responder.

---

## 3. Soluciones Implementadas

### Solución 1 — Fix del `\r\n` en la API key

**Acción en código** (`src/api/factories/service_factory.py`):

```python
# Antes:
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

# Después:
# .strip() elimina defensivamente \r, \n, espacios y tabs al leer el secret.
anthropic_api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip() or None
```

**Acción en Secret Manager** (ejecución manual):

```bash
gcloud secrets versions access latest \
  --secret="anthropic-api-key" \
  --project=retail-recommendations-449216 | \
  tr -d '\r\n' | \
  gcloud secrets versions add "anthropic-api-key" \
    --project=retail-recommendations-449216 \
    --data-file=-
```

**Justificación técnica:** La corrección en código es la solución permanente y defensiva — protege contra futuros secretos creados con el mismo problema. La limpieza del secret en Secret Manager elimina la fuente del problema. Ambas son necesarias: la primera previene recurrencia, la segunda resuelve el estado actual.

**Resultado:** Keep-alive #2 OK en 2196ms, keep-alive #3 OK en 1201ms — confirmados en logs de producción.

---

### Solución 2 — Reducción de `max_tokens` a valores conversacionales

**Acción en código** (`src/api/core/claude_config.py`):

```python
# Antes:
ClaudeModelTier.HAIKU:  max_tokens=1000
ClaudeModelTier.SONNET: max_tokens=2000
ClaudeModelTier.OPUS:   max_tokens=4000

# Después:
ClaudeModelTier.HAIKU:  max_tokens=300   # respuesta conversacional breve
ClaudeModelTier.SONNET: max_tokens=500   # respuesta conversacional, no documento
ClaudeModelTier.OPUS:   max_tokens=800   # análisis, nunca usado en producción actualmente
```

**Acción en Secret Manager** (ejecución manual por Yasmani):

El secret `claude-max-tokens` fue actualizado manualmente de `2000` a `500`.

**Logging defensivo añadido** (`_apply_environment_overrides()` en `claude_config.py`): Se añadió un log explícito que emite el `max_tokens` efectivo al arrancar, con nivel `WARNING` si el secret sobreescribe el valor del código:

```
📊 claude_config_effective: model=claude-sonnet-4-20250514, max_tokens=500, temperature=0.7
```

Este log permite verificar en cualquier momento qué valor real está usando Claude en producción con la query de GCP Logs Explorer: `jsonPayload.event=~"claude_config_effective"`.

**Justificación técnica:** Una respuesta conversacional de recomendación de moda (2–4 oraciones) requiere entre 80 y 200 tokens de output. `max_tokens=2000` fue dimensionado para casos de análisis extensos, no para respuestas de chat. Con `max_tokens=500` y el modelo Sonnet a ~30–50 tokens/segundo, el tiempo de generación cae a 1–3 segundos, perfectamente manejable dentro del `wait_for(8.0s)`.

---

### Solución 3 — Corrección de timeouts en Parallel Processor

**Acción en código** (`src/api/core/parallel_processor.py`, función `execute_mcp_operations_parallel()`):

```python
# Antes:
ParallelTask("mcp_recommendations")  timeout=3.0s
ParallelTask("personalization")      timeout=4.0s

# Después:
ParallelTask("mcp_recommendations")  timeout=10.0s  # cubre diversificación + hybrid recommender
ParallelTask("personalization")      timeout=5.0s   # cubre inicialización del singleton
```

**Contexto de la corrección** (`src/api/core/mcp_conversation_handler.py`): El `asyncio.wait_for` alrededor de `generate_personalized_response()` también fue actualizado de `timeout=3.0` a `timeout=8.0` para alinear ambas capas.

**Justificación técnica:** Había dos capas de timeout independientes. La capa del Parallel Processor controla cuánto puede durar cada función wrapper antes de que el procesamiento paralelo la descarte. La capa del `wait_for` controla cuánto puede durar la llamada real a Claude. Si la primera capa expira primero, la segunda nunca se ejecuta. Los nuevos valores respetan la jerarquía correcta: `ParallelTask.timeout > wait_for.timeout` garantiza que la llamada a Claude tenga el presupuesto completo.

---

## 4. Componentes Modificados

| Archivo | Cambio aplicado | Impacto |
|---|---|---|
| `src/api/factories/service_factory.py` | `.strip()` defensivo en `ANTHROPIC_API_KEY` | Elimina `\r\n` antes de enviar el header HTTP |
| `src/api/core/claude_config.py` | `max_tokens`: 2000→500 (Sonnet), 1000→300 (Haiku), 4000→800 (Opus) | Reduce tiempo de generación de 8–65s a 1–3s |
| `src/api/core/claude_config.py` | Logging en `_apply_environment_overrides()` | Hace visible el `max_tokens` efectivo en producción |
| `src/api/core/parallel_processor.py` | `ParallelTask` timeouts: 3.0→10.0s y 4.0→5.0s | Evita que el processor mate tareas antes de que Claude responda |
| `src/api/core/mcp_conversation_handler.py` | `asyncio.wait_for` timeout: 3.0→8.0s | Permite a Claude completar la respuesta |
| Secret Manager `anthropic-api-key` | Recreado sin `\r\n` (acción manual) | La clave llega limpia al header HTTP |
| Secret Manager `claude-max-tokens` | Actualizado de `2000` a `500` (acción manual) | Alinea el secret con el código |

**Nota:** Los archivos `src/api/main_unified_redis.py` (PASO 8.5 warm-up y PASO 8.6 keep-alive) fueron modificados en la sesión anterior (16–17/03/2026) y estaban ya desplegados. Esta sesión los validó como funcionales tras corregir el error de la API key.

---

## 5. Resultados Obtenidos

### Estado final del sistema

| Componente | Estado antes de la sesión | Estado al cierre |
|---|---|---|
| Claude API (warm-up / keep-alive) | ❌ Falla con `\r\n` en API key | ✅ Keep-alive #2: 2196ms, #3: 1201ms |
| MCP personalization | ❌ Timeout constante (8097ms) | ✅ Cache hit: **314ms** |
| Endpoint `/v1/mcp/recommendations` | ❌ Siempre fallback (sin personalización) | ✅ Personalización real de Claude activa |
| Smoke test M3 (19 checks) | ❌ Errores en todos los runs | ✅ **19/19 — 100%** |
| `/v1/recommendations` (TF-IDF) | ✅ Funcional (no afectado) | ✅ 430ms promedio (5 requests) |
| Redis NoneType errors | ✅ Resuelto sesión anterior | ✅ Ausente en todos los logs |
| GCP Metrics export | ✅ Pipeline M3 operacional | ✅ 6 exports (metrics_count=111) |
| KB Background Sync | ✅ Funcional | ✅ Cycle 2 incremental: 0 cambios, 2.5s |

### Métricas de rendimiento observadas

| Métrica | Valor |
|---|---|
| MCP endpoint — primera request (cache miss) | ~7.8s (dentro del timeout de 8s) |
| MCP endpoint — segunda request (cache hit) | **314ms** |
| Recommendations endpoint — latencia promedio | **430ms** (5 requests) |
| Keep-alive Claude API — primera llamada post-deploy | 2196ms |
| Keep-alive Claude API — llamadas subsiguientes | ~1200ms |
| KB full sync (Cycle 1) | ~107s (sync inicial normal) |
| KB incremental sync (Cycle 2) | 2.5s (0 cambios detectados) |
| GCP Metrics export interval | ~60s |

### Cronología de resolución

```
09:32  Primera lectura de logs (revisión -00057-x4w) — error \r\n identificado
09:57  Deploy revisión -00058-cd6 con fix API key
10:00  Keep-alive #2 OK en 2196ms — confirmación del fix
11:18  Error MCP timeout (8.0s) identificado — causa: max_tokens=2000
12:28  Fix max_tokens en claude_config.py
12:28  Secret claude-max-tokens actualizado a 500 (acción manual de Yasmani)
12:55  Deploy revisión -00061-rmx
12:57  Smoke test run 1 — MCP: 7849ms (cache miss, pero 200 OK ✅)
13:00  Smoke test run 2 — MCP: **314ms** (cache hit ✅) — 19/19 ✅
```

---

## 6. Observaciones y Gaps

### 6.1 Latencia de primera request MCP (cache miss)

La primera llamada al endpoint MCP tras un deploy o tras la expiración del cache (TTL 5 minutos) tarda aproximadamente **7.8 segundos**. Este tiempo cubre:

- TCP/TLS handshake a `api.anthropic.com`: ~1.2–2.2s (mitigado por el keep-alive, pero la primera llamada real con prompt complejo es mayor que un ping)
- Generación de tokens por Sonnet con `max_tokens=500`: ~4–6s dependiendo del tamaño del prompt y carga del modelo

Aunque el sistema responde con HTTP 200 y personalización real de Claude, 7.8s es elevado para un endpoint de UX en producción. Las estrategias de mitigación se describen en la sección 8.

### 6.2 El secret `CLAUDE_MAX_TOKENS` como zona ciega

La función `_apply_environment_overrides()` en `ClaudeConfigurationService` permite que cualquier secret en Cloud Run sobreescriba silenciosamente `max_tokens`. Durante esta sesión, el secret tenía valor `2000` y hacía invisible el cambio en el código durante días. El logging defensivo añadido en esta sesión resuelve parcialmente esto, pero la arquitectura crea una tensión entre flexibilidad operacional y previsibilidad del código.

### 6.3 `CLAUDE_MAX_RETRIES=3` en la configuración

`get_anthropic_client_params()` devuelve `max_retries=3` por defecto (desde `CLAUDE_MAX_RETRIES` env var). Aunque el SDK de Anthropic gestiona estos reintentos internamente con backoff, en el contexto de Cloud Run con un `asyncio.wait_for` de 8s, múltiples reintentos pueden consumir el presupuesto de tiempo. Este valor no fue cambiado en esta sesión y merece revisión.

### 6.4 Scale-to-zero de Cloud Run

La decisión arquitectónica de mantener `min-instances=0` (sin instancias mínimas, por coste) implica que el warm-up y el keep-alive no sobreviven a los cold starts. Tras ~5 minutos de inactividad, Cloud Run termina la instancia y el siguiente request paga el coste completo de startup + warm-up de Claude. El keep-alive solo mantiene la conexión TCP activa mientras la instancia vive.

### 6.5 Alerta KB Sync — warning cosmético

La alerta `[WARNING] KB Sync Failures` en GCP Cloud Monitoring tiene un warning de unidades (`cast_units` no aplicado). Funciona correctamente a nivel de detección pero el log de GCP muestra la advertencia. Fix: `cast_units(val(), "") > 0.01`. No fue resuelto en esta sesión.

---

## 7. Consideraciones y Recomendaciones

### 7.1 Los secrets de Cloud Run son fuente de verdad en producción

**Lección aprendida:** Cualquier secret en Cloud Run Secret Manager que se mapee a una variable de entorno leída por `_apply_environment_overrides()` sobreescribe silenciosamente el valor del código. Cambiar el código sin cambiar el secret no tiene efecto en producción.

**Regla práctica:** Antes de cualquier cambio en parámetros de Claude (`max_tokens`, `model`, `temperature`), verificar el valor actual de los secrets correspondientes:

```bash
gcloud secrets versions access latest \
  --secret="claude-max-tokens" \
  --project=retail-recommendations-449216
```

### 7.2 Los secrets creados desde Windows contienen `\r\n`

**Lección aprendida:** Cualquier secret creado con `echo` en PowerShell/CMD, o copiado desde un editor Windows sin tratamiento especial, puede contener `\r\n` al final. Este carácter es invisible en los logs y en la UI de Secret Manager, pero causa `httpcore.LocalProtocolError` en httpx.

**Regla práctica:** Siempre crear secrets con `tr -d '\r\n'` o con `-n` en echo. Para actualizar:

```bash
echo -n "valor_sin_newline" | \
  gcloud secrets versions add "nombre-secret" \
  --project=retail-recommendations-449216 \
  --data-file=-
```

### 7.3 `max_tokens` debe calibrarse por caso de uso, no por capacidad del modelo

**Lección aprendida:** `max_tokens` no es un límite de seguridad — es el número máximo de tokens que Claude va a generar. Si el modelo genera habitualmente respuestas cortas pero `max_tokens` es alto, el tiempo de respuesta puede no verse afectado. Pero si el modelo intenta generar respuestas largas (como puede ocurrir con prompts que piden análisis detallados), el tiempo escala linealmente con `max_tokens`.

Para respuestas conversacionales de chat (2–4 oraciones), 200–500 tokens es suficiente y correcto. Para análisis o documentos, 800–2000 puede ser necesario. La configuración debe reflejar el caso de uso real, no el caso extremo teórico.

### 7.4 Los timeouts en capas independientes deben estar jerarquizados

**Lección aprendida:** El sistema tiene dos capas de timeout independientes para las operaciones MCP: el `ParallelTask.timeout` del Parallel Processor (capa 1) y el `asyncio.wait_for()` del handler (capa 2). Si la capa 1 expira antes que la capa 2, la capa 2 nunca se ejecuta. La jerarquía correcta es siempre `timeout_capa_1 > timeout_capa_2`.

**Regla práctica:** Al modificar cualquier timeout, verificar si existe una capa externa que pueda expirar antes.

### 7.5 Añadir logging de "punto de verdad" para parámetros críticos

**Lección aprendida:** El error de `max_tokens` persistió durante varios deploys porque no había ningún log que mostrara el valor efectivo que estaba usando Claude. El log `claude_config_effective` añadido en esta sesión resuelve eso.

**Regla práctica:** Para cualquier parámetro crítico que afecte latencia, costo o comportamiento, loguear explícitamente el valor efectivo (no el valor del código, sino el que realmente se usa) al arrancar el servicio, indicando la fuente (código vs secret vs env var).

---

## 8. Próximos Pasos

### 8.1 Estrategia A — Cambiar modelo a Haiku para personalización MCP ⚡ Alta prioridad

**Objetivo:** Reducir la latencia de primera request MCP de ~7.8s a ~1.5–2.5s.

**Justificación:** Haiku es 5–8x más rápido que Sonnet en generación de tokens. Para respuestas conversacionales de recomendación de moda (2–3 oraciones), la diferencia de calidad perceptible entre Haiku y Sonnet es mínima. La velocidad de respuesta tiene mayor impacto en UX que la riqueza del texto de recomendación.

**Implementación:**

```bash
# Opción 1: Variable de entorno en Cloud Run
gcloud run services update retail-recommender \
  --update-env-vars CLAUDE_MODEL_TIER=HAIKU \
  --region us-central1 \
  --project retail-recommendations-449216

# Opción 2: Secret (si CLAUDE_MODEL_TIER está mapeado como secret)
echo -n "HAIKU" | gcloud secrets versions add "claude-model-tier" \
  --project=retail-recommendations-449216 --data-file=-
```

**Latencia esperada con Haiku + max_tokens=300:** ~1.5–2.5s en cache miss.

---

### 8.2 Estrategia B — Reducir `max_tokens` a 200 ⚡ Alta prioridad

**Objetivo:** Reducción adicional de latencia sin cambiar de modelo.

**Justificación:** 500 tokens sigue siendo generoso. En producción, las respuestas reales de personalización son de 80–150 tokens. Reducir el límite a 200 reduce el tiempo de generación en el peor caso sin degradar las respuestas típicas.

**Implementación:**

```bash
echo -n "200" | gcloud secrets versions add "claude-max-tokens" \
  --project=retail-recommendations-449216 --data-file=-
```

**Nota:** Con Haiku (Estrategia A) + max_tokens=200, la latencia esperada de primera request baja a ~1.0–1.8s.

---

### 8.3 Estrategia C — Pre-warming del cache en startup 🔵 Media prioridad

**Objetivo:** Garantizar que la primera request real del usuario siempre sea un cache hit.

**Concepto:** Extender el PASO 8.5 (warm-up TCP) para también ejecutar `generate_personalized_response()` con datos ficticios durante el startup, cargando el resultado en el `personalization_cache` con TTL de 5 minutos. Si el primer request real del usuario llega dentro de esos 5 minutos, encontrará un cache hit y responderá en ~300ms.

**Implementación:** Añadir en el lifespan de `main_unified_redis.py`, después del PASO 8.5:

```python
# PASO 8.5b: Pre-warm personalization cache
try:
    logger.info("🔥 Pre-warming personalization cache...")
    dummy_context = MCPConversationContext(...)  # contexto vacío
    dummy_products = [...]  # muestra de 5 productos del catálogo
    await mcp_engine.generate_personalized_response(
        mcp_context=dummy_context,
        recommendations=dummy_products
    )
    logger.info("✅ Personalization cache pre-warmed")
except Exception as e:
    logger.warning(f"⚠️ Cache pre-warm failed (non-critical): {e}")
```

---

### 8.4 Estrategia D — Streaming de respuestas Claude 🔵 Largo plazo

**Objetivo:** Reducir la latencia percibida de 7.8s a ~300ms mostrando tokens progresivamente.

**Concepto:** En lugar de esperar el mensaje completo de Claude, usar `client.messages.stream()` y enviar los tokens al frontend via Server-Sent Events (SSE) a medida que se generan. El usuario ve texto aparecer desde los primeros 300ms aunque el mensaje completo tarde 7 segundos.

**Requisitos:** Cambios en el endpoint MCP para soporte SSE, y soporte en el frontend para consumir streams. Es un cambio arquitectónico significativo — se recomienda como mejora planificada, no como hotfix.

---

### 8.5 Fixes menores pendientes

| Acción | Prioridad | Archivo / Ubicación |
|---|---|---|
| Fix cosmético alerta KB Sync: `cast_units(val(), "") > 0.01` | Baja | GCP Cloud Monitoring — Alerta `[WARNING] KB Sync Failures` |
| Revisar `CLAUDE_MAX_RETRIES=3` y evaluar reducción a 1 en contexto de Cloud Run | Media | `claude_config.py` / env var Cloud Run |
| Consolidar ~400KB de código muerto (archivos `main_*.py` variants, módulos duplicados) | Media | `src/api/` — previo a inicio de L4 |
| Planificar inicio de **L4 ML Content Optimization** (~26 Marzo 2026) | Planificación | Requiere ≥3 semanas de historial en `kb_content_versions` |
| Verificar instrumentación del timer en `ShopifyKBSyncService` | Baja | `src/api/services/shopify_kb_sync.py` — chart KB Sync Duration p95 vacío |

---

## Apéndice — Arquitectura de timeouts post-sesión

```
Request → /v1/mcp/recommendations/{product_id}
           │
           ▼
   mcp_conversation_handler.py
   ├── [FASE 3] execute_mcp_operations_parallel()
   │       ├── ParallelTask("mcp_recommendations")   timeout=10.0s
   │       ├── ParallelTask("personalization")        timeout=5.0s
   │       └── ParallelTask("market_context")         timeout=3.0s
   │
   └── [FASE 4] asyncio.wait_for(
               generate_personalized_response(),
               timeout=8.0s              ← siempre < ParallelTask.timeout
           )
```

**Jerarquía correcta:** `ParallelTask.timeout (10s) > wait_for.timeout (8s)` garantiza que el presupuesto de tiempo de Claude no sea interrumpido prematuramente por el Parallel Processor.

---

## Apéndice — Query de verificación post-deploy

Para confirmar que el sistema está usando la configuración correcta tras cualquier deploy:

```
# En GCP Logs Explorer
resource.type="cloud_run_revision"
jsonPayload.event=~"claude_config_effective"
```

Resultado esperado:
```json
{
  "event": "📊 claude_config_effective: model=claude-sonnet-4-20250514, max_tokens=500, temperature=0.7"
}
```

Si `max_tokens` muestra un valor distinto de 500 (o del valor esperado), un secret en Cloud Run está sobreescribiendo la configuración del código.

---

*DCT — Sesión 20 de Marzo de 2026 | Retail Recommender System v2.1.0 | Versión 1.0*
