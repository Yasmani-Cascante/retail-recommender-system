#!/usr/bin/env python3
"""
Test Query Hash Fix Verification
================================

Test para verificar que el fix de normalización de queries funciona
y resolver el problema de cache miss entre queries similares.
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

async def test_query_hash_fix():
    print("🧪 TESTING QUERY HASH FIX...")
    print("=" * 50)
    
    try:
        # Importar componentes
        from src.api.core.intelligent_personalization_cache import IntelligentPersonalizationCache
        from src.api.factories.service_factory import ServiceFactory
        
        # Obtener Redis service
        redis_service = await ServiceFactory.get_redis_service()
        cache = IntelligentPersonalizationCache(redis_service)
        
        # Test data
        user_id = "test_user_hash_fix"
        context = {
            "market_id": "US",
            "user_segment": "standard",
            "product_categories": ["electronics"]
        }
        
        # Test las queries exactas de los logs
        query1 = "Show me some recomendations"  # Query original
        query2 = "show me more"                  # Query follow-up
        
        print("\\n1️⃣ Testing Query Normalization:")
        
        # Test normalization
        norm1 = cache._normalize_query_for_cache(query1)
        norm2 = cache._normalize_query_for_cache(query2)
        
        print(f"   Query 1: '{query1}'")
        print(f"   Normalized: '{norm1}'")
        print(f"   Query 2: '{query2}'")
        print(f"   Normalized: '{norm2}'")
        
        # Test hash generation
        hash1 = cache._generate_query_hash(query1, context)
        hash2 = cache._generate_query_hash(query2, context)
        
        print(f"\\n2️⃣ Testing Hash Generation:")
        print(f"   Hash 1: {hash1}")
        print(f"   Hash 2: {hash2}")
        print(f"   Hashes identical: {hash1 == hash2}")
        
        if hash1 == hash2:
            print("   ✅ SUCCESS: Queries now generate same hash!")
        else:
            print("   ❌ ISSUE: Queries still generate different hashes")
            print(f"   Debug - Norm1: {norm1}, Norm2: {norm2}")
            return False
        
        # Test cache write/read cycle
        print("\\n3️⃣ Testing Cache Write/Read Cycle:")
        
        test_response = {
            "personalized_response": "Here are electronics recommendations!",
            "personalized_recommendations": [
                {"id": "1", "title": "Test Product 1"},
                {"id": "2", "title": "Test Product 2"}
            ],
            "personalization_metadata": {
                "strategy_used": "test_strategy",
                "personalization_score": 0.9
            }
        }
        
        # Write con primera query
        print(f"   Writing cache with: '{query1}'")
        start_time = time.time()
        write_success = await cache.cache_personalization_response(
            user_id=user_id,
            query=query1,
            context=context,
            response=test_response,
            ttl=300
        )
        write_time = (time.time() - start_time) * 1000
        print(f"   Cache write: {write_success} ({write_time:.1f}ms)")
        
        # Read con segunda query (similar)
        print(f"   Reading cache with: '{query2}'")
        start_time = time.time()
        cached_result = await cache.get_cached_personalization(
            user_id=user_id,
            query=query2,
            context=context
        )
        read_time = (time.time() - start_time) * 1000
        
        if cached_result:
            print(f"   ✅ CACHE HIT: {read_time:.1f}ms")
            print(f"   Cache age: {cached_result.get('personalization_metadata', {}).get('cache_age_seconds', 0):.1f}s")
            print("   🎉 SUCCESS: Fix is working correctly!")
        else:
            print(f"   ❌ CACHE MISS: {read_time:.1f}ms")
            print("   Something is still wrong with cache")
            return False
        
        # Test additional query variations
        print("\\n4️⃣ Testing Additional Query Variations:")
        
        test_queries = [
            "Show me recommendations",
            "show me some recommendations", 
            "find me more products",
            "show me other items"
        ]
        
        for test_query in test_queries:
            norm = cache._normalize_query_for_cache(test_query)
            test_hash = cache._generate_query_hash(test_query, context)
            matches_original = test_hash == hash1
            
            print(f"   '{test_query}' → '{norm}' → Match: {matches_original}")
        
        # Performance comparison
        print("\\n5️⃣ Performance Comparison:")
        print(f"   Without cache: ~1500-1800ms (Claude API call)")
        print(f"   With cache hit: {read_time:.1f}ms")
        if read_time > 0:
            improvement = ((1600 - read_time) / 1600) * 100
            print(f"   Performance improvement: {improvement:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"\\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(test_query_hash_fix())
        print(f"\\n" + "="*50)
        if result:
            print("✅ QUERY HASH FIX WORKING CORRECTLY")
            print("Cache should now hit on similar queries!")
        else:
            print("❌ Query hash fix has issues")
    except Exception as e:
        print(f"\\n💥 Test script failed: {e}")
