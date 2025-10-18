# 📋 FASE 2 DÍA 3 - PLAN DE MIGRACIÓN

**Fecha:** 17 de Octubre, 2025  
**Archivo Objetivo:** products_router.py  
**Complejidad:** MEDIA  
**Tiempo Estimado:** 2-3 horas

---

## 🔍 HALLAZGOS DEL ANÁLISIS

### **Estado Actual:**

**products_router.py ya tiene dependency functions locales:**
```python
# Definidas EN EL ROUTER (líneas 109-149):
async def get_enterprise_inventory_service()
async def get_enterprise_product_cache()
async def get_enterprise_availability_checker()
```

**Problema:**
- ❌ Funciones duplicadas (también existen en dependencies.py)
- ❌ No sigue el pattern del Día 2 (recommendations.py)
- ❌ Endpoints NO usan `Depends()` en firma
- ❌ Llaman funciones directamente dentro del cuerpo

**Ejemplo actual:**
```python
@router.get("/products/health")
async def products_health_check():
    # ❌ Llamada directa, sin Depends()
    inventory_service = await get_enterprise_inventory_service()
```

---

## 🎯 OBJETIVO DE LA MIGRACIÓN

**Transformar de:**
```python
# ❌ ANTI-PATTERN: Función local + llamada directa
async def get_enterprise_inventory_service():
    return await ServiceFactory.get_inventory_service_singleton()

@router.get("/products/health")
async def products_health_check():
    inventory = await get_enterprise_inventory_service()
```

**A:**
```python
# ✅ FASTAPI DI PATTERN: Import + Depends()
from src.api.dependencies import get_inventory_service
from src.api.inventory.inventory_service import InventoryService

@router.get("/products/health")
async def products_health_check(
    inventory: InventoryService = Depends(get_inventory_service)
):
    # inventory ya está inyectado!
```

---

## 📊 ANÁLISIS COMPARATIVO

### **Antes de Migración:**
| Aspecto | Status | Problema |
|---------|--------|----------|
| Dependency Functions | ❌ Locales | Duplicación de código |
| Endpoint Signatures | ❌ Sin Depends() | No testeable |
| Type Hints | 🟡 Parciales | Inconsistente |
| Consistency | ❌ No | Diferente de recommendations.py |
| Code Location | ❌ En router | Debe estar en dependencies.py |

### **Después de Migración:**
| Aspecto | Status | Beneficio |
|---------|--------|-----------|
| Dependency Functions | ✅ Centralizadas | Single source of truth |
| Endpoint Signatures | ✅ Con Depends() | Testeable con override |
| Type Hints | ✅ Completos | Type safety |
| Consistency | ✅ Sí | Mismo pattern que Día 2 |
| Code Location | ✅ dependencies.py | Mejor organización |

---

## 🛠️ PASOS DE IMPLEMENTACIÓN

### **PASO 1: Actualizar dependencies.py** (15 min)

**Agregar función faltante:**
```python
async def get_availability_checker():
    """
    Get AvailabilityChecker instance.
    
    Integra InventoryService para verificar disponibilidad de productos.
    """
    try:
        inventory = await get_inventory_service()
        from src.api.inventory.availability_checker import create_availability_checker
        checker = create_availability_checker(inventory)
        logger.debug("AvailabilityChecker dependency injected")
        return checker
    except Exception as e:
        logger.error(f"Failed to get AvailabilityChecker: {e}")
        raise
```

**Agregar type alias:**
```python
AvailabilityCheckerDep = Annotated[
    'AvailabilityChecker',
    Depends(get_availability_checker)
]
```

---

### **PASO 2: Crear products_router_migrated.py** (1.5-2 horas)

**2.1 Actualizar Imports:**
```python
# ============================================================================
# FASTAPI DEPENDENCY INJECTION - NEW PATTERN (Phase 2 Day 3)
# ============================================================================

from src.api.dependencies import (
    get_inventory_service,
    get_product_cache,
    get_availability_checker
)

# Type hints for better IDE support
from src.api.inventory.inventory_service import InventoryService
from src.api.core.product_cache import ProductCache
from src.api.inventory.availability_checker import AvailabilityChecker

# ============================================================================
# LEGACY FUNCTIONS - DEPRECATED (can be removed after validation)
# ============================================================================

# ❌ OLD PATTERN: Local dependency functions (DEPRECATED)
# async def get_enterprise_inventory_service(): ...
# async def get_enterprise_product_cache(): ...
# async def get_enterprise_availability_checker(): ...
```

