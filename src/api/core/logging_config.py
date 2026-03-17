"""
Structured Logging Configuration
==================================

Configuración centralizada de structured logging usando structlog.

Este módulo proporciona:
1. JSON logging para producción (parseable por ELK, Datadog, Splunk)
2. Pretty printing para desarrollo local
3. Contexto automático (timestamp, level, logger_name)
4. Thread-safe y async-safe
5. Integration con Python logging standard

Author: Retail Recommender System Team
Date: 2026-02-05
Version: 1.0.0 - Initial Implementation (FASE 0 - H1)
"""

import sys
import logging
import structlog
from typing import Any, Dict
from pythonjsonlogger import jsonlogger


# ══════════════════════════════════════════════════════════════════════════
# CONFIGURATION CONSTANTS
# ══════════════════════════════════════════════════════════════════════════

DEFAULT_LOG_LEVEL = "INFO"
JSON_FORMAT = True  # Set to False for development (pretty printing)


# ══════════════════════════════════════════════════════════════════════════
# CUSTOM PROCESSORS
# ══════════════════════════════════════════════════════════════════════════

def add_app_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Add application-specific context to every log entry.
    
    Adds:
    - app_name: "retail-recommender"
    - environment: from ENV var or "development"
    - version: from config or "unknown"
    
    Args:
        logger: Python logger instance
        method_name: Logging method name (info, error, etc)
        event_dict: Current log event dictionary
        
    Returns:
        Updated event_dict with app context
        
    Example Output:
    ---------------
    {
        "event": "kb_sync_started",
        "app_name": "retail-recommender",
        "environment": "production",
        "version": "v2.1.0",
        "timestamp": "2026-02-05T10:30:45.123456Z",
        ...
    }
    """
    import os
    
    event_dict["app_name"] = "retail-recommender"
    event_dict["environment"] = os.getenv("ENVIRONMENT", "development")
    event_dict["version"] = os.getenv("APP_VERSION", "v2.1.0")
    
    return event_dict


def add_severity_level(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Add severity level for better filtering in logging platforms.
    
    Maps Python log levels to severity:
    - DEBUG → DEBUG
    - INFO → INFO
    - WARNING → WARNING
    - ERROR → ERROR
    - CRITICAL → CRITICAL
    
    Args:
        logger: Python logger instance
        method_name: Logging method name
        event_dict: Current log event dictionary
        
    Returns:
        Updated event_dict with severity field
    """
    if "level" in event_dict:
        event_dict["severity"] = event_dict["level"].upper()
    
    return event_dict


# ══════════════════════════════════════════════════════════════════════════
# STRUCTLOG CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════

