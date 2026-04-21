"""${message}

Descripcion:
    [Completar: que problema resuelve esta migration y por que es necesaria]

Cambios en schema:
    [Completar: lista de DDL aplicados: ADD COLUMN, CREATE TABLE, etc.]

Rollback:
    [Completar: descripcion de lo que hace downgrade() para revertir]

Revision ID: ${up_revision}
Revises:     ${down_revision | comma,n}
Create Date: ${create_date}
"""

# Identificadores de revision generados automaticamente por Alembic.
# NO modificar manualmente estos valores.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# ---------------------------------------------------------------------------
# UPGRADE: Aplica los cambios de schema
# ---------------------------------------------------------------------------
def upgrade() -> None:
    """
    Aplica los cambios de esta migration al schema de la base de datos.

    Buenas practicas:
    -----------------
    1. Usar IF NOT EXISTS / IF EXISTS para idempotencia:
           op.execute("ALTER TABLE t ADD COLUMN IF NOT EXISTS col TEXT;")

    2. Registrar en schema_migrations (nuestro audit log de negocio):
           op.execute('''
               INSERT INTO schema_migrations (version, description, migration_file)
               VALUES (<N>, '<descripcion>', '<nombre_archivo>.py')
               ON CONFLICT (version) DO NOTHING;
           ''')

    3. Siempre tener un downgrade() que revierte exactamente upgrade().

    4. Probar con dry-run antes de aplicar:
           alembic upgrade head --sql

    5. Aplicar en TEST primero, luego en PROD.
    """
    ## Implementar aqui los cambios de schema ##
    pass


# ---------------------------------------------------------------------------
# DOWNGRADE: Revierte los cambios de upgrade()
# ---------------------------------------------------------------------------
def downgrade() -> None:
    """
    Revierte exactamente los cambios aplicados por upgrade().

    Uso:
        alembic downgrade -1       -> revertir ultima migration
        alembic downgrade <rev>    -> revertir a una revision especifica

    IMPORTANTE: Si upgrade() agrega datos criticos (INSERT), downgrade()
    debe eliminarlos. Si no es posible un rollback seguro, documentarlo
    aqui y escalarlo como decision de arquitectura antes de aplicar.
    """
    ## Implementar aqui el rollback exacto de upgrade() ##
    pass
