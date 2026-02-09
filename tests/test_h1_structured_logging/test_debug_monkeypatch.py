"""
Debug Test for Monkeypatch Approach - H1 Structured Logging
============================================================

This test validates that the monkeypatch approach works correctly.
It's marked with @pytest.mark.debug to exclude it from CI runs.

Author: Retail Recommender System Team
Date: 2026-02-06
"""

import pytest


@pytest.mark.debug
def test_monkeypatch_captures_events(log_capture):
    """
    Debug test: Validate monkeypatch approach captures events correctly.
    
    This test:
    1. Imports module INSIDE test (after fixture setup)
    2. Creates client and page
    3. Calls is_kb_page with missing sub_intent
    4. Validates event was captured
    """
    # Import INSIDE test - AFTER fixture has setup monkeypatch
    from src.api.integrations.shopify_kb_client import ShopifyKBClient
    from src.api.core.models.kb_models import ShopifyPage
    
    # Create page
    page = ShopifyPage(
        id=123456789,
        title="Test Page",
        body_html="<p>Test content</p>",
        handle="test-page",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z"
    )
    
    # Create client
    client = ShopifyKBClient("test.myshopify.com", "token")
    
    # Clear init event
    log_capture.clear()
    
    # Call is_kb_page with metafields that have content but miss sub_intent
    result = client.is_kb_page(
        page,
        {"custom.kb_metadata": {"category": "general"}}
    )
    
    # Validate
    assert result is False
    assert log_capture.has_event('shopify_kb_metadata_missing_sub_intent'), \
        f"Event not found. Events captured: {[e.get('event') for e in log_capture.events]}"


@pytest.mark.debug
def test_direct_logger_access(log_capture):
    """
    Debug test: Validate direct logger access works.
    
    This test verifies that calling the logger directly
    (without going through ShopifyKBClient) works correctly.
    """
    # Import module INSIDE test
    import src.api.integrations.shopify_kb_client as kb_module
    
    # Clear any existing events
    log_capture.clear()
    
    # Call logger directly
    kb_module.logger.info('test_direct_event', test_field='test_value')
    
    # Validate
    assert len(log_capture.events) == 1
    assert log_capture.has_event('test_direct_event')
    
    event = log_capture.get_event('test_direct_event')
    assert event['test_field'] == 'test_value'


@pytest.mark.debug 
def test_empty_dict_gotcha_documented(log_capture):
    """
    Debug test: Document the empty dict gotcha.
    
    EDGE CASE DOCUMENTATION:
    Empty dict {} is falsy in Python, causing early return in is_kb_page.
    This is INTENTIONAL behavior - empty metadata should fail fast.
    
    This test documents this behavior to prevent future confusion.
    """
    from src.api.integrations.shopify_kb_client import ShopifyKBClient
    from src.api.core.models.kb_models import ShopifyPage
    
    client = ShopifyKBClient("test.myshopify.com", "token")
    log_capture.clear()
    
    page = ShopifyPage(
        id=123,
        title="Test",
        body_html="<p>Content</p>",
        handle="test",
        created_at="2024-01-01",
        updated_at="2024-01-01"
    )
    
    # ACT: Empty dict should cause early return
    result = client.is_kb_page(page, {"custom.kb_metadata": {}})
    
    # ASSERT: Returns False AND no events logged
    assert result is False
    assert len(log_capture.events) == 0, \
        "Empty dict should cause early return BEFORE logging"


if __name__ == "__main__":
    pytest.main([__file__, "-xvs", "-m", "debug"])
