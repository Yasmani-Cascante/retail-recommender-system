#!/usr/bin/env python3
"""
DEBUG TEST: Verificar turn increment paso a paso
"""

import requests
import time
import json

def debug_turn_increment():
    """Test de debugging detallado"""
    
    print("🔧 DEBUG TURN INCREMENT TEST")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    headers = {
        "X-API-Key": "2fed9999056fab6dac5654238f0cae1c",
        "Content-Type": "application/json"
    }
    
    session_id = f"debug_test_{int(time.time())}"
    print(f"📋 Using session_id: {session_id}")
    
    # Primera conversación
    print("\n🔍 PRIMERA CONVERSACIÓN:")
    response1 = requests.post(f"{base_url}/v1/mcp/conversation", 
        headers=headers, 
        json={
            "query": "I need shoes for running",
            "user_id": "debug_user",
            "session_id": session_id,
            "market_id": "US"
        }, 
        timeout=30
    )
    
    if response1.status_code == 200:
        data1 = response1.json()
        session_meta1 = data1.get("session_metadata", {})
        
        print(f"   Status: ✅ {response1.status_code}")
        print(f"   Session ID: {session_meta1.get('session_id', 'N/A')}")
        print(f"   Turn Number: {session_meta1.get('turn_number', 'N/A')}")
        print(f"   State Persisted: {session_meta1.get('state_persisted', 'N/A')}")
        print(f"   Response length: {len(data1.get('answer', ''))}")
        
        # Debug adicional
        if 'metadata' in data1:
            print(f"   Metadata keys: {list(data1['metadata'].keys())}")
            
    else:
        print(f"   Status: ❌ {response1.status_code}")
        print(f"   Error: {response1.text[:200]}")
        return False
    
    time.sleep(3)  # Esperar un poco más
    
    # Segunda conversación
    print("\n🔍 SEGUNDA CONVERSACIÓN:")
    response2 = requests.post(f"{base_url}/v1/mcp/conversation", 
        headers=headers, 
        json={
            "query": "What about Nike running shoes?",
            "user_id": "debug_user", 
            "session_id": session_id,  # MISMO session_id
            "market_id": "US"
        }, 
        timeout=30
    )
    
    if response2.status_code == 200:
        data2 = response2.json()
        session_meta2 = data2.get("session_metadata", {})
        
        print(f"   Status: ✅ {response2.status_code}")
        print(f"   Session ID: {session_meta2.get('session_id', 'N/A')}")
        print(f"   Turn Number: {session_meta2.get('turn_number', 'N/A')}")
        print(f"   State Persisted: {session_meta2.get('state_persisted', 'N/A')}")
        print(f"   Response length: {len(data2.get('answer', ''))}")
        
    else:
        print(f"   Status: ❌ {response2.status_code}")
        print(f"   Error: {response2.text[:200]}")
        return False
    
    # Análisis de resultados
    print(f"\n📊 ANÁLISIS DE RESULTADOS:")
    print("=" * 30)
    
    turn1 = session_meta1.get('turn_number', 0)
    turn2 = session_meta2.get('turn_number', 0)
    
    print(f"Turn 1: {turn1}")
    print(f"Turn 2: {turn2}")
    
    session_id1 = session_meta1.get('session_id', 'N/A')
    session_id2 = session_meta2.get('session_id', 'N/A')
    
    print(f"Session ID 1: {session_id1}")
    print(f"Session ID 2: {session_id2}")
    print(f"Session IDs match: {session_id1 == session_id2}")
    
    if turn2 > turn1:
        print(f"\n🎉 ✅ SUCCESS! Turn incremented from {turn1} to {turn2}")
        return True
    elif turn1 == turn2:
        print(f"\n❌ FAILED: Turn did not increment (both are {turn1})")
        return False
    else:
        print(f"\n⚠️ WEIRD: Turn decreased from {turn1} to {turn2}")
        return False

if __name__ == "__main__":
    success = debug_turn_increment()
    print(f"\nFinal Result: {'PASSED' if success else 'FAILED'}")