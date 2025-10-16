# 🚀 FASE 1: PLAN DE IMPLEMENTACIÓN EJECUTABLE (CONTINUACIÓN)

**Fecha Inicio:** 15 de Octubre, 2025  
**Duración:** 5 días laborables  
**Objetivo:** Extend ServiceFactory sin breaking changes

---

## 📅 TIMELINE DETALLADO - 5 DÍAS (CONTINUACIÓN)

### **DÍA 4: Testing Integrado + Performance** 🧪 (CONTINUACIÓN)

#### **Afternoon (4 horas):** (CONTINUACIÓN)
```
14:00-16:00: Edge Cases & Error Handling
- [ ] Test with Redis down
- [ ] Test with Shopify unavailable
- [ ] Test with Google Cloud issues
- [ ] Test concurrent access (multiple threads)
- [ ] Test race conditions (async locks)

16:00-18:00: Regression Testing
- [ ] Run ALL existing tests
- [ ] Verify legacy factories still work
- [ ] Test all routers still functional
- [ ] Test MCP integration
- [ ] Check health endpoints
```

**Entregable Día 4:**
- ✅ All integration tests passing
- ✅ Performance equal or better than baseline
- ✅ No regressions detected
- ✅ Edge cases handled

---

### **DÍA 5: Documentation + Code Review Prep** 📝

#### **Morning (4 horas):**
```
09:00-11:00: Code Cleanup
- [ ] Remove debug logs
- [ ] Optimize imports
- [ ] Consistent naming conventions
- [ ] Add type hints everywhere
- [ ] Format with black/autopep8

11:00-13:00: Documentation
- [ ] Update CURRENT_ARCHITECTURE.md
- [ ] Create FASE_1_COMPLETION_REPORT.md
- [ ] Update inline docstrings
- [ ] Create migration guide (for future phases)
- [ ] Update README if needed
```

#### **Afternoon (4 horas):**
```
14:00-16:00: Final Validation
- [ ] Full system test (3 cold starts)
- [ ] Capture new metrics
- [ ] Compare with baseline
- [ ] Verify all acceptance criteria
- [ ] Screenshot logs for evidence

16:00-17:30: Code Review Preparation
- [ ] Self-review checklist
- [ ] Prepare PR description
- [ ] List all changes
- [ ] Document testing done
- [ ] Create demo script

17:30-18:00: PR Creation
- [ ] Create Pull Request
- [ ] Add reviewers
- [ ] Link to documentation
- [ ] Add testing evidence
```

**Entregable Día 5:**
- ✅ Code cleanup complete
- ✅ Documentation updated
- ✅ PR created and ready for review
- ✅ Evidence of testing
- ✅ Metrics comparison document

---

## 📝 CHECKLIST COMPLETO - IMPLEMENTACIÓN

### **Pre-Implementation:**
- [ ] Baseline metrics captured (✅ DONE)
- [ ] Branch created
- [ ] Backup files created
- [ ] Team notified

### **Implementation (Días 1-3):**

#### **service_factory.py Changes:**
- [ ] Import TYPE_CHECKING added
- [ ] Import TFIDFRecommender (type hint)
- [ ] Import RetailAPIRecommender (type hint)
- [ ] Import HybridRecommender (type hint)
- [ ] Class variable: `_tfidf_recommender`
- [ ] Class variable: `_tfidf_lock`
- [ ] Method: `_get_tfidf_lock()`
- [ ] Method: `get_tfidf_recommender(auto_load=False)`
- [ ] Class variable: `_retail_recommender`
- [ ] Class variable: `_retail_lock`
- [ ] Method: `_get_retail_lock()`
- [ ] Method: `get_retail_recommender()`
- [ ] Class variable: `_hybrid_recommender`
- [ ] Class variable: `_hybrid_lock`
- [ ] Method: `_get_hybrid_lock()`
- [ ] Method: `get_hybrid_recommender()`