**2.2 Migrar Endpoints:**

**Endpoints a migrar (3 principales):**

1. **`products_health_check()`:**
```python
# BEFORE:
@router.get("/products/health")
async def products_health_check():
    inventory_service = await get_enterprise_inventory_service()

# AFTER:
@router.get("/products/health")
async def products_health_check(
    inventory: InventoryService = Depends(get_inventory_service),
    cache: ProductCache = Depends(get_product_cache)
):
    # Use injected dependencies
```

2. **`get_products()`:**
```python
# BEFORE:
async def get_products(...):
    inventory_service = await get_enterprise_inventory_service()
    availability_checker = get_enterprise_availability_checker()

# AFTER:
async def get_products(
    ...,
    inventory: InventoryService = Depends(get_inventory_service),
    availability_checker: AvailabilityChecker = Depends(get_availability_checker)
):
    # Use injected dependencies
```

3. **`get_product()`:**
```python
# BEFORE:
async def get_product(...):
    cache = await get_enterprise_product_cache()
    inventory_service = await get_enterprise_inventory_service()

# AFTER:
async def get_product(
    ...,
    cache: ProductCache = Depends(get_product_cache),
    inventory: InventoryService = Depends(get_inventory_service)
):
    # Use injected dependencies
```

**Endpoints SIN cambios (no usan dependencies):**
- `_get_shopify_products()` - Helper function
- `_get_sample_products()` - Helper function
- Etc.

---

### **PASO 3: Aplicar Migración con Safety** (15 min)

**3.1 Crear script de migración:**
```python
# scripts/migrate_products_router.py
```

**3.2 Ejecutar migración:**
```bash
python scripts/migrate_products_router.py

# Expected output:
# ✅ Backup created: products_router_original_backup_TIMESTAMP.py
# ✅ Migration applied: products_router.py updated
# ✅ Verification passed
```

---

### **PASO 4: Testing Manual** (45 min)

**4.1 Start server:**
```bash
python -m uvicorn src.api.main_unified_redis:app --reload
```

**4.2 Test endpoints:**
```bash
# Test 1: Health check
curl http://localhost:8000/v1/products/health

# Test 2: List products
curl "http://localhost:8000/v1/products/?limit=10&market_id=US"

# Test 3: Individual product
curl "http://localhost:8000/v1/products/123?market_id=US&include_inventory=true"

# Test 4: With availability filter
curl "http://localhost:8000/v1/products/?available_only=true"
```

**Expected:** Todas 200 OK, mismas respuestas que antes

---

## 📈 MÉTRICAS DE ÉXITO

### **Criterios de Aceptación:**

| Criterio | Target | Validación |
|----------|--------|------------|
| Migración exitosa | ✅ | Script completa sin errores |
| Backup creado | ✅ | Archivo backup existe |
| Servidor arranca | ✅ | No import/startup errors |
| Endpoint health | ✅ | 200 OK |
| Endpoint get_products | ✅ | 200 OK, same response |
| Endpoint get_product | ✅ | 200 OK, same response |
| Zero breaking changes | ✅ | All tests pass |
| Performance mantenido | ✅ | Response times similar |
| DI working | ✅ | Dependencies inyectadas |
| Type hints | ✅ | IDE autocomplete funciona |

---

## 🎓 OPORTUNIDADES DE APRENDIZAJE

### **1. Refactoring Pattern Recognition**

**Qué aprenderás:**
- Identificar código duplicado en sistemas grandes
- Reconocer anti-patterns (funciones locales cuando deberían ser centralizadas)
- Decidir qué código mover vs eliminar vs mantener

