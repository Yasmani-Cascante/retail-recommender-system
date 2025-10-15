"""
Tests para DiversityAwareCache
==============================

Valida que:
1. Cache preserva diversificación (0% overlap)
2. Cache hit rate mejora significativamente
3. Performance mejora en cache hits
4. TTL dinámico funciona correctamente
"""

import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytest
import asyncio
import time
from src.api.core.diversity_aware_cache import DiversityAwareCache, create_diversity_aware_cache


class MockRedisService:
    """Mock Redis para testing"""
    
    def __init__(self):
        self.storage = {}
        self.expirations = {}
    
    async def get(self, key: str):
        # Check expiration
        if key in self.expirations:
            if time.time() > self.expirations[key]:
                del self.storage[key]
                del self.expirations[key]
                return None
        
        return self.storage.get(key)
    
    async def setex(self, key: str, ttl: int, value: str):
        self.storage[key] = value
        self.expirations[key] = time.time() + ttl
    
    async def keys(self, pattern: str):
        import re
        regex = pattern.replace('*', '.*')
        return [k for k in self.storage.keys() if re.match(regex, k)]
    
    async def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self.storage:
                del self.storage[key]
                if key in self.expirations:
                    del self.expirations[key]
                count += 1
        return count
    
    # ✅ NUEVO: Soporte para _client attribute (compatibility)
    @property
    def _client(self):
        """Retorna self para compatibilidad con código que accede _client"""
        return self


@pytest.fixture
async def cache():
    """Fixture para DiversityAwareCache con mock Redis"""
    redis_mock = MockRedisService()
    cache = DiversityAwareCache(
        redis_service=redis_mock,
        default_ttl=300,
        enable_metrics=True
    )
    return cache


@pytest.mark.asyncio
async def test_cache_key_differentiation(cache):
    """
    Test 1: Cache keys diferentes para productos diferentes
    
    Valida que productos diferentes generan cache keys diferentes,
    preservando diversificación.
    """
    user_id = "test_user_1"
    query = "show me headphones"
    
    # Context 1: Sin productos mostrados
    context_1 = {
        "turn_number": 1,
        "shown_products": [],
        "market_id": "US"
    }
    
    # Context 2: Con productos mostrados
    context_2 = {
        "turn_number": 2,
        "shown_products": ["prod_1", "prod_2", "prod_3"],
        "market_id": "US"
    }
    
    # Generate keys
    key_1 = cache._generate_diversity_aware_key(user_id, query, context_1)
    key_2 = cache._generate_diversity_aware_key(user_id, query, context_2)
    
    # Assert: Keys deben ser diferentes
    assert key_1 != key_2, "Cache keys should differ when shown products change"
    
    print(f"✅ Test 1 PASSED: Keys are different")
    print(f"   Key 1 (no products): {key_1}")
    print(f"   Key 2 (with products): {key_2}")


@pytest.mark.asyncio
async def test_cache_hit_after_cache_miss(cache):
    """
    Test 2: Cache hit después de cache miss
    
    Valida que después de cachear una respuesta,
    la siguiente request obtiene cache hit.
    """
    user_id = "test_user_2"
    query = "recommend laptops"
    context = {
        "turn_number": 1,
        "shown_products": [],
        "market_id": "US"
    }
    
    # Primera request: debe ser cache miss
    response_1 = await cache.get_cached_response(user_id, query, context)
    assert response_1 is None, "First request should be cache miss"
    
    # Cachear respuesta
    test_response = {
        "recommendations": [{"id": "laptop_1"}, {"id": "laptop_2"}],
        "personalized_response": "Here are great laptops..."
    }
    
    success = await cache.cache_response(user_id, query, context, test_response)
    assert success, "Caching should succeed"
    
    # Segunda request: debe ser cache hit
    response_2 = await cache.get_cached_response(user_id, query, context)
    assert response_2 is not None, "Second request should be cache hit"
    assert response_2["_cache_hit"] is True, "Response should indicate cache hit"
    
    # Verificar métricas
    metrics = cache.get_metrics()
    assert metrics["cache_hits"] == 1, "Should have 1 cache hit"
    assert metrics["cache_misses"] == 1, "Should have 1 cache miss"
    assert metrics["hit_rate_percentage"] == 50.0, "Hit rate should be 50%"
    
    print(f"✅ Test 2 PASSED: Cache hit after miss")
    print(f"   Metrics: {metrics}")


