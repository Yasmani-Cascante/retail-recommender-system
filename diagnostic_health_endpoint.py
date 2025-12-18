# diagnostic_health_endpoint.py
"""
Script de diagnóstico para verificar qué retorna /v1/health/detailed
"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath('.'))

from httpx import AsyncClient, ASGITransport
from src.api.main_unified_redis import app

async def test_health_endpoint():
    """Test qué retorna el health endpoint"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        
        print("=" * 80)
        print("🔍 DIAGNOSTIC: Testing /v1/health/detailed endpoint")
        print("=" * 80)
        
        try:
            response = await client.get(
                "/v1/health/detailed",
                headers={"X-API-Key": "2fed9999056fab6dac5654238f0cae1c"}
            )
            
            print(f"\n✅ Status Code: {response.status_code}")
            print(f"\n📦 Response JSON:")
            
            if response.status_code == 200:
                data = response.json()
                import json
                print(json.dumps(data, indent=2))
                
                print(f"\n🔑 Top-level keys: {list(data.keys())}")
                
                # Análisis de estructura
                if "status" in data:
                    print(f"\n📊 Status keys: {list(data['status'].keys()) if isinstance(data['status'], dict) else type(data['status'])}")
                
                print("\n" + "=" * 80)
                
            else:
                print(f"❌ Error response: {response.text}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_health_endpoint())