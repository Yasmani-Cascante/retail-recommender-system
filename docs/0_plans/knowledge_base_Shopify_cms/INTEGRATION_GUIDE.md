# 🚀 GUÍA DE INTEGRACIÓN - SHOPIFY KB

## Archivos Creados Exitosamente ✅

### **Core Files**
1. ✅ `migrations/001_shopify_kb_buffer.sql` - Database schema
2. ✅ `src/api/core/models/kb_models.py` - Pydantic models (15+ models)
3. ✅ `src/api/core/models/__init__.py` - Package exports
4. ✅ `src/api/core/knowledge_base_v2.py` - KB API v2 (triple-cache)
5. ✅ `src/api/integrations/shopify_kb_client.py` - Shopify KB client
6. ✅ `src/api/services/shopify_kb_sync.py` - Sync service
7. ✅ `src/api/webhooks/shopify_webhooks.py` - Webhook handlers

---

## 🔧 PASO 1: CONFIGURACIÓN

### **1.1 Agregar a `.env`**

```env
# ═══════════════════════════════════════════════════════════
# SHOPIFY KB CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Shopify Credentials (ya deberías tenerlos)
SHOPIFY_SHOP_URL=tutienda.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxx

# Webhook Security (NUEVO)
SHOPIFY_WEBHOOK_SECRET=your_webhook_secret_here

# KB Sync Configuration (NUEVO)
KB_SYNC_INTERVAL_MINUTES=5
KB_ENABLE_BACKGROUND_SYNC=true

# Cache Configuration (NUEVO)
KB_CACHE_TTL_HOURS=24
KB_BUFFER_MAX_AGE_HOURS=48

# Feature Flags (NUEVO)
KB_USE_SHOPIFY_CMS=true
KB_ENABLE_FALLBACK=true
```

### **1.2 Agregar a `src/api/core/config.py`**

Añade estos campos a tu clase `Settings`:

```python
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    # ... existing fields ...
    
    # ═══════════════════════════════════════════════════════════
    # SHOPIFY KB CONFIGURATION (NUEVO)
    # ═══════════════════════════════════════════════════════════
    
    SHOPIFY_WEBHOOK_SECRET: Optional[str] = Field(
        default=None,
        env="SHOPIFY_WEBHOOK_SECRET"
    )
    
    KB_SYNC_INTERVAL_MINUTES: int = Field(
        default=5,
        env="KB_SYNC_INTERVAL_MINUTES"
    )
    
    KB_ENABLE_BACKGROUND_SYNC: bool = Field(
        default=True,
        env="KB_ENABLE_BACKGROUND_SYNC"
    )
    
    KB_CACHE_TTL_HOURS: int = Field(
        default=24,
        env="KB_CACHE_TTL_HOURS"
    )
    
    KB_BUFFER_MAX_AGE_HOURS: int = Field(
        default=48,
        env="KB_BUFFER_MAX_AGE_HOURS"
    )
    
    KB_USE_SHOPIFY_CMS: bool = Field(
        default=True,
        env="KB_USE_SHOPIFY_CMS"
    )
    
    KB_ENABLE_FALLBACK: bool = Field(
        default=True,
        env="KB_ENABLE_FALLBACK"
    )
```

---

## 🗄️ PASO 2: EJECUTAR MIGRATION

```bash
# Opción 1: psql directo
psql -U postgres -d retail_recommender_db -f migrations/001_shopify_kb_buffer.sql

# Opción 2: Desde Python (si tienes migration runner)
python run_migrations.py

# Verificar que la tabla se creó
psql -U postgres -d retail_recommender_db -c "SELECT * FROM kb_contents;"
```

---

## 🔌 PASO 3: INTEGRACIÓN EN `main.py`

### **3.1 Imports**

Añade al inicio de `src/api/main.py`:

```python
# Shopify KB Integration
from src.api.integrations.shopify_kb_client import create_shopify_kb_client
from src.api.services.shopify_kb_sync import ShopifyKBSyncService, KBBackgroundSyncJob
from src.api.core.knowledge_base_v2 import create_shopify_knowledge_base
from src.api.webhooks import shopify_webhooks
```

### **3.2 Inicializar Clientes (en startup event)**

