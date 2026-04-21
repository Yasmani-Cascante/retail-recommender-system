"""l2_content_versioning

Descripcion:
    Migration L2: agrega soporte de Content Versioning al sistema KB.

    Esta migration implementa el esquema necesario para que
    ShopifyKBSyncService pueda:
    1. Detectar si el contenido Markdown de una página cambió entre ciclos
       de sync, evitando escrituras fantasma en PostgreSQL.
    2. Archivar el historial de versiones anteriores en una tabla separada,
       proporcionando un audit trail para L4 (ML Content Optimization).

    CAMBIOS EN kb_contents:
    - content_hash  VARCHAR(64): SHA256 del contenido Markdown almacenado.
      NULL en registros existentes hasta que el backfill lo popule.
      Índice para acelerar queries de comparación de hashes.
    - content_version INTEGER NOT NULL DEFAULT 1: contador de cambios reales
      del contenido (no del ciclo de sync).

    NUEVA TABLA kb_content_versions:
    - Historial de las N versiones anteriores de cada registro kb_contents.
    - ON DELETE CASCADE garantiza que borrar el registro padre limpia el historial.
    - UNIQUE (kb_content_id, version) previene duplicados en retries.
    - Índice por (kb_content_id, version DESC) optimiza las consultas de poda
      (_prune_old_versions usa ORDER BY version DESC LIMIT N).

Estado del schema al aplicar este migration:

    Tabla: kb_contents (modificada)
      Columnas nuevas:
        content_hash     VARCHAR(64)           -- SHA256 del Markdown (nullable al inicio)
        content_version  INTEGER NOT NULL DEFAULT 1  -- Contador de versiones reales
      Índices nuevos:
        idx_kb_contents_content_hash ON kb_contents (content_hash)

    Tabla: kb_content_versions (nueva)
      Columnas:
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
        kb_content_id    UUID NOT NULL REFERENCES kb_contents(id) ON DELETE CASCADE
        version          INTEGER NOT NULL
        content          TEXT NOT NULL
        content_html     TEXT              -- nullable: puede estar ausente
        content_hash     VARCHAR(64) NOT NULL
        title            VARCHAR(500)
        replaced_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        sync_source      VARCHAR(50) DEFAULT 'background_sync'
      Constraints:
        UNIQUE (kb_content_id, version)
      Índices:
        idx_kb_content_versions_content_id ON (kb_content_id, version DESC)
        idx_kb_content_versions_replaced_at ON (kb_content_id, replaced_at ASC)

Post-migration: ejecutar el backfill para poblar content_hash en registros existentes:
    python scripts/l2_backfill_content_hash.py --dry-run  # verificar primero
    python scripts/l2_backfill_content_hash.py            # ejecutar en real

Revision ID: 0002
Revises:     0001
Create Date: 2026-03-01
"""

