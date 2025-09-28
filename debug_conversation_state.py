#!/usr/bin/env python3
"""
Test con Logging Detallado - Conversation State Persistence
==========================================================

Este script ejecuta un test simple pero con logging comprehensivo
para identificar exactamente dónde falla la persistencia.

Con el logging añadido al sistema, ahora podremos ver:
1. Si Redis se conecta correctamente
2. Si save_conversation_state se ejecuta y tiene éxito
3. Si load_conversation_state encuentra los datos
4. Dónde exactamente falla el flujo

Uso:
    python test_with_detailed_logging.py
"""

import asyncio
import aiohttp
import json
import time
import uuid

async def test_with_detailed_logging():
    """Test simple con logging detallado para debugging"""
    
    print("🔍 TESTING WITH DETAILED LOGGING")
    print("="*50)
    
    # Configuración
    BASE_URL = "http://localhost:8000"
    API_KEY = "2fed9999056fab6dac5654238f0cae1c"
    
    # Generate unique identifiers
    session_id = f"detailed_test_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    user_id = f"test_user_{uuid.uuid4().hex[:4]}"
    
    print(f"📋 Session ID: {session_id}")
    print(f"👤 User ID: {user_id}")
    print(f"🌐 Base URL: {BASE_URL}")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "DetailedLoggingTest/1.0"
    }
    
    async with aiohttp.ClientSession() as session:
        
        print(f"\n" + "="*50)
        print("🔄 PRIMERA CONVERSACIÓN")
        print("="*50)
        
        payload1 = {
            "query": "I want to buy shoes for running",
            "user_id": user_id,
            "session_id": session_id,
            "market_id": "US"
        }
        
        print(f"📤 Request payload:")
        print(json.dumps(payload1, indent=2))
        
        start_time = time.time()
        
        try:
            async with session.post(f"{BASE_URL}/v1/mcp/conversation", json=payload1, headers=headers) as response:
                
                response_time = (time.time() - start_time) * 1000
                print(f"\n📥 Response received in {response_time:.0f}ms")
                print(f"   Status: {response.status}")
                
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ API Error: {error_text}")
                    return False
                
                data1 = await response.json()
                
                # Analizar respuesta
                session_meta1 = data1.get("session_metadata", {})
                turn1 = session_meta1.get("turn_number", 0)
                session_id1 = session_meta1.get("session_id", "")
                state_persisted1 = session_meta1.get("state_persisted", False)
                
                print(f"\n📊 Response Analysis:")
                print(f"   Turn Number: {turn1}")
                print(f"   Session ID: {session_id1}")
                print(f"   State Persisted: {state_persisted1}")
                print(f"   Session ID Match: {session_id1 == session_id}")
                
                if not state_persisted1:
                    print(f"⚠️  WARNING: State not persisted in first conversation")
                
        except Exception as e:
            print(f"❌ First conversation failed: {e}")
            return False
        
        # Pausa entre conversaciones para permitir que se complete el save
        print(f"\n⏳ Waiting 3 seconds between conversations...")
        await asyncio.sleep(3)
        
        print(f"\n" + "="*50)
        print("🔄 SEGUNDA CONVERSACIÓN (MISMO SESSION_ID)")
        print("="*50)
        
        payload2 = {
            "query": "Actually, I prefer running sneakers in blue color",
            "user_id": user_id,
            "session_id": session_id,  # ✅ MISMO session_id
            "market_id": "US"
        }
        
        print(f"📤 Request payload:")
        print(json.dumps(payload2, indent=2))
        
        start_time = time.time()
        
        try:
            async with session.post(f"{BASE_URL}/v1/mcp/conversation", json=payload2, headers=headers) as response:
                
                response_time = (time.time() - start_time) * 1000
                print(f"\n📥 Response received in {response_time:.0f}ms")
                print(f"   Status: {response.status}")
                
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ API Error: {error_text}")
                    return False
                
                data2 = await response.json()
                
                # Analizar respuesta
                session_meta2 = data2.get("session_metadata", {})
                turn2 = session_meta2.get("turn_number", 0)
                session_id2 = session_meta2.get("session_id", "")
                state_persisted2 = session_meta2.get("state_persisted", False)
                
                print(f"\n📊 Response Analysis:")
                print(f"   Turn Number: {turn2}")
                print(f"   Session ID: {session_id2}")
                print(f"   State Persisted: {state_persisted2}")
                print(f"   Session ID Match: {session_id2 == session_id}")
                
        except Exception as e:
            print(f"❌ Second conversation failed: {e}")
            return False
        
        # === ANÁLISIS FINAL ===
        print(f"\n" + "="*50)
        print("🎯 FINAL ANALYSIS")
        print("="*50)
        
        print(f"Session consistency:")
        print(f"  Sent: {session_id}")
        print(f"  Resp1: {session_id1}")
        print(f"  Resp2: {session_id2}")
        print(f"  Match: {session_id == session_id1 == session_id2}")
        
        print(f"\nTurn progression:")
        print(f"  First conversation: {turn1}")
        print(f"  Second conversation: {turn2}")
        print(f"  Incremented: {turn2 > turn1}")
        
        print(f"\nState persistence:")
        print(f"  First: {state_persisted1}")
        print(f"  Second: {state_persisted2}")
        
        if turn2 > turn1:
            print(f"\n🎉 SUCCESS: Turn numbers are incrementing!")
            print(f"   Fix #1 is working correctly")
            return True
        else:
            print(f"\n🚨 FAILED: Turn numbers not incrementing")
            print(f"   This indicates the root cause is still present")
            print(f"\n💡 Next steps:")
            print(f"   1. Check server logs for detailed error messages")
            print(f"   2. Look for Redis connection/save/load errors")
            print(f"   3. Verify session_id consistency")
            return False

async def main():
    """Función principal"""
    print("🚀 STARTING DETAILED LOGGING TEST")
    print("This test will help us identify the root cause of conversation state persistence issues")
    print("\nIMPORTANT: Check the server logs for detailed debugging information")
    print("Look for messages like:")
    print("  - '🔧 ATTEMPTING to save conversation state'")
    print("  - '✅ STATE SAVED SUCCESSFULLY'")
    print("  - '🔍 ATTEMPTING to load existing session'")
    print("  - '✅ LOADED existing MCP context'")
    print("  - Any Redis connection errors")
    
    try:
        success = await test_with_detailed_logging()
        
        print(f"\n" + "="*60)
        
        if success:
            print(f"🎉 TEST PASSED: Conversation state persistence is working!")
        else:
            print(f"🚨 TEST FAILED: Check server logs for root cause")
            print(f"")
            print(f"Key things to look for in server logs:")
            print(f"  1. Redis connection failures")
            print(f"  2. JSON serialization errors")
            print(f"  3. Session save/load failures")
            print(f"  4. Session ID mismatches")
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 2

if __name__ == "__main__":
    import sys
    result = asyncio.run(main())
    sys.exit(result)