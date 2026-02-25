# DCT — M3: Distributed Locking (Redis)
## Estado: ✅ IMPLEMENTACIÓN COMPLETA Y VALIDADA
*Versión: 2.0 | Fecha: 2026-02-25 | Plan: Mejoras Técnicas KB System*

---

## RESUMEN EJECUTIVO

La fase M3 del Plan de Mejoras Técnicas implementa **distributed locking mediante Redis** para proteger operaciones de escritura en la base de datos de Knowledge Base contra race conditions en entornos multi-instancia (Cloud Run horizontal scaling).

La implementación está **completamente validada**: 30 tests pasando (22 unitarios + 8 de integración), cobertura de todos los escenarios críticos (happy path, timeout, degraded mode, atomicity), y un bug post-implementación encontrado y corregido durante la sesión de validación.

---

## TABLA DE ESTADO FINAL

| Paso | Descripción | Estado | Tests |
|------|-------------|--------|-------|
| 1 | `RedisService.distributed_lock()` + `DistributedLockError` | ✅ | 11 tests |
| 2 | `ShopifyKBSyncService._upsert_kb_content()` con feature flag | ✅ | 6 tests |
| 3 | Métricas Prometheus (3 nuevas métricas M3) | ✅ | Cubierto en test unitario |
| 4a | Tests unitarios — `tests/unit/test_distributed_lock.py` | ✅ | 22/22 PASSED |
| 4b | Tests integración — `tests/integration/kb/test_distributed_locking.py` | ✅ | 8/8 PASSED |
| 5 | **Bug fix: structlog no configurado en tests** | ✅ | 3 tests desbloqueados |

**Total tests M3: 30/30 PASSED — 0 FAILED — 0 ERRORS**

---

## ARCHIVOS AFECTADOS

### Producción — Modificados

#### `src/api/core/redis_service.py`
```
CAMBIOS:
  + Logger migrado a structlog (H1-compatible, M3-required)
  + Clase DistributedLockError(Exception)
  + Método async distributed_lock() como @asynccontextmanager
  + Instrumentación Prometheus (lazy import, degrada si no disponible)

SECCIÓN NUEVA: "# M3: DISTRIBUTED LOCKING" (después de reset_stats())
```

#### `src/api/services/shopify_kb_sync.py`
```
CAMBIOS:
  + Feature flag _use_distributed_locks (desde KB_DISTRIBUTED_LOCKS env var)
  + Import DistributedLockError con fallback local para resiliencia de import
  + _upsert_kb_content(): dos capas de concurrencia + retry logic (max 3)
```

#### `src/api/core/prometheus_metrics.py`
```
CAMBIOS:
  + Sección "KB DISTRIBUTED LOCK METRICS (M3)"
  + kb_distributed_lock_acquisitions_total (Counter, labels: result)
  + kb_distributed_lock_wait_seconds (Histogram)
  + kb_distributed_lock_timeouts_total (Counter)
  + metrics_count: 7 → 10
  + integration_phase: M2 → M3
```

### Tests — Creados

#### `tests/unit/test_distributed_lock.py`
```
COBERTURA: 22 tests en 5 clases
  TestDistributedLockHappyPath     (5) — flujo normal completo
  TestDistributedLockTimeout       (3) — acquire() → False
  TestDistributedLockDegradedMode  (3) — Redis no disponible
  TestDistributedLockErrorClass    (5) — jerarquía de excepción
  TestDistributedLockFeatureFlag   (6) — routing flag on/off + retry
```

#### `tests/integration/kb/test_distributed_locking.py`
```
COBERTURA: 8 tests en 3 clases
  TestDistributedLockConcurrency       (4) — exclusión mutua real
  TestMultipleInstancesConcurrency     (2) — 5 instancias simuladas
  TestDistributedLockAtomicity         (2) — sin corrupción de datos
  
INFRAESTRUCTURA: SimulatedRedisLockStore + InMemoryRedisLock
  → Simula semántica NX de Redis en memoria
  → No requiere Redis real en CI/CD
```

### Tests — Bug Fix en Infraestructura

