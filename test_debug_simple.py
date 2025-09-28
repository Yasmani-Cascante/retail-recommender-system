#!/usr/bin/env python3
"""
Test simple para capturar los logs de debugging detallados
==========================================================
"""

import requests
import time
import json

def test_turn_debugging():
    """Test de debugging simple"""
    
    base_url = "http://localhost:8000"
    session_id = f"debug_session_{int(time.time())}"
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": "2fed9999056fab6dac5654238f0cae1c"
    }
    
    print("🧪 TESTING TURN DEBUG LOGGING")
    print("=" * 50)
    
    # Primera llamada
    print("\\n1️⃣ PRIMERA LLAMADA:")
    payload1 = {
        "query": "show me some recommendations",
        "market_id": "US",
        "session_id": session_id
    }
    
    response1 = requests.post(f"{base_url}/v1/mcp/conversation", json=payload1, headers=headers)
    print(f"Status: {response1.status_code}")
    
    if response1.status_code == 200:
        data1 = response1.json()
        print(f"Recommendations: {len(data1.get('recommendations', []))}")
    
    # Pausa
    time.sleep(2)
    
    # Segunda llamada - debería mostrar debugging detallado
    print("\\n2️⃣ SEGUNDA LLAMADA (should show detailed turn debugging):")
    payload2 = {
        "query": "show me more",
        "market_id": "US", 
        "session_id": session_id
    }
    
    response2 = requests.post(f"{base_url}/v1/mcp/conversation", json=payload2, headers=headers)
    print(f"Status: {response2.status_code}")
    
    if response2.status_code == 200:
        data2 = response2.json()
        print(f"Recommendations: {len(data2.get('recommendations', []))}")
        
        metadata = data2.get('metadata', {})
        print(f"Diversification applied: {metadata.get('diversification_applied', 'N/A')}")
    
    print("\\n🔍 CHECK SERVER CONSOLE for detailed debug logs starting with '🔍 DEBUG:'")

if __name__ == "__main__":
    test_turn_debugging()
