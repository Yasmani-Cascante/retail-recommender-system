# 📋 PLAN DE IMPLEMENTACIÓN - FASE H3
## **Enhanced Health Checks - Sistema de Monitoreo Completo**

**Fecha de Planificación:** 2026-02-10  
**Arquitecto:** Yasmani (Senior Software Architect)  
**Sistema:** Retail Recommender System v2.1.0  
**Dependencias:** ✅ FASE H1 (Structured Logging) - COMPLETADA  
**Dependencias:** ✅ FASE H2 (Schema Versioning) - COMPLETADA  
**Estado:** 📝 PLANIFICACIÓN COMPLETADA - READY FOR IMPLEMENTATION

---

## 📊 RESUMEN EJECUTIVO

### **Objetivo de la Fase H3**

Implementar sistema de health checks **comprehensivo y enterprise-grade** que proporcione:

1. **Visibilidad completa** del estado del sistema
2. **Detección temprana** de degradación
3. **Métricas detalladas** para dashboards
4. **Integración** con K8s, load balancers y monitoring

### **Situación Actual (10-Feb-2026)**

**✅ YA IMPLEMENTADO:**
```
src/api/routers/health_kb.py (EXISTENTE - 544 líneas)
├─ GET /health/kb - Health check comprehensivo
│  ├─ PostgreSQL connectivity ✅
│  ├─ KB content availability ✅
│  ├─ Redis connectivity ✅
│  ├─ Sync metrics ✅
│  ├─ Language coverage ✅
│  ├─ Warnings generation ✅
│  └─ Recommendations ✅
│
└─ GET /health/kb/simple - Health check simplificado
   ├─ PostgreSQL check ✅
   └─ KB content > 0 check ✅
```

**❌ GAPS IDENTIFICADOS (Plan Consolidado H3):**

Según el `Plan_de_accion_consolidado_06022026.md`, H3 debe agregar:

1. **Shopify GraphQL API health check** (actualmente comentado)
2. **Schema version verification** (aprovechando H2)
3. **Content staleness alerts** (>48h warning)
4. **Deep check mode** (query param `?deep=true`)
5. **Response time optimization** (<500ms target)
6. **Structured logging integration** (aprovechando H1)

---

## 🎯 ANÁLISIS DE ESTADO ACTUAL

### **Archivo: `src/api/routers/health_kb.py`**

#### ✅ **FORTALEZAS ACTUALES**

**1. Arquitectura Sólida**
```python
# ✅ Models bien definidos (Pydantic)
class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

class ComponentHealth(BaseModel): ...
class KBHealthResponse(BaseModel): ...
```

**2. Checks Exhaustivos**
```python
# ✅ 3 checks principales implementados
- check_postgres_connectivity() → Pool info, table existence
- check_kb_content_availability() → Content + language coverage
- check_redis_connectivity() → Usando redis.health_check()
```

**3. Métricas Detalladas**
```python
# ✅ Sync metrics comprehensivos
class SyncMetrics(BaseModel):
    total_records: int
    languages: List[LanguageCoverage]
    oldest_sync: datetime
    newest_sync: datetime
    stale_records_24h: int
    stale_records_7d: int
```

**4. Warnings & Recommendations**
```python
# ✅ Lógica inteligente de alertas
def generate_warnings_and_recommendations(...) → tuple[List, List]
```

**5. Parallel Execution**
```python
# ✅ Checks en paralelo para performance
postgres_check, content_check, redis_check = await asyncio.gather(...)
```

#### ❌ **GAPS vs PLAN CONSOLIDADO H3**

**GAP #1: Shopify GraphQL API Check (CRÍTICO)**
```python
# ❌ ACTUAL: Comentado y no funcional
# Check 3: Shopify GraphQL API (optional, slow)
if query_param_deep_check:  # ← NO EXISTE query_param_deep_check
    try:
        locales = await shopify_client._get_shop_locales()  # ← NO DEPENDENCY
```
**Problema:** 
- No hay dependency injection de `shopify_client`
- No hay query parameter `?deep=true`
- Check completamente no funcional

**GAP #2: Schema Version Verification (FASE H2)**
```python
# ❌ FALTA: Verificar schema_version es consistente
# Debería verificar:
# - Tabla schema_migrations existe
# - Current version matches expected version
# - No pending migrations
```

**GAP #3: Structured Logging (FASE H1)**
```python
# ❌ ACTUAL: Logging no estructurado
logger.error("postgresql_health_check_failed", error=str(e))
# ↑ Parece estructurado pero logger es standard Python logging

# ✅ DEBERÍA SER:
import structlog
logger = structlog.get_logger(__name__)
logger.error(
    "postgresql_health_check_failed",
    error=str(e),
    component="postgresql",
    check_type="connectivity"
)
```

**GAP #4: Content Staleness Alert (>48h)**
```python
# ✅ PARCIALMENTE IMPLEMENTADO: Detecta staleness
staleness = datetime.utcnow() - last_sync
if count == 0 or staleness > timedelta(hours=48):
    overall_status = "degraded"

# ❌ PERO: No genera warning explícito
# Debería agregar a warnings: "Content not synced in 72 hours"
```

**GAP #5: Response Time Target (<500ms)**
```python
# ❌ NO MEDIDO: No hay timing de health check
# Debería instrumentar para verificar:
# - Total response time < 500ms (without deep check)
# - Individual check times logged
```

