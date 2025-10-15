# 🔧 FASE 1: CAMBIOS EN service_factory.py

**Archivo:** `src/api/factories/service_factory.py`  
**Línea inicial:** Después del método `get_product_cache_singleton()` (línea ~180)  
**Acción:** AGREGAR nuevos métodos

---

## 📝 MÉTODO 1: get_tfidf_recommender()

**Ubicación:** Línea ~190  
**Propósito:** Crear singleton TF-IDF recommender compatible con StartupManager

```python
# ============================================================================
# 🤖 RECOMMENDER SINGLETONS - Fase 1 Implementation
# ============================================================================

_tfidf_recommender: Optional['TFIDFRecommender'] = None
_tfidf_lock: Optional[asyncio.Lock] = None

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
    
    Note:
        For production startup, use auto_load=False and let StartupManager
        handle the loading via load_recommender() function in main.
        
        For testing, use auto_load=True to get immediately usable instance.
    """
    from src.recommenders.tfidf_recommender import TFIDFRecommender
    from src.api.core.config import get_settings
    
    if cls._tfidf_recommender is None:
        tfidf_lock = cls._get_tfidf_lock()
        async with tfidf_lock:
            # Double-check locking
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
                            logger.info("✅ TF-IDF model auto-loaded successfully")
                        else:
                            logger.warning("⚠️ TF-IDF auto-load failed")
                    else:
                        logger.warning(f"⚠️ Model file not found: {model_path}")
    
    return cls._tfidf_recommender
```

**Explicación:**
- ✅ **Singleton pattern:** Solo una instancia global
- ✅ **Thread-safe:** Async lock previene race conditions
- ✅ **Compatible con StartupManager:** `auto_load=False` (default) retorna instancia sin cargar
- ✅ **Testing friendly:** `auto_load=True` para tests que necesitan modelo cargado
- ✅ **Lazy initialization:** Se crea solo cuando se necesita

**Beneficios:**
- 🔄 Reemplaza `RecommenderFactory.create_tfidf_recommender()`
- ✅ Centralizado en ServiceFactory
- ✅ No rompe código existente (StartupManager sigue funcionando)

---

## 📝 MÉTODO 2: get_retail_recommender()

**Ubicación:** Línea ~240  
**Propósito:** Crear singleton Retail API recommender

```python
_retail_recommender: Optional['RetailAPIRecommender'] = None
_retail_lock: Optional[asyncio.Lock] = None

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
        This may take 4+ seconds on first call due to Google Cloud
        service initialization. This is normal and expected.
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

**Explicación:**
- ✅ **Singleton pattern:** Una instancia compartida
- ✅ **Configuration injection:** Lee settings automáticamente
- ⚠️ **Performance note:** Primera llamada tarda ~4s (Google Cloud init)

**Beneficios:**
- 🔄 Reemplaza `RecommenderFactory.create_retail_recommender()`
- ✅ Reutiliza instancia en lugar de recrear
- ✅ Settings centralizados

---

## 📝 MÉTODO 3: get_hybrid_recommender()

**Ubicación:** Línea ~280  
**Propósito:** Crear singleton Hybrid recommender con auto-wiring

```python
_hybrid_recommender: Optional['HybridRecommender'] = None
_hybrid_lock: Optional[asyncio.Lock] = None

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
        HybridRecommender with all dependencies wired
    
    Note:
        Dependencies are automatically fetched from ServiceFactory singletons.
        This ensures consistency across the application.
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
                    logger.info("   Auto-fetching TF-IDF recommender...")
                    content_recommender = await cls.get_tfidf_recommender(auto_load=False)
                
                if retail_recommender is None:
                    logger.info("   Auto-fetching Retail recommender...")
                    retail_recommender = await cls.get_retail_recommender()
                
                if product_cache is None:
                    logger.info("   Auto-fetching ProductCache...")
                    product_cache = await cls.get_product_cache_singleton()
                
                # Create hybrid recommender based on settings
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
                
                logger.info("✅ Hybrid recommender singleton created")
                logger.info(f"   Content weight: {settings.content_weight}")
                logger.info(f"   Exclude seen: {settings.exclude_seen_products}")
    
    return cls._hybrid_recommender