#### **Testing:**
- [ ] Unit test: `test_tfidf_singleton()`
- [ ] Unit test: `test_tfidf_auto_load_true()`
- [ ] Unit test: `test_tfidf_auto_load_false()`
- [ ] Unit test: `test_retail_singleton()`
- [ ] Unit test: `test_retail_configuration()`
- [ ] Unit test: `test_hybrid_singleton()`
- [ ] Unit test: `test_hybrid_auto_wiring()`
- [ ] Unit test: `test_hybrid_manual_injection()`
- [ ] Integration test: `test_all_three_together()`
- [ ] Integration test: `test_with_startup_manager()`
- [ ] Integration test: `test_concurrent_access()`
- [ ] Regression test: All existing tests pass

### **Validation (Día 4):**
- [ ] Performance test: Startup time ≤7s
- [ ] Performance test: Memory usage acceptable
- [ ] Edge case: Redis unavailable
- [ ] Edge case: Shopify unavailable
- [ ] Edge case: Google Cloud timeout
- [ ] Backward compatibility: Legacy factories work
- [ ] Backward compatibility: All routers work
- [ ] Backward compatibility: MCP integration works

### **Documentation (Día 5):**
- [ ] FASE_1_CHANGES_service_factory.md (✅ DONE)
- [ ] FASE_1_COMPLETION_REPORT.md
- [ ] Update CURRENT_ARCHITECTURE.md
- [ ] Migration guide created
- [ ] Inline docstrings complete

### **Delivery:**
- [ ] All code committed
- [ ] PR created
- [ ] Reviewers assigned
- [ ] CI/CD passing
- [ ] Ready for merge

---

## ✅ CRITERIOS DE ACEPTACIÓN - FASE 1

### **Must Have (Obligatorio):**

#### **Funcionalidad:**
- [ ] `get_tfidf_recommender()` implemented and working
- [ ] `get_retail_recommender()` implemented and working
- [ ] `get_hybrid_recommender()` implemented and working
- [ ] Auto-wiring funciona correctamente
- [ ] Singletons funcionan (misma instancia retornada)
- [ ] Thread-safe (async locks funcionan)

#### **Compatibilidad:**
- [ ] Zero breaking changes
- [ ] StartupManager sigue funcionando
- [ ] Legacy `RecommenderFactory` sigue funcionando
- [ ] All existing tests pass
- [ ] All routers functioning
- [ ] MCP integration working

#### **Performance:**
- [ ] Startup time ≤7s (maintain baseline)
- [ ] Memory usage no increase
- [ ] Redis connection ≤1s
- [ ] TF-IDF load ≤100ms

#### **Testing:**
- [ ] 100% unit test coverage for new methods
- [ ] Integration tests passing
- [ ] Regression tests passing
- [ ] Edge cases tested

#### **Documentation:**
- [ ] All methods documented (docstrings)
- [ ] Architecture docs updated
- [ ] Completion report created
- [ ] Migration guide available

### **Should Have (Deseable):**
- [ ] Code review approval
- [ ] CI/CD green
- [ ] Performance equal or better than baseline
- [ ] Logs clean and informative

### **Nice to Have (Bonus):**
- [ ] Performance improvements
- [ ] Additional optimizations
- [ ] Enhanced error messages
- [ ] Metrics dashboard

---

## 🔧 CAMBIOS ESPECÍFICOS - CÓDIGO

### **ARCHIVO 1: service_factory.py**

**Ubicación:** `src/api/factories/service_factory.py`

#### **Cambio 1: Imports (Línea ~10)**

```python
# ANTES:
from typing import Optional
import asyncio
import logging

# DESPUÉS (AGREGAR):
from typing import Optional, TYPE_CHECKING
import asyncio
import logging

# ✅ ADD: Type hints para imports circulares
if TYPE_CHECKING:
    from src.recommenders.tfidf_recommender import TFIDFRecommender
    from src.recommenders.retail_api import RetailAPIRecommender
    from src.api.core.hybrid_recommender import HybridRecommender
```

**Razón:** Evitar circular imports pero mantener type hints.

---