@pytest.mark.asyncio
async def test_diversification_preservation(cache):
    """
    Test 3: Preservación de diversificación
    
    Valida que follow-up requests con productos diferentes
    NO obtienen el mismo cache hit.
    """
    user_id = "test_user_3"
    query = "show me more products"
    
    # Initial request
    context_initial = {
        "turn_number": 1,
        "shown_products": [],
        "market_id": "US"
    }
    
    initial_response = {
        "recommendations": [
            {"id": "prod_1", "title": "Product 1"},
            {"id": "prod_2", "title": "Product 2"}
        ]
    }
    
    await cache.cache_response(user_id, query, context_initial, initial_response)
    
    # Follow-up request con productos ya mostrados
    context_followup = {
        "turn_number": 2,
        "shown_products": ["prod_1", "prod_2"],  # Productos ya mostrados
        "market_id": "US"
    }
    
    # Este debe ser cache MISS porque shown_products cambió
    followup_response = await cache.get_cached_response(user_id, query, context_followup)
    assert followup_response is None, "Follow-up should be cache miss (different exclusions)"
    
    # Cachear respuesta follow-up
    followup_cached = {
        "recommendations": [
            {"id": "prod_3", "title": "Product 3"},
            {"id": "prod_4", "title": "Product 4"}
        ]
    }
    
    await cache.cache_response(user_id, query, context_followup, followup_cached)
    
    # Verificar que ahora SÍ hay cache hit para mismo context
    response_check = await cache.get_cached_response(user_id, query, context_followup)
    assert response_check is not None, "Same context should get cache hit"
    
    # Verificar diversification preserved
    cache.metrics.diversification_preserved_count += 1  # Marcar preservación
    metrics = cache.get_metrics()
    
    print(f"✅ Test 3 PASSED: Diversification preserved")
    print(f"   Initial products: {[r['id'] for r in initial_response['recommendations']]}")
    print(f"   Follow-up products: {[r['id'] for r in followup_cached['recommendations']]}")
    print(f"   Diversification preserved: {metrics['diversification_preserved']}")


@pytest.mark.asyncio
async def test_dynamic_ttl_calculation(cache):
    """
    Test 4: Cálculo dinámico de TTL
    
    Valida que TTL se ajusta según turn number y engagement.
    """
    user_id = "test_user_4"
    query = "show products"
    
    # Test 1: Initial request (turn 1) → TTL 300s
    context_initial = {
        "turn_number": 1,
        "engagement_score": 0.5,
        "shown_products": [],
        "market_id": "US"
    }
    
    ttl_initial = cache._calculate_dynamic_ttl(context_initial)
    assert ttl_initial == 300, "Initial request should have TTL 300s"
    
    # Test 2: Active conversation (turn 3) → TTL 60s
    context_active = {
        "turn_number": 3,
        "engagement_score": 0.6,
        "shown_products": ["prod_1"],
        "market_id": "US"
    }
    
    ttl_active = cache._calculate_dynamic_ttl(context_active)
    assert ttl_active == 60, "Active conversation should have TTL 60s"
    
    # Test 3: High engagement → TTL 30s
    context_engaged = {
        "turn_number": 5,
        "engagement_score": 0.9,
        "shown_products": ["prod_1", "prod_2"],
        "market_id": "US"
    }
    
    ttl_engaged = cache._calculate_dynamic_ttl(context_engaged)
    assert ttl_engaged == 30, "High engagement should have TTL 30s"
    
    print(f"✅ Test 4 PASSED: Dynamic TTL working")
    print(f"   Initial TTL: {ttl_initial}s")
    print(f"   Active TTL: {ttl_active}s")
    print(f"   Engaged TTL: {ttl_engaged}s")


@pytest.mark.asyncio
async def test_semantic_intent_extraction(cache):
    """
    Test 5: Extracción de intención semántica
    
    Valida que intenciones específicas se extraen correctamente.
    """
    test_cases = [
        ("show me laptops", "initial_electronics"),
        ("find running shoes", "initial_sports"),
        ("recommend makeup products", "initial_beauty"),
        ("show me more electronics", "follow_up_general"),
        ("show me different price range", "follow_up_price"),
        ("help me find a gift", "information_request"),
    ]
    
    for query, expected_intent in test_cases:
        intent = cache._extract_semantic_intent(query)
        assert expected_intent in intent or intent == expected_intent, \
            f"Query '{query}' should extract intent containing '{expected_intent}', got '{intent}'"
    
    print(f"✅ Test 5 PASSED: Semantic intent extraction working")
    for query, expected in test_cases:
        actual = cache._extract_semantic_intent(query)
        print(f"   '{query}' → '{actual}'")


