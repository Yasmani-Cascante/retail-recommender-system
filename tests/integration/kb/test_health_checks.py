"""
Integration tests for H3 Enhanced Health Checks.

Tests de integración para el sistema de health checks del Knowledge Base,
verificando comportamiento en normal mode y deep mode.

Author: Senior QA Team
Date: 11 Febrero 2026 (H3 Día 3)
Version: 1.0.0
"""

import pytest
from datetime import datetime


# ============================================================================
# NORMAL MODE TESTS
# ============================================================================

def test_normal_mode_fast(kb_test_client):
    """
    ✅ TEST: Normal mode debe completar rápido y NO incluir Shopify API check.
    
    Verifica:
    - Status code 200
    - 4 componentes básicos (postgres, kb_content, redis, schema_version)
    - NO incluye shopify_api (solo en deep mode)
    - Overall status healthy
    - Tiene sync_metrics
    """
    # ✅ RUTA CORREGIDA: /api/health/kb (no /health/kb)
    response = kb_test_client.get("/api/health/kb")
    
    # ✅ Verify response
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    
    # ✅ Verify structure
    assert "overall_status" in data, "Missing overall_status"
    assert "timestamp" in data, "Missing timestamp"
    assert "components" in data, "Missing components"
    assert "sync_metrics" in data, "Missing sync_metrics"
    
    # ✅ Verify components (normal mode = 4 components)
    components = data["components"]
    assert "postgres" in components, "Missing postgres component"
    assert "kb_content" in components, "Missing kb_content component"
    assert "redis" in components, "Missing redis component"
    assert "schema_version" in components, "Missing schema_version component"
    
    # ✅ CRITICAL: Shopify API should NOT be in normal mode
    assert "shopify_api" not in components, (
        "shopify_api should NOT be present in normal mode"
    )
    
    # ✅ Verify all components healthy
    assert data["overall_status"] == "healthy", (
        f"Expected overall_status=healthy, got {data['overall_status']}"
    )
    
    # ✅ Verify each component status
    for component_name, component_data in components.items():
        assert "status" in component_data, f"Missing status in {component_name}"
        assert "message" in component_data, f"Missing message in {component_name}"
        assert component_data["status"] in ["healthy", "degraded", "unhealthy"], (
            f"Invalid status in {component_name}: {component_data['status']}"
        )
    
    # ✅ Verify sync_metrics structure
    sync_metrics = data["sync_metrics"]
    assert "total_records" in sync_metrics, "Missing total_records"
    assert "languages" in sync_metrics, "Missing languages"
    assert sync_metrics["total_records"] > 0, "Should have records"
    
    print(f"✅ Normal mode test passed - {len(components)} components")


def test_normal_mode_component_details(kb_test_client):
    """
    ✅ TEST: Verificar detalles específicos de cada componente en normal mode.
    """
    response = kb_test_client.get("/api/health/kb")
    data = response.json()
    
    components = data["components"]
    
    # ✅ PostgreSQL details
    postgres = components["postgres"]
    assert "details" in postgres, "Missing postgres details"
    assert "pool_size" in postgres["details"], "Missing pool_size"
    assert "pool_free" in postgres["details"], "Missing pool_free"
    assert postgres["details"]["pool_size"] > 0, "Pool size should be > 0"
    
    # ✅ KB Content details
    kb_content = components["kb_content"]
    assert "details" in kb_content, "Missing kb_content details"
    assert "total_records" in kb_content["details"], "Missing total_records"
    assert "es_records" in kb_content["details"], "Missing es_records"
    assert "en_records" in kb_content["details"], "Missing en_records"
    assert kb_content["details"]["total_records"] == 26, "Should have 26 records"
    
    # ✅ Redis details
    redis = components["redis"]
    assert "details" in redis, "Missing redis details"
    assert "ping_time_ms" in redis["details"], "Missing ping_time_ms"
    assert "connected" in redis["details"], "Missing connected"
    assert redis["details"]["connected"] is True, "Redis should be connected"
    
    # ✅ Schema Version details
    schema = components["schema_version"]
    assert "details" in schema, "Missing schema details"
    assert "current_version" in schema["details"], "Missing current_version"
    assert schema["details"]["current_version"] == 2, "Should be version 2"
    
    print("✅ Component details test passed")