**GAP #6: Table Name Inconsistency**
```python
# ❌ BUG DETECTADO: Tabla incorrecta
table_exists = await conn.fetchval("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_name = 'kb_content'  # ← INCORRECTO
    )
""")

# ✅ DEBERÍA SER: 'kb_contents' (plural)
```

---

## 📋 PLAN DE IMPLEMENTACIÓN DETALLADO

### **Enfoque: INCREMENTAL & SAFE**

```
Día 1 (4h): Fixes críticos + Structured Logging
├─ Fix tabla name inconsistency (kb_content → kb_contents)
├─ Migrar a structured logging (structlog)
├─ Agregar schema version check
└─ Tests de regresión

Día 2 (4h): Shopify GraphQL Check + Deep Mode
├─ Implementar ?deep=true query parameter
├─ Agregar dependency injection de ShopifyKBClient
├─ Implementar check_shopify_graphql()
└─ Tests de integración

Día 3 (3h): Performance + Observability
├─ Instrumentar timing de checks
├─ Mejorar staleness warnings
├─ Response time validation (<500ms)
└─ Documentation updates

TOTAL: 11 horas (1.5 días) ✅
```

---

## 🔧 IMPLEMENTACIÓN - DÍA 1

### **TASK 1.1: Fix Table Name Inconsistency** (15 min)

**Problema:**
```python
# ❌ INCORRECTO
table_name = 'kb_content'  # Singular
```

**Solución:**
```python
# ✅ CORRECTO
table_name = 'kb_contents'  # Plural (como en migration 002)
```

**Archivo:** `src/api/routers/health_kb.py`  
**Línea:** ~127

**Cambio:**
```python
# src/api/routers/health_kb.py (línea ~127)

async def check_postgres_connectivity(
    db_pool: asyncpg.Pool
) -> ComponentHealth:
    """..."""
    try:
        async with db_pool.acquire() as conn:
            # ... código existente ...
            
            # ✅ FIX: Tabla correcta (plural)
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'kb_contents'  # ← FIXED
                )
            """)
            
            if not table_exists:
                return ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    message="Table kb_contents does not exist",  # ← FIXED
                    details={"error": "Database schema incomplete"}
                )
```

**Test de Validación:**
```python
# tests/integration/health/test_kb_health_fixes.py

async def test_postgres_check_finds_kb_contents_table():
    """Verify postgres check uses correct table name."""
    from src.api.routers.health_kb import check_postgres_connectivity
    from src.api.dependencies import get_db_pool
    
    db_pool = await get_db_pool()
    result = await check_postgres_connectivity(db_pool)
    
    assert result.status == HealthStatus.HEALTHY
    assert "kb_contents" in result.message.lower()
```

---

### **TASK 1.2: Migrar a Structured Logging** (45 min)

**Situación Actual:**
```python
# ❌ ACTUAL: Standard Python logging
import logging
logger = logging.getLogger(__name__)

logger.error("postgresql_health_check_failed", error=str(e))
# Output: "postgresql_health_check_failed"
# → No parseable, no queryable
```

**Migración a Structlog:**
```python
# ✅ NUEVO: Structured logging (FASE H1)
import structlog
logger = structlog.get_logger(__name__)

logger.error(
    "postgresql_health_check_failed",
    error=str(e),
    error_type=type(e).__name__,
    component="postgresql",
    check_type="connectivity"
)
# Output JSON:
# {
#   "event": "postgresql_health_check_failed",
#   "error": "connection timeout",
#   "error_type": "TimeoutError",
#   "component": "postgresql",
#   "check_type": "connectivity",
#   "timestamp": "2026-02-10T14:30:45.123Z",
#   "level": "error"
# }
```

**Cambios en Archivo:**

