# tests/load/locust_comprehensive.py
"""
🎯 COMPREHENSIVE LOAD TESTING SCRIPT
====================================

Script de load testing completo que simula el comportamiento real de usuarios
en un sistema de recomendaciones para retail.

Autor: Arquitecto Senior & Load Testing Expert
Versión: 2.0 - Comprehensive Coverage
Fecha: Agosto 2025

🏪 SIMULACIÓN REALISTA DE E-COMMERCE:
Este script simula diferentes tipos de usuarios en una tienda online:
- Browsing users: Navegan productos, ven recomendaciones
- Active shoppers: Buscan productos específicos, ven detalles
- Engaged users: Usan chat conversacional, requieren personalización
- System monitors: Health checks de infraestructura
"""

import random
import os
from dotenv import load_dotenv
load_dotenv()  # API_KEY sale del .env local o del entorno de la sesion, nunca del codigo
import json
import time
from locust import HttpUser, task, between, events
from typing import Dict, List

# 🎨 CONFIGURACIÓN DE SIMULACIÓN
class EcommerceConfig:
    """Configuración realista para simular tráfico de e-commerce"""
    
    # Productos de muestra para testing
    SAMPLE_PRODUCT_IDS = [
        "product_001", "product_002", "product_003", "product_004", "product_005",
        "product_006", "product_007", "product_008", "product_009", "product_010"
    ]
    
    # Queries realistas para búsqueda
    SAMPLE_QUERIES = [
        "running shoes", "wireless headphones", "coffee machine", "laptop bag",
        "yoga mat", "smartphone case", "bluetooth speaker", "winter jacket",
        "desk chair", "water bottle", "gaming mouse", "reading glasses"
    ]
    
    # Conversaciones realistas para MCP
    CONVERSATION_QUERIES = [
        "I need something for my morning workout",
        "Looking for a gift for my tech-savvy friend",
        "What's good for working from home?",
        "I want to upgrade my kitchen appliances",
        "Need something for outdoor activities",
        "Looking for professional work accessories",
        "What's trending in electronics?",
        "I need comfortable clothing for travel"
    ]
    
    # Mercados soportados
    MARKETS = ["US", "ES", "MX"]