#### `tests/conftest.py`
```
CAMBIO: Configuración de structlog añadida a nivel top-level (antes de fixtures)

PROBLEMA RESUELTO:
  TypeError: Logger._log() got an unexpected keyword argument 'lock_name'
  → 3 tests de TestDistributedLockDegradedMode fallaban

CAUSA RAÍZ:
  redis_service.py usa la API de structlog con kwargs estructurados:
    logger.warning("event", lock_name=..., action=..., note=...)
  Sin structlog.configure(), la librería delega a logging.Logger estándar,
  que NO acepta kwargs arbitrarios → TypeError.

SOLUCIÓN:
  Llamar structlog.configure() a nivel top-level del conftest antes de
  cualquier fixture, usando PrintLoggerFactory (no pasa por stdlib Logger).
```

---

## ARQUITECTURA IMPLEMENTADA

### Flujo de `distributed_lock()`

```
Entrada: distributed_lock(lock_name, timeout=30, blocking_timeout=5, sleep=0.1)

  ┌─ ¿_client is None OR _connected is False? ─────────────────────────────┐
  │                                                                          │
  │  DEGRADED MODE                                                           │
  │  ┌─────────────────────────────────────────────┐                        │
  │  │ log.warning("redis_unavailable", ...)        │                        │
  │  │ Prometheus: acquisitions{result="degraded"}  │                        │
  │  │ yield None                  ← sin lock real  │                        │
  │  │ return                                       │                        │
  │  └─────────────────────────────────────────────┘                        │
  │                                                                          │
  └──── No (Redis disponible) ───────────────────────────────────────────────┘
       │
       ▼
  lock = client.lock(lock_name, timeout, blocking_timeout, sleep)
       │
       ▼
  acquired = await lock.acquire()     ← polling hasta blocking_timeout
       │
       ├─── True ────────────────────────────────────────────────────────────┐
       │                                                                      │
       │    Prometheus: acquisitions{result="acquired"}                       │
       │    Prometheus: wait_seconds.observe(elapsed)                         │
       │    yield lock   ← bloque "async with" ejecuta aquí                  │
       │                                                                      │
       │    [finally]                                                         │
       │    await lock.release()   ← siempre, incluso si hay excepción        │
       │      Si release falla (TTL expiró): log.debug + silencioso           │
       │                                                                      │
       └──────────────────────────────────────────────────────────────────────┘
       │
       └─── False ───────────────────────────────────────────────────────────┐
            Prometheus: acquisitions{result="timeout"}                        │
            Prometheus: timeouts_total.inc()                                  │
            raise DistributedLockError(f"'{lock_name}' within {timeout}s")   │
            └──────────────────────────────────────────────────────────────────┘
```

### Dos Capas de Concurrencia en `_upsert_kb_content()`

```
async with self._db_semaphore:                    # CAPA 1: Intra-instancia
    │                                             # asyncio.Semaphore(N)
    │   Limita goroutines DENTRO de esta instancia.
    │   Evita agotar el pool de conexiones de PostgreSQL.
    │   Siempre activo, independiente del feature flag.
    │
    ├── if self._use_distributed_locks:           # CAPA 2: Cross-instance
    │       try:
    │           async with redis.distributed_lock(lock_key):
    │               async with db.acquire() as conn:
    │                   await conn.execute(UPSERT_QUERY, ...)
    │       except DistributedLockError:
    │           retry_count += 1
    │           if retry_count < MAX_RETRIES (3):
    │               await asyncio.sleep(0.1 * retry_count)
    │               continue
    │           else:
    │               raise   ← propagar al caller
    │
    └── else:                                    # LEGACY (pre-M3, default)
            async with db.acquire() as conn:
                await conn.execute(UPSERT_QUERY, ...)
```

**¿Por qué dos capas y no una?**

| Escenario | Semáforo asyncio | Redis Lock | Resultado |
|-----------|-----------------|------------|-----------|
| 2 goroutines, misma instancia, mismo record | ✅ bloquea | no activo | ✅ seguro |
| 2 instancias Cloud Run, mismo record | ❌ no protege | ✅ bloquea | ✅ seguro |
| 2 instancias, records distintos | ❌ no afecta | ✅ keys distintas → paralelo | ✅ eficiente |
| Redis caído, una instancia | ✅ bloquea | degraded: yield None | ✅ funciona |

