"""
Pruebas de rendimiento para la API del sistema de recomendaciones.

Este módulo contiene pruebas para evaluar el rendimiento de los componentes principales
de la API, midiendo tiempos de respuesta y uso de recursos.
"""

import pytest
import os
import time
import logging
import asyncio
from unittest.mock import patch, MagicMock
from statistics import mean, median, stdev
import random
from fastapi.testclient import TestClient

# Asegurar que src está en el PYTHONPATH
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Importar test_logging para configurar logging
from tests.test_logging import setup_test_logging, get_test_logger
from tests.data.sample_products import SAMPLE_PRODUCTS

# Configurar logging específico para pruebas de rendimiento
logger = get_test_logger("performance")

class TestAPIPerformance:
    """Pruebas de rendimiento para los endpoints de la API."""
    
    @pytest.fixture
    def performance_client(self):
        """
        Fixture que proporciona un cliente configurado para pruebas de rendimiento.
        
        Utiliza mocks para componentes externos pero mide tiempos reales de procesamiento.
        """
        # Patch componentes
        with patch('src.api.factories.RecommenderFactory.create_tfidf_recommender') as mock_create_tfidf, \
             patch('src.api.factories.RecommenderFactory.create_retail_recommender') as mock_create_retail, \
             patch('src.api.factories.RecommenderFactory.create_hybrid_recommender') as mock_create_hybrid, \
             patch('src.api.startup_helper.StartupManager.is_healthy') as mock_is_healthy:
            
            # Configurar mocks pero con pequeños retrasos para simular procesamiento real
            mock_tfidf = MagicMock()
            mock_tfidf.loaded = True
            mock_tfidf.product_data = SAMPLE_PRODUCTS
            # Simular tiempo de procesamiento para búsqueda
            mock_tfidf.search_products = lambda query, n: (
                time.sleep(0.01 * len(query)), SAMPLE_PRODUCTS[:min(n, 5)])[1]
            mock_tfidf.get_product_by_id = lambda id: next(
                (p for p in SAMPLE_PRODUCTS if str(p.get('id')) == str(id)), None)
            mock_tfidf.health_check.return_value = {"status": "operational", "loaded": True}
            mock_create_tfidf.return_value = mock_tfidf
            
            mock_retail = MagicMock()
            mock_create_retail.return_value = mock_retail
            
            mock_hybrid = MagicMock()
            # Simular tiempos de procesamiento variables para recomendaciones
            def mock_get_recommendations(**kwargs):
                # Simular variabilidad en tiempos de respuesta
                time.sleep(random.uniform(0.01, 0.05))
                return SAMPLE_PRODUCTS[:min(kwargs.get('n_recommendations', 5), 10)]
                
            mock_hybrid.get_recommendations = mock_get_recommendations
            mock_hybrid.record_user_event = lambda **kwargs: (
                time.sleep(0.01), {"status": "success", "event_type": kwargs.get('event_type', 'detail-page-view')})[1]
            mock_hybrid.content_weight = 0.5
            mock_create_hybrid.return_value = mock_hybrid
            
            # Configurar verificación de salud
            mock_is_healthy.return_value = (True, "")
            
            # Importar aplicación e inicializar cliente
            from src.api.main_unified import app
            client = TestClient(app)
            
            # Añadir API key para autenticación en todas las solicitudes
            client.headers = {"X-API-Key": "test-api-key-123"}
            
            yield client
    
    def test_endpoint_response_times(self, performance_client):
        """
        Mide los tiempos de respuesta de los principales endpoints.
        
        Esta prueba realiza múltiples solicitudes a cada endpoint principal
        y registra estadísticas sobre los tiempos de respuesta.
        """
        # Configuración
        n_requests = 10
        endpoints = [
            "/health",
            "/v1/products/",
            "/v1/recommendations/test_prod_1",
            "/v1/recommendations/user/test_user_1",
            "/v1/products/search/?q=camiseta"
        ]
        
        results = {}
        
        # Ejecutar solicitudes a cada endpoint
        for endpoint in endpoints:
            times = []
            for _ in range(n_requests):
                start_time = time.time()
                response = performance_client.get(endpoint)
                end_time = time.time()
                assert response.status_code == 200, f"Fallo en endpoint {endpoint}: {response.text}"
                times.append((end_time - start_time) * 1000)  # Convertir a ms
            
            # Calcular estadísticas
            results[endpoint] = {
                "min_ms": min(times),
                "max_ms": max(times),
                "avg_ms": mean(times),
                "median_ms": median(times),
                "stdev_ms": stdev(times) if len(times) > 1 else 0
            }
            
            # Logging
            logger.info(f"Rendimiento del endpoint {endpoint}:")
            logger.info(f"  Min: {results[endpoint]['min_ms']:.2f}ms")
            logger.info(f"  Max: {results[endpoint]['max_ms']:.2f}ms")
            logger.info(f"  Avg: {results[endpoint]['avg_ms']:.2f}ms")
            logger.info(f"  Median: {results[endpoint]['median_ms']:.2f}ms")
            logger.info(f"  StdDev: {results[endpoint]['stdev_ms']:.2f}ms")
        
        # Verificaciones básicas (estos valores pueden ajustarse según el entorno)
        for endpoint, stats in results.items():
            # El tiempo de respuesta promedio debería ser razonable
            assert stats["avg_ms"] < 1000, f"Tiempo promedio demasiado alto para {endpoint}: {stats['avg_ms']:.2f}ms"
            # El tiempo máximo no debería ser demasiado mayor que el promedio
            assert stats["max_ms"] < stats["avg_ms"] * 5, f"Variabilidad excesiva para {endpoint}"
    
    def test_concurrent_requests(self, performance_client):
        """
        Evalúa el rendimiento con solicitudes concurrentes.
        
        Esta prueba simula múltiples usuarios realizando solicitudes simultáneas
        y mide los tiempos de respuesta bajo carga.
        """
        import concurrent.futures
        
        # Configuración
        n_concurrent = 10
        endpoint = "/v1/recommendations/test_prod_1"
        
        def make_request():
            start_time = time.time()
            response = performance_client.get(endpoint)
            end_time = time.time()
            return {
                "status_code": response.status_code,
                "time_ms": (end_time - start_time) * 1000
            }
        
        # Ejecutar solicitudes concurrentes
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_concurrent) as executor:
            futures = [executor.submit(make_request) for _ in range(n_concurrent)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # Analizar resultados
        times = [result["time_ms"] for result in results]
        successful = [result for result in results if result["status_code"] == 200]
        
        # Logging
        logger.info(f"Rendimiento con {n_concurrent} solicitudes concurrentes:")
        logger.info(f"  Solicitudes exitosas: {len(successful)}/{n_concurrent}")
        logger.info(f"  Tiempo promedio: {mean(times):.2f}ms")
        logger.info(f"  Tiempo máximo: {max(times):.2f}ms")
        
        # Verificaciones
        assert len(successful) == n_concurrent, f"Solo {len(successful)}/{n_concurrent} solicitudes exitosas"
        # El tiempo promedio bajo carga no debería ser extremadamente alto
        assert mean(times) < 2000, f"Tiempo promedio demasiado alto bajo carga: {mean(times):.2f}ms"
    
    def test_event_registration_performance(self, performance_client):
        """
        Evalúa el rendimiento del registro de eventos de usuario.
        
        Esta prueba mide los tiempos de respuesta para registrar diferentes tipos
        de eventos de usuario, simulando un escenario de uso real.
        """
        # Eventos a registrar
        events = [
            {"user_id": "test_user_1", "event_type": "detail-page-view", "product_id": "test_prod_1"},
            {"user_id": "test_user_1", "event_type": "add-to-cart", "product_id": "test_prod_2"},
            {"user_id": "test_user_1", "event_type": "purchase-complete", "product_id": "test_prod_2", "purchase_amount": 59.99},
            {"user_id": "test_user_2", "event_type": "search", "product_id": None},
            {"user_id": "test_user_2", "event_type": "category-page-view", "product_id": None},
        ]
        
        results = []
        
        # Registrar cada evento y medir tiempo
        for event in events:
            # Construir URL
            url = f"/v1/events/user/{event['user_id']}?event_type={event['event_type']}"
            if event.get("product_id"):
                url += f"&product_id={event['product_id']}"
            if event.get("purchase_amount"):
                url += f"&purchase_amount={event['purchase_amount']}"
            
            # Medir tiempo
            start_time = time.time()
            response = performance_client.post(url)
            end_time = time.time()
            
            # Registrar resultados
            assert response.status_code == 200, f"Fallo al registrar evento: {response.text}"
            results.append({
                "event_type": event["event_type"],
                "time_ms": (end_time - start_time) * 1000
            })
        
        # Calcular estadísticas
        event_type_times = {}
        for result in results:
            event_type = result["event_type"]
            if event_type not in event_type_times:
                event_type_times[event_type] = []
            event_type_times[event_type].append(result["time_ms"])
        
        # Logging
        for event_type, times in event_type_times.items():
            avg_time = mean(times)
            logger.info(f"Rendimiento para eventos de tipo '{event_type}':")
            logger.info(f"  Tiempo promedio: {avg_time:.2f}ms")
            
            # Verificación
            assert avg_time < 500, f"Tiempo promedio demasiado alto para eventos '{event_type}': {avg_time:.2f}ms"
    
    def test_memory_usage(self):
        """
        Mide el consumo de memoria durante la operación normal.
        
        Esta prueba requiere el módulo memory_profiler que debe instalarse por separado:
        pip install memory-profiler
        """
        try:
            import memory_profiler
        except ImportError:
            pytest.skip("memory_profiler no está instalado. Instale con: pip install memory-profiler")
        
        # Importar módulo principal para medir su consumo de memoria
        from src.api.main_unified import app
        
        # Punto de referencia de memoria antes de la creación del objeto
        mem_before = memory_profiler.memory_usage()[0]
        
        # Crear cliente de prueba (esto carga las dependencias)
        client = TestClient(app)
        
        # Punto de referencia después de la creación
        mem_after = memory_profiler.memory_usage()[0]
        
        # Logging
        mem_diff = mem_after - mem_before
        logger.info(f"Consumo de memoria para inicialización de la aplicación:")
        logger.info(f"  Antes: {mem_before:.2f} MiB")
        logger.info(f"  Después: {mem_after:.2f} MiB")
        logger.info(f"  Diferencia: {mem_diff:.2f} MiB")
        
        # Verificación (ajustar según las expectativas)
        # Este límite es arbitrario y debería ajustarse según el entorno
        assert mem_diff < 200, f"Consumo de memoria excesivo: {mem_diff:.2f} MiB"
    
    def test_startup_time(self):
        """
        Mide el tiempo de inicio de la aplicación.
        
        Esta prueba es importante porque los tiempos de inicio lentos
        pueden afectar negativamente el despliegue en Cloud Run.
        """
        # Medir tiempo para importar y crear la aplicación
        start_time = time.time()
        
        # Importar módulo principal (esto ejecuta el código de inicialización)
        from importlib import reload
        import src.api.main_unified
        reload(src.api.main_unified)
        
        end_time = time.time()
        startup_time = (end_time - start_time) * 1000  # ms
        
        # Logging
        logger.info(f"Tiempo de inicio de la aplicación: {startup_time:.2f}ms")
        
        # Verificación (ajustar según expectativas)
        # Este límite es arbitrario y debería ajustarse según el entorno
        assert startup_time < 2000, f"Tiempo de inicio excesivo: {startup_time:.2f}ms"
