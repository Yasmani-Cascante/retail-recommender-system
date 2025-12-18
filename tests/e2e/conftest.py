"""
E2E Tests Configuration and Shared Fixtures
=========================================================================

Provides shared fixtures and configuration for all E2E tests:
- FastAPI TestClient setup
- Redis connection management
- Mock factories configuration
- Test data seeding
- Performance tracking
- Cleanup utilities

Usage:
    All fixtures are automatically available to tests in tests/e2e/

Author: Senior Architecture Team
Date: Diciembre 2025
Version: 1.0.0 - Fase 3B
"""

import os
import sys
import asyncio
import pytest
import redis.asyncio as redis
from typing import AsyncGenerator, Generator, Dict, Any
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# Import application
from src.api.main_unified_redis import app
# from src.api.factories import ServiceFactory
from src.api.factories.service_factory import ServiceFactory
# from src.api.core.market_context_manager import MarketContextManager
from src.api.mcp.adapters.market_manager import MarketContextManager

from src.api.core.redis_service import RedisService

# Import mock factories
from tests.e2e.factories.api_mocks import (
    ClaudeAPIMockFactory,
    RetailAPIMockFactory,
    ShopifyAPIMockFactory,
    create_test_product_catalog
)


# ==============================================================================
# PYTEST CONFIGURATION
# ==============================================================================

def pytest_configure(config):
    """Configure pytest for E2E tests."""
    # Register custom markers
    config.addinivalue_line(
        "markers", "e2e: End-to-end test"
    )
    config.addinivalue_line(
        "markers", "smoke: Smoke test (critical path)"
    )
    config.addinivalue_line(
        "markers", "user_journey: Complete user journey test"
    )
    
    # Set test environment
    os.environ["ENV"] = "test"
    os.environ["ENABLE_TEST_MODE"] = "true"
    os.environ["ENABLE_MOCK_EXTERNAL_APIS"] = "true"


# ==============================================================================
# EVENT LOOP FIXTURES
# ==============================================================================

@pytest.fixture(scope="session")
# def event_loop() -> Generator:
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create event loop for async tests.
    
    Scope: session (reuse across all tests)
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# ==============================================================================
# FASTAPI APP WITH OVERRIDES - Required by mock_auth
# ==============================================================================

@pytest.fixture(scope="function")
def app_with_overrides() -> Generator[FastAPI, None, None]:
    """
    Get FastAPI app with dependency overrides.
    
    Allows tests to override dependencies with mocks.
    
    Scope: function (per test)
    
    Returns:
        FastAPI app instance
    """
    # Clear any existing overrides
    app.dependency_overrides.clear()
    
    yield app
    
    # Clean up overrides after test
    app.dependency_overrides.clear()


# ==============================================================================
# MOCK AUTH - Authentication bypass for E2E tests
# ==============================================================================

@pytest.fixture(scope="function")
def mock_auth(app_with_overrides: FastAPI):
    """
    Mock authentication for E2E tests.
    
    Overrides BOTH get_current_user AND get_api_key dependencies
    to allow tests to call authenticated endpoints without real API keys.
    
    IMPORTANT: Many endpoints require BOTH dependencies:
    - get_api_key: Validates API key header
    - get_current_user: Validates authenticated user
    
    Args:
        app_with_overrides: FastAPI app with clean overrides
    
    Yields:
        FastAPI app with mocked authentication
    """
    from src.api.security_auth import get_current_user, get_api_key  # ✅ Agregar get_api_key
    
    async def mock_get_current_user():
        """Mock authentication - always returns test_user"""
        return "test_user"
    
    async def mock_get_api_key():  # ✅ NUEVO
        """Mock API key - always returns valid test key"""
        return "test_api_key_2fed9999056fab6dac5654238f0cae1c"
    
    # Override dependency
    app_with_overrides.dependency_overrides[get_current_user] = mock_get_current_user
    app_with_overrides.dependency_overrides[get_api_key] = mock_get_api_key  # ✅ NUEVO
    
    logger.info("✅ Mock authentication activated - BOTH dependencies bypassed")
    
    yield app_with_overrides
    
    # Cleanup
    app_with_overrides.dependency_overrides.clear()
    logger.info("🧹 Mock authentication cleaned up")
    
# ==============================================================================
# REDIS FIXTURES
# ==============================================================================

