"""
Test completo del endpoint de conversación con adaptación de mercado
"""

import requests
import json
from datetime import datetime

def test_conversation_endpoint():
    """Prueba el endpoint de conversación"""
    
    API_URL = "http://localhost:8000/v1/mcp/conversation"
    API_KEY = "2fed9999056fab6dac5654238f0cae1c"
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    print("🧪 TEST DEL ENDPOINT DE CONVERSACIÓN")
    print("=" * 60)
    
    # Test 1: Con market_id = US
    print("\n1️⃣ Test con market_id = US")
    data = {
        "query": "busco aros de oro elegantes",
        "market_id": "US",
        "session_id": f"test_us_{int(datetime.now().timestamp())}"
    }
    
    response = requests.post(API_URL, headers=headers, json=data)
    
    if response.status_code == 200:
        result = response.json()
        print("✅ Respuesta exitosa")
        
        # Verificar recomendaciones
        recommendations = result.get("recommendations", [])
        print(f"\nRecomendaciones recibidas: {len(recommendations)}")
        
        if recommendations:
            first_rec = recommendations[0]
            print(f"\nPrimera recomendación:")
            print(f"  Título: {first_rec.get('title')}")
            print(f"  Precio: ${first_rec.get('price')} {first_rec.get('currency')}")
            
            # Verificar adaptación
            if "_market_adaptation" in first_rec:
                adaptation = first_rec["_market_adaptation"]
                print(f"\n  Adaptación:")
                print(f"    Adaptado: {adaptation.get('adapted', False)}")
                print(f"    Market ID: {adaptation.get('market_id')}")
                if not adaptation.get('adapted'):
                    print(f"    Error: {adaptation.get('error')}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
    
    # Test 2: Con market_id = default
    print("\n\n2️⃣ Test con market_id = default")
    data["market_id"] = "default"
    data["session_id"] = f"test_default_{int(datetime.now().timestamp())}"
    
    response = requests.post(API_URL, headers=headers, json=data)
    
    if response.status_code == 200:
        result = response.json()
        print("✅ Respuesta exitosa")
        
        recommendations = result.get("recommendations", [])
        if recommendations:
            first_rec = recommendations[0]
            print(f"\nPrimera recomendación:")
            print(f"  Precio: ${first_rec.get('price')} {first_rec.get('currency')}")
            
            if "_market_adaptation" in first_rec:
                adaptation = first_rec["_market_adaptation"]
                print(f"  Adaptado: {adaptation.get('adapted', False)}")
                if adaptation.get('error'):
                    print(f"  Error: {adaptation.get('error')}")

if __name__ == "__main__":
    test_conversation_endpoint()