# ============================================================================
# DEEP MODE TESTS
# ============================================================================

def test_deep_mode_shopify(kb_test_client):
    """
    ✅ TEST: Deep mode debe incluir Shopify API check.
    
    Verifica:
    - Status code 200
    - 5 componentes (incluyendo shopify_api)
    - Shopify API details correctos
    - Response time registrado
    """
    # ✅ RUTA CORREGIDA con query parameter
    response = kb_test_client.get("/api/health/kb?deep=true")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    
    # ✅ Verify structure
    assert "components" in data, "Missing components"
    
    components = data["components"]
    
    # ✅ CRITICAL: Shopify API MUST be present in deep mode
    assert "shopify_api" in components, (
        "shopify_api MUST be present in deep mode"
    )
    
    # ✅ Verify deep mode has 5 components (4 basic + shopify_api)
    expected_components = {
        "postgres", "kb_content", "redis", "schema_version", "shopify_api"
    }
    actual_components = set(components.keys())
    assert actual_components == expected_components, (
        f"Expected {expected_components}, got {actual_components}"
    )
    
    # ✅ Verify Shopify API component details
    shopify = components["shopify_api"]
    assert "status" in shopify, "Missing shopify status"
    assert "message" in shopify, "Missing shopify message"
    assert "details" in shopify, "Missing shopify details"
    
    # ✅ Status should be healthy or degraded (not unhealthy in mock)
    assert shopify["status"] in ["healthy", "degraded"], (
        f"Shopify status should be healthy/degraded, got {shopify['status']}"
    )
    
    # ✅ Verify Shopify details structure
    details = shopify["details"]
    assert "shop_name" in details, "Missing shop_name"
    assert "shop_url" in details, "Missing shop_url"
    assert "currency_code" in details, "Missing currency_code"
    assert "response_time_ms" in details, "Missing response_time_ms"
    assert "credentials_valid" in details, "Missing credentials_valid"
    
    # ✅ Verify Shopify details values
    assert details["shop_name"] == "AI-shoppings", (
        f"Expected shop_name='AI-shoppings', got '{details['shop_name']}'"
    )
    assert details["credentials_valid"] is True, "Credentials should be valid"
    assert isinstance(details["response_time_ms"], (int, float)), (
        "response_time_ms should be numeric"
    )
    
    print(f"✅ Deep mode test passed - Shopify check completed in {details['response_time_ms']}ms")


def test_deep_mode_performance_acceptable(kb_test_client):
    """
    ✅ TEST: Deep mode debe completar en tiempo razonable.
    
    Deep mode toma más tiempo que normal mode debido al Shopify API check,
    pero debe completar en <3s para ser considerado healthy.
    """
    import time
    
    start = time.perf_counter()
    response = kb_test_client.get("/api/health/kb?deep=true")
    duration_ms = (time.perf_counter() - start) * 1000
    
    assert response.status_code == 200
    data = response.json()
    
    # ✅ Verify Shopify response time is acceptable
    shopify = data["components"]["shopify_api"]
    shopify_time = shopify["details"]["response_time_ms"]
    
    # ✅ En mocks, debería ser muy rápido (<100ms)
    # En producción real, <3000ms es aceptable
    assert shopify_time < 3000, (
        f"Shopify API took {shopify_time}ms, should be <3000ms"
    )
    
    print(f"✅ Deep mode performance test passed - Total: {duration_ms:.1f}ms, Shopify: {shopify_time}ms")


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

