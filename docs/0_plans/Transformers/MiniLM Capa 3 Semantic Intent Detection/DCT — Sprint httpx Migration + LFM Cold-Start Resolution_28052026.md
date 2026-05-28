# DCT — Sprint httpx Migration + LFM Cold-Start Resolution
**Fecha de cierre:** 28/05/2026  
**Revisión desplegada:** `retail-recommender-00196-29d`  
**Sistema:** Retail Recommender System v2.1.0  
**Archivos modificados:** `src/api/integrations/shopify_client.py`, `src/api/main_unified_redis.py`, `src/api/mcp/engines/mcp_personalization_engine.py`, `src/api/core/mcp_conversation_handler.py`, `src/api/routers/visual_search_router.py`

---

## Contexto y problema original

Ante el despliegue de la integración de LFM (Liquid AI vía OpenRouter/Together.ai), el sistema presentaba tres problemas simultáneos que bloqueaban el flujo conversacional:

1. **lazy-price timeout permanente**: `asyncio.to_thread(requests.post)` no podía cancelarse limpiamente. Cada cancelación por `asyncio.wait_for(5s)` dejaba el pool de conexiones de `requests` en estado indeterminado. La siguiente llamada siempre era una cold connection (~10.5s), superando el timeout de 5s. Todos los turns terminaban con `[lazy-price] Timeout (5s)` y precios CLP_RATES fallback.

2. **LFM cold-start de ~11-12s**: Together.ai descarga el modelo de GPU tras inactividad. La primera llamada tras startup o inactividad tardaba 11-12s, superando el timeout configurado. El sistema caía a Claude fallback (que tampoco funcionaba por crédito agotado), devolviendo una respuesta genérica de 57 caracteres.

3. **Claude fallback con 3 retries innecesarios**: Error HTTP 400 por crédito Anthropic agotado es permanente. El código hacía 3 reintentos (~580ms) sin beneficio.

**Métricas de línea base (pre-sprint):**
- Turn con lazy-price: **12.7s** (siempre timeout)
- Turn con F-01 + product_context: **22.1s** (10s product_context + 5s lazy-price + 7s Claude retries)
- LFM: timeout en 100% de los turns fríos

---

## Diagnóstico técnico

### Root cause 1: `asyncio.to_thread(requests.post)` — pool envenenado

```
asyncio.wait_for(get_prices_for_products(), timeout=5.0)
       │
       │  [5s] asyncio.TimeoutError → función retorna ✅
       │
       │  PERO el thread sigue con requests.post hasta los 30s
       │  Connection del thread queda en estado INDETERMINADO
       │  requests.Session guarda esa conexión como 'disponible'
       └→ Siguiente llamada reutiliza conexión rota → cold start siempre
```

Confirmado con 3 consultas sucesivas (Turn 1: 52s gap, Turn 2: 43s gap) — todas cold.

### Root cause 2: LFM cold-start en Together.ai (dos capas)

OpenRouter logs confirmaron solo 2 de 3 requests llegaban a OpenRouter:
- **Turn 1** (04:13 PM): NO llegó a OpenRouter — TCP/TLS a OpenRouter no establecido
- **Turn 2** (04:14 PM): SÍ llegó a OpenRouter — Together.ai tardó >8s en cargar el modelo
- **Turn 3** (04:15 PM): 419ms — modelo ya cargado

Dos capas de cold-start:
1. Conexión TCP/TLS al endpoint OpenRouter (primera llamada)
2. Carga del modelo LFM en GPU de Together.ai (~11-12s tras inactividad)

### Root cause 3: Timeout ordering interior/exterior

El outer timeout en `mcp_conversation_handler.py` era 12s desde el inicio del flow. El inner LFM timeout era también 12s pero comenzaba 0.6s después (post lazy-price). Resultado: el outer (12s desde start) disparaba antes que el inner (12.6s desde start), y el código de skip-Claude nunca ejecutaba.

---

## Implementación

### Fix 1 — httpx migration en `shopify_client.py` (fix quirúrgico y luego migración completa)

