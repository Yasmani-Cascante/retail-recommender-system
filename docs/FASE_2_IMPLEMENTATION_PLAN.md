# 🎯 FASE 2: FASTAPI DEPENDENCY INJECTION - PLAN DETALLADO

**Fecha:** 16 de Octubre, 2025  
**Duración:** 3-4 días  
**Prerequisito:** ✅ Fase 1 completada

---

## 📊 ANÁLISIS DEL ESTADO ACTUAL

### **Problema Identificado:** ❌ ANTI-PATTERN

```python
# En routers/recommendations.py (línea 3):
from src.api.core.recommenders import hybrid_recommender, content_recommender, retail_recommender

# En el endpoint:
recommendations = await hybrid_recommender.get_recommendations(...)
```

**Issues:**
1. ❌ **Imports globales** - Componentes como variables globales
2. ❌ **No dependency injection** - Acoplamiento fuerte
3. ❌ **Testing difícil** - No se pueden mockear fácilmente
4. ❌ **No lifecycle management** - No control de instancias
5. ❌ **No FastAPI DI** - No aprovecha el sistema moderno de FastAPI

---

## 🎯 OBJETIVO DE FASE 2

### **Transformación:**

**ANTES (Anti-pattern):**
```python
# Router
from src.api.core.recommenders import hybrid_recommender

@router.get("/recommendations/{product_id}")
async def get_recommendations(product_id: str):
    # Usa variable global importada
    return await hybrid_recommender.get_recommendations(product_id)
```

**DESPUÉS (FastAPI DI Pattern):**
```python
# dependencies.py
async def get_hybrid_recommender() -> HybridRecommender:
    return await ServiceFactory.get_hybrid_recommender()

# Router
from fastapi import Depends
from src.api.dependencies import get_hybrid_recommender

@router.get("/recommendations/{product_id}")
async def get_recommendations(
    product_id: str,
    hybrid: HybridRecommender = Depends(get_hybrid_recommender)
):
    # Usa dependencia inyectada
    return await hybrid.get_recommendations(product_id)
```

**Beneficios:**
- ✅ **Testeable** - Fácil mockear con override_dependency
- ✅ **Desacoplado** - No imports directos de componentes
- ✅ **Lifecycle** - FastAPI maneja el ciclo de vida
- ✅ **Moderno** - Sigue best practices de FastAPI
- ✅ **Type-safe** - Type hints claros

---

## 📋 SCOPE DE FASE 2

### **QUÉ VAMOS A HACER:**

1. ✅ **Crear `dependencies.py`**
   - Dependency providers para todos los componentes
   - Type hints con Annotated
   - Documentation clara

2. ✅ **Migrar 2 routers (Proof of Concept)**
   - `recommendations.py` - Router principal
   - `products_router.py` - Router secundario
   - Validar el pattern funciona

3. ✅ **Tests de integración**
   - Test dependency override
   - Test que routers funcionan con DI
   - Performance tests

4. ✅ **Documentation**
   - Migration guide
   - Examples de uso
   - Best practices

### **QUÉ NO VAMOS A HACER (Fase 3):**

- ❌ Migrar main_unified_redis.py
- ❌ Eliminar variables globales
- ❌ Migrar todos los routers
- ❌ Breaking changes

---

## 🏗️ ARQUITECTURA DE DEPENDENCIES.PY

### **Estructura:**