### Lock Key Format

```
Formato:  kb_sync:lock:{sub_intent}:{language}:{category}
Ejemplo:  kb_sync:lock:policy_return:es:general

Caso especial: category=None se normaliza a "general"
  → Consistente con COALESCE(category, 'general') en la DB query
  → Evita que None y "general" sean tratados como locks distintos
```

---

## VARIABLES DE ENTORNO

| Variable | Default | Descripción | Activar en... |
|----------|---------|-------------|---------------|
| `KB_DISTRIBUTED_LOCKS` | `false` | Activa Redis locking cross-instance | Cloud Run multi-instancia |
| `KB_SYNC_SEMAPHORE_SIZE` | `1` | Concurrencia intra-instancia (M1) | Siempre en multi-core |

**Configuración recomendada para Cloud Run (producción, multi-instancia):**
```bash
KB_DISTRIBUTED_LOCKS=true
KB_SYNC_SEMAPHORE_SIZE=5
```

**Rollback instantáneo sin redeploy:**
```bash
KB_DISTRIBUTED_LOCKS=false   # Vuelve al comportamiento pre-M3
```

---

## COMANDOS DE VALIDACIÓN

```bash
# ─── Validación completa M3 ───────────────────────────────────────────────

# Tests unitarios
pytest tests/unit/test_distributed_lock.py -v

# Tests de integración
pytest tests/integration/kb/test_distributed_locking.py -v

# Suite completa M3 con coverage
pytest tests/unit/test_distributed_lock.py \
       tests/integration/kb/test_distributed_locking.py \
  -v \
  --cov=src.api.core.redis_service \
  --cov=src.api.services.shopify_kb_sync \
  --cov-report=term-missing

# ─── Filtros útiles ───────────────────────────────────────────────────────

# Solo degraded mode (los 3 tests desbloqueados por el bug fix)
pytest tests/unit/test_distributed_lock.py -v -k "Degraded"

# Solo feature flag routing
pytest tests/unit/test_distributed_lock.py -v -k "FeatureFlag"

# Solo atomicity (corrección de race conditions)
pytest tests/integration/kb/test_distributed_locking.py -v -k "Atomicity"

# ─── Resultado esperado ───────────────────────────────────────────────────
# 30 passed, 0 failed, 0 errors
```

---

## MÉTRICAS PROMETHEUS

```promql
# ── Tasa de adquisiciones por resultado ──────────────────────────────────
# result="acquired" | "timeout" | "degraded"
rate(kb_distributed_lock_acquisitions_total[5m])

# ── Tiempo de espera para obtener el lock (P95) ───────────────────────────
# Indica contención entre instancias
histogram_quantile(0.95, rate(kb_distributed_lock_wait_seconds_bucket[5m]))

# ── Timeouts por minuto (alerta: >5/min indica problema) ─────────────────
rate(kb_distributed_lock_timeouts_total[5m]) * 60

# ── Porcentaje de operaciones en modo degradado ───────────────────────────
# Alerta: >0% indica que Redis no está disponible
rate(kb_distributed_lock_acquisitions_total{result="degraded"}[5m])
  /
rate(kb_distributed_lock_acquisitions_total[5m]) * 100

# ── Ratio adquisiciones exitosas vs fallidas ──────────────────────────────
sum(rate(kb_distributed_lock_acquisitions_total{result="acquired"}[5m]))
  /
sum(rate(kb_distributed_lock_acquisitions_total[5m]))
```

**Umbrales de alerta recomendados:**

| Métrica | Warning | Critical |
|---------|---------|----------|
| Timeout rate | >2/min | >10/min |
| Wait P95 | >200ms | >1000ms |
| Degraded mode | >0% | >5% |
| Success ratio | <99% | <95% |

---

## BUG ENCONTRADO Y CORREGIDO EN VALIDACIÓN

### Descripción del Bug