```python
# src/api/routers/health_kb.py

# ─────────────────────────────────────────────────────────────────────────
# IMPORTS (Top of file)
# ─────────────────────────────────────────────────────────────────────────

# ❌ REMOVE:
# import logging

# ✅ ADD:
import structlog

# ─────────────────────────────────────────────────────────────────────────
# LOGGER INITIALIZATION (After imports)
# ─────────────────────────────────────────────────────────────────────────

# ❌ REMOVE:
# logger = logging.getLogger(__name__)

# ✅ ADD:
logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# STRUCTURED LOGGING IN check_postgres_connectivity()
# ─────────────────────────────────────────────────────────────────────────

async def check_postgres_connectivity(
    db_pool: asyncpg.Pool
) -> ComponentHealth:
    """..."""
    try:
        # ... código existente ...
        
        # ✅ ADD: Success log estructurado
        logger.info(
            "postgres_health_check_passed",
            component="postgresql",
            pool_size=pool_size,
            pool_free=pool_free,
            pool_usage_pct=round((pool_size - pool_free) / pool_size * 100, 2)
        )
        
        return ComponentHealth(...)
        
    except asyncpg.PostgresError as e:
        # ✅ CHANGE: Structured error log
        logger.error(
            "postgres_health_check_failed",
            error=str(e),
            error_type=type(e).__name__,
            component="postgresql",
            check_type="connectivity"
        )
        return ComponentHealth(...)
    except Exception as e:
        # ✅ CHANGE: Structured error log
        logger.error(
            "postgres_health_check_failed",
            error=str(e),
            error_type=type(e).__name__,
            component="postgresql",
            check_type="connectivity"
        )
        return ComponentHealth(...)


# ─────────────────────────────────────────────────────────────────────────
# STRUCTURED LOGGING IN check_kb_content_availability()
# ─────────────────────────────────────────────────────────────────────────

async def check_kb_content_availability(
    db_pool: asyncpg.Pool
) -> ComponentHealth:
    """..."""
    try:
        # ... código existente ...
        
        # ✅ ADD: Content metrics log
        logger.info(
            "kb_content_availability_checked",
            component="kb_content",
            total_records=total_records,
            es_records=es_count,
            en_records=en_count,
            status=status.value
        )
        
        return ComponentHealth(...)
        
    except Exception as e:
        # ✅ CHANGE: Structured error log
        logger.error(
            "kb_content_check_failed",
            error=str(e),
            error_type=type(e).__name__,
            component="kb_content"
        )
        return ComponentHealth(...)


# ─────────────────────────────────────────────────────────────────────────
# STRUCTURED LOGGING IN check_redis_connectivity()
# ─────────────────────────────────────────────────────────────────────────

async def check_redis_connectivity(redis: RedisService) -> ComponentHealth:
    """..."""
    try:
        # ... código existente ...
        
        # ✅ ADD: Redis status log
        logger.info(
            "redis_health_check_passed",
            component="redis",
            status=status,
            ping_time_ms=health_data.get("ping_time_ms")
        )
        
        return ComponentHealth(...)
        
    except Exception as e:
        # ✅ CHANGE: Structured error log
        logger.error(
            "redis_health_check_failed",
            error=str(e),
            error_type=type(e).__name__,
            component="redis"
        )
        return ComponentHealth(...)


# ─────────────────────────────────────────────────────────────────────────
# STRUCTURED LOGGING IN health_check_kb() endpoint
# ─────────────────────────────────────────────────────────────────────────

@router.get("/kb", ...)
async def health_check_kb(...) -> KBHealthResponse:
    """..."""
    
    # ✅ ADD: Start log
    logger.info(
        "health_check_started",
        endpoint="/health/kb"
    )
    
    # ... código existente ...
    
    # ✅ ADD: Completion log
    logger.info(
        "health_check_completed",
        endpoint="/health/kb",
        overall_status=overall_status.value,
        components_healthy=sum(1 for c in components.values() if c.status == HealthStatus.HEALTHY),
        components_degraded=sum(1 for c in components.values() if c.status == HealthStatus.DEGRADED),
        components_unhealthy=sum(1 for c in components.values() if c.status == HealthStatus.UNHEALTHY),
        warnings_count=len(warnings),
        recommendations_count=len(recommendations)
    )
    
    return KBHealthResponse(...)
```

**Tests:**
```python
# tests/integration/health/test_kb_health_logging.py

import structlog
from structlog.testing import LogCapture

async def test_health_check_produces_structured_logs():
    """Verify health check produces structured JSON logs."""
    
    # Capture logs
    cap = LogCapture()
    structlog.configure(processors=[cap])
    
    # Execute health check
    response = await client.get("/health/kb")
    
    # Verify structured logs
    assert len(cap.entries) > 0
    
    # Find health_check_completed log
    completed_log = next(
        (e for e in cap.entries if e["event"] == "health_check_completed"),
        None
    )
    
    assert completed_log is not None
    assert "overall_status" in completed_log
    assert "components_healthy" in completed_log
    assert "warnings_count" in completed_log
```

---

### **TASK 1.3: Add Schema Version Check** (1h)

**Objetivo:** Verificar que schema está en versión esperada (aprovecha FASE H2).

**Nueva Función:**
```python
# src/api/routers/health_kb.py

async def check_schema_version(
    db_pool: asyncpg.Pool
) -> ComponentHealth:
    """
    Verifica que schema está en versión esperada.
    
    Checks (FASE H2 integration):
    - Tabla schema_migrations existe
    - Versión actual es >= versión esperada
    - No hay pending migrations críticas
    
    Returns:
        ComponentHealth con estado del schema versioning
    """
    try:
        async with db_pool.acquire() as conn:
            # Check 1: schema_migrations table existe
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'schema_migrations'
                )
            """)
            
            if not table_exists:
                logger.warning(
                    "schema_migrations_table_not_found",
                    component="schema_version",
                    impact="Cannot track schema version"
                )
                return ComponentHealth(
                    status=HealthStatus.DEGRADED,
                    message="Schema versioning not enabled (H2 not applied)",
                    details={
                        "schema_migrations_exists": False,
                        "recommendation": "Apply migration 002_add_schema_versioning.sql"
                    }
                )
            
            # Check 2: Get current version
            current_version = await conn.fetchval(
                "SELECT MAX(version) FROM schema_migrations"
            )
            
            # Check 3: Get schema_version from kb_contents
            kb_version = await conn.fetchval(
                "SELECT DISTINCT schema_version FROM kb_contents LIMIT 1"
            )
            
            # Expected version (update as schema evolves)
            EXPECTED_MIN_VERSION = 2  # After H2, should be at least version 2
            
            if current_version < EXPECTED_MIN_VERSION:
                logger.warning(
                    "schema_version_outdated",
                    component="schema_version",
                    current_version=current_version,
                    expected_min_version=EXPECTED_MIN_VERSION
                )
                return ComponentHealth(
                    status=HealthStatus.DEGRADED,
                    message=f"Schema version outdated (current: {current_version}, expected: >= {EXPECTED_MIN_VERSION})",
                    details={
                        "current_version": current_version,
                        "expected_min_version": EXPECTED_MIN_VERSION,
                        "recommendation": "Run pending migrations"
                    }
                )
            
            # Check 4: Get migration history
            migrations = await conn.fetch(
                "SELECT version, description, applied_at FROM schema_migrations ORDER BY version"
            )
            
            logger.info(
                "schema_version_check_passed",
                component="schema_version",
                current_version=current_version,
                kb_schema_version=kb_version,
                total_migrations=len(migrations)
            )
            
            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                message=f"Schema version OK (v{current_version})",
                details={
                    "current_version": current_version,
                    "kb_schema_version": kb_version,
                    "total_migrations": len(migrations),
                    "migrations": [
                        {
                            "version": m["version"],
                            "description": m["description"],
                            "applied_at": m["applied_at"].isoformat()
                        }
                        for m in migrations
                    ]
                }
            )
            
    except Exception as e:
        logger.error(
            "schema_version_check_failed",
            error=str(e),
            error_type=type(e).__name__,
            component="schema_version"
        )
        return ComponentHealth(
            status=HealthStatus.DEGRADED,  # Not critical
            message=f"Error checking schema version: {str(e)}",
            details={"error_type": type(e).__name__}
        )
```

