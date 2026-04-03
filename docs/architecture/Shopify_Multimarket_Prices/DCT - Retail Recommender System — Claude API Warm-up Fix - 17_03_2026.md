# DCT — Retail Recommender System — Claude API Warm-up Fix — 17_03_2026

# Documento de Continuidad Técnica

## Retail Recommender System v2.1.0 — Sesión 16-17/03/2026

> **Estado al cierre:** Todos los fixes aplicados localmente. Pendiente deploy final para validar warm-up de Claude API.
> 

---

## 🚀 PROMPT DE CONTINUIDAD — PEGAR EN NUEVA SESIÓN

```
Contexto: Estamos trabajando en el Retail Recommender System v2.1.0, desplegado en Cloud Run (retail-recommender-lzf2y6pspa-uc.a.run.app), proyecto GCP retail-recommendations-449216.

Última sesión (16-17/03/2026): Sesión intensiva de diagnóstico y fixes post-M3. Se resolvieron 3 problemas críticos en producción. Quedó pendiente validar el último fix tras deploy.

Problema activo: El endpoint MCP /v1/mcp/recommendations/{product_id} siempre responde en ~3.3s (timeout de 3.0s) en lugar de <2s. El fix aplicado (warm-up de Claude API en startup) está en el código local pero NO ha sido desplegado aún.

Por favor lee el documento de continuidad en Notion titulado "DCT — Retail Recommender System — Claude API Warm-up Fix — 17_03_2026" para obtener el contexto completo antes de continuar.
```

---

## 1. Archivos modificados en esta sesión (todos locales, pendientes de deploy)

| Archivo | Cambio | Estado |
| --- | --- | --- |
| `src/api/factories/service_factory.py` | `get_db_pool()` — usa `os.environ` con fallback a settings | ✅ Validado en producción |
| `src/api/factories/service_factory.py` | `get_mcp_recommender()` — pasa `anthropic_client` al constructor | ✅ Sin NoneType errors |
| `src/api/factories/service_factory.py` | `get_mcp_recommender()` — `http2=False`  • `httpx.Timeout` explícito | ⚠️ No resolvió el problema |
| `src/api/mcp/engines/mcp_personalization_engine.py` | `asyncio.sleep(1s) → sleep(0.05s)` en retry loop | ✅ Confirmado en logs (gap=1.553s) |
| `src/api/core/mcp_conversation_handler.py` | `prepare_mcp_engine()` usa singleton del ServiceFactory | ✅ Bajó 3320ms→355ms (1 vez) |
| `src/api/core/mcp_conversation_handler.py` | Timeout mensaje corregido "1.5s"→"3.0s" | ✅ |
| `src/api/core/0_legacy/claude_optimization.deprecated.py` | Archivo movido desde core/ | ✅ |
| `src/api/main_unified_redis.py` | **PASO 8.5: Warm-up Claude API en startup** | ⏳ PENDIENTE DEPLOY |

---

## 2. Diagnóstico definitivo del problema de Claude API

### Causa raíz confirmada

`AsyncAnthropic` establece conexiones TCP/TLS de forma **lazy** (solo en la primera llamada real). En Cloud Run, ese primer intento tarda sistemáticamente ~1.5s y falla con `"Connection error"`. El `asyncio.wait_for(timeout=3.0)` del handler se agota porque:

```
T+0.0s   generate_personalized_response() inicia
T+~1.5s  Intento 1: "Connection error" (TCP handshake falla)
T+0.05s  sleep(50ms) — reducido de 1s
T+~1.5s  Intento 2: "Connection error" (mismo problema)
T+3.0s   wait_for timeout → "⏰ MCP personalization timeout (3.0s)"
T+3.3s   HTTP 200 con base recommendations (sin personalización Claude)
```

### Por qué http2=False NO funcionó

El problema ocurre a nivel **TCP connect**, antes de que el protocolo HTTP se negocie. HTTP/1.1 vs HTTP/2 es irrelevante en este punto.

### Evidencia del patrón

- La **única vez** que el MCP respondió en 355ms fue en el RUN 2 del deploy 21:17 — inmediatamente después de que el RUN 1 estableció una conexión parcial durante el cold start.
- **Todos los demás deploys** siempre dan ~3.3s = exactamente el timeout de 3.0s + 0.3s overhead.
- El singleton existe en memoria pero la conexión TCP **no persiste entre requests** en Cloud Run (NAT cierra estados inactivos).

