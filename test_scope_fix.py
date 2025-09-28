#!/usr/bin/env python3
"""
Test Rápido Post-Fix de Scope
==============================

Test para verificar que el scope fix resuelve el problema básico
"""

import requests
import sys
import os
import json
import time

from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def test_scope_fix():
    """Test rápido del scope fix"""
    
    print("🔧 TESTING SCOPE FIX - POST CORRECTION")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    api_key = os.getenv("API_KEY", "default_key")

    headers = {
        "X-API-Key": api_key,  # Usar la API key por defecto
        "Content-Type": "application/json"
    }
    
    request_data = {
        "query": "test recommendations",
        "user_id": "test_scope_fix",
        "session_id": f"scope_test_{int(time.time())}",
        "market_id": "US",
        "n_recommendations": 3
    }
    
    print("🧪 Ejecutando llamada de test...")
    print(f"   Query: {request_data['query']}")
    
    try:
        response = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=request_data,
            timeout=15
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            recommendations = data.get("recommendations", [])
            metadata = data.get("metadata", {})
            
            print(f"   ✅ Recommendations: {len(recommendations)}")
            print(f"   ✅ Diversification Applied: {metadata.get('diversification_applied', 'N/A')}")
            
            if len(recommendations) > 0:
                print("\n🎉 SCOPE FIX EXITOSO")
                print("   - Handler ya no falla por scope error")
                print("   - Recomendaciones se generan correctamente")
                print("   - Sistema funcional para test de diversificación")
                return True
            else:
                print("\n⚠️ SCOPE CORREGIDO PERO SIN RECOMENDACIONES")
                print("   - No hay error de scope")
                print("   - Pero sistema no genera recomendaciones")
                print("   - Posible problema en hybrid recommender")
                return False
                
        else:
            print(f"   ❌ Status Error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False

if __name__ == "__main__":
    result = test_scope_fix()
    print(f"\nResultado: {'✅ ÉXITO' if result else '❌ FALLA'}")