# @pytest.fixture(scope="session")
@pytest.fixture(scope="function")
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """
    Create Redis client for E2E tests.
    
    Connects to Redis test instance (localhost:6380).
    
    Scope: session (shared across all tests)
    
    Yields:
        Redis client instance
    """
    # Connect to test Redis instance
    client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6380")),
        db=int(os.getenv("REDIS_DB", "0")),
        password=os.getenv("REDIS_PASSWORD", ""),
        decode_responses=True
    )
    
    # Verify connection
    try:
        await client.ping()
        print(f"\n✅ Redis connected: {os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6380')}")
    except Exception as e:
        pytest.fail(f"❌ Redis connection failed: {e}\nMake sure Redis is running: docker-compose -f docker-compose.test.yml up -d")
    
    yield client
    
    # Cleanup
    await client.close()


@pytest.fixture(scope="function")
async def clean_redis(redis_client: redis.Redis) -> AsyncGenerator[redis.Redis, None]:
    """
    Provide clean Redis instance for each test.
    
    Flushes Redis before and after each test to ensure isolation.
    
    Scope: function (per test)
    
    Yields:
        Redis client with clean state
    """
    # Clean before test
    await redis_client.flushdb()
    
    yield redis_client
    
    # Clean after test
    await redis_client.flushdb()


@pytest.fixture(scope="function")
async def redis_service(clean_redis: redis.Redis) -> AsyncGenerator[RedisService, None]:
    """
    Create RedisService instance for tests.
    
    Provides enterprise Redis service with connection pooling.
    
    Scope: function (per test)
    
    Yields:
        Configured RedisService instance
    """
    # service = RedisService(
    #     host=os.getenv("REDIS_HOST", "localhost"),
    #     port=int(os.getenv("REDIS_PORT", "6380")),
    #     db=int(os.getenv("REDIS_DB", "0")),
    #     pool_size=10,
    #     decode_responses=True
    # )
    
    # await service.connect()

    # ✅ Usar ServiceFactory (enterprise pattern)
    service = await ServiceFactory.get_redis_service()
    
    yield service
    # ✅ ServiceFactory maneja el cleanup automáticamente
    # await service.disconnect()


# ==============================================================================
# FASTAPI CLIENT FIXTURES
# ==============================================================================

@pytest.fixture(scope="function")
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Create AsyncClient for FastAPI testing.
    
    Provides HTTP client for making requests to FastAPI endpoints.
    
    Scope: function (per test)
    
    Yields:
        AsyncClient configured for testing
    """
    # async with AsyncClient(app=app, base_url="http://test") as client:
    async with AsyncClient(
    transport=ASGITransport(app=app),
    base_url="http://test"
    ) as client:
        
        yield client

# ==============================================================================
# ✅ FIXTURE CON WARMUP PARA TESTS E2E
# ==============================================================================
"""
SOLUCIÓN AL PROBLEMA: Tests E2E fallando con 503 "Catalog not loaded"

ROOT CAUSE:
- TFIDFRecommender tarda 2-3 segundos en cargar catálogo
- Tests hacen request inmediatamente
- Race condition: test ejecuta antes que catalog cargue

SOLUCIÓN:
- Fixture espera a que catálogo termine de cargar
- Usa health endpoint para verificar estado
- Timeout de 30 segundos con retry logic
- Logs informativos para debugging

INSTRUCCIONES:
1. Copiar este código a tests/e2e/conftest.py
2. Agregar después de la fixture test_client existente
3. Actualizar tests para usar test_client_with_warmup

Author: Senior QA Team
Date: 13 Diciembre 2025
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# ==============================================================================
# TEST CLIENT CON WARMUP - SOLUCIONA RACE CONDITION
# ==============================================================================