#### **Cambio 2: Class Variables (Línea ~45, después de _personalization_lock)**

```python
# ANTES:
_personalization_lock: Optional[asyncio.Lock] = None

# DESPUÉS (AGREGAR):
_personalization_lock: Optional[asyncio.Lock] = None

# ✅ ADD: Recommender singletons - Fase 1
_tfidf_recommender: Optional['TFIDFRecommender'] = None
_tfidf_lock: Optional[asyncio.Lock] = None

_retail_recommender: Optional['RetailAPIRecommender'] = None
_retail_lock: Optional[asyncio.Lock] = None

_hybrid_recommender: Optional['HybridRecommender'] = None
_hybrid_lock: Optional[asyncio.Lock] = None
```

**Razón:** Singleton storage + locks para thread-safety.

---

#### **Cambio 3: Métodos TF-IDF (Línea ~180, después de get_product_cache_singleton)**

```python
# ✅ ADD: Después de get_product_cache_singleton() method

# ============================================================================
# 🤖 RECOMMENDER SINGLETONS - Fase 1 Implementation
# ============================================================================

@classmethod
def _get_tfidf_lock(cls):
    """Get or create TF-IDF lock (lazy initialization)"""
    if cls._tfidf_lock is None:
        cls._tfidf_lock = asyncio.Lock()
    return cls._tfidf_lock

@classmethod
async def get_tfidf_recommender(cls, auto_load: bool = False) -> 'TFIDFRecommender':
    """
    ✅ FASE 1: Get TF-IDF recommender singleton.
    
    Args:
        auto_load: If True, load model immediately (for tests).
                  If False, return unloaded instance (compatible with StartupManager).
    
    Returns:
        TFIDFRecommender instance (loaded or unloaded based on auto_load)
    
    Examples:
        # For production (with StartupManager):
        recommender = await ServiceFactory.get_tfidf_recommender()
        # StartupManager will call recommender.load() later
        
        # For testing (immediate load):
        recommender = await ServiceFactory.get_tfidf_recommender(auto_load=True)
        # Model is loaded and ready to use
    """
    from src.recommenders.tfidf_recommender import TFIDFRecommender
    from src.api.core.config import get_settings
    
    if cls._tfidf_recommender is None:
        tfidf_lock = cls._get_tfidf_lock()
        async with tfidf_lock:
            # Double-check locking pattern
            if cls._tfidf_recommender is None:
                settings = get_settings()
                model_path = getattr(settings, 'tfidf_model_path', 'data/tfidf_model.pkl')
                
                logger.info(f"✅ Creating TF-IDF recommender singleton: {model_path}")
                cls._tfidf_recommender = TFIDFRecommender(model_path=model_path)
                
                # Optional: Auto-load for testing scenarios
                if auto_load:
                    logger.info("🔄 Auto-loading TF-IDF model...")
                    import os
                    if os.path.exists(model_path):
                        success = await cls._tfidf_recommender.load()
                        if success:
                            logger.info(f"✅ TF-IDF model auto-loaded: {len(cls._tfidf_recommender.product_data)} products")
                        else:
                            logger.warning("⚠️ TF-IDF auto-load failed")
                    else:
                        logger.warning(f"⚠️ Model file not found: {model_path}")
    
    return cls._tfidf_recommender
```

**Razón:** 
- Singleton pattern con lazy init
- Compatible con StartupManager (auto_load=False default)
- Testing friendly (auto_load=True para tests)

---

#### **Cambio 4: Métodos Retail API (Línea ~240)**