```python
"""
FastAPI Dependency Injection Providers
======================================

Enterprise dependency injection para componentes del sistema.

Author: Senior Architecture Team
Date: 2025-10-16
Version: 1.0.0 - Fase 2 Implementation
"""

from typing import Annotated
from fastapi import Depends
from src.api.factories.service_factory import ServiceFactory

# ============================================================================
# Type Aliases - Modern FastAPI Pattern
# ============================================================================

# Recommenders
TFIDFRecommenderDep = Annotated[
    'TFIDFRecommender',
    Depends(lambda: ServiceFactory.get_tfidf_recommender())
]

RetailRecommenderDep = Annotated[
    'RetailAPIRecommender', 
    Depends(lambda: ServiceFactory.get_retail_recommender())
]

HybridRecommenderDep = Annotated[
    'HybridRecommender',
    Depends(lambda: ServiceFactory.get_hybrid_recommender())
]

# Infrastructure
ProductCacheDep = Annotated[
    'ProductCache',
    Depends(lambda: ServiceFactory.get_product_cache_singleton())
]

RedisServiceDep = Annotated[
    'RedisService',
    Depends(lambda: ServiceFactory.get_redis_service())
]

# ============================================================================
# Dependency Providers - Explicit Functions
# ============================================================================

async def get_tfidf_recommender():
    """Get TF-IDF recommender singleton via ServiceFactory"""
    return await ServiceFactory.get_tfidf_recommender()

async def get_retail_recommender():
    """Get Retail API recommender singleton via ServiceFactory"""
    return await ServiceFactory.get_retail_recommender()

async def get_hybrid_recommender():
    """Get Hybrid recommender singleton with auto-wiring"""
    return await ServiceFactory.get_hybrid_recommender()

async def get_product_cache():
    """Get ProductCache singleton"""
    return await ServiceFactory.get_product_cache_singleton()

async def get_redis_service():
    """Get RedisService singleton"""
    return await ServiceFactory.get_redis_service()

# ============================================================================
# Composite Dependencies - For complex scenarios
# ============================================================================

async def get_recommendation_context():
    """
    Get full recommendation context with all dependencies.
    
    Returns dict with tfidf, retail, hybrid, and cache.
    Useful for endpoints that need multiple recommenders.
    """
    return {
        "tfidf": await get_tfidf_recommender(),
        "retail": await get_retail_recommender(),
        "hybrid": await get_hybrid_recommender(),
        "cache": await get_product_cache()
    }
```

---

## 📅 TIMELINE - 3-4 DÍAS

### **DÍA 1: Crear dependencies.py** 🔧

#### **Morning (4 horas):**
```
09:00-10:00: Design dependencies.py structure
- Type aliases con Annotated
- Explicit dependency functions
- Composite dependencies

10:00-12:00: Implement dependencies.py
- All dependency providers
- Type hints completos
- Documentation strings

12:00-13:00: Unit tests
- Test cada dependency provider
- Test type hints
- Test ServiceFactory integration
```

#### **Afternoon (4 horas):**
```
14:00-16:00: Integration tests
- Test dependency override
- Test con FastAPI TestClient
- Mock scenarios

16:00-18:00: Documentation
- Usage examples
- Migration guide draft
- Best practices

Deliverable: dependencies.py + tests
```

---

### **DÍA 2: Migrar recommendations.py** 🔧

#### **Morning (4 horas):**
```
09:00-10:00: Analysis
- Review recommendations.py
- Identify all component usage
- Plan migration strategy

10:00-12:00: Implementation
- Replace global imports with Depends()
- Update all endpoints
- Maintain backward compatibility

12:00-13:00: Testing
- Test cada endpoint
- Verify same behavior
- Performance validation
```

#### **Afternoon (4 horas):**
```
14:00-16:00: Refinement
- Code review self-review
- Optimize type hints
- Clean up imports

16:00-18:00: Integration testing
- Full router test suite
- Edge cases
- Error handling

Deliverable: recommendations.py migrado + tests
```

---

### **DÍA 3: Migrar products_router.py** 🔧

#### **Morning (4 horas):**
```
09:00-10:00: Analysis
- Review products_router.py
- Identify dependencies
- Plan migration

10:00-12:00: Implementation
- Migrate to Depends()
- Update endpoints
- Type hints

12:00-13:00: Testing
- Router tests
- Integration tests
```

#### **Afternoon (4 horas):**
```
14:00-17:00: Validation completa
- Test ambos routers juntos
- Performance comparison
- Regression testing

17:00-18:00: Documentation update
- Complete migration guide
- Examples
- Troubleshooting guide

Deliverable: products_router.py migrado + docs
```

---

### **DÍA 4: Polish & Documentation** 📝

#### **Morning (4 horas):**
```
09:00-11:00: Code cleanup
- Remove deprecated code
- Optimize imports
- Consistent style

11:00-13:00: Comprehensive testing
- Full test suite
- Performance benchmarks
- Load testing
```

#### **Afternoon (4 horas):**
```
14:00-16:00: Documentation final
- Complete migration guide
- API documentation update
- Examples y patterns

16:00-17:00: Demo preparation
- Working examples
- Before/after comparison
- Performance metrics

17:00-18:00: Fase 2 completion report
- Summary document
- Metrics comparison
- Next steps (Fase 3)

Deliverable: Complete Fase 2 package
```

---

## 🧪 TESTING STRATEGY

