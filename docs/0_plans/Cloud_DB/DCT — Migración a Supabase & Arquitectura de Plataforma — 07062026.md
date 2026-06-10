# DCT — Migración a Supabase & Arquitectura de Plataforma — 07/06/2026

## Resumen Ejecutivo

Esta sesión completa la migración de la base de datos del sistema Retail Recommender v2.1.0 desde **Neon PostgreSQL** (producción) / [**localhost**](http://localhost) (desarrollo) hacia **Supabase PostgreSQL**, estableciendo los cimientos para la futura plataforma multi-app de soluciones e-commerce para Shopify.

**Estado al cierre de sesión:** Supabase activo en producción (Cloud Run). Neon pausado. Sistema funcionando al 100%.

---

## 1. Contexto Arquitectónico

### Qué NO está en PostgreSQL (hallazgo crítico)

Antes de entender la migración, es fundamental saber dónde vive cada tipo de dato en el sistema:

| Dato | Dónde vive | Por qué |
| --- | --- | --- |
| Productos Shopify | Shopify API + Redis cache | Alta frecuencia, TTL corto |
| Conversaciones MCP | Redis (TTL 1h) | Estado temporal |
| Embeddings FAISS | GCS bucket + embedding-service | Binarios de ML |
| Recomendaciones | TF-IDF en memoria + Redis | Cálculo en tiempo real |
| **Knowledge Base (KB)** | **PostgreSQL** | Persistencia, versioning |

PostgreSQL en este sistema tiene un único rol: almacenar el **Knowledge Base** — las páginas de política y ayuda sincronizadas desde Shopify CMS.

### Schema actual en producción (Supabase)

Schema `public` — 4 tablas operativas:

```
public
├── kb_contents          (20 columnas) — KB sincronizado desde Shopify (26 registros)
├── kb_content_versions  (9 columnas)  — Historial de versiones L2 (vacía en Neon/prod)
├── schema_migrations    (7 columnas)  — Audit trail de Alembic
└── alembic_version      (1 columna)   — Versión actual: 0002
```

**Lo que gestiona `kb_contents`:** Sub-intents mapeados a páginas Shopify (`policy_return`, `policy_shipping`, `product_sizing`, etc.) con contenido en Markdown por idioma (ES/EN).

---

## 2. Diseño de Schemas — Plataforma Completa

El diseño actual es la Fase 1 de una arquitectura mayor para la plataforma multi-app:

### Schema `public` (actual — migrado)

Contiene el KB del sistema Chat AI. Sin multi-tenancy todavía — sirve a una sola tienda (`ai-shoppings.myshopify.com`).

### Schema `platform` (Fase 7 — pendiente)

Gestiona la plataforma SaaS multi-tenant. Se crea cuando se inicia el desarrollo de Data Insights.

```sql
CREATE SCHEMA IF NOT EXISTS platform;

-- Cada tienda Shopify conectada = 1 tenant
CREATE TABLE platform.tenants (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_url   VARCHAR(200) NOT NULL UNIQUE,  -- ai-shoppings.myshopify.com
    shop_name  VARCHAR(200),
    plan       VARCHAR(50) NOT NULL DEFAULT 'free',
    active     BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Qué apps tiene habilitadas cada tenant
CREATE TABLE platform.tenant_apps (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES platform.tenants(id),
    app_slug  VARCHAR(50) NOT NULL,  -- 'chat_ai' | 'data_insights'
    enabled   BOOLEAN NOT NULL DEFAULT true,
    config    JSONB
);
```

### Schema `insights` (para app Data Insights — pendiente)

```sql
CREATE SCHEMA IF NOT EXISTS insights;
-- product_snapshots: snapshots periódicos de productos Shopify
-- analytics_events: interacciones de usuarios
-- reports: reportes generados por Claude
-- ai_scores: scores de análisis IA por producto
-- mat_views: vistas materializadas (se refrescan tras sync worker 02:00 UTC)
```

### Por qué NO existe un schema `shared` con productos

Durante el diseño se evaluó un schema `shared` con tablas `products`, `orders`, `customers`. **Decisión: descartado.** Los productos viven en Shopify API + Redis cache por razones de arquitectura (alta frecuencia, TTL corto, datos binarios de embeddings en GCS). Duplicarlos en PostgreSQL crearía inconsistencias sin beneficio.

---

## 3. Configuración de Conexión Supabase

### Connection Method: Session Pooler — y por qué

Supabase ofrece tres métodos de conexión:

| Método | Puerto | IPv4 | asyncpg compat | Elección |
| --- | --- | --- | --- | --- |
| Direct connection | 5432 | ❌ solo IPv6 | ✅ | ❌ Cloud Run es IPv4 |
| Transaction pooler | 6543 | ✅ | ❌ rompe prepared statements | ❌ |
| **Session pooler** | **5432** | **✅** | **✅** | **✅ elegida** |

Cloud Run (GCP us-central1) usa IPv4. Direct connection requiere IPv4 add-on ($4/mes extra). Transaction pooler opera en modo transaction — asyncpg usa prepared statements por defecto y esto falla silenciosamente.

**Session Pooler** mantiene conexión al mismo backend PostgreSQL durante la sesión, exactamente como espera `asyncpg.create_pool()`.

### Variables de entorno — Cloud Run (producción)

```bash
# Única variable de conexión (Session Pooler)
DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-1-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require

# Variables eliminadas (ya no aplican):
# DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SSL
```

### Variables de entorno — desarrollo local (.env)

```bash
# Misma URL de Supabase — entorno unificado
DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-1-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require

# Las variables individuales DB_HOST/DB_PORT/etc están comentadas
```

### Proyecto Supabase

- **Nombre:** retail-recommender-platform
- **Project ref:** `imhjtqxtumfkqdricbrf`
- **Región:** us-east-1 (AWS) — la más cercana a Cloud Run us-central1
- **Host Session Pooler:** `aws-1-us-east-1.pooler.supabase.com`
- **Plan:** Free tier (suficiente para volumen actual: 26 páginas KB)
- **Extensiones activas:** uuid-ossp, pgcrypto, vector (pgvector para embeddings futuros)

---

## 4. Cambios de Código — `main_unified_redis.py`

Todos los cambios están en el bloque de inicialización del pool PostgreSQL (~líneas 1635–1700).

### Cambio 1 — Soporte `DATABASE_URL` con fallback explícito

**Antes:** Solo leía variables individuales `DB_HOST`, `DB_PORT`, etc.

**Después:** `DATABASE_URL` tiene prioridad absoluta (igual que `alembic/env.py`). Si no está presente, lanza `EnvironmentError` con mensaje claro en lugar de un `NameError` críptico.

```python
import urllib.parse as _urlparse
_database_url_raw = os.environ.get("DATABASE_URL")
if _database_url_raw:
    _pu = _urlparse.urlparse(_database_url_raw)
    _qs = dict(_urlparse.parse_qsl(_pu.query))
    db_host_final     = _pu.hostname or settings.db_host
    db_port_final     = int(_pu.port or settings.db_port)
    db_user_final     = _urlparse.unquote(_pu.username or "") or settings.db_user
    db_password_final = _urlparse.unquote(_pu.password or "") or settings.db_password
    db_name_final     = _pu.path.lstrip("/") or settings.db_name
    db_ssl_final      = _qs.get("sslmode") in ("require", "verify-full", "verify-ca")
    db_ssl_value_final = "require" if db_ssl_final else False
    logger.info("db_config_from_DATABASE_URL", host=db_host_final, ...)
else:
    # DATABASE_URL is required — individual DB_* variables no longer supported
    raise EnvironmentError(
        "DATABASE_URL environment variable is not set. "
        "Configure it with the Supabase connection string."
    )
```

### Cambio 2 — `statement_cache_size=0` en `asyncpg.create_pool()`

**Problema:** asyncpg cachea prepared statements por defecto. Supavisor (session pooler) puede rotar la conexión al backend PostgreSQL entre requests — el statement cacheado apunta a una conexión que ya no existe → error silencioso en producción.

```python
db_pool = await asyncpg.create_pool(
    host=db_host_final,
    ...otros params...
    statement_cache_size=0,          # REQUERIDO para Supabase
    max_cached_statement_lifetime=0, # REQUERIDO para Supabase
)
```

### Cambio 3 — Limpieza de comentarios y fix de NameError

- **Eliminados:** 23 líneas de comentarios obsoletos específicos de Neon (SSL/Pydantic explanation)
- **Corregido:** `NameError` — el `logger.info` posterior al bloque if/else referenciaba `db_ssl_env` que solo existía en la rama `else`. Al tomar el path `DATABASE_URL`, el sistema lanzaría `NameError: name 'db_ssl_env' is not defined`.
- **Añadidos:** Comentarios concisos y precisos sobre la nueva lógica

---

## 5. Fases de Migración

### ✅ Fase 0 — Pre-migración

- Verificada versión Alembic local: `0002 (head)`
- Conteo de datos: `kb_contents=26`, `kb_content_versions=26` (local), `last_sync=2026-05-31`
- Backups creados: `backup_pre_supabase_.sql` (local) y `backup_neon_pre_supabase_20260607.sql` (Neon)

### ✅ Fase 1 — Crear Proyecto Supabase

- Proyecto `retail-recommender-platform` creado en us-east-1
- Extensiones habilitadas: `uuid-ossp`, `pgcrypto`, `vector`
- Session Pooler seleccionado (ver sección 3)

### ✅ Fase 2 — Aplicar Schema via Alembic

- `DATABASE_URL` configurada en `.env` apuntando a Supabase
- `alembic upgrade head` aplicó migrations `0001` y `0002` correctamente
- Verificación en Supabase SQL Editor: 4 tablas creadas con columnas correctas
- **Nota:** Security Advisor mostró 4 warnings "RLS Disabled in Public" — esperado y no bloqueante. FastAPI conecta como service role (postgres user) que bypasses RLS. Resolver en Fase 7 con policies por tenant.

### ✅ Fase 3 — Migrar Datos desde Neon

- Dump data-only desde Neon: `pg_dump --data-only --table=kb_contents --table=kb_content_versions`
- **Hallazgo:** Neon producción tiene `kb_content_versions` vacía (0 filas). Los 26 registros en la tabla local son de desarrollo.
- Import a Supabase: `kb_contents=26` ✅, `kb_content_versions=0` ✅ (correcto — coincide con Neon prod)
- `last_sync=2026-06-07` (KB sync corrió en Neon esa mañana antes del dump)

### ✅ Fase 4 — Cambios de Código FastAPI

Tres cambios aplicados a `src/api/main_unified_redis.py` (ver sección 4).

Archivos generados para referencia:

- `main_unified_redis_patched.py` — limpieza de comentarios + fix NameError
- `main_unified_redis_final.py` — eliminación del bloque backward-compat

### ✅ Fase 5 — Testing Local

- Startup: `db_config_from_DATABASE_URL` en logs → `PostgreSQL pool created and tested successfully`
- KB Answer ES: `200 OK`, `layer=postgresql`, `response_time_ms=<10`, `is_fresh=True`
- KB Answer EN: `200 OK`, `layer=postgresql`, `response_time_ms=<10`, `is_fresh=True`
- KB Manual Sync: `success_rate=100.0`, 13 páginas, 19.68s
- MCP Conversation `busco un vestido`: `200 OK`, 8 recomendaciones CHF, Redis session management OK

### ✅ Fase 6 — Deploy Cloud Run

```bash
gcloud run services update retail-recommender-fixed \
  --region us-central1 \
  --update-env-vars "DATABASE_URL=postgresql://..."
gcloud run services update retail-recommender-fixed \
  --region us-central1 \
  --remove-env-vars "DB_HOST,DB_PORT,DB_USER,DB_PASSWORD,DB_NAME,DB_SSL"
```

Verificación en GCP Logs Explorer:

- `db_config_from_DATABASE_URL` con `host=aws-1-us-east-1.pooler.supabase.com`, `ssl=true` — en AMBAS instancias (revision `retail-recommender-00203-hbq`)
- `PostgreSQL pool created and tested successfully` — en ambas instancias
- KB queries en producción: `layer=postgresql`, `200 OK`, `<10ms`

---

## 6. Fases Pendientes

### Fase 7 — Platform Foundation (ejecutar al iniciar Data Insights)

Crear el schema `platform` con la infraestructura multi-tenant. No bloquea ninguna funcionalidad actual.

**Alembic migration `0003`:**

```sql
CREATE SCHEMA IF NOT EXISTS platform;

CREATE TABLE platform.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_url VARCHAR(200) NOT NULL UNIQUE,
    shop_name VARCHAR(200),
    plan VARCHAR(50) NOT NULL DEFAULT 'free',
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE platform.tenant_apps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES platform.tenants(id) ON DELETE CASCADE,
    app_slug VARCHAR(50) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    config JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tenant inicial (tienda actual)
INSERT INTO platform.tenants (shop_url, shop_name, plan)
VALUES ('ai-shoppings.myshopify.com', 'AI Shoppings', 'pro')
ON CONFLICT (shop_url) DO NOTHING;
```

**✅ RLS activado en tablas existentes** (resuelto el 07/06/2026):

Ejecutado directamente en Supabase SQL Editor. Los 4 errores del Security Advisor desaparecieron.

```sql
-- Ejecutado y validado:
ALTER TABLE public.alembic_version     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schema_migrations   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.kb_contents         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.kb_content_versions ENABLE ROW LEVEL SECURITY;
-- Sin policies por ahora: alembic_version y schema_migrations nunca deben
-- ser accesibles vía PostgREST. Las policies por tenant para kb_contents
-- se añadirán en Fase 7 junto con el schema platform.
```

Estado Security Advisor post-ejecución: **0 errors**, 0 warning, 4 info (esperado).

Los 4 items "RLS Enabled No Policy" en Info son correctos por diseño: el service role (FastAPI) bypasses RLS automáticamente. Las policies se añadirán en Fase 7.

**⚠️ Warning pendiente — Function Search Path Mutable (Solucionado, ya no hay warnings)**

El Security Advisor detecta que `public.update_kb_contents_updated_at` (trigger function creada en migration 0001) no tiene `search_path` explícito. Sin él, un usuario con permisos podría manipular el search_path para ejecutar objetos distintos a los esperados.

Fix listo para ejecutar en SQL Editor:

```sql
CREATE OR REPLACE FUNCTION public.update_kb_contents_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;
```

Nota: `SET search_path = ''` obliga a rutas calificadas. `NOW()` es built-in y no requiere calificación. La lógica del trigger no cambia.

### Neon — Limpieza pendiente

- **Pausado:** sí (inmediato tras migración, sin necesidad de 72h porque no hay clientes reales)
- **Eliminar definitivamente:** esperar 2-4 semanas por si se necesita consultar datos históricos
- URL de referencia para consultas históricas si es necesario: `ep-blue-firefly-ajafeedi.c-3.us-east-2.aws.neon.tech`

### Claude API — Créditos (hallazgo de la sesión)

En los logs de Cloud Run se detectó:

```
Claude API warm-up failed: BadRequestError: 400 — 'Your credit...'
```

El sistema funciona porque el path de recomendaciones usa LFM vía OpenRouter. Pero cualquier llamada directa a Anthropic API fallará. Verificar y recargar créditos en el dashboard de Anthropic.

---

## 7. Guía de Troubleshooting

### Si el sistema no conecta a Supabase al iniciar

1. Verificar que `DATABASE_URL` está seteada en el entorno (Cloud Run env vars o `.env` local)
2. El error será explícito: `EnvironmentError: DATABASE_URL environment variable is not set`
3. Si el error es de conexión, verificar que la URL usa `aws-1-us-east-1.pooler.supabase.com:5432` (Session Pooler) y NO el puerto 6543 ni el host directo `db.[ref].supabase.co`

### Si hay errores de prepared statements con asyncpg

Verificar que `asyncpg.create_pool()` tiene los parámetros:

```python
statement_cache_size=0,
max_cached_statement_lifetime=0,
```

Sin estos, el Supavisor session pooler puede causar errores silenciosos al rotar conexiones.

### Si los logs muestran el path equivocado

El log `db_config_from_DATABASE_URL` en el startup confirma que se tomó el path correcto. Campos a verificar: `host`, `port`, `database`, `ssl`. Si no aparece este log, `DATABASE_URL` no está presente en el entorno.

### Si Alembic no conecta

`alembic/env.py` también usa `DATABASE_URL`. Verificar que está en `.env`. La URL debe incluir `?sslmode=require`.

---

## 8. Decisiones Técnicas Registradas

**Por qué Supabase sobre Neon:**

Supabase tiene Auth + RLS integrado (crítico para SaaS multi-tenant), pgvector nativo, SDK oficial para Next.js 14, y Storage para documentos. El overhead de migración fue mínimo (2 tablas + cambio de connection string).

**Por qué `DATABASE_URL` toma prioridad sobre `DB_*` individuales:**

Consistencia con `alembic/env.py` que ya usaba este patrón. Una sola variable es más segura en Cloud Run Secret Manager. Compatible con todos los providers de PostgreSQL (Neon, Supabase, RDS) sin cambios de código.

**Por qué se eliminó el bloque `else` backward-compatible:**

Todos los entornos usan `DATABASE_URL`. El bloque generaba código muerto y una falsa sensación de seguridad (si `DATABASE_URL` desaparecía, caía a `settings.*` defaults que apuntan a [localhost](http://localhost)). El reemplazo por `EnvironmentError` explícito es más honesto y más fácil de diagnosticar.

**Por qué `DB_SSL=true` fue eliminada:**

Redundante cuando `DATABASE_URL` está presente. SSL se configura via `?sslmode=require` en la URL. La variable solo se leía en el bloque `else` que ya no existe.

---

## 9. Estado de Infraestructura al Cierre

| Componente | Estado | Notas |
| --- | --- | --- |
| Supabase (producción) | ✅ Activo | retail-recommender-platform, us-east-1 |
| Cloud Run (FastAPI) | ✅ Activo | revision 00203-hbq, DATABASE_URL configurada |
| Redis (RedisLabs) | ✅ Activo | sin cambios en esta sesión |
| Neon | ⏸️ Pausado | backup disponible, eliminar en 2-4 semanas |
| Embedding Service | ✅ Activo | sin cambios en esta sesión |
| Claude API | ⚠️ Créditos | verificar y recargar |

---

## 10. Referencias

- **Supabase Dashboard:** [https://supabase.com/dashboard/project/imhjtqxtumfkqdricbrf](https://supabase.com/dashboard/project/imhjtqxtumfkqdricbrf)
- **Cloud Run:** [https://console.cloud.google.com/run/detail/us-central1/retail-recommender-fixed](https://console.cloud.google.com/run/detail/us-central1/retail-recommender-fixed)
- **Alembic migrations:** `retail-recommender-system/alembic/versions/`
- **Archivo modificado:** `src/api/main_unified_redis.py` (~líneas 1635–1700)
- **Backup Neon:** `backup_neon_pre_supabase_20260607.sql` (raíz del proyecto)