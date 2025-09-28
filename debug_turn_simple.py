#!/usr/bin/env python3
"""
DEBUG SIMPLE: Turn Count Zero Issue
===================================

Script simple para debuggear por qué turn_count devuelve 0
"""

import requests
import time
import json

def debug_session_response():
    """Debug simple de la respuesta del session"""
    
    print("🔍 SIMPLE SESSION RESPONSE DEBUG")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    headers = {
        "X-API-Key": "2fed9999056fab6dac5654238f0cae1c",
        "Content-Type": "application/json"
    }
    
    session_id = f"debug_simple_{int(time.time())}"
    print(f"Session ID: {session_id}")
    
    # Primera conversación con debug completo
    print("\n📤 CONVERSATION 1:")
    
    payload = {
        "query": "Debug test shoes",
        "user_id": "debug_user",
        "session_id": session_id,
        "market_id": "US"
    }
    
    try:
        response = requests.post(f"{base_url}/v1/mcp/conversation", 
                               headers=headers, 
                               json=payload, 
                               timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            print("✅ Response received")
            
            # Examinar session_metadata completo
            session_metadata = data.get("session_metadata", {})
            
            print(f"\n🔍 COMPLETE SESSION METADATA:")
            for key, value in session_metadata.items():
                print(f"   {key}: {value}")
            
            # Campos específicos de interés
            turn_number = session_metadata.get("turn_number", "NOT_FOUND")
            turn_count = session_metadata.get("turn_count", "NOT_FOUND") 
            total_turns = session_metadata.get("total_turns", "NOT_FOUND")
            
            print(f"\n🔍 TURN FIELDS:")
            print(f"   turn_number: {turn_number}")
            print(f"   turn_count: {turn_count}")
            print(f"   total_turns: {total_turns}")
            
            return session_id
            
        else:
            print(f"❌ Request failed: {response.status_code}")
            print(f"Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    print("🚀 DEBUGGING TURN COUNT ZERO ISSUE")
    print("=" * 50)
    
    session_id = debug_session_response()
    
    if session_id:
        print(f"\n✅ Debug completed for session: {session_id}")
        print(f"\n💡 Look at the session_metadata above.")
        print(f"If turn_number is 0, we need to fix the calculation logic.")
    else:
        print(f"\n❌ Debug failed - check server status")
