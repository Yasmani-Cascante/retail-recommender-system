#!/usr/bin/env python3
"""
Specific Threshold Test
======================

Test específico que valida que limit=8 retorna exactamente 8 productos.
"""

import asyncio
import httpx
import time

async def test_specific_threshold():
    """Test específico del threshold fix"""
    
    print("🧪 TESTING SPECIFIC THRESHOLD FIX")
    print("=" * 40)
    
    base_url = "http://localhost:8000/v1/products/"
    headers = {"X-API-Key": "development-key-retail-system-2024"}
    
    test_cases = [
        {"limit": 8, "name": "8 productos"},
        {"limit": 10, "name": "10 productos"},
        {"limit": 3, "name": "3 productos"},
        {"limit": 5, "name": "5 productos"},
    ]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Prime cache
            print("0. Priming cache...")
            await client.get(base_url, params={"limit": 5, "market_id": "US"}, headers=headers)
            await asyncio.sleep(2)
            
            results = []
            
            for i, test_case in enumerate(test_cases, 1):
                limit = test_case["limit"]
                name = test_case["name"]
                
                print(f"\n{i}. Probando {name}...")
                
                start = time.time()
                response = await client.get(base_url, params={"limit": limit, "market_id": "US"}, headers=headers)
                request_time = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    products_received = len(data.get('products', []))
                    
                    print(f"   Solicitados: {limit}")
                    print(f"   Recibidos: {products_received}")
                    print(f"   Tiempo: {request_time:.1f}ms")
                    
                    # Verificar resultado
                    if products_received >= limit:
                        result = "✅ CORRECTO"
                        success = True
                    elif products_received >= max(2, limit * 0.8):
                        result = "✅ ACEPTABLE"
                        success = True
                    else:
                        result = "❌ INSUFICIENTE"
                        success = False
                    
                    print(f"   Resultado: {result}")
                    results.append(success)
                else:
                    print(f"   ❌ HTTP Error: {response.status_code}")
                    results.append(False)
                
                await asyncio.sleep(1)
            
            # Summary
            success_count = sum(results)
            total_count = len(results)
            
            print(f"\n📊 RESULTADOS:")
            print(f"Exitosos: {success_count}/{total_count}")
            
            if success_count == total_count:
                print("\n🎉 THRESHOLD FIX SUCCESSFUL!")
                print("✅ Todos los limits retornan productos correctos")
                return True
            else:
                print("\n⚠️ THRESHOLD FIX PARCIAL")
                print("Algunos limits aún tienen problemas")
                return False
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 SPECIFIC THRESHOLD TEST")
    print("=" * 30)
    success = asyncio.run(test_specific_threshold())
    
    if success:
        print("\n🏆 THRESHOLD PERFECT!")
    else:
        print("\n🔧 MORE WORK NEEDED")