**Fase 1 (prueba mínima):** Solo `get_prices_for_products` migrado a `httpx.AsyncClient` singleton. Resultados validados: cold connection 10.5s → 820ms con httpx.

**Fase 2 (migración completa):** Todos los métodos async de `ShopifyIntegration`:

| Método | Antes | Después |
|---|---|---|
| `get_prices_for_products` | `asyncio.to_thread(requests.post, timeout=10)` | `httpx.AsyncClient` singleton |
| `get_product_context_by_handle` REST | `asyncio.to_thread(_make_request_with_retry)` | `httpx.get()` |
| `get_product_context_by_handle` GraphQL | `asyncio.to_thread(requests.post, timeout=5)` | `httpx.post()` |
| `_graphql_query` | `asyncio.to_thread(requests.post, timeout=30)` | `httpx.post()` |
| `_graphql_query_with_retry` | `asyncio.to_thread(requests.post, timeout=30)` + `requests.exceptions` | `httpx.post()` + `_httpx` exceptions |

**Patrón del singleton:**
```python
_shopify_httpx_client: \"_httpx.AsyncClient | None\" = None

def _get_shopify_httpx_client() -> \"_httpx.AsyncClient\":
    global _shopify_httpx_client
    if _shopify_httpx_client is None:
        _shopify_httpx_client = _httpx.AsyncClient(
            timeout=_httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0),
            limits=_httpx.Limits(
                max_keepalive_connections=5,
                max_connections=10,
                keepalive_expiry=30.0,
            ),
        )
    return _shopify_httpx_client
```

### Fix 2 — Outfit carousel precios Shopify en `visual_search_router.py`

Estructura de tres fases:
1. **Fase 1**: Redis lookup para todos los PIDs del outfit
2. **Fase 2**: `get_prices_for_products` con httpx para cache misses (timeout 5s)
3. **Fase 3**: Build respuesta con precios reales (fallback CLP_RATES si timeout)

Log de validación: `outfit_prices_from_shopify products=16 market_id=CH`

### Fix 3 — LFM fallback limpio en `mcp_personalization_engine.py`

```python
_lfm_failed = False
if self._lfm_mcp_enabled and self._lfm_client:
    try:
        resp = await asyncio.wait_for(
            self._lfm_client.complete(system_prompt, user_prompt),
            timeout=10.0
            # Inner: 10s desde LFM start = 10.6s desde outer start
            # Outer: 12s desde outer start → inner dispara PRIMERO
        )
        return resp.content
    except Exception as e:
        logger.warning('LFM MCP call failed, falling back to Claude: %s', e)
        _lfm_failed = True

# TEMPORAL: skip Claude cuando LFM falla y Claude sin crédito
if _lfm_failed:
    logger.info(\"lfm_failed_claude_skipped: LFM timeout + Claude sin credito (400). \"
                \"TEMPORAL: eliminar cuando se integre el modelo de reemplazo.\")
    return \"Te ayudo a encontrar lo que buscas. ¿Qué te interesa hoy?\"
```

**Fix adicional en Claude retry loop:**
```python
except Exception as api_error:
    if hasattr(api_error, 'status_code') and api_error.status_code == 400:
        logger.warning(\"Claude billing error (400) — skipping remaining retries.\")
        break  # No reintentamos — el error 400 es permanente
    if attempt < max_retries:
        await asyncio.sleep(0.05)
```

### Fix 4 — LFM warmup (PASO 8.5c) en `main_unified_redis.py`

Path corregido de `app.state.mcp_recommender._personalization_engine` (inexistente) a `ServiceFactory.get_mcp_recommender()` (correcto).

```python
async def _warmup_lfm_connection() -> None:
    await asyncio.sleep(8.0)
    engine = await ServiceFactory.get_mcp_recommender()
    if not (engine and engine._lfm_mcp_enabled and engine._lfm_client):
        return
    resp = await asyncio.wait_for(
        engine._lfm_client.complete(\"Eres un asistente util.\", \"Responde hola.\"),
        timeout=14.0  # Acepta cold-start completo (~11-12s)
    )
```

