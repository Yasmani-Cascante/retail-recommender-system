"""
Configuración de fixtures para tests de Knowledge Base Health Checks.

✅ REFACTORIZADO (12 Feb 2026): Reutiliza infraestructura existente de tests/conftest.py
y tests/fixtures/kb/kb_fixtures.py para evitar duplicación.

Este módulo EXTIENDE las fixtures existentes solo con lo específico para health checks.

Author: Senior QA Team
Date: 12 Febrero 2026 (H3 Día 3 - Refactored)
Version: 2.0.0 - Reutilizando infraestructura
"""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timedelta

# ============================================================================
# REUTILIZAR FIXTURES EXISTENTES
# ============================================================================
# Las siguientes fixtures YA EXISTEN en tests/conftest.py:
# - mock_db_pool ✅
# - mock_shopify_kb_client ✅  
# - mock_kb_redis_service ✅
# - test_app_with_mocks ✅
# - test_client ✅
#
# Solo necesitamos EXTENDERLAS con funcionalidad específica para health checks

# ============================================================================
# HEALTH CHECK SPECIFIC MOCKS (Extensions)
# ============================================================================

@pytest.fixture
def mock_db_pool_health_check(mock_db_pool):
    """
    Extiende mock_db_pool con queries específicas para health checks.
    
    Reutiliza: tests/conftest.py::mock_db_pool
    Extiende con: Queries específicas de health_kb.py
    """
    conn = AsyncMock()
    
    # ✅ Mock fetchval responses para health check queries
    async def mock_fetchval(query, *args):
        query_lower = query.lower()
        
        # SELECT 1 (connectivity)
        if "select 1" in query_lower:
            return 1
        
        # Count queries
        if "count(*)" in query_lower:
            if "kb_contents" in query_lower:
                # ✅ CRITICAL FIX: Check staleness PRIMERO, antes de language checks
                # Query de staleness: SELECT COUNT(*) FROM kb_contents WHERE last_synced < $1
                if "last_synced <" in query_lower:
                    return 0  # Todos los registros son frescos (<24h)
                # Language-specific counts
                elif "language = 'es'" in query_lower or "language = $1" in query_lower:
                    if args and args[0] == 'es':
                        return 13
                    elif "language = 'es'" in query_lower:
                        return 13
                elif "language = 'en'" in query_lower or (args and args[0] == 'en'):
                    return 13
                else:
                    return 26  # Total de registros
            elif "schema_migrations" in query_lower:
                return 2
        
        # Schema version
        if "max(version)" in query_lower:
            return 2
        
        # Timestamps
        if "min(last_synced)" in query_lower:
            return datetime.utcnow() - timedelta(hours=1)
        if "max(last_synced)" in query_lower:
            return datetime.utcnow()
        
        # Table/column existence
        if "exists" in query_lower:
            return True
        
        return None
    
    # ✅ Mock fetch for language coverage
    async def mock_fetch(query, *args):
        if "group by language" in query.lower():
            now = datetime.utcnow()
            return [
                {
                    "language": "en",
                    "total": 13,
                    "sub_intents": ["account_modifications", "account_orders", "general_faq",
                                  "policy_payment", "policy_privacy", "policy_return",
                                  "policy_shipping", "policy_warranty", "product_availability",
                                  "product_care", "product_material", "product_sizing", "unknown"],
                    "last_synced": now
                },
                {
                    "language": "es", 
                    "total": 13,
                    "sub_intents": ["account_modifications", "account_orders", "general_faq",
                                  "policy_payment", "policy_privacy", "policy_return",
                                  "policy_shipping", "policy_warranty", "product_availability",
                                  "product_care", "product_material", "product_sizing", "unknown"],
                    "last_synced": now - timedelta(seconds=2)
                }
            ]
        return []
    
    conn.fetchval = AsyncMock(side_effect=mock_fetchval)
    conn.fetch = AsyncMock(side_effect=mock_fetch)
    conn.execute = AsyncMock(return_value="OK")
    
    # Context manager
    class MockAcquire:
        async def __aenter__(self):
            return conn
        async def __aexit__(self, *args):
            pass
    
    from unittest.mock import MagicMock
    mock_db_pool.acquire = MagicMock(return_value=MockAcquire())
    mock_db_pool.get_size = MagicMock(return_value=5)
    mock_db_pool.get_idle_size = MagicMock(return_value=2)
    
    return mock_db_pool


@pytest.fixture
def mock_redis_health_check(mock_kb_redis_service):
    """
    Extiende mock_kb_redis_service con health check funcional.
    
    Reutiliza: tests/conftest.py::mock_kb_redis_service
    Extiende con: health_check() method
    """
    async def mock_health_check(timeout=1.0):
        """Mock health check that accepts timeout parameter."""
        return {
            "status": "healthy",
            "connected": True,
            "ping_time_ms": 149.02,
            "last_test": "successful"
        }
    
    # ✅ CRITICAL FIX: Usar wraps en lugar de side_effect
    mock_kb_redis_service.health_check = AsyncMock(wraps=mock_health_check)
    return mock_kb_redis_service
    return mock_kb_redis_service


@pytest.fixture
def mock_shopify_health_check(mock_shopify_kb_client):
    """
    Extiende mock_shopify_kb_client con GraphQL query para health check.
    
    Reutiliza: tests/conftest.py::mock_shopify_kb_client
    Extiende con: _graphql_query() para shop info
    """
    async def mock_graphql_query(query, variables=None):
        return {
            "shop": {
                "name": "AI-shoppings",
                "primaryDomain": {"url": "https://ai-shoppings.myshopify.com"},
                "currencyCode": "CLP"
            }
        }
    
    mock_shopify_kb_client._graphql_query = AsyncMock(side_effect=mock_graphql_query)
    return mock_shopify_kb_client


