# 🚀 M2: CACHE SHOPIFY API - PLAN DE IMPLEMENTACIÓN

**Fase**: M2 - Cache Shopify Translation API  
**Fecha**: 14 Febrero 2026  
**Prioridad**: Media (optimización de performance)  
**Estado**: 📋 **PLANIFICADO**

---

## 🎯 OBJETIVO

Reducir tiempo de KB sync mediante cache de traducciones de Shopify API en Redis.

**Target**: Reducir sync time de 3.55s a <0.5s (7x speedup) en syncs subsecuentes.

---

## 📊 JUSTIFICACIÓN (BASADO EN M1 PROFILING)

### Bottleneck Identificado

```
Shopify API calls: 88% del tiempo total
├─ Fetch KB pages:       0.997s (38.5%)  ← Ya usa metafields cache
├─ Fetch translations:   0.713s (27.5%)  ← TARGET M2
└─ Sync translations:    0.585s (22.6%)  ← TARGET M2

DB operations: 0.2% del tiempo (despreciable)
```

**Problema**: Cada sync hace llamadas repetidas a Shopify Translation API:
- 13 páginas × 1 traducción (EN) = 13 llamadas GraphQL
- 13 páginas × 1 título traducido = 13 llamadas GraphQL adicionales
- **Total: 26 llamadas GraphQL por sync**

**Oportunidad**: Traducciones cambian raramente (solo cuando marketing actualiza content).

---

## 💡 SOLUCIÓN PROPUESTA

### Estrategia de Cache

**Tipo**: Write-through cache con TTL largo

**Arquitectura**:
```
┌─────────────────┐
│  KB Sync        │
│  Service        │
└────────┬────────┘
         │
         ├──> 1. Check Redis Cache
         │    (key: kb:trans:{page_id}:{locale})
         │
         ├──> 2. If MISS → Fetch from Shopify API
         │    └─> Store in cache (TTL: 24h)
         │
         └──> 3. Return cached data
```

**Cache Keys**:
```python
# Translation body HTML
f"kb:trans:body:{page_id}:{locale}"

# Translation title
f"kb:trans:title:{page_id}:{locale}"

# Shop locales (ya existe)
f"kb:shop:locales"  # TTL: 1h
```

**TTL Strategy**:
- **24 horas** para translations (cambian raramente)
- **1 hora** para shop locales (ya implementado)
- **Manual invalidation** vía webhook cuando se actualiza página

---

## 📐 DISEÑO TÉCNICO

### Opción A: Cache en ShopifyKBClient (RECOMENDADO)

**Ventajas**:
- ✅ Reutilizable (cualquier servicio que use ShopifyKBClient se beneficia)
- ✅ Encapsulación clara (client maneja su propio cache)
- ✅ No modifica shopify_kb_sync.py

**Implementación**:

