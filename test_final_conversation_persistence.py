#!/usr/bin/env python3
"""
VERIFICATION FINAL: Test conversation state persistence con servidor corriendo
============================================================================

El startup event está funcionando correctamente según los logs.
Ahora vamos a verificar que la conversation state persistence funciona.
"""

import requests
import time
import json

def test_conversation_persistence_final():
    """
    Test final de conversation state persistence con servidor corriendo
    """
    
    print("🎯 FINAL CONVERSATION STATE PERSISTENCE TEST")
    print("=" * 60)
    
    base_url = "http://localhost:8000"
    api_key = "2fed9999056fab6dac5654238f0cae1c"
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    # Test session ID único
    test_session_id = f"final_test_{int(time.time())}"
    
    print(f"📋 Test Configuration:")
    print(f"   Base URL: {base_url}")
    print(f"   Session ID: {test_session_id}")
    
    # Primera conversación
    print(f"\n🔄 PRIMERA CONVERSACIÓN")
    print("-" * 30)
    
    payload1 = {
        "query": "I want to buy running shoes",
        "user_id": "test_user_final",
        "session_id": test_session_id,
        "market_id": "US"
    }
    
    try:
        print("📤 Enviando primera conversación...")
        response1 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=payload1,
            timeout=30
        )
        
        if response1.status_code == 200:
            data1 = response1.json()
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
            
        else:
            print(f"❌ Primera conversación falló: {response1.status_code}")
            print(f"   Response: {response1.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ Error en primera conversación: {e}")
        return False
    
    # Esperar entre conversaciones
    print(f"\n⏳ Esperando 3 segundos...")
    time.sleep(3)
    
    # Segunda conversación - MISMO SESSION ID
    print(f"\n🔄 SEGUNDA CONVERSACIÓN (MISMA SESIÓN)")
    print("-" * 40)
    
    payload2 = {
        "query": "Actually, I prefer blue running shoes",
        "user_id": "test_user_final", 
        "session_id": test_session_id,  # MISMO session_id
        "market_id": "US"
    }
    
    try:
        print("📤 Enviando segunda conversación...")
        response2 = requests.post(
            f"{base_url}/v1/mcp/conversation",
            headers=headers,
            json=payload2,
            timeout=30
        )
        
        if response2.status_code == 200:
            data2 = response2.json()
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
            print(f"\n🔍 VALIDACIONES CRÍTICAS:")
            
            # 1. Session ID consistency
            session_consistent = session_id2 == test_session_id
            print(f"   Session ID consistent: {'✅' if session_consistent else '❌'}")
            if not session_consistent:
                print(f"      Expected: {test_session_id}")
                print(f"      Got: {session_id2}")
            
            # 2. Turn number increment - ESTE ES EL TEST CRÍTICO
            turn_incremented = turn_number2 > turn_number1
            print(f"   Turn number incremented: {'✅' if turn_incremented else '❌'}")
            print(f"      First conversation: {turn_number1}")
            print(f"      Second conversation: {turn_number2}")
            
            # 3. State persistence
            state_ok = state_persisted2
            print(f"   State persisted: {'✅' if state_ok else '❌'}")
            
            # RESULTADO FINAL
            all_passed = session_consistent and turn_incremented and state_ok
            
            print(f"\n🎯 RESULTADO FINAL:")
            if all_passed:
                print("🎉 ¡CONVERSATION STATE PERSISTENCE FUNCIONA COMPLETAMENTE!")
                print("✅ Las sesiones persisten entre requests")
                print("✅ Los turn numbers incrementan correctamente")
                print("✅ El estado se guarda y carga exitosamente")
                print("\n🚀 LISTO PARA PROCEDER A FASE 3!")
                return True
            else:
                print("❌ CONVERSATION STATE PERSISTENCE TODAVÍA TIENE ISSUES")
                if not session_consistent:
                    print("   - Session ID no es consistente")
                if not turn_incremented:
                    print("   - Turn numbers no incrementan")
                if not state_ok:
                    print("   - Estado no persiste")
                return False
                
        else:
            print(f"❌ Segunda conversación falló: {response2.status_code}")
            print(f"   Response: {response2.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ Error en segunda conversación: {e}")
        return False

def test_server_health():
    """Verificar que el servidor está corriendo"""
    
    print("🔍 VERIFICANDO ESTADO DEL SERVIDOR")
    print("-" * 40)
    
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Servidor funcionando: {health_data.get('status', 'unknown')}")
            return True
        else:
            print(f"❌ Servidor no responde correctamente: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ No se puede conectar al servidor: {e}")
        print("💡 Asegúrate de que el servidor esté corriendo:")
        print("   python src/api/main_unified_redis.py")
        return False

def main():
    """Función principal"""
    
    print("🚀 VERIFICATION FINAL - CONVERSATION STATE PERSISTENCE")
    print("🎯 Test definitivo con servidor corriendo")
    print("=" * 80)
    
    # Verificar servidor
    server_ok = test_server_health()
    
    if not server_ok:
        print("\n❌ TEST ABORTADO - Servidor no disponible")
        return False
    
    # Test conversation persistence
    persistence_ok = test_conversation_persistence_final()
    
    if persistence_ok:
        print(f"\n🎉 ¡ÉXITO COMPLETO!")
        print("🎯 Conversation State Persistence está funcionando perfectamente")
        print("🚀 El sistema está listo para Fase 3")
        
        print(f"\n📋 PRÓXIMOS PASOS RECOMENDADOS:")
        print("   1. Ejecutar validación completa de Fase 2:")
        print("      python tests/phase2_consolidation/validate_phase2_complete.py")
        print("   2. Verificar que success rate > 85%")
        print("   3. Proceder con Fase 3 (Microservicios)")
        
    else:
        print(f"\n❌ TODAVÍA HAY ISSUES")
        print("🔧 Necesita debugging adicional en el flujo de conversación")
    
    return persistence_ok

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
