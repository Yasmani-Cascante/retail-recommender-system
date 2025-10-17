# 🏗️ FACTORY PATTERN SPRAWL - PARTE 2: PLAN EJECUTABLE

**Fecha:** 15 de Octubre, 2025  
**Arquitecto:** Senior Software Architect + Claude Sonnet 4.5  
**Estado:** ✅ ANÁLISIS COMPLETO - READY FOR IMPLEMENTATION

---

## 📋 RESUMEN EJECUTIVO

### Contexto Parte 1
- ✅ 900 LOC analizadas en `factories.py`
- ✅ 60% duplicación (540/900 LOC)
- ✅ 28 métodos (18 redundantes)
- ✅ Triple implementación: Sync/Async/Enterprise

### Hallazgos Parte 2 - Consumers

**DESCUBRIMIENTO CRÍTICO:** Sistema tiene DOS arquitecturas paralelas:

1. **ServiceFactory (Modern):** Pure async, singletons, DI ✅
2. **Legacy Factories:** Sync/Async variants, 60% duplicación ❌

**Impacto:**
- `main_unified_redis.py` mezcla ambas arquitecturas
- Routers usan global state (NO dependency injection)
- Inconsistencia sync/async
- 60% código nunca usado en producción

---

## 🔍 CONSUMER ANALYSIS SUMMARY

### 1. ServiceFactory (service_factory.py) - ✅ MODERN
- 600 líneas, 100% async
- Thread-safe singletons
- Circuit breaker
- **Problema:** Solo 6/15 componentes

### 2. main_unified_redis.py - ⚠️ HYBRID
```python
# ❌ PROBLEMA: Mixing
tfidf = RecommenderFactory.create_tfidf_recommender()  # SYNC
cache = await ServiceFactory.get_product_cache_singleton()  # ASYNC
```

### 3. Routers - ❌ NO DEPENDENCY INJECTION
```python
# ❌ ACTUAL: Global state
def get_mcp_client():
    from src.api import main_unified_redis
    return main_unified_redis.mcp_recommender.mcp_client

# ✅ DEBERÍA SER: FastAPI DI
@router.get("/endpoint")
async def endpoint(client: MCPClientDep):
    pass
```

---

## 🎯 PROBLEMAS IDENTIFICADOS (PRIORIDAD)

| # | Problema | Severidad | Impacto |
|---|----------|-----------|---------|
| P1 | Inconsistencia Sync/Async | 🔴 CRÍTICO | Blocking I/O, performance |
| P2 | Global State Dependency | 🔴 CRÍTICO | Acoplamiento, testing |
| P3 | ServiceFactory Incompleto | 🟡 ALTO | Duplicación persiste |
| P4 | Fallback Factory Creation | 🟡 MEDIO | Rompe singletons |
| P5 | No FastAPI DI | 🟢 BAJO | Testing difícil |

---

## 🏗️ SOLUCIÓN: ARQUITECTURA TARGET

```
ServiceFactory (Unified Manager)
  ├─ Infrastructure: Redis, Cache, Inventory
  ├─ Recommenders: TF-IDF, Retail, Hybrid
  ├─ MCP: Client, MarketManager, Cache
  └─ AI: Conversation, Personalization
      ↓
dependencies.py (FastAPI DI)
      ↓
Routers (Pure DI, No Global State)
```

---

## 📅 IMPLEMENTACIÓN: 4 FASES (4 SEMANAS)

### FASE 1: Extender ServiceFactory (5 días) ⭐
**Objetivo:** Agregar métodos faltantes

**Cambios en `service_factory.py`:**
```python
class ServiceFactory:
    # NEW singletons
    _tfidf_recommender: Optional[TFIDFRecommender] = None
    _retail_recommender: Optional[RetailRecommender] = None
    _hybrid_recommender: Optional[HybridRecommender] = None
    
    @classmethod
    async def get_tfidf_recommender(cls):
        if cls._tfidf_recommender is None:
            async with cls._get_tfidf_lock():
                # Async load/train
                cls._tfidf_recommender = await cls._create_tfidf()
        return cls._tfidf_recommender
    
    @classmethod
    async def get_hybrid_recommender(cls):
        # Auto-wire ALL dependencies
        tfidf = await cls.get_tfidf_recommender()
        retail = await cls.get_retail_recommender()
        cache = await cls.get_product_cache_singleton()
        return HybridRecommender(tfidf, retail, cache)
```

**Entregable:** 15 métodos (vs 6 actuales)  
**Risk:** BAJO

---

### FASE 2: FastAPI Dependencies (3 días) ⭐
**Objetivo:** Infraestructura DI

**Crear `src/api/dependencies.py`:**
```python
from typing import Annotated
from fastapi import Depends

async def get_hybrid_recommender_dep():
    return await ServiceFactory.get_hybrid_recommender()

async def get_mcp_client_dep():
    return await ServiceFactory.get_mcp_client()

# Type aliases
HybridRecommenderDep = Annotated[HybridRecommender, Depends(get_hybrid_recommender_dep)]
MCPClientDep = Annotated[MCPClient, Depends(get_mcp_client_dep)]
```

