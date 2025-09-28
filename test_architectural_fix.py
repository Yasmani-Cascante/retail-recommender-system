#!/usr/bin/env python3
"""
Architectural Fix Validation Test
================================

Test para validar que el fix arquitectónico funciona:
- Direct API call O(1) vs búsqueda lineal O(n)
- Performance improvement significativo
- Correctness mantenido
"""

import asyncio
import httpx
import time

async def test_architectural_fix():
    """Test del fix arquitectónico"""
    
    print("🏗️ TESTING ARCHITECTURAL FIX")
    print("=" * 40)
    
    base_url = "http://localhost:8000"
    headers = {"X-API-Key": "development-key-retail-system-2024"}
    
    # Productos de test (incluyendo el que estaba fallando)
    test_products = [
        "9978476757301",  # El que estaba fallando
        "9978689487157",  # Producto conocido
        "9978851328309",  # Otro conocido
        "fake_product_123" # Para test 404
    ]
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            print("1. Testing individual products with new architecture...")
            
            individual_results = []
            
            for i, product_id in enumerate(test_products, 1):
                print(f"\n{i}. Testing product {product_id}...")
                
                # Test endpoint individual
                start = time.time()
                response = await client.get(f"{base_url}/v1/products/{product_id}", headers=headers)
                individual_time = (time.time() - start) * 1000
                
                print(f"   Status: {response.status_code}")
                print(f"   Time: {individual_time:.1f}ms")
                
                if response.status_code == 200:
                    data = response.json()
                    title = data.get("title", "No title")
                    is_sample = data.get("is_sample", False)
                    fetch_strategy = data.get("fetch_strategy", "unknown")
                    
                    print(f"   Title: {title}")
                    print(f"   Is sample: {is_sample}")
                    print(f"   Fetch strategy: {fetch_strategy}")
                    
                    # Validar que no sea datos falsos
                    is_real = not is_sample and "Producto Ejemplo" not in title
                    
                    individual_results.append({
                        "product_id": product_id,
                        "time_ms": individual_time,
                        "found": True,
                        "is_real": is_real,
                        "fetch_strategy": fetch_strategy
                    })
                    
                elif response.status_code == 404:
                    print(f"   ✅ Proper 404 for missing product")
                    individual_results.append({
                        "product_id": product_id,
                        "time_ms": individual_time,
                        "found": False,
                        "is_real": True,  # 404 is correct behavior
                        "fetch_strategy": "not_found"
                    })
                else:
                    print(f"   ❌ Unexpected status: {response.status_code}")
                
                await asyncio.sleep(0.5)
            
            # Test performance comparison si está disponible
            print("\n2. Testing performance comparison...")
            
            comparison_results = []
            
            for product_id in test_products[:2]:  # Solo productos reales
                try:
                    print(f"\nComparing methods for {product_id}...")
                    
                    comparison_response = await client.get(
                        f"{base_url}/debug/product-comparison/{product_id}", 
                        headers=headers
                    )
                    
                    if comparison_response.status_code == 200:
                        comparison_data = comparison_response.json()
                        
                        results = comparison_data.get("results", {})
                        ranking = comparison_data.get("performance_ranking", [])
                        improvement = comparison_data.get("recommendation", {}).get("direct_api_vs_search_improvement", "N/A")
                        
                        print(f"   Performance ranking: {ranking}")
                        print(f"   Direct API vs Search improvement: {improvement}")
                        
                        comparison_results.append({
                            "product_id": product_id,
                            "comparison": results,
                            "improvement": improvement
                        })
                    else:
                        print(f"   Comparison not available ({comparison_response.status_code})")
                        
                except Exception as e:
                    print(f"   Comparison failed: {e}")
                
                await asyncio.sleep(0.5)
            
            # Summary
            print(f"\n📊 ARCHITECTURAL FIX TEST SUMMARY:")
            print("=" * 50)
            
            # Individual endpoint analysis
            real_products = [r for r in individual_results if r["found"] and r["is_real"]]
            fast_products = [r for r in real_products if r["time_ms"] < 1000]
            direct_api_used = [r for r in real_products if r.get("fetch_strategy") == "direct_api"]
            
            print(f"Products tested: {len(individual_results)}")
            print(f"Real products found: {len(real_products)}")
            print(f"Fast responses (<1s): {len(fast_products)}")
            print(f"Direct API strategy used: {len(direct_api_used)}")
            
            if real_products:
                avg_time = sum(r["time_ms"] for r in real_products) / len(real_products)
                print(f"Average response time: {avg_time:.1f}ms")
            
            # Performance comparison analysis
            if comparison_results:
                print(f"\nPerformance comparisons available: {len(comparison_results)}")
                for comp in comparison_results:
                    print(f"  {comp['product_id']}: {comp['improvement']} improvement")
            
            # Success criteria
            success_criteria = [
                len(real_products) >= len(test_products) - 1,  # All real products found (except fake)
                len(fast_products) >= len(real_products) * 0.8,  # 80% fast responses
                len(direct_api_used) > 0  # At least some using direct API
            ]
            
            if all(success_criteria):
                print("\n🎉 ARCHITECTURAL FIX SUCCESSFUL!")
                print("✅ Real products found correctly")
                print("✅ Performance targets met")
                print("✅ Direct API strategy working")
                return True
            else:
                print("\n⚠️ ARCHITECTURAL FIX NEEDS MORE WORK")
                print("Some criteria not met")
                return False
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 ARCHITECTURAL FIX VALIDATION TEST")
    print("=" * 40)
    success = asyncio.run(test_architectural_fix())
    
    if success:
        print("\n🏆 ARCHITECTURE VALIDATED!")
        print("O(1) direct API calls working correctly")
    else:
        print("\n🔧 MORE ARCHITECTURAL WORK NEEDED")
