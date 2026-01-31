-- ============================================================================
-- MIGRATION: Create kb_content table for Knowledge Base v2
-- ============================================================================
-- 
-- Purpose: Create table structure for Shopify Knowledge Base multi-language
-- Author: Retail Recommender System Team
-- Date: 2026-01-30
-- Version: 1.0
--
-- Requirements:
-- - PostgreSQL 12+
-- - Database: retail_recommender_db (or your database name)
-- - User with CREATE TABLE permissions
--
-- ============================================================================

-- Drop table if exists (CAUTION: Use only in development)
-- DROP TABLE IF EXISTS kb_content CASCADE;

-- Create kb_content table
CREATE TABLE IF NOT EXISTS kb_content (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Content identification
    sub_intent VARCHAR(100) NOT NULL,
    language VARCHAR(10) DEFAULT 'es',
    category VARCHAR(100),
    
    -- Content data
    content TEXT NOT NULL,
    content_html TEXT,
    title VARCHAR(500),
    
    -- Shopify metadata
    shopify_page_id BIGINT NOT NULL,
    shopify_url VARCHAR(500),
    shopify_handle VARCHAR(200),
    
    -- Timestamps
    last_synced TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Unique constraint: one entry per (sub_intent, language, category)
    CONSTRAINT uk_kb_content_intent_lang_cat 
        UNIQUE(sub_intent, language, COALESCE(category, 'general'))
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_kb_content_sub_intent ON kb_content(sub_intent);
CREATE INDEX IF NOT EXISTS idx_kb_content_language ON kb_content(language);
CREATE INDEX IF NOT EXISTS idx_kb_content_category ON kb_content(category);
CREATE INDEX IF NOT EXISTS idx_kb_content_last_synced ON kb_content(last_synced);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_kb_content_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trg_kb_content_updated_at ON kb_content;
CREATE TRIGGER trg_kb_content_updated_at
    BEFORE UPDATE ON kb_content
    FOR EACH ROW
    EXECUTE FUNCTION update_kb_content_updated_at();

-- Insert sample data for testing (OPTIONAL)
-- Uncomment these lines if you want test data

-- English - Return Policy
INSERT INTO kb_content (
    sub_intent, language, category,
    content, title,
    shopify_page_id, shopify_url, shopify_handle
) VALUES (
    'policy_return', 'en', 'general',
    E'# Return Policy\n\nWe offer a **30-day return policy** for all items.\n\n## Conditions:\n- Items must be in original condition\n- Include original packaging\n- Proof of purchase required\n\n## Process:\n1. Contact customer service\n2. Receive return authorization\n3. Ship item back\n4. Refund processed within 5-7 business days',
    'Return Policy - 30 Days',
    1001, 'https://store.example.com/pages/return-policy', 'return-policy'
) ON CONFLICT (sub_intent, language, COALESCE(category, 'general')) DO UPDATE SET
    content = EXCLUDED.content,
    last_synced = NOW();

-- Spanish - Política de Devoluciones
INSERT INTO kb_content (
    sub_intent, language, category,
    content, title,
    shopify_page_id, shopify_url, shopify_handle
) VALUES (
    'policy_return', 'es', 'general',
    E'# Política de Devoluciones\n\nOfrecemos una **política de devoluciones de 30 días** para todos los artículos.\n\n## Condiciones:\n- Los artículos deben estar en su condición original\n- Incluir empaque original\n- Se requiere comprobante de compra\n\n## Proceso:\n1. Contacte al servicio al cliente\n2. Reciba la autorización de devolución\n3. Envíe el artículo de vuelta\n4. Reembolso procesado en 5-7 días hábiles',
    'Política de Devoluciones - 30 Días',
    1002, 'https://store.example.com/es/pages/politica-devoluciones', 'politica-devoluciones'
) ON CONFLICT (sub_intent, language, COALESCE(category, 'general')) DO UPDATE SET
    content = EXCLUDED.content,
    last_synced = NOW();

-- English - Shipping Policy
INSERT INTO kb_content (
    sub_intent, language, category,
    content, title,
    shopify_page_id, shopify_url, shopify_handle
) VALUES (
    'policy_shipping', 'en', 'general',
    E'# Shipping Policy\n\nWe offer **free shipping** on orders over $50.\n\n## Delivery Times:\n- Standard: 5-7 business days\n- Express: 2-3 business days\n- International: 10-15 business days\n\n## Tracking:\nYou will receive a tracking number via email once your order ships.',
    'Shipping Policy',
    1003, 'https://store.example.com/pages/shipping-policy', 'shipping-policy'
) ON CONFLICT (sub_intent, language, COALESCE(category, 'general')) DO UPDATE SET
    content = EXCLUDED.content,
    last_synced = NOW();

-- Spanish - Política de Envíos
INSERT INTO kb_content (
    sub_intent, language, category,
    content, title,
    shopify_page_id, shopify_url, shopify_handle
) VALUES (
    'policy_shipping', 'es', 'general',
    E'# Política de Envíos\n\nOfrecemos **envío gratis** en pedidos superiores a $50.\n\n## Tiempos de Entrega:\n- Estándar: 5-7 días hábiles\n- Express: 2-3 días hábiles\n- Internacional: 10-15 días hábiles\n\n## Rastreo:\nRecibirá un número de rastreo por email una vez que su pedido sea enviado.',
    'Política de Envíos',
    1004, 'https://store.example.com/es/pages/politica-envios', 'politica-envios'
) ON CONFLICT (sub_intent, language, COALESCE(category, 'general')) DO UPDATE SET
    content = EXCLUDED.content,
    last_synced = NOW();

-- Verification query
SELECT 
    sub_intent,
    language,
    category,
    LEFT(content, 50) as content_preview,
    title
FROM kb_content
ORDER BY sub_intent, language;

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- 
-- Verify with:
-- SELECT language, COUNT(*) FROM kb_content GROUP BY language;
--
-- Expected output:
-- language | count
-- ---------+-------
-- en       |     2
-- es       |     2
--
-- ============================================================================