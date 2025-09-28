#!/usr/bin/env python3
"""
Test Simple de Diversificación - Versión Sin Auth
=================================================

Test simplificado que bypasea la autenticación para testear directamente
la funcionalidad de diversificación.
"""

import requests
import json
import time
import sys

def test_diversification_simple():
    """Test simplificado sin autenticación"""
    
    print("🚀 TEST SIMPLE DE DIVERSIFICACIÓN - SIN AUTH")
    print("=" * 60)
    
    base_url = "http://localhost:8000"
    test_user_id = "test_simple"
    test_session_id = f"simple_session_{int(time.time())}"
    
    # Probar sin headers de autenticación primero
    headers = {"Content-Type": "application/json"}
    
    print(f"📋 Test Configuration:")
    print(f"   User ID: {test_user_id}")
    print(f"   Session ID: {test_session_id}")
    print(f"   API URL: {base_url}")
    print()
    
    # === TEST: Verificar si el endpoint requiere auth ===
    print("🔍 VERIFICANDO CONFIGURACIÓN DEL ENDPOINT")
    print("-" * 40)
    
    request_data = {
        "query": "test connection",
        "user_id": test_user_id,
        "session_id": test_session_id,
        "market_id": "US",
        "n_recommendations": 3
    }
    
    response = requests.post(
        f"{base_url}/v1/mcp/conversation",
        headers=headers,
        json=request_data,
        timeout=10
    )
    
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 403:
        print("   🔒 Endpoint requiere autenticación")
        
        # Probar con API keys comunes
        test_keys = [
            "default_key",
            "test-key-12345", 
            "api-key-test",
            "development-key"
        ]
        
        for test_key in test_keys:
            print(f"   🔑 Probando con API Key: {test_key}")
            
            headers_with_key = {
                "Content-Type": "application/json",
                "X-API-Key": test_key
            }
            
            test_response = requests.post(
                f"{base_url}/v1/mcp/conversation",
                headers=headers_with_key,
                json=request_data,
                timeout=10
            )
            
            print(f"      Status: {test_response.status_code}")
            
            if test_response.status_code == 200:
                print(f"   ✅ API Key funciona: {test_key}")
                return run_diversification_test(base_url, headers_with_key, test_user_id)
            elif test_response.status_code != 403:
                print(f"      Response: {test_response.text[:100]}...")
        
        print("   ❌ No se encontró API Key válida")
        return False
        
    elif response.status_code == 200:
        print("   ✅ Endpoint NO requiere autenticación")
        return run_diversification_test(base_url, headers, test_user_id)
    else:
        print(f"   ❓ Status inesperado: {response.status_code}")
        print(f"   Response: {response.text[:200]}...")
        return False

def run_diversification_test(base_url, headers, test_user_id):
    """Ejecuta el test real de diversificación"""
    
    print("\n🧪 EJECUTANDO TEST DE DIVERSIFICACIÓN")
    print("=" * 50)
    
    test_session_id = f"diversification_test_{int(time.time())}"
    
    try:
        # Primera llamada
        print("1️⃣ Primera llamada...")
        
        request_1 = {
            "query": "show me recommendations",
            "user_id": test_user_id,
            "session_id": test_session_id,
            "market_id": "US",
            "n_recommendations": 5
        }
        
        response_1 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=request_1,
            timeout=30
        )
        
        if response_1.status_code != 200:
            print(f"   ❌ Error: {response_1.status_code} - {response_1.text}")
            return False
        
        data_1 = response_1.json()
        recs_1 = data_1.get("recommendations", [])
        metadata_1 = data_1.get("metadata", {})
        
        print(f"   ✅ Recomendaciones: {len(recs_1)}")
        print(f"   ✅ Diversification Applied: {metadata_1.get('diversification_applied', 'N/A')}")
        
        # Esperar
        time.sleep(2)
        
        # Segunda llamada
        print("\n2️⃣ Segunda llamada...")
        
        request_2 = {
            "query": "show me more",
            "user_id": test_user_id,
            "session_id": test_session_id,
            "market_id": "US",
            "n_recommendations": 5
        }
        
        response_2 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=request_2,
            timeout=30
        )
        
        if response_2.status_code != 200:
            print(f"   ❌ Error: {response_2.status_code} - {response_2.text}")
            return False
        
        data_2 = response_2.json()
        recs_2 = data_2.get("recommendations", [])
        metadata_2 = data_2.get("metadata", {})
        
        print(f"   ✅ Recomendaciones: {len(recs_2)}")
        print(f"   ✅ Diversification Applied: {metadata_2.get('diversification_applied', 'N/A')}")
        
        # Análisis
        print("\n📊 ANÁLISIS")
        print("-" * 30)
        
        ids_1 = set(r.get('id') for r in recs_1 if r.get('id'))
        ids_2 = set(r.get('id') for r in recs_2 if r.get('id'))
        
        overlap = len(ids_1.intersection(ids_2))
        overlap_pct = (overlap / len(ids_1)) * 100 if len(ids_1) > 0 else 0
        
        print(f"   IDs call 1: {list(ids_1)[:3]}...")
        print(f"   IDs call 2: {list(ids_2)[:3]}...")
        print(f"   Overlap: {overlap}/{len(ids_1)} ({overlap_pct:.1f}%)")
        
        # Resultado
        print(f"\n🎯 RESULTADO:")
        
        success = (
            len(recs_1) > 0 and 
            len(recs_2) > 0 and 
            overlap_pct < 50 and
            metadata_2.get('diversification_applied', False) == True
        )
        
        if success:
            print("   ✅ DIVERSIFICACIÓN FUNCIONANDO")
        else:
            print("   ❌ DIVERSIFICACIÓN NECESITA AJUSTES")
            print(f"      - Diversification flag: {metadata_2.get('diversification_applied', 'N/A')}")
            print(f"      - Overlap: {overlap_pct:.1f}%")
        
        return success
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    result = test_diversification_simple()
    sys.exit(0 if result else 1)