```python
# En src/api/integrations/shopify_kb_client.py

class ShopifyKBClient(ShopifyIntegration):
    
    def __init__(self, shop_url, access_token, redis_service=None, webhook_secret=None):
        super().__init__(shop_url, access_token)
        self.redis = redis_service  # ✅ NEW: Redis para cache
        self.webhook_secret = webhook_secret
        # ... existing code ...
        
        # ✅ NEW: Cache TTLs configurables
        self._translation_cache_ttl = int(os.getenv("KB_TRANSLATION_CACHE_TTL", "86400"))  # 24h
    
    async def get_page_translations(self, page_id: int) -> Dict[str, str]:
        """
        Fetch translations with Redis cache.
        
        Cache strategy:
        1. Try Redis first
        2. If miss → Fetch from Shopify
        3. Store in Redis with 24h TTL
        """
        translations = {}
        
        # Get available locales (already cached 1h)
        primary_locale, available_locales = await self._get_shop_locales()
        
        if not available_locales:
            return {}
        
        # ✅ NEW: Parallel fetch with cache check
        async def fetch_translation_cached(locale: str) -> tuple[str, Optional[str]]:
            """Fetch translation with cache layer."""
            
            if not self.redis:
                # Fallback: No cache, fetch directly
                return await self._fetch_translation_from_shopify(page_id, locale)
            
            # Check cache
            cache_key = f"kb:trans:body:{page_id}:{locale}"
            
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    logger.debug(
                        "translation_cache_hit",
                        page_id=page_id,
                        locale=locale,
                        cache_key=cache_key
                    )
                    return (locale, cached)
            except Exception as e:
                logger.warning(
                    "translation_cache_read_failed",
                    page_id=page_id,
                    locale=locale,
                    error=str(e)
                )
            
            # Cache miss → Fetch from Shopify
            logger.debug(
                "translation_cache_miss",
                page_id=page_id,
                locale=locale
            )
            
            locale, translated_html = await self._fetch_translation_from_shopify(page_id, locale)
            
            # Store in cache
            if translated_html and self.redis:
                try:
                    await self.redis.set(
                        cache_key,
                        translated_html,
                        ttl=self._translation_cache_ttl
                    )
                    logger.debug(
                        "translation_cached",
                        page_id=page_id,
                        locale=locale,
                        ttl_seconds=self._translation_cache_ttl
                    )
                except Exception as e:
                    logger.warning(
                        "translation_cache_write_failed",
                        page_id=page_id,
                        locale=locale,
                        error=str(e)
                    )
            
            return (locale, translated_html)
        
        # Execute all fetches in parallel (cache or Shopify)
        translation_tasks = [
            fetch_translation_cached(locale) 
            for locale in available_locales
        ]
        
        translation_results = await asyncio.gather(*translation_tasks)
        
        # Build result dict
        for locale, translated_html in translation_results:
            if translated_html is not None:
                translations[locale] = translated_html
        
        logger.info(
            "translations_fetched_with_cache",
            page_id=page_id,
            translations_count=len(translations),
            locales=list(translations.keys())
        )
        
        return translations
    
    async def _fetch_translation_from_shopify(
        self, 
        page_id: int, 
        locale: str
    ) -> tuple[str, Optional[str]]:
        """Original fetch logic (extracted from get_page_translations)."""
        try:
            translation_query = """
            query getPageTranslation($resourceId: ID!, $locale: String!) {
                translatableResource(resourceId: $resourceId) {
                    resourceId
                    translations(locale: $locale) {
                        key
                        value
                        locale
                    }
                }
            }
            """
            
            variables = {
                "resourceId": f"gid://shopify/Page/{page_id}",
                "locale": locale
            }
            
            data = await self._graphql_query_with_retry(translation_query, variables)
            resource = data.get("translatableResource", {})
            translations_raw = resource.get("translations", [])
            
            for trans in translations_raw:
                if trans["key"] == "body_html" and trans["value"]:
                    return (locale, trans["value"])
            
            return (locale, None)
            
        except Exception as e:
            logger.warning(
                "translation_fetch_failed",
                page_id=page_id,
                locale=locale,
                error=str(e),
                error_type=type(e).__name__
            )
            return (locale, None)
    
    async def get_page_title_translation(
        self, 
        page_id: int,
        locale: str
    ) -> Optional[str]:
        """
        Fetch title translation with cache.
        """
        if not self.redis:
            # Fallback: No cache
            return await self._fetch_title_from_shopify(page_id, locale)
        
        # Check cache
        cache_key = f"kb:trans:title:{page_id}:{locale}"
        
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                logger.debug(
                    "title_translation_cache_hit",
                    page_id=page_id,
                    locale=locale
                )
                return cached
        except Exception as e:
            logger.warning(
                "title_cache_read_failed",
                page_id=page_id,
                locale=locale,
                error=str(e)
            )
        
        # Cache miss → Fetch from Shopify
        logger.debug(
            "title_translation_cache_miss",
            page_id=page_id,
            locale=locale
        )
        
        title = await self._fetch_title_from_shopify(page_id, locale)
        
        # Store in cache
        if title and self.redis:
            try:
                await self.redis.set(
                    cache_key,
                    title,
                    ttl=self._translation_cache_ttl
                )
                logger.debug(
                    "title_translation_cached",
                    page_id=page_id,
                    locale=locale
                )
            except Exception as e:
                logger.warning(
                    "title_cache_write_failed",
                    page_id=page_id,
                    locale=locale,
                    error=str(e)
                )
        
        return title
    
    async def _fetch_title_from_shopify(
        self,
        page_id: int,
        locale: str
    ) -> Optional[str]:
        """Original title fetch logic."""
        try:
            translation_query = """
            query getPageTitleTranslation($resourceId: ID!, $locale: String!) {
                translatableResource(resourceId: $resourceId) {
                    resourceId
                    translations(locale: $locale) {
                        key
                        value
                        locale
                    }
                }
            }
            """
            
            variables = {
                "resourceId": f"gid://shopify/Page/{page_id}",
                "locale": locale
            }
            
            data = await self._graphql_query_with_retry(translation_query, variables)
            resource = data.get("translatableResource", {})
            translations = resource.get("translations", [])
            
            for trans in translations:
                if trans["key"] == "title" and trans["value"]:
                    return trans["value"]
            
            return None
            
        except Exception as e:
            logger.warning(
                "title_fetch_failed",
                page_id=page_id,
                locale=locale,
                error=str(e)
            )
            return None
    
    async def invalidate_translation_cache(self, page_id: int) -> None:
        """
        Invalidate all cached translations for a page.
        
        Call this when page is updated via webhook.
        """
        if not self.redis:
            return
        
        # Get all possible locales
        try:
            primary_locale, available_locales = await self._get_shop_locales()
            all_locales = [primary_locale] + available_locales
        except Exception as e:
            logger.warning(
                "locale_fetch_failed_during_invalidation",
                page_id=page_id,
                error=str(e)
            )
            # Hardcode common locales as fallback
            all_locales = ['es', 'en', 'pt', 'fr', 'de']
        
        # Delete all cached translations
        deleted_count = 0
        for locale in all_locales:
            try:
                body_key = f"kb:trans:body:{page_id}:{locale}"
                title_key = f"kb:trans:title:{page_id}:{locale}"
                
                await self.redis.delete(body_key)
                await self.redis.delete(title_key)
                deleted_count += 2
            except Exception as e:
                logger.warning(
                    "cache_invalidation_failed",
                    page_id=page_id,
                    locale=locale,
                    error=str(e)
                )
        
        logger.info(
            "translation_cache_invalidated",
            page_id=page_id,
            keys_deleted=deleted_count
        )
```