**Entregable:** 15 dependency functions  
**Risk:** BAJO

---

### FASE 3: Migrar main (4 días) ⭐⭐
**Objetivo:** Solo ServiceFactory en startup

**ANTES:**
```python
tfidf = RecommenderFactory.create_tfidf_recommender()  # SYNC
hybrid = RecommenderFactory.create_hybrid_recommender(...)
```

**DESPUÉS:**
```python
# ✅ TODO async via ServiceFactory
tfidf = await ServiceFactory.get_tfidf_recommender()
hybrid = await ServiceFactory.get_hybrid_recommender()
```

**Entregable:** -150 LOC, no global vars  
**Risk:** MEDIO - Rollback plan required

---

### FASE 4: Migrar Routers (6 días) ⭐⭐
**Objetivo:** Eliminar global state

**ANTES:**
```python
def get_mcp_client():
    from src.api import main_unified_redis
    return main_unified_redis.mcp_recommender.mcp_client
```

**DESPUÉS:**
```python
from src.api.dependencies import MCPClientDep

@router.get("/endpoint")
async def endpoint(client: MCPClientDep):
    pass
```

**Entregable:** 0 imports de main  
**Risk:** MEDIO - Gradual rollout

---

## 🗑️ CLEANUP FINAL

**Después Fase 4:**
```bash
rm src/api/factories/factories.py  # -900 LOC
```

**Beneficios:**

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| LOC | 1500 | 900 | -40% |
| Duplicación | 60% | 0% | -60% |
| Métodos | 28 | 15 | -46% |
| Variants | 3/método | 1/método | -67% |
| Global vars | 8 | 0 | -100% |

---

## ✅ CHECKLIST IMPLEMENTACIÓN

### Pre-Fase
- [ ] Branch `feature/unified-factory`
- [ ] Backups
- [ ] Test environment

### Fase 1
- [ ] Agregar singletons a ServiceFactory
- [ ] `get_tfidf_recommender()`
- [ ] `get_retail_recommender()`
- [ ] `get_hybrid_recommender()`
- [ ] Unit tests
- [ ] Code review

### Fase 2
- [ ] Crear `dependencies.py`
- [ ] 15 dependency functions
- [ ] Type aliases
- [ ] Tests
- [ ] Documentation

### Fase 3
- [ ] Feature flag `USE_UNIFIED_FACTORY`
- [ ] Rewrite `lifespan()`
- [ ] Remove RecommenderFactory usage
- [ ] Remove global vars
- [ ] Tests startup
- [ ] Rollback plan

### Fase 4
- [ ] Feature flag `USE_DI_ROUTERS`
- [ ] Migrate mcp_router.py
- [ ] Migrate products_router.py
- [ ] E2E tests
- [ ] Remove global imports
- [ ] Gradual rollout

### Cleanup
- [ ] Validate in production (1 week)
- [ ] Delete `factories.py`
- [ ] Update documentation
- [ ] Celebrate 🎉

---

## 🎯 MÉTRICAS DE ÉXITO

| Métrica | Baseline | Target |
|---------|----------|--------|
| Code Duplication | 60% | 0% |
| Factory Methods | 28 | 15 |
| Global Variables | 8 | 0 |
| Startup Time | 8s | <5s |
| Test Coverage | 65% | 85% |

---

## 🚨 RIESGOS Y MITIGACIONES

**Riesgo 1: Breaking Changes**
- Mitigación: Feature flags, gradual rollout, rollback plan

**Riesgo 2: Performance Degradation**
- Mitigación: Benchmarks, profiling, monitoring

**Riesgo 3: Incomplete Migration**
- Mitigación: Checklist, code review, linters, CI/CD

---

## 📚 PRÓXIMOS PASOS

1. **Planning Session** (2h)
   - Review Parte 1 + 2
   - Assign tasks
   - Setup branches

2. **Start Fase 1** (Week 1)
   - Implement new ServiceFactory methods
   - Unit tests
   - Code review

3. **Weekly Reviews**
   - Track progress
   - Adjust plan
   - Celebrate wins

---

## ✅ CONCLUSIÓN

**Ready for Implementation:**
- ✅ Análisis completo
- ✅ 5 problemas críticos identificados
- ✅ Plan 4 fases definido
- ✅ Migration path sin breaking changes
- ✅ Testing strategy

**Beneficios Post-Implementación:**
- 60% reducción duplicación
- 100% async architecture
- 0 global state
- 100% DI compliance
- 85% test coverage

**Timeline:** 4 semanas
**Start Date:** Cuando el equipo esté listo
**Owner:** Senior Architecture Team

---

**FIN PARTE 2**