**Síntoma:**
```
FAILED tests/unit/test_distributed_lock.py::TestDistributedLockDegradedMode::test_body_executes_when_client_is_none
FAILED tests/unit/test_distributed_lock.py::TestDistributedLockDegradedMode::test_yields_none_in_degraded_mode
FAILED tests/unit/test_distributed_lock.py::TestDistributedLockDegradedMode::test_degraded_mode_when_connected_is_false_but_client_exists

TypeError: Logger._log() got an unexpected keyword argument 'lock_name'
```

**Causa raíz:**
`redis_service.py` usa la API de structlog con kwargs estructurados en el path de degraded mode:
```python
logger.warning(
    "distributed_lock_redis_unavailable",
    lock_name=lock_name,          # ← kwargs estructurados
    action="yielding_without_lock",
    note="degraded_mode_active_no_cross_instance_protection"
)
```

Sin `structlog.configure()`, la librería usa internamente `stdlib.LoggerFactory()`, que delega al `logging.Logger` estándar de Python. Ese logger **no acepta kwargs arbitrarios** → `TypeError`.

Solo los tests de DegradedMode fallaban porque son los únicos que activan ese código path (cuando `_client is None` o `_connected is False`).

**Por qué solo en tests y no en producción:**
En producción, `configure_structlog()` se llama en `main.py` durante el startup, configurando correctamente `PrintLoggerFactory` y `BoundLogger`. En tests, ese startup no ocurre.

**Fix aplicado:**

*`tests/conftest.py`* — añadido a nivel top-level (antes de cualquier fixture):
```python
try:
    import structlog

    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(),   # No delega a stdlib
        processors=[
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        cache_logger_on_first_use=False,    # Evita logger no-configurado cacheado
        context_class=dict,
        wrapper_class=structlog.BoundLogger,
    )
except ImportError:
    pass
```

*`src/api/core/redis_service.py`* — logger migrado de stdlib a structlog:
```python
# ANTES
import logging
logger = logging.getLogger(__name__)

# DESPUÉS
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)  # Fallback
```

**Lección aprendida:**
> `structlog.configure()` debe llamarse **antes** de usar cualquier logger con kwargs estructurados. En tests, el lugar correcto es el top-level del `conftest.py` — no dentro de fixtures (que se ejecutan después de la importación de módulos).

---

## DECISIONES DE DISEÑO DOCUMENTADAS

### 1. Availability > Consistency en Degraded Mode

**Decisión**: Si Redis no está disponible → continuar sin lock (yield None).
**Alternativa rechazada**: Bloquear el sync hasta que Redis vuelva.
**Razonamiento**: El sistema de KB es de lectura frecuente. Un sync retrasado es mejor que un sync completamente bloqueado. La pérdida de protección cross-instance es un riesgo aceptable durante outages breves de Redis.

### 2. Default `KB_DISTRIBUTED_LOCKS=false`

**Decisión**: El feature flag está desactivado por defecto.
**Razonamiento**: Preserva exactamente el comportamiento pre-M3 en todos los entornos existentes. Solo activar cuando se confirma despliegue multi-instancia real.

### 3. TTL=30s + blocking_timeout=5s

**Decisión**: TTL largo (previene deadlocks si instancia muere con el lock). Blocking timeout corto (responde rápido si hay contención).
**Trade-off**: Con TTL=30s, si una instancia muere en el medio del upsert, el lock se libera automáticamente en máximo 30s. Con blocking_timeout=5s, una instancia esperará máximo 5s antes de lanzar DistributedLockError y hacer retry.

### 4. Lock granularidad por record (no global)

**Decisión**: Lock key incluye `sub_intent + language + category`.
**Resultado**: Records distintos se sincronizan en paralelo (máximo throughput). Solo el mismo record exacto es serializado entre instancias.

### 5. Retry con exponential backoff (max 3 intentos)

**Decisión**: 3 intentos con `sleep(0.1 * attempt)` entre intentos.
**Razonamiento**: Un lock contended usualmente se libera en <1s. 3 intentos con backoff dan ~0.6s de ventana total. Si después de 3 intentos sigue fallando, hay un problema real y el caller debe saberlo.

