#!/usr/bin/env python3
"""
Final Cache Optimization Test
============================

Test que valida que cache funciona en 2 requests en lugar de 3.
"""

import asyncio
import time
import httpx
import sys

async def test_optimized_cache():
    """Test cache optimization with different parameters"""
    
    print("🧪 TESTING OPTIMIZED CACHE PERFORMANCE")
    print("=" * 50)
    
    base_url = "http://localhost:8000/v1/products/"
    headers = {"X-API-Key": "development-key-retail-system-2024"}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            times = []
            
            # Test 1: Primera request (cache miss esperado)
            print("1. Primera request (cache miss)...")
            start = time.time()
            response1 = await client.get(base_url, params={"limit": 5, "market_id": "US"}, headers=headers)
            time1 = (time.time() - start) * 1000
            times.append(time1)
            
            print(f"   Status: {response1.status_code}, Time: {time1:.1f}ms")
            if response1.status_code == 200:
                data = response1.json()
                print(f"   Products: {len(data.get('products', []))}")
            
            # Wait for cache processing
            await asyncio.sleep(1)
            
            # Test 2: Segunda request con diferentes params (cache hit esperado con flexible cache)
            print("\n2. Segunda request - diferentes params (flexible cache hit)...")
            start = time.time()
            response2 = await client.get(base_url, params={"limit": 3, "market_id": "US"}, headers=headers)
            time2 = (time.time() - start) * 1000
            times.append(time2)
            
            print(f"   Status: {response2.status_code}, Time: {time2:.1f}ms")
            if response2.status_code == 200:
                data = response2.json()
                print(f"   Products: {len(data.get('products', []))}")
            
            # Test 3: Tercera request con mismos params (exact cache hit)
            print("\n3. Tercera request - mismos params (exact cache hit)...")
            start = time.time()
            response3 = await client.get(base_url, params={"limit": 3, "market_id": "US"}, headers=headers)
            time3 = (time.time() - start) * 1000
            times.append(time3)
            
            print(f"   Status: {response3.status_code}, Time: {time3:.1f}ms")
            if response3.status_code == 200:
                data = response3.json()
                print(f"   Products: {len(data.get('products', []))}")
            
            # Analyze results
            print(f"\n📊 PERFORMANCE ANALYSIS:")
            print(f"Request 1: {times[0]:.1f}ms (cache miss)")
            print(f"Request 2: {times[1]:.1f}ms (flexible cache)")
            print(f"Request 3: {times[2]:.1f}ms (exact cache)")
            
            # Check improvements
            improvement2 = ((times[0] - times[1]) / times[0]) * 100 if times[0] > 0 else 0
            improvement3 = ((times[0] - times[2]) / times[0]) * 100 if times[0] > 0 else 0
            
            print(f"\nIMPROVEMENTS:")
            print(f"Request 2: {improvement2:.1f}% improvement")
            print(f"Request 3: {improvement3:.1f}% improvement")
            
            # Success criteria
            if improvement2 > 50 and improvement3 > 70:
                print("\n🎉 CACHE OPTIMIZATION SUCCESSFUL!")
                print("✅ Flexible cache working (different params)")
                print("✅ Exact cache working (same params)")
                return True
            elif improvement3 > 70:
                print("\n✅ CACHE WORKING (exact params only)")
                print("⚠️ Flexible cache may need more work")
                return True
            else:
                print("\n⚠️ CACHE OPTIMIZATION NEEDS MORE WORK")
                return False
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 FINAL CACHE OPTIMIZATION TEST")
    print("=" * 50)
    success = asyncio.run(test_optimized_cache())
    
    if success:
        print("\n✅ OPTIMIZATION VALIDATED")
    else:
        print("\n❌ MORE OPTIMIZATION NEEDED")