### **Unit Tests:**
```python
# test_dependencies.py

import pytest
from fastapi.testclient import TestClient
from src.api.dependencies import *

@pytest.mark.asyncio
async def test_get_tfidf_recommender():
    """Test TF-IDF dependency provider"""
    recommender = await get_tfidf_recommender()
    assert recommender is not None
    assert type(recommender).__name__ == 'TFIDFRecommender'

@pytest.mark.asyncio  
async def test_dependency_singleton():
    """Test that dependencies return singletons"""
    r1 = await get_tfidf_recommender()
    r2 = await get_tfidf_recommender()
    assert r1 is r2  # Same instance

@pytest.mark.asyncio
async def test_get_hybrid_with_autowiring():
    """Test hybrid dependency with auto-wiring"""
    hybrid = await get_hybrid_recommender()
    assert hybrid.content_recommender is not None
    assert hybrid.retail_recommender is not None
```

### **Integration Tests:**
```python
# test_router_with_di.py

def test_recommendations_endpoint_with_di():
    """Test recommendations endpoint uses DI correctly"""
    client = TestClient(app)
    
    response = client.get("/recommendations/123")
    assert response.status_code == 200
    assert "recommendations" in response.json()

def test_dependency_override():
    """Test we can override dependencies for testing"""
    mock_recommender = MockRecommender()
    
    app.dependency_overrides[get_hybrid_recommender] = lambda: mock_recommender
    
    client = TestClient(app)
    response = client.get("/recommendations/123")
    
    assert response.status_code == 200
    # Verify mock was used
```

---

## 📊 EXAMPLE: ANTES vs DESPUÉS

### **ANTES (recommendations.py):**

```python
# ❌ ANTI-PATTERN: Global imports
from src.api.core.recommenders import hybrid_recommender, content_recommender

@router.get("/recommendations/{product_id}")
async def get_recommendations(
    product_id: str,
    n: int = Query(5)
):
    # ❌ Usa variable global
    recommendations = await hybrid_recommender.get_recommendations(
        product_id=product_id,
        n_recommendations=n
    )
    return {"recommendations": recommendations}
```

**Issues:**
- ❌ No type hints en parámetros de componentes
- ❌ Testing require patches complejos
- ❌ No lifecycle management
- ❌ Acoplamiento fuerte

---

### **DESPUÉS (recommendations.py con DI):**

```python
# ✅ FASTAPI DI PATTERN
from fastapi import Depends
from src.api.dependencies import get_hybrid_recommender
from src.api.core.hybrid_recommender import HybridRecommender

@router.get("/recommendations/{product_id}")
async def get_recommendations(
    product_id: str,
    n: int = Query(5),
    # ✅ Dependency injection
    hybrid: HybridRecommender = Depends(get_hybrid_recommender)
):
    # ✅ Usa dependencia inyectada
    recommendations = await hybrid.get_recommendations(
        product_id=product_id,
        n_recommendations=n
    )
    return {"recommendations": recommendations}
```

**Benefits:**
- ✅ Type hints claros (HybridRecommender)
- ✅ Easy testing (app.dependency_overrides)
- ✅ FastAPI maneja lifecycle
- ✅ Desacoplado, testeable, mantenible

---

### **Testing con DI:**

```python
# test_recommendations_new.py

def test_recommendations_with_mock():
    """Easy mocking with dependency override"""
    
    # Create mock
    mock_hybrid = MockHybridRecommender()
    mock_hybrid.get_recommendations = AsyncMock(
        return_value=[{"id": "1", "score": 0.9}]
    )
    
    # Override dependency
    app.dependency_overrides[get_hybrid_recommender] = lambda: mock_hybrid
    
    # Test
    client = TestClient(app)
    response = client.get("/recommendations/123?n=5")
    
    # Verify
    assert response.status_code == 200
    assert len(response.json()["recommendations"]) == 1
    mock_hybrid.get_recommendations.assert_called_once()
    
    # Cleanup
    app.dependency_overrides.clear()
```

**Antes** esto requería:
- Monkey patching de módulos
- Mock complejos de imports
- Código frágil

**Ahora** es:
- Simple override
- Clean y claro
- Fácil de mantener

---

## ✅ CRITERIOS DE ACEPTACIÓN

### **Must Have:**

#### **dependencies.py:**
- [ ] Todos los dependency providers implementados
- [ ] Type hints con Annotated
- [ ] Documentation strings completas
- [ ] Integration con ServiceFactory
- [ ] Unit tests passing

#### **Router Migration:**
- [ ] recommendations.py migrado completamente
- [ ] products_router.py migrado completamente
- [ ] Zero breaking changes
- [ ] All endpoints funcionando
- [ ] Type hints correctos