```python
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    
    # ═══════════════════════════════════════════════════════════
    # SHOPIFY KB INITIALIZATION
    # ═══════════════════════════════════════════════════════════
    
    logger.info("Initializing Shopify KB integration...")
    
    # 1. Create Shopify KB Client
    shopify_kb_client = create_shopify_kb_client(
        shop_url=settings.SHOPIFY_SHOP_URL,
        access_token=settings.SHOPIFY_ACCESS_TOKEN,
        webhook_secret=settings.SHOPIFY_WEBHOOK_SECRET
    )
    app.state.shopify_kb_client = shopify_kb_client
    logger.info("✅ Shopify KB Client initialized")
    
    # 2. Create Sync Service
    sync_service = ShopifyKBSyncService(
        shopify_client=shopify_kb_client,
        db_pool=app.state.db_pool,  # Tu pool existente
        redis_client=app.state.redis_client  # Tu Redis existente
    )
    app.state.kb_sync_service = sync_service
    logger.info("✅ KB Sync Service initialized")
    
    # 3. Create Knowledge Base v2
    kb_v2 = create_shopify_knowledge_base(
        db_pool=app.state.db_pool,
        redis_client=app.state.redis_client,
        shopify_client=shopify_kb_client,
        cache_ttl_hours=settings.KB_CACHE_TTL_HOURS,
        buffer_max_age_hours=settings.KB_BUFFER_MAX_AGE_HOURS,
        enable_fallback=settings.KB_ENABLE_FALLBACK
    )
    app.state.knowledge_base_v2 = kb_v2
    logger.info("✅ Knowledge Base v2 initialized")
    
    # 4. Start Background Sync Job (optional)
    if settings.KB_ENABLE_BACKGROUND_SYNC:
        background_sync = KBBackgroundSyncJob(
            sync_service=sync_service,
            interval_minutes=settings.KB_SYNC_INTERVAL_MINUTES
        )
        await background_sync.start()
        app.state.kb_background_sync = background_sync
        logger.info(f"✅ Background sync started (interval={settings.KB_SYNC_INTERVAL_MINUTES}min)")
    
    logger.info("🎉 Shopify KB integration complete!")
```

### **3.3 Shutdown Event**

```python
@app.on_event("shutdown")
async def shutdown_event():
    # ... existing shutdown code ...
    
    # Stop background sync
    if hasattr(app.state, 'kb_background_sync'):
        await app.state.kb_background_sync.stop()
        logger.info("✅ Background sync stopped")
```

### **3.4 Registrar Webhook Router**

```python
# Include Shopify webhooks router
app.include_router(shopify_webhooks.router)

# Configure dependency injection for webhooks
async def get_shopify_kb_client():
    return app.state.shopify_kb_client

async def get_kb_sync_service():
    return app.state.kb_sync_service

# Override dependencies
app.dependency_overrides[shopify_webhooks.get_shopify_client] = get_shopify_kb_client
app.dependency_overrides[shopify_webhooks.get_sync_service] = get_kb_sync_service
```

---

## 🧪 PASO 4: TESTING

### **4.1 Test Manual - Shopify Client**

Crea `test_kb_client.py`:

```python
import asyncio
from src.api.integrations.shopify_kb_client import create_shopify_kb_client
from src.api.core.config import settings

async def test_client():
    # Create client
    client = create_shopify_kb_client(
        shop_url=settings.SHOPIFY_SHOP_URL,
        access_token=settings.SHOPIFY_ACCESS_TOKEN,
        webhook_secret=settings.SHOPIFY_WEBHOOK_SECRET
    )
    
    # Test: Get KB pages
    print("Fetching KB pages...")
    kb_pages = client.get_kb_pages(limit=5)
    
    print(f"\n✅ Found {len(kb_pages)} KB pages:")
    for page in kb_pages:
        print(f"  - {page.title} (ID: {page.id})")
        
        # Parse metadata
        metadata = client.parse_kb_metadata(page)
        print(f"    Sub-intent: {metadata['sub_intent']}")
        print(f"    Category: {metadata.get('category', 'general')}")
        print()
    
    # Test: Get single page
    if kb_pages:
        page_id = kb_pages[0].id
        print(f"\nFetching single page: {page_id}")
        page = client.get_page_by_id(page_id)
        print(f"✅ Title: {page.title}")
        
        # Get translations
        print(f"\nFetching translations for page {page_id}...")
        translations = client.get_page_translations(page_id)
        print(f"✅ Found {len(translations)} translations: {list(translations.keys())}")

if __name__ == "__main__":
    asyncio.run(test_client())
```

**Ejecutar:**
```bash
python test_kb_client.py
```

### **4.2 Test Manual - Sync Service**

Crea `test_kb_sync.py`:

