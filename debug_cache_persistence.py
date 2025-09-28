"""
Debug Script - Cache Persistence Investigation
===========================================

Script para diagnosticar por qué el cache no persiste entre llamadas.

Ejecutar: python debug_cache_persistence.py
"""

import asyncio
import json
import hashlib
import logging
import time

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_cache_persistence():
    """Debug completo del sistema de cache"""
    
    print("🔍 DEBUGGING CACHE PERSISTENCE...")
    print("=" * 50)
    
    try:
        # Test 1: Verificar Redis connection
        print("\n1️⃣ Testing Redis Connection...")
        
        try:
            from src.api.factories.service_factory import ServiceFactory
            redis_service = await ServiceFactory.get_redis_service()
            
            # Test basic Redis operations
            test_key = "debug_test_key"
            test_value = "debug_test_value"
            
            start_time = time.time()
            await redis_service.set(test_key, test_value, ttl=300)
            set_time = (time.time() - start_time) * 1000
            
            start_time = time.time()
            retrieved_value = await redis_service.get(test_key)
            get_time = (time.time() - start_time) * 1000
            
            print(f"   ✅ Redis SET: {set_time:.1f}ms")
            print(f"   ✅ Redis GET: {get_time:.1f}ms") 
            print(f"   ✅ Value match: {retrieved_value == test_value}")
            
            if get_time > 100:
                print(f"   ⚠️ WARNING: Redis GET is slow ({get_time:.1f}ms)")
                
        except Exception as e:
            print(f"   ❌ Redis connection failed: {e}")
            return False
        
        # Test 2: Verificar cache key generation
        print("\n2️⃣ Testing Cache Key Generation...")
        
        from src.api.core.intelligent_personalization_cache import IntelligentPersonalizationCache
        cache = IntelligentPersonalizationCache()
        
        # Simular misma query múltiples veces
        test_queries = [
            "show me electronics",
            "show me electronics",  # Identical
            "Show me electronics",  # Case different  
            "show me electronics ", # Trailing space
        ]
        
        test_context = {
            "market_id": "US",
            "user_segment": "standard",
            "product_categories": ["electronics"]
        }
        
        hashes = []
        for i, query in enumerate(test_queries):
            query_hash = cache._generate_query_hash(query, test_context)
            hashes.append(query_hash)
            print(f"   Query {i+1}: '{query}' → {query_hash}")
        
        unique_hashes = set(hashes)
        print(f"   📊 Unique hashes: {len(unique_hashes)} of {len(hashes)}")
        
        if len(unique_hashes) > 1:
            print("   ⚠️ WARNING: Similar queries generating different hashes")
            
        # Test 3: Simular cache write/read cycle
        print("\n3️⃣ Testing Cache Write/Read Cycle...")
        
        cache_with_redis = IntelligentPersonalizationCache(redis_service)
        
        test_user = "debug_user_123"
        test_query = "test personalization query"
        test_response = {
            "personalized_response": "Test personalized response",
            "personalized_recommendations": [{"id": "1", "title": "Test Product"}],
            "personalization_metadata": {
                "strategy_used": "test",
                "personalization_score": 0.8
            }
        }
        
        # Write to cache
        start_time = time.time()
        write_success = await cache_with_redis.cache_personalization_response(
            user_id=test_user,
            query=test_query,
            context=test_context,
            response=test_response,
            ttl=300
        )
        write_time = (time.time() - start_time) * 1000
        
        print(f"   ✅ Cache write: {write_success} ({write_time:.1f}ms)")
        
        # Read from cache immediately
        start_time = time.time()
        cached_result = await cache_with_redis.get_cached_personalization(
            user_id=test_user,
            query=test_query,
            context=test_context
        )
        read_time = (time.time() - start_time) * 1000
        
        print(f"   ✅ Cache read: {cached_result is not None} ({read_time:.1f}ms)")
        
        if cached_result:
            print(f"   ✅ Response match: {len(cached_result.get('personalized_response', ''))} chars")
        else:
            print("   ❌ Cache read returned None - PROBLEM IDENTIFIED")
            
        # Test 4: Check cache stats
        print("\n4️⃣ Cache Statistics...")
        stats = await cache_with_redis.get_cache_stats()
        for key, value in stats.items():
            print(f"   📊 {key}: {value}")
            
        return cached_result is not None
        
    except Exception as e:
        print(f"\n❌ DEBUG FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(debug_cache_persistence())
        if result:
            print(f"\n✅ Cache persistence working correctly")
        else:
            print(f"\n❌ Cache persistence has issues")
    except Exception as e:
        print(f"\n💥 Debug script failed: {e}")
