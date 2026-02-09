"""
Unit Tests for shopify_kb_client.py Structured Logging
=======================================================

Tests that validate structured logging events in ShopifyKBClient.

Author: Retail Recommender System Team
Date: 2026-02-06
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from conftest import assert_event_logged, assert_error_logged

from src.api.integrations.shopify_kb_client import (
    ShopifyKBClient,
    KBMetadataParser
)
from src.api.core.models.kb_models import ShopifyPage


# ══════════════════════════════════════════════════════════════════════════
# INITIALIZATION TESTS
# ══════════════════════════════════════════════════════════════════════════

def test_init_logs_client_initialized(log_capture):
    """Test that __init__ logs shopify_kb_client_initialized event."""
    # Arrange & Act
    client = ShopifyKBClient(
        shop_url="test.myshopify.com",
        access_token="test_token",
        webhook_secret="test_secret"
    )
    
    # Assert
    assert_event_logged(
        log_capture,
        "shopify_kb_client_initialized",
        {
            "shop_url": "test.myshopify.com",
            "webhook_validation_enabled": True
        }
    )


def test_init_logs_webhook_disabled(log_capture):
    """Test __init__ logs webhook_validation_enabled=False when no secret."""
    # Arrange & Act
    client = ShopifyKBClient(
        shop_url="test.myshopify.com",
        access_token="test_token",
        webhook_secret=None
    )
    
    # Assert
    event = log_capture.get_event("shopify_kb_client_initialized")
    assert event["webhook_validation_enabled"] is False


# ══════════════════════════════════════════════════════════════════════════
# IS_KB_PAGE TESTS
# ══════════════════════════════════════════════════════════════════════════

def test_is_kb_page_logs_invalid_type(log_capture, sample_shopify_page):
    """Test is_kb_page logs warning for invalid metadata type."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    # Act
    result = client.is_kb_page(
        sample_shopify_page,
        {"custom.kb_metadata": "not_a_dict"}  # Invalid type
    )
    
    # Assert
    assert result is False
    assert_event_logged(
        log_capture,
        "shopify_kb_metadata_invalid_type",
        {
            "page_id": sample_shopify_page.id,
            "actual_type": "str"
        }
    )


def test_is_kb_page_logs_missing_sub_intent(log_capture, sample_shopify_page):
    """Test is_kb_page logs warning for missing sub_intent."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    # CORRECTO: Usar dict con contenido
    # NOTA: Usar dict con contenido, no vacío {}
# {} es falsy en Python y causaría return temprano en is_kb_page
    metafields = {
        "custom.kb_metadata": {
            "category": "general",  # Tiene contenido pero NO sub_intent
            "language": "es"
        }
    }

    result = client.is_kb_page(sample_shopify_page, metafields)

    # Assert
    assert result is False
    assert_event_logged(
        log_capture,
        "shopify_kb_metadata_missing_sub_intent",
        {"page_id": sample_shopify_page.id}
    )


def test_is_kb_page_logs_empty_body(log_capture):
    """Test is_kb_page logs info for empty body_html."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    page = ShopifyPage(
        id=123,
        title="Test",
        body_html="   ",  # Empty
        handle="test",
        created_at="2024-01-01",
        updated_at="2024-01-01"
    )
    
    # Act
    result = client.is_kb_page(
        page,
        {"custom.kb_metadata": {"sub_intent": "test"}}
    )
    
    # Assert
    assert result is False
    assert_event_logged(
        log_capture,
        "shopify_kb_page_skipped_empty_body",
        {"page_id": 123}
    )


# ══════════════════════════════════════════════════════════════════════════
# GET_KB_PAGES TESTS
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_kb_pages_logs_fetch_started(log_capture):
    """Test get_kb_pages logs fetch_started event."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    with patch.object(client, 'get_pages', new_callable=AsyncMock) as mock_get_pages:
        mock_get_pages.return_value = []
        
        # Act
        await client.get_kb_pages(limit=10, validate_metadata=True)
        
        # Assert
        assert_event_logged(
            log_capture,
            "shopify_kb_pages_fetch_started",
            {
                "limit": 10,
                "validate_metadata": True
            }
        )


@pytest.mark.asyncio
async def test_get_kb_pages_logs_pages_retrieved(log_capture):
    """Test get_kb_pages logs pages_retrieved event."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    mock_pages = [
        {"id": 1, "title": "Page 1", "body_html": "<p>test</p>", "handle": "p1"},
        {"id": 2, "title": "Page 2", "body_html": "<p>test</p>", "handle": "p2"}
    ]
    
    with patch.object(client, 'get_pages', new_callable=AsyncMock) as mock_get_pages:
        mock_get_pages.return_value = mock_pages
        with patch.object(client, 'get_page_metafields', new_callable=AsyncMock) as mock_meta:
            mock_meta.return_value = {}
            
            # Act
            await client.get_kb_pages()
            
            # Assert
            assert_event_logged(
                log_capture,
                "shopify_pages_retrieved",
                {"total_pages": 2}
            )


