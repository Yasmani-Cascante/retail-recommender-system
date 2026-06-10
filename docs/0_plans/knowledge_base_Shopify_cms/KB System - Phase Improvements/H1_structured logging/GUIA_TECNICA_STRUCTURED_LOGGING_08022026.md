# 📘 GUÍA TÉCNICA - STRUCTURED LOGGING IMPLEMENTATION

**Sistema:** Retail Recommender System  
**Fase:** H1 - Structured Logging Migration  
**Fecha:** 2026-02-08  
**Versión:** 1.0.0

---

## 📖 TABLA DE CONTENIDOS

1. [Introducción](#introducción)
2. [Arquitectura de Logging](#arquitectura-de-logging)
3. [Convenciones y Patrones](#convenciones-y-patrones)
4. [Guía de Implementación](#guía-de-implementación)
5. [Testing de Structured Logging](#testing-de-structured-logging)
6. [Troubleshooting](#troubleshooting)
7. [Mejores Prácticas](#mejores-prácticas)
8. [Referencia Rápida](#referencia-rápida)

---

## 🎯 INTRODUCCIÓN

### **¿Qué es Structured Logging?**

Structured Logging transforma logs de texto plano a eventos JSON estructurados:

**ANTES (String Logging):**
```python
logger.info(f"Product {product_id} retrieved from Redis in {elapsed}ms")
```

**DESPUÉS (Structured Logging):**
```python
logger.info(
    "product_cache_redis_hit",
    product_id=product_id,
    elapsed_ms=elapsed,
    source="redis"
)
```

---

### **¿Por Qué Structured Logging?**

| Beneficio | Descripción |
|-----------|-------------|
| **Queryable** | `event="product_cache_redis_hit" AND elapsed_ms > 100` |
| **Aggregatable** | Promedios, percentiles, conteos automáticos |
| **Alertable** | Reglas basadas en campos estructurados |
| **Traceable** | Correlation IDs, request tracking |
| **Scalable** | Procesamiento automático sin regex |

---

### **Stack Tecnológico**

```
┌─────────────────────────────────────┐
│   Application Code (FastAPI)       │
│   └─ structlog.get_logger(__name__)│
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│   Structlog (v24.1.0)              │
│   └─ Processors + Formatters       │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│   Output Targets                    │
│   ├─ Console (Development)          │
│   ├─ File (Production)              │
│   └─ Shipping (Elasticsearch, etc.) │
└─────────────────────────────────────┘
```

---

## 🏗️ ARQUITECTURA DE LOGGING

### **Configuración Global**

**Ubicación:** `src/api/core/config.py` o `main.py`

```python
import structlog

def configure_logging():
    """
    Configura structured logging para toda la aplicación.
    
    CRÍTICO: Llamar ANTES de cualquier logger.get_logger()
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

**Llamar en `main.py`:**
```python
from fastapi import FastAPI
from src.api.core.config import configure_logging

configure_logging()  # ← ANTES de cualquier import que use logging

app = FastAPI()
```

---

### **Uso en Módulos**

**En CADA archivo que necesite logging:**

```python
# ============================================================================
# H1: STRUCTURED LOGGING IMPORT
# ============================================================================
import structlog
logger = structlog.get_logger(__name__)

# ============================================================================
# RESTO DEL CÓDIGO
# ============================================================================

class MyClass:
    def __init__(self):
        logger.info(
            "my_class_initialized",
            config_param=value
        )
```

---

## 📏 CONVENCIONES Y PATRONES

### **Naming Convention**

```
{component}_{subcomponent}_{action}_{status}

Ejemplos:
- product_cache_redis_hit
- product_cache_shopify_error
- redis_connection_success
- shopify_kb_page_validated
```

---

### **Niveles de Log**

| Nivel | Uso | Ejemplo |
|-------|-----|---------|
| `DEBUG` | High-frequency, desarrollo | Cache hits, operaciones exitosas |
| `INFO` | Eventos importantes, operaciones | Inicialización, warmup completado |
| `WARNING` | Situaciones anómalas, no errores | Producto no encontrado, datos corruptos |
| `ERROR` | Fallos que requieren atención | Errores de conexión, excepciones |

**Regla de Oro:**
> Si el evento ocurre >100 veces/minuto en producción → `DEBUG`  
> Si el evento indica estado del sistema → `INFO`  
> Si algo falló pero hay fallback → `WARNING`  
> Si algo falló sin recovery → `ERROR`

---

### **Campos Estándar**

**SIEMPRE incluir (automático):**
- `timestamp` - ISO 8601 format
- `event` - Nombre del evento
- `level` - debug, info, warning, error
- `logger` - Nombre del módulo

**SIEMPRE incluir (manual) cuando aplique:**
- `product_id` - ID del producto
- `user_id` - ID del usuario (si disponible)
- `request_id` - Correlation ID (si disponible)
- `error` - Mensaje de error
- `error_type` - Clase de excepción
- `exc_info` - True para stack trace completo

---

### **Campos Contextuales**

```python
# ✅ BUENO - Contexto rico
logger.info(
    "product_cache_redis_hit",
    product_id=product_id,
    data_length=len(data),
    ttl_seconds=ttl,
    source="redis"
)

# ❌ MALO - Sin contexto
logger.info("product_cache_redis_hit")

# ❌ MALO - String interpolation (no queryable)
logger.info(f"Product {product_id} hit Redis")
```

---

## 🛠️ GUÍA DE IMPLEMENTACIÓN

### **PASO 1: Importar Structlog**

```python
# Al inicio del archivo, después de imports estándar
import structlog
logger = structlog.get_logger(__name__)
```

---

### **PASO 2: Identificar Puntos de Logging**

**Categorías a instrumentar:**

1. **Initialization**
   ```python
   def __init__(self, ...):
       # Setup
       logger.info(
           "component_initialized",
           param1=value1,
           param2=value2
       )
   ```

2. **Operations (Successful)**
   ```python
   result = await self.operation()
   if result:
       logger.debug(  # ← DEBUG si high-frequency
           "component_operation_success",
           operation="get",
           result_size=len(result)
       )
   ```

3. **Operations (Failed)**
   ```python
   if not result:
       logger.warning(
           "component_operation_failed",
           operation="get",
           reason="not_found"
       )
   ```

4. **Errors**
   ```python
   try:
       result = await self.external_call()
   except Exception as e:
       logger.error(
           "component_external_call_error",
           error=str(e),
           error_type=type(e).__name__,
           exc_info=True  # ← CRÍTICO para stack trace
       )
   ```

---

### **PASO 3: Migrar Logs Existentes**

**Proceso de Migración:**

```python
# ANTES
logger.info(f"Connecting to Redis at {host}:{port}")

# DESPUÉS
logger.info(
    "redis_connection_attempt",
    host=host,
    port=port
)
```

**Template de Migración:**

1. Identificar el string log
2. Extraer variables interpoladas
3. Crear evento con nombre descriptivo
4. Pasar variables como kwargs
5. Agregar contexto adicional relevante

---

### **PASO 4: Probar el Logging**

Ver sección [Testing de Structured Logging](#testing-de-structured-logging)

---

## 🧪 TESTING DE STRUCTURED LOGGING

### **Setup de Tests**

**Fixture Estándar:**

```python
import pytest
import structlog
from structlog.testing import LogCapture

@pytest.fixture
def log_capture(monkeypatch):
    """
    Captura eventos de structured logging para testing.
    
    Yields:
        LogCapture: Objeto con lista de eventos en .entries
    """
    capture = LogCapture()
    
    structlog.configure(
        processors=[capture],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    
    yield capture
    
    capture.entries.clear()
```

---

### **Patrón de Test Básico**

```python
@pytest.mark.asyncio
async def test_operation_logs_event(log_capture):
    """Test: Operación loggea evento con campos correctos."""
    # Setup
    component = MyComponent()
    
    # Execute
    log_capture.entries.clear()  # ← Limpiar eventos previos
    result = await component.operation("param1")
    
    # Verify
    events = [e for e in log_capture.entries if e.get("event") == "component_operation_success"]
    assert len(events) == 1
    
    event = events[0]
    assert event["level"] == "info"
    assert event["param1"] == "param1"
    assert "result_size" in event
```

---

### **Patrón de Test de Errores**

```python
@pytest.mark.asyncio
async def test_operation_logs_error(log_capture, mock_dependency):
    """Test: Error loggea evento con exc_info."""
    # Setup: Dependency lanza error
    mock_dependency.call.side_effect = Exception("Test error")
    component = MyComponent(dependency=mock_dependency)
    
    # Execute
    log_capture.entries.clear()
    result = await component.operation()
    
    # Verify
    error_events = [e for e in log_capture.entries if e.get("event") == "component_operation_error"]
    assert len(error_events) == 1
    
    event = error_events[0]
    assert event["level"] == "error"
    assert event["error_type"] == "Exception"
    assert "Test error" in event["error"]
```

---

### **Gotchas de Testing**

#### **1. Empty Dict Gotcha**

```python
# ❌ INCORRECTO - entries es objeto, no lista
events = log_capture.entries.get("event") == "my_event"

# ✅ CORRECTO - iterar sobre entries
events = [e for e in log_capture.entries if e.get("event") == "my_event"]
```

#### **2. Monkeypatch Scope**

```python
# ✅ CORRECTO - Fixture con yield
@pytest.fixture
def log_capture(monkeypatch):
    capture = LogCapture()
    structlog.configure(processors=[capture], ...)
    yield capture  # ← Permite cleanup
    capture.entries.clear()
```

#### **3. Async Mocking**

```python
# ❌ INCORRECTO - Mock no es awaitable
mock.method = Mock(return_value=value)

# ✅ CORRECTO - AsyncMock es awaitable
mock.method = AsyncMock(return_value=value)
```

---

## 🔧 TROUBLESHOOTING

### **Problema 1: "No se capturan eventos en tests"**

**Síntomas:**
```python
events = [e for e in log_capture.entries if e.get("event") == "my_event"]
assert len(events) == 1  # ← Falla: len(events) == 0
```

**Causas Posibles:**

1. **No se limpió entries antes del test**
   ```python
   # ✅ FIX
   log_capture.entries.clear()
   await component.operation()
   ```

2. **Configuración de structlog sobrescrita**
   ```python
   # ✅ FIX - Asegurar que fixture se ejecuta primero
   def test_my_test(log_capture):  # ← log_capture PRIMERO
       ...
   ```

3. **Logger no configurado correctamente**
   ```python
   # ❌ INCORRECTO
   from logging import getLogger
   logger = getLogger(__name__)
   
   # ✅ CORRECTO
   import structlog
   logger = structlog.get_logger(__name__)
   ```

---

### **Problema 2: "Tests fallan con AsyncMock"**

**Síntomas:**
```python
TypeError: object Mock can't be used in 'await' expression
```

**Causa:**
Función async mockeada con `Mock` en vez de `AsyncMock`

**Fix:**
```python
# ❌ INCORRECTO
mock.async_method = Mock(return_value=value)

# ✅ CORRECTO
mock.async_method = AsyncMock(return_value=value)

# ✅ CORRECTO para patch
mock_from_url = AsyncMock(return_value=mock_client)
with patch("module.redis.from_url", new=mock_from_url):
    ...
```

---

### **Problema 3: "Eventos duplicados"**

**Síntomas:**
```python
assert len(events) == 1  # ← Falla: len(events) == 2
```

**Causa:**
Try-except anidados loggeando el mismo error

**Fix:**
```python
# ❌ INCORRECTO - Logging duplicado
async def _get_data(self):
    try:
        return await self.client.get()
    except Exception as e:
        logger.error("get_error", ...)  # ← Log 1

async def get_data(self):
    try:
        return await self._get_data()
    except Exception as e:
        logger.error("get_error", ...)  # ← Log 2 (DUPLICADO!)

# ✅ CORRECTO - Solo loggear en método público
async def _get_data(self):
    # NO capturar excepción, dejar que se propague
    return await self.client.get()

async def get_data(self):
    try:
        return await self._get_data()
    except Exception as e:
        logger.error("get_error", ...)  # ← UN SOLO LOG
```

---

## 💡 MEJORES PRÁCTICAS

### **DO: Cosas que SIEMPRE debes hacer**

1. **Usar nombres de evento descriptivos**
   ```python
   # ✅ BUENO
   logger.info("product_cache_redis_hit", product_id=pid)
   
   # ❌ MALO
   logger.info("hit", id=pid)
   ```

2. **Incluir contexto rico**
   ```python
   # ✅ BUENO
   logger.error(
       "shopify_api_error",
       product_id=pid,
       error=str(e),
       error_type=type(e).__name__,
       exc_info=True,
       retry_attempt=retry_count
   )
   
   # ❌ MALO
   logger.error("error", error=str(e))
   ```

3. **Usar exc_info para errores**
   ```python
   # ✅ BUENO
   logger.error("operation_failed", exc_info=True)
   
   # ❌ MALO
   logger.error("operation_failed")  # Sin stack trace
   ```

4. **Limpiar log_capture en tests**
   ```python
   # ✅ BUENO
   log_capture.entries.clear()
   result = await operation()
   
   # ❌ MALO (eventos acumulados de tests previos)
   result = await operation()
   ```

---

### **DON'T: Cosas que NUNCA debes hacer**

1. **NO usar f-strings**
   ```python
   # ❌ MALO - No queryable
   logger.info(f"Product {pid} retrieved")
   
   # ✅ BUENO
   logger.info("product_retrieved", product_id=pid)
   ```

2. **NO loggear datos sensibles**
   ```python
   # ❌ MALO
   logger.info("user_login", password=password)
   
   # ✅ BUENO
   logger.info("user_login", user_id=user_id)
   ```

3. **NO capturar excepciones en métodos privados**
   ```python
   # ❌ MALO
   async def _get_from_source(self):
       try:
           return await self.client.get()
       except Exception as e:
           logger.error("error", ...)  # ← Duplicado!
   
   # ✅ BUENO
   async def _get_from_source(self):
       return await self.client.get()  # Deja que se propague
   ```

4. **NO usar nombres genéricos**
   ```python
   # ❌ MALO
   logger.info("success")
   logger.error("failed")
   
   # ✅ BUENO
   logger.info("cache_warmup_completed")
   logger.error("redis_connection_failed")
   ```

---

## 📚 REFERENCIA RÁPIDA

### **Cheat Sheet de Eventos**

```python
# INITIALIZATION
logger.info(
    "component_initialized",
    config_key=value,
    dependency_status=status
)

# SUCCESSFUL OPERATION
logger.debug(  # o .info si importante
    "component_operation_success",
    operation_type="get",
    result_count=count,
    elapsed_ms=elapsed
)

# FAILED OPERATION (con fallback)
logger.warning(
    "component_operation_failed",
    operation_type="get",
    reason="not_found",
    fallback_used=True
)

# ERROR (sin recovery)
logger.error(
    "component_operation_error",
    operation_type="get",
    error=str(e),
    error_type=type(e).__name__,
    exc_info=True
)

# PERFORMANCE METRIC
logger.info(
    "component_performance_metric",
    operation="warmup",
    total_items=count,
    elapsed_seconds=elapsed,
    items_per_second=throughput
)

# HEALTH CHECK
logger.info(
    "component_health_check",
    status="healthy",
    connections_active=count,
    last_error=None
)
```

---

### **Quick Commands**

```bash
# Ejecutar tests H1
pytest tests/test_h1_structured_logging/ -v

# Ejecutar test específico
pytest tests/test_h1_structured_logging/test_redis_client_logging.py::test_redis_connection_success -v

# Ver logs en formato JSON
pytest tests/test_h1_structured_logging/ -v --log-cli-level=DEBUG

# Coverage de H1
pytest tests/test_h1_structured_logging/ --cov=src/api/core --cov-report=html
```

---

### **Estructura de Archivos H1**

```
retail-recommender-system/
├── src/api/core/
│   ├── redis_client.py          # ✅ Migrado H1
│   ├── product_cache.py         # ✅ Migrado H1
│   └── shopify_kb_client.py     # ✅ Migrado H1
│
├── tests/test_h1_structured_logging/
│   ├── test_redis_client_logging.py        # 35 tests
│   ├── test_product_cache_logging.py       # 23 tests
│   ├── test_shopify_kb_client_logging.py   # 15 tests
│   └── test_debug_monkeypatch.py           #  3 tests
│
└── migrations/
    ├── H1_TEST_RESULTS_VALIDATION.md
    ├── GUIA_TECNICA_STRUCTURED_LOGGING.md   # ← Este archivo
    └── FIX_*.md                              # Documentación de fixes
```

---

## 🎓 RECURSOS ADICIONALES

### **Documentación Oficial**
- [Structlog Docs](https://www.structlog.org/en/stable/)
- [Structlog Best Practices](https://www.structlog.org/en/stable/standard-library.html)

### **Ejemplos en el Proyecto**
- `src/api/core/redis_client.py` - Cliente Redis con logging completo
- `src/api/core/product_cache.py` - Sistema de caché multi-fuente
- `tests/test_h1_structured_logging/` - 68 tests de referencia

### **Contacto**
Para dudas o extensiones de esta guía, consultar:
- Documentación del proyecto en `/migrations`
- Tests de referencia en `test_h1_structured_logging/`

---

**Última Actualización:** 2026-02-08  
**Versión:** 1.0.0  
**Autor:** Sistema Retail Recommender - Equipo de Arquitectura