```python
# ✅ ADD: Después de get_tfidf_recommender()

@classmethod
def _get_retail_lock(cls):
    """Get or create Retail API lock"""
    if cls._retail_lock is None:
        cls._retail_lock = asyncio.Lock()
    return cls._retail_lock

@classmethod
async def get_retail_recommender(cls) -> 'RetailAPIRecommender':
    """
    ✅ FASE 1: Get Google Retail API recommender singleton.
    
    Returns:
        RetailAPIRecommender instance configured with project settings
    
    Note:
        First call may take 4+ seconds due to Google Cloud service
        initialization. This is normal and expected behavior.
        
        ALTS warnings are normal when running outside GCP.
    """
    from src.recommenders.retail_api import RetailAPIRecommender
    from src.api.core.config import get_settings
    
    if cls._retail_recommender is None:
        retail_lock = cls._get_retail_lock()
        async with retail_lock:
            if cls._retail_recommender is None:
                settings = get_settings()
                
                logger.info("✅ Creating Retail API recommender singleton")
                logger.info(f"   Project: {settings.google_project_number}")
                logger.info(f"   Location: {settings.google_location}")
                logger.info(f"   Catalog: {settings.google_catalog}")
                
                cls._retail_recommender = RetailAPIRecommender(
                    project_number=settings.google_project_number,
                    location=settings.google_location,
                    catalog=settings.google_catalog,
                    serving_config_id=settings.google_serving_config
                )
                
                logger.info("✅ Retail API recommender singleton created")
    
    return cls._retail_recommender
```

**Razón:**
- Singleton para reutilizar instancia (costosa de crear)
- Configuration injection automática
- Logging para troubleshooting

---

#### **Cambio 5: Métodos Hybrid (Línea ~290)**

```python
# ✅ ADD: Después de get_retail_recommender()

@classmethod
def _get_hybrid_lock(cls):
    """Get or create Hybrid lock"""
    if cls._hybrid_lock is None:
        cls._hybrid_lock = asyncio.Lock()
    return cls._hybrid_lock

@classmethod
async def get_hybrid_recommender(
    cls,
    content_recommender=None,
    retail_recommender=None,
    product_cache=None
) -> 'HybridRecommender':
    """
    ✅ FASE 1: Get Hybrid recommender singleton with auto-wiring.
    
    Args:
        content_recommender: Optional TF-IDF recommender (auto-fetched if None)
        retail_recommender: Optional Retail recommender (auto-fetched if None)
        product_cache: Optional ProductCache (auto-fetched if None)
    
    Returns:
        HybridRecommender with all dependencies wired automatically
    
    Note:
        When dependencies are None, they are automatically fetched from
        ServiceFactory singletons. This ensures consistency and reduces
        boilerplate code.
        
    Examples:
        # Auto-wiring (recommended):
        hybrid = await ServiceFactory.get_hybrid_recommender()
        
        # Manual injection (for testing):
        hybrid = await ServiceFactory.get_hybrid_recommender(
            content_recommender=mock_tfidf,
            retail_recommender=mock_retail
        )
    """
    from src.api.core.config import get_settings
    
    if cls._hybrid_recommender is None:
        hybrid_lock = cls._get_hybrid_lock()
        async with hybrid_lock:
            if cls._hybrid_recommender is None:
                settings = get_settings()
                
                logger.info("✅ Creating Hybrid recommender singleton with auto-wiring")
                
                # ✅ AUTO-WIRING: Fetch dependencies from ServiceFactory
                if content_recommender is None:
                    logger.info("   🔄 Auto-fetching TF-IDF recommender...")
                    content_recommender = await cls.get_tfidf_recommender(auto_load=False)
                
                if retail_recommender is None:
                    logger.info("   🔄 Auto-fetching Retail recommender...")
                    retail_recommender = await cls.get_retail_recommender()
                
                if product_cache is None:
                    logger.info("   🔄 Auto-fetching ProductCache...")
                    product_cache = await cls.get_product_cache_singleton()
                
                # ✅ Create hybrid recommender based on settings
                if settings.exclude_seen_products:
                    from src.api.core.hybrid_recommender import HybridRecommenderWithExclusion
                    logger.info("   Using HybridRecommenderWithExclusion")
                    
                    cls._hybrid_recommender = HybridRecommenderWithExclusion(
                        content_recommender=content_recommender,
                        retail_recommender=retail_recommender,
                        content_weight=settings.content_weight,
                        product_cache=product_cache
                    )
                else:
                    from src.api.core.hybrid_recommender import HybridRecommender
                    logger.info("   Using HybridRecommender (basic)")
                    
                    cls._hybrid_recommender = HybridRecommender(
                        content_recommender=content_recommender,
                        retail_recommender=retail_recommender,
                        content_weight=settings.content_weight,
                        product_cache=product_cache
                    )
                
                logger.info("✅ Hybrid recommender singleton created successfully")
                logger.info(f"   Content weight: {settings.content_weight}")
                logger.info(f"   Exclude seen products: {settings.exclude_seen_products}")
    
    return cls._hybrid_recommender
```

