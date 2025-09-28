#!/usr/bin/env python3
"""
Individual Product Performance Test
==================================

Test específico para validar optimización de productos individuales.
"""

import asyncio
import httpx
import time

async def test_individual_product_performance():
    """Test performance de productos individuales"""
    
    print("🧪 TESTING INDIVIDUAL PRODUCT PERFORMANCE")
    print("=" * 50)
    
    base_url = "http://localhost:8000/v1/products"
    debug_url = "http://localhost:8000/debug/product"
    headers = {"X-API-Key": "development-key-retail-system-2024"}
    
    # Test products (usar IDs reales si están disponibles)
    test_products = [
        "9978689487157",
        "9978851328309", 
        "9978741129525",
        "test_product_001"  # Fallback test
    ]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            results = []
            
            print("1. Testing individual product endpoints...")
            
            for i, product_id in enumerate(test_products, 1):
                print(f"\n{i}. Testing product {product_id}...")
                
                # Test 1: First call (cache miss expected)
                start = time.time()
                response1 = await client.get(f"{base_url}/{product_id}", headers=headers)
                time1 = (time.time() - start) * 1000
                
                print(f"   First call: {response1.status_code}, {time1:.1f}ms")
                
                if response1.status_code == 200:
                    data1 = response1.json()
                    cache_hit1 = data1.get("cache_hit", False)
                    print(f"   Cache hit: {cache_hit1}")
                
                # Wait a moment
                await asyncio.sleep(0.5)
                
                # Test 2: Second call (cache hit expected)
                start = time.time()
                response2 = await client.get(f"{base_url}/{product_id}", headers=headers)
                time2 = (time.time() - start) * 1000
                
                print(f"   Second call: {response2.status_code}, {time2:.1f}ms")
                
                if response2.status_code == 200:
                    data2 = response2.json()
                    cache_hit2 = data2.get("cache_hit", False)
                    print(f"   Cache hit: {cache_hit2}")
                
                # Test 3: Debug endpoint
                try:
                    debug_response = await client.get(f"{debug_url}/{product_id}", headers=headers)
                    if debug_response.status_code == 200:
                        debug_data = debug_response.json()
                        cache_time = debug_data.get("cache", {}).get("time_ms")
                        shopify_time = debug_data.get("shopify", {}).get("time_ms")
                        print(f"   Debug - Cache: {cache_time}ms, Shopify: {shopify_time}ms")
                except:
                    print("   Debug endpoint not available")
                
                # Analyze performance
                improvement = ((time1 - time2) / time1 * 100) if time1 > 0 and time2 > 0 else 0
                
                result = {
                    "product_id": product_id,
                    "first_call_ms": time1,
                    "second_call_ms": time2,
                    "improvement_percent": improvement,
                    "cache_working": time2 < time1 * 0.8,  # 20% improvement minimum
                    "acceptable_performance": time2 < 500   # Under 500ms for cached
                }
                
                results.append(result)
                print(f"   Improvement: {improvement:.1f}%")
                
                await asyncio.sleep(0.5)
            
            # Summary
            print(f"\n📊 INDIVIDUAL PRODUCT TEST SUMMARY:")
            print("=" * 50)
            
            working_cache = sum(1 for r in results if r["cache_working"])
            good_performance = sum(1 for r in results if r["acceptable_performance"])
            avg_improvement = sum(r["improvement_percent"] for r in results) / len(results)
            
            print(f"Products tested: {len(results)}")
            print(f"Cache working: {working_cache}/{len(results)}")
            print(f"Good performance: {good_performance}/{len(results)}")
            print(f"Average improvement: {avg_improvement:.1f}%")
            
            for result in results:
                status = "✅" if result["cache_working"] and result["acceptable_performance"] else "⚠️"
                print(f"{status} {result['product_id']}: {result['first_call_ms']:.0f}ms → {result['second_call_ms']:.0f}ms ({result['improvement_percent']:.1f}%)")
            
            if working_cache >= len(results) * 0.8 and good_performance >= len(results) * 0.8:
                print("\n🎉 INDIVIDUAL PRODUCT OPTIMIZATION SUCCESSFUL!")
                print("✅ Cache working effectively")
                print("✅ Performance targets met")
                return True
            else:
                print("\n⚠️ INDIVIDUAL PRODUCT OPTIMIZATION NEEDS WORK")
                print("Some products not meeting performance targets")
                return False
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 INDIVIDUAL PRODUCT PERFORMANCE TEST")
    print("=" * 40)
    success = asyncio.run(test_individual_product_performance())
    
    if success:
        print("\n🏆 OPTIMIZATION VALIDATED!")
    else:
        print("\n🔧 MORE OPTIMIZATION NEEDED")