**Integración en health_check_kb():**
```python
@router.get("/kb", ...)
async def health_check_kb(...) -> KBHealthResponse:
    """..."""
    
    # ✅ ADD: Schema version check to parallel execution
    postgres_check, content_check, redis_check, schema_check = await asyncio.gather(
        check_postgres_connectivity(db_pool),
        check_kb_content_availability(db_pool),
        check_redis_connectivity(redis),
        check_schema_version(db_pool),  # ← NUEVO
        return_exceptions=True
    )
    
    # ... handle exceptions ...
    
    components = {
        "postgres": postgres_check,
        "kb_content": content_check,
        "redis": redis_check,
        "schema_version": schema_check  # ← NUEVO
    }
    
    # ... resto del código ...
```

**Tests:**
```python
# tests/integration/health/test_schema_version_check.py

async def test_schema_version_check_healthy():
    """Verify schema version check passes when H2 applied."""
    from src.api.routers.health_kb import check_schema_version
    from src.api.dependencies import get_db_pool
    
    db_pool = await get_db_pool()
    result = await check_schema_version(db_pool)
    
    assert result.status == HealthStatus.HEALTHY
    assert result.details["current_version"] >= 2
    assert "migrations" in result.details

async def test_schema_version_check_degraded_if_h2_not_applied():
    """Verify degraded status if schema_migrations doesn't exist."""
    # Simulate: Drop schema_migrations temporarily
    async with db_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS schema_migrations")
    
    result = await check_schema_version(db_pool)
    
    assert result.status == HealthStatus.DEGRADED
    assert "not enabled" in result.message.lower()
    
    # Restore table
    await apply_migration("002_add_schema_versioning.sql")
```

---

### **TASK 1.4: Test de Regresión Completo** (30 min)

**Objetivo:** Garantizar que cambios no rompen funcionalidad existente.

**Suite de Tests:**
```python
# tests/integration/health/test_health_regression.py

import pytest
from fastapi.testclient import TestClient

class TestHealthRegressionSuite:
    """Regression tests for health checks after H3 changes."""
    
    async def test_health_kb_endpoint_still_works(self, client):
        """Verify /health/kb endpoint works after H3 changes."""
        response = await client.get("/health/kb")
        
        assert response.status_code == 200
        
        data = response.json()
        assert "overall_status" in data
        assert "components" in data
        assert "sync_metrics" in data
        assert "warnings" in data
        assert "recommendations" in data
    
    async def test_health_simple_endpoint_still_works(self, client):
        """Verify /health/kb/simple endpoint works."""
        response = await client.get("/health/kb/simple")
        
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["records"] > 0
    
    async def test_health_response_structure_unchanged(self, client):
        """Verify response structure matches original schema."""
        response = await client.get("/health/kb")
        data = response.json()
        
        # Verify original fields still present
        assert "postgres" in data["components"]
        assert "kb_content" in data["components"]
        assert "redis" in data["components"]
        
        # Verify new field added
        assert "schema_version" in data["components"]
        
        # Verify sync_metrics structure unchanged
        metrics = data["sync_metrics"]
        assert "total_records" in metrics
        assert "languages" in metrics
        assert "oldest_sync" in metrics
    
    async def test_health_check_performance_not_degraded(self, client):
        """Verify health check still completes quickly."""
        import time
        
        start = time.time()
        response = await client.get("/health/kb")
        duration = (time.time() - start) * 1000  # ms
        
        assert response.status_code == 200
        assert duration < 500, f"Health check too slow: {duration}ms"
    
    async def test_all_original_warnings_still_generated(self, client):
        """Verify warning generation logic unchanged."""
        # Simulate stale content
        await set_kb_last_synced(datetime.utcnow() - timedelta(hours=72))
        
        response = await client.get("/health/kb")
        data = response.json()
        
        warnings = data["warnings"]
        assert any("not synced" in w.lower() for w in warnings)
    
    async def test_structured_logs_generated(self, client, log_capture):
        """Verify structured logs are generated."""
        response = await client.get("/health/kb")
        
        logs = log_capture.entries
        assert len(logs) > 0
        
        # Verify JSON structure
        for log in logs:
            assert "event" in log
            assert "timestamp" in log
            assert "level" in log
```

