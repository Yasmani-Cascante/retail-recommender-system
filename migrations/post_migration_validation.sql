-- ============================================================================
-- POST-MIGRATION VALIDATION QUERIES
-- ============================================================================
-- Migration: 002_add_schema_versioning.sql
-- Date: 2026-02-05
-- Purpose: Verify migration applied correctly
-- ============================================================================

-- Query 1: Verify schema_version column added
SELECT 
    'schema_version column' AS check_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'kb_contents' 
AND column_name = 'schema_version';

-- Query 2: Verify schema_migrations table structure
SELECT 
    'schema_migrations columns' AS check_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'schema_migrations'
ORDER BY ordinal_position;

-- Query 3: Check all migrations recorded
SELECT 
    'Migrations history' AS check_name,
    version,
    description,
    applied_at,
    migration_file
FROM schema_migrations
ORDER BY version;

-- Query 4: Verify kb_contents data integrity
SELECT 
    'kb_contents integrity' AS check_name,
    COUNT(*) AS total_records,
    COUNT(DISTINCT schema_version) AS unique_versions,
    MIN(schema_version) AS min_version,
    MAX(schema_version) AS max_version,
    COUNT(CASE WHEN schema_version IS NULL THEN 1 END) AS null_count
FROM kb_contents;

-- Query 5: Show sample kb_contents rows with new column
SELECT 
    id,
    sub_intent,
    language,
    schema_version,
    created_at,
    updated_at
FROM kb_contents
LIMIT 2;

-- Query 6: Verify indexes on schema_migrations
SELECT 
    'schema_migrations indexes' AS check_name,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'schema_migrations'
ORDER BY indexname;

-- Query 7: Count total columns in kb_contents (should be 18 now)
SELECT 
    'Total columns count' AS check_name,
    COUNT(*) AS column_count
FROM information_schema.columns
WHERE table_name = 'kb_contents';

-- Query 8: Verify current schema version
SELECT 
    'Current schema version' AS check_name,
    MAX(version) AS current_version,
    COUNT(*) AS total_migrations
FROM schema_migrations;

-- ============================================================================
-- SUCCESS SUMMARY
-- ============================================================================

SELECT 
    '=== MIGRATION 002 VALIDATION SUMMARY ===' AS summary,
    (SELECT COUNT(*) FROM schema_migrations) AS migrations_applied,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'kb_contents' AND column_name = 'schema_version') AS schema_version_exists,
    (SELECT COUNT(*) FROM kb_contents) AS total_records,
    (SELECT MAX(version) FROM schema_migrations) AS current_schema_version;

-- ============================================================================
-- END OF VALIDATION
-- ============================================================================