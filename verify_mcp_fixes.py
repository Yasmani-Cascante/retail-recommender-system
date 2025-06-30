#!/usr/bin/env python
"""
Script para verificar que las correcciones de MCP están funcionando.
"""

import requests
import json
import time

def test_health_endpoint():
    """Prueba el endpoint de health para verificar el estado de MCP"""
    print("🔍 Probando endpoint /health...")
    
    try:
        response = requests.get("http://localhost:8000/health", timeout=10)
        
        if response.status_code == 200:
            health_data = response.json()
            print("✅ Health endpoint responde correctamente")
            
            # Verificar componente MCP
            mcp_status = health_data.get("components", {}).get("mcp", {})
            print(f"📊 Estado MCP: {mcp_status.get('status', 'unknown')}")
            
            if mcp_status.get("status") == "error":
                print(f"❌ Error en MCP: {mcp_status.get('error', 'No details')}")
                print(f"🔧 Tipo de recomendador: {mcp_status.get('recommender_type', 'unknown')}")
                return False
            else:
                print(f"✅ MCP funcionando - Tipo: {mcp_status.get('recommender_type', 'unknown')}")
                return True
        else:
            print(f"❌ Health endpoint error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error conectando al servidor: {e}")
        return False

def test_mcp_conversation_endpoint():
    """Prueba el endpoint de conversación MCP"""
    print("\n🔍 Probando endpoint /v1/mcp/conversation...")
    
    try:
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": "2fed9999056fab6dac5654238f0cae1c"  # API key del .env
        }
        
        payload = {
            "query": "I need an elegant dress for dinner under $200",
            "user_id": "test_user_123",
            "market_id": "US",
            "n_recommendations": 5
        }
        
        response = requests.post(
            "http://localhost:8000/v1/mcp/conversation",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            conv_data = response.json()
            print("✅ Conversación MCP responde correctamente")
            print(f"📝 Respuesta: {conv_data.get('answer', '')[:100]}...")
            print(f"🎯 Recomendaciones: {len(conv_data.get('recommendations', []))}")
            return True
        elif response.status_code == 503:
            print("⚠️ Servicio no disponible (probablemente cargando)")
            return False
        else:
            print(f"❌ Conversation endpoint error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error en conversación MCP: {e}")
        return False

def main():
    """Ejecuta las pruebas de verificación"""
    print("🚀 VERIFICACIÓN DE CORRECCIONES MCP")
    print("=" * 50)
    
    # Esperar un poco para que el servidor esté listo
    print("⏳ Esperando que el servidor esté listo...")
    time.sleep(2)
    
    # Test 1: Health endpoint
    health_ok = test_health_endpoint()
    
    # Test 2: MCP conversation endpoint
    conversation_ok = test_mcp_conversation_endpoint()
    
    print("\n" + "=" * 50)
    print("📊 RESUMEN:")
    print(f"Health endpoint: {'✅ OK' if health_ok else '❌ FAIL'}")
    print(f"MCP conversation: {'✅ OK' if conversation_ok else '❌ FAIL'}")
    
    if health_ok and conversation_ok:
        print("\n🎉 ¡Todas las correcciones funcionan correctamente!")
    elif health_ok:
        print("\n✅ Health corregido, pero conversation endpoint necesita ajustes")
    else:
        print("\n⚠️ Algunas correcciones necesitan más trabajo")
    
    return health_ok and conversation_ok

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