**Ejecución:**
```bash
# Día 1 - Final validation
pytest tests/integration/health/test_health_regression.py -v

# Expected output:
# ✅ test_health_kb_endpoint_still_works PASSED
# ✅ test_health_simple_endpoint_still_works PASSED
# ✅ test_health_response_structure_unchanged PASSED
# ✅ test_health_check_performance_not_degraded PASSED
# ✅ test_all_original_warnings_still_generated PASSED
# ✅ test_structured_logs_generated PASSED
#
# 6/6 tests PASSED
```

---

## 🔧 IMPLEMENTACIÓN - DÍA 2

### **TASK 2.1: Implement Deep Check Mode** (1h)

**Objetivo:** Agregar parámetro `?deep=true` para checks extensivos (Shopify API).

**Cambios en Endpoint:**
```python
# src/api/routers/health_kb.py

@router.get(
    "/kb",
    response_model=KBHealthResponse,
    summary="Knowledge Base Health Check",
    description="""
    Comprehensive health check for KB v2 Multi-Language system.
    
    Query Parameters:
    - deep (bool, optional): If True, performs deep checks including Shopify API.
                             Default: False
                             Warning: Deep check adds ~2-3 seconds latency
    
    Example: GET /health/kb?deep=true
    """
)
async def health_check_kb(
    deep: bool = False,  # ← NUEVO PARÁMETRO
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis: RedisService = Depends(get_redis_service)
) -> KBHealthResponse:
    """
    Ejecuta health check completo del Knowledge Base.
    
    Args:
        deep: Si True, ejecuta checks profundos (Shopify API, etc.)
              Agrega ~2-3s de latency pero verifica conectividad externa.
    """
    
    logger.info(
        "health_check_started",
        endpoint="/health/kb",
        deep_check=deep
    )
    
    # Preparar lista de checks
    check_tasks = [
        check_postgres_connectivity(db_pool),
        check_kb_content_availability(db_pool),
        check_redis_connectivity(redis),
        check_schema_version(db_pool)
    ]
    
    # ✅ AGREGAR: Shopify check solo si deep=True
    if deep:
        # Dependency injection de ShopifyKBClient
        from src.api.dependencies import get_shopify_kb_client
        shopify_client = await get_shopify_kb_client()
        
        check_tasks.append(
            check_shopify_graphql(shopify_client)
        )
    
    # Ejecutar todos los checks en paralelo
    results = await asyncio.gather(*check_tasks, return_exceptions=True)
    
    # ... procesar resultados ...
```

---

### **TASK 2.2: Implement Shopify GraphQL Check** (2h)

**Nueva Dependency:**
```python
# src/api/dependencies.py

from src.api.integrations.shopify_kb_client import ShopifyKBClient

async def get_shopify_kb_client() -> ShopifyKBClient:
    """
    Dependency para obtener cliente de Shopify KB.
    
    Returns:
        ShopifyKBClient inicializado
    """
    # ✅ TODO: Implementar lógica de inicialización
    # Probablemente ya existe en alguna parte del código
    ...
```

**Nueva Función de Check:**
```python
# src/api/routers/health_kb.py

async def check_shopify_graphql(
    shopify_client: ShopifyKBClient
) -> ComponentHealth:
    """
    Verifica conectividad con Shopify GraphQL API.
    
    Checks:
    - API accesible (HTTP 200)
    - shopLocales query exitoso
    - Latency razonable (<3s)
    
    WARNING: Esta operación es LENTA (~2-3s)
    Solo debe ejecutarse con ?deep=true
    
    Returns:
        ComponentHealth con estado de Shopify API
    """
    import time
    
    try:
        start_time = time.time()
        
        # ✅ CALL: Fetch shop locales (test query)
        primary_locale, available_locales = await shopify_client._get_shop_locales()
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Validar latency
        if latency_ms > 5000:  # >5s es muy lento
            logger.warning(
                "shopify_graphql_slow",
                component="shopify",
                latency_ms=latency_ms,
                threshold_ms=5000
            )
            return ComponentHealth(
                status=HealthStatus.DEGRADED,
                message=f"Shopify API responding slowly ({latency_ms:.0f}ms)",
                details={
                    "latency_ms": round(latency_ms, 2),
                    "primary_locale": primary_locale,
                    "available_locales": available_locales
                }
            )
        
        logger.info(
            "shopify_graphql_check_passed",
            component="shopify",
            latency_ms=latency_ms,
            primary_locale=primary_locale,
            locales_count=len(available_locales)
        )
        
        return ComponentHealth(
            status=HealthStatus.HEALTHY,
            message=f"Shopify GraphQL API OK ({latency_ms:.0f}ms)",
            details={
                "latency_ms": round(latency_ms, 2),
                "primary_locale": primary_locale,
                "available_locales": available_locales,
                "locales_count": len(available_locales)
            }
        )
        
    except Exception as e:
        logger.error(
            "shopify_graphql_check_failed",
            error=str(e),
            error_type=type(e).__name__,
            component="shopify"
        )
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Shopify API error: {str(e)}",
            details={"error_type": type(e).__name__}
        )
```

