# Guia Tecnica -- Alembic Migrations (Fase M5)

Sistema: Retail Recommender System v2.1.0
Fecha:   2026-02-27
Fase:    M5 -- Alembic Migrations
Estado:  Implementado

---

## 1. Por que Alembic? Contexto y Decisiones

Antes de M5, las migrations se aplicaban como scripts SQL manuales en `migrations/`.
El problema de ese enfoque es la ausencia de control de version automatizado:
no habia forma de saber si el DB de TEST tenia la misma version de schema que PROD,
ni un mecanismo estandar de rollback.

Alembic resuelve exactamente eso:
- Control de version del schema en la propia DB (tabla `alembic_version`)
- Orden de ejecucion garantizado (cadena de revisiones encadenadas)
- Rollback estructurado via `alembic downgrade`
- Dry-run via `alembic upgrade head --sql` (revisar SQL antes de aplicar)
- Compatible con Cloud SQL -- solo cambia DB_HOST en .env

### Estrategia: Script-only (sin autogenerate)

Usamos Alembic en modo script-only:

    Usamos:     alembic revision -m "descripcion"
                -> Genera el archivo .py con estructura vacia
                -> El desarrollador escribe el SQL en upgrade() / downgrade()

    No usamos:  alembic revision --autogenerate
                -> Requiere modelos SQLAlchemy ORM
                -> Nuestra app usa asyncpg directamente, sin ORM

SQLAlchemy esta instalado unicamente como abstraccion de conexion para Alembic.
La aplicacion sigue usando asyncpg directamente en runtime.

### Dos tablas de tracking: por que coexisten

    alembic_version   -> Tabla de Alembic (1 sola fila: version actual del schema)
                         Control tecnico interno del framework.

    schema_migrations -> Nuestro audit log (creado en H2)
                         Registro historico de negocio con descripcion, checksum,
                         execution_time, applied_by, etc.

No son redundantes. Son complementarias con propositos distintos.
En cada migration nueva, se actualiza ambas tablas.

---

## 2. Estructura de Archivos

    retail-recommender-system/
    +-- alembic.ini                                <- Config principal de Alembic
    +-- alembic/
    |   +-- env.py                                 <- Configuracion de conexion DB
    |   +-- script.py.mako                         <- Template para nuevas migrations
    |   +-- versions/
    |       +-- 0001_baseline_post_h2_schema.py    <- Baseline (punto de partida)
    |       +-- (futuras migrations aqui)
    +-- migrations/                                <- Scripts SQL manuales (pre-Alembic)
    |   +-- 001_shopify_kb_buffer_FIXED.sql        <- Ya aplicada (NO tocar)
    |   +-- 002_add_schema_versioning.sql          <- Ya aplicada (NO tocar)
    |   +-- 002_rollback_schema_versioning.sql     <- Rollback manual disponible
    +-- scripts/
        +-- m5_alembic_setup.py                    <- Script de validacion/activacion

---

## 3. Comandos Esenciales

    # Estado y navegacion
    alembic current              # En que version esta este DB?
    alembic history --verbose    # Historial completo de migrations
    alembic check                # Hay migrations pendientes?

    # Aplicar migrations
    alembic upgrade head         # Aplicar TODAS las migrations pendientes
    alembic upgrade 0002         # Aplicar hasta una revision especifica
    alembic upgrade head --sql   # DRY-RUN: ver SQL sin aplicarlo

    # Revertir migrations
    alembic downgrade -1         # Revertir la ultima migration
    alembic downgrade 0001       # Revertir a una revision especifica
    alembic downgrade base       # Revertir TODAS (extremo, cuidado en PROD)

    # Crear nueva migration
    alembic revision -m "descripcion_en_minusculas_con_guiones_bajos"
    # Genera: alembic/versions/<hash>_descripcion.py

    # Activacion inicial (solo UNA VEZ por environment)
    alembic stamp 0001           # Registrar baseline sin ejecutar DDL

---

## 4. Workflow Estandar para Nuevas Migrations

Seguir este proceso en TODAS las migrations futuras, sin excepcion:

    1. CREAR BRANCH
       git checkout -b feat/db-migration-descripcion-corta

    2. GENERAR archivo de migration
       alembic revision -m "descripcion_de_lo_que_hace"
       # Editar el archivo generado en alembic/versions/

    3. IMPLEMENTAR upgrade() y downgrade()
       (ver plantilla en seccion 4.1)

    4. DRY-RUN -- revisar SQL antes de aplicar
       alembic upgrade head --sql

    5. APLICAR en TEST
       # Verificar que DB_HOST apunta al DB de TEST
       alembic upgrade head

    6. VERIFICAR en TEST
       alembic current
       # Ejecutar smoke tests del sistema

    7. CODE REVIEW
       git push + Pull Request
       # El reviewer valida que downgrade() revierte exactamente upgrade()

    8. APLICAR en PROD (tras merge a main)
       # Cambiar DB_HOST al DB de PROD
       alembic upgrade head

    9. VERIFICAR en PROD
       alembic current

    10. DOCUMENTAR en DCT correspondiente


### 4.1 Plantilla de Migration

