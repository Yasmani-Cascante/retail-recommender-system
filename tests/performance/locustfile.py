"""
Configuración de pruebas de carga con Locust para el sistema de recomendaciones.

Este archivo define escenarios de prueba de carga para evaluar el rendimiento 
del sistema de recomendaciones bajo diferentes niveles de tráfico.

Para ejecutar:
    locust -f tests/performance/locustfile.py

Requiere instalar el paquete Locust:
    pip install locust
"""

import time
import json
import random
from locust import HttpUser, task, between, tag

# Datos de muestra para pruebas
SAMPLE_PRODUCT_IDS = [
    "test_prod_1", "test_prod_2", "test_prod_3", "test_prod_4", "test_prod_5", 
    "test_prod_6", "test_prod_7", "test_prod_8", "test_prod_9", "10"
]

SAMPLE_USER_IDS = [
    "test_user_1", "test_user_2", "test_user_3", "test_user_4", "test_user_5",
    "customer_1", "customer_2", "anonymous"
]

SEARCH_TERMS = [
    "camiseta", "pantalón", "zapatillas", "smartphone", "libro",
    "python", "deportivas", "tablet", "televisor"
]

EVENT_TYPES = [
    "detail-page-view", "add-to-cart", "purchase-complete", 
    "search", "category-page-view", "home-page-view"
]