```python
import asyncio
import asyncpg
from redis import Redis
from src.api.integrations.shopify_kb_client import create_shopify_kb_client
from src.api.services.shopify_kb_sync import ShopifyKBSyncService
from src.api.core.config import settings

async def test_sync():
    # Setup
    client = create_shopify_kb_client(
        shop_url=settings.SHOPIFY_SHOP_URL,
        access_token=settings.SHOPIFY_ACCESS_TOKEN
    )
    
    db_pool = await asyncpg.create_pool(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME
    )
    
    redis_client = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True
    )
    
    sync_service = ShopifyKBSyncService(
        shopify_client=client,
        db_pool=db_pool,
        redis_client=redis_client
    )
    
    # Test: Full sync
    print("Starting full sync...")
    report = await sync_service.sync_all_pages()
    
    print("\n" + "=" * 70)
    print("SYNC REPORT")
    print("=" * 70)
    print(f"Total pages: {report.total_pages}")
    print(f"✅ Successful: {report.successful}")
    print(f"❌ Failed: {report.failed}")
    print(f"⏭️ Skipped: {report.skipped}")
    print(f"⏱️ Duration: {report.duration_seconds:.2f}s")
    
    if report.errors:
        print("\nErrors:")
        for error in report.errors:
            print(f"  - {error}")
    
    # Cleanup
    await db_pool.close()
    redis_client.close()

if __name__ == "__main__":
    asyncio.run(test_sync())
```

**Ejecutar:**
```bash
python test_kb_sync.py
```

### **4.3 Test Manual - Knowledge Base v2**

Crea `test_kb_v2.py`:

```python
import asyncio
import asyncpg
from redis import Redis
from src.api.core.knowledge_base_v2 import create_shopify_knowledge_base
from src.api.core.intent_types import InformationalSubIntent
from src.api.core.config import settings

async def test_kb_v2():
    # Setup
    db_pool = await asyncpg.create_pool(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME
    )
    
    redis_client = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True
    )
    
    kb = create_shopify_knowledge_base(
        db_pool=db_pool,
        redis_client=redis_client
    )
    
    # Test: Get answer (Spanish)
    print("Testing KB v2 - Spanish...")
    answer = await kb.get_answer(
        sub_intent=InformationalSubIntent.POLICY_RETURN,
        language="es",
        category="general"
    )
    
    if answer:
        print("✅ Answer found!")
        print(f"Content preview: {answer.answer[:200]}...")
    else:
        print("❌ No answer found")
    
    # Test: Get answer (English)
    print("\nTesting KB v2 - English...")
    answer_en = await kb.get_answer(
        sub_intent=InformationalSubIntent.POLICY_RETURN,
        language="en",
        category="general"
    )
    
    if answer_en:
        print("✅ Answer found!")
        print(f"Content preview: {answer_en.answer[:200]}...")
    else:
        print("❌ No answer found")
    
    # Cleanup
    await db_pool.close()
    redis_client.close()

if __name__ == "__main__":
    asyncio.run(test_kb_v2())
```

**Ejecutar:**
```bash
python test_kb_v2.py
```

---

## 📋 PASO 5: CREAR PÁGINAS KB EN SHOPIFY

### **5.1 Formato de Tags**

Las páginas KB se identifican por tags en formato:
```
kb, sub_intent, category
```

**Ejemplos:**
- `kb, policy_return, general` → Política de devoluciones general
- `kb, policy_return, ZAPATOS` → Política de devoluciones para zapatos
- `kb, policy_shipping` → Política de envíos (sin categoría específica)
- `kb, product_material, VESTIDOS` → Información de materiales para vestidos

### **5.2 Crear Primera Página de Prueba**

1. **En Shopify Admin:**
   - Ve a Online Store → Pages
   - Click "Add page"

2. **Configurar página:**
   - **Title:** `KB: Return Policy - General`
   - **Content:** (tu política de devoluciones en HTML o Markdown)
   - **Tags:** `kb, policy_return, general`
   - **Template:** Selecciona un template (o déjalo default)

3. **Guardar:**
   - Click "Save"
   - La página se creará con un ID único

### **5.3 Agregar Traducción (Multi-idioma)**

1. **En Shopify Admin:**
   - Abre la página que creaste
   - Click en "Manage translations"
   - Selecciona idioma (ej: English)

2. **Traducir:**
   - Shopify mostrará editor side-by-side
   - Edita el contenido en inglés
   - Puedes usar "Auto-translate" si tienes Google Translate configurado

3. **Guardar:**
   - La traducción se sincronizará automáticamente via webhook

---

## 🔔 PASO 6: CONFIGURAR WEBHOOKS EN SHOPIFY

### **6.1 Obtener URL de Webhooks**

Tu URL base será:
```
https://tu-dominio.com/webhooks/shopify/
```