**Ejemplo práctico:**
```python
# ❌ ANTI-PATTERN: Duplicación
# En products_router.py:
async def get_enterprise_inventory_service():
    return await ServiceFactory.get_inventory_service_singleton()

# En dependencies.py:
async def get_inventory_service():
    return await ServiceFactory.get_inventory_service_singleton()

# ✅ SOLUCIÓN: Una sola implementación en dependencies.py
# Router solo importa y usa
```

---

### **2. FastAPI Dependency Injection Deep Dive**

**Qué aprenderás:**
- Por qué `Depends()` en la firma es mejor que llamadas directas
- Cómo FastAPI cachea dependencies dentro de un request
- Testing con dependency override

**Comparación:**
```python
# ❌ LLAMADA DIRECTA (no testeable):
async def endpoint():
    service = await get_service()  # Hard to mock

# ✅ DEPENDENCY INJECTION (testeable):
async def endpoint(service = Depends(get_service)):
    # FastAPI inyecta, fácil override en tests
    pass

# En tests:
app.dependency_overrides[get_service] = lambda: MockService()
```

---

### **3. Code Organization Principles**

**Qué aprenderás:**
- **Single Responsibility Principle:** Un archivo, un propósito
- **DRY (Don't Repeat Yourself):** Eliminar duplicación
- **Separation of Concerns:** Router != Dependency Provider

**Arquitectura:**
```
src/api/
├── dependencies.py    ← Dependency providers (Single Source of Truth)
├── routers/
│   ├── products_router.py    ← Business logic only
│   └── recommendations.py     ← Business logic only
└── factories/
    └── service_factory.py     ← Singleton creation
```

---

### **4. Safe Refactoring Strategy**

**Qué aprenderás:**
- Crear backup automático antes de cambios
- Validar cambios antes de commit
- Rollback strategy si algo falla

**Process:**
```
1. Analyze → Understand current code
2. Plan → Document changes
3. Backup → Automatic timestamped copy
4. Migrate → Apply changes
5. Validate → Test all endpoints
6. Rollback if needed → Copy backup back
7. Commit → Save working version
```

---

### **5. Type Safety Benefits**

**Qué aprenderás:**
- Cómo type hints mejoran developer experience
- IDE autocomplete con type hints
- Catch errors before runtime

**Ejemplo:**
```python
# ❌ Sin type hints:
async def endpoint(inventory):
    result = inventory.check()  # ¿Qué métodos tiene inventory?

# ✅ Con type hints:
async def endpoint(inventory: InventoryService):
    result = inventory.check()  # IDE muestra todos los métodos!
    #              ^
    #              IDE autocomplete: check_availability(), 
    #                                get_stock_level(), etc.
```

---

## 📝 CHECKLIST DE PROGRESO

### **Pre-Migración:**
- [ ] Analizar products_router.py completo
- [ ] Identificar endpoints que usan dependencies
- [ ] Verificar dependencies.py tiene todas las funciones
- [ ] Crear plan de migración detallado

### **Implementación:**
- [ ] Actualizar dependencies.py (agregar get_availability_checker)
- [ ] Crear products_router_migrated.py
- [ ] Migrar endpoints principales (3)
- [ ] Actualizar imports
- [ ] Agregar type hints
- [ ] Eliminar funciones duplicadas
- [ ] Actualizar documentation

### **Migración:**
- [ ] Crear script de migración
- [ ] Ejecutar backup automático
- [ ] Aplicar migración
- [ ] Verificar archivos copiados

### **Validation:**
- [ ] Start server sin errores
- [ ] Test endpoint health
- [ ] Test endpoint get_products
- [ ] Test endpoint get_product
- [ ] Test otros endpoints
- [ ] Verificar logs por warnings
- [ ] Comparar performance

### **Post-Migración:**
- [ ] Documentar cambios
- [ ] Crear comparison antes/después
- [ ] Commit código
- [ ] Celebrar éxito! 🎉

---

## 🚀 READY TO START

**Estado:** ✅ Plan completo y validado  
**Próximo paso:** Actualizar dependencies.py  
**Confianza:** ALTA - Pattern ya probado en Día 2

---

**Preparado por:** Senior Architecture Mentor  
**Para:** Developer Learning Journey  
**Objetivo:** No solo migrar, sino **enseñar arquitectura moderna**
