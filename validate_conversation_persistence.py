#!/usr/bin/env python3
"""
CONVERSATION STATE PERSISTENCE - VALIDATION SCRIPT
=================================================

Script específico para validar que el fix de conversación state persistence funciona correctamente
"""

import sys
import time
import json
import asyncio
import requests
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_conversation_state_persistence():
    """
    Test específico para conversation state persistence
    
    Valida que:
    1. El state_manager se inicializa correctamente  
    2. Las sesiones persisten entre requests
    3. Los turn numbers incrementan correctamente
    4. El estado se guarda y carga exitosamente
    """
    
    print("🔍 TESTING CONVERSATION STATE PERSISTENCE")
    print("=" * 60)
    
    # Configuración del test
    base_url = "http://localhost:8000"
    api_key = "2fed9999056fab6dac5654238f0cae1c"
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    # Generar session_id único para el test
    test_session_id = f"persistence_test_{int(time.time())}"
    test_user_id = "test_user_persistence"
    
    print(f"📋 Test Parameters:")
    print(f"   Session ID: {test_session_id}")
    print(f"   User ID: {test_user_id}")
    print(f"   Base URL: {base_url}")
    
    # Test 1: Primera conversación
    print(f"\n🔄 TEST 1: Primera conversación")
    print("-" * 30)
    
    payload1 = {
        "query": "I want to buy running shoes",
        "user_id": test_user_id,
        "session_id": test_session_id,
        "market_id": "US"
    }
    
    try:
        response1 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=payload1,
            timeout=30
        )
        
        if response1.status_code == 200:
            data1 = response1.json()
            
            # Extraer información de la primera conversación
            session_metadata1 = data1.get("session_metadata", {})
            turn_number1 = session_metadata1.get("turn_number", 0)
            session_id1 = session_metadata1.get("session_id", data1.get("session_id"))
            state_persisted1 = session_metadata1.get("state_persisted", False)
            
            print(f"✅ Primera conversación exitosa:")
            print(f"   Status: {response1.status_code}")
            print(f"   Session ID: {session_id1}")
            print(f"   Turn Number: {turn_number1}")
            print(f"   State Persisted: {state_persisted1}")
            print(f"   Response length: {len(data1.get('answer', ''))}")
            
            # Validaciones primera conversación
            if turn_number1 != 1:
                print(f"⚠️ WARNING: Expected turn_number=1, got {turn_number1}")
            
            if session_id1 != test_session_id:
                print(f"⚠️ WARNING: Session ID mismatch. Expected {test_session_id}, got {session_id1}")
                test_session_id = session_id1  # Usar el ID devuelto para consistencia
            
            if not state_persisted1:
                print(f"⚠️ WARNING: State not persisted in first conversation")
            
        else:
            print(f"❌ Primera conversación falló: Status {response1.status_code}")
            print(f"   Response: {response1.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error en primera conversación: {e}")
        return False
    
    # Esperar entre conversaciones
    print(f"\n⏳ Esperando 2 segundos entre conversaciones...")
    time.sleep(2)
    
    # Test 2: Segunda conversación (misma sesión)
    print(f"\n🔄 TEST 2: Segunda conversación (misma sesión)")
    print("-" * 40)
    
    payload2 = {
        "query": "Actually, I prefer blue running shoes with good cushioning",
        "user_id": test_user_id,
        "session_id": test_session_id,  # MISMO session_id
        "market_id": "US"
    }
    
    try:
        response2 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=payload2,
            timeout=30
        )
        
        if response2.status_code == 200:
            data2 = response2.json()
            
            # Extraer información de la segunda conversación
            session_metadata2 = data2.get("session_metadata", {})
            turn_number2 = session_metadata2.get("turn_number", 0)
            session_id2 = session_metadata2.get("session_id", data2.get("session_id"))
            state_persisted2 = session_metadata2.get("state_persisted", False)
            
            print(f"✅ Segunda conversación exitosa:")
            print(f"   Status: {response2.status_code}")
            print(f"   Session ID: {session_id2}")
            print(f"   Turn Number: {turn_number2}")
            print(f"   State Persisted: {state_persisted2}")
            print(f"   Response length: {len(data2.get('answer', ''))}")
            
            # VALIDACIONES CRÍTICAS
            success = True
            
            # Validación 1: Session ID consistency
            if session_id2 != test_session_id:
                print(f"❌ FAIL: Session ID inconsistency. Expected {test_session_id}, got {session_id2}")
                success = False
            else:
                print(f"✅ PASS: Session ID consistent")
            
            # Validación 2: Turn number increment
            if turn_number2 <= turn_number1:
                print(f"❌ FAIL: Turn number not incremented. First: {turn_number1}, Second: {turn_number2}")
                success = False
            else:
                print(f"✅ PASS: Turn number incremented ({turn_number1} → {turn_number2})")
            
            # Validación 3: State persistence
            if not state_persisted2:
                print(f"❌ FAIL: State not persisted in second conversation")
                success = False
            else:
                print(f"✅ PASS: State persisted in second conversation")
            
            return success
            
        else:
            print(f"❌ Segunda conversación falló: Status {response2.status_code}")
            print(f"   Response: {response2.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error en segunda conversación: {e}")
        return False

def test_server_health():
    """Test básico de salud del servidor"""
    
    print(f"\n🔍 TESTING SERVER HEALTH")
    print("-" * 30)
    
    try:
        response = requests.get("http://localhost:8000/health", timeout=10)
        
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Server health: {health_data.get('status', 'unknown')}")
            
            # Verificar componentes específicos
            components = health_data.get('components', {})
            for component, status in components.items():
                comp_status = status.get('status', 'unknown') if isinstance(status, dict) else status
                print(f"   {component}: {comp_status}")
            
            return True
        else:
            print(f"❌ Server health check failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Server health check error: {e}")
        return False

def main():
    """Función principal de validación"""
    
    print("🚀 CONVERSATION STATE PERSISTENCE VALIDATION")
    print("=" * 80)
    
    # Test 1: Server health
    print("\n📋 STEP 1: Server Health Check")
    health_ok = test_server_health()
    
    if not health_ok:
        print("❌ Server health check failed - cannot proceed with conversation tests")
        print("💡 Make sure the server is running: python src/api/main_unified_redis.py")
        return False
    
    # Test 2: Conversation state persistence
    print("\n📋 STEP 2: Conversation State Persistence")
    persistence_ok = test_conversation_state_persistence()
    
    # Summary
    print(f"\n📊 VALIDATION SUMMARY")
    print("=" * 40)
    
    tests = [
        ("Server Health", health_ok),
        ("Conversation State Persistence", persistence_ok)
    ]
    
    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    
    for test_name, result in tests:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\n🎯 OVERALL RESULT: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Conversation state persistence is working correctly")
        print("✅ Turn numbers increment properly")
        print("✅ Session state persists between requests")
        return True
    else:
        print("\n❌ SOME TESTS FAILED")
        print("🔧 Issues identified with conversation state persistence")
        print("💡 Review the state manager initialization and Redis connectivity")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
