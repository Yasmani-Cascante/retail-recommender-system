**RETAIL RECOMMENDER SYSTEM**

Documento Técnico de Cierre de Fase

**L2: Content Versioning**

Eliminación de Escrituras Fantasma mediante SHA256

  -----------------------------------------------------------------------
  **Campo**              **Valor**
  ---------------------- ------------------------------------------------
  Versión del sistema    v2.1.0

  Fase                   L2 --- Content Versioning

  Estado                 ✅ COMPLETADA Y VALIDADA

  Fecha de cierre        02 de Marzo de 2026

  Fase anterior          M5 --- Alembic Migrations

  Siguiente fase         L3 / M4 según prioridad del roadmap

  Migration aplicada     0002_l2_content_versioning

  Tests PASSED           62 / 62 (100%)
  -----------------------------------------------------------------------

> **1. Resumen Ejecutivo**
>
> **✅ FASE VALIDADA --- L2 Content Versioning**
>
> 62/62 tests PASSED · 26/26 registros backfilled · 0 NULL restantes ·
> 26 hashes únicos

La fase L2 implementa un sistema de detección de cambios de contenido
basado en hashing SHA256 dentro del pipeline de sincronización Shopify →
PostgreSQL del Knowledge Base (KB). Su objetivo principal es eliminar
las escrituras fantasma: actualizaciones innecesarias en la base de
datos que ocurren cuando el contenido de una página de Shopify no ha
cambiado entre ciclos de sincronización.

Antes de L2, cada ciclo de sync ejecutaba un INSERT...ON CONFLICT DO
UPDATE sin importar si el contenido era idéntico al ya almacenado. Con
26 registros y ciclos cada 5 minutos, esto generaba hasta 7.488
escrituras innecesarias por día, incrementando updated_at
artificialmente e invalidando el caché Redis sin razón real.

L2 resuelve esto con un mecanismo de tres pasos: calcular el SHA256 del
Markdown entrante, compararlo con el hash almacenado, y solo escribir si
hay diferencia real. Como beneficio adicional, archiva el historial de
versiones anteriores en una tabla dedicada, sentando las bases para L4
(ML Content Optimization).

> **2. Problema que Resuelve**

**2.1 El Ciclo de Sincronización Pre-L2**

El sistema ejecuta un ciclo de sincronización completo cada 5 minutos
(KBBackgroundSyncJob). En cada ciclo, para cada una de las 26 páginas
del KB en Shopify, el sistema ejecutaba:

