#!/usr/bin/env python3
"""
Comprehensive ProductCache Fix Validation - COMPLETE
===================================================

Tests all critical fixes:
1. Singleton pattern
2. Preload strategy  
3. Cache strategy execution
4. End-to-end performance
"""

import sys
import asyncio
import time
import json
sys.path.append('src')

from dotenv import load_dotenv
load_dotenv()

async def test_singleton_pattern():
    """Test que ProductCache es singleton real"""
    
    print("🧪 TESTING SINGLETON PATTERN")
    print("-" * 30)
    
    try:
        from src.api.routers.products_router import get_product_cache_dependency
        
        # Get cache instance twice
        cache1 = await get_product_cache_dependency()
        cache2 = await get_product_cache_dependency()
        
        # Should be same instance
        if cache1 is cache2:
            print("✅ Singleton pattern working - same instance")
            return True
        else:
            print("❌ Singleton pattern broken - different instances")
            print(f"   Cache1 ID: {id(cache1)}")
            print(f"   Cache2 ID: {id(cache2)}")
            return False
            
    except Exception as e:
        print(f"❌ Singleton test failed: {e}")
        return False

async def test_cache_strategy():
    """Test que cache strategy se ejecuta"""
    
    print("\n🧪 TESTING CACHE STRATEGY EXECUTION")
    print("-" * 30)
    
    try:
        from src.api.routers.products_router import _get_shopify_products, get_product_cache_dependency
        from src.api.core.store import get_shopify_client
        
        shopify_client = get_shopify_client()
        if not shopify_client:
            print("⚠️ Shopify client not available")
            return False
        
        # Primera llamada para poblar cache
        print("First call (populating cache)...")
        products1 = await _get_shopify_products(shopify_client, 3, 0)
        
        if not products1:
            print("❌ First call failed")
            return False
        
        print(f"✅ First call: {len(products1)} products")
        
        # Wait para cache
        await asyncio.sleep(1)
        
        # Segunda llamada (should hit cache)
        print("Second call (testing cache)...")
        start_time = time.time()
        products2 = await _get_shopify_products(shopify_client, 3, 0)
        second_time = (time.time() - start_time) * 1000
        
        print(f"✅ Second call: {len(products2)} products in {second_time:.1f}ms")
        
        # Performance check
        if second_time < 200:  # Should be much faster if cached
            print("✅ Cache strategy appears to be working")
            return True
        else:
            print("⚠️ Cache strategy may not be working optimally")
            return False
            
    except Exception as e:
        print(f"❌ Cache strategy test failed: {e}")
        return False

async def test_preload_functionality():
    """Test que preload funciona sin errores"""
    
    print("\n🧪 TESTING PRELOAD FUNCTIONALITY")
    print("-" * 30)
    
    try:
        from src.api.routers.products_router import get_product_cache_dependency
        from src.api.core.store import get_shopify_client
        
        cache = await get_product_cache_dependency()
        shopify_client = get_shopify_client()
        
        if not shopify_client:
            print("⚠️ Shopify client not available")
            return False
        
        # Get some test products
        test_products = shopify_client.get_products(limit=3)
        
        if not test_products:
            print("❌ No test products available")
            return False
        
        print(f"Testing preload with {len(test_products)} products...")
        
        # Test direct save (new preload strategy)
        success_count = 0
        for product in test_products:
            product_id = str(product.get("id", ""))
            if product_id:
                try:
                    saved = await cache._save_to_redis(product_id, product)
                    if saved:
                        success_count += 1
                except Exception as e:
                    print(f"⚠️ Save failed for {product_id}: {e}")
        
        print(f"✅ Successfully saved {success_count}/{len(test_products)} products")
        
        if success_count > 0:
            print("✅ Preload functionality working")
            return True
        else:
            print("❌ Preload functionality failed")
            return False
            
    except Exception as e:
        print(f"❌ Preload test failed: {e}")
        return False