@pytest.fixture(scope="function")
async def test_client_with_warmup(   
    app_with_overrides: FastAPI  # ✅ AGREGAR este parámetro
) -> AsyncGenerator[AsyncClient, None]:
    """
    Create AsyncClient with catalog warmup.
    
    ✅ SOLUCIÓN: Ejecutar lifespan manualmente antes de crear cliente
    
    El problema: AsyncClient NO ejecuta lifespan automáticamente
    La solución: Forzar ejecución manual del lifespan context manager
    
    Scope: function (per test)
    
    Yields:
        AsyncClient: Client con catalog pre-cargado
    """
    # ============================================================================
    # CRITICAL FIX: Importar y ejecutar lifespan manualmente
    # ============================================================================
    
    from src.api.main_unified_redis import lifespan
    # from src.api.main_unified_redis import lifespan, app
    # from src.api.security_auth import get_current_user
    
    # ✅ FIX: Mock authentication BEFORE creating client
    # async def mock_get_current_user():
    #     """Mock authentication - always returns test_user"""
    #     return "test_user"
    
    # Override authentication dependency
    # app.dependency_overrides[get_current_user] = mock_get_current_user
    # logger.info("✅ Mock authentication activated in test_client_with_warmup")

    logger.info("🔄 Forcing lifespan startup execution for test environment...")
    
    # ✅ Ejecutar el lifespan context manager manualmente
    async with lifespan(app_with_overrides):
        logger.info("✅ Lifespan startup completed")
        
        # Verificar que el catálogo se cargó
        from src.api.main_unified_redis import tfidf_recommender
        
        if tfidf_recommender and hasattr(tfidf_recommender, 'loaded'):
            logger.info(
                f"📊 TFIDFRecommender status after lifespan:\n"
                f"   Loaded: {tfidf_recommender.loaded}\n"
                f"   Products: {len(tfidf_recommender.product_data) if tfidf_recommender.product_data else 0}"
            )
        else:
            logger.warning("⚠️ TFIDFRecommender not available after lifespan")
        
        # ============================================================================
        # CREATE CLIENT (dentro del context del lifespan)
        # ============================================================================
        
        async with AsyncClient(
            transport=ASGITransport(app=app_with_overrides),
            base_url="http://test"
        ) as client:
            
            # ============================================================================
            # QUICK VERIFICATION (debería estar listo inmediatamente)
            # ============================================================================
            
            logger.info("🔄 Quick verification of catalog...")
            
            max_retries = 3  # Solo 3 intentos - debería estar listo
            retry_delay = 0.5
            catalog_loaded = False
            
            for attempt in range(1, max_retries + 1):
                try:
                    response = await client.get(
                        "/v1/health/detailed",
                        headers={"X-API-Key": "2fed9999056fab6dac5654238f0cae1c"}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        status = data.get("status", {})
                        loaded = status.get("loaded", False)
                        product_count = status.get("product_count", 0)
                        categories_count = status.get("categories_count", 0)
                        
                        if loaded and product_count > 0:
                            logger.info(
                                f"✅ Catalog verified!\n"
                                f"   Products: {product_count}\n"
                                f"   Categories: {categories_count}\n"
                                f"   Verification time: {attempt * retry_delay}s"
                            )
                            catalog_loaded = True
                            break
                        else:
                            logger.debug(
                                f"⏳ Attempt {attempt}/{max_retries}:\n"
                                f"   loaded={loaded}, products={product_count}"
                            )
                    else:
                        logger.debug(f"⚠️ Unexpected status: {response.status_code}")
                
                except Exception as e:
                    logger.debug(f"⚠️ Verification error: {e}")
                
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay)
            
            if not catalog_loaded:
                error_msg = (
                    f"❌ CATALOG VERIFICATION FAILED\n"
                    f"   Lifespan executed but catalog not loaded\n"
                    f"   Check startup logs in main_unified_redis.py"
                )
                logger.error(error_msg)
                pytest.fail(error_msg)
            
            logger.info("✅ Test client ready with verified catalog")
            yield client
            
    #     logger.debug("🧹 Test client cleanup")
    #     # ✅ FIX: Clear dependency overrides after test
    #     app.dependency_overrides.clear()
    #     logger.info("🧹 Mock authentication cleaned up")
    # logger.debug("🧹 Lifespan shutdown complete")


# ==============================================================================
# BACKWARD COMPATIBILITY - LEGACY FIXTURE
# ==============================================================================

# ⚠️ DEPRECATION NOTICE:
# La fixture original `test_client` se mantiene para compatibilidad
# pero tests deberían migrar a `test_client_with_warmup` para evitar 503 errors

# @pytest.fixture(scope="function")
# def app_with_overrides() -> Generator[FastAPI, None, None]:
    
#     """
#     Get FastAPI app with dependency overrides.
    
#     Allows tests to override dependencies with mocks.
    
#     Scope: function (per test)
    
#     Returns:
#         FastAPI app instance
#     """
#     # Clear any existing overrides
#     app.dependency_overrides.clear()
    
#     yield app
    
#     # Clean up overrides after test
#     app.dependency_overrides.clear()


# ==============================================================================
# MOCK FACTORIES FIXTURES
# ==============================================================================

@pytest.fixture(scope="function")
def mock_claude_api() -> MagicMock:
    """
    Create mock for Claude/Anthropic API.
    
    Provides predictable responses for conversational tests.
    
    Scope: function (per test)
    
    Returns:
        Mock Claude API client
    """
    mock = MagicMock()
    
    # Default successful response
    mock.messages.create = AsyncMock(
        return_value=ClaudeAPIMockFactory.create_conversation_response(
            message="Test message",
            recommendations=[
                {"id": "prod_001", "title": "Test Product 1"},
                {"id": "prod_002", "title": "Test Product 2"}
            ]
        )
    )
    
    return mock


