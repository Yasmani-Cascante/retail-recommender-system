# Plan de Migración a Supabase — Retail Recommender Platform
**Fecha:** 2026-06-07  
**Basado en:** Inspección directa del código (`main_unified_redis.py`, `alembic/`, `.env`, `migrations/`)  
**Estado:** Borrador para revisión

---

## 1. Re-evaluación de la Propuesta Original

### Qué cambió después de leer el código

La propuesta inicial de la sesión anterior tenía **errores conceptuales** que el código corrige:

| Lo que propuse | Lo que el código muestra | Conclusión |
|---|---|---|
| Schema `shared` con `products`, `orders`, `customers` | Los productos viven en Shopify API + Redis cache. No hay tabla de products en PostgreSQL. | ❌ Ese schema **no aplica** en esta arquitectura |
| Schema `chat` con `conversations`, `messages` | Las conversaciones viven en Redis (`CONVERSATION_CACHE_TTL=3600`). No hay tabla de conversaciones en DB. | ❌ Ese schema **no aplica** |
| Migración compleja de muchas tablas | Solo existen 2 tablas operativas: `kb_contents` + `kb_content_versions` | ✅ La migración es **mucho más simple** |
| Supabase vs Neon como decisión mayor | `asyncpg.create_pool()` usa host/port/user/password — mismo patrón que Neon. Cambio mínimo de código. | ✅ La migración de conexión es **trivial** |

### Estado actual real del sistema

```
PostgreSQL (actual)
├── kb_contents           ← Knowledge Base (páginas de Shopify CMS)
├── kb_content_versions   ← Historial de versiones (L2 Content Versioning)
├── schema_migrations     ← Audit trail de Alembic
└── alembic_version       ← Tracking de migraciones
```

**Los productos, conversaciones, recomendaciones y embeddings NO están en PostgreSQL.** Están en:
- Productos: Shopify API + Redis cache
- Conversaciones: Redis (TTL 1 hora)
- Embeddings FAISS: GCS bucket + embedding-service (Cloud Run)
- Recomendaciones: TF-IDF en memoria + Redis

### Schema design corregido para la plataforma

```
Supabase PostgreSQL
├── public schema (migrado desde estado actual)
│   ├── kb_contents           ← existente
│   ├── kb_content_versions   ← existente
│   ├── schema_migrations     ← existente
│   └── alembic_version       ← existente
│
├── platform schema (NUEVO — Phase 2)
│   ├── tenants               ← cada tienda Shopify = 1 tenant
│   ├── tenant_apps           ← qué apps tiene cada tenant
│   ├── billing               ← subscripción e info de pago
│   └── api_keys              ← keys por tenant (reemplaza API_KEY hardcoded)
│
└── insights schema (NUEVO — Phase 3, cuando se construya Data Insights)
    ├── product_snapshots     ← snapshots periódicos de productos Shopify
    ├── analytics_events      ← interacciones de usuarios
    ├── reports               ← reportes generados
    └── ai_scores             ← scores de Claude por producto
```

---

## 2. Bug Crítico Identificado: asyncpg + Supabase

### El problema

El código actual en `main_unified_redis.py` (línea 1674):

```python
# ACTUAL — falta statement_cache_size
db_pool = await asyncpg.create_pool(
    host=db_host_final,
    port=db_port_final,
    user=db_user_final,
    password=db_password_final,
    database=db_name_final,
    ssl=db_ssl_value_final,
    min_size=5,
    max_size=20,
    command_timeout=60
    # ❌ FALTA: statement_cache_size=0
)
```

Supabase utiliza **Supavisor** (connection pooler) en modo transaction. En ese modo, las **prepared statements** de PostgreSQL no funcionan porque el pool no garantiza que el mismo backend sirva la misma sesión. asyncpg usa prepared statements por defecto y esto causa errores silenciosos o crashes al usar el pooler.

### La solución (requerida antes del go-live)

```python
# CORRECTO para Supabase
db_pool = await asyncpg.create_pool(
    host=db_host_final,
    port=db_port_final,
    user=db_user_final,
    password=db_password_final,
    database=db_name_final,
    ssl=db_ssl_value_final,
    min_size=5,
    max_size=20,
    command_timeout=60,
    statement_cache_size=0,          # ← REQUERIDO para Supabase
    max_cached_statement_lifetime=0  # ← REQUERIDO para Supabase
)
```

**Nota:** Si se usa la **conexión directa** de Supabase (puerto 5432, `db.{ref}.supabase.co`) en vez del pooler (puerto 6543), `statement_cache_size=0` no es estrictamente obligatorio. Sin embargo, es buena práctica incluirlo para compatibilidad futura con el pooler.

