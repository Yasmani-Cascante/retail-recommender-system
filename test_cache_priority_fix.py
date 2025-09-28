#!/usr/bin/env python3
"""
ProductCache Performance Test
============================

Valida que ProductCache está priorizando correctamente sobre Shopify.
"""

import sys
import asyncio
import time
sys.path.append('src')

from dotenv import load_dotenv
load_dotenv()

async def test_cache_priority():
    """Test que cache tiene prioridad sobre Shopify"""
    
    print("🧪 TESTING PRODUCTCACHE PRIORITY")
    print("=" * 50)
    
    try:
        from src.api.routers.products_router import _get_shopify_products, get_product_cache_dependency
        from src.api.core.store import get_shopify_client
        
        shopify_client = get_shopify_client()
        if not shopify_client:
            print("❌ Shopify client no disponible")
            return False
        
        # Test 1: Primera llamada (cache miss)
        print("\n1. Primera llamada (cache miss esperado)...")
        start_time = time.time()
        
        products1 = await _get_shopify_products(shopify_client, 3, 0)
        
        first_time = (time.time() - start_time) * 1000
        print(f"   Productos: {len(products1)}")
        print(f"   Tiempo: {first_time:.1f}ms")
        
        if products1:
            print("   ✅ Primera llamada exitosa")
        else:
            print("   ❌ Primera llamada falló")
            return False
        
        # Wait para que preload termine
        await asyncio.sleep(2)
        
        # Test 2: Segunda llamada (cache hit esperado)
        print("\n2. Segunda llamada (cache hit esperado)...")
        start_time = time.time()
        
        products2 = await _get_shopify_products(shopify_client, 3, 0)
        
        second_time = (time.time() - start_time) * 1000
        print(f"   Productos: {len(products2)}")
        print(f"   Tiempo: {second_time:.1f}ms")
        
        # Verificar performance improvement
        if second_time < first_time * 0.8:  # Al menos 20% más rápido
            print("   ✅ Cache hit detectado - performance mejorado")
            cache_working = True
        else:
            print("   ⚠️ No se detectó mejora de cache")
            cache_working = False
        
        # Test 3: Verificar cache stats
        print("\n3. Verificando cache statistics...")
        try:
            cache = await get_product_cache_dependency()
            stats = cache.get_stats()
            
            print(f"   Total requests: {stats.get('total_requests', 0)}")
            print(f"   Redis hits: {stats.get('redis_hits', 0)}")
            print(f"   Hit ratio: {stats.get('hit_ratio', 0):.2f}")
            
            if stats.get('redis_hits', 0) > 0:
                print("   ✅ Cache statistics muestran hits")
                stats_good = True
            else:
                print("   ⚠️ No se detectaron cache hits en stats")
                stats_good = False
                
        except Exception as e:
            print(f"   ❌ Error verificando stats: {e}")
            stats_good = False
        
        # Test 4: Verificar popular products
        print("\n4. Verificando popular products...")
        try:
            cache = await get_product_cache_dependency()
            popular = await cache.get_popular_products("US", 5)
            
            print(f"   Popular products encontrados: {len(popular)}")
            
            if len(popular) > 0:
                print("   ✅ Popular products funcionando")
                popular_working = True
            else:
                print("   ⚠️ Popular products no retorna resultados")
                popular_working = False
                
        except Exception as e:
            print(f"   ❌ Error verificando popular products: {e}")
            popular_working = False
        
        # Resultado final
        if cache_working and stats_good and popular_working:
            print("\n🎉 CACHE PRIORITY FIX SUCCESSFUL!")
            print("✅ Cache está funcionando correctamente")
            print("✅ Performance mejorado detectado")
            print("✅ Statistics y popular products funcionando")
            return True
        else:
            print("\n⚠️ CACHE ISSUES DETECTED")
            print(f"Cache working: {cache_working}")
            print(f"Stats good: {stats_good}")
            print(f"Popular working: {popular_working}")
            return False
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

async def test_endpoint_performance():
    """Test que el endpoint /products/ prioriza cache"""
    
    print("\n🧪 TESTING ENDPOINT CACHE PRIORITY")
    print("=" * 50)
    
    try:
        import httpx
        
        # Test endpoint con múltiples calls
        async with httpx.AsyncClient() as client:
            times = []
            
            for i in range(3):
                print(f"\nCall {i+1}/3...")
                
                start_time = time.time()
                
                response = await client.get(
                    "http://localhost:8000/v1/products/",
                    params={"limit": 3, "page": 1, "market_id": "US"},
                    headers={"X-API-Key": "development-key-retail-system-2024"}
                )
                
                request_time = (time.time() - start_time) * 1000
                times.append(request_time)
                
                print(f"   Status: {response.status_code}")
                print(f"   Tiempo: {request_time:.1f}ms")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"   Productos: {len(data.get('products', []))}")
                
                # Esperar entre requests
                if i < 2:
                    await asyncio.sleep(1)
            
            # Analizar performance improvement
            if len(times) >= 3:
                print(f"\n📊 ANÁLISIS DE PERFORMANCE:")
                print(f"   Call 1: {times[0]:.1f}ms")
                print(f"   Call 2: {times[1]:.1f}ms")
                print(f"   Call 3: {times[2]:.1f}ms")
                
                # Verificar mejora
                if times[2] < times[0] * 0.9:  # Al menos 10% mejora
                    print("   ✅ Performance improvement detectado")
                    return True
                else:
                    print("   ⚠️ No se detectó performance improvement")
                    return False
            
        return False
    
    except Exception as e:
        print(f"❌ Endpoint test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 PRODUCTCACHE PRIORITY VALIDATION")
    print("=" * 60)
    
    # Test cache priority
    cache_ok = asyncio.run(test_cache_priority())
    
    # Test endpoint performance
    endpoint_ok = asyncio.run(test_endpoint_performance())
    
    if cache_ok and endpoint_ok:
        print("\n🎯 VALIDATION SUCCESSFUL!")
        print("✅ ProductCache priority working")
        print("✅ Endpoint performance improved")
        print("✅ Cache-first strategy implemented")
    else:
        print("\n⚠️ SOME ISSUES REMAIN")
        print("Check individual test results above")
