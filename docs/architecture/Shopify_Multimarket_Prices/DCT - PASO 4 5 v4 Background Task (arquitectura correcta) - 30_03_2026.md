# DCT - PASO 4.5 v4 Background Task (arquitectura correcta) - 30_03_2026

## El diagnóstico real

**Historial de versiones del PASO 4.5:**

- v1: `get_products_with_shopify_prices()` con timeout 60s → **falla** (REST tarda 130s)
- v2: GraphQL directo sin retry → **falla** (throttled sin recuperación, 692/3062)
- v3: GraphQL con retry/backoff + 0.5s pausa → **funciona** (3062/3062) pero **startup tarda ~206s**
- v4: Igual que v3 pero como **background task** → startup en ~14s, enriquecimiento en background

**El problema de fondo (el que no habiamos resuelto):**

Todas las versiones anteriores bloqueaban el `lifespan()` antes del `yield`. En FastAPI:

```
lifespan() antes del yield == startup bloqueante

Uvicorn no acepta requests hasta que lifespan() llega al yield.
En Cloud Run: health check no responde hasta ese momento.
Si el startup > timeoutSeconds (300s) -> deploy falla.
```

La solucion correcta siempre fue `asyncio.create_task()` — lanzar el trabajo en background y continuar al `yield` inmediatamente.

---

## Solucion implementada: PASO 4.5 v4

### Arquitectura

```
startup lifespan() (bloqueante, ~14s):
  PASO 1-4: Redis, TF-IDF, ProductCache, etc.
  PASO 4.5: asyncio.create_task(_enrich_catalog_with_shopify_prices(...)) <- no awaited
            logger.info("Enriquecimiento lanzado en segundo plano...")
  PASO 5-11: ProductCache, HybridRecommender, Claude warmup...
  yield  <- Uvicorn listo en ~14s, requests aceptados

Background task (no bloqueante, ~3-4 min despues del startup):
  103 batches GraphQL con retry/backoff
  Inyectar market_prices en tfidf_recommender.product_data
  logger.info("[PASO 4.5 BG] Completado: 3062/3062 productos enriquecidos")
```

### Seguridad de concurrencia

- **Escrituras:** solo el background task escribe `product["market_prices"]`
- **Lecturas:** los handlers leen `product.get("market_prices", {})` sin bloquear
- **Python GIL:** garantiza atomicidad de asignacion de dict
- **Fallback CLP_RATES:** activo en `_format_price_for_market()` hasta que el task completa
- **Sin locks:** no necesarios porque escrituras y lecturas son en campos distintos

---

## Cambio en main_unified_[redis.py](http://redis.py)

**Archivo:** `src/api/main_unified_redis.py`

**Tamano:** 122KB → 135KB

El PASO 4.5 v3 bloqueante (el loop de batches con `await asyncio.sleep(0.5)` entre cada uno) fue envuelto en `if False:` (codigo inerte) y reemplazado por:

1. Definicion de `async def _enrich_catalog_with_shopify_prices(catalog, shop_url, access_token)` — la corrutina con toda la logica de batches/retry/backoff
2. `asyncio.create_task(...)` para lanzarla sin await
3. Log confirmando que el startup continua sin bloquear

---

## Logs esperados

**En startup (~14s):**

```
[00:13:22] INFO  PASO 4.5: Enriquecimiento Shopify lanzado en segundo plano.
                  Startup continua sin bloquear. market_prices se inyectaran
                  automaticamente en ~3-4 min mientras el sistema ya sirve requests.
[00:13:28] INFO  CORRECTED Enterprise startup completed successfully
[00:13:29] INFO  Application startup complete. <- Uvicorn listo
```

**~3-4 min despues del startup (en background):**

```
[00:13:22] INFO  [PASO 4.5 BG] Iniciando enriquecimiento de precios (3062 productos, 103 batches)...
[00:16:XX] INFO  [PASO 4.5 BG] Completado: 3062/3062 productos enriquecidos |
                  batches OK=103 FAIL=0 | CL=3062 CH=3062 MX=3062 ES=3062 | ~206000ms
```

**En requests durante el periodo de transicion (primeros ~3-4 min):**

```
WARNING [OpcionA-fallback] product '...' sin market_prices para mercado CH.
        Usando CLP_RATES hardcodeado. <- OK, esperado mientras el BG task corre
```

**En requests despues de que el BG task completa:**

```
# Sin [OpcionA-fallback] WARNINGs -> precios exactos de Shopify
```

---

## Leccion de arquitectura

Esta es la leccion mas importante de toda la iteracion del PASO 4.5:

**El patron correcto para trabajo costoso en startup de FastAPI:**

```python
@asynccontextmanager
async def lifespan(app):
    # Trabajo rapido y critico aqui (Redis, TF-IDF, etc.)
    
    # Trabajo costoso pero no critico: background task
    asyncio.create_task(work_that_takes_minutes())
    
    yield  # <- Sistema listo para requests inmediatamente
    
    # Shutdown
```

Antes de llegar a esta solucion, iteramos v1 (timeout), v2 (throttled), v3 (funciona pero lento) porque enfocamos el problema en *como hacer el trabajo mas rapido* en lugar de *si el trabajo debe bloquear el startup*. La pregunta correcta era: *Necesita completarse antes de servir el primer request?* No, porque tenemos CLP_RATES como fallback valido.

**Regla de diseno:** Si un proceso de startup puede continuar con un fallback mientras el trabajo costoso se completa, usa `asyncio.create_task()` y no `await`.