### Bug adicional: main_unified_redis.py no soporta DATABASE_URL

`alembic/env.py` sí soporta `DATABASE_URL` como variable de entorno (toma prioridad sobre `DB_*` individuales). Pero `main_unified_redis.py` NO lo soporta — solo lee `DB_HOST`, `DB_PORT`, etc.

Esto es inconsistente. Si se configura `DATABASE_URL` en Cloud Run (como se hizo para Neon), Alembic funcionaría pero el servidor FastAPI no.

**Solución:** Agregar soporte de `DATABASE_URL` a `main_unified_redis.py` en la misma sección de inicialización del pool.

---

## 3. Pregunta Pendiente (Requerida Antes de Ejecutar)

**¿Cuál es el estado actual de la DB en producción (Cloud Run)?**

El `.env` local apunta a `localhost:5432/retail_recommender_db`.  
El DCT `DCT_Neon_Migration_Closure_04032026.docx` documenta que la migración a Neon se completó.  
La URL de Neon está **comentada** en `.env`: `# DATABASE_URL=postgresql://neondb_owner:npg_FUx2AiePG5yp@ep-blue-firefly...`

**Necesito confirmar:**
1. ¿Las Cloud Run env vars actuales apuntan a Neon o a otro lugar?
2. ¿Cuántos registros tiene `kb_contents` en producción? (para saber qué data migrar)
3. ¿Qué Alembic version está en producción? (`alembic current` contra Neon)

Si producción está en Neon: migración = Neon → Supabase  
Si producción está en local/Docker: migración = local PostgreSQL → Supabase

---

## 4. Plan de Migración Detallado

### Fase 0 — Pre-migración (Día 1 AM, 1-2 horas)

**Objetivo:** Confirmar estado actual, crear backups, verificar datos.

```powershell
# 1. Verificar versión de Alembic en la DB local
alembic current

# 2. Contar datos actuales
psql -h localhost -U postgres -d retail_recommender_db -c "
SELECT 
  (SELECT COUNT(*) FROM kb_contents) AS kb_contents_rows,
  (SELECT COUNT(*) FROM kb_content_versions) AS kb_versions_rows,
  (SELECT MAX(last_synced) FROM kb_contents) AS last_sync;
"

# 3. Crear backup completo de la DB local
pg_dump -h localhost -U postgres -d retail_recommender_db \
  --no-owner --no-acl \
  -f backup_pre_supabase_$(date +%Y%m%d).sql

# 4. Si producción está en Neon, hacer el mismo backup de Neon
pg_dump "postgresql://neondb_owner:npg_FUx2AiePG5yp@ep-blue-firefly-ajafeedi.c-3.us-east-2.aws.neon.tech/neondb?sslmode=require" \
  --no-owner --no-acl \
  -f backup_neon_pre_supabase_$(date +%Y%m%d).sql
```

**Criterio de paso:** Backup exitoso, row counts conocidos.

---

### Fase 1 — Crear Proyecto Supabase (Día 1 PM, 30 min)

**Objetivo:** Configurar el proyecto Supabase con las extensiones correctas.

