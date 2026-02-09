"""
Pytest Configuration and Fixtures for H1 Structured Logging Tests
==================================================================

Provides fixtures for capturing and validating structlog events.

Author: Retail Recommender System Team
Date: 2026-02-06
Version: 2.0 - Refactored with separation of concerns
"""

import pytest
import structlog
import sys
from unittest.mock import Mock, AsyncMock
from typing import List, Dict, Any, Optional, Generator


# ══════════════════════════════════════════════════════════════════════════
# STRUCTLOG CAPTURE - Encapsulated Logic
# ══════════════════════════════════════════════════════════════════════════

class StructlogCapture:
    """
    Encapsulates all logic for capturing structlog events in tests.
    
    This class handles:
    1. Creating a capturing BoundLogger subclass
    2. Monkeypatching structlog
    3. Reconfiguring structlog
    4. Forcing module reloads
    5. Providing helper methods for assertions
    
    Usage:
        capture = StructlogCapture()
        capture.setup(monkeypatch)
        
        # Your test code here
        logger.info("test_event", field="value")
        
        assert capture.has_event("test_event")
        capture.clear()
    """
    
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self._original_bound_logger = None
        self._capturing_class = None
    
    def setup(self, monkeypatch) -> None:
        """
        Setup structlog capture mechanism.
        
        This method:
        1. Creates CapturingBoundLogger subclass
        2. Monkeypatches structlog.stdlib.BoundLogger
        3. Reconfigures structlog to use the capturing class
        4. Forces reload of target modules
        
        Args:
            monkeypatch: pytest monkeypatch fixture
        """
        import structlog.stdlib
        
        # Store original for potential restoration
        self._original_bound_logger = structlog.stdlib.BoundLogger
        
        # Create capturing class with reference to this instance
        capture_instance = self
        
        class CapturingBoundLogger(self._original_bound_logger):
            """
            BoundLogger subclass that captures events before logging.
            
            This class intercepts _proxy_to_logger() which is the central
            method called by info(), warning(), error(), etc.
            """
            
            def _proxy_to_logger(self, method_name, event=None, **event_kw):
                """
                Intercept logging calls to capture events.
                
                Args:
                    method_name: Log level (info, warning, error, etc.)
                    event: Event name/message
                    **event_kw: Event fields
                """
                # Capture the event
                event_dict = {
                    "event": event,
                    "level": method_name,
                    **event_kw
                }
                capture_instance.events.append(event_dict)
                
                # Call parent to maintain normal logging
                return super()._proxy_to_logger(method_name, event, **event_kw)
        
        self._capturing_class = CapturingBoundLogger
        
        # Monkeypatch structlog.stdlib.BoundLogger
        monkeypatch.setattr(
            structlog.stdlib,
            'BoundLogger',
            CapturingBoundLogger
        )
        
        # Reconfigure structlog
        self._reconfigure_structlog()
        
        # Force module reloads
        self._force_module_reload()
    
    def _reconfigure_structlog(self) -> None:
        """
        Reconfigure structlog to use CapturingBoundLogger.
        
        Preserves existing configuration but replaces wrapper_class
        and disables caching.
        """
        config = structlog.get_config()
        
        structlog.configure(
            processors=config.get('processors', []),
            wrapper_class=self._capturing_class,
            context_class=config.get('context_class', dict),
            logger_factory=config.get('logger_factory'),
            cache_logger_on_first_use=False,  # Critical for testing
        )
    
    def _force_module_reload(self) -> None:
        """
        Force reload of modules that use structlog loggers.
        
        This ensures they use the new CapturingBoundLogger instead
        of cached logger instances.
        """
        modules_to_clear = [
            'src.api.integrations.shopify_kb_client',
        ]
        
        for module_name in modules_to_clear:
            if module_name in sys.modules:
                del sys.modules[module_name]
    
    # ──────────────────────────────────────────────────────────────────────
    # Query Methods
    # ──────────────────────────────────────────────────────────────────────
    
    def has_event(self, event_name: str) -> bool:
        """Check if an event was logged."""
        return any(e.get("event") == event_name for e in self.events)
    
    def get_event(self, event_name: str) -> Dict[str, Any]:
        """Get first event matching event_name."""
        for event in self.events:
            if event.get("event") == event_name:
                return event
        return {}
    
    def get_events(self, event_name: str) -> List[Dict[str, Any]]:
        """Get all events matching event_name."""
        return [e for e in self.events if e.get("event") == event_name]
    
    def clear(self) -> None:
        """Clear all captured events."""
        self.events.clear()


@pytest.fixture(scope='function')
# def log_capture(monkeypatch) -> StructlogCapture:
def log_capture(monkeypatch) -> Generator[StructlogCapture, None, None]:
    """
    Fixture that provides structlog event capture for tests.
    
    Usage:
        def test_something(log_capture):
            logger.info("test_event", field="value")
            assert log_capture.has_event("test_event")
    """
    capture = StructlogCapture()
    capture.setup(monkeypatch)
    yield capture
    capture.clear()


