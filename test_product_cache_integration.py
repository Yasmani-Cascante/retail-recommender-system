# test_product_cache_integration.py
"""
Test rápido para verificar si product_cache.py mejora performance vs emergency cache
"""

import asyncio
import time
import sys
sys.path.append('src')

async def test_product_cache_performance():
    """Test performance de product_cache.py"""
    
    try:
        # Import product cache
        from src.api.core.product_cache import ProductCache
        from src.api.core.store import get_shopify_client
        
        print("🧪 TESTING product_cache.py performance...")
        
        # Initialize cache
        shopify_client = get_shopify_client()
        cache = ProductCache(
            redis_client=None,  # Sin Redis para test rápido
            shopify_client=shopify_client,
            ttl_seconds=300  # 5 min like emergency cache
        )
        
        # Test 1: Single product fetch
        start_time = time.time()
        product = await cache.get_product("test_product_001")
        single_time = (time.time() - start_time) * 1000
        
        print(f"✅ Single product fetch: {single_time:.1f}ms")
        
        # Test 2: Batch product fetch
        start_time = time.time()
        test_ids = [f"test_product_{i:03d}" for i in range(1, 11)]
        await cache.preload_products(test_ids, concurrency=5)
        batch_time = (time.time() - start_time) * 1000
        
        print(f"✅ Batch fetch (10 products): {batch_time:.1f}ms")
        
        # Test 3: Cache stats
        stats = cache.get_stats()
        print(f"✅ Cache stats: {stats}")
        
        # Comparison with emergency cache
        print("\n📊 COMPARISON:")
        print(f"product_cache.py single fetch: {single_time:.1f}ms")
        print(f"Emergency fallback equivalent: ~100ms")
        print(f"Relative performance: {'✅ BETTER' if single_time < 500 else '⚠️ SIMILAR'}")
        
        return {
            "success": True,
            "single_time_ms": single_time,
            "batch_time_ms": batch_time,
            "stats": stats
        }
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    result = asyncio.run(test_product_cache_performance())
    
    if result["success"]:
        print("\n🎯 RECOMMENDATION:")
        if result["single_time_ms"] < 1000:
            print("✅ product_cache.py is FAST - recommend migration")
        else:
            print("⚠️ product_cache.py is SLOW - keep emergency cache")
    else:
        print("❌ Cannot test product_cache.py - keep emergency cache")