# ============================================================================
# DEPENDENCY OVERRIDES
# ============================================================================

@pytest.fixture
def override_kb_health_dependencies(
    mock_db_pool_health_check,
    mock_redis_health_check,
    mock_shopify_health_check
):
    """
    Dependency overrides específicos para health check tests.
    
    Combina fixtures existentes + extensiones health-specific.
    """
    from src.api.dependencies import (
        get_db_pool,
        get_redis_service
    )
    
    # Mock KB sync service
    from unittest.mock import MagicMock
    sync_service = MagicMock()
    sync_service.shopify = mock_shopify_health_check
    
    try:
        from src.api.dependencies import get_kb_sync_service
        return {
            get_db_pool: lambda: mock_db_pool_health_check,
            get_redis_service: lambda: mock_redis_health_check,
            get_kb_sync_service: lambda: sync_service
        }
    except ImportError:
        # Fallback si get_kb_sync_service no existe
        return {
            get_db_pool: lambda: mock_db_pool_health_check,
            get_redis_service: lambda: mock_redis_health_check
        }


# ============================================================================
# TEST CLIENT (Reutiliza test_client existente)
# ============================================================================

@pytest.fixture
def kb_test_client(override_kb_health_dependencies):
    """
    TestClient configurado para KB health checks.
    
    Reutiliza: Lógica de tests/conftest.py::test_client
    Aplica: Dependency overrides específicos de health checks
    """
    from fastapi.testclient import TestClient
    from src.api.main_unified_redis import app
    
    app.dependency_overrides.update(override_kb_health_dependencies)
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.fixture
def kb_test_client_degraded(
    mock_db_pool_health_check, 
    mock_degraded_redis, 
    mock_shopify_health_check
):
    """
    FIXED (12 Feb 2026): TestClient específico para tests con Redis degraded.
    
    FIX APLICADO:
    - Usa callable dependencies como keys (get_db_pool, get_redis_service)
    - NO usa strings como keys ("db_pool", "redis")
    - Garantiza que FastAPI encuentre los overrides correctamente
    
    Similar a kb_test_client pero usa mock_degraded_redis.
    """
    from fastapi.testclient import TestClient
    from src.api.main_unified_redis import app
    from src.api.dependencies import (
        get_db_pool,
        get_redis_service,
        get_kb_sync_service
    )
    from unittest.mock import MagicMock
    
    # ✅ Crear sync service mock
    sync_service = MagicMock()
    sync_service.shopify = mock_shopify_health_check
    
    # ✅ CRITICAL FIX: Usar callables dependency como keys, NO strings
    # FastAPI busca por la función dependency, no por string name
    overrides = {
        get_db_pool: lambda: mock_db_pool_health_check,  # ✅ Callable key
        get_redis_service: lambda: mock_degraded_redis,   # ✅ Callable key (DEGRADED)
        get_kb_sync_service: lambda: sync_service         # ✅ Callable key
    }
    
    # ✅ Aplicar overrides
    app.dependency_overrides.update(overrides)
    
    try:
        with TestClient(app) as client:
            yield client
    finally:
        # ✅ CRITICAL: Siempre limpiar overrides, incluso si hay exception
        app.dependency_overrides.clear()


# ============================================================================
# UTILITY FIXTURES
# ============================================================================

@pytest.fixture
def sample_health_response():
    """Sample expected response structure for assertions."""
    return {
        "overall_status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "postgres": {
                "status": "healthy",
                "message": "PostgreSQL connectivity OK",
                "details": {"pool_size": 5, "pool_free": 2, "pool_usage_pct": 60}
            },
            "kb_content": {
                "status": "healthy",
                "message": "Content available in multiple languages",
                "details": {"total_records": 26, "es_records": 13, "en_records": 13}
            },
            "redis": {
                "status": "healthy",
                "message": "Redis connectivity OK",
                "details": {"ping_time_ms": 149.02, "connected": True}
            },
            "schema_version": {
                "status": "healthy",
                "message": "Schema versioning OK",
                "details": {"current_version": 2, "total_migrations": 2}
            }
        },
        "sync_metrics": {"total_records": 26, "stale_records_24h": 0, "stale_records_7d": 0},
        "warnings": [],
        "recommendations": []
    }


@pytest.fixture
def mock_degraded_redis(mock_kb_redis_service):
    """Redis mock in degraded state for error handling tests."""
    async def mock_degraded_health(timeout=1.0):
        """Mock health check that accepts timeout parameter."""
        return {
            "status": "degraded",
            "connected": True,
            "ping_time_ms": 850.0,
            "last_test": "slow_response"
        }
    
    # ✅ CRITICAL FIX: Usar return_value directo en lugar de side_effect
    # side_effect con función causa problemas con parámetros kwargs
    mock_kb_redis_service.health_check = AsyncMock(wraps=mock_degraded_health)
    return mock_kb_redis_service


@pytest.fixture
def mock_unhealthy_db():
    """DB pool mock in unhealthy state for error handling tests."""
    from unittest.mock import MagicMock
    pool = AsyncMock()
    pool.acquire = MagicMock(side_effect=Exception("PostgreSQL connection failed"))
    return pool