# ══════════════════════════════════════════════════════════════════════════
# TEST DATA FACTORIES
# ══════════════════════════════════════════════════════════════════════════

class MetafieldsFactory:
    """Factory for creating test metafields data."""
    
    @staticmethod
    def with_missing_sub_intent() -> Dict[str, Any]:
        """Metafields with content but missing required sub_intent field."""
        return {
            "custom.kb_metadata": {
                "category": "general",
                "language": "es"
            }
        }
    
    @staticmethod
    def with_invalid_type() -> Dict[str, Any]:
        """Metafields with invalid type (string instead of dict)."""
        return {
            "custom.kb_metadata": "not_a_dict"
        }
    
    @staticmethod
    def empty_dict() -> Dict[str, Any]:
        """
        Metafields with empty dict.
        Note: {} is falsy, causes early return before validation
        """
        return {
            "custom.kb_metadata": {}
        }
    
    @staticmethod
    def missing_metadata() -> Dict[str, Any]:
        """Metafields without kb_metadata field."""
        return {}
    
    @staticmethod
    def valid() -> Dict[str, Any]:
        """Valid KB metafields with all required fields."""
        return {
            "custom.kb_metadata": {
                "sub_intent": "policy_return",
                "category": "general",
                "language": "es"
            }
        }


@pytest.fixture
def metafields_factory() -> MetafieldsFactory:
    """Fixture providing metafields factory."""
    return MetafieldsFactory


# ══════════════════════════════════════════════════════════════════════════
# MOCK FIXTURES
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_redis_service() -> AsyncMock:
    """Mock RedisService for testing."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.health_check = AsyncMock(return_value={
        "status": "healthy",
        "ping_time_ms": 10.5
    })
    return redis


@pytest.fixture
def mock_db_pool() -> AsyncMock:
    """Mock PostgreSQL connection pool for testing."""
    pool = AsyncMock()
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    pool.acquire = AsyncMock(return_value=conn)
    pool.__aenter__ = AsyncMock(return_value=conn)
    pool.__aexit__ = AsyncMock()
    return pool


@pytest.fixture
def mock_shopify_client() -> Mock:
    """Mock ShopifyKBClient for testing."""
    client = Mock()
    client.get_kb_pages = AsyncMock(return_value=[])
    client.get_page_by_id = Mock(return_value=None)
    client.get_page_translations = AsyncMock(return_value={})
    client._get_shop_locales = AsyncMock(return_value=("es", ["en"]))
    return client


@pytest.fixture
def sample_shopify_page():
    """Sample ShopifyPage for testing."""
    from src.api.core.models.kb_models import ShopifyPage
    
    return ShopifyPage(
        id=123456789,
        title="Test Page",
        body_html="<p>Test content</p>",
        handle="test-page",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        published_at="2024-01-01T00:00:00Z",
        tags="kb, policy_return, general"
    )


# ══════════════════════════════════════════════════════════════════════════
# ASSERTION HELPERS
# ══════════════════════════════════════════════════════════════════════════

def assert_event_logged(
    log_capture: StructlogCapture,
    event_name: str,
    expected_fields: Optional[Dict[str, Any]] = None
) -> None:
    """Assert that an event was logged with expected fields."""
    assert log_capture.has_event(event_name), \
        f"Event '{event_name}' not found in captured events: " \
        f"{[e.get('event') for e in log_capture.events]}"
    
    if expected_fields:
        event = log_capture.get_event(event_name)
        for field_name, expected_value in expected_fields.items():
            assert field_name in event, \
                f"Field '{field_name}' not found in event '{event_name}'. " \
                f"Available fields: {list(event.keys())}"
            assert event[field_name] == expected_value, \
                f"Field '{field_name}' has value '{event[field_name]}', " \
                f"expected '{expected_value}'"


def assert_event_count(
    log_capture: StructlogCapture,
    event_name: str,
    expected_count: int
) -> None:
    """Assert that an event was logged exactly N times."""
    events = log_capture.get_events(event_name)
    actual_count = len(events)
    assert actual_count == expected_count, \
        f"Event '{event_name}' logged {actual_count} times, expected {expected_count}"


def assert_error_logged(
    log_capture: StructlogCapture,
    event_name: str,
    with_exc_info: bool = True
) -> None:
    """Assert that an error event was logged."""
    assert log_capture.has_event(event_name), \
        f"Error event '{event_name}' not found. " \
        f"Available events: {[e.get('event') for e in log_capture.events]}"
    
    event = log_capture.get_event(event_name)
    assert "error" in event or "error_type" in event, \
        f"Error event '{event_name}' missing error information. " \
        f"Available fields: {list(event.keys())}"
    
    if with_exc_info:
        assert event.get("exc_info") is True, \
            f"Error event '{event_name}' missing exc_info=True"