---

## LEARNING OPPORTUNITIES

### Patrón: `@asynccontextmanager` con garantía de liberación

```python
@asynccontextmanager
async def managed_resource():
    resource = await acquire()
    acquired = True
    try:
        yield resource          # El bloque "async with" ejecuta aquí
    finally:
        if acquired:
            await resource.release()  # SIEMPRE se ejecuta, incluso con excepciones
```

**Por qué es importante**: Sin el `finally`, una excepción dentro del bloque `async with` dejaría el lock adquirido hasta expirar por TTL (hasta 30s), bloqueando todas las demás instancias durante ese tiempo.

### Patrón: Feature Flag para Dark Launch

```python
# En __init__
self._use_feature = os.getenv("FEATURE_X", "false").lower() in ("true", "1", "yes")

# En el método
if self._use_feature:
    # Nueva lógica
else:
    # Lógica anterior (intacta, sin modificar)
```

**Valor**: Permite activar en staging, validar, luego activar en producción sin redeploy. Rollback en segundos.

### Patrón: Lazy Import de Métricas

```python
try:
    from src.api.core.prometheus_metrics import kb_distributed_lock_acquisitions_total
    kb_distributed_lock_acquisitions_total.labels(result="acquired").inc()
except ImportError:
    pass  # Continuar sin métricas — no es error fatal
```

**Valor**: El módulo funciona en entornos de test donde prometheus_client puede no estar disponible, y en producción las métricas se registran normalmente.

### Patrón: Test de Concurrencia con asyncio.gather

```python
async def test_exclusion_mutua():
    holders = []
    
    async def task(instance_id):
        async with instance.distributed_lock("test:lock"):
            holders.append(instance_id)       # Entró en la sección crítica
            await asyncio.sleep(0.05)         # Simula trabajo
            holders.remove(instance_id)       # Salió
            assert len(holders) <= 1          # Invariante de exclusión
    
    # Lanzar 5 tareas concurrentes
    await asyncio.gather(*[task(i) for i in range(5)])
```

**Valor**: Patrón para verificar exclusión mutua real en tests async sin necesidad de Redis externo.

### Por qué `structlog.configure()` va en el top-level de conftest.py

```python
# conftest.py (top-level, fuera de fixtures)
import structlog
structlog.configure(...)  # ← CORRECTO: se ejecuta al importar el módulo

# conftest.py (dentro de fixture) — INCORRECTO
@pytest.fixture(autouse=True)
def setup_logging():
    structlog.configure(...)  # Demasiado tarde: los módulos ya importaron sus loggers
```

Los módulos Python resuelven sus variables de módulo (`logger = structlog.get_logger(__name__)`) en el momento de la importación, antes de que los fixtures se ejecuten. Si `structlog.configure()` no se llamó antes de esa importación, el logger queda ligado a la configuración por defecto (que delega a stdlib).

---

## RELACIÓN CON EL PLAN DE MEJORAS TÉCNICAS

```
FASE 0 (Completada): Estabilidad y Observabilidad Base
  H1 ✅ Structured Logging
  H2 ✅ Schema Versioning
  H3 ✅ Enhanced Health Checks
  H4 ✅ Title Translation

FASE 1 (Completada): Quick Wins
  M1 ✅ Optimize Sync Performance
  M2 ✅ Prometheus Metrics

FASE 2 (Completada): Foundation Escalable
  M3 ✅ Distributed Locking (Redis)  ← ESTE DOCUMENTO
  M4 🔄 Incremental Sync (Webhooks)  ← SIGUIENTE
  M5 ⏳ Alembic Migrations

FASE 3 (Pendiente): Features Avanzadas
  L1 ⏳ HTML→Markdown Library
  L2 ⏳ Content Versioning
  L3 ⏳ Multi-Region Support
  L4 ⏳ ML Content Optimization
```

---

*Documento versión: 2.0*
*Creado: 2026-02-25*
*Validación: 2026-02-25 — 30/30 tests pasando*
*Próxima fase: M4 — Incremental Sync (Webhooks)*