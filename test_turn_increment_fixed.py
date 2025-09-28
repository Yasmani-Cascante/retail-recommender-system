#!/usr/bin/env python3
"""
TEST MEJORADO: Verificar turn increment después de fix
"""

import requests
import time
import json

def test_turn_increment_fixed():
    """Test que verifica que el turn_number incrementa correctamente"""
    
    print("🧪 TEST TURN INCREMENT - POST FIX")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    headers = {
        "X-API-Key": "2fed9999056fab6dac5654238f0cae1c",
        "Content-Type": "application/json"
    }
    
    session_id = f"test_fix_{int(time.time())}"
    results = []
    
    # Hacer 3 conversaciones para verificar incremento
    queries = [
        "I need running shoes",
        "Show me Nike options",
        "What about Adidas?"
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n📍 Conversación {i}:")
        response = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json={
                "query": query,
                "user_id": "test_user",
                "session_id": session_id,
                "market_id": "US"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            session_meta = data.get("session_metadata", {})
            turn_number = session_meta.get("turn_number", "N/A")
            
            print(f"   Query: {query}")
            print(f"   Turn Number: {turn_number}")
            print(f"   Expected: {i}")
            print(f"   ✅ PASS" if turn_number == i else f"   ❌ FAIL")
            
            results.append({
                "turn": i,
                "expected": i,
                "actual": turn_number,
                "passed": turn_number == i
            })
        else:
            print(f"   ❌ Error: {response.status_code}")
            results.append({
                "turn": i,
                "expected": i,
                "actual": "ERROR",
                "passed": False
            })
        
        time.sleep(2)  # Esperar entre requests
    
    # Resumen
    print(f"\n📊 RESUMEN DE RESULTADOS:")
    print("=" * 40)
    
    all_passed = all(r["passed"] for r in results)
    
    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(f"{status} Turn {r['turn']}: Expected {r['expected']}, Got {r['actual']}")
    
    if all_passed:
        print(f"\n🎉 SUCCESS! All turns incremented correctly!")
        return True
    else:
        print(f"\n❌ FAILED: Turn numbers not incrementing properly")
        return False

if __name__ == "__main__":
    success = test_turn_increment_fixed()
    print(f"\nTest Result: {'PASSED' if success else 'FAILED'}")
    exit(0 if success else 1)
