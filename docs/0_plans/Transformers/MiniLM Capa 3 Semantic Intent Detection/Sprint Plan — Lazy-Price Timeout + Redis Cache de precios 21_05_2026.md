# Sprint Plan — Lazy-Price Timeout + Redis Cache de Precios — 21_05_2026

**Estado:** 🟡 PLANIFICADO — listo para ejecutar

**Prioridad:** Alta — resuelve G-01 y G-02 simultáneamente

**Dependencias:** Ninguna (no requiere webhook ni cambio de infraestructura)

**Archivos críticos:** `mcp_personalization_engine.py` (~212KB — leer en secciones), `visual_search_router.py`

**Referencia arquitectónica:** `docs\architecture\Shopify_Multimarket_Prices\Lazy Resolution\` (02/03/2026 y 03/04/2026)

---

## 1. Diagnóstico confirmado

### El problema: lazy-price sin timeout ni cache

Logs de producción (21/05/2026, rev 00186) muestran el patrón exacto:

```
[13:20:17.98] SSLError: TLSV1_ALERT_DECODE_ERROR (Shopify SSL intermitente)
[13:20:26.13] [lazy-price] Consultando Shopify para 8 productos (mercado: CH)...
[13:20:38.12] ⏰ MCP personalization timeout (8.0s) — using base recommendations
```

Breakdown del problema en 3 capas:

**Capa 1 — Sin timeout en lazy-price:** `_enrich_recommendations_lazy()` llama a `get_prices_for_products()` sin timeout propio. Cuando Shopify tiene SSL errors y reintentos, el proceso espera 11-12 segundos. El único límite es el timeout de personalización (8s), que ya está agotado cuando Shopify por fin responde.

**Capa 2 — Sin memoria entre requests:** Los precios se guardan en RAM por producto (tras el primer fetch). Pero con `min-instances=0`, cada instancia nueva empieza vacía. Dos instancias distintas pagan el costo Shopify independientemente.

**Capa 3 — Outfit endpoint sin acceso a precios Shopify:** El carousel de outfit no llama a lazy-price (latencia inaceptable para un endpoint que debe responder en < 500ms) y usa tasas fijas CLP_RATES como fallback permanente.

### Por qué esta solución (y no otras)

La arquitectura de 3 fases documentada el 02/03/2026 es la correcta. El pre-calentamiento batch al startup (PASO 4.5, desactivado 21/04/2026) fue descartado por las razones correctas: precalentaba 3.062 × 4 = 12.248 precios cuando por sesión se usan 12-20. Redis TTL lazy es superior en todos los ejes.

---

## 2. Solución: 4 partes coordinadas

```
Parte A: Timeout en la llamada Shopify (fix al síntoma, riesgo cero)
  _enrich_recommendations_lazy() → asyncio.wait_for(shopify_call, timeout=5.0)
  Si expira: log lazy_price_timeout, continuar con CLP_RATES

Parte B: Redis write después de cada lazy-price exitoso (fix a la raíz)
  Por cada producto enriquecido: redis.set("price:{id}:{market}", data, ex=3600)
  Primera request: Shopify (200-500ms cuando está sano)
  Segunda request en adelante (cualquier instancia): Redis HIT ~1ms

Parte C: Redis lookup al inicio de lazy-price (skip Shopify si ya está cacheado)
  Al inicio de _enrich_recommendations_lazy(), por cada producto:
  cached = await redis.get("price:{id}:{market}")
  Si hit: inyectar precio directamente, no llamar Shopify para ese producto

Parte D: Redis lookup en outfit endpoint (cierra G-01)
  visual_search_router.py → antes de _CLP_MARKET_RATES:
  cached = await redis.get("price:{pid}:{market_id}")
  Si hit: usar precio real de Shopify
  Si miss: _CLP_MARKET_RATES (fallback, igual que ahora)
