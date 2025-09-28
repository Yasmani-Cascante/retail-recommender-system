#!/usr/bin/env python3
"""
Shopify Request Monitoring
=========================

Monitorea el performance de requests a Shopify para detectar problemas.
"""

import time
import asyncio
import sys
sys.path.append('src')

from dotenv import load_dotenv
load_dotenv()

async def monitor_shopify_requests():
    """Monitorea varios tipos de requests"""
    
    print("📊 SHOPIFY REQUEST MONITORING")
    print("=" * 50)
    
    try:
        from src.api.core.store import get_shopify_client
        
        client = get_shopify_client()
        if not client:
            print("❌ Shopify client no disponible")
            return
        
        # Tests de diferentes tamaños
        test_cases = [
            {"limit": 1, "offset": 0, "name": "Single product"},
            {"limit": 3, "offset": 0, "name": "Small batch"},
            {"limit": 10, "offset": 0, "name": "Medium batch"},
            {"limit": 25, "offset": 0, "name": "Large batch"},
            {"limit": 5, "offset": 10, "name": "Offset pagination"},
        ]
        
        results = []
        
        for test_case in test_cases:
            print(f"\n🧪 {test_case['name']} (limit={test_case['limit']}, offset={test_case['offset']})...")
            
            start_time = time.time()
            
            try:
                products = client.get_products(
                    limit=test_case['limit'], 
                    offset=test_case['offset']
                )
                
                duration = (time.time() - start_time) * 1000
                count = len(products) if products else 0
                
                result = {
                    **test_case,
                    "duration_ms": duration,
                    "products_returned": count,
                    "status": "success",
                    "efficiency": count / (duration / 1000) if duration > 0 else 0  # products per second
                }
                
                print(f"   ✅ {count} productos en {duration:.1f}ms ({result['efficiency']:.1f} prod/sec)")
                
            except Exception as e:
                result = {
                    **test_case,
                    "duration_ms": 0,
                    "products_returned": 0,
                    "status": "error",
                    "error": str(e),
                    "efficiency": 0
                }
                
                print(f"   ❌ Error: {e}")
            
            results.append(result)
            
            # Pequeña pausa entre tests
            await asyncio.sleep(1)
        
        # Resumen de resultados
        print("\n📊 RESUMEN DE PERFORMANCE:")
        print("=" * 50)
        
        successful_tests = [r for r in results if r["status"] == "success"]
        
        if successful_tests:
            avg_efficiency = sum(r["efficiency"] for r in successful_tests) / len(successful_tests)
            max_duration = max(r["duration_ms"] for r in successful_tests)
            min_duration = min(r["duration_ms"] for r in successful_tests)
            
            print(f"✅ Tests exitosos: {len(successful_tests)}/{len(results)}")
            print(f"📈 Eficiencia promedio: {avg_efficiency:.1f} productos/segundo")
            print(f"⏱️ Tiempo máximo: {max_duration:.1f}ms")
            print(f"⚡ Tiempo mínimo: {min_duration:.1f}ms")
            
            # Determinar estado del sistema
            if max_duration < 10000 and avg_efficiency > 0.5:
                print("\n🎉 SISTEMA OPTIMIZADO")
                print("✅ Todos los requests dentro de tiempos aceptables")
            elif max_duration < 20000:
                print("\n⚠️ SISTEMA FUNCIONAL")
                print("Algunos requests pueden ser lentos pero aceptables")
            else:
                print("\n❌ SISTEMA NECESITA OPTIMIZACIÓN")
                print("Requests demasiado lentos")
        else:
            print("❌ No se completaron tests exitosos")
        
    except Exception as e:
        print(f"❌ Monitoring failed: {e}")

if __name__ == "__main__":
    asyncio.run(monitor_shopify_requests())