**Razón:**
- Auto-wiring elimina boilerplate
- Dependency injection moderna
- Configuration-driven (exclude_seen_products)
- Testing-friendly (manual injection option)

---

## 🧪 TESTS A CREAR

### **ARCHIVO: tests/test_service_factory_phase1.py**

```python
"""
Tests para Fase 1: ServiceFactory extended methods
"""
import pytest
import asyncio
from src.api.factories.service_factory import ServiceFactory

# ============================================================================
# TF-IDF Tests
# ============================================================================

@pytest.mark.asyncio
async def test_tfidf_singleton():
    """Verify same TF-IDF instance is returned"""
    r1 = await ServiceFactory.get_tfidf_recommender()
    r2 = await ServiceFactory.get_tfidf_recommender()
    assert r1 is r2, "Should return same singleton instance"

@pytest.mark.asyncio
async def test_tfidf_auto_load_false():
    """Verify auto_load=False returns unloaded instance"""
    recommender = await ServiceFactory.get_tfidf_recommender(auto_load=False)
    assert recommender is not None
    # Note: loaded state depends on StartupManager, don't assert here

@pytest.mark.asyncio
async def test_tfidf_auto_load_true():
    """Verify auto_load=True loads model"""
    recommender = await ServiceFactory.get_tfidf_recommender(auto_load=True)
    assert recommender is not None
    # If model file exists, should be loaded
    import os
    if os.path.exists('data/tfidf_model.pkl'):
        assert recommender.loaded == True
        assert len(recommender.product_data) > 0

# ============================================================================
# Retail API Tests
# ============================================================================

@pytest.mark.asyncio
async def test_retail_singleton():
    """Verify same Retail API instance is returned"""
    r1 = await ServiceFactory.get_retail_recommender()
    r2 = await ServiceFactory.get_retail_recommender()
    assert r1 is r2, "Should return same singleton instance"

@pytest.mark.asyncio
async def test_retail_configuration():
    """Verify Retail API is configured correctly"""
    from src.api.core.config import get_settings
    settings = get_settings()
    
    recommender = await ServiceFactory.get_retail_recommender()
    assert recommender.project_number == settings.google_project_number
    assert recommender.location == settings.google_location

# ============================================================================
# Hybrid Tests
# ============================================================================

@pytest.mark.asyncio
async def test_hybrid_singleton():
    """Verify same Hybrid instance is returned"""
    r1 = await ServiceFactory.get_hybrid_recommender()
    r2 = await ServiceFactory.get_hybrid_recommender()
    assert r1 is r2, "Should return same singleton instance"

@pytest.mark.asyncio
async def test_hybrid_auto_wiring():
    """Verify dependencies are auto-fetched"""
    hybrid = await ServiceFactory.get_hybrid_recommender()
    assert hybrid.content_recommender is not None
    assert hybrid.retail_recommender is not None
    assert hybrid.product_cache is not None

@pytest.mark.asyncio
async def test_hybrid_manual_injection():
    """Verify manual injection works"""
    from unittest.mock import Mock
    
    mock_tfidf = Mock()
    mock_retail = Mock()
    mock_cache = Mock()
    
    # Reset singleton for this test
    ServiceFactory._hybrid_recommender = None
    
    hybrid = await ServiceFactory.get_hybrid_recommender(
        content_recommender=mock_tfidf,
        retail_recommender=mock_retail,
        product_cache=mock_cache
    )
    
    assert hybrid.content_recommender is mock_tfidf
    assert hybrid.retail_recommender is mock_retail
    assert hybrid.product_cache is mock_cache

# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_all_three_methods_together():
    """Verify all three methods work together"""
    tfidf = await ServiceFactory.get_tfidf_recommender()
    retail = await ServiceFactory.get_retail_recommender()
    hybrid = await ServiceFactory.get_hybrid_recommender()
    
    assert tfidf is not None
    assert retail is not None
    assert hybrid is not None
    assert hybrid.content_recommender is tfidf
    assert hybrid.retail_recommender is retail

@pytest.mark.asyncio
async def test_concurrent_access():
    """Verify thread-safe concurrent access"""
    async def get_recommender():
        return await ServiceFactory.get_tfidf_recommender()
    
    # Create 10 concurrent tasks
    tasks = [get_recommender() for _ in range(10)]
    results = await asyncio.gather(*tasks)
    
    # All should be the same instance
    first = results[0]
    assert all(r is first for r in results), "All should be same singleton"

# ============================================================================
# Backward Compatibility Tests
# ============================================================================

@pytest.mark.asyncio
async def test_legacy_factories_still_work():
    """Verify RecommenderFactory still functional"""
    from src.api.factories.factories import RecommenderFactory
    
    # Legacy sync method should still work
    tfidf_legacy = RecommenderFactory.create_tfidf_recommender()
    assert tfidf_legacy is not None

@pytest.mark.asyncio
async def test_startup_manager_compatibility():
    """Verify StartupManager can still use recommender"""
    recommender = await ServiceFactory.get_tfidf_recommender(auto_load=False)
    
    # Should be unloaded initially (StartupManager will load it)
    # Note: This test assumes clean state; in real system StartupManager may have loaded it
    assert recommender is not None
```