### Solución implementada (PASO 8.5 en main_unified_[redis.py](http://redis.py))

```python
# Durante el startup (lifespan), después de crear el singleton:
if app.state.mcp_recommender and app.state.mcp_recommender.claude:
    await asyncio.wait_for(
        app.state.mcp_recommender.claude.messages.create(
            model="claude-haiku-4-5-20251001",  # Haiku: más rápido para warm-up
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}]
        ),
        timeout=15.0
    )
    # Logs: "✅ Claude API connection warmed up in Xms"
```

**Por qué funciona:** Establece el TCP/TLS durante el startup donde hay presupuesto de tiempo, manteniendo la conexión warm para los requests reales.

---

## 3. Fixes validados en producción

### Fix A — DB pool usa os.environ (VALIDADO ✅)

**Síntoma resuelto:** `[Errno 111] Connection refused` → Pool se conectaba a `localhost` porque `settings.db_host` devolvía el default de Pydantic.

**Evidencia:** KB sync bajó de **~184s → ~7s** (reduce de sync completo a tiempo normal). Error cambió de `ECONNREFUSED` a `health_check_slow_response` (host correcto, latencia variable de Neon).

**Archivo:** `src/api/factories/service_factory.py` → `get_db_pool()`

```python
# Leer con prioridad a os.environ (garantía Cloud Run)
db_host = os.environ.get("DB_HOST") or settings.db_host
db_port = int(os.environ.get("DB_PORT", str(settings.db_port)))
# ... etc
```

### Fix B — sleep 50ms en retry (VALIDADO ✅)

**Síntoma resuelto:** El `asyncio.sleep(1)` consumía el presupuesto de 3.0s antes de que el reintento pudiera completarse.

**Evidencia en logs:** MCP Call #2 muestra gap exacto de `1.553s` entre attempt 1 y attempt 2 (era `>2.5s` antes).

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py` líneas 1228 y 1237

```python
# Antes:
await asyncio.sleep(1)  # consumía presupuesto
# Después:
await asyncio.sleep(0.05)  # libera socket sin consumir presupuesto
```

### Fix C — anthropic_client en singleton (VALIDADO ✅)

**Síntoma resuelto:** `NoneType object has no attribute 'messages'` — `get_mcp_recommender()` creaba el engine sin pasar el cliente Anthropic.

**Archivo:** `src/api/factories/service_factory.py` → `get_mcp_recommender()`

---

## 4. Próxima acción — Deploy y validación del warm-up

### Paso 1: Deploy

```bash
gcloud run deploy retail-recommender \
  --source . \
  --region us-central1 \
  --project retail-recommendations-449216
