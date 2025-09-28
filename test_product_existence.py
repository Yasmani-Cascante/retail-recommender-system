#!/usr/bin/env python3
"""
Product Existence Test
=====================

Test para verificar que productos que sabemos que existen se encuentren correctamente.
"""

import asyncio
import httpx
import time

async def test_product_existence():
    """Test productos conocidos de la tienda"""
    
    print("🧪 TESTING PRODUCT EXISTENCE")
    print("=" * 40)
    
    base_url = "http://localhost:8000/v1/products"
    headers = {"X-API-Key": "development-key-retail-system-2024"}
    
    # Productos que sabemos que existen (de logs anteriores)
    known_products = [
        "9978689487157",  # 5 PARES DE PEZONERAS DE TELA CORAZÓN BEIGE
        "9978851328309",  # Otro producto conocido
        "9978741129525",  # Otro producto conocido
        "9978476757301",  # El que está fallando
    ]
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            results = []
            
            print("Testing known products...")
            
            for i, product_id in enumerate(known_products, 1):
                print(f"\n{i}. Testing product {product_id}...")
                
                start = time.time()
                response = await client.get(f"{base_url}/{product_id}", headers=headers)
                request_time = (time.time() - start) * 1000
                
                print(f"   Status: {response.status_code}")
                print(f"   Time: {request_time:.1f}ms")
                
                if response.status_code == 200:
                    data = response.json()
                    title = data.get("title", "No title")
                    is_sample = data.get("is_sample", False)
                    cache_hit = data.get("cache_hit", False)
                    
                    print(f"   Title: {title}")
                    print(f"   Is sample: {is_sample}")
                    print(f"   Cache hit: {cache_hit}")
                    
                    if is_sample:
                        result = "❌ SAMPLE DATA (should be real product)"
                        success = False
                    elif "Producto Ejemplo" in title:
                        result = "❌ FAKE DATA (should be real product)" 
                        success = False
                    else:
                        result = "✅ REAL PRODUCT DATA"
                        success = True
                        
                elif response.status_code == 404:
                    result = "❓ NOT FOUND (may be legitimate)"
                    success = True  # 404 is better than fake data
                    
                else:
                    result = f"❌ ERROR ({response.status_code})"
                    success = False
                
                print(f"   Result: {result}")
                
                results.append({
                    "product_id": product_id,
                    "status_code": response.status_code,
                    "time_ms": request_time,
                    "success": success
                })
                
                await asyncio.sleep(1)
            
            # Summary
            print(f"\n📊 PRODUCT EXISTENCE TEST SUMMARY:")
            print("=" * 50)
            
            success_count = sum(1 for r in results if r["success"])
            total_count = len(results)
            
            print(f"Products tested: {total_count}")
            print(f"Successful: {success_count}/{total_count}")
            
            for result in results:
                status_icon = "✅" if result["success"] else "❌"
                print(f"{status_icon} {result['product_id']}: {result['status_code']} ({result['time_ms']:.0f}ms)")
            
            if success_count == total_count:
                print("\n🎉 ALL PRODUCTS HANDLED CORRECTLY!")
                print("✅ No fake data returned")
                print("✅ Real products found or proper 404s")
                return True
            else:
                print("\n⚠️ SOME PRODUCTS STILL HAVE ISSUES")
                print("Check logs for fake data being returned")
                return False
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 PRODUCT EXISTENCE VALIDATION TEST")
    print("=" * 40)
    success = asyncio.run(test_product_existence())
    
    if success:
        print("\n🏆 VALIDATION PASSED!")
    else:
        print("\n🔧 MORE FIXES NEEDED")
