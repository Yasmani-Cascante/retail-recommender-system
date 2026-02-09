-- ═══════════════════════════════════════════════════════════════════════════
-- ROLLBACK: Revert Migration 002 - Schema Versioning
-- ═══════════════════════════════════════════════════════════════════════════
-- Version: 002
-- Date: 2026-02-05
-- Description: Safely removes schema versioning changes
--
-- WARNING: This will DROP the schema_migrations table entirely.
--          Only use if you need to completely revert versioning system.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

-- ───────────────────────────────────────────────────────────────────────────
-- Step 1: Backup verification
-- ───────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    RAISE NOTICE '⚠️  ROLLBACK STARTED - Migration 002';
    RAISE NOTICE '⚠️  This will remove schema versioning system';
    RAISE NOTICE '⚠️  Ensure you have a database backup before proceeding';
END $$;

-- ───────────────────────────────────────────────────────────────────────────
-- Step 2: Remove schema_version column from kb_contents
-- ───────────────────────────────────────────────────────────────────────────

ALTER TABLE kb_contents 
DROP COLUMN IF EXISTS schema_version;

RAISE NOTICE '✅ Column kb_contents.schema_version removed';

-- ───────────────────────────────────────────────────────────────────────────
-- Step 3: Drop schema_migrations table
-- ───────────────────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS schema_migrations CASCADE;

RAISE NOTICE '✅ Table schema_migrations dropped';

COMMIT;

-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFICATION
-- ═══════════════════════════════════════════════════════════════════════════

-- Verify column removed
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'kb_contents' 
        AND column_name = 'schema_version'
    ) THEN
        RAISE EXCEPTION 'Rollback failed: schema_version column still exists';
    END IF;
    RAISE NOTICE '✅ Verification passed: schema_version column removed';
END $$;

-- Verify table dropped
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.tables 
        WHERE table_name = 'schema_migrations'
    ) THEN
        RAISE EXCEPTION 'Rollback failed: schema_migrations table still exists';
    END IF;
    RAISE NOTICE '✅ Verification passed: schema_migrations table dropped';
END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- SUCCESS MESSAGE
-- ═══════════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    RAISE NOTICE '════════════════════════════════════════════════════════════════';
    RAISE NOTICE 'Migration 002 rollback completed successfully!';
    RAISE NOTICE '✅ Schema versioning system removed';
    RAISE NOTICE '✅ Database reverted to pre-002 state';
    RAISE NOTICE '════════════════════════════════════════════════════════════════';
END $$;

-- ═══════════════════════════════════════════════════════════════════════════
-- END OF ROLLBACK
-- ═══════════════════════════════════════════════════════════════════════════