class RetailRecommenderUser(HttpUser):
    """
    🛍️ Usuario simulado de e-commerce que realiza acciones realistas
    """
    
    # Tiempo de espera entre acciones (simula lectura/pensamiento del usuario)
    wait_time = between(1, 4)
    
    def on_start(self):
        """Inicialización del usuario simulado"""
        self.api_key = os.environ.get("API_KEY", "")
        self.headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        
        # Crear perfil de usuario único
        self.user_id = f"load_user_{random.randint(1000, 9999)}"
        self.market_id = random.choice(EcommerceConfig.MARKETS)
        self.session_id = f"session_{int(time.time())}_{random.randint(100, 999)}"
        
        # Carrito de compras simulado
        self.cart_items = []
        self.viewed_products = []
        
        print(f"🆔 Usuario iniciado: {self.user_id} en mercado {self.market_id}")

    # ========================================================================
    # 🏪 ENDPOINTS PRINCIPALES DEL SISTEMA (PESO ALTO)
    # ========================================================================

    @task(15)  # Tarea más frecuente - núcleo del negocio
    def conversational_recommendation(self):
        """
        🤖 Endpoint principal MCP - Conversaciones personalizadas
        Simula usuarios pidiendo recomendaciones a través de chat AI
        """
        query = random.choice(EcommerceConfig.CONVERSATION_QUERIES)
        
        payload = {
            "query": query,
            "user_id": self.user_id,
            "market_id": self.market_id,
            "session_id": self.session_id,
            "enable_optimization": True,
            "max_recommendations": random.randint(3, 8)
        }
        
        with self.client.post(
            "/v1/mcp/conversation/optimized",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="🤖 MCP Conversation"
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    recommendations = data.get('recommendations', [])
                    if len(recommendations) > 0:
                        # Simular que el usuario ve algunos productos recomendados
                        for rec in recommendations[:2]:  # Ver primeros 2
                            if 'id' in rec:
                                self.viewed_products.append(rec['id'])
                        response.success()
                    else:
                        response.failure("Empty recommendations")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            elif response.status_code == 422:
                response.failure("Validation error - check payload structure")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(12)  # Segunda tarea más importante
    def get_product_recommendations(self):
        """
        🛍️ Recomendaciones basadas en producto específico
        Simula usuarios viendo productos relacionados
        """
        product_id = random.choice(EcommerceConfig.SAMPLE_PRODUCT_IDS)
        
        params = {
            "n": random.randint(4, 10),
            "exclude_seen": "true"
        }
        
        with self.client.get(
            f"/v1/recommendations/{product_id}",
            params=params,
            headers=self.headers,
            catch_response=True,
            name="🛍️ Product Recommendations"
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        # Agregar productos vistos
                        for product in data[:3]:
                            if isinstance(product, dict) and 'id' in product:
                                self.viewed_products.append(product['id'])
                        response.success()
                    elif isinstance(data, dict) and data.get('recommendations'):
                        response.success()
                    else:
                        response.failure("No recommendations returned")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            elif response.status_code == 404:
                response.failure("Product not found")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(10)  # Navegación de productos
    def browse_products(self):
        """
        📋 Listar productos con paginación
        Simula usuarios navegando el catálogo
        """
        params = {
            "page": random.randint(1, 5),
            "page_size": random.randint(10, 50)
        }
        
        with self.client.get(
            "/v1/products/",
            params=params,
            headers=self.headers,
            catch_response=True,
            name="📋 Browse Products"
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    # Validar estructura de respuesta
                    if isinstance(data, dict):
                        products = data.get('products', data.get('items', []))
                    else:
                        products = data if isinstance(data, list) else []
                    
                    if len(products) > 0:
                        # Simular que usuario ve algunos productos
                        for product in products[:2]:
                            if isinstance(product, dict) and 'id' in product:
                                self.viewed_products.append(product['id'])
                        response.success()
                    else:
                        response.failure("No products returned")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"HTTP {response.status_code}")

    # ========================================================================
    # 🔍 ENDPOINTS DE BÚSQUEDA Y DESCUBRIMIENTO (PESO MEDIO)
    # ========================================================================

    @task(6)  # Búsqueda de productos
    def search_products(self):
        """
        🔍 Búsqueda semántica de productos
        Simula usuarios buscando productos específicos
        """
        query = random.choice(EcommerceConfig.SAMPLE_QUERIES)
        
        params = {
            "q": query,
            "limit": random.randint(5, 20)
        }
        
        with self.client.get(
            "/v1/products/search/",
            params=params,
            headers=self.headers,
            catch_response=True,
            name="🔍 Product Search"
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    results = data if isinstance(data, list) else data.get('results', [])
                    if len(results) > 0:
                        # Usuario ve primeros resultados
                        for result in results[:2]:
                            if isinstance(result, dict) and 'id' in result:
                                self.viewed_products.append(result['id'])
                        response.success()
                    else:
                        response.failure("No search results")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"HTTP {response.status_code}")

    # ========================================================================
    # 📊 ENDPOINTS DE MONITOREO Y MÉTRICAS (PESO BAJO)
    # ========================================================================

    @task(3)  # Métricas del sistema
    def get_system_metrics(self):
        """
        📊 Métricas de rendimiento del sistema
        Simula dashboards y monitoring consultando métricas
        """
        with self.client.get(
            "/v1/metrics",
            headers=self.headers,
            catch_response=True,
            name="📊 System Metrics"
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    # Validar estructura básica de métricas
                    if isinstance(data, dict) and len(data) > 0:
                        response.success()
                    else:
                        response.failure("Empty metrics response")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(2)  # Health check (infraestructura)
    def health_check(self):
        """
        ⚕️ Health check del sistema
        Simula load balancers y monitoring tools verificando salud
        """
        with self.client.get(
            "/health",
            catch_response=True,
            name="⚕️ Health Check"
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    # Verificar que health check tenga estructura válida
                    if isinstance(data, dict) and 'status' in data:
                        if data['status'] in ['operational', 'healthy', 'ok']:
                            response.success()
                        else:
                            response.failure(f"Unhealthy status: {data['status']}")
                    else:
                        response.failure("Invalid health check structure")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"HTTP {response.status_code}")

    # ========================================================================
    # 🎯 FLUJOS DE USUARIO REALISTAS (TAREAS COMBINADAS)
    # ========================================================================

    @task(1)  # Flujo combinado: busqueda y recomendaciones
    def complete_shopping_flow(self):
        """
        Flujo combinado de usuario: busqueda -> recomendaciones de producto.
        (El paso de evento se retiro con la ruta /v1/events/user/, eliminada en S-3.)
        """
        # 1. Buscar producto
        search_query = random.choice(EcommerceConfig.SAMPLE_QUERIES)
        self.client.get(
            "/v1/products/search/",
            params={"q": search_query, "limit": 5},
            headers=self.headers,
            name="🔍 Shopping Flow - Search"
        )
        
        # 2. Ver recomendaciones de producto
        product_id = random.choice(EcommerceConfig.SAMPLE_PRODUCT_IDS)
        self.client.get(
            f"/v1/recommendations/{product_id}",
            params={"n": 5},
            headers=self.headers,
            name="🛍️ Shopping Flow - Recommendations"
        )

# ========================================================================
# 📊 EVENT LISTENERS PARA MÉTRICAS AVANZADAS
# ========================================================================

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """
    📊 Listener para capturar métricas detalladas durante el test
    """
    if exception:
        print(f"❌ Error en {name}: {exception}")
    elif response_time > 2000:  # Alertar sobre requests lentos
        print(f"⚠️ Slow request detected: {name} took {response_time:.2f}ms")

@events.test_start.add_listener  
def on_test_start(environment, **kwargs):
    """🚀 Mensaje de inicio del load test"""
    print("=" * 80)
    print("🚀 INICIANDO LOAD TEST COMPREHENSIVO")
    print("🎯 Simulando tráfico realista de e-commerce")
    print("📊 Endpoints cubiertos:")
    print("   • MCP Conversations (🤖)")
    print("   • Product Recommendations (🛍️)")
    print("   • Product Browsing (📋)")
    print("   • User Recommendations (👤)")
    print("   • Product Search (🔍)")
    print("   • User Events (📊)")
    print("   • System Metrics (📊)")
    print("   • Health Checks (⚕️)")
    print("=" * 80)

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """🏁 Resumen final del load test"""
    print("=" * 80)
    print("🏁 LOAD TEST COMPLETADO")
    print("📊 Revisa los resultados en el dashboard de Locust")
    print("🎯 Endpoints más críticos para analizar:")
    print("   1. 🤖 MCP Conversation (núcleo del negocio)")
    print("   2. 🛍️ Product Recommendations (experiencia usuario)")
    print("   3. ⚕️ Health Check (estabilidad infraestructura)")
    print("=" * 80)

# ========================================================================
# 🎛️ CONFIGURACIÓN AVANZADA (OPCIONAL)
# ========================================================================

class AdvancedEcommerceUser(RetailRecommenderUser):
    """
    🎓 Usuario avanzado con patrones de comportamiento más complejos
    Usar solo para tests de alta complejidad
    """
    
    # Usuarios avanzados son más rápidos
    wait_time = between(0.5, 2)
    
    @task(1)
    def advanced_personalization_flow(self):
        """
        🧠 Flujo avanzado que simula usuarios power con múltiples interacciones
        """
        # Conversación personalizada con contexto
        conversation_payload = {
            "query": f"Based on my previous purchases, what would you recommend for {random.choice(['work', 'leisure', 'fitness', 'travel'])}?",
            "user_id": self.user_id,
            "market_id": self.market_id,
            "session_id": self.session_id,
            "enable_optimization": True,
            "context": {
                "previous_purchases": self.viewed_products[:3],
                "preferences": {
                    "price_range": random.choice(["budget", "mid", "premium"]),
                    "style": random.choice(["casual", "professional", "sporty"])
                }
            }
        }
        
        self.client.post(
            "/v1/mcp/conversation/optimized",
            json=conversation_payload,
            headers=self.headers,
            name="🧠 Advanced Personalization"
        )