@pytest.fixture(scope="function")
def mock_retail_api() -> MagicMock:
    """
    Create mock for Google Cloud Retail API.
    
    Provides predictable collaborative filtering responses.
    
    Scope: function (per test)
    
    Returns:
        Mock Retail API client
    """
    mock = MagicMock()
    
    # Predict method
    mock.predict = AsyncMock(
        return_value=RetailAPIMockFactory.create_predict_response(
            user_id="test_user",
            n_recommendations=5
        )
    )
    
    # Write user event method
    mock.write_user_event = AsyncMock(
        return_value=RetailAPIMockFactory.create_user_event_response(
            event_type="detail-page-view",
            product_id="prod_001",
            user_id="test_user"
        )
    )
    
    return mock


@pytest.fixture(scope="function")
def mock_shopify_api() -> MagicMock:
    """
    Create mock for Shopify API.
    
    Provides predictable product catalog responses.
    
    Scope: function (per test)
    
    Returns:
        Mock Shopify API client
    """
    mock = MagicMock()
    
    # Get product method
    mock.get_product = AsyncMock(
        return_value=ShopifyAPIMockFactory.create_product_response(
            product_id="prod_001",
            title="Test Product",
            price=99.99
        )
    )
    
    # Get products list method
    mock.get_products = AsyncMock(
        return_value=ShopifyAPIMockFactory.create_products_list_response(
            count=10
        )
    )
    
    return mock


# ==============================================================================
# TEST DATA FIXTURES
# ==============================================================================

@pytest.fixture(scope="session")
def test_product_catalog() -> list[Dict[str, Any]]:
    """
    Create test product catalog.
    
    Generates 50 realistic test products.
    
    Scope: session (shared across all tests)
    
    Returns:
        List of product dictionaries
    """
    return create_test_product_catalog(count=50)


@pytest.fixture(scope="function")
def sample_user_data() -> Dict[str, Any]:
    """
    Create sample user data for tests.
    
    Scope: function (per test)
    
    Returns:
        User data dictionary
    """
    return {
        "user_id": "test_user_123",
        "email": "test@example.com",
        "name": "Test User",
        "market": "US",
        "preferences": {
            "categories": ["shoes", "clothing"],
            "brands": ["Nike", "Adidas"],
            "price_range": {"min": 50, "max": 200}
        },
        "purchase_history": []
    }


@pytest.fixture(scope="function")
def sample_conversation_context() -> Dict[str, Any]:
    """
    Create sample conversation context for MCP tests.
    
    Scope: function (per test)
    
    Returns:
        Conversation context dictionary
    """
    return {
        "conversation_id": "conv_test_123",
        "user_id": "test_user_123",
        "market": "US",
        "messages": [
            {
                "role": "user",
                "content": "Hi, I need help finding running shoes",
                "timestamp": datetime.now().isoformat()
            },
            {
                "role": "assistant",
                "content": "I'd be happy to help you find the perfect running shoes!",
                "timestamp": datetime.now().isoformat()
            }
        ],
        "context": {
            "intent": "product_search",
            "category": "shoes",
            "user_preferences": {}
        }
    }


# ==============================================================================
# MARKET CONTEXT FIXTURES
# ==============================================================================

@pytest.fixture(scope="function")
def us_market_context() -> Dict[str, Any]:
    """US market configuration."""
    return {
        "market_id": "US",
        "currency": "USD",
        "language": "en",
        "locale": "en_US",
        "timezone": "America/New_York"
    }


@pytest.fixture(scope="function")
def es_market_context() -> Dict[str, Any]:
    """ES (Spain) market configuration."""
    return {
        "market_id": "ES",
        "currency": "EUR",
        "language": "es",
        "locale": "es_ES",
        "timezone": "Europe/Madrid"
    }


@pytest.fixture(scope="function")
def mx_market_context() -> Dict[str, Any]:
    """MX (Mexico) market configuration."""
    return {
        "market_id": "MX",
        "currency": "MXN",
        "language": "es",
        "locale": "es_MX",
        "timezone": "America/Mexico_City"
    }


# ==============================================================================
# PERFORMANCE TRACKING FIXTURES
# ==============================================================================