**Modificación en ServiceFactory**:

```python
# src/api/factories/service_factory.py

@classmethod
async def get_kb_sync_service(cls) -> 'ShopifyKBSyncService':
    """Get ShopifyKBSyncService singleton."""
    lock = cls._get_kb_sync_lock()
    
    async with lock:
        if cls._kb_sync_service is None:
            logger.info("Initializing ShopifyKBSyncService...")
            
            try:
                from src.api.services.shopify_kb_sync import ShopifyKBSyncService
                from src.api.core.store import get_shopify_kb_client_with_cache  # ✅ NEW
                
                db_pool = await cls.get_db_pool()
                redis = await cls.get_redis_service()
                
                # ✅ NEW: Pass redis to KB client for caching
                shopify = get_shopify_kb_client_with_cache(redis_service=redis)
                
                if shopify is None:
                    raise RuntimeError("ShopifyKBClient initialization failed")
                
                cls._kb_sync_service = ShopifyKBSyncService(
                    shopify_client=shopify,
                    db_pool=db_pool,
                    redis_service=redis
                )
                
                logger.info("✅ ShopifyKBSyncService initialized with translation cache")
                
            except Exception as e:
                logger.error(f"❌ Failed to create ShopifyKBSyncService: {e}")
                raise
        
        return cls._kb_sync_service
```

**Modificación en store.py**:

```python
# src/api/core/store.py

def get_shopify_kb_client_with_cache(redis_service=None):
    """Get ShopifyKBClient with Redis cache support."""
    global shopify_kb_client
    
    shop_url = os.getenv("SHOPIFY_SHOP_URL")
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    
    if not shop_url or not access_token:
        logging.error("Missing Shopify credentials")
        return None
    
    # Create client with Redis cache
    try:
        shopify_kb_client = ShopifyKBClient(
            shop_url=shop_url,
            access_token=access_token,
            redis_service=redis_service  # ✅ NEW: Pass Redis
        )
        logging.info(f"Shopify KB client initialized with cache for {shop_url}")
        return shopify_kb_client
    except Exception as e:
        logging.error(f"Error initializing Shopify KB client: {e}")
        return None
```

---

## 📊 IMPACTO ESPERADO

### Performance Projection

**First sync (cache miss)**:
```
Duration: ~3.55s (igual que ahora)
- Fetch pages: 0.997s
- Fetch translations: 0.713s (miss → Shopify)
- Sync translations: 0.585s
- DB writes: 0.052s
- Cache writes: +0.1s (nuevo overhead)
Total: ~3.65s (ligeramente peor)
```

**Subsequent syncs (cache hit)**:
```
Duration: ~0.5s
- Fetch pages: 0.997s (no cacheable, depende de metafields)
- Fetch translations: 0.05s (hit → Redis, 14x faster)
- Sync translations: 0.05s (hit → Redis, 11x faster)
- DB writes: 0.052s
- Cache overhead: negligible
Total: ~0.5s (7x faster!)
```

**ROI**:
- First sync: +3% slower (overhead aceptable)
- Subsequent syncs: **7x faster**
- Cache hit rate esperado: >90% (traducciones cambian raramente)

---

## 🔧 CONFIGURACIÓN

### Environment Variables

```bash
# M2 Optimization - Translation Cache
KB_TRANSLATION_CACHE_TTL=86400  # 24 horas (default)

# Opción: Deshabilitar cache (debugging)
# KB_TRANSLATION_CACHE_TTL=0  # 0 = disabled
```

---

## 🧪 PLAN DE TESTING

### Fase 1: Implementación (2-3 horas)

1. **Modificar ShopifyKBClient** (1.5h)
   - Agregar parámetro `redis_service` en `__init__`
   - Refactorizar `get_page_translations` con cache
   - Refactorizar `get_page_title_translation` con cache
   - Agregar `invalidate_translation_cache` method

