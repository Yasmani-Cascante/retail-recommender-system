"""baseline_post_h2_schema

Descripcion:
    Migration de baseline (punto de partida). Documenta el estado del schema
    de la base de datos despues de las fases H1 y H2, implementadas con
    scripts SQL manuales antes de introducir Alembic.

    Esta migration NO aplica ningun DDL. Su proposito es exclusivamente
    registrar el estado actual del schema como punto de partida conocido
    para todas las migrations futuras gestionadas por Alembic.

Estado del schema al crear este baseline (2026-02-27):

    Tabla: kb_contents
      Origen: migrations/001_shopify_kb_buffer_FIXED.sql
      Columnas:
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
        sub_intent       VARCHAR(50) NOT NULL
        language         VARCHAR(5) NOT NULL DEFAULT 'es'
        category         VARCHAR(50)
        content          TEXT NOT NULL
        content_html     TEXT
        title            VARCHAR(500)
        meta_description TEXT
        shopify_page_id  BIGINT NOT NULL
        shopify_url      VARCHAR(500)
        shopify_handle   VARCHAR(200)
        last_synced      TIMESTAMP NOT NULL DEFAULT NOW()
        created_at       TIMESTAMP (via trigger)
        updated_at       TIMESTAMP (via trigger)
        schema_version   INTEGER DEFAULT 1  (agregado en H2)

    Tabla: schema_migrations
      Origen: migrations/002_add_schema_versioning.sql
      Columnas:
        version          INTEGER PRIMARY KEY
        description      TEXT NOT NULL
        applied_at       TIMESTAMP DEFAULT NOW()
        applied_by       TEXT DEFAULT CURRENT_USER
        checksum         TEXT
        execution_time_ms INTEGER
        migration_file   VARCHAR(200)
      Datos:
        version=1: Initial kb_contents table creation
        version=2: Add schema_version column and schema_migrations table

    Tabla: alembic_version  (creada automaticamente por Alembic al hacer stamp)
      version_num  VARCHAR(32) NOT NULL

Historial pre-Alembic (scripts SQL manuales aplicados manualmente):
    001 -> migrations/001_shopify_kb_buffer_FIXED.sql   (tabla kb_contents)
    002 -> migrations/002_add_schema_versioning.sql     (schema_migrations + schema_version)

Instrucciones de activacion (EJECUTAR UNA SOLA VEZ por environment):
    # Marcar como aplicado SIN ejecutar ningun DDL:
    alembic stamp 0001

    # Verificar resultado:
    alembic current
    # Expected: 0001 (head)

Revision ID: 0001
Revises:     None  (es el root, no tiene padre)
Create Date: 2026-02-27
"""

# Identificadores de revision.
# revision = '0001' fue asignado manualmente para mayor legibilidad.
# Alembic normalmente genera un hash aleatorio; el ID manual es valido y soportado.
revision = '0001'
down_revision = None    # None = es el root del arbol de migrations
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# UPGRADE: Baseline sin DDL
# ---------------------------------------------------------------------------
def upgrade() -> None:
    """
    Baseline migration: no aplica ningun cambio de schema.

    El schema fue creado por los scripts SQL manuales 001 y 002.
    Este upgrade() esta vacio intencionalmente.

    Activar con:
        alembic stamp 0001
        (NO ejecutar 'alembic upgrade head' en una DB existente con este schema)
    """
    # Intencionalmente vacio.
    # El schema kb_contents + schema_migrations ya fue creado por:
    #   migrations/001_shopify_kb_buffer_FIXED.sql
    #   migrations/002_add_schema_versioning.sql
    pass


# ---------------------------------------------------------------------------
# DOWNGRADE: No aplicable al baseline
# ---------------------------------------------------------------------------
def downgrade() -> None:
    """
    Downgrade desde baseline: no es posible.

    No se puede deshacer el baseline porque referencaria un estado
    anterior a Alembic. Eliminar las tablas requiere un proceso de
    limpieza manual controlado, no un rollback automatizado.

    Para recrear el schema desde cero, usar los scripts SQL manuales:
        migrations/002_rollback_schema_versioning.sql
        (y luego el equivalente para 001)
    """
    # Intencionalmente vacio.
    # El baseline no tiene un downgrade aplicable.
    pass