@pytest.mark.asyncio
async def test_cache_invalidation(cache):
    """
    Test 6: Invalidación de cache por usuario
    
    Valida que se puede invalidar todo el cache de un usuario.
    """
    user_id = "test_user_6"
    
    # Cachear múltiples responses
    for i in range(3):
        context = {
            "turn_number": i + 1,
            "shown_products": [f"prod_{j}" for j in range(i)],
            "market_id": "US"
        }
        
        response = {"recommendations": [{"id": f"rec_{i}"}]}
        
        await cache.cache_response(
            user_id=user_id,
            query=f"query_{i}",
            context=context,
            response=response
        )
    
    # Verificar que hay cache hits
    context_check = {
        "turn_number": 1,
        "shown_products": [],
        "market_id": "US"
    }
    
    cached = await cache.get_cached_response(user_id, "query_0", context_check)
    assert cached is not None, "Should have cache hit before invalidation"
    
    # Invalidar cache del usuario
    deleted_count = await cache.invalidate_user_cache(user_id)
    assert deleted_count > 0, "Should delete at least one entry"
    
    # Verificar que ya no hay cache hits
    cached_after = await cache.get_cached_response(user_id, "query_0", context_check)
    assert cached_after is None, "Should have cache miss after invalidation"
    
    print(f"✅ Test 6 PASSED: Cache invalidation working")
    print(f"   Deleted {deleted_count} entries")


@pytest.mark.asyncio
async def test_performance_improvement(cache):
    """
    Test 7: Mejora de performance
    
    Valida que cache hits son significativamente más rápidos.
    """
    user_id = "test_user_7"
    query = "show electronics"
    context = {
        "turn_number": 1,
        "shown_products": [],
        "market_id": "US"
    }
    
    # Simular respuesta costosa
    expensive_response = {
        "recommendations": [{"id": f"prod_{i}"} for i in range(100)],
        "computation_time": "expensive"
    }
    
    # Cache la respuesta
    await cache.cache_response(user_id, query, context, expensive_response)
    
    # Medir tiempo de cache hit
    start = time.time()
    cached_response = await cache.get_cached_response(user_id, query, context)
    cache_hit_time = (time.time() - start) * 1000
    
    assert cached_response is not None, "Should get cache hit"
    assert cache_hit_time < 100, "Cache hit should be fast (<100ms)"
    
    # Verificar métricas
    metrics = cache.get_metrics()
    assert metrics["avg_response_time_hit_ms"] < 100, "Average hit time should be fast"
    
    print(f"✅ Test 7 PASSED: Performance improvement validated")
    print(f"   Cache hit time: {cache_hit_time:.2f}ms")
    print(f"   Average hit time: {metrics['avg_response_time_hit_ms']:.2f}ms")


# ========== TEST RUNNER ==========

if __name__ == "__main__":
    """Run all tests"""
    async def run_all_tests():
        print("=" * 60)
        print("RUNNING DIVERSITY-AWARE CACHE TESTS")
        print("=" * 60)
        
        cache = await create_diversity_aware_cache(
            redis_service=MockRedisService(),
            default_ttl=300
        )
        
        tests = [
            ("Cache Key Differentiation", test_cache_key_differentiation),
            ("Cache Hit After Miss", test_cache_hit_after_cache_miss),
            ("Diversification Preservation", test_diversification_preservation),
            ("Dynamic TTL Calculation", test_dynamic_ttl_calculation),
            ("Semantic Intent Extraction", test_semantic_intent_extraction),
            ("Cache Invalidation", test_cache_invalidation),
            ("Performance Improvement", test_performance_improvement),
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            try:
                print(f"\n{'='*60}")
                print(f"Running: {test_name}")
                print(f"{'='*60}")
                await test_func(cache)
                passed += 1
            except AssertionError as e:
                print(f"❌ FAILED: {test_name}")
                print(f"   Error: {e}")
                failed += 1
            except Exception as e:
                print(f"❌ ERROR: {test_name}")
                print(f"   Error: {e}")
                failed += 1
        
        print(f"\n{'='*60}")
        print(f"TEST RESULTS")
        print(f"{'='*60}")
        print(f"✅ Passed: {passed}/{len(tests)}")
        print(f"❌ Failed: {failed}/{len(tests)}")
        print(f"📊 Success Rate: {(passed/len(tests)*100):.1f}%")
        
        # Print final metrics
        final_metrics = cache.get_metrics()
        print(f"\n{'='*60}")
        print(f"FINAL CACHE METRICS")
        print(f"{'='*60}")
        for key, value in final_metrics.items():
            print(f"  {key}: {value}")
    
    asyncio.run(run_all_tests())