2. **Modificar ServiceFactory** (0.5h)
   - Pasar `redis_service` al crear ShopifyKBClient
   - Actualizar `store.py` factory function

3. **Testing unitario** (1h)
   - Test cache hit
   - Test cache miss
   - Test cache invalidation
   - Test fallback sin Redis

### Fase 2: Validación (1 hora)

1. **Benchmark con cache**:
   ```bash
   # First run (cold cache)
   python scripts/benchmark_kb_sync_baseline.py
   # Expected: ~3.65s
   
   # Second run (warm cache)
   python scripts/benchmark_kb_sync_baseline.py
   # Expected: ~0.5s (7x faster!)
   ```

2. **Profiling detallado**:
   ```bash
   python scripts/profile_kb_sync.py
   # Verificar:
   # - Cache hits en logs
   # - Fetch translations: 0.05s (vs 0.713s sin cache)
   ```

3. **Testing cache invalidation**:
   ```bash
   # Manual invalidation test
   python -c "
   from src.api.dependencies import get_kb_sync_service
   import asyncio
   async def test():
       service = await get_kb_sync_service()
       await service.shopify.invalidate_translation_cache(158888329525)
   asyncio.run(test())
   "
   ```

### Fase 3: Deployment (30 min)

1. **Deploy a staging**
2. **Monitor 24h**:
   - Cache hit rate (target: >90%)
   - Sync duration (target: <0.5s en warm cache)
   - Redis memory usage (estimado: ~2MB por 13 páginas)
3. **Deploy a production**

---

## ⚠️ RIESGOS Y MITIGACIONES

### Riesgo 1: Traducciones Stale

**Problema**: Cache de 24h puede mostrar contenido desactualizado.

**Mitigación**:
- ✅ Implementar webhook `pages/update` para invalidar cache
- ✅ TTL configurable (reducir a 1h si necesario)
- ✅ Manual invalidation via endpoint `/api/kb/cache/invalidate/{page_id}`

### Riesgo 2: Redis Memory Usage

**Estimación**:
```
13 páginas × 2 locales × 2 keys (body + title) = 52 keys
Average size: ~10KB por translation
Total: ~520KB

Con 100 páginas: ~4MB (aceptable)
```

**Mitigación**:
- ✅ TTL automático (24h) libera memoria
- ✅ Monitor Redis memory usage
- ✅ Implementar LRU eviction policy si necesario

### Riesgo 3: Cache Inconsistency

**Problema**: Sync puede ver mezcla de cached/fresh data.

**Mitigación**:
- ✅ Atomic invalidation (delete all locales for page)
- ✅ Version tags en cache keys (futuro)
- ✅ Fallback graceful si Redis falla

---

## 📋 CHECKLIST DE IMPLEMENTACIÓN

### Pre-Implementation
- [ ] Revisar plan M2 con equipo
- [ ] Aprobar ROI (7x speedup en warm cache)
- [ ] Confirmar Redis disponible y configurado

### Implementation
- [ ] Modificar `shopify_kb_client.py`
- [ ] Modificar `service_factory.py`
- [ ] Modificar `store.py`
- [ ] Agregar tests unitarios
- [ ] Commit: `feat(kb-sync): M2 - Add translation cache layer`

### Testing
- [ ] Ejecutar benchmarks (cold/warm)
- [ ] Ejecutar profiling
- [ ] Test cache invalidation
- [ ] Verificar fallback sin Redis

### Deployment
- [ ] Deploy staging
- [ ] Monitor 24h
- [ ] Validar cache hit rate >90%
- [ ] Deploy production

### Documentation
- [ ] Actualizar README con M2 config
- [ ] Crear DCT M2
- [ ] Documentar cache invalidation strategy

---

## 💰 ROI ESTIMADO

**Esfuerzo**: 4-5 horas total
- Implementación: 2-3h
- Testing: 1h
- Deployment: 1h

**Beneficio**:
- First sync: +3% slower (aceptable)
- **Subsequent syncs: 7x faster**
- Reduced Shopify API calls: 26 → 0 (en warm cache)
- Reduced API costs (si aplicable)

**Conclusión**: ROI excelente. Worth it si KB syncs son frecuentes (>1/hora).

---

## 🔮 FUTURAS MEJORAS (M3?)

Si M2 es exitoso:

1. **Cache de metafields** (actualmente no cached):
   - Fetch pages: 0.997s → 0.05s
   - Additional 20x speedup en fetch

2. **Smart invalidation**:
   - Solo invalidar locale modificado (no todos)
   - Webhook granular por locale

3. **Prefetching**:
   - Background job para warm cache
   - Proactive invalidation antes de sync

---

**Autor**: Yasmani Roque  
**Fecha**: 14 Febrero 2026  
**Estado**: Planificado - Pendiente aprobación  
**Próximo paso**: Review con equipo → Implementación