class RecommenderUser(HttpUser):
    """
    Simula un usuario interactuando con el sistema de recomendaciones.
    
    Esta clase define diferentes tareas que los usuarios simulados realizarán
    durante la prueba de carga, representando patrones de uso reales.
    """
    # Tiempo de espera entre tareas: entre 1 y 5 segundos
    wait_time = between(1, 5)
    
    def on_start(self):
        """Inicialización al comienzo de la simulación para cada usuario."""
        # Configurar API key para autenticación
        self.client.headers = {
            "X-API-Key": "test-api-key-123"
        }
        # Asignar ID de usuario para esta sesión
        self.user_id = random.choice(SAMPLE_USER_IDS)
    
    @tag("health")
    @task(1)
    def check_health(self):
        """Verifica el estado de salud del sistema."""
        with self.client.get("/health", name="Health Check", catch_response=True) as response:
            if response.status_code == 200:
                health_data = response.json()
                if health_data["status"] == "operational":
                    response.success()
                else:
                    response.failure(f"Estado no operacional: {health_data['status']}")
            else:
                response.failure(f"Health check falló: {response.status_code}")
    
    @tag("browse")
    @task(5)
    def browse_products(self):
        """Navega por el catálogo de productos."""
        # 50% del tiempo usa paginación
        if random.random() < 0.5:
            page = random.randint(1, 3)
            page_size = random.choice([10, 20, 50])
            with self.client.get(f"/v1/products/?page={page}&page_size={page_size}", 
                               name="Browse Products (with pagination)", 
                               catch_response=True) as response:
                self._validate_products_response(response)
        else:
            with self.client.get("/v1/products/", 
                               name="Browse Products", 
                               catch_response=True) as response:
                self._validate_products_response(response)
    
    @tag("search")
    @task(3)
    def search_products(self):
        """Busca productos específicos."""
        query = random.choice(SEARCH_TERMS)
        with self.client.get(f"/v1/products/search/?q={query}", 
                           name="Search Products", 
                           catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if "products" in data and "total" in data:
                    response.success()
                else:
                    response.failure("Respuesta de búsqueda mal formada")
            else:
                response.failure(f"Búsqueda falló: {response.status_code}")
    
    @tag("recommendations")
    @task(10)
    def get_product_recommendations(self):
        """Obtiene recomendaciones basadas en producto."""
        product_id = random.choice(SAMPLE_PRODUCT_IDS)
        n = random.choice([3, 5, 10])
        content_weight = random.choice([0.3, 0.5, 0.7])
        
        with self.client.get(f"/v1/recommendations/{product_id}?n={n}&content_weight={content_weight}", 
                           name="Product Recommendations", 
                           catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if "recommendations" in data and len(data["recommendations"]) > 0:
                    response.success()
                else:
                    response.failure("No se recibieron recomendaciones")
            else:
                response.failure(f"Obtención de recomendaciones falló: {response.status_code}")
    
    @tag("recommendations")
    @task(7)
    def get_user_recommendations(self):
        """Obtiene recomendaciones personalizadas para usuario."""
        n = random.choice([3, 5, 10])
        
        with self.client.get(f"/v1/recommendations/user/{self.user_id}?n={n}", 
                           name="User Recommendations", 
                           catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if "recommendations" in data and len(data["recommendations"]) > 0:
                    response.success()
                else:
                    response.failure("No se recibieron recomendaciones para el usuario")
            else:
                response.failure(f"Obtención de recomendaciones para usuario falló: {response.status_code}")
    
    @tag("events")
    @task(15)
    def record_user_event(self):
        """Registra un evento de usuario."""
        event_type = random.choice(EVENT_TYPES)
        
        # Construir URL base
        url = f"/v1/events/user/{self.user_id}?event_type={event_type}"
        
        # Para algunos tipos de evento, añadir ID de producto
        if event_type in ["detail-page-view", "add-to-cart", "purchase-complete"]:
            product_id = random.choice(SAMPLE_PRODUCT_IDS)
            url += f"&product_id={product_id}"
            
            # Para eventos de compra, añadir monto
            if event_type == "purchase-complete":
                purchase_amount = round(random.uniform(10, 200), 2)
                url += f"&purchase_amount={purchase_amount}"
        
        with self.client.post(url, name=f"Record Event: {event_type}", catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    response.success()
                else:
                    response.failure(f"Evento no registrado correctamente: {data}")
            else:
                response.failure(f"Registro de evento falló: {response.status_code}")
    
    @tag("categories")
    @task(2)
    def browse_by_category(self):
        """Navega productos por categoría."""
        category = random.choice(["Ropa", "Calzado", "Electrónica", "Libros", "Varios"])
        
        with self.client.get(f"/v1/products/category/{category}", 
                           name=f"Browse Category: {category}", 
                           catch_response=True) as response:
            if response.status_code == 200:
                # Categorías inexistentes pueden devolver 404, lo cual es correcto
                response.success()
            elif response.status_code == 404 and "No products found in category" in response.text:
                # Esto es un comportamiento esperado para categorías sin productos
                response.success()
            else:
                response.failure(f"Navegación por categoría falló: {response.status_code}")
    
    @tag("customers")
    @task(1)
    def list_customers(self):
        """Lista los clientes disponibles."""
        with self.client.get("/v1/customers/", 
                           name="List Customers", 
                           catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if "customers" in data and "total" in data:
                    response.success()
                else:
                    response.failure("Respuesta de clientes mal formada")
            else:
                response.failure(f"Listado de clientes falló: {response.status_code}")
    
    def _validate_products_response(self, response):
        """Valida la respuesta de productos."""
        if response.status_code == 200:
            data = response.json()
            if "products" in data and "total" in data:
                response.success()
            else:
                response.failure("Respuesta de productos mal formada")
        else:
            response.failure(f"Obtención de productos falló: {response.status_code}")


class UserFlowSimulation(HttpUser):
    """
    Simula flujos completos de usuarios, siguiendo patrones de navegación realistas.
    
    Esta clase realiza secuencias de tareas que representan sesiones de usuario completas,
    como buscar, ver detalles, añadir al carrito y completar compras.
    """
    # Tiempo de espera entre tareas: entre 3 y 8 segundos
    wait_time = between(3, 8)
    
    def on_start(self):
        """Inicialización al comienzo de la simulación para cada usuario."""
        # Configurar API key para autenticación
        self.client.headers = {
            "X-API-Key": "test-api-key-123"
        }
        # Asignar ID de usuario para esta sesión
        self.user_id = random.choice(SAMPLE_USER_IDS)
        # Carrito de compras simulado
        self.cart = []
    
    @tag("user_flow")
    @task(1)
    def complete_shopping_flow(self):
        """Simula un flujo completo de compra."""
        # 1. Navegar a la página principal
        self.client.get("/health", name="Shopping Flow: Start")
        time.sleep(random.uniform(1, 2))
        
        # 2. Ver productos o buscar
        if random.random() < 0.5:
            # Navegar por productos
            self.client.get("/v1/products/", name="Shopping Flow: Browse Products")
        else:
            # Buscar productos
            query = random.choice(SEARCH_TERMS)
            self.client.get(f"/v1/products/search/?q={query}", name="Shopping Flow: Search Products")
        time.sleep(random.uniform(1, 3))
        
        # 3. Ver detalles de producto(s) - simulado con registro de eventos
        viewed_products = []
        for _ in range(random.randint(1, 4)):
            product_id = random.choice(SAMPLE_PRODUCT_IDS)
            viewed_products.append(product_id)
            self.client.post(
                f"/v1/events/user/{self.user_id}?event_type=detail-page-view&product_id={product_id}",
                name="Shopping Flow: View Product"
            )
            time.sleep(random.uniform(1, 3))
            
            # Ver recomendaciones para este producto
            self.client.get(
                f"/v1/recommendations/{product_id}?n=5",
                name="Shopping Flow: View Recommendations"
            )
            time.sleep(random.uniform(1, 2))
        
        # 4. Añadir productos al carrito
        cart_products = random.sample(viewed_products, min(len(viewed_products), random.randint(1, 2)))
        for product_id in cart_products:
            self.cart.append(product_id)
            self.client.post(
                f"/v1/events/user/{self.user_id}?event_type=add-to-cart&product_id={product_id}",
                name="Shopping Flow: Add to Cart"
            )
            time.sleep(random.uniform(1, 2))
        
        # 5. Finalizar compra (50% de probabilidad)
        if random.random() < 0.5 and self.cart:
            for product_id in self.cart:
                # Simular precio
                purchase_amount = round(random.uniform(10, 200), 2)
                self.client.post(
                    f"/v1/events/user/{self.user_id}?event_type=purchase-complete&product_id={product_id}&purchase_amount={purchase_amount}",
                    name="Shopping Flow: Complete Purchase"
                )
            # Limpiar carrito
            self.cart = []
        
        # 6. Ver recomendaciones personalizadas
        self.client.get(
            f"/v1/recommendations/user/{self.user_id}?n=5",
            name="Shopping Flow: Personal Recommendations"
        )
