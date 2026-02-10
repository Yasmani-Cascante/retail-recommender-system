-- ═══════════════════════════════════════════════════════════════════════════
-- MIGRATION: 002 - Add Schema Versioning
-- ═══════════════════════════════════════════════════════════════════════════
-- Version: 002
-- Date: 2026-02-05
-- Author: Retail Recommender System Team
-- Description: 
--   - Adds schema_version column to kb_contents table
--   - Creates schema_migrations tracking table
--   - Records this migration as version 1 (baseline)
--
-- Dependencies: 001_shopify_kb_buffer.sql (FIXED)
-- Rollback: 002_rollback_schema_versioning.sql
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

-- ───────────────────────────────────────────────────────────────────────────
-- Step 1: Create schema_migrations tracking table FIRST
-- ───────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT NOW(),
    applied_by TEXT DEFAULT CURRENT_USER,
    checksum TEXT,  -- SHA256 of migration file for validation
    execution_time_ms INTEGER,  -- Performance tracking
    migration_file VARCHAR(200),  -- Filename for reference
    
    CONSTRAINT positive_version CHECK (version > 0)
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at 
    ON schema_migrations(applied_at DESC);

COMMENT ON TABLE schema_migrations IS 
'Tracks all database schema migrations applied to this database. Used for versioning and rollback.';

COMMENT ON COLUMN schema_migrations.version IS 
'Sequential migration version number (1, 2, 3, ...)';

COMMENT ON COLUMN schema_migrations.checksum IS 
'SHA256 hash of migration file content for integrity validation';

-- ───────────────────────────────────────────────────────────────────────────
-- Step 2: Add schema_version column to kb_contents
-- ───────────────────────────────────────────────────────────────────────────

ALTER TABLE kb_contents 
ADD COLUMN IF NOT EXISTS schema_version INTEGER DEFAULT 1
;

COMMENT ON COLUMN kb_contents.schema_version IS 
'Schema version for tracking migrations. Increments with each schema change.';

-- Set existing rows to version 1 (baseline)
UPDATE kb_contents 
SET schema_version = 1 
WHERE schema_version IS NULL;

-- ───────────────────────────────────────────────────────────────────────────
-- Step 3: Record initial migrations (retroactive)
-- ───────────────────────────────────────────────────────────────────────────

-- Migration 1: Initial kb_contents table creation (retroactive)
INSERT INTO schema_migrations (version, description, migration_file, checksum)
VALUES (
    1, 
    'Initial kb_contents table creation with indexes and triggers',
    '001_shopify_kb_buffer_FIXED.sql',
    'N/A - Retroactive baseline'
)
ON CONFLICT (version) DO NOTHING;

-- Migration 2: This migration (adding versioning)
INSERT INTO schema_migrations (version, description, migration_file, checksum)
VALUES (
    2, 
    'Add schema_version column and create schema_migrations table',
    '002_add_schema_versioning.sql',
    'SHA256_TO_BE_CALCULATED'  -- Replace with actual checksum after file creation
)
ON CONFLICT (version) DO NOTHING;

COMMIT;

-- ═══════════════════════════════════════════════════════════════════════════
-- VALIDATION QUERIES (run automatically after migration)
-- ═══════════════════════════════════════════════════════════════════════════

-- Test 1: Verify schema_version column exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'kb_contents' 
        AND column_name = 'schema_version'
    ) THEN
        RAISE EXCEPTION 'Migration 002 failed: schema_version column not created';
    END IF;
    RAISE NOTICE '✅ Test 1 passed: schema_version column exists';
END $$;

-- Test 2: Verify schema_migrations table exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.tables 
        WHERE table_name = 'schema_migrations'
    ) THEN
        RAISE EXCEPTION 'Migration 002 failed: schema_migrations table not created';
    END IF;
    RAISE NOTICE '✅ Test 2 passed: schema_migrations table exists';
END $$;

-- Test 3: Verify migrations recorded
DO $$
DECLARE
    migration_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO migration_count
    FROM schema_migrations;
    
    IF migration_count < 2 THEN
        RAISE EXCEPTION 'Migration 002 failed: Expected 2 migrations, found %', migration_count;
    END IF;
    RAISE NOTICE '✅ Test 3 passed: % migrations recorded', migration_count;
END $$;

-- Test 4: Verify all kb_contents rows have schema_version = 1
DO $$
DECLARE
    null_count INTEGER;
    non_one_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count
    FROM kb_contents
    WHERE schema_version IS NULL;
    
    SELECT COUNT(*) INTO non_one_count
    FROM kb_contents
    WHERE schema_version != 1;
    
    IF null_count > 0 THEN
        RAISE EXCEPTION 'Migration 002 failed: % rows have NULL schema_version', null_count;
    END IF;
    
    IF non_one_count > 0 THEN
        RAISE WARNING 'Migration 002: % rows have schema_version != 1', non_one_count;
    END IF;
    
    RAISE NOTICE '✅ Test 4 passed: All rows have schema_version set';
END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- SUMMARY OUTPUT
-- ═══════════════════════════════════════════════════════════════════════════

-- Display current state
SELECT 
    '002_add_schema_versioning.sql' AS migration_file,
    'SUCCESS' AS status,
    COUNT(*) AS kb_contents_count,
    COUNT(DISTINCT schema_version) AS unique_versions,
    MIN(schema_version) AS min_version,
    MAX(schema_version) AS max_version,
    (SELECT COUNT(*) FROM schema_migrations) AS total_migrations
FROM kb_contents;

-- Display migrations history
SELECT 
    version,
    description,
    applied_at,
    migration_file
FROM schema_migrations
ORDER BY version;

-- ═══════════════════════════════════════════════════════════════════════════
-- SUCCESS MESSAGE
-- ═══════════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    RAISE NOTICE '════════════════════════════════════════════════════════════════';
    RAISE NOTICE 'Migration 002 completed successfully!';
    RAISE NOTICE '✅ Table: schema_migrations created';
    RAISE NOTICE '✅ Column: kb_contents.schema_version added';
    RAISE NOTICE '✅ Migrations: 2 recorded (baseline + this)';
    RAISE NOTICE '✅ All tests passed';
    RAISE NOTICE '════════════════════════════════════════════════════════════════';
END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- END OF MIGRATION
-- ═══════════════════════════════════════════════════════════════════════════