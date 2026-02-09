-- ═══════════════════════════════════════════════════════════════════════════
-- PRE-MIGRATION VALIDATION QUERIES
-- ═══════════════════════════════════════════════════════════════════════════

-- Query 1: Check current data volume
SELECT 
    'Current kb_contents data' AS check_name,
    COUNT(*) AS total_records,
    COUNT(DISTINCT sub_intent) AS unique_sub_intents,
    COUNT(DISTINCT language) AS unique_languages,
    MIN(created_at) AS oldest_record,
    MAX(created_at) AS newest_record,
    pg_size_pretty(pg_total_relation_size('kb_contents')) AS table_size
FROM kb_contents;

-- Query 2: Verify schema_version doesn't exist yet
SELECT 
    CASE 
        WHEN EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = 'kb_contents' 
            AND column_name = 'schema_version'
        ) 
        THEN '❌ STOP: schema_version already exists!'
        ELSE '✅ OK: schema_version does not exist - safe to proceed'
    END AS pre_check_result;

-- Query 3: Verify schema_migrations doesn't exist yet
SELECT 
    CASE 
        WHEN EXISTS (
            SELECT 1 
            FROM information_schema.tables 
            WHERE table_name = 'schema_migrations'
        ) 
        THEN '❌ STOP: schema_migrations already exists!'
        ELSE '✅ OK: schema_migrations does not exist - safe to proceed'
    END AS pre_check_result;

-- Query 4: List all current columns (for comparison after migration)
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'kb_contents'
ORDER BY ordinal_position;

-- Query 5: Check for any locks on kb_contents table
SELECT 
    pid,
    usename,
    application_name,
    state,
    query
FROM pg_stat_activity
WHERE query LIKE '%kb_contents%'
AND state != 'idle';