# Identificadores de revision.
revision = '0002'
down_revision = '0001'  # Encadena desde el baseline post-H2
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# UPGRADE: Agregar columnas + tabla de versiones
# ---------------------------------------------------------------------------
def upgrade() -> None:
    """
    Aplica el schema de Content Versioning (L2).

    ORDEN DE OPERACIONES:
    1. Agregar content_hash a kb_contents (nullable para compatibilidad)
    2. Agregar content_version a kb_contents (con default 1)
    3. Crear índice en content_hash
    4. Crear tabla kb_content_versions
    5. Crear índices en kb_content_versions

    Por qué content_hash es nullable al inicio:
        Los registros existentes no tienen hash calculado todavía.
        Hacerlo NOT NULL aquí requeriría un valor default, pero el default
        debe ser el SHA256 del contenido — lo cual requiere Python, no SQL.
        El backfill (scripts/l2_backfill_content_hash.py) popula el valor
        en todos los registros existentes después de aplicar esta migration.
        Una migration 0003 futura puede agregar NOT NULL una vez que el
        backfill haya corrido exitosamente en todos los environments.

    Por qué content_version tiene DEFAULT 1:
        Los registros existentes se consideran "versión 1" (el estado en el
        que estaban antes de activar Content Versioning). Cuando L2 actualice
        por primera vez un registro, incrementará de 1 a 2.
    """
    # ── Paso 1 y 2: Columnas nuevas en kb_contents ────────────────────────
    # Usamos batch_alter_table para compatibilidad con SQLite en tests locales.
    # En PostgreSQL, ADD COLUMN es una operación muy rápida (solo metadata).
    with op.batch_alter_table('kb_contents', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'content_hash',
                sa.String(length=64),
                nullable=True,    # Nullable: registros existentes aún no tienen hash
                comment='SHA256 del contenido Markdown. NULL hasta que corra el backfill L2.'
            )
        )
        batch_op.add_column(
            sa.Column(
                'content_version',
                sa.Integer(),
                nullable=False,
                server_default='1',   # DEFAULT 1 en DB para registros existentes
                comment='Contador de versiones de contenido. Incrementa en cada cambio real.'
            )
        )

    # ── Paso 3: Índice en content_hash ────────────────────────────────────
    # El índice acelera las queries de comparación en _execute_upsert():
    #   SELECT ... WHERE content_hash = $1
    # Con solo 26 registros en kb_contents, el índice no es crítico hoy,
    # pero es buena práctica prepararlo antes de que el volumen crezca (L3).
    op.create_index(
        'idx_kb_contents_content_hash',
        'kb_contents',
        ['content_hash'],
        unique=False    # No unique: dos registros distintos podrían tener el mismo contenido
    )

    # ── Paso 4: Crear tabla kb_content_versions ────────────────────────────
    op.create_table(
        'kb_content_versions',

        # Clave primaria: UUID generado por PostgreSQL
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            primary_key=True
        ),

        # Foreign key al registro padre en kb_contents.
        # ON DELETE CASCADE: si se borra el registro padre, se borran sus versiones.
        # Esto es intencional: si se borra una página de Shopify del KB, su historial
        # ya no tiene valor y puede limpiarse con ella.
        sa.Column(
            'kb_content_id',
            sa.UUID(),
            sa.ForeignKey(
                'kb_contents.id',
                ondelete='CASCADE',
                name='fk_kb_content_versions_content_id'
            ),
            nullable=False,
            comment='ID del registro padre en kb_contents'
        ),

        # Número de versión: el mismo valor que content_version tenía en
        # kb_contents ANTES de ser reemplazado. No es autoincremental —
        # es copiado desde kb_contents.content_version en el Paso 4 de _execute_upsert().
        sa.Column(
            'version',
            sa.Integer(),
            nullable=False,
            comment='Número de versión archivada. Copia de content_version antes del reemplazo.'
        ),

        # Contenido Markdown archivado (versión anterior)
        sa.Column(
            'content',
            sa.Text(),
            nullable=False,
            comment='Contenido Markdown de esta versión archivada'
        ),

        # HTML original (puede ser None si no se almacenó)
        sa.Column(
            'content_html',
            sa.Text(),
            nullable=True,
            comment='HTML de Shopify de esta versión archivada. Nullable.'
        ),

        # Hash SHA256 del contenido archivado.
        # Permite a L4 detectar si dos versiones distintas tenían el mismo contenido
        # (ej. un revert accidental).
        sa.Column(
            'content_hash',
            sa.String(length=64),
            nullable=False,
            comment='SHA256 del campo content de esta versión'
        ),

        # Título de la página en el momento de archivar
        sa.Column(
            'title',
            sa.String(length=500),
            nullable=True
        ),

        # Timestamp de cuándo fue reemplazada esta versión.
        # Permite reconstruir la línea de tiempo de cambios.
        sa.Column(
            'replaced_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('NOW()'),
            nullable=False,
            comment='Cuándo fue reemplazada esta versión por una nueva'
        ),

        # Fuente del sync que detectó el cambio y archivó esta versión.
        # Valores posibles: 'background_sync', 'webhook', 'manual'
        sa.Column(
            'sync_source',
            sa.String(length=50),
            server_default='background_sync',
            nullable=True,
            comment="Qué disparó el sync que archivó esta versión: 'background_sync', 'webhook', etc."
        ),

        # Constraint de unicidad: (kb_content_id, version) es un par único.
        # Junto con ON CONFLICT DO NOTHING en _archive_content_version(),
        # previene duplicados silenciosamente en caso de retries.
        sa.UniqueConstraint(
            'kb_content_id',
            'version',
            name='uq_kb_content_versions_content_version'
        ),
    )

    # ── Paso 5: Índices en kb_content_versions ─────────────────────────────

    # Índice compuesto (kb_content_id, version DESC):
    # Usado por _prune_old_versions() para encontrar las N versiones más recientes:
    #   ORDER BY version DESC LIMIT $max_versions
    # El DESC en el índice evita un sort adicional en PostgreSQL.
    op.create_index(
        'idx_kb_content_versions_content_id',
        'kb_content_versions',
        [
            'kb_content_id',
            sa.text('version DESC')    # Índice descendente para poda eficiente
        ],
        unique=False
    )

    # Índice en (kb_content_id, replaced_at ASC):
    # Útil para queries de L4 que reconstruyen la línea de tiempo de cambios:
    #   SELECT * FROM kb_content_versions WHERE kb_content_id=$1 ORDER BY replaced_at
    op.create_index(
        'idx_kb_content_versions_replaced_at',
        'kb_content_versions',
        ['kb_content_id', 'replaced_at'],
        unique=False
    )


# ---------------------------------------------------------------------------
# DOWNGRADE: Revertir los cambios de L2
# ---------------------------------------------------------------------------
def downgrade() -> None:
    """
    Revierte el schema de Content Versioning (L2).

    ORDEN INVERSO al upgrade (importante para integridad referencial):
    1. Eliminar índices de kb_content_versions
    2. Eliminar tabla kb_content_versions (junto con datos de historial)
    3. Eliminar índice de content_hash en kb_contents
    4. Eliminar columnas content_hash y content_version de kb_contents

    ADVERTENCIA: El downgrade elimina TODOS los datos de historial almacenados
    en kb_content_versions. Esta acción es irreversible. Solo ejecutar si
    se tiene certeza de que el historial no es necesario o está respaldado.

    Para ejecutar:
        alembic downgrade 0001

    Si la intención es solo desactivar L2 sin perder el historial, usar
    la variable de entorno:
        KB_CONTENT_VERSIONING=false
    Esto desactiva L2 en el código sin tocar el schema ni los datos.
    """
    # ── Paso 1: Eliminar índices de kb_content_versions ───────────────────
    op.drop_index('idx_kb_content_versions_replaced_at', table_name='kb_content_versions')
    op.drop_index('idx_kb_content_versions_content_id', table_name='kb_content_versions')

    # ── Paso 2: Eliminar tabla (CASCADE implícita en la tabla misma) ───────
    # NOTA: Los datos de historial se pierden permanentemente.
    op.drop_table('kb_content_versions')

    # ── Paso 3: Eliminar índice en kb_contents ────────────────────────────
    op.drop_index('idx_kb_contents_content_hash', table_name='kb_contents')

    # ── Paso 4: Eliminar columnas de kb_contents ──────────────────────────
    with op.batch_alter_table('kb_contents', schema=None) as batch_op:
        batch_op.drop_column('content_version')
        batch_op.drop_column('content_hash')