**Tests:**
```python
# tests/integration/health/test_shopify_check.py

async def test_shopify_check_only_with_deep_mode():
    """Verify Shopify check only runs with ?deep=true."""
    
    # Without deep parameter
    response = await client.get("/health/kb")
    data = response.json()
    
    assert "shopify" not in data["components"]
    
    # With deep=true
    response = await client.get("/health/kb?deep=true")
    data = response.json()
    
    assert "shopify" in data["components"]
    assert data["components"]["shopify"]["status"] in ["healthy", "degraded", "unhealthy"]

async def test_shopify_check_measures_latency():
    """Verify Shopify check measures API latency."""
    response = await client.get("/health/kb?deep=true")
    data = response.json()
    
    shopify_component = data["components"]["shopify"]
    assert "latency_ms" in shopify_component["details"]
    assert shopify_component["details"]["latency_ms"] > 0

async def test_shopify_check_fails_gracefully():
    """Verify Shopify check handles API failures."""
    # Mock Shopify client to raise exception
    with mock.patch.object(
        shopify_client,
        '_get_shop_locales',
        side_effect=TimeoutError("GraphQL timeout")
    ):
        response = await client.get("/health/kb?deep=true")
        data = response.json()
        
        assert data["components"]["shopify"]["status"] == "unhealthy"
        assert "timeout" in data["components"]["shopify"]["message"].lower()
```

---

## 🔧 IMPLEMENTACIÓN - DÍA 3

### **TASK 3.1: Instrumentar Performance Metrics** (1h)

**Objetivo:** Medir y validar response time (<500ms target sin deep check).

**Timing Middleware:**
```python
# src/api/routers/health_kb.py

import time
from functools import wraps

def measure_check_time(check_name: str):
    """
    Decorator para medir tiempo de ejecución de checks.
    
    Usage:
    ------
    @measure_check_time("postgres")
    async def check_postgres_connectivity(...):
        ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            duration_ms = (time.time() - start) * 1000
            
            logger.info(
                "health_check_timing",
                check=check_name,
                duration_ms=round(duration_ms, 2),
                status=result.status.value if hasattr(result, 'status') else "unknown"
            )
            
            return result
        return wrapper
    return decorator


# Aplicar a todas las funciones de check
@measure_check_time("postgres")
async def check_postgres_connectivity(...): ...

@measure_check_time("kb_content")
async def check_kb_content_availability(...): ...

@measure_check_time("redis")
async def check_redis_connectivity(...): ...

@measure_check_time("schema_version")
async def check_schema_version(...): ...

@measure_check_time("shopify")
async def check_shopify_graphql(...): ...
```

**Total Timing en Endpoint:**
```python
@router.get("/kb", ...)
async def health_check_kb(...) -> KBHealthResponse:
    """..."""
    
    # ✅ START TIMING
    start_time = time.time()
    
    logger.info(
        "health_check_started",
        endpoint="/health/kb",
        deep_check=deep
    )
    
    # ... ejecutar checks ...
    
    # ✅ END TIMING
    total_duration_ms = (time.time() - start_time) * 1000
    
    logger.info(
        "health_check_completed",
        endpoint="/health/kb",
        overall_status=overall_status.value,
        total_duration_ms=round(total_duration_ms, 2),
        deep_check=deep,
        components_count=len(components),
        warnings_count=len(warnings)
    )
    
    # ✅ VALIDATION: Alert if too slow (without deep check)
    if not deep and total_duration_ms > 500:
        logger.warning(
            "health_check_slow",
            total_duration_ms=total_duration_ms,
            threshold_ms=500,
            recommendation="Investigate slow components"
        )
    
    return KBHealthResponse(...)
```

**Tests:**
```python
# tests/integration/health/test_health_performance.py

async def test_health_check_completes_within_500ms():
    """Verify health check meets performance target."""
    import time
    
    start = time.time()
    response = await client.get("/health/kb")  # Without deep
    duration_ms = (time.time() - start) * 1000
    
    assert response.status_code == 200
    assert duration_ms < 500, f"Health check too slow: {duration_ms:.2f}ms (target: <500ms)"

async def test_deep_check_acceptable_latency():
    """Verify deep check completes within reasonable time."""
    import time
    
    start = time.time()
    response = await client.get("/health/kb?deep=true")
    duration_ms = (time.time() - start) * 1000
    
    assert response.status_code == 200
    # Deep check allows up to 5 seconds (includes Shopify API)
    assert duration_ms < 5000, f"Deep check too slow: {duration_ms:.2f}ms"
```

---

### **TASK 3.2: Mejorar Staleness Warnings** (30 min)

**Objetivo:** Generar warnings más descriptivos para content staleness.

**Mejora en `generate_warnings_and_recommendations()`:**
```python
def generate_warnings_and_recommendations(
    components: Dict[str, ComponentHealth],
    sync_metrics: Optional[SyncMetrics]
) -> tuple[List[str], List[str]]:
    """
    Genera warnings y recomendaciones basadas en el estado del sistema.
    """
    warnings = []
    recommendations = []
    
    # ... código existente ...
    
    # ✅ MEJORADO: Content staleness warning más detallado
    if sync_metrics and sync_metrics.oldest_sync:
        age_hours = (datetime.utcnow() - sync_metrics.oldest_sync).total_seconds() / 3600
        
        if age_hours > 72:  # >3 días
            warnings.append(
                f"⚠️ Content severely stale: oldest record is {age_hours:.1f} hours old (>72h threshold)"
            )
            recommendations.append(
                "URGENT: Run sync_all_pages() immediately to update content"
            )
        elif age_hours > 48:  # >2 días
            warnings.append(
                f"Content moderately stale: oldest record is {age_hours:.1f} hours old (>48h threshold)"
            )
            recommendations.append(
                "Run sync_all_pages() soon to keep content fresh"
            )
    
    # ✅ NUEVO: Per-language staleness
    if sync_metrics:
        for lang_coverage in sync_metrics.languages:
            if lang_coverage.last_synced:
                age_hours = (datetime.utcnow() - lang_coverage.last_synced).total_seconds() / 3600
                
                if age_hours > 48:
                    warnings.append(
                        f"Language '{lang_coverage.language}' content stale: {age_hours:.1f} hours old"
                    )
                    recommendations.append(
                        f"Sync Shopify pages with language={lang_coverage.language}"
                    )
    
    return warnings, recommendations
```