```

### Paso 2: Verificar en Cloud Logging que el warm-up funcionó

Buscar en los logs de startup (~1-2 min después del deploy):

```
🔥 Warming up Claude API connection (TCP/TLS handshake)...
✅ Claude API connection warmed up in <X>ms — TCP/TLS established
```

Si aparece `⚠️ Claude API warm-up failed` o `⚠️ Claude API warm-up timeout`, el warm-up no funcionó y hay que investigar por qué.

### Paso 3: Smoke test y validar B4.3

```powershell
.\tests\smoke\smoke_observability_M3.ps1 -Verbose
```

**Objetivo:** Bloque 4.3 MCP endpoint < 2000ms (era ~3300-3500ms antes)

### Paso 4: Si warm-up no funciona — Plan B

Si el warm-up también falla (timeout de 15s durante startup), hay que investigar si Cloud Run tiene restricciones de egress en los primeros segundos del arranque. En ese caso, la alternativa es aumentar el timeout externo a 8-10s (no recomendado para UX) o configurar `min-instances=1` para evitar cold starts.

---

## 5. Estado de issues conocidos

| Issue | Estado | Notas |
| --- | --- | --- |
| DB pool ECONNREFUSED | ✅ RESUELTO | KB sync: 184s→7s |
| NoneType claude client | ✅ RESUELTO | Sin más errores NoneType |
| sleep(1s) retry | ✅ RESUELTO | gap=1.553s confirmado |
| Claude Connection error / MCP timeout | ⏳ PENDIENTE | Fix: warm-up startup (PASO 8.5) |
| KB errors (kb_upsert_failed) | ⚠️ TRANSITORIO | Solo aparece en primer KB sync; relacionado con Neon latencia |
| Redis slow response (1599ms ping) | ⚠️ MONITOREAR | Redis Enterprise con latencia alta en períodos inactivos |
| GCP dashboards sin datos | ✅ RESUELTO (M3) | [custom.googleapis.com/](http://custom.googleapis.com/) metrics activas |

---

## 6. Arquitectura del fix de Claude API — explicación pedagógica

> 💡 **Para entender por qué la misma solución puede funcionar o no en distintos entornos:**
> 

El `AsyncAnthropic` client usa `httpx.AsyncClient` internamente, que mantiene un **pool de conexiones** TCP por hostname. Este pool es lazy por defecto — no abre ninguna conexión hasta que se hace la primera llamada.

En **local (desarrollo):** La primera llamada tarda ~300ms pero rara vez falla porque la red local es estable y el timeout de connect de httpx por defecto (~5s) da tiempo suficiente.

En **Cloud Run:** El NAT de GCP cierra estados TCP salientes inactivos agresivamente. Cuando el primer request llega al endpoint MCP, el client intenta establecer TCP a `api.anthropic.com:443` — pero Cloud Run puede tardar ~1.5s en establecer el NAT mapping inicial, y httpx tiene un comportamiento de connect que puede fallar antes de ese tiempo.

El **warm-up durante startup** resuelve esto porque:

1. Se ejecuta cuando el sistema ya tiene recursos disponibles
2. Tiene 15s de presupuesto (vs 3s en requests reales)
3. Establece el NAT mapping de GCP
4. El `httpx.AsyncClient` mantiene la conexión en su pool por defecto durante 30s
5. Cuando llega el primer request real, la conexión ya existe → ~1.5-2s de tiempo de respuesta Claude normal

---

## 7. Contexto del proyecto para nuevas sesiones

- **Proyecto:** `C:\Users\yasma\Desktop\retail-recommender-system\`
- **Deploy activo:** Cloud Run `retail-recommender-lzf2y6pspa-uc.a.run.app`
- **GCP Project:** `retail-recommendations-449216`
- **Entry point:** `src/api/main_unified_redis.py`
- **ServiceFactory:** `src/api/factories/service_factory.py`
- **MCP Engine:** `src/api/mcp/engines/mcp_personalization_engine.py`
- **MCP Handler:** `src/api/core/mcp_conversation_handler.py`

### Principios de trabajo establecidos

1. **Leer antes de modificar** — siempre verificar el archivo real antes de editar
2. **Un fix a la vez** — validar cada cambio antes del siguiente
3. **Evidence-based** — toda conclusión basada en logs/código, no suposiciones
4. **GCP dashboards** — siempre usar Builder visual mode, nunca el editor de código
5. **os.environ vs settings** — en Cloud Run, siempre `os.environ.get("KEY") or settings.field`

### Próximas fases planificadas

- **Dead code consolidation:** ~400KB de código muerto (`main_*.py` variants, módulos duplicados)
- **L4 (ML Content Optimization):** Deferred hasta que `kb_content_versions` tenga suficientes datos históricos
- **M5 (Alembic Migrations):** Groundwork analizado pero no implementado

---

## 8. Logs de referencia para diagnóstico futuro

### Logs de startup esperados tras el warm-up

```json
{"event": "🔥 Warming up Claude API connection (TCP/TLS handshake)...", "level": "info"}
{"event": "✅ Claude API connection warmed up in 2341ms — TCP/TLS established", "level": "info"}
```

### Logs de problema — si warm-up falla

```json
{"event": "⚠️ Claude API warm-up failed: Connection error — first MCP request may timeout", "level": "warning"}
```

### Logs de éxito en requests MCP

Sin logs de `"Connection error on attempt 1"` ni `"MCP personalization timeout (3.0s)"` → personalización real de Claude activa.

### Logs de DB pool (referencia)

```json
{"event": "🔒 ServiceFactory DB pool: host=<neon-endpoint>.neon.tech, port=5432, db=..., ssl=require"}
{"event": "✅ PostgreSQL pool initialized via ServiceFactory (ssl=require)"}
```

[DCT — Sistema Conversacional — Estabilización y Fixes — 27_03_2026](DCT%20%E2%80%94%20Sistema%20Conversacional%20%E2%80%94%20Estabilizaci%C3%B3n%20y%20Fi%20330cfd3fcb2881988987eb5f13582e9a.md)