### Fix 5 — LFM keep-alive periódico (PASO 8.7) en `main_unified_redis.py`

Background task que pinga LFM cada 300s (5 min) para mantener el modelo cargado en GPU de Together.ai:

```python
LFM_KEEPALIVE_INTERVAL_S = 300  # 5 minutos entre pings
# Costo: ~$0.000026/ping × 12 pings/hora × 24h = ~$0.0075/día
# Timeout: 15s (acepta cold-start inesperado sin romper el loop)
```

**Shutdown limpio añadido:**
```python
if lfm_keepalive_task is not None and not lfm_keepalive_task.done():
    lfm_keepalive_task.cancel()
    await asyncio.gather(lfm_keepalive_task, return_exceptions=True)
```

### Fix 6 — Documentación actualizada en tres archivos

| Archivo | Líneas | Cambio |
|---|---|---|
| `mcp_personalization_engine.py` | 1435-1447 | Documentación del ordering inner/outer timeout con evidencia 26/05/2026 |
| `main_unified_redis.py` | 1352-1355 | Referencia a PASO 8.7 como complemento del warmup |
| `mcp_conversation_handler.py` | ~L1336 | Historial timeout actualizado: `8.0s→12.0s` con justificación correcta |

---

## Resultados validados en logs (Rev 00196-29d, 28/05/2026)

### Startup

| Componente | Tiempo | Estado |
|---|---|---|
| MiniLM warmup | 13.587s (ONNX load) | ✅ |
| Shopify prices warmup | 910ms (httpx pool warm) | ✅ |
| LFM warmup | **3s** (modelo ya cargado) | ✅ |
| LFM keep-alive PASO 8.7 | Started ✅, First ping 6.348s | ✅ |

### Consultas

| Turn | lazy-price | F-01 | LFM | Total | Mejora |
|---|---|---|---|---|---|
| 1 (no F-01) | 680ms | — | 450ms | **2.215s** | 77.8% |
| 2 (F-01) | 356ms | 350ms | 280ms | **1.612s** | 83.9% |
| 3 (F-01) | 389ms | 680ms | 360ms | **2.145s** | 78.5% |

**Todos los turns: precios reales Shopify CHF. Cero timeouts. 8 IDs almacenados por turn.**

### Diversificación multi-turno confirmada

```
Turn 1: 8 IDs almacenados
Turn 2: shown_products=8 (Turn 1), excluidos correctamente
Turn 3: shown_products=16 (Turn 1 + Turn 2), excluidos correctamente
```

### GUARD intent detector

```
Turn 2: ML quiso cambiar TRANSACTIONAL→INFORMATIONAL (92.7% confidence)
        GUARD: rule-based tenía patrón real → mantiene TRANSACTIONAL ✅
```

---

## Problemas conocidos y gaps para próximas sesiones

### Gap 1 — Precios sospechosos en diversificación (ALTA)

**Síntoma:** Turns 2 y 3 muestran precios como `0.01 CHF`, `3.0 CHF` en las recomendaciones diversificadas.

**Causa raíz:** Al diversificar con exclusión de 8+ productos ya vistos, el algoritmo selecciona de 40+ categorías distintas incluyendo accesorios de bajo precio (AROS, CLUTCH, BRAZALETES). La conversión CLP→CHF de estos productos produce valores mínimos.

**Impacto UX:** El usuario pide \"similares a este conjunto\" y recibe accesorios de 0.01 CHF.

**Solución propuesta:** Cuando hay `current_product_context`, la diversificación de Turns 2+ debería priorizar productos de la misma categoría y colecciones antes de diversificar hacia otras categorías.

### Gap 2 — `price_clp=10` en cálculo de upsell F-01 (MEDIA)

**Síntoma:** `F-01 upsell tier_instruction_active=False ltv_tier=anon price_clp=10` — el precio mostrado es 10 CLP cuando el producto vale ~112 CHF.

