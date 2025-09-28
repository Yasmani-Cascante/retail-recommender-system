# test_diversification_with_server.py
import requests
import time
import json

async def test_diversification_with_running_server():
    """Test diversificación con servidor FastAPI ejecutándose"""
    
    base_url = "http://localhost:8000"
    api_key = "2fed9999056fab6dac5654238f0cae1c"
    
    # Headers con API key
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    
    print("🧪 TESTING DIVERSIFICATION WITH RUNNING SERVER...")
    print("=" * 60)
    
    test_user_id = "test_user_diversification"
    test_session_id = f"test_session_{int(time.time())}"
    
    print(f"📋 Test User: {test_user_id}")
    print(f"📋 Test Session: {test_session_id}")
    print(f"📋 API Key: {api_key[:8]}...")
    print()
    
    try:
        # Primera llamada
        print("1️⃣ PRIMERA LLAMADA - 'show me some recommendations'")
        print("-" * 50)
        
        start_time = time.time()
        response1 = requests.post(
            f"{base_url}/v1/mcp/conversation", 
            json={
                "query": "show me some recommendations",
                "market_id": "US", 
                "session_id": test_session_id
            },
            headers=headers
        )
        call1_time = (time.time() - start_time) * 1000
        
        print(f"   ✅ Status Code: {response1.status_code}")
        print(f"   ✅ Response Time: {call1_time:.1f}ms")
        
        if response1.status_code == 200:
            data1 = response1.json()
            recs1 = data1.get("recommendations", [])
            metadata1 = data1.get("metadata", {})
            
            print(f"   ✅ Recommendations Count: {len(recs1)}")
            print(f"   ✅ Cache Hit: {metadata1.get('cache_hit', False)}")
            print(f"   ✅ Diversification Applied: {metadata1.get('diversification_applied', False)}")
            
            if len(recs1) > 0:
                recs1_ids = [rec.get('id') for rec in recs1 if rec.get('id')]
                print(f"   ✅ Recommendation IDs: {recs1_ids[:3]}...")
            else:
                print("   ⚠️ No recommendations returned")
        else:
            print(f"   ❌ Error Response: {response1.text}")
            return
        
        print()
        
        # Esperar un momento para simular tiempo real
        time.sleep(2)
        
        # Segunda llamada
        print("2️⃣ SEGUNDA LLAMADA - 'show me more'")
        print("-" * 50)
        
        start_time = time.time()
        response2 = requests.post(
            f"{base_url}/v1/mcp/conversation", 
            json={
                "query": "show me more",
                "market_id": "US",
                "session_id": test_session_id  # Mismo session_id
            },
            headers=headers
        )
        call2_time = (time.time() - start_time) * 1000
        
        print(f"   ✅ Status Code: {response2.status_code}")
        print(f"   ✅ Response Time: {call2_time:.1f}ms")
        
        if response2.status_code == 200:
            data2 = response2.json()
            recs2 = data2.get("recommendations", [])
            metadata2 = data2.get("metadata", {})
            
            print(f"   ✅ Recommendations Count: {len(recs2)}")
            print(f"   ✅ Cache Hit: {metadata2.get('cache_hit', False)}")
            print(f"   ✅ Diversification Applied: {metadata2.get('diversification_applied', False)}")
            
            if len(recs2) > 0:
                recs2_ids = [rec.get('id') for rec in recs2 if rec.get('id')]
                print(f"   ✅ Recommendation IDs: {recs2_ids[:3]}...")
            else:
                print("   ⚠️ No recommendations returned")
        else:
            print(f"   ❌ Error Response: {response2.text}")
            return
        
        print()
        
        # === ANÁLISIS DE DIVERSIFICACIÓN ===
        print("📊 ANÁLISIS DE DIVERSIFICACIÓN")
        print("-" * 50)
        
        if response1.status_code == 200 and response2.status_code == 200:
            data1 = response1.json()
            data2 = response2.json()
            
            recs1 = data1.get("recommendations", [])
            recs2 = data2.get("recommendations", [])
            
            recs1_ids = set(rec.get('id') for rec in recs1 if rec.get('id'))
            recs2_ids = set(rec.get('id') for rec in recs2 if rec.get('id'))
            
            common_ids = recs1_ids.intersection(recs2_ids)
            overlap_percentage = (len(common_ids) / max(len(recs1_ids), 1)) * 100
            
            print(f"   🔍 Recomendaciones 1: {len(recs1)} productos")
            print(f"   🔍 Recomendaciones 2: {len(recs2)} productos") 
            print(f"   🔍 Productos en común: {len(common_ids)}")
            print(f"   🔍 Porcentaje de overlap: {overlap_percentage:.1f}%")
            
            print()
            print("🎯 VERIFICACIÓN DE ÉXITO")
            print("-" * 50)
            
            # Criterios de éxito
            performance_ok = call1_time < 3000 and call2_time < 2000
            diversification_applied = data2.get("metadata", {}).get("diversification_applied", False)
            low_overlap = overlap_percentage < 50
            both_have_recs = len(recs1) > 0 and len(recs2) > 0
            
            print(f"   {'✅' if performance_ok else '❌'} Performance aceptable: Call1: {call1_time:.0f}ms, Call2: {call2_time:.0f}ms")
            print(f"   {'✅' if diversification_applied else '❌'} Diversificación aplicada en call 2: Applied: {diversification_applied}")
            print(f"   {'✅' if low_overlap else '❌'} Bajo overlap entre recomendaciones: Overlap: {overlap_percentage:.1f}%")
            print(f"   {'✅' if both_have_recs else '❌'} Ambas llamadas con recomendaciones: Recs1: {len(recs1)}, Recs2: {len(recs2)}")
            
            if all([performance_ok, diversification_applied, low_overlap, both_have_recs]):
                print()
                print("🎉 ✅ DIVERSIFICATION IMPLEMENTATION SUCCESS")
                print("   Todos los criterios de éxito cumplidos.")
            else:
                print()
                print("⚠️ IMPLEMENTACIÓN NECESITA AJUSTES")
                print("   Algunos criterios no se cumplieron.")
                
        print()
        print("=" * 60)
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: No se puede conectar al servidor")
        print("   Asegúrate de que el servidor esté ejecutándose:")
        print("   uvicorn src.api.main_unified_redis:app --reload --port 8000")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_diversification_with_running_server())