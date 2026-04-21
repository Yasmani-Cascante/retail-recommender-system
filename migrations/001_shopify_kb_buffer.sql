-- ============================================================================
-- Migration: 001_shopify_kb_buffer.sql (FIXED)
-- Description: Creates the Knowledge Base buffer table for Shopify CMS sync
-- Author: Retail Recommender System Team
-- Date: 2026-01-11
-- Fixed: 2026-02-04 - Encoding + Syntax errors resolved
-- ============================================================================

-- Create table WITHOUT the problematic constraint
CREATE TABLE IF NOT EXISTS kb_contents (
    -- PRIMARY KEY & IDENTIFICATION
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- KNOWLEDGE BASE METADATA
    sub_intent VARCHAR(50) NOT NULL,
    language VARCHAR(5) NOT NULL DEFAULT 'es',
    category VARCHAR(50),
    
    -- CONTENT (Multiple formats for flexibility)
    content TEXT NOT NULL,
    content_html TEXT,
    title VARCHAR(500),
    meta_description TEXT,
    
    -- SHOPIFY SYNC METADATA
    shopify_page_id BIGINT NOT NULL,
    shopify_url VARCHAR(500),
    shopify_handle VARCHAR(200),
    last_synced TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- CACHE METADATA
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    cache_version INTEGER NOT NULL DEFAULT 1,
    
    -- EXTENDED DATA (JSON for flexibility)
    related_links JSONB,
    metadata JSONB
);

-- ============================================================================
-- UNIQUE CONSTRAINT usando UNIQUE INDEX con expresión
-- Este approach permite usar COALESCE en el constraint
-- ============================================================================

CREATE UNIQUE INDEX idx_unique_kb_content 
    ON kb_contents(sub_intent, language, COALESCE(category, 'general'));

-- ============================================================================
-- PERFORMANCE INDEXES
-- ============================================================================

-- Primary lookup index (most common query)
CREATE INDEX IF NOT EXISTS idx_kb_lookup 
    ON kb_contents(sub_intent, language, category)
    WHERE category IS NOT NULL;

-- Shopify ID lookup (for webhook processing)
CREATE INDEX IF NOT EXISTS idx_shopify_page_id 
    ON kb_contents(shopify_page_id);

-- Language filter index
CREATE INDEX IF NOT EXISTS idx_language 
    ON kb_contents(language);

-- Stale content detection (for cleanup jobs)
CREATE INDEX IF NOT EXISTS idx_last_synced 
    ON kb_contents(last_synced);

-- Category-based queries
CREATE INDEX IF NOT EXISTS idx_category 
    ON kb_contents(category)
    WHERE category IS NOT NULL;

-- ============================================================================
-- TRIGGERS
-- Automatic timestamp management
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_kb_contents_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to call the function on UPDATE
DROP TRIGGER IF EXISTS trigger_update_kb_contents_timestamp ON kb_contents;
CREATE TRIGGER trigger_update_kb_contents_timestamp
    BEFORE UPDATE ON kb_contents
    FOR EACH ROW
    EXECUTE FUNCTION update_kb_contents_updated_at();

-- ============================================================================
-- COMMENTS
-- Documentation for database schema
-- ============================================================================

COMMENT ON TABLE kb_contents IS 
'Knowledge Base content buffer from Shopify CMS. Acts as cache layer between Shopify and Redis with 48h TTL.';

COMMENT ON COLUMN kb_contents.id IS 
'UUID primary key, auto-generated via gen_random_uuid()';

COMMENT ON COLUMN kb_contents.sub_intent IS 
'Knowledge Base sub-intent classification (e.g., policy_return, product_care)';

COMMENT ON COLUMN kb_contents.language IS 
'ISO 639-1 language code (es, en, pt, etc.)';

COMMENT ON COLUMN kb_contents.category IS 
'Optional product category for context-specific content';

COMMENT ON COLUMN kb_contents.content IS 
'Primary content in Markdown format from Shopify CMS';

COMMENT ON COLUMN kb_contents.shopify_page_id IS 
'Shopify Page ID for tracking source and webhook processing';

COMMENT ON COLUMN kb_contents.last_synced IS 
'Timestamp of last successful sync from Shopify. Used to detect stale content (>48h).';

COMMENT ON COLUMN kb_contents.related_links IS 
'JSON array of related resources: [{"title": "...", "url": "..."}]';

COMMENT ON COLUMN kb_contents.metadata IS 
'Flexible JSON field for additional data: tags, priority, custom fields, etc.';

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Verify table creation
SELECT 
    table_name,
    table_type
FROM information_schema.tables
WHERE table_name = 'kb_contents';

-- Verify indexes (should show 7 indexes)
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'kb_contents'
ORDER BY indexname;

-- Verify columns (should show 17 columns)
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'kb_contents'
ORDER BY ordinal_position;

-- Verify triggers (should show 1 trigger)
SELECT 
    trigger_name,
    event_manipulation,
    event_object_table
FROM information_schema.triggers
WHERE event_object_table = 'kb_contents';

-- ============================================================================
-- SUCCESS MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 001 completed successfully!';
    RAISE NOTICE 'Table: kb_contents created';
    RAISE NOTICE 'Indexes: 7 created';
    RAISE NOTICE 'Triggers: 1 created';
    RAISE NOTICE '========================================';
END $$;

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================