---

## 📊 MÉTRICAS POST-IMPLEMENTACIÓN

### **Comparación con Baseline:**

```yaml
Startup Time:
  Baseline: 6.9s
  Target: ≤7s
  Actual: [TO BE MEASURED]

ServiceFactory Methods:
  Baseline: 6 methods
  Target: 9 methods (+50%)
  Actual: [AFTER IMPLEMENTATION]

Code Duplication:
  Baseline: ~60%
  Target: Still ~60% (no change this phase)
  Actual: [UNCHANGED - as expected]

Memory Usage:
  Baseline: [BASELINE VALUE]
  Target: No significant increase
  Actual: [TO BE MEASURED]

Test Coverage:
  Baseline: [EXISTING COVERAGE]
  Target: +15 new tests
  Actual: [AFTER TESTS]
```

---

## 🎯 PRÓXIMOS PASOS DESPUÉS DE FASE 1

### **Semana Siguiente - Fase 2:**
1. Create `dependencies.py` with FastAPI dependency functions
2. Type aliases (Annotated)
3. Documentation

### **Semana 3 - Fase 3:**
1. Migrate `main_unified_redis.py` to use ServiceFactory
2. Remove global variables
3. Testing

### **Semana 4 - Fase 4:**
1. Migrate routers to use FastAPI DI
2. Remove legacy factory imports
3. Final cleanup

---

## ✅ RESUMEN - ACCIÓN INMEDIATA

### **HOY (primeras 2 horas):**
1. ✅ Create branch: `git checkout -b feature/phase1-extend-servicefactory`
2. ✅ Backup `service_factory.py`
3. ✅ Begin implementing `get_tfidf_recommender()`

### **Esta Semana (5 días):**
- Días 1-3: Implement 3 métodos
- Día 4: Integration testing
- Día 5: Documentation + PR

### **Resultado Esperado:**
- ✅ 3 nuevos métodos en ServiceFactory
- ✅ Zero breaking changes
- ✅ Tests passing
- ✅ PR ready for review

---

**Status:** ✅ PLAN COMPLETO Y EJECUTABLE  
**Ready to begin:** SÍ  
**First task:** Create branch + implement get_tfidf_recommender()

¿Comenzamos con la implementación? 🚀