```

**Redis key format:** `price:{shopify_product_id}:{market_id}` con TTL=3600s (1 hora)

**Ejemplo de clave:** `price:9978563854645:CH`

---

## 3. Plan de implementación paso a paso

### Reglas de la sesión

- Leer `mcp_personalization_engine.py` en secciones (head/tail — archivo ~212KB). **Nunca leer el archivo completo.**
- Hacer UN cambio a la vez, verificar antes de continuar.
- Usar `grep` o `search_files` para encontrar funciones específicas antes de editar.

---

### Paso 1 — Reconocimiento del archivo (15 min)

**Objetivo:** Entender el estado actual de `_enrich_recommendations_lazy()` y `get_prices_for_products()`.

```bash
# En la sesión, ejecutar primero:
# Buscar la función objetivo
# Filesystem:search_files path=...mcp/engines/ pattern=*mcp_personalization_engine*

# Luego leer la función con head/tail para ubicar las líneas exactas
# de _enrich_recommendations_lazy() y get_prices_for_products()
```

**Entregable:** Números de línea exactos de `_enrich_recommendations_lazy()` antes de editar.

---

### Paso 2 — Parte A: Timeout en Shopify call (30 min)

**Archivo:** `src/api/mcp/engines/mcp_personalization_engine.py`

**Ubicar:** La llamada `await self.shopify_client.get_prices_for_products(...)` dentro de `_enrich_recommendations_lazy()`

**Cambio a aplicar:**

```python
# ANTES:
result = await self.shopify_client.get_prices_for_products(
    product_ids=product_ids,
    markets=[market_id, "CL", "ES", "MX"]
)

# DESPUÉS:
# Timeout configurable via env var (mismo patrón que PRODUCT_CONTEXT_TIMEOUT_S)
lazy_price_timeout = float(os.getenv("LAZY_PRICE_TIMEOUT_S", "5.0"))
try:
    result = await asyncio.wait_for(
        self.shopify_client.get_prices_for_products(
            product_ids=product_ids,
            markets=[market_id, "CL", "ES", "MX"]
        ),
        timeout=lazy_price_timeout,
    )
except asyncio.TimeoutError:
    logger.warning(
        "lazy_price_timeout",
        product_count=len(product_ids),
        market_id=market_id,
        timeout_s=lazy_price_timeout,
        note="proceeding with CLP_RATES fallback"
    )
    return  # Sale de _enrich_recommendations_lazy(), CLP_RATES activo
```

**Validación:** Levantar localmente con `LAZY_PRICE_TIMEOUT_S=0.001` para forzar el timeout y verificar que el log `lazy_price_timeout` aparece y el sistema continúa sin error.

**Variable de entorno para Cloud Run:** `LAZY_PRICE_TIMEOUT_S=5` (5 segundos es suficiente para Shopify en condiciones normales; los SSL retries deben acotarse en ese margen).

---

### Paso 3 — Parte C: Redis lookup al inicio de lazy-price (45 min)

**Objetivo:** Si los precios ya están en Redis (de una request anterior), no llamar a Shopify.

**Ubicar en `_enrich_recommendations_lazy()`:** el loop donde se determina qué productos necesitan enriquecimiento.

```python
# Al inicio del loop de productos, antes de acumular product_ids para Shopify:

products_to_enrich = []  # productos que realmente necesitan llamada a Shopify

for rec in recommendations:
    product_id = str(rec.get("id", ""))
    if not product_id:
        continue

    # Prioridad 1: market_prices ya en RAM (enriquecimiento previo en esta instancia)
    if market_id in rec.get("market_prices", {}):
        continue  # ya tiene precio, skip

    # Prioridad 2 (NUEVO): Redis cache por producto
    redis_key = f"price:{product_id}:{market_id}"
    try:
        cached_raw = await redis_service.get(redis_key)
        if cached_raw:
            price_data = json.loads(cached_raw)
            # Inyectar en market_prices igual que lo hace Shopify
            if "market_prices" not in rec:
                rec["market_prices"] = {}
            rec["market_prices"][market_id] = price_data
            logger.debug(
                "lazy_price_redis_hit",
                product_id=product_id, market_id=market_id
            )
            continue  # skip Shopify para este producto
    except Exception:
        pass  # Si Redis falla, continuar a Shopify

    products_to_enrich.append(product_id)  # necesita Shopify