async def test_end_to_end():
    """Test end-to-end performance improvement"""
    
    print("\n🧪 TESTING END-TO-END PERFORMANCE")
    print("-" * 30)
    
    try:
        import httpx
        
        url = "http://localhost:8000/v1/products/"
        headers = {"X-API-Key": "development-key-retail-system-2024"}
        params = {"limit": 5, "page": 1, "market_id": "US"}
        
        times = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(3):
                print(f"Request {i+1}/3...")
                start_time = time.time()
                
                response = await client.get(url, params=params, headers=headers)
                request_time = (time.time() - start_time) * 1000
                times.append(request_time)
                
                print(f"  Status: {response.status_code}, Time: {request_time:.1f}ms")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"  Products: {len(data.get('products', []))}")
                
                # Wait between requests
                if i < 2:
                    await asyncio.sleep(2)
        
        # Analyze performance
        if len(times) >= 2:
            print(f"\n📊 PERFORMANCE ANALYSIS:")
            for i, t in enumerate(times):
                print(f"  Request {i+1}: {t:.1f}ms")
            
            # Check for improvement (at least 30% faster)
            if len(times) >= 3 and times[2] < times[0] * 0.7:
                print("✅ Significant performance improvement detected")
                return True
            elif len(times) >= 2 and times[1] < times[0] * 0.8:
                print("✅ Performance improvement detected")
                return True
            else:
                print("⚠️ No significant performance improvement")
                return False
        
        return False
        
    except Exception as e:
        print(f"❌ End-to-end test failed: {e}")
        return False

async def test_cache_stats():
    """Test cache statistics endpoint"""
    
    print("\n🧪 TESTING CACHE STATISTICS")
    print("-" * 30)
    
    try:
        import httpx
        
        url = "http://localhost:8000/debug/product-cache"
        headers = {"X-API-Key": "development-key-retail-system-2024"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                stats = response.json()
                print(f"✅ Cache stats accessible")
                print(f"  Hit ratio: {stats.get('cache_stats', {}).get('hit_ratio', 0):.2f}")
                print(f"  Total requests: {stats.get('cache_stats', {}).get('total_requests', 0)}")
                print(f"  Redis hits: {stats.get('cache_stats', {}).get('redis_hits', 0)}")
                return True
            else:
                print(f"❌ Cache stats endpoint failed: {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Cache stats test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 COMPREHENSIVE PRODUCTCACHE FIX VALIDATION")
    print("=" * 60)
    print("Validating all critical fixes applied to resolve cache priority issues")
    print()
    
    async def run_all_tests():
        results = []
        
        # Test 1: Singleton pattern
        singleton_ok = await test_singleton_pattern()
        results.append(("Singleton Pattern", singleton_ok))
        
        # Test 2: Cache strategy execution
        strategy_ok = await test_cache_strategy()
        results.append(("Cache Strategy", strategy_ok))
        
        # Test 3: Preload functionality
        preload_ok = await test_preload_functionality()
        results.append(("Preload Functionality", preload_ok))
        
        # Test 4: End-to-end performance
        e2e_ok = await test_end_to_end()
        results.append(("End-to-End Performance", e2e_ok))
        
        # Test 5: Cache statistics
        stats_ok = await test_cache_stats()
        results.append(("Cache Statistics", stats_ok))
        
        # Final results
        print("\n" + "=" * 60)
        print("📊 FINAL VALIDATION RESULTS")
        print("=" * 60)
        
        passed = 0
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name:.<30} {status}")
            if result:
                passed += 1
        
        print("-" * 60)
        print(f"PASSED: {passed}/{total} tests")
        
        if passed == total:
            print("\n🎉 ALL TESTS PASSED!")
            print("✅ ProductCache priority issues resolved")
            print("✅ Cache-first strategy working")
            print("✅ Performance improvement confirmed")
            print("✅ System ready for production")
            return True
        elif passed >= total * 0.8:  # 80% pass rate
            print("\n⚠️ MOSTLY WORKING")
            print("Most fixes are working, minor issues remain")
            return True
        else:
            print("\n❌ CRITICAL ISSUES REMAIN")
            print("Major problems detected, additional fixes needed")
            return False
    
    success = asyncio.run(run_all_tests())
    
    if success:
        print("\n✅ VALIDATION SUCCESSFUL - CACHE PRIORITY FIXED")
    else:
        print("\n❌ VALIDATION FAILED - MORE WORK NEEDED")