@pytest.mark.asyncio
async def test_get_kb_pages_logs_parse_error(log_capture):
    """Test get_kb_pages logs parse error for invalid page data."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    mock_pages = [
        {"id": 1},  # Missing required fields
    ]
    
    with patch.object(client, 'get_pages', new_callable=AsyncMock) as mock_get_pages:
        mock_get_pages.return_value = mock_pages
        
        # Act
        await client.get_kb_pages()
        
        # Assert
        assert log_capture.has_event("shopify_page_parse_error")


# ══════════════════════════════════════════════════════════════════════════
# GET_PAGE_BY_ID TESTS
# ══════════════════════════════════════════════════════════════════════════

def test_get_page_by_id_logs_fetch(log_capture):
    """Test get_page_by_id logs fetch event."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    with patch.object(client, '_make_request_with_retry') as mock_request:
        mock_request.return_value.json.return_value = {
            "page": {
                "id": 123,
                "title": "Test",
                "body_html": "<p>test</p>",
                "handle": "test",
                "created_at": "2024-01-01",
                "updated_at": "2024-01-01"
            }
        }
        
        # Act
        client.get_page_by_id(123)
        
        # Assert
        assert_event_logged(
            log_capture,
            "shopify_page_fetch_by_id",
            {"page_id": 123}
        )
        assert_event_logged(
            log_capture,
            "shopify_page_fetched",
            {"page_id": 123}
        )


def test_get_page_by_id_logs_error(log_capture):
    """Test get_page_by_id logs error event."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    with patch.object(client, '_make_request_with_retry') as mock_request:
        mock_request.side_effect = Exception("API Error")
        
        # Act
        result = client.get_page_by_id(123)
        
        # Assert
        assert result is None
        assert_error_logged(
            log_capture,
            "shopify_page_fetch_error",
            with_exc_info=True
        )


# ══════════════════════════════════════════════════════════════════════════
# TRANSLATIONS TESTS
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_page_translations_logs_no_locales(log_capture):
    """Test get_page_translations logs when no translation locales available."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    with patch.object(client, '_get_shop_locales', new_callable=AsyncMock) as mock_locales:
        mock_locales.return_value = ("es", [])  # No translation locales
        
        # Act
        result = await client.get_page_translations(123)
        
        # Assert
        assert result == {}
        assert_event_logged(
            log_capture,
            "shopify_no_translation_locales",
            {
                "page_id": 123,
                "primary_locale": "es"
            }
        )


@pytest.mark.asyncio
async def test_get_page_translations_logs_cache_hit(log_capture):
    """Test _get_shop_locales logs cache hit."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    
    # Pre-populate cache
    client._cached_locales = ("es", ["en"])
    from datetime import datetime, timedelta
    client._locales_cache_expires_at = datetime.utcnow() + timedelta(hours=1)
    
    log_capture.clear()
    
    # Act
    result = await client._get_shop_locales()
    
    # Assert
    assert result == ("es", ["en"])
    assert_event_logged(
        log_capture,
        "shopify_locales_cache_hit"
    )


# ══════════════════════════════════════════════════════════════════════════
# WEBHOOK VALIDATION TESTS
# ══════════════════════════════════════════════════════════════════════════

def test_validate_webhook_logs_disabled(log_capture):
    """Test validate_webhook logs warning when validation disabled."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token", webhook_secret=None)
    log_capture.clear()
    
    # Act
    result = client.validate_webhook(b"test_data", "test_hmac")
    
    # Assert
    assert result is True
    assert_event_logged(
        log_capture,
        "shopify_webhook_validation_disabled",
        {"reason": "webhook_secret_not_configured"}
    )


def test_validate_webhook_logs_invalid_hmac(log_capture):
    """Test validate_webhook logs error for invalid HMAC."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token", webhook_secret="secret")
    log_capture.clear()
    
    # Act
    result = client.validate_webhook(b"test_data", "invalid_hmac")
    
    # Assert
    assert result is False
    assert log_capture.has_event("shopify_webhook_invalid_hmac")


# ══════════════════════════════════════════════════════════════════════════
# CACHE INVALIDATION TESTS
# ══════════════════════════════════════════════════════════════════════════

def test_invalidate_locales_cache_logs(log_capture):
    """Test invalidate_locales_cache logs event."""
    # Arrange
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    # Act
    client.invalidate_locales_cache()
    
    # Assert
    assert_event_logged(
        log_capture,
        "shopify_locales_cache_invalidated"
    )