# Solo llamar Shopify para los productos sin precio en Redis
if products_to_enrich:
    # ... llamada a get_prices_for_products(products_to_enrich) con timeout (Parte A)
```

---

### Paso 4 — Parte B: Redis write después de Shopify (30 min)

**Ubicar:** El punto donde `_enrich_recommendations_lazy()` recibe los resultados de `get_prices_for_products()` y los inyecta en `rec["market_prices"]`.

```python
# Después de inyectar cada precio en RAM:
for product_id, price_by_market in result.items():
    # ... lógica existente de inyección en rec["market_prices"] ...

    # (NUEVO) Persistir en Redis para requests futuros de cualquier instancia
    for mkt_id, price_data in price_by_market.items():
        redis_key = f"price:{product_id}:{mkt_id}"
        try:
            await redis_service.set(
                redis_key,
                json.dumps(price_data),
                ex=3600  # TTL: 1 hora
            )
        except Exception:
            pass  # Si Redis falla, el precio sigue en RAM — no es crítico

    logger.debug(
        "lazy_price_redis_cached",
        product_id=product_id,
        markets=list(price_by_market.keys())
    )
```

---

### Paso 5 — Parte D: Redis lookup en outfit endpoint (20 min)

**Archivo:** `src/api/routers/visual_search_router.py`

**Ubicar:** El bloque donde se construye `cat_products` con la lógica de precios.

Este archivo ya fue editado en la sesión anterior (fix CLP→CHF). El cambio es agregar el Redis lookup ANTES del `_CLP_MARKET_RATES`:

```python
# ANTES (actual):
if mkt:
    price    = mkt.get("price") or prod.get("price")
    currency = mkt.get("currency", "CLP")
else:
    market_cfg = _CLP_MARKET_RATES.get(market_id, _CLP_MARKET_RATES["CL"])
    base_clp   = float(prod.get("price") or 0)
    price      = round(base_clp * market_cfg["rate"], 2)
    currency   = market_cfg["currency"]

# DESPUÉS (con Redis lookup):
if mkt:
    # Prioridad 1: market_prices en RAM (del catalogo pre-enriquecido)
    price    = mkt.get("price") or prod.get("price")
    currency = mkt.get("currency", "CLP")
else:
    # Prioridad 2: Redis cache (precio real de Shopify de una request anterior)
    redis_key = f"price:{pid}:{market_id}"
    redis_price = None
    try:
        cached_raw = await redis_service.get(redis_key)
        if cached_raw:
            redis_price = json.loads(cached_raw)
    except Exception:
        pass

    if redis_price:
        # Precio real de Shopify disponible en Redis—mismo que el conversacional
        price    = redis_price.get("price") or redis_price.get("amount")
        currency = redis_price.get("currency", "CHF" if market_id == "CH" else "CLP")
    else:
        # Prioridad 3: Conversión local con tasas fijas (fallback)
        market_cfg = _CLP_MARKET_RATES.get(market_id, _CLP_MARKET_RATES["CL"])
        base_clp   = float(prod.get("price") or 0)
        price      = round(base_clp * market_cfg["rate"], 2)
        currency   = market_cfg["currency"]
```

**Nota sobre async en el outfit router:** el endpoint ya es `async def`. La llamada `await redis_service.get(...)` es compatible. Verificar que `redis_service` esté disponible en ese scope (puede requerir `ServiceFactory.get_redis_service()` igual que en otros routers).

---

### Paso 6 — Validación local (30 min)

```powershell
# 1. Levantar la API localmente
$env:MINILM_INTENT_ENABLED = "true"
$env:LAZY_PRICE_TIMEOUT_S = "5"
uvicorn src.api.main_unified_redis:app --port 8080 --log-level debug

# 2. Primera query TRANSACCIONAL ("Busco un conjunto completo")
# Verificar en logs:
#   [lazy-price] Consultando Shopify para 8 productos...
#   lazy_price_redis_cached product_id=... markets=['CH', 'CL', ...]