**Causa:** El campo de precio leído por el upsell engine no toma el valor de `product_context.get('price')` sino un valor por defecto.

**Impacto:** El tier de upsell no se calcula correctamente para usuarios anónimos en páginas de producto.

### Gap 3 — Visual search precios incorrectos (MEDIA)

**Síntoma:** `/v1/mcp/visual-search` muestra valores CLP con símbolo `€` (ej. `74,990.00 €`) en mercado CH.

**Causa:** El endpoint no tiene market adaptation. No usa httpx ni el lazy-price pipeline.

**Solución propuesta:** Añadir market adaptation al endpoint de visual search, reutilizando el mismo patrón que el outfit carousel.

### Gap 4 — LFM keep-alive #1 tardó 6.348s (BAJA)

**Observación:** El primer ping del keep-alive (41 segundos después del último LFM call real) tardó 6.348s.

**Causa:** Variabilidad de latencia de Together.ai incluso con modelo warm.

**Impacto:** Ninguno en producción — dentro del timeout de 15s. El keep-alive cumplió su función.

### Gap 5 — Startup: 3 minutos 21 segundos (BAJA)

**Causa:** PostgreSQL pool creation (~84s) + Shopify KB sync (~45s). Pre-existente.

**Impacto:** Cloud Run cold-start visible en despliegues nuevos. No afecta instancias calientes.

---

## Arquitectura de timeouts — estado final

```
[mcp_conversation_handler.py]
asyncio.wait_for(generate_personalized_response(), timeout=12.0)
  ├── lazy-price: ~0.6s (httpx warm)
  └── LFM: asyncio.wait_for(lfm.complete(), timeout=10.0)
         │  Cold-start (>10s): inner dispara a 10.6s < outer 12s ✅
         │  Warm: ~280-450ms
         └── Si falla: _lfm_failed=True → skip Claude → respuesta default

[main_unified_redis.py]
PASO 8.5c: LFM warmup al startup (timeout=14s, sleep=8s)
PASO 8.7:  LFM keep-alive periódico (interval=300s, timeout=15s)
```

---

## Aprendizajes de arquitectura

1. **`asyncio.to_thread(requests.post)` nunca es cancelable limpiamente.** Si la función está en un camino crítico con `asyncio.wait_for`, usar `httpx.AsyncClient` (nativo async). El pool de `requests` queda envenenado con cada cancelación.

2. **Cold-start externo tiene dos capas.** Para servicios como Together.ai: (a) TCP/TLS al endpoint del proxy, (b) carga del modelo en GPU del proveedor final. Un warmup al startup resuelve ambas. Un keep-alive periódico evita la regresión.

3. **El ordering interior/exterior de `asyncio.wait_for` importa.** Si el inner timeout empieza 0.6s después del outer, debe ser al menos 1.4s más corto para disparar primero. (outer=12s, lazy-price=0.6s → inner≤10.6s → elegimos 10s).

4. **Errores HTTP 400 de billing son permanentes.** El código de retry loop debe distinguir errores transitorios (429, 5xx) de permanentes (400 billing) para no desperdiciar tiempo.

5. **El path a singletons debe verificarse con logs de producción.** `app.state.mcp_recommender._personalization_engine` no existía — solo `ServiceFactory.get_mcp_recommender()` retorna el engine directamente. Siempre confirmar antes de usar en código de warmup.

---

## Próximos pasos

1. **Integrar modelo alternativo a Claude** — cuando esté disponible, reemplazar el bloque `if _lfm_failed` TEMPORAL y eliminar el skip de Claude
2. **Fix `price_clp=10` en upsell F-01** — leer precio desde `product_context`
3. **Revisar estrategia de diversificación con F-01** — priorizar misma categoría/colecciones del producto actual antes de diversificar
4. **Market adaptation en visual search** — reutilizar patrón outfit carousel
5. **Activar PASO 8.6 (Claude keep-alive)** — cuando se integre el modelo alternativo con créditos"