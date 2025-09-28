#!/usr/bin/env python3
"""
Test Cache Diagnosis - Sistema Actual
=====================================

Test para diagnosticar exactamente por qué el cache no funciona
en el sistema actual, SIN modificaciones.
"""

import asyncio
import sys
import time
sys.path.append('src')

# Cargar variables de entorno
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

async def test_cache_diagnosis():
    print("🔍 DIAGNOSING CACHE PERSISTENCE ISSUE...")
    print("=" * 60)
    
    try:
        # Importar componentes actuales
        from src.api.core.intelligent_personalization_cache import IntelligentPersonalizationCache
        from src.api.factories.service_factory import ServiceFactory
        
        # Obtener Redis service
        print("\n1️⃣ Getting Redis Service...")
        redis_service = await ServiceFactory.get_redis_service()
        if redis_service:
            health = await redis_service.health_check()
            print(f"   Redis status: {health.get('status', 'unknown')}")
            print(f"   Redis connected: {health.get('connected', False)}")
            if 'ping_time_ms' in health:
                print(f"   Redis ping: {health['ping_time_ms']:.1f}ms")
        else:
            print("   ❌ Redis service not available")
            return False
        
        # Test data - usando las mismas queries de los logs
        user_id = "widget_user_test_cache"
        context = {
            "market_id": "US",
            "user_segment": "standard", 
            "product_categories": ["electronics"]
        }
        
        test_response = {
            "personalized_response": "Here are electronics recommendations for you!",
            "personalized_recommendations": [
                {"id": "1", "title": "Test Electronics 1"},
                {"id": "2", "title": "Test Electronics 2"}
            ],
            "personalization_metadata": {
                "strategy_used": "test_strategy",
                "personalization_score": 0.85
            }
        }
        
        # Crear cache instance
        print("\n2️⃣ Creating Cache Instance...")
        cache = IntelligentPersonalizationCache(redis_service)
        
        # Test exact queries from logs
        query1 = "Show me some recomendations"  # From logs
        query2 = "show me more"                  # From logs
        
        print(f"\n3️⃣ Testing Query Hash Generation...")
        print(f"   Query 1: '{query1}'")
        print(f"   Query 2: '{query2}'")
        
        # Generate hashes to see if they're different
        hash1 = cache._generate_query_hash(query1, context)
        hash2 = cache._generate_query_hash(query2, context)
        
        print(f"   Hash 1: {hash1}")
        print(f"   Hash 2: {hash2}")
        print(f"   Hashes identical: {hash1 == hash2}")
        
        if hash1 != hash2:
            print("   🎯 ROOT CAUSE: Different queries generate different hashes!")
            print("      This explains why we get cache miss on second call")
        
        # Test cache write performance
        print(f"\n4️⃣ Testing Cache Write Performance...")
        start_time = time.time()
        write_success = await cache.cache_personalization_response(
            user_id=user_id,
            query=query1,
            context=context,
            response=test_response,
            ttl=300
        )
        write_time = (time.time() - start_time) * 1000
        print(f"   Cache write success: {write_success}")
        print(f"   Cache write time: {write_time:.1f}ms")
        
        if write_time > 200:
            print("   ⚠️ SLOW WRITE: Cache write is slower than expected")
        
        # Test cache read performance with SAME query
        print(f"\n5️⃣ Testing Cache Read with SAME Query...")
        start_time = time.time()
        cached_result_same = await cache.get_cached_personalization(
            user_id=user_id,
            query=query1,  # Same query
            context=context
        )
        read_time_same = (time.time() - start_time) * 1000
        
        print(f"   Cache read (same query): {cached_result_same is not None}")
        print(f"   Cache read time: {read_time_same:.1f}ms")
        
        # Test cache read with DIFFERENT query
        print(f"\n6️⃣ Testing Cache Read with DIFFERENT Query...")
        start_time = time.time()
        cached_result_diff = await cache.get_cached_personalization(
            user_id=user_id,
            query=query2,  # Different query
            context=context
        )
        read_time_diff = (time.time() - start_time) * 1000
        
        print(f"   Cache read (different query): {cached_result_diff is not None}")
        print(f"   Cache read time: {read_time_diff:.1f}ms")
        
        # Cache statistics
        print(f"\n7️⃣ Cache Statistics...")
        stats = await cache.get_cache_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        # Redis direct test
        print(f"\n8️⃣ Redis Direct Operations Test...")
        test_key = "direct_test_key"
        test_value = "direct_test_value"
        
        start_time = time.time()
        redis_write = await redis_service.set(test_key, test_value, ttl=60)
        redis_write_time = (time.time() - start_time) * 1000
        
        start_time = time.time()
        redis_read = await redis_service.get(test_key)
        redis_read_time = (time.time() - start_time) * 1000
        
        print(f"   Redis direct write: {redis_write} ({redis_write_time:.1f}ms)")
        print(f"   Redis direct read: {redis_read == test_value} ({redis_read_time:.1f}ms)")
        
        # Analysis and recommendations
        print(f"\n🎯 ANALYSIS AND FINDINGS:")
        print("="*40)
        
        if hash1 != hash2:
            print("❌ PROBLEM: Different queries generate different cache keys")
            print("   - This is why cache never hits on follow-up queries")
            print("   - Queries like 'show recommendations' vs 'show me more' get different hashes")
        
        if write_time > 200 or read_time_same > 200:
            print("❌ PROBLEM: Redis operations are slow")
            print(f"   - Write: {write_time:.1f}ms (should be <100ms)")
            print(f"   - Read: {read_time_same:.1f}ms (should be <100ms)")
        
        if not cached_result_same:
            print("❌ CRITICAL: Cache write/read cycle not working")
            print("   - Even identical queries don't hit cache")
        
        return {
            "cache_works_same_query": cached_result_same is not None,
            "cache_works_diff_query": cached_result_diff is not None,
            "hash_identical": hash1 == hash2,
            "redis_performance_ok": redis_write_time < 100 and redis_read_time < 100,
            "overall_diagnosis": "See analysis above"
        }
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(test_cache_diagnosis())
        print(f"\n" + "="*60)
        if result:
            print("✅ Diagnosis completed - see findings above")
        else:
            print("❌ Diagnosis failed")
    except Exception as e:
        print(f"\n💥 Test script failed: {e}")