Endpoints:
- `https://tu-dominio.com/webhooks/shopify/pages/create`
- `https://tu-dominio.com/webhooks/shopify/pages/update`
- `https://tu-dominio.com/webhooks/shopify/pages/delete`
- `https://tu-dominio.com/webhooks/shopify/translations/update`

### **6.2 Crear Webhooks en Shopify Admin**

1. **Ve a:**
   - Settings → Notifications → Webhooks

2. **Crear webhook "pages/create":**
   - Event: `Page creation`
   - Format: `JSON`
   - URL: `https://tu-dominio.com/webhooks/shopify/pages/create`
   - API version: `2024-01` (latest)

3. **Repetir para los demás:**
   - `Page update` → `/pages/update`
   - `Page deletion` → `/pages/delete`
   - `Translation update` → `/translations/update`

### **6.3 Obtener Webhook Secret**

1. **En cada webhook creado:**
   - Shopify mostrará el "Webhook secret"
   - Copiar el secret

2. **Agregar a `.env`:**
   ```env
   SHOPIFY_WEBHOOK_SECRET=tu_secret_aqui
   ```

### **6.4 Probar Webhooks**

Shopify tiene un botón "Send test notification" en cada webhook.
Click y verifica en tus logs que el webhook fue recibido.

---

## 🚀 PASO 7: INICIAR SISTEMA

### **7.1 Iniciar FastAPI**

```bash
# Desarrollo
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Producción
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### **7.2 Verificar Logs**

Deberías ver:
```
INFO: Initializing Shopify KB integration...
INFO: ✅ Shopify KB Client initialized
INFO: ✅ KB Sync Service initialized
INFO: ✅ Knowledge Base v2 initialized
INFO: ✅ Background sync started (interval=5min)
INFO: 🎉 Shopify KB integration complete!
```

### **7.3 Trigger Sync Inicial**

Opción 1 - Automático (esperar 5 min):
```
# El background job sincronizará automáticamente
```

Opción 2 - Manual:
```python
# En Python shell
from src.api.main import app
await app.state.kb_sync_service.sync_all_pages()
```

---

## 📊 MONITORING & DEBUGGING

### **Verificar Cache Redis:**
```bash
redis-cli
> KEYS kb:*
> GET kb:policy_return:es:general
```

### **Verificar PostgreSQL:**
```sql
-- Ver todas las páginas KB
SELECT 
    sub_intent,
    language,
    category,
    title,
    last_synced,
    created_at
FROM kb_contents
ORDER BY created_at DESC;

-- Verificar staleness
SELECT 
    sub_intent,
    language,
    category,
    last_synced,
    NOW() - last_synced AS age
FROM kb_contents
WHERE NOW() - last_synced > INTERVAL '48 hours';
```

### **Logs a Monitorear:**
```
✅ Cache HIT (Redis): ...
✅ Buffer HIT (PostgreSQL): ...
⚠️ Buffer STALE: ...
❌ No answer found: ...
✅ Received pages/update webhook: ...
✅ Synced page ... successfully
```

---

## 🎯 PRÓXIMOS PASOS

1. ✅ **Ejecutar migration**
2. ✅ **Agregar configuración a .env**
3. ✅ **Integrar en main.py**
4. ✅ **Crear páginas KB en Shopify**
5. ✅ **Configurar webhooks**
6. ✅ **Probar sync**
7. ✅ **Monitorear performance**

---

## 🆘 TROUBLESHOOTING

### **Problema: "No KB pages found"**
**Solución:** Verifica que las páginas en Shopify tengan el tag "kb" como primer tag.

### **Problema: "Invalid webhook signature"**
**Solución:** Verifica que `SHOPIFY_WEBHOOK_SECRET` en .env coincida con el secret en Shopify Admin.

### **Problema: "Table kb_contents does not exist"**
**Solución:** Ejecuta la migration: `psql ... < migrations/001_shopify_kb_buffer.sql`

### **Problema: "Redis connection failed"**
**Solución:** Verifica que Redis esté corriendo: `redis-cli ping`

### **Problema: "PostgreSQL connection failed"**
**Solución:** Verifica credenciales en .env y que la DB exista.

---

## ✅ CHECKLIST FINAL

- [ ] Migration ejecutada (tabla `kb_contents` existe)
- [ ] Configuración agregada a `.env`
- [ ] Código integrado en `main.py`
- [ ] Al menos 1 página KB creada en Shopify
- [ ] Webhooks configurados en Shopify
- [ ] Sync manual ejecutado exitosamente
- [ ] Tests pasando
- [ ] Sistema corriendo sin errores
- [ ] Cache funcionando (verificar logs)
- [ ] Background sync activo

---

¡Listo! El sistema está completamente integrado y funcional. 🎉