**Pasos:**
1. Ir a [supabase.com/dashboard](https://supabase.com/dashboard) → New Project
2. **Nombre:** `retail-recommender-platform`
3. **Región:** `us-east-1` (AWS) — la más cercana a Cloud Run `us-central1`
4. **Password:** Generar contraseña fuerte y guardar en 1Password/gestor
5. Plan: Free tier para comenzar (migrar a Pro cuando se active Data Insights)

**Habilitar extensiones** (desde Dashboard → Database → Extensions):
```sql
-- Correr en el SQL Editor de Supabase Dashboard
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- UUIDs
CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- gen_random_uuid() (ya existe en PG16)
CREATE EXTENSION IF NOT EXISTS "vector";      -- pgvector para embeddings futuros
```

**Obtener connection strings** (Dashboard → Settings → Database):
- Direct connection: `postgresql://postgres.[ref]:[password]@db.[ref].supabase.co:5432/postgres`
- Anotar `[ref]` (Project Reference ID)

---

### Fase 2 — Aplicar Schema vía Alembic (Día 1 PM, 30 min)

**Objetivo:** Crear las tablas en Supabase usando las migraciones existentes.

**Ventaja:** No necesitamos `pg_dump --schema-only`. Ya tenemos Alembic con las migraciones exactas.

```powershell
# 1. Agregar DATABASE_URL al .env temporalmente para Alembic
# Editar .env y DESCOMENTAR/MODIFICAR:
DATABASE_URL=postgresql://postgres.[ref]:[password]@db.[ref].supabase.co:5432/postgres?sslmode=require

# 2. Verificar que Alembic ve la DB de Supabase
alembic current  # Debe mostrar "head (empty)" o error de tabla inexistente

# 3. Aplicar todas las migraciones
alembic upgrade head

# 4. Verificar que las tablas se crearon
psql "postgresql://postgres.[ref]:[password]@db.[ref].supabase.co:5432/postgres?sslmode=require" -c "
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
"
# Esperado: alembic_version, kb_content_versions, kb_contents, schema_migrations
```

**Criterio de paso:** 4 tablas creadas, `alembic current` muestra `0002`.

---

### Fase 3 — Migrar Datos (Día 1 PM, 15 min)

**Objetivo:** Copiar los datos de `kb_contents` y `kb_content_versions` a Supabase.

**Si la DB de origen es local:**
```powershell
# Export data only (schema ya existe por Alembic)
pg_dump -h localhost -U postgres -d retail_recommender_db \
  --data-only \
  --no-owner \
  --table=kb_contents \
  --table=kb_content_versions \
  --table=schema_migrations \
  -f data_only_$(date +%Y%m%d).sql

# Import a Supabase
psql "postgresql://postgres.[ref]:[password]@db.[ref].supabase.co:5432/postgres?sslmode=require" \
  -f data_only_$(date +%Y%m%d).sql
```

**Si la DB de origen es Neon:**
```powershell
# Export desde Neon
pg_dump "postgresql://neondb_owner:npg_FUx2AiePG5yp@ep-blue-firefly-ajafeedi.c-3.us-east-2.aws.neon.tech/neondb?sslmode=require" \
  --data-only \
  --no-owner \
  --table=kb_contents \
  --table=kb_content_versions \
  --table=schema_migrations \
  -f data_neon_$(date +%Y%m%d).sql

# Import a Supabase
psql "postgresql://postgres.[ref]:[password]@db.[ref].supabase.co:5432/postgres?sslmode=require" \
  -f data_neon_$(date +%Y%m%d).sql
```

**Verificación:**
```sql
-- Correr en Supabase SQL Editor
SELECT 
  (SELECT COUNT(*) FROM kb_contents) AS kb_contents_rows,
  (SELECT COUNT(*) FROM kb_content_versions) AS kb_versions_rows,
  (SELECT MAX(last_synced) FROM kb_contents) AS last_sync;
-- Debe coincidir con los counts de la Fase 0
```

**Criterio de paso:** Row counts coinciden con el backup de Fase 0.

---

### Fase 4 — Actualizar Código FastAPI (Día 2 AM, 2-3 horas)

**Objetivo:** Aplicar los cambios mínimos requeridos al código.

#### 4.1 — Fix crítico: `asyncpg.create_pool()` en `main_unified_redis.py`

Línea ~1674. Cambio exacto:

```python
# ANTES (líneas 1674-1683)
db_pool = await asyncpg.create_pool(
    host=db_host_final,
    port=db_port_final,
    user=db_user_final,
    password=db_password_final,
    database=db_name_final,
    ssl=db_ssl_value_final,
    min_size=5,
    max_size=20,
    command_timeout=60
)

# DESPUÉS
db_pool = await asyncpg.create_pool(
    host=db_host_final,
    port=db_port_final,
    user=db_user_final,
    password=db_password_final,
    database=db_name_final,
    ssl=db_ssl_value_final,
    min_size=5,
    max_size=20,
    command_timeout=60,
    # ✅ Requerido para Supabase: desactiva prepared statements cacheados
    # que son incompatibles con el connection pooler (Supavisor) de Supabase.
    # Impacto de performance: despreciable para nuestro volumen (26 páginas KB).
    statement_cache_size=0,
    max_cached_statement_lifetime=0
)
```

#### 4.2 — Mejora: Soporte de `DATABASE_URL` en `main_unified_redis.py`

Agregar parsing de `DATABASE_URL` para consistencia con `alembic/env.py`. En el bloque de lectura de variables DB (~línea 1658):

```python
# DESPUÉS de las líneas existentes de db_host_final, db_port_final, etc.
# Agregar soporte de DATABASE_URL como override completo:

_database_url_raw = os.environ.get("DATABASE_URL")
if _database_url_raw:
    # DATABASE_URL tiene prioridad absoluta (mismo comportamiento que alembic/env.py)
    # Parsear host, port, user, password, database desde la URL
    import urllib.parse as _urlparse
    _parsed = _urlparse.urlparse(_database_url_raw)
    db_host_final     = _parsed.hostname or db_host_final
    db_port_final     = _parsed.port or db_port_final
    db_user_final     = _urlparse.unquote(_parsed.username or "") or db_user_final
    db_password_final = _urlparse.unquote(_parsed.password or "") or db_password_final
    db_name_final     = _parsed.path.lstrip("/") or db_name_final
    # SSL: si la URL contiene sslmode=require, activar SSL
    _qs = dict(_urlparse.parse_qsl(_parsed.query))
    if _qs.get("sslmode") in ("require", "verify-full", "verify-ca"):
        db_ssl_value_final = "require"
    logger.info(
        "db_config_from_DATABASE_URL",
        host=db_host_final,
        port=db_port_final,
        database=db_name_final
    )
```

#### 4.3 — Actualizar `alembic.ini` y `.env`

Actualizar `.env` con la nueva configuración de Supabase:

```bash
# === DB LOCAL (desarrollo) ===
# Comentar las líneas de localhost:
# DB_HOST=localhost
# DB_PORT=5432
# DB_USER=postgres
# DB_PASSWORD=admin
# DB_NAME=retail_recommender_db

# === SUPABASE (desarrollo y producción) ===
DATABASE_URL=postgresql://postgres.[ref]:[password]@db.[ref].supabase.co:5432/postgres?sslmode=require
DB_SSL=true
```

#### 4.4 — Actualizar `requirements.txt` / `requirements.cloudrun.txt`

No hay cambios de dependencias. `asyncpg` ya está instalado. `supabase-py` NO es necesario — continuamos usando asyncpg directamente, que es lo correcto para una API con queries SQL explícitas.

---

### Fase 5 — Testing Local (Día 2 PM, 1-2 horas)

**Objetivo:** Verificar que el sistema completo funciona contra Supabase local.

```powershell
# 1. Iniciar el servidor con la nueva configuración
python src/api/main_unified_redis.py

# 2. Verificar log de startup — buscar estas líneas:
# ✅ PostgreSQL pool created and tested successfully
# (NO debe aparecer: ❌ PostgreSQL connection failed)

# 3. Test del endpoint KB
curl -X GET "http://localhost:8000/api/kb/answer" \
  -H "X-API-Key: 2fed9999056fab6dac5654238f0cae1c" \
  -H "Content-Type: application/json" \
  -d '{"sub_intent": "policy_return", "language": "es"}'

# 4. Verificar que la sincronización KB funciona
curl -X POST "http://localhost:8000/api/kb/sync/manual" \
  -H "X-API-Key: 2fed9999056fab6dac5654238f0cae1c"

# 5. Test del sistema de chat MCP completo
curl -X POST "http://localhost:8000/v1/mcp/chat" \
  -H "X-API-Key: 2fed9999056fab6dac5654238f0cae1c" \
  -H "Content-Type: application/json" \
  -d '{"message": "busco un vestido", "session_id": "test-001", "market": "CL"}'
```

**Criterio de paso:** Todos los endpoints responden correctamente y la DB de Supabase recibe escrituras.

---

### Fase 6 — Deploy a Cloud Run (Día 3, 1 hora)

**Objetivo:** Actualizar las variables de entorno en producción.

```powershell
# Actualizar env vars en Cloud Run
gcloud run services update retail-recommender \
  --region us-central1 \
  --update-env-vars "DATABASE_URL=postgresql://postgres.[ref]:[password]@db.[ref].supabase.co:5432/postgres?sslmode=require" \
  --update-env-vars "DB_SSL=true" \
  --update-env-vars "DB_HOST=" \
  --update-env-vars "DB_PORT=" \
  --update-env-vars "DB_USER=" \
  --update-env-vars "DB_PASSWORD=" \
  --update-env-vars "DB_NAME="

# Verificar el deploy
gcloud run services describe retail-recommender --region us-central1 | grep -A5 "DATABASE_URL"
```

**Smoke test post-deploy:**
```powershell
$BASE_URL = "https://retail-recommender-fixed-178362262166.us-central1.run.app"

# Health check
curl "$BASE_URL/health"

# KB answer
curl -X GET "$BASE_URL/api/kb/answer?sub_intent=policy_return&language=es" \
  -H "X-API-Key: 2fed9999056fab6dac5654238f0cae1c"
```

**Criterio de paso:** Health check retorna `{"postgres": "connected", "db_type": "supabase"}` (o similar).

---

### Fase 7 — Platform Foundation (Separado, cuando se construya Data Insights)

**Objetivo:** Agregar las tablas de plataforma para multi-tenancy.

Esta fase es INDEPENDIENTE de la migración de base de datos. No bloquea el go-live de la migración. Se ejecuta cuando estén listos para construir Data Insights.

**Migration 0003 (Alembic):**
```sql
-- Schema para gestión de plataforma multi-tenant
CREATE SCHEMA IF NOT EXISTS platform;

CREATE TABLE IF NOT EXISTS platform.tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_url    VARCHAR(200) NOT NULL UNIQUE,  -- ai-shoppings.myshopify.com
    shop_name   VARCHAR(200),
    plan        VARCHAR(50)  NOT NULL DEFAULT 'free',
    active      BOOLEAN      NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS platform.tenant_apps (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES platform.tenants(id) ON DELETE CASCADE,
    app_slug    VARCHAR(50)  NOT NULL,  -- 'chat_ai', 'data_insights'
    enabled     BOOLEAN      NOT NULL DEFAULT true,
    config      JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_apps_tenant_id 
    ON platform.tenant_apps(tenant_id);

-- Insertar el tenant actual (única tienda en producción)
INSERT INTO platform.tenants (shop_url, shop_name, plan)
VALUES ('ai-shoppings.myshopify.com', 'AI Shoppings', 'pro')
ON CONFLICT (shop_url) DO NOTHING;
```

---

## 5. Resumen de Cambios de Código

| Archivo | Cambio | Prioridad |
|---|---|---|
| `src/api/main_unified_redis.py` | Agregar `statement_cache_size=0` a `asyncpg.create_pool()` | 🔴 CRÍTICO — sin esto, Supabase puede fallar |
| `src/api/main_unified_redis.py` | Agregar soporte `DATABASE_URL` parsing | 🟡 IMPORTANTE — consistencia con Alembic |
| `.env` | Cambiar a `DATABASE_URL` de Supabase | 🔴 CRÍTICO — nueva config |
| `alembic.ini` | No cambia — ya usa env var `DATABASE_URL` | ✅ Ya correcto |
| `requirements.txt` | No cambia — asyncpg ya instalado | ✅ Sin cambios |

---

## 6. Rollback Plan

Si algo falla después de Phase 6:

```powershell
# Revertir a Neon (o local) en segundos
gcloud run services update retail-recommender \
  --region us-central1 \
  --update-env-vars "DATABASE_URL=postgresql://neondb_owner:npg_FUx2AiePG5yp@ep-blue-firefly-ajafeedi.c-3.us-east-2.aws.neon.tech/neondb?sslmode=require"
```

Tiempo de rollback: ~2 minutos (un solo comando).  
La Neon DB no se toca durante la migración — permanece como fallback hasta que Supabase esté validado en producción durante 72 horas.

---

## 7. Timeline Estimado

| Fase | Día | Duración | Responsable |
|---|---|---|---|
| 0 — Pre-migración + Backups | Día 1 AM | 1-2h | Dev |
| 1 — Crear proyecto Supabase | Día 1 AM | 30 min | Dev |
| 2 — Aplicar schema (Alembic) | Día 1 PM | 30 min | Dev |
| 3 — Migrar datos | Día 1 PM | 15 min | Dev |
| 4 — Actualizar código | Día 2 AM | 2-3h | Dev |
| 5 — Testing local | Día 2 PM | 1-2h | Dev |
| 6 — Deploy Cloud Run | Día 3 AM | 1h | Dev |
| **Validación 72h en prod** | Días 3-6 | Monitoring | Todos |
| 7 — Platform Foundation | TBD (Data Insights) | Semana separada | Dev |

**Total: 2-3 días de desarrollo activo + 72h de observación en producción.**

---

## 8. Decisiones Pendientes (Preguntas para el Usuario)

Antes de comenzar la ejecución, confirmar:

1. **¿Cuál es el estado de la DB de producción?**
   - ¿Cloud Run apunta a Neon actualmente?
   - ¿Cuántos registros hay en `kb_contents` en producción?
   
2. **¿Queremos ventana de mantenimiento?**
   - El sync KB corre a las 02:00 UTC. ¿Hacemos la migración justo después de ese ciclo para datos frescos?
   
3. **¿Qué región de Supabase prefieren?**
   - Recomendación: `us-east-1` (más cercana a Cloud Run `us-central1`)
   - Alternativa: `eu-west-1` si el equipo está en Europa (latencia de gestión)
   
4. **¿Comenzamos con Free tier o Pro?**
   - Free tier: 500 MB, 2 vCPUs — suficiente para la KB (26 páginas)
   - Pro ($25/mes): backups automáticos, más connections, más RAM
   - Recomendación: **Pro** para producción (backups automáticos son críticos)

---

*Generado desde inspección directa del código. Versión 1.0 para revisión del equipo.*