@pytest.fixture(scope="function")
def performance_tracker():
    """
    Track performance metrics during test execution.
    
    Records response times and provides assertions.
    
    Scope: function (per test)
    
    Returns:
        PerformanceTracker instance
    """
    class PerformanceTracker:
        def __init__(self):
            self.metrics = []
        
        def record(self, operation: str, duration: float):
            """Record operation duration."""
            self.metrics.append({
                "operation": operation,
                "duration": duration,
                "timestamp": datetime.now().isoformat()
            })
        
        def assert_under(self, threshold: float, operation: str = None):
            """Assert all or specific operations are under threshold."""
            if operation:
                relevant_metrics = [m for m in self.metrics if m["operation"] == operation]
            else:
                relevant_metrics = self.metrics
            
            for metric in relevant_metrics:
                assert metric["duration"] < threshold, (
                    f"Operation '{metric['operation']}' took {metric['duration']:.3f}s, "
                    f"expected < {threshold}s"
                )
        
        def get_stats(self) -> Dict[str, Any]:
            """Get performance statistics."""
            if not self.metrics:
                return {}
            
            durations = [m["duration"] for m in self.metrics]
            return {
                "total_operations": len(self.metrics),
                "total_time": sum(durations),
                "avg_time": sum(durations) / len(durations),
                "min_time": min(durations),
                "max_time": max(durations),
                "operations": self.metrics
            }
    
    return PerformanceTracker()


# ==============================================================================
# SEED DATA FIXTURES
# ==============================================================================

@pytest.fixture(scope="function")
async def seed_redis_with_products(
    clean_redis: redis.Redis,
    test_product_catalog: list[Dict[str, Any]]
) -> AsyncGenerator[redis.Redis, None]:
    """
    Seed Redis with test products.
    
    Pre-populates Redis cache with test product data.
    
    Scope: function (per test)
    
    Yields:
        Redis client with seeded data
    """
    # Seed products
    for product in test_product_catalog[:10]:  # Seed first 10 products
        key = f"product:{product['id']}"
        await clean_redis.set(
            key,
            json.dumps(product),
            ex=3600  # 1 hour TTL
        )
    
    print(f"\n✅ Seeded Redis with {10} test products")
    
    yield clean_redis


# ==============================================================================
# CLEANUP FIXTURES
# ==============================================================================

@pytest.fixture(scope="function", autouse=True)
async def cleanup_service_factory():
    """
    Reset ServiceFactory between tests.
    
    Ensures singleton instances don't leak between tests.
    
    Scope: function (auto-use, runs for every test)
    """
    yield
    
    # Reset ServiceFactory after each test
    # This ensures clean state for next test
    if hasattr(ServiceFactory, '_instances'):
        ServiceFactory._instances.clear()


# ==============================================================================
# HELPER FIXTURES
# ==============================================================================

@pytest.fixture(scope="function")
def assert_response_structure():
    """
    Helper fixture for asserting response structure.
    
    Provides common assertions for API responses.
    
    Scope: function (per test)
    """
    def _assert_structure(response: Dict[str, Any], expected_keys: list[str]):
        """Assert response has expected keys."""
        for key in expected_keys:
            assert key in response, f"Expected key '{key}' not found in response"
    
    return _assert_structure


@pytest.fixture(scope="function")
def create_mock_request():
    """
    Factory for creating mock FastAPI Request objects.
    
    Scope: function (per test)
    """
    def _create_request(
        method: str = "GET",
        url: str = "http://test/",
        headers: Dict[str, str] = None
    ):
        """Create mock request."""
        from fastapi import Request
        from starlette.datastructures import Headers
        
        if headers is None:
            headers = {}
        
        # Create mock scope
        scope = {
            "type": "http",
            "method": method,
            "path": url,
            "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        }
        
        # Return mock request
        return Request(scope)
    
    return _create_request


# ==============================================================================
# SESSION FIXTURES (Run once per session)
# ==============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Setup test environment before any tests run.
    
    Scope: session (runs once before all tests)
    """
    print("\n" + "="*80)
    print("🚀 STARTING E2E TEST SUITE - FASE 3B")
    print("="*80)
    print(f"Environment: {os.getenv('ENV', 'test')}")
    print(f"Redis: {os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6380')}")
    print(f"Mock External APIs: {os.getenv('ENABLE_MOCK_EXTERNAL_APIS', 'true')}")
    print("="*80 + "\n")
    
    yield
    
    print("\n" + "="*80)
    print("✅ E2E TEST SUITE COMPLETED")
    print("="*80 + "\n")


# ==============================================================================
# NOTES:
# ==============================================================================
# - All fixtures are available to tests automatically
# - Use clean_redis for isolated test execution
# - Use mock_* fixtures to avoid external API calls
# - Use performance_tracker to validate response times
# - Fixtures cleanup automatically after tests
# ==============================================================================