```python
# alembic/versions/000X_descripcion_de_la_migration.py
"""descripcion_de_la_migration

Descripcion:
    [Que problema resuelve y por que es necesaria]

Cambios en schema:
    [Lista de DDL: ADD COLUMN x, CREATE TABLE y, etc.]

Rollback:
    [Que hace downgrade() para revertir exactamente]

Revision ID: <generado por alembic>
Revises: <revision anterior>
Create Date: YYYY-MM-DD
"""
revision = '<hash>'
down_revision = '<revision_anterior>'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # 1. Aplicar cambios de schema (idempotente cuando sea posible)
    op.execute("""
        ALTER TABLE kb_contents
        ADD COLUMN IF NOT EXISTS nueva_columna TEXT;
    """)

    # 2. Registrar en nuestro audit log de negocio
    op.execute("""
        INSERT INTO schema_migrations (version, description, migration_file)
        VALUES (3, 'Descripcion del cambio', '000X_nombre.py')
        ON CONFLICT (version) DO NOTHING;
    """)


def downgrade() -> None:
    # Revertir EXACTAMENTE lo que hizo upgrade()
    op.execute("""
        ALTER TABLE kb_contents
        DROP COLUMN IF EXISTS nueva_columna;
    """)
    op.execute("""
        DELETE FROM schema_migrations WHERE version = 3;
    """)
```

---

## 5. Activacion Inicial: TEST y PROD

Ejecutar UNA SOLA VEZ por environment. No repetir.

    # Paso 1: Verificar prerequisitos (recomendado siempre primero)
    python scripts/m5_alembic_setup.py --check

    # Paso 2: Stamp en TEST
    # Asegurarse de que DB_HOST en .env.test apunta al DB de TEST
    python scripts/m5_alembic_setup.py --stamp --env test
    alembic current
    # Expected: 0001 (head)

    # Paso 3: Stamp en PROD
    # Cambiar DB_HOST en .env al DB de PROD
    python scripts/m5_alembic_setup.py --stamp
    alembic current
    # Expected: 0001 (head)

---

## 6. Convivencia con Scripts SQL Manuales (pre-Alembic)

Los archivos en `migrations/` son el historial pre-Alembic. Regla simple:

    migrations/*.sql     -> Historial. NO modificar. NO volver a aplicar.
    alembic/versions/    -> Toda migration FUTURA va aqui.

Si por alguna razon se necesita referenciar un script SQL antiguo,
hacerlo solo en el docstring de la migration, nunca ejecutarlo via Alembic.

---

## 7. Compatibilidad con Cloud SQL (Planes Futuros)

Cuando se migre a Cloud SQL, solo se necesita cambiar el .env:

    # .env actualizado con datos de Cloud SQL
    DB_HOST=<IP publica o socket de Cloud SQL>
    DB_PORT=5432
    DB_USER=<usuario>
    DB_PASSWORD=<password>
    DB_NAME=retail_recommender_db

    # Verificar conectividad
    python scripts/m5_alembic_setup.py --check

    # Si el DB de Cloud SQL ya tiene el schema (backup restaurado):
    alembic current     # Ver si alembic_version existe
    # Si existe: no hacer nada, continuar normalmente
    # Si no existe: alembic stamp 0001

    # Continuar workflow normal
    alembic upgrade head

Alembic no tiene dependencia de donde vive el PostgreSQL.
Solo necesita conectarse a el. El codigo de alembic/env.py no cambia.

---

## 8. Criterios de Exito (M5)

    Criterio                              Verificacion                  Estado
    -----------------------------------   ---------------------------   --------
    alembic instalado                     alembic --version >= 1.13.0  OK
    alembic_version en DB (TEST)          SELECT * FROM alembic_version  OK (2026-02-27)
    alembic_version en DB (PROD)          SELECT * FROM alembic_version  OK (2026-02-27)
    Tablas existentes intactas            Conteos pre/post stamp         OK (sin DDL)
    alembic current = 0001 (head)         alembic current                OK (TEST y PROD)
    Sin migrations pendientes             alembic heads vs current       OK (sincronizados)
    Baseline dry-run = sin SQL            alembic upgrade head --sql     OK (por diseno)
    Workflow documentado                  Este documento                 OK

    Estado Final: M5 COMPLETADO -- 2026-02-27
    Proxima fase: L1 -- HTML -> Markdown Library

---

## 9. Troubleshooting

ERROR: Can't locate revision identified by '0001'
    Causa: Alembic no encuentra el archivo de la revision.
    Fix:   Verificar que existe alembic/versions/0001_baseline_post_h2_schema.py

ERROR: Target database is not up to date
    Causa: Hay migrations en alembic/versions/ que no estan aplicadas.
    Fix:   alembic upgrade head

ERROR: sqlalchemy.exc.OperationalError: connection refused
    Causa: DB_HOST/DB_PORT no son accesibles.
    Fix:   Verificar que PostgreSQL esta corriendo.
           python scripts/m5_alembic_setup.py --check

ERROR Windows: 'alembic' is not recognized as a command
    Causa: El entorno virtual no esta activado.
    Fix:   .venv\Scripts\activate
           alembic --version

alembic_version ya existe con version diferente
    Causa: Alembic fue inicializado anteriormente con otro baseline.
    Fix:   SELECT * FROM alembic_version;   -> ver version actual
           alembic history                  -> ver arbol de revisiones
           Consultar al arquitecto antes de proceder.

ERROR: FAILED: Can't proceed with --autogenerate option; env does not provide MetaData
    Causa: 'alembic check' requiere target_metadata con modelos SQLAlchemy ORM.
           Nuestra estrategia es script-only (target_metadata = None), lo que
           hace que 'alembic check' falle siempre. NO es un error de M5.
    Fix:   Este error es esperado y NO indica un problema real.
           Usar en su lugar:
               alembic current     -> ver version registrada en DB
               alembic heads       -> ver ultima revision disponible
           Si current muestra '0001 (head)' -> todo esta correcto.
           El script m5_alembic_setup.py --status usa 'alembic heads' correctamente.
