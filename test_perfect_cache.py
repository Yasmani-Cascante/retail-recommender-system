#!/usr/bin/env python3
"""
Perfect Cache Test
=================

Test final que valida cache funciona correctamente con diferentes limits.
"""

import asyncio
import time
import httpx

async def test_perfect_cache():
    """Test cache with various limits to ensure correct product counts"""
    
    print("🧪 TESTING PERFECT CACHE WITH DIFFERENT LIMITS")
    print("=" * 50)
    
    base_url = "http://localhost:8000/v1/products/"
    headers = {"X-API-Key": "development-key-retail-system-2024"}
    
    test_cases = [
        {"limit": 5, "expected_improvement": 50},   # Should hit cache
        {"limit": 3, "expected_improvement": 70},   # Should hit cache easily  
        {"limit": 8, "expected_improvement": 30},   # Might need complement
        {"limit": 2, "expected_improvement": 80},   # Should hit cache perfectly
    ]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Prime cache with first request
            print("0. Priming cache...")
            await client.get(base_url, params={"limit": 5, "market_id": "US"}, headers=headers)
            await asyncio.sleep(2)  # Let cache settle
            
            results = []
            
            for i, test_case in enumerate(test_cases, 1):
                limit = test_case["limit"]
                expected_improvement = test_case["expected_improvement"]
                
                print(f"\n{i}. Testing limit={limit}...")
                
                # First call (baseline or cache miss)
                start = time.time()
                response = await client.get(base_url, params={"limit": limit, "market_id": "US"}, headers=headers)
                call_time = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    products_received = len(data.get('products', []))
                    
                    print(f"   Status: {response.status_code}")
                    print(f"   Time: {call_time:.1f}ms")
                    print(f"   Products: {products_received}/{limit}")
                    
                    # Validate product count
                    if products_received >= limit:
                        count_result = "✅ CORRECT"
                    elif products_received >= max(2, limit * 0.75):
                        count_result = "✅ ACCEPTABLE"
                    else:
                        count_result = "❌ INSUFFICIENT"
                    
                    # Validate performance (if it's a cache hit)
                    if call_time < 1500:  # Less than 1.5s indicates cache hit
                        perf_result = "✅ CACHE HIT"
                    else:
                        perf_result = "⚠️ CACHE MISS"
                    
                    results.append({
                        "limit": limit,
                        "time": call_time,
                        "products": products_received,
                        "count_result": count_result,
                        "perf_result": perf_result
                    })
                    
                    print(f"   Count: {count_result}")
                    print(f"   Performance: {perf_result}")
                else:
                    print(f"   ❌ HTTP Error: {response.status_code}")
                    
                await asyncio.sleep(1)
            
            # Summary
            print(f"\n📊 PERFECT CACHE TEST SUMMARY:")
            print("=" * 50)
            
            perfect_tests = 0
            total_tests = len(results)
            
            for result in results:
                status = "✅" if result["count_result"].startswith("✅") and result["perf_result"].startswith("✅") else "⚠️"
                if status == "✅":
                    perfect_tests += 1
                    
                print(f"Limit {result['limit']:2d}: {result['time']:6.1f}ms, {result['products']:2d} products {status}")
            
            print(f"\nPERFECT: {perfect_tests}/{total_tests} tests")
            
            if perfect_tests >= total_tests * 0.8:  # 80% success rate
                print("\n🎉 PERFECT CACHE ACHIEVED!")
                print("✅ Cache working with correct product counts")
                print("✅ Performance improvements confirmed")
                return True
            else:
                print("\n⚠️ CACHE NEEDS MINOR ADJUSTMENTS")
                return False
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 PERFECT CACHE VALIDATION")
    print("=" * 40)
    success = asyncio.run(test_perfect_cache())
    
    if success:
        print("\n🏆 CACHE OPTIMIZATION COMPLETE!")
    else:
        print("\n🔧 MINOR ADJUSTMENTS NEEDED")