#### **Testing:**
- [ ] Unit tests para dependencies (10+ tests)
- [ ] Integration tests para routers (10+ tests)
- [ ] Dependency override tests (5+ tests)
- [ ] Performance tests (igual o mejor)

#### **Documentation:**
- [ ] Migration guide completo
- [ ] Usage examples
- [ ] Before/after comparison
- [ ] Troubleshooting guide

### **Should Have:**
- [ ] Performance igual o mejor que antes
- [ ] Code review approval
- [ ] CI/CD green
- [ ] All tests >95% coverage

### **Nice to Have:**
- [ ] Automated migration script
- [ ] Additional router migrations
- [ ] Performance improvements

---

## 🎯 BENEFICIOS ESPERADOS

### **Para Developers:**
```python
# Antes: Confuso, acoplado
from src.api.core.recommenders import hybrid_recommender
recommendations = await hybrid_recommender.get_recommendations(...)

# Después: Claro, desacoplado
async def endpoint(hybrid: HybridRecommender = Depends(get_hybrid_recommender)):
    recommendations = await hybrid.get_recommendations(...)
```

### **Para Testing:**
```python
# Antes: Difícil
with patch('src.api.core.recommenders.hybrid_recommender'):
    # Complex mocking

# Después: Fácil
app.dependency_overrides[get_hybrid_recommender] = lambda: mock
```

### **Para Arquitectura:**
- ✅ Separation of concerns
- ✅ Inversion of control
- ✅ Dependency inversion principle
- ✅ Modern FastAPI patterns

---

## 🚨 RIESGOS Y MITIGACIONES

### **Riesgo 1: Breaking changes accidentales** 🟡 MEDIO
**Mitigación:**
- Comprehensive test suite antes de migrar
- Regression testing después de cada cambio
- Rollback plan ready

### **Riesgo 2: Performance degradation** 🟢 BAJO
**Mitigación:**
- FastAPI DI es muy eficiente
- Singletons ya implementados (Fase 1)
- Performance tests en cada cambio

### **Riesgo 3: Learning curve del equipo** 🟢 BAJO
**Mitigación:**
- Documentation clara con examples
- Pair programming sessions
- Code review detallado

---

## 📦 ENTREGABLES FASE 2

### **Código:**
1. ✅ `src/api/dependencies.py` (nuevo)
2. ✅ `src/api/routers/recommendations.py` (modificado)
3. ✅ `src/api/routers/products_router.py` (modificado)

### **Tests:**
1. ✅ `tests/test_dependencies.py` (nuevo)
2. ✅ `tests/test_recommendations_di.py` (nuevo)
3. ✅ `tests/test_products_router_di.py` (nuevo)

### **Documentation:**
1. ✅ `FASE_2_IMPLEMENTATION_PLAN.md` (este documento)
2. ✅ `FASE_2_MIGRATION_GUIDE.md`
3. ✅ `FASE_2_COMPLETION_REPORT.md`

---

## 🎓 PATRONES A SEGUIR

### **1. Annotated Type Aliases (Modern Pattern):**
```python
from typing import Annotated
from fastapi import Depends

HybridDep = Annotated[HybridRecommender, Depends(get_hybrid_recommender)]

# Usage in endpoint:
async def endpoint(hybrid: HybridDep):
    ...
```

### **2. Explicit Dependency Functions:**
```python
async def get_hybrid_recommender() -> HybridRecommender:
    """Explicit, documented, type-safe"""
    return await ServiceFactory.get_hybrid_recommender()
```

### **3. Composite Dependencies:**
```python
async def get_recommendation_context():
    """Bundle multiple dependencies"""
    return {
        "tfidf": await get_tfidf_recommender(),
        "retail": await get_retail_recommender(),
        "hybrid": await get_hybrid_recommender()
    }
```

---

## 🏁 CONCLUSIÓN FASE 2

**Objetivo:** Implementar FastAPI Dependency Injection moderna

**Scope:** 
- ✅ Crear dependencies.py
- ✅ Migrar 2 routers (proof of concept)
- ✅ Comprehensive testing
- ✅ Documentation completa

**Timeline:** 3-4 días

**Riesgo:** 🟢 BAJO (singletons ya funcionan desde Fase 1)

**Value:** 🟢 ALTO (testability, maintainability, modern patterns)

**Ready to begin:** SÍ ✅

---

**Next:** ¿Comenzamos con Día 1 - Crear dependencies.py? 🚀

**Autor:** Senior Architecture Team  
**Fecha:** 16 de Octubre, 2025  
**Status:** 📋 PLANNING COMPLETE - READY FOR IMPLEMENTATION
