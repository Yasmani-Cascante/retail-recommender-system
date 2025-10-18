# 📋 PRODUCTS_ROUTER.PY - CAMBIOS ESPECÍFICOS PARA MIGRACIÓN

**Archivo:** products_router.py  
**Estrategia:** Modificar in-place con edit_file  
**Cambios:** Mínimos y quirúrgicos

---

## 🎯 CAMBIOS A REALIZAR

### **CAMBIO 1: Actualizar Header y Versión** (Líneas 1-10)

```python
# ANTES:
"""
Products Router - Enterprise Architecture + Full Legacy Support
...
Version: 2.1.0 - Enterprise Migration with Full Legacy Support
"""

# DESPUÉS:
"""
Products Router - MIGRATED TO FASTAPI DEPENDENCY INJECTION
...
Version: 3.0.0 - FastAPI DI Migration (Phase 2 Day 3)
Date: 2025-10-17

MIGRATION STATUS: ✅ Phase 2 Day 3 Complete
"""
```

---

### **CAMBIO 2: Reemplazar Imports de Dependencies** (Después línea 24)

```python
# AGREGAR DESPUÉS DE: from src.api.inventory.availability_checker import create_availability_checker

# ============================================================================
# FASTAPI DEPENDENCY INJECTION - NEW PATTERN (Phase 2 Day 3)
# ============================================================================

from src.api.dependencies import (
    get_inventory_service,
    get_product_cache,
    get_availability_checker
)
```

---

### **CAMBIO 3: Comentar Funciones Enterprise Locales** (Líneas ~109-149)

```python
# COMENTAR ESTAS FUNCIONES (mantener para referencia):

"""
❌ OLD PATTERN - Local dependency functions (DEPRECATED)
# async def get_enterprise_inventory_service():
# async def get_enterprise_product_cache():
# async def get_enterprise_availability_checker():
"""
```

---

### **CAMBIO 4: Migrar products_health_check()** (Línea ~250)

```python
# ANTES:
@router.get("/products/health")
async def products_health_check():
    redis_service = await get_redis_service()
    inventory_service = await get_enterprise_inventory_service()
    cache = await get_enterprise_product_cache()

# DESPUÉS:
@router.get("/products/health")
async def products_health_check(
    redis_service: RedisService = Depends(get_redis_service),
    inventory: InventoryService = Depends(get_inventory_service),
    cache: ProductCache = Depends(get_product_cache)
):
    """
    MIGRATED: ✅ Using FastAPI Dependency Injection (Phase 2 Day 3)
    """
```

---

### **CAMBIO 5: Migrar get_products()** (Línea ~320)

```python
# ANTES:
async def get_products(
    limit: int = ...,
    ...
    api_key: str = Depends(get_api_key)
):
    ...
    inventory_service = await get_enterprise_inventory_service()

# DESPUÉS:
async def get_products(
    limit: int = ...,
    ...
    api_key: str = Depends(get_api_key),
    # ✅ NEW: FastAPI Dependency Injection
    inventory: InventoryService = Depends(get_inventory_service)
):
    """
    MIGRATED: ✅ Using FastAPI Dependency Injection (Phase 2 Day 3)
    """
    # Reemplazar: inventory_service → inventory
```

---

### **CAMBIO 6: Migrar get_product()** (Línea ~420)

```python
# ANTES:
async def get_product(
    product_id: str,
    ...
    api_key: str = Depends(get_api_key)
):
    cache = await get_enterprise_product_cache()
    inventory_service = await get_enterprise_inventory_service()

# DESPUÉS:
async def get_product(
    product_id: str,
    ...
    api_key: str = Depends(get_api_key),
    # ✅ NEW: FastAPI Dependency Injection
    cache: ProductCache = Depends(get_product_cache),
    inventory: InventoryService = Depends(get_inventory_service)
):
    """
    MIGRATED: ✅ Using FastAPI Dependency Injection (Phase 2 Day 3)
    """
    # Variables ya están inyectadas, no necesitan await get_enterprise_*()
```

---

## 📝 RESUMEN DE CAMBIOS

| Sección | Tipo de Cambio | Líneas Afectadas |
|---------|----------------|------------------|
| Header | Documentación | ~10 |
| Imports | Agregar | ~5 |
| Local Functions | Comentar | ~40 |
| health_check | Migrar endpoint | ~30 |
| get_products | Migrar endpoint | ~20 |
| get_product | Migrar endpoint | ~20 |

**Total:** ~125 líneas modificadas de ~1600 líneas (8%)

---

## ✅ ESTRATEGIA DE APLICACIÓN

Dado que el archivo es muy grande y el write_file se cortó, voy a:

1. **Usar múltiples `edit_file` calls** - Cambios quirúrgicos precisos
2. **Un cambio a la vez** - Validar cada modificación
3. **Mantener funcionalidad** - Zero breaking changes
4. **Backup primero** - Crear backup del original

**Ventajas:**
- ✅ No reescribe todo el archivo
- ✅ Cambios precisos y verificables
- ✅ Menos riesgo de errores
- ✅ Más rápido que reescribir 1600 líneas

---

## 🚀 PRÓXIMO PASO

Aplicar cambios con `edit_file` uno por uno, empezando por el header.
