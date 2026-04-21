"""baseline_post_h2_schema

Descripcion:
    Migration 0001: Crea el schema completo del estado post-H2.

    CAMBIO RESPECTO A VERSION ANTERIOR:
        Antes: upgrade() estaba vacio (pass). Disenado solo para sellar
               una DB existente con 'alembic stamp 0001'.
        Ahora: upgrade() crea el schema completo. Esto permite que DBs
               nuevas (Neon, Cloud SQL, staging) puedan construir el
               schema desde cero con 'alembic upgrade head'.

    RETROCOMPATIBILIDAD:
        La DB local (retail_recommender_db) ya tiene alembic_version='0001'
        estampado. Alembic NO re-ejecuta migrations ya aplicadas.
        Este cambio NO afecta la DB local en absoluto.

    Schema que crea esta migration:
        - Tabla kb_contents (18 columnas + 6 indices + 1 trigger)
        - Tabla schema_migrations (7 columnas + 1 indice)
        - Columna schema_version en kb_contents (agregada en H2)
        - 2 registros de audit en schema_migrations (baseline retroactivo)

    Fuente del DDL:
        migrations/001_shopify_kb_buffer_FIXED.sql  (tabla + indices + triggers)
        migrations/002_add_schema_versioning.sql    (schema_migrations + schema_version)

Revision ID: 0001
Revises:     None
Create Date: 2026-02-27 (actualizado 2026-03-03)
"""

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


def upgrade() -> None:
    """
    Crea el schema completo del estado post-H2.

    Equivale a ejecutar en orden:
        1. migrations/001_shopify_kb_buffer_FIXED.sql
        2. migrations/002_add_schema_versioning.sql

    Es idempotente: usa IF NOT EXISTS en todas las operaciones DDL.
    Se puede ejecutar sobre una DB vacia o una que ya tenga parte del schema.
    """

    conn = op.get_bind()

    # ── PARTE 1: Tabla kb_contents (de 001_shopify_kb_buffer_FIXED.sql) ────

    # Funcion para el trigger de updated_at.
    # CREATE OR REPLACE es idempotente por definicion.
    conn.execute(text("""
        CREATE OR REPLACE FUNCTION update_kb_contents_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """))

    # Tabla principal del Knowledge Base.
    # IF NOT EXISTS garantiza idempotencia.
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kb_contents (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sub_intent       VARCHAR(50)  NOT NULL,
            language         VARCHAR(5)   NOT NULL DEFAULT 'es',
            category         VARCHAR(50),
            content          TEXT         NOT NULL,
            content_html     TEXT,
            title            VARCHAR(500),
            meta_description TEXT,
            shopify_page_id  BIGINT       NOT NULL,
            shopify_url      VARCHAR(500),
            shopify_handle   VARCHAR(200),
            last_synced      TIMESTAMP    NOT NULL DEFAULT NOW(),
            created_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
            cache_version    INTEGER      NOT NULL DEFAULT 1,
            related_links    JSONB,
            metadata         JSONB
        )
    """))

    # Indice unico: (sub_intent, language, category) con COALESCE para NULLs.
    # IF NOT EXISTS disponible en PostgreSQL 9.5+. Neon usa PG16, sin problema.
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_kb_content
            ON kb_contents(sub_intent, language, COALESCE(category, 'general'))
    """))

    # Indices de performance
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_kb_lookup
            ON kb_contents(sub_intent, language, category)
            WHERE category IS NOT NULL
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_shopify_page_id
            ON kb_contents(shopify_page_id)
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_language
            ON kb_contents(language)
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_last_synced
            ON kb_contents(last_synced)
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_category
            ON kb_contents(category)
            WHERE category IS NOT NULL
    """))

    # Trigger de updated_at.
    # DROP IF EXISTS + CREATE evita error si el trigger ya existe.
    conn.execute(text("""
        DROP TRIGGER IF EXISTS trigger_update_kb_contents_timestamp ON kb_contents
    """))
    conn.execute(text("""
        CREATE TRIGGER trigger_update_kb_contents_timestamp
            BEFORE UPDATE ON kb_contents
            FOR EACH ROW
            EXECUTE FUNCTION update_kb_contents_updated_at()
    """))

    # ── PARTE 2: schema_migrations + schema_version (de 002_add_schema_versioning.sql) ──

    # Tabla de audit trail de migrations.
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version           INTEGER PRIMARY KEY,
            description       TEXT    NOT NULL,
            applied_at        TIMESTAMP NOT NULL DEFAULT NOW(),
            applied_by        TEXT    DEFAULT CURRENT_USER,
            checksum          TEXT,
            execution_time_ms INTEGER,
            migration_file    VARCHAR(200),
            CONSTRAINT positive_version CHECK (version > 0)
        )
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
            ON schema_migrations(applied_at DESC)
    """))

    # Columna schema_version en kb_contents (H2).
    # IF NOT EXISTS evita error si ya existe (idempotente).
    conn.execute(text("""
        ALTER TABLE kb_contents
        ADD COLUMN IF NOT EXISTS schema_version INTEGER DEFAULT 1
    """))

    # Registros retroactivos de audit (ON CONFLICT DO NOTHING = idempotente)
    conn.execute(text("""
        INSERT INTO schema_migrations (version, description, migration_file, checksum)
        VALUES
            (1, 'Initial kb_contents table creation with indexes and triggers',
             '001_shopify_kb_buffer_FIXED.sql', 'N/A - Retroactive baseline'),
            (2, 'Add schema_version column and create schema_migrations table',
             '002_add_schema_versioning.sql', 'N/A - Retroactive baseline')
        ON CONFLICT (version) DO NOTHING
    """))


def downgrade() -> None:
    """
    Elimina el schema completo.

    ADVERTENCIA: destruye todos los datos de kb_contents.
    Solo ejecutar en environments de test o staging.

    Uso: alembic downgrade base
    """
    conn = op.get_bind()

    # Orden inverso: primero lo que depende de kb_contents
    conn.execute(text("DROP TABLE IF EXISTS schema_migrations CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS kb_contents CASCADE"))
    conn.execute(text("DROP FUNCTION IF EXISTS update_kb_contents_updated_at() CASCADE"))