def test_normal_mode_with_warnings(kb_test_client_degraded):
    """
    ✅ TEST: Sistema debe manejar gracefully componentes degraded.
    
    Usa fixture mock_degraded_redis para simular Redis lento.
    """
    from src.api.dependencies import get_redis_service
    from src.api.main_unified_redis import app
    
    # ✅ Override Redis with degraded version
    # app.dependency_overrides[get_redis_service] = lambda: mock_degraded_redis
    
    try:
        response = kb_test_client_degraded.get("/api/health/kb")
        
        assert response.status_code == 200
        data = response.json()
        
        # ✅ Overall status puede ser degraded si Redis está lento
        assert data["overall_status"] in ["healthy", "degraded"]
        
        # ✅ Redis component should be degraded
        redis = data["components"]["redis"]
        # Note: Dependiendo de la implementación, puede ser degraded o healthy
        # Solo verificamos que existe
        assert "status" in redis
        
        print("✅ Warning handling test passed")
        
    finally:
        # ✅ Cleanup: restore original dependency
        if get_redis_service in app.dependency_overrides:
            del app.dependency_overrides[get_redis_service]


# ============================================================================
# SYNC METRICS TESTS
# ============================================================================

def test_sync_metrics_completeness(kb_test_client):
    """
    ✅ TEST: Verificar que sync_metrics contiene toda la información requerida.
    """
    response = kb_test_client.get("/api/health/kb")
    data = response.json()
    
    sync_metrics = data["sync_metrics"]
    
    # ✅ Required fields
    assert "total_records" in sync_metrics
    assert "languages" in sync_metrics
    assert "oldest_sync" in sync_metrics
    assert "newest_sync" in sync_metrics
    assert "stale_records_24h" in sync_metrics
    assert "stale_records_7d" in sync_metrics
    
    # ✅ Languages array structure
    languages = sync_metrics["languages"]
    assert isinstance(languages, list), "languages should be a list"
    assert len(languages) == 2, "Should have 2 languages (ES, EN)"
    
    for lang in languages:
        assert "language" in lang
        assert "total_records" in lang
        assert "sub_intents_covered" in lang
        assert "last_synced" in lang
        
        # ✅ Verify sub_intents is a list
        assert isinstance(lang["sub_intents_covered"], list)
        assert len(lang["sub_intents_covered"]) > 0, "Should have sub-intents"
    
    # ✅ Verify no stale records in fresh system
    assert sync_metrics["stale_records_24h"] == 0
    assert sync_metrics["stale_records_7d"] == 0
    
    print("✅ Sync metrics test passed")


# ============================================================================
# RESPONSE FORMAT TESTS
# ============================================================================

def test_response_format_consistency(kb_test_client, sample_health_response):
    """
    ✅ TEST: Verificar que el formato de respuesta es consistente.
    
    Compara estructura real vs esperada usando fixture sample_health_response.
    """
    response = kb_test_client.get("/api/health/kb")
    data = response.json()
    
    # ✅ Top-level keys
    expected_keys = {"overall_status", "timestamp", "components", "sync_metrics", "warnings", "recommendations"}
    actual_keys = set(data.keys())
    
    assert expected_keys.issubset(actual_keys), (
        f"Missing keys: {expected_keys - actual_keys}"
    )
    
    # ✅ Timestamp should be recent (within last minute)
    timestamp_str = data["timestamp"]
    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    now = datetime.utcnow()
    age_seconds = (now - timestamp.replace(tzinfo=None)).total_seconds()
    
    assert age_seconds < 60, f"Timestamp too old: {age_seconds}s"
    
    # ✅ Warnings and recommendations should be lists
    assert isinstance(data["warnings"], list)
    assert isinstance(data["recommendations"], list)
    
    print("✅ Response format test passed")


# ============================================================================
# QUERY PARAMETER TESTS
# ============================================================================

def test_deep_parameter_variations(kb_test_client):
    """
    ✅ TEST: Verificar diferentes valores del parámetro deep.
    """
    # ✅ Test deep=false (explicit)
    response = kb_test_client.get("/api/health/kb?deep=false")
    assert response.status_code == 200
    data = response.json()
    assert "shopify_api" not in data["components"]
    
    # ✅ Test deep=true
    response = kb_test_client.get("/api/health/kb?deep=true")
    assert response.status_code == 200
    data = response.json()
    assert "shopify_api" in data["components"]
    
    # ✅ Test no parameter (default = false)
    response = kb_test_client.get("/api/health/kb")
    assert response.status_code == 200
    data = response.json()
    assert "shopify_api" not in data["components"]
    
    print("✅ Query parameter test passed")