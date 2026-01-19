-- ============================================================================
-- Migration: 001_shopify_kb_buffer.sql
-- Description: Creates the Knowledge Base buffer table for Shopify CMS sync
-- Author: Retail Recommender System Team
-- Date: 2026-01-11
-- ============================================================================

-- ----------------------------------------------------------------------------
-- TABLE: kb_contents
-- Purpose: Buffer/cache layer for Shopify CMS Knowledge Base pages
-- 
-- Architecture:
--   Shopify CMS (Source of Truth)
--        -> Webhooks + Polling
--   Sync Service (FastAPI)
--        -> Parse + Transform
--   PostgreSQL Buffer (48h cache) <- THIS TABLE
--        -> Fast access
--   Redis Cache (24h hot cache)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS kb_contents (
    -- ========================================================================
    -- PRIMARY KEY & IDENTIFICATION
    -- ========================================================================
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- ========================================================================
    -- KNOWLEDGE BASE METADATA
    -- ========================================================================
    
    -- Intent classification (maps to InformationalSubIntent enum)
    sub_intent VARCHAR(50) NOT NULL,
    
    -- Language code (ISO 639-1: "es", "en", "pt", etc.)
    language VARCHAR(5) NOT NULL DEFAULT 'es',
    
    -- Optional category for product-specific content
    -- Examples: "ZAPATOS", "VESTIDOS", "ACCESORIOS", "general", NULL
    category VARCHAR(50),
    
    -- ========================================================================
    -- CONTENT (Multiple formats for flexibility)
    -- ========================================================================
    
    -- Primary content (Markdown format from Shopify)
    content TEXT NOT NULL,
    
    -- HTML version (if needed for direct rendering)
    content_html TEXT,
    
    -- Page title (for SEO, display)
    title VARCHAR(500),
    
    -- SEO meta description
    meta_description TEXT,
    
    -- ========================================================================
    -- SHOPIFY SYNC METADATA
    -- ========================================================================
    
    -- Shopify Page ID (for tracking source)
    shopify_page_id BIGINT NOT NULL,
    
    -- Shopify Page URL (for reference)
    shopify_url VARCHAR(500),
    
    -- Shopify Page handle (URL-friendly identifier)
    shopify_handle VARCHAR(200),
    
    -- Last sync timestamp from Shopify
    last_synced TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- ========================================================================
    -- CACHE METADATA
    -- ========================================================================
    
    -- Record creation timestamp
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Last update timestamp (updated on sync)
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Cache version (incremented on updates, for invalidation)
    cache_version INTEGER NOT NULL DEFAULT 1,
    
    -- ========================================================================
    -- EXTENDED DATA (JSON for flexibility)
    -- ========================================================================
    
    -- Related links/resources
    -- Example: [{"title": "Start Return", "url": "/account/returns"}]
    related_links JSONB,
    
    -- Additional metadata (tags, custom fields, etc.)
    -- Example: {"tags": ["policy", "important"], "priority": "high"}
    metadata JSONB,
    
    -- ========================================================================
    -- CONSTRAINTS
    -- ========================================================================
    
    -- Unique constraint: One content per (sub_intent, language, category)
    -- This ensures no duplicates and enables efficient upserts
    CONSTRAINT unique_kb_content UNIQUE(sub_intent, language, COALESCE(category, 'general'))
);

-- ----------------------------------------------------------------------------
-- INDEXES
-- Performance optimization for common query patterns
-- ----------------------------------------------------------------------------

-- Primary lookup index (most common query)
-- Used by: get_kb_answer(sub_intent, language, category)
CREATE INDEX IF NOT EXISTS idx_kb_lookup 
    ON kb_contents(sub_intent, language, category)
    WHERE category IS NOT NULL;

-- Shopify ID lookup (for webhook processing)
-- Used by: sync service to find existing records
CREATE INDEX IF NOT EXISTS idx_kb_shopify_id 
    ON kb_contents(shopify_page_id);

-- Sync status monitoring (for staleness checks)
-- Used by: background jobs to identify stale content
CREATE INDEX IF NOT EXISTS idx_kb_sync_status 
    ON kb_contents(last_synced DESC);

-- Language-specific queries (for multi-language support)
-- Used by: language-specific content retrieval
CREATE INDEX IF NOT EXISTS idx_kb_language 
    ON kb_contents(language, sub_intent);

-- Category-specific queries
-- Used by: product-category specific content
CREATE INDEX IF NOT EXISTS idx_kb_category 
    ON kb_contents(category)
    WHERE category IS NOT NULL;

-- Full-text search on content (optional, for future search feature)
-- CREATE INDEX IF NOT EXISTS idx_kb_content_search 
--     ON kb_contents USING gin(to_tsvector('spanish', content));

-- ----------------------------------------------------------------------------
-- TRIGGERS
-- Automatic timestamp management
-- ----------------------------------------------------------------------------

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_kb_contents_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.cache_version = OLD.cache_version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update timestamp on UPDATE
CREATE TRIGGER kb_contents_update_timestamp
    BEFORE UPDATE ON kb_contents
    FOR EACH ROW
    EXECUTE FUNCTION update_kb_contents_timestamp();

-- ----------------------------------------------------------------------------
-- COMMENTS (Documentation)
-- ----------------------------------------------------------------------------

COMMENT ON TABLE kb_contents IS 
'Knowledge Base content buffer synced from Shopify CMS. Acts as performance cache and resilience layer.';

COMMENT ON COLUMN kb_contents.sub_intent IS 
'Maps to InformationalSubIntent enum (e.g., policy_return, policy_shipping, product_material)';

COMMENT ON COLUMN kb_contents.language IS 
'ISO 639-1 language code (es, en, pt). Primary language from Shopify Markets.';

COMMENT ON COLUMN kb_contents.category IS 
'Optional product category for context-specific content (e.g., ZAPATOS for shoes-specific return policy)';

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

-- ----------------------------------------------------------------------------
-- VERIFICATION
-- ----------------------------------------------------------------------------

-- Verify table creation
SELECT 
    table_name,
    table_type
FROM information_schema.tables
WHERE table_name = 'kb_contents';

-- Verify indexes
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'kb_contents'
ORDER BY indexname;

-- Verify columns
SELECT 
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'kb_contents'
ORDER BY ordinal_position;

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