```

**Explicación:**
- ✅ **Auto-wiring:** Busca dependencias automáticamente si no se proveen
- ✅ **Configuration-driven:** Crea tipo correcto según settings
- ✅ **Dependency injection:** Inyecta ProductCache, TF-IDF, Retail
- ✅ **Singleton:** Una instancia compartida

**Beneficios:**
- 🔄 Reemplaza `RecommenderFactory.create_hybrid_recommender()`
- ✅ Auto-wiring elimina boilerplate
- ✅ Garantiza consistencia de dependencias

---

## 📝 MÉTODO 4-7: MCP Components (OPCIONAL - Fase 1.5)

**Ubicación:** Línea ~360  
**Status:** OPCIONAL - Puede hacerse en Fase 1 o después

```python
# ============================================================================
# 🎯 MCP SINGLETONS - Fase 1.5 (Optional)
# ============================================================================

_mcp_client: Optional['MCPClientEnhanced'] = None
_user_event_store: Optional['UserEventStore'] = None

@classmethod
async def get_mcp_client(cls) -> 'MCPClientEnhanced':
    """✅ FASE 1.5: Get MCP client singleton"""
    # Implementation similar to above patterns
    pass

@classmethod
async def get_user_event_store(cls) -> 'UserEventStore':
    """✅ FASE 1.5: Get UserEventStore singleton with enterprise Redis"""
    # Uses cls.get_redis_service() automatically
    pass
```

**Decisión:** Implementar en Fase 1 SOLO si hay tiempo. No es crítico.

---

## 📊 SUMMARY OF CHANGES - service_factory.py

### **Líneas agregadas:** ~180 líneas
### **Métodos nuevos:** 3 críticos + 4 opcionales

**Críticos (Must Have):**
1. ✅ `get_tfidf_recommender()` - Línea ~190
2. ✅ `get_retail_recommender()` - Línea ~240  
3. ✅ `get_hybrid_recommender()` - Línea ~280

**Opcionales (Nice to Have):**
4. ⚪ `get_mcp_client()` - Fase 1.5
5. ⚪ `get_user_event_store()` - Fase 1.5
6. ⚪ `get_market_manager()` - Fase 1.5
7. ⚪ `get_market_cache()` - Fase 1.5

### **Imports necesarios:**

```python
# Agregar al inicio del archivo (línea ~20)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.recommenders.tfidf_recommender import TFIDFRecommender
    from src.recommenders.retail_api import RetailAPIRecommender
    from src.api.core.hybrid_recommender import HybridRecommender
```

---

## ✅ BENEFICIOS DE ESTOS CAMBIOS

### **Arquitectura:**
- ✅ Centralización en ServiceFactory
- ✅ Singleton pattern consistente
- ✅ Dependency injection mejorada
- ✅ Auto-wiring de dependencias

### **Mantenibilidad:**
- ✅ Un solo lugar para crear componentes
- ✅ Configuration centralizada
- ✅ Fácil testing (mocking singletons)

### **Performance:**
- ✅ Reutilización de instancias
- ✅ No recrear componentes caros
- ✅ Lazy initialization

### **Compatibilidad:**
- ✅ StartupManager sigue funcionando
- ✅ Zero breaking changes
- ✅ Legacy code puede coexistir

---

## 🧪 TESTING STRATEGY

### **Test 1: Singleton behavior**
```python
async def test_tfidf_singleton():
    """Verify same instance is returned"""
    r1 = await ServiceFactory.get_tfidf_recommender()
    r2 = await ServiceFactory.get_tfidf_recommender()
    assert r1 is r2  # Same object
```

### **Test 2: Auto-wiring**
```python
async def test_hybrid_auto_wiring():
    """Verify dependencies are auto-fetched"""
    hybrid = await ServiceFactory.get_hybrid_recommender()
    assert hybrid.content_recommender is not None
    assert hybrid.retail_recommender is not None
    assert hybrid.product_cache is not None
```

### **Test 3: StartupManager compatibility**
```python
async def test_startup_manager_compat():
    """Verify auto_load=False works with StartupManager"""
    recommender = await ServiceFactory.get_tfidf_recommender(auto_load=False)
    assert recommender.loaded == False  # Not loaded yet
    # StartupManager will call load() later
```

---

**Status:** ✅ DESIGN COMPLETE  
**Next:** Implement in code  
**Timeline:** 2-3 días para implementación + testing