---

### **TASK 3.3: Documentation Updates** (30 min)

**Actualizar Docstrings:**
```python
# src/api/routers/health_kb.py

"""
Health Check Endpoint - Knowledge Base v2 (ENHANCED - FASE H3)
==============================================================

🎯 OBJETIVO:
Proporcionar visibilidad completa del estado del sistema KB Multi-Language
con checks comprehensivos, métricas detalladas y alertas tempranas.

✅ FEATURES (Post-H3):
- ✅ PostgreSQL connectivity + pool metrics
- ✅ KB content availability + language coverage
- ✅ Redis connectivity (degraded mode friendly)
- ✅ Schema versioning status (FASE H2 integration)
- ✅ Shopify GraphQL API health (deep mode only)
- ✅ Content staleness alerts (>48h, >72h)
- ✅ Structured logging (FASE H1 integration)
- ✅ Performance instrumentation (<500ms target)

🔄 USAGE:
- Kubernetes liveness probe: GET /health/kb/simple
- Kubernetes readiness probe: GET /health/kb
- Monitoring dashboard: GET /health/kb (poll every 60s)
- Deep validation: GET /health/kb?deep=true (manual check)

📊 RESPONSE FORMAT:
{
  "overall_status": "healthy" | "degraded" | "unhealthy",
  "timestamp": "2026-02-10T14:30:45.123Z",
  "components": {
    "postgres": { "status": "healthy", "message": "...", "details": {...} },
    "kb_content": { "status": "healthy", ... },
    "redis": { "status": "healthy", ... },
    "schema_version": { "status": "healthy", ... },
    "shopify": { "status": "healthy", ... }  // Only with ?deep=true
  },
  "sync_metrics": {
    "total_records": 27,
    "languages": [...],
    "stale_records_24h": 0,
    ...
  },
  "warnings": [],
  "recommendations": []
}

⚡ PERFORMANCE:
- Normal mode: <500ms target
- Deep mode: ~2-3s (includes Shopify API call)

🔗 DEPENDENCIES:
- FASE H1: Structured Logging (structlog)
- FASE H2: Schema Versioning (schema_migrations table)

Fecha: 10 Febrero 2026 (Updated for H3)
Version: 2.0.0 (Enhanced Health Checks)
"""
```

**README Update:**
```markdown
# Health Check Endpoints

## GET /health/kb

Comprehensive health check for Knowledge Base system.

**Query Parameters:**
- `deep` (boolean, optional): Enable deep checks including Shopify API validation.
  - Default: `false`
  - Warning: Adds ~2-3s latency

**Response Time:**
- Normal mode: <500ms
- Deep mode: ~2-3s

**Status Levels:**
- `healthy`: All systems operational
- `degraded`: Minor issues (e.g., Redis slow, missing translations)
- `unhealthy`: Critical issues (e.g., DB down, no content)

**Examples:**

```bash
# Quick check (K8s readiness probe)
curl http://localhost:8000/health/kb

# Deep check (manual validation)
curl http://localhost:8000/health/kb?deep=true

# Parse with jq
curl http://localhost:8000/health/kb | jq '.components.postgres'
```

## GET /health/kb/simple

Simplified health check for load balancers.

**Response:** HTTP 200 if healthy, HTTP 503 if unhealthy

**Usage:**
```bash
# K8s liveness probe
livenessProbe:
  httpGet:
    path: /health/kb/simple
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
```
```

---

## ✅ VALIDACIÓN FINAL

### **Checklist Pre-Deployment**

```bash
# ─────────────────────────────────────────────────────────────────────────
# DÍA 1: FIXES + STRUCTURED LOGGING + SCHEMA VERSION
# ─────────────────────────────────────────────────────────────────────────

# 1. Verificar tabla name fix
grep -n "kb_content'" src/api/routers/health_kb.py
# Debería mostrar 'kb_contents' (plural)

# 2. Verificar structured logging
grep -n "import structlog" src/api/routers/health_kb.py
grep -n "structlog.get_logger" src/api/routers/health_kb.py

# 3. Run tests
pytest tests/integration/health/test_health_regression.py -v
pytest tests/integration/health/test_schema_version_check.py -v

# Expected: ALL PASSED

# ─────────────────────────────────────────────────────────────────────────
# DÍA 2: DEEP CHECK + SHOPIFY API
# ─────────────────────────────────────────────────────────────────────────

# 4. Verificar deep parameter
grep -n "deep: bool = False" src/api/routers/health_kb.py

# 5. Verificar Shopify check implementado
grep -n "check_shopify_graphql" src/api/routers/health_kb.py

# 6. Run tests
pytest tests/integration/health/test_shopify_check.py -v

# Expected: ALL PASSED

# ─────────────────────────────────────────────────────────────────────────
# DÍA 3: PERFORMANCE + OBSERVABILITY
# ─────────────────────────────────────────────────────────────────────────

# 7. Verificar timing instrumentation
grep -n "measure_check_time" src/api/routers/health_kb.py

# 8. Run performance tests
pytest tests/integration/health/test_health_performance.py -v

# Expected: test_health_check_completes_within_500ms PASSED

# ─────────────────────────────────────────────────────────────────────────
# VALIDACIÓN COMPLETA
# ─────────────────────────────────────────────────────────────────────────

# 9. Run ALL health tests
pytest tests/integration/health/ -v

# Expected: 15-20 tests ALL PASSED

# 10. Manual smoke test
curl http://localhost:8000/health/kb | jq '.'
curl http://localhost:8000/health/kb?deep=true | jq '.'
curl http://localhost:8000/health/kb/simple

# Expected: All return 200, valid JSON
```