> INSERT INTO kb_contents (sub_intent, language, content, \...) VALUES
> (\$1, \$2, \$3, \...) ON CONFLICT (sub_intent, language,
> COALESCE(category, \'general\')) DO UPDATE SET content =
> EXCLUDED.content, updated_at = NOW(), \-- ← Siempre se actualiza
> last_synced = NOW()

Este patrón funciona correctamente pero tiene un defecto: es ciego al
contenido. Si la página de Shopify no cambió, el sistema igualmente
ejecuta el UPDATE, tocando updated_at e invalidando el caché Redis
innecesariamente.

**2.2 Impacto Cuantificado**

  -----------------------------------------------------------------------
  **Métrica**              **Pre-L2**             **Con L2 (ciclo sin
                                                  cambio)**
  ------------------------ ---------------------- -----------------------
  Escrituras en PostgreSQL 26 UPDATEs / ciclo     0 UPDATEs (early
                                                  return)

  Invalidaciones Redis     26 / ciclo             0 (caché preservado)

  Escrituras/día           \~7.488                \~0 en días sin cambios
  (estimado)                                      

  updated_at               Sí (cada 5 min)        No (solo en cambio
  artificialmente avanzado                        real)

  Historial de cambios     No disponible          Archivado en
                                                  kb_content_versions
  -----------------------------------------------------------------------

> **3. Qué se Implementó**

**3.1 Componentes del Sistema**

  ----------------------------------------------------------------------------------
  **Componente**                  **Tipo**        **Descripción**
  ------------------------------- --------------- ----------------------------------
  \_compute_content_hash()        Método Python   Calcula SHA256 del Markdown.
                                                  Determinista, UTF-8, 64 chars hex.

  \_archive_content_version()     Método Python   Archiva el contenido ANTERIOR en
                                                  kb_content_versions antes de
                                                  sobreescribir.

  \_prune_old_versions()          Método Python   Elimina versiones antiguas que
                                                  excedan
                                                  KB_MAX_VERSIONS_PER_CONTENT.

  \_execute_upsert() rama L2      Método Python   Flujo de 7 pasos con comparación
                                                  de hashes y archivado condicional.

  content_hash VARCHAR(64)        Columna         SHA256 del Markdown almacenado.
                                  PostgreSQL      Nullable hasta backfill.

  content_version INTEGER         Columna         Contador de versiones reales.
                                  PostgreSQL      DEFAULT 1. Se incrementa en cambio
                                                  real.

  kb_content_versions             Tabla           Historial de versiones archivadas
                                  PostgreSQL      con FK CASCADE y UNIQUE
                                                  constraint.

  0002_l2_content_versioning.py   Migration       DDL completo: columnas, tabla,
                                  Alembic         índices, downgrade.

  l2_backfill_content_hash.py     Script one-time Pobla content_hash en registros
                                                  existentes. Idempotente.

  KB_CONTENT_VERSIONING           Feature flag    Activa/desactiva L2 sin redeploy.
                                  (.env)          Default: true (activado).

  KB_MAX_VERSIONS_PER_CONTENT     Variable .env   Límite de versiones históricas por
                                                  registro. Default: 10.
  ----------------------------------------------------------------------------------

**3.2 Schema de la Tabla kb_content_versions**

> CREATE TABLE kb_content_versions ( id UUID PRIMARY KEY DEFAULT
> gen_random_uuid(), kb_content_id UUID NOT NULL REFERENCES
> kb_contents(id) ON DELETE CASCADE, version INTEGER NOT NULL, content
> TEXT NOT NULL, \-- Markdown archivado content_html TEXT, \-- HTML
> original (nullable) content_hash VARCHAR(64) NOT NULL, \-- SHA256 de
> esta versión title VARCHAR(500), replaced_at TIMESTAMPTZ NOT NULL
> DEFAULT NOW(), sync_source VARCHAR(50) DEFAULT \'background_sync\',
> UNIQUE (kb_content_id, version) );
>
> **4. Cómo Funciona --- Flujo de Datos**

**4.1 Ciclo sin cambio de contenido (caso más frecuente)**

Este es el camino que recorre el sistema en la gran mayoría de los
ciclos de sincronización, cuando el contenido de las páginas de Shopify
no ha cambiado:

> Shopify API → HTML sin cambio ↓ \_html_to_markdown() → Markdown
> idéntico al anterior ↓ \_compute_content_hash() → SHA256 =
> \'abc123\...\' (mismo que en DB) ↓ SELECT content_hash FROM
> kb_contents → \'abc123\...\' ↓ incoming_hash == stored_hash → EARLY
> RETURN ↓ UPDATE last_synced solamente (NO updated_at, NO content) ↓ NO
> invalida Redis → caché preservado hasta TTL natural ↓ Log:
> kb_content_unchanged (nivel DEBUG, no INFO)

**4.2 Ciclo con cambio real de contenido**

Cuando el equipo de contenido edita una página en Shopify CMS, el
siguiente ciclo de sync detecta el cambio y ejecuta el flujo completo de
archivado:

> Shopify API → HTML modificado (ej: \'30 días\' → \'60 días\') ↓
> \_compute_content_hash() → SHA256 = \'xyz789\...\' (DIFERENTE al
> almacenado) ↓ SELECT current (id, hash=\'abc123\', version=1,
> content=old_markdown) ↓ incoming_hash != stored_hash → PROCEDER ↓ Paso
> 4: \_archive_content_version() → INSERT en kb_content_versions
> (kb_content_id, version=1, content=old_markdown, hash=\'abc123\') ↓
> Paso 5: UPDATE kb_contents SET content=\'new_markdown\',
> content_hash=\'xyz789\', content_version=2, updated_at=NOW() ↓ Paso 7:
> \_prune_old_versions() → conservar solo las últimas 10 versiones ↓
> Invalidar Redis → próxima request obtiene contenido actualizado

**4.3 Diagrama de decisión simplificado**

  ----------------------------------------------------------------------------------
  **Condición**                 **Acción**       **PostgreSQL**      **Redis**
  ----------------------------- ---------------- ------------------- ---------------
  content_hash igual al         Early return     Solo last_synced    Sin invalidar
  almacenado                                                         

  content_hash diferente        Archivar +       Archive + UPDATE +  Invalidar
                                actualizar       version++           

  Registro nuevo (no existe)    Insertar         INSERT con          Invalidar
                                                 version=1           

  Hash NULL en DB               Tratar como      Archive + UPDATE    Invalidar
  (pre-backfill)                diferente                            

  KB_CONTENT_VERSIONING=false   Comportamiento   Upsert siempre      Invalidar
                                pre-L2                               siempre
  ----------------------------------------------------------------------------------

> **5. Arquitectura --- Componentes Involucrados**

  -----------------------------------------------------------------------------
  **Capa**         **Componente**         **Rol en L2**
  ---------------- ---------------------- -------------------------------------
  Servicio         ShopifyKBSyncService   Orquesta el flujo completo. Contiene
                                          los 4 métodos L2.

  Servicio         KBBackgroundSyncJob    Dispara sync_all_pages() cada
                                          KB_SYNC_INTERVAL_MINUTES.

  Integración      ShopifyKBClient        Fetch de páginas y traducciones. No
                                          modificado en L2.

  Cache            RedisService           Invalidación condicional (solo cuando
                                          hay cambio real).

  Base de datos    kb_contents            Tabla principal enriquecida con
                                          content_hash y content_version.

  Base de datos    kb_content_versions    Nueva tabla de historial de versiones
                                          archivadas.

  Observabilidad   structlog              Logs DEBUG para ciclos sin cambio,
                                          INFO/ERROR para cambios.

  Config           .env                   Flags KB_CONTENT_VERSIONING y
                                          KB_MAX_VERSIONS_PER_CONTENT.

  Migrations       Alembic 0002           DDL schema L2. Downgrade disponible
                                          para rollback.
  -----------------------------------------------------------------------------

**5.1 Integración con fases previas**

-   M1 (Semáforo): \_execute_upsert() respeta self.\_db_semaphore --- L2
    no rompe la concurrencia controlada.

-   M3 (Distributed Lock): El lock opera en la capa externa
    (\_upsert_kb_content). L2 vive dentro del lock, garantizando que el
    SELECT y el UPDATE son atómicos entre instancias.

-   L1 (HTML→Markdown): \_html_to_markdown() es determinista --- el
    mismo HTML siempre produce el mismo Markdown, lo que hace los hashes
    estables y comparables entre ciclos.

-   M4 (Webhooks): sync_single_page() llama a \_upsert_kb_content(), que
    ya incluye L2 automáticamente.

> **6. Validación --- Resultados de Tests**

  ------------------------------------------------------------------------------------
  **Suite**                        **Tests**   **Estado**    **Cobertura**
  -------------------------------- ----------- ------------- -------------------------
  Unit --- TestComputeContentHash  8           ✅ 8/8 PASSED Determinismo,
                                                             sensibilidad, formato,
                                                             Unicode, vacío

  Unit ---                         4           ✅ 4/4 PASSED Parámetros, ON CONFLICT,
  TestArchiveContentVersion                                  nullable html,
                                                             sync_source

  Unit --- TestPruneOldVersions    4           ✅ 4/4 PASSED CTE+DELETE, logs,
                                                             sin-delete silencioso

  Unit --- TestExecuteUpsertPreL2  2           ✅ 2/2 PASSED Rollback behavior, query
                                                             pre-L2

  Unit ---                         4           ✅ 4/4 PASSED Skip write, touch
  TestExecuteUpsertHashUnchanged                             last_synced, no archive

  Unit ---                         3           ✅ 3/3 PASSED Archive + update + prune
  TestExecuteUpsertHashChanged                               

  Unit ---                         3           ✅ 3/3 PASSED INSERT sin archive, sin
  TestExecuteUpsertNewRecord                                 prune

  Unit ---                         1           ✅ 1/1 PASSED NULL tratado como cambio
  TestExecuteUpsertNullHashInDB                              

  Unit --- TestFeatureFlag         6           ✅ 6/6 PASSED Flags, defaults,
                                                             max_versions

  Unit --- TestL2Regression        6           ✅ 6/6 PASSED Métodos existen, L1
                                                             intacto

  Integration --- Escenario A (sin 3           ✅ 3/3 PASSED Skip write, log, no cache
  cambio)                                                    invalidation

  Integration --- Escenario B      4           ✅ 4/4 PASSED Hash change, archive,
  (cambio real)                                              version++, prune

  Integration --- Escenario C      4           ✅ 4/4 PASSED INSERT, sin archive, sin
  (nuevo registro)                                           prune

  Integration --- Escenario D      2           ✅ 2/2 PASSED NULL → fuerza UPDATE y
  (NULL en DB)                                               archive

  Integration --- Escenario E      4           ✅ 4/4 PASSED Pre-L2 behavior, toggling
  (flag off)                                                 

  Integration --- Escenario F      1           ✅ 1/1 PASSED ES/EN independientes
  (multi-idioma)                                             

  Integration --- Escenario G      3           ✅ 3/3 PASSED L1 determinista, L1
  (no-regresión L1)                                          intacto

  TOTAL                            62          ✅ 62/62      
                                               PASSED (100%) 
  ------------------------------------------------------------------------------------

**6.1 Evidencia de Producción --- Backfill**

  -----------------------------------------------------------------------
  **Métrica**                    **Resultado**
  ------------------------------ ----------------------------------------
  Total registros en kb_contents 26

  Registros backfilled           26 / 26 (100%)
  (content_hash NOT NULL)        

  Registros con NULL restantes   0

  Hashes únicos                  26 (ningún contenido duplicado)

  Distribución por idioma --- ES 13 / 13 ✅

  Distribución por idioma --- EN 13 / 13 ✅

  Duración del backfill          \< 1 segundo (batch único)

  kb_content_versions al activar 0 filas (historial empieza limpio)
  -----------------------------------------------------------------------

> **7. Impacto en Performance y Mantenibilidad**

**7.1 Performance**

-   **Ciclos sin cambio:** El SELECT adicional (Paso 2) añade \~1-2ms
    por registro. Con 26 registros y el early return inmediato, el ciclo
    completo es significativamente más rápido que el upsert pre-L2
    porque evita los 26 UPDATEs.

-   **Ciclos con cambio real:** Ligeramente más lentos que pre-L2 por el
    archive y el prune, pero estos ocurren raramente (solo cuando el
    equipo de contenido edita páginas). El impacto es despreciable.

-   **Redis:** El caché ahora permanece válido hasta su TTL natural en
    ciclos sin cambio. Esto reduce la presión de reconstrucción del
    caché y mejora el hit rate.

-   **PostgreSQL write amplification:** Eliminada en días sin cambios de
    contenido. El updated_at ya no avanza artificialmente, lo que hace
    que las queries de auditoría que filtran por updated_at sean
    significativamente más útiles.

**7.2 Observabilidad**

L2 introduce una distinción clara en los logs entre operación normal y
cambio real:

  ------------------------------------------------------------------------
  **Evento**                 **Log Level**   **Evento structlog**
  -------------------------- --------------- -----------------------------
  Contenido sin cambio (caso DEBUG           kb_content_unchanged
  frecuente)                                 

  Contenido actualizado      DEBUG           kb_content_updated

  Registro nuevo insertado   DEBUG           kb_content_inserted

  Versión archivada          DEBUG           content_version_archived

  Versiones podadas          DEBUG           content_versions_pruned
  ------------------------------------------------------------------------

Al filrar logs por kb_content_unchanged=0 y kb_content_updated\>0, los
equipos de operaciones pueden detectar inmediatamente cuándo el
contenido del KB cambia en Shopify, algo imposible de distinguir en el
sistema pre-L2.

**7.3 Mantenibilidad**

-   El feature flag KB_CONTENT_VERSIONING permite rollback instantáneo
    sin redeploy --- solo cambiando el .env y reiniciando el servicio.

-   La columna content_version actúa como contador de integridad: si un
    registro tiene version=5, significa que su contenido fue modificado
    4 veces desde la primera sincronización.

-   La tabla kb_content_versions preserva el historial completo para
    auditoría, debugging y el futuro pipeline de ML (L4).

> **8. Procedimiento de Rollback**

**8.1 Rollback de código (sin pérdida de schema)**

Para desactivar L2 sin perder el historial ni revertir la migration:

> \# En .env --- cambiar true → false: KB_CONTENT_VERSIONING=false \#
> Reiniciar el servicio: \# Cloud Run: nuevo deploy con la variable
> actualizada \# Local: reiniciar uvicorn \# Efecto inmediato: el
> sistema vuelve al upsert pre-L2. \# Los datos en kb_content_versions
> se preservan. \# La columna content_hash queda en kb_contents
> (inerte).

**8.2 Rollback completo de schema (destructivo)**

> **⚠️ ADVERTENCIA: Esta operación elimina TODOS los datos de historial
> en kb_content_versions. Es irreversible.**
>
> \# Solo si se necesita revertir el schema completamente: alembic
> downgrade 0001 \# Esto elimina: \# - Tabla kb_content_versions (con
> todos sus datos) \# - Columnas content_hash y content_version de
> kb_contents \# - Índices asociados
>
> **9. Limitaciones Conocidas**

  -----------------------------------------------------------------------------------
  **Limitación**                **Impacto**         **Mitigación**
  ----------------------------- ------------------- ---------------------------------
  content_hash es nullable en   Registros           Backfill ejecutado. Migration
  schema                        pre-backfill sin    0003 puede agregar NOT NULL
                                hash serán tratados después de confirmar todos los
                                como \'cambio\' en  environments.
                                el primer ciclo     
                                post-L2             

  Los integration tests usan    No prueban el DDL   Backfill en producción valida las
  mocks de asyncpg (no DB real) real ni las queries queries reales. Tests E2E con DB
                                SQL contra          real recomendados para staging.
                                PostgreSQL          

  SELECT adicional por registro \~1-2ms extra por   Con 26 registros, el impacto
  en cada ciclo                 registro en modo L2 total es \<60ms por ciclo ---
                                                    despreciable frente al bottleneck
                                                    Shopify API (\~88% del tiempo).

  Historial limitado a N        Si una página       Configurable. Para L4 aumentar a
  versiones por                 cambia más de 10    50 o más antes de activar el
  KB_MAX_VERSIONS_PER_CONTENT   veces, las          pipeline de ML.
                                versiones más       
                                antiguas se pierden 

  No existe migration 0003 para content_hash        Planificado como tarea de
  NOT NULL                      permanece nullable  hardening post-validación
                                indefinidamente en  multi-environment.
                                el schema           
  -----------------------------------------------------------------------------------

> **10. Mejoras Futuras**

**Migration 0003 --- NOT NULL constraint**

Una vez confirmado que el backfill se ha ejecutado en todos los
environments (prod, staging, test), agregar el constraint NOT NULL a
content_hash para garantizar integridad a nivel de schema:

> \# Migration 0003 (futura): ALTER TABLE kb_contents ALTER COLUMN
> content_hash SET NOT NULL;

**L3 --- Multi-Region Support**

Distribuir el contenido del KB a múltiples regiones geográficas
(us-central1, eu-west1). L2 sienta las bases para L3 porque el
content_hash permite verificar la consistencia entre réplicas sin
comparar el contenido completo.

**L4 --- ML Content Optimization**

La tabla kb_content_versions es el dataset de entrenamiento para L4.
Cada versión archivada representa un cambio editorial en el KB. Un
pipeline ML puede analizar qué cambios de contenido correlacionan con
mejoras en las métricas de resolución de intenciones del chatbot.

**Tests E2E con DB real**

Complementar los integration tests actuales (con mocks asyncpg) con
tests contra una instancia PostgreSQL real en el pipeline de CI/CD. Esto
validaría el DDL real, los índices, y las queries SQL contra el motor de
base de datos real.

**Alertas basadas en content_version**

Agregar una alerta de monitoreo que notifique cuando content_version de
cualquier registro supere un umbral en un periodo corto de tiempo ---
señal de ediciones frecuentes o inestabilidad en el contenido de
Shopify.

> **11. Archivos Modificados / Creados**

  --------------------------------------------------------------------------------------------------
  **Archivo**                                          **Tipo**     **Descripción del cambio**
  ---------------------------------------------------- ------------ --------------------------------
  src/api/services/shopify_kb_sync.py                  Modificado   4 métodos L2 nuevos + rama L2 en
                                                                    \_execute_upsert() + feature
                                                                    flags en \_\_init\_\_

  alembic/versions/0002_l2_content_versioning.py       Creado       DDL completo: columnas
                                                                    content_hash/content_version,
                                                                    tabla kb_content_versions,
                                                                    índices, downgrade

  scripts/l2_backfill_content_hash.py                  Creado       Script one-time con \--dry-run,
                                                                    \--verbose, \--verify. Carga
                                                                    .env automáticamente.

  tests/unit/test_l2_content_versioning.py             Creado       41 unit tests en 9 clases de
                                                                    test con aislamiento completo
                                                                    via AsyncMock

  tests/integration/kb/test_l2_content_versioning.py   Creado       21 integration tests en 7
                                                                    escenarios de operación real

  .env                                                 Modificado   KB_CONTENT_VERSIONING=true y
                                                                    KB_MAX_VERSIONS_PER_CONTENT=10
                                                                    agregados
  --------------------------------------------------------------------------------------------------

*Documento generado automáticamente al cierre de la fase L2 --- Content
Versioning*

*Retail Recommender System v2.1.0 · 02 de Marzo de 2026 · Fase L2
COMPLETADA*