def configure_structlog(
    log_level: str = DEFAULT_LOG_LEVEL,
    json_format: bool = JSON_FORMAT
) -> None:
    """
    Configure structlog for structured logging.
    
    This function sets up:
    1. Processors pipeline (add context, format timestamps, etc)
    2. JSON output for production OR pretty print for development
    3. Integration with Python standard logging
    4. Thread-local context storage
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: If True, output JSON. If False, pretty print.
        
    Usage:
    ------
    ```python
    # In main.py or __init__.py:
    from src.api.core.logging_config import configure_structlog
    
    configure_structlog(log_level="INFO", json_format=True)
    
    # Then in any module:
    import structlog
    logger = structlog.get_logger(__name__)
    
    logger.info(
        "kb_sync_completed",
        successful=10,
        failed=0,
        duration_ms=1234
    )
    ```
    
    Output (JSON format):
    ---------------------
    {
        "event": "kb_sync_completed",
        "successful": 10,
        "failed": 0,
        "duration_ms": 1234,
        "timestamp": "2026-02-05T10:30:45.123456Z",
        "level": "info",
        "logger": "src.api.services.shopify_kb_sync",
        "app_name": "retail-recommender",
        "environment": "production",
        "version": "v2.1.0"
    }
    
    Output (Pretty format for development):
    ---------------------------------------
    2026-02-05 10:30:45 [info     ] kb_sync_completed
        successful=10 failed=0 duration_ms=1234
        logger=src.api.services.shopify_kb_sync
    """
    
    # ──────────────────────────────────────────────────────────────────────
    # Configure Python standard logging
    # ──────────────────────────────────────────────────────────────────────
    # NOTE: We do NOT use logging.basicConfig() here.
    # basicConfig() adds a second StreamHandler to the root logger, which
    # causes every log event to be emitted TWICE:
    #   - Once via basicConfig's handler (raw dict string, unformatted)
    #   - Once via our ProcessorFormatter handler (structlog-formatted)
    # Instead, we configure the root logger directly and clear any
    # pre-existing handlers (e.g., those added by uvicorn on startup)
    # before attaching our single structlog handler.
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear ALL existing handlers from root logger to avoid duplicates.
    # This is safe because we are the authoritative logging configurator
    # for this application — uvicorn's own access/error loggers use child
    # loggers ("uvicorn", "uvicorn.access") and are unaffected by this.
    root_logger.handlers.clear()
    
    # ──────────────────────────────────────────────────────────────────────
    # Configure structlog processors pipeline
    # ──────────────────────────────────────────────────────────────────────
    
    shared_processors = [
        # Add log level to event dict
        structlog.stdlib.add_log_level,
        
        # Add logger name to event dict
        structlog.stdlib.add_logger_name,
        
        # Add timestamp (ISO 8601 format with timezone)
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        
        # Add app-specific context
        add_app_context,
        
        # Add severity level
        add_severity_level,
        
        # Add exception info if present
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        
        # Decode unicode escape sequences
        structlog.processors.UnicodeDecoder(),
    ]
    
    # ──────────────────────────────────────────────────────────────────────
    # Choose renderer based on format preference
    # ──────────────────────────────────────────────────────────────────────
    
    if json_format:
        # JSON renderer for production (parseable by logging platforms)
        renderer = structlog.processors.JSONRenderer()
    else:
        # Pretty console renderer for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    # ──────────────────────────────────────────────────────────────────────
    # Configure structlog
    # ──────────────────────────────────────────────────────────────────────
    
    structlog.configure(
        processors=shared_processors + [
            # Filter by log level
            structlog.stdlib.filter_by_level,
            
            # Positional args handling
            structlog.stdlib.PositionalArgumentsFormatter(),
            
            # Prepare for stdlib integration
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        
        # Context class for thread-local storage
        context_class=dict,
        
        # Logger factory (use stdlib)
        logger_factory=structlog.stdlib.LoggerFactory(),
        
        # Cache loggers for performance
        cache_logger_on_first_use=True,
    )
    
    # ──────────────────────────────────────────────────────────────────────
    # Configure Python logging to use structlog formatter
    # ──────────────────────────────────────────────────────────────────────
    
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    
    # Attach the single structlog-formatted handler to the root logger.
    # All application loggers inherit from root, so this one handler
    # covers every logger in the system — no duplicate output.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


# ══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def get_logger(name: str = None) -> structlog.BoundLogger:
    """
    Get a structured logger instance.
    
    This is a convenience wrapper around structlog.get_logger()
    that ensures consistent logger creation across the application.
    
    Args:
        name: Logger name (typically __name__ of the module)
              If None, uses calling module's name automatically
        
    Returns:
        Configured structlog.BoundLogger instance
        
    Usage:
    ------
    ```python
    from src.api.core.logging_config import get_logger
    
    logger = get_logger(__name__)
    
    logger.info(
        "operation_started",
        operation_id="abc-123",
        user_id="user-456"
    )
    ```
    """
    return structlog.get_logger(name)


# ══════════════════════════════════════════════════════════════════════════
# CONTEXT MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════

def bind_context(**kwargs: Any) -> None:
    """
    Bind context variables to all subsequent log entries in current thread/task.
    
    This adds key-value pairs to the logging context that will be
    automatically included in all log entries until cleared.
    
    Useful for:
    - Request ID tracking across multiple log entries
    - User ID for all operations in a request
    - Transaction ID for distributed tracing
    
    Args:
        **kwargs: Key-value pairs to bind to context
        
    Usage:
    ------
    ```python
    from src.api.core.logging_config import bind_context, get_logger
    
    logger = get_logger(__name__)
    
    # Bind request context
    bind_context(
        request_id="req-abc-123",
        user_id="user-456",
        market="US"
    )
    
    # All subsequent logs will include request_id, user_id, market
    logger.info("processing_started")
    # → {"event": "processing_started", "request_id": "req-abc-123", ...}
    
    logger.info("processing_completed", items_processed=10)
    # → {"event": "processing_completed", "request_id": "req-abc-123", 
    #    "items_processed": 10, ...}
    ```
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """
    Remove specific keys from logging context.
    
    Args:
        *keys: Keys to remove from context
        
    Usage:
    ------
    ```python
    unbind_context("request_id", "user_id")
    ```
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """
    Clear all context variables.
    
    Useful for:
    - Cleanup after request processing
    - Resetting context in tests
    - Starting fresh context for new operation
    
    Usage:
    ------
    ```python
    from src.api.core.logging_config import clear_context
    
    # After request completes
    clear_context()
    ```
    """
    structlog.contextvars.clear_contextvars()


# ══════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS FOR COMMON PATTERNS
# ══════════════════════════════════════════════════════════════════════════

def log_function_call(
    logger: structlog.BoundLogger,
    function_name: str,
    **kwargs: Any
) -> None:
    """
    Log a function call with standardized format.
    
    Args:
        logger: Structlog logger instance
        function_name: Name of function being called
        **kwargs: Function arguments to log
        
    Usage:
    ------
    ```python
    def sync_page(page_id: int, language: str):
        log_function_call(
            logger,
            "sync_page",
            page_id=page_id,
            language=language
        )
        # ... function logic
    ```
    """
    logger.debug(
        "function_called",
        function=function_name,
        **kwargs
    )


def log_performance(
    logger: structlog.BoundLogger,
    operation: str,
    duration_ms: float,
    **kwargs: Any
) -> None:
    """
    Log performance metrics with standardized format.
    
    Args:
        logger: Structlog logger instance
        operation: Operation name
        duration_ms: Duration in milliseconds
        **kwargs: Additional metrics
        
    Usage:
    ------
    ```python
    import time
    
    start = time.time()
    # ... do work
    duration = (time.time() - start) * 1000
    
    log_performance(
        logger,
        "kb_sync",
        duration_ms=duration,
        pages_synced=13,
        errors=0
    )
    ```
    """
    logger.info(
        "performance_metric",
        operation=operation,
        duration_ms=round(duration_ms, 2),
        **kwargs
    )


# ══════════════════════════════════════════════════════════════════════════
# AUTO-CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════

# NOTE: Do NOT auto-configure on import
# Let the application configure explicitly in main.py or __init__.py
# This prevents side effects during testing and allows customization

if __name__ == "__main__":
    # Example usage when running this module directly
    configure_structlog(log_level="INFO", json_format=False)
    
    logger = get_logger(__name__)
    
    logger.info(
        "example_log_entry",
        operation="test",
        status="success",
        count=42
    )
    
    # With context
    bind_context(request_id="req-123", user_id="user-456")
    logger.info("another_log_with_context")
    
    clear_context()
    logger.info("log_after_context_cleared")