---

## 📊 MÉTRICAS DE ÉXITO

### **Criterios de Aceptación**

| Criterio | Target | Validación |
|----------|--------|------------|
| **Table name fix** | kb_contents (plural) | ✅ Grep + tests |
| **Structured logging** | 100% migrado | ✅ Log capture tests |
| **Schema version check** | Implementado | ✅ check_schema_version() exists |
| **Deep mode** | ?deep=true funcional | ✅ Shopify check runs |
| **Shopify API check** | Implementado | ✅ Latency < 5s |
| **Performance** | <500ms (normal) | ✅ Performance tests |
| **Response structure** | Sin breaking changes | ✅ Regression tests |
| **Test coverage** | >90% | ✅ pytest --cov |

### **KPIs Post-H3**

```
Antes (Pre-H3):
├─ Checks: 3 (PostgreSQL, KB content, Redis)
├─ Structured logging: ❌ No
├─ Schema versioning check: ❌ No
├─ Shopify API check: ❌ No
├─ Performance target: No medido
└─ Deep mode: ❌ No implementado

Después (Post-H3):
├─ Checks: 4 normal + 1 deep (5 total) ✅
├─ Structured logging: ✅ 100%
├─ Schema versioning check: ✅ Implementado
├─ Shopify API check: ✅ Deep mode only
├─ Performance target: ✅ <500ms validado
└─ Deep mode: ✅ ?deep=true funcional
```

---

## 🚀 DEPLOYMENT

### **Rollout Strategy**

```
FASE 1: Development
├─ Crear branch: feat/h3-enhanced-health-checks
├─ Implementar cambios Día 1-3
├─ Tests locales: pytest
└─ Smoke tests: curl local

FASE 2: Staging
├─ Merge a staging branch
├─ Deploy a staging environment
├─ Run integration tests
├─ Monitor logs (structlog output)
└─ Validate performance (<500ms)

FASE 3: Production (Blue-Green)
├─ Deploy a producción (canary 10%)
├─ Monitor health endpoints
├─ Validate metrics
├─ Scale to 100% if healthy
└─ Rollback plan ready
```

### **Rollback Plan**

```bash
# Si health checks fallan en prod:

# 1. Revert deploy
git revert <commit-hash>
git push origin main

# 2. Redeploy versión anterior
kubectl rollout undo deployment/retail-recommender-api

# 3. Verify rollback
curl http://prod-api/health/kb

# 4. Investigation
kubectl logs -f deployment/retail-recommender-api | grep "health_check"
```

---

## 📚 DOCUMENTACIÓN ADICIONAL

### **Referencias Internas**

```
docs/
├─ 0_plans/
│  └─ KB System - Phase Improvements/
│     └─ Plan_de_accion_consolidado_06022026.md (H3 definition)
│
├─ deployment/
│  └─ h2_schema_versioning/
│     └─ DCT_FASE_H2_COMPLETADA_Y_VALIDADA_10FEB2026.md
│
└─ architecture/
   └─ health_checks_architecture.md (TO CREATE)
```

### **External References**

- Structured Logging: https://www.structlog.org/
- FastAPI Health Checks: https://fastapi.tiangolo.com/advanced/testing/
- Kubernetes Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

---

## ✅ CONCLUSIÓN

### **Estado del Plan**

```
┌──────────────────────────────────────────────────────────────┐
│ ✅ FASE H3: PLANNING COMPLETADA                              │
├──────────────────────────────────────────────────────────────┤
│ Análisis de estado actual: ✅ COMPLETADO                     │
│ Gap analysis: ✅ 6 gaps identificados                        │
│ Plan detallado: ✅ 3 días / 11 horas                         │
│ Tests definidos: ✅ 15-20 tests                              │
│ Métricas de éxito: ✅ 8 criterios                            │
│ Rollback strategy: ✅ PREPARADA                              │
├──────────────────────────────────────────────────────────────┤
│ RECOMENDACIÓN: ✅ PROCEDER CON IMPLEMENTACIÓN                │
└──────────────────────────────────────────────────────────────┘
```

### **Próximos Pasos Inmediatos**

**AHORA (HOY):**
1. ✅ Revisar y aprobar este plan
2. ✅ Crear branch `feat/h3-enhanced-health-checks`
3. ✅ Comenzar Día 1 - Task 1.1 (table name fix)

**ESTA SEMANA:**
1. Completar Día 1-3 (11 horas)
2. Run all tests (15-20 tests)
3. Merge to staging
4. Validation en staging

**PRÓXIMA SEMANA:**
1. Deploy to production (canary)
2. Monitor 24-48h
3. Full production rollout
4. Declarar H3 completada

---

**Elaborado por:** Yasmani (Senior Software Architect)  
**Fecha:** 2026-02-10  
**Versión:** 1.0.0  
**Status:** ✅ READY FOR IMPLEMENTATION

---

**FIN DEL PLAN DE IMPLEMENTACIÓN - FASE H3**
