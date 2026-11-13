# test_mcp_bridge.py
import requests
import os
from dotenv import load_dotenv
load_dotenv()  # API_KEY sale del .env local o del entorno de la sesion, nunca del codigo
import json
import time

# Configuración
BRIDGE_URL = "http://localhost:3001"
API_URL = "http://localhost:8000"  # Ajusta si es necesario
API_KEY = os.environ.get("API_KEY", "")  # del .env o del entorno de la sesion

# Función para formatear la salida JSON
def pretty_json(data):
    return json.dumps(data, indent=2, ensure_ascii=False)

# 1. Verificar el estado de salud del bridge
print("1️⃣ Verificando estado de salud del bridge...")
try:
    response = requests.get(f"{BRIDGE_URL}/health")
    print(f"✅ Estado: {response.status_code}")
    print(pretty_json(response.json()))
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "-"*50 + "\n")

# 2. Probar consulta conversacional directa al bridge
print("2️⃣ Probando consulta conversacional directa al bridge...")
try:
    payload = {
        "query": "Busco una camisa azul",
        "sessionId": f"test-session-{int(time.time())}"
    }
    response = requests.post(f"{BRIDGE_URL}/api/mcp/conversation", json=payload)
    print(f"✅ Estado: {response.status_code}")
    print(pretty_json(response.json()))
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "-"*50 + "\n")

# 3. Probar integración con la API principal
print("3️⃣ Probando integración con la API principal...")
try:
    payload = {
        "query": "Busco una camisa azul",
        "user_id": "test_user",
        "market_id": "ES",
        "n_recommendations": 3
    }
    headers = {"X-API-Key": API_KEY}
    response = requests.post(f"{API_URL}/v1/mcp/conversation", json=payload, headers=headers)
    print(f"✅ Estado: {response.status_code}")
    print(pretty_json(response.json()))
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "-"*50 + "\n")

# 4. Probar el endpoint de mercados soportados
print("4️⃣ Verificando mercados soportados...")
try:
    headers = {"X-API-Key": API_KEY}
    response = requests.get(f"{API_URL}/v1/mcp/markets", headers=headers)
    print(f"✅ Estado: {response.status_code}")
    print(pretty_json(response.json()))
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "-"*50 + "\n")

print("🎯 Pruebas completadas")
