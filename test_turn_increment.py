#!/usr/bin/env python3
"""
TURN INCREMENT TEST: Specific test for turn number increment
"""

import requests
import time
import json

def test_turn_increment_specific():
    """Test específico para increment de turn numbers"""
    
    print("🔢 TURN INCREMENT SPECIFIC TEST")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    api_key = "2fed9999056fab6dac5654238f0cae1c"
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    # Session ID único
    session_id = f"turn_test_{int(time.time())}"
    
    print(f"Session ID: {session_id}")
    
    # Conversación 1
    print("\n📤 Conversación 1:")
    payload1 = {
        "query": "Hello, I need help with shoes",
        "user_id": "turn_test_user",
        "session_id": session_id,
        "market_id": "US"
    }
    
    response1 = requests.post(f"{base_url}/v1/mcp/conversation", headers=headers, json=payload1, timeout=20)
    
    if response1.status_code == 200:
        data1 = response1.json()
        turn1 = data1.get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn number: {turn1}")
    else:
        print(f"   Error: {response1.status_code}")
        return False
    
    time.sleep(2)
    
    # Conversación 2
    print("\n📤 Conversación 2:")
    payload2 = {
        "query": "What about running shoes specifically?",
        "user_id": "turn_test_user",
        "session_id": session_id,  # SAME SESSION
        "market_id": "US"
    }
    
    response2 = requests.post(f"{base_url}/v1/mcp/conversation", headers=headers, json=payload2, timeout=20)
    
    if response2.status_code == 200:
        data2 = response2.json()
        turn2 = data2.get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn number: {turn2}")
    else:
        print(f"   Error: {response2.status_code}")
        return False
    
    time.sleep(2)
    
    # Conversación 3
    print("\n📤 Conversación 3:")
    payload3 = {
        "query": "Show me blue running shoes",
        "user_id": "turn_test_user", 
        "session_id": session_id,  # SAME SESSION
        "market_id": "US"
    }
    
    response3 = requests.post(f"{base_url}/v1/mcp/conversation", headers=headers, json=payload3, timeout=20)
    
    if response3.status_code == 200:
        data3 = response3.json()
        turn3 = data3.get("session_metadata", {}).get("turn_number", 0)
        print(f"   Turn number: {turn3}")
    else:
        print(f"   Error: {response3.status_code}")
        return False
    
    # Análisis
    print(f"\n🔍 TURN PROGRESSION ANALYSIS:")
    print(f"   Conversation 1: {turn1}")
    print(f"   Conversation 2: {turn2}")
    print(f"   Conversation 3: {turn3}")
    
    success = turn1 == 1 and turn2 == 2 and turn3 == 3
    
    if success:
        print("\n🎉 ✅ TURN INCREMENT WORKING PERFECTLY!")
        print("   Turn numbers increment correctly: 1 → 2 → 3")
        return True
    else:
        print("\n❌ TURN INCREMENT STILL NOT WORKING")
        expected = [1, 2, 3]
        actual = [turn1, turn2, turn3]
        for i, (exp, act) in enumerate(zip(expected, actual)):
            status = "✅" if exp == act else "❌"
            print(f"   Conv {i+1}: Expected {exp}, Got {act} {status}")
        return False

if __name__ == "__main__":
    success = test_turn_increment_specific()
    exit(0 if success else 1)
