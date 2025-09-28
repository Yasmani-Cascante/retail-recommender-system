# tests/performance/claude_load_test.py
"""
Load Testing Framework para Claude Integration
============================================

Tests de carga específicos para validar la integración Claude centralizada.
Target: >500 RPS, <2s P95 response time, <0.1% error rate

Author: Arquitecto Senior
Version: 1.0.0
"""

import json
import time
import random
from locust import HttpUser, task, between
from locust.exception import StopUser
import logging

# Configurar logging para debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ClaudeConversationUser(HttpUser):
    """
    Usuario simulado para testing de conversaciones Claude
    """
    wait_time = between(1, 3)  # Pausa entre requests
    
    def on_start(self):
        """Inicialización del usuario de testing"""
        self.api_key = "2fed9999056fab6dac5654238f0cae1c"  # API key from .env
        self.user_id = f"load_test_user_{random.randint(1000, 9999)}"
        self.session_id = f"session_{int(time.time())}_{random.randint(100, 999)}"
        
        # Headers para todas las requests
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "Claude-LoadTest/1.0"
        }
        
        logger.info(f"🧪 Load test user initialized: {self.user_id}")
    
    @task(3)
    def test_mcp_conversation_basic(self):
        """
        Test básico de conversación MCP con Claude
        Weight: 3 (ejecuta más frecuentemente)
        """
        conversation_payloads = [
            {
                "message": "Recomiéndame productos para mi cocina",
                "user_id": self.user_id,
                "market_id": "US",
                "context": {
                    "intent": "product_discovery",
                    "category": "kitchen"
                }
            },
            {
                "message": "Busco ropa deportiva para correr",
                "user_id": self.user_id,
                "market_id": "ES", 
                "context": {
                    "intent": "product_search",
                    "category": "sports"
                }
            },
            {
                "message": "¿Cuáles son los productos más populares?",
                "user_id": self.user_id,
                "market_id": "MX",
                "context": {
                    "intent": "trending_inquiry"
                }
            }
        ]
        
        payload = random.choice(conversation_payloads)
        
        with self.client.post(
            "/v1/mcp/conversation",
            headers=self.headers,
            json=payload,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    
                    # Validar estructura de respuesta esperada
                    required_fields = ["response", "context", "recommendations"]
                    missing_fields = [field for field in required_fields if field not in response_data]
                    
                    if missing_fields:
                        response.failure(f"Missing fields in response: {missing_fields}")
                    elif response.elapsed.total_seconds() > 2.0:
                        response.failure(f"Response too slow: {response.elapsed.total_seconds():.2f}s")
                    else:
                        response.success()
                        
                        # Log métricas adicionales
                        if "claude_metrics" in response_data:
                            claude_metrics = response_data["claude_metrics"]
                            logger.info(f"Claude model used: {claude_metrics.get('model_tier', 'unknown')}")
                            
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"HTTP {response.status_code}: {response.text}")
    
    @task(2)
    def test_recommendations_with_claude(self):
        """
        Test de recomendaciones que activan personalización Claude
        Weight: 2
        """
        with self.client.get(
            f"/v1/recommendations/user/{self.user_id}",
            headers=self.headers,
            params={"n": 5, "include_ai_insights": "true"},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "recommendations" in data and len(data["recommendations"]) > 0:
                        response.success()
                    else:
                        response.failure("Empty recommendations")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON in recommendations")
            else:
                response.failure(f"Recommendations failed: {response.status_code}")
    
    @task(1)
    def test_health_claude_endpoint(self):
        """
        Test del endpoint de health check específico de Claude
        Weight: 1 (menos frecuente)
        """
        with self.client.get(
            "/health/claude",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    health_data = response.json()
                    if health_data.get("status") in ["healthy", "degraded"]:
                        response.success()
                    else:
                        response.failure(f"Invalid health status: {health_data.get('status')}")
                except json.JSONDecodeError:
                    response.failure("Invalid health check JSON")
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(1)
    def test_claude_configuration_endpoint(self):
        """
        Test del endpoint de configuración Claude (si existe)
        Weight: 1
        """
        with self.client.get(
            "/v1/metrics",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    metrics_data = response.json()
                    # Verificar que contiene métricas Claude
                    if "claude_metrics" in metrics_data or "claude_model_tier" in str(metrics_data):
                        response.success()
                    else:
                        response.failure("No Claude metrics found")
                except json.JSONDecodeError:
                    response.failure("Invalid metrics JSON")
            else:
                response.failure(f"Metrics endpoint failed: {response.status_code}")

class ClaudeStressUser(HttpUser):
    """
    Usuario para stress testing con carga intensiva
    """
    wait_time = between(0.1, 0.5)  # Carga más agresiva
    
    def on_start(self):
        self.api_key = "2fed9999056fab6dac5654238f0cae1c"
        self.user_id = f"stress_user_{random.randint(10000, 99999)}"
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
    @task
    def stress_test_conversation(self):
        """Test de estrés para conversaciones Claude"""
        payload = {
            "message": f"Test de estrés #{random.randint(1, 1000)}",
            "user_id": self.user_id,
            "market_id": random.choice(["US", "ES", "MX"]),
            "context": {"test_type": "stress"}
        }
        
        with self.client.post(
            "/v1/mcp/conversation",
            headers=self.headers,
            json=payload,
            catch_response=True
        ) as response:
            # Criterios más estrictos para stress test
            if response.status_code != 200:
                response.failure(f"Stress test failed: {response.status_code}")
            elif response.elapsed.total_seconds() > 1.5:
                response.failure(f"Stress test too slow: {response.elapsed.total_seconds():.2f}s")
            else:
                response.success()

# Configuración de testing por escenario
class ClaudeLoadTestScenarios:
    """
    Escenarios de testing predefinidos para diferentes casos de uso
    """
    
    @staticmethod
    def normal_load():
        """Carga normal de producción simulada"""
        return {
            "users": 50,
            "spawn_rate": 5,
            "run_time": "5m",
            "expected_rps": 200,
            "max_response_time": 2.0
        }
    
    @staticmethod
    def peak_load():
        """Carga pico simulada"""
        return {
            "users": 200,
            "spawn_rate": 10,
            "run_time": "10m", 
            "expected_rps": 500,
            "max_response_time": 2.0
        }
    
    @staticmethod
    def stress_test():
        """Test de estrés para encontrar límites"""
        return {
            "users": 500,
            "spawn_rate": 20,
            "run_time": "3m",
            "expected_rps": 1000,
            "max_response_time": 3.0
        }

if __name__ == "__main__":
    print("🧪 Claude Load Testing Framework")
    print("=" * 50)
    print("Escenarios disponibles:")
    print("1. Normal Load: locust -f claude_load_test.py --users 50 --spawn-rate 5")
    print("2. Peak Load: locust -f claude_load_test.py --users 200 --spawn-rate 10") 
    print("3. Stress Test: locust -f claude_load_test.py ClaudeStressUser --users 500 --spawn-rate 20")
    print("\nTarget Metrics:")
    print("- Throughput: >500 RPS sustained")
    print("- Response Time P95: <2s")
    print("- Error Rate: <0.1%")
    print("- Memory Usage: Stable under load")