# 3. Segunda query TRANSACCIONAL (misma query)
# Verificar en logs:
#   lazy_price_redis_hit product_id=... market_id=CH (x8)
#   [lazy-price] 8/8 enriquecidos desde Redis en <10ms
#   NO debe aparecer "Consultando Shopify"

# 4. Verificar outfit search
# Verificar que el carousel muestra precios reales de Shopify
# (no tasas fijas 0.00089) cuando Redis tiene los datos
```

---

### Paso 7 — Deploy y validación en producción

```powershell
# Deploy — no requiere rebuild de Docker (solo cambios de código Python)
# Los cambios son en .py, no en Dockerfile ni requirements
docker build -t gcr.io/retail-recommendations-449216/retail-recommender:latest -f Dockerfile.cloudrun .
docker push gcr.io/retail-recommendations-449216/retail-recommender:latest
gcloud run deploy retail-recommender \
  --image gcr.io/retail-recommendations-449216/retail-recommender:latest \
  --region us-central1 \
  --set-env-vars LAZY_PRICE_TIMEOUT_S=5
```

**Logs a verificar en GCP después del deploy:**

```
# Request 1 (instancia fría):
lazy_price_timeout           ← si Shopify SSL issue activo
  O
lazy_price_redis_cached      ← si Shopify responde bien

# Request 2 (mismo producto):
lazy_price_redis_hit (x8)    ← CLAVE: confirma cache funcionando
✅ PARALLEL MCP conversation flow completed in ~800ms   ← vs 12.8s anterior
```

---

## 4. Criterios de éxito

| Criterio | Cómo verificar | Objetivo |
| --- | --- | --- |
| Redis cache activo | `lazy_price_redis_hit` en logs de segunda request | Al menos 6/8 hits en 2ª request |
| Latencia TRANSACCIONAL | `PARALLEL MCP flow completed in Xms` | < 2.000ms (vs 12.800ms actual) |
| Sin timeout personaliz. | Ausencia de `⏰ MCP personalization timeout` | 0 timeouts para productos cacheados |
| Outfit precios reales | Prices en carousel = prices en chat para mismo producto | Coincidencia exacta |
| Sin regresión | Tests pasan, sistema responde | `pytest -m "not slow"` verde |

---

## 5. Riesgos y mitigaciones

**Riesgo 1 — `mcp_personalization_engine.py` es complejo y grande (~212KB):**

Mitigación: leer SIEMPRE con head/tail o search_files antes de editar. Un cambio a la vez. Nunca leer el archivo completo en el contexto.

**Riesgo 2 — Formato del dato en Redis puede no coincidir con lo que espera `_format_price_for_market()`:**

Mitigación: antes de escribir el Redis write (Parte B), leer cómo `get_prices_for_products()` devuelve los datos y cómo `_format_price_for_market()` los consume. El JSON en Redis debe tener exactamente las mismas claves.

**Riesgo 3 — `redis_service` puede no estar disponible en el scope del outfit router:**

Mitigación: verificar cómo otros routers acceden a Redis (ejemplo: `mcp_router.py` o `products_router.py`). Usar el mismo patrón (`ServiceFactory.get_redis_service()`).

**Riesgo 4 — El await en el outfit router puede necesitar que la función sea `async`:**

Mitigación: el endpoint ya es `async def` (tiene `await` para el embedding service). Compatible.

---

## 6. Trabajo futuro (post-sprint)

**Fase 3 de la arquitectura lazy (cuando el webhook `products/update` esté activo):**

- Invalidar Redis al recibir webhook: `Redis.delete("price:{id}:*")`
- Eliminar `CLP_RATES` del código (ya no hay fallback de último recurso)
- Desactivar el bloque `PASO 4.5` definitivamente (ya desactivado, pero puede eliminarse)

**Métrica de alerta:**

Cuando `[OpcionA-fallback]` aparece consistentemente en logs = Shopify no disponible + Redis vacío. Configurar alerta en Cloud Monitoring.

---

*Plan creado al cierre de la sesión 21/05/2026. Siguiente sesión: Paso 1 — reconocimiento de `mcp_personalization_engine.py`.*