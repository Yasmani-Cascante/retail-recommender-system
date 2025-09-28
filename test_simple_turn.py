#!/usr/bin/env python3
"""
SIMPLE TURN TEST: Quick verification
"""

import requests
import time

def test_simple_turn_increment():
    """Test simple de 2 conversaciones"""
    
    print("🔢 SIMPLE TURN INCREMENT TEST")
    print("=" * 40)
    
    base_url = "http://localhost:8000"
    headers = {
        "X-API-Key": "2fed9999056fab6dac5654238f0cae1c",
        "Content-Type": "application/json"
    }
    
    session_id = f"simple_test_{int(time.time())}"
    
    # Conversación 1
    print("📤 Conversation 1...")
    response1 = requests.post(f"{base_url}/v1/mcp/conversation", 
        headers=headers, 
        json={
            "query": "I need shoes",
            "user_id": "simple_user",
            "session_id": session_id,
            "market_id": "US"
        }, 
        timeout=20
    )
    
    if response1.status_code == 200:
        turn1 = response1.json().get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn 1: {turn1}")
    else:
        print(f"   Error: {response1.status_code}")
        return False
    
    time.sleep(2)
    
    # Conversación 2
    print("📤 Conversation 2...")
    response2 = requests.post(f"{base_url}/v1/mcp/conversation", 
        headers=headers, 
        json={
            "query": "What about running shoes?",
            "user_id": "simple_user", 
            "session_id": session_id,
            "market_id": "US"
        }, 
        timeout=20
    )
    
    if response2.status_code == 200:
        turn2 = response2.json().get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn 2: {turn2}")
    else:
        print(f"   Error: {response2.status_code}")
        return False
    
    # Resultado
    print(f"\n🔍 RESULT:")
    print(f"   Turn 1: {turn1}")
    print(f"   Turn 2: {turn2}")
    
    if turn2 > turn1:
        print(f"\n🎉 ✅ SUCCESS! Turn incremented from {turn1} to {turn2}")
        return True
    else:
        print(f"\n❌ FAILED: Turn did not increment")
        return False

if __name__ == "__main__":
    success = test_simple_turn_increment()
    print(f"\nResult: {'PASSED' if success else 'FAILED'}")
