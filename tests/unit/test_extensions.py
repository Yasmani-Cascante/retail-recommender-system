"""
Pruebas unitarias para el sistema de extensiones.

Este módulo contiene pruebas para verificar que el sistema de extensiones
funciona correctamente, permitiendo añadir funcionalidades modulares a la API.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

# Asegurar que src está en el PYTHONPATH
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Importar la extensión de métricas y configuración
from src.api.extensions.metrics_extension import MetricsExtension
from src.api.core.config import RecommenderSettings

class TestMetricsExtension:
    
    @pytest.fixture
    def mock_app(self):
        """Fixture para un mock de la aplicación FastAPI."""
        app = FastAPI()
        return app
    
    @pytest.fixture
    def mock_settings(self):
        """Fixture para configuración simulada para pruebas."""
        settings = MagicMock(spec=RecommenderSettings)
        settings.use_metrics = True
        settings.app_name = "Test App"
        settings.app_version = "1.0.0-test"
        return settings
    
    @pytest.fixture
    def metrics_extension(self, mock_app, mock_settings):
        """Fixture para crear una instancia de la extensión de métricas."""
        return MetricsExtension(mock_app, mock_settings)
    
    def test_extension_initialization(self, metrics_extension, mock_app, mock_settings):
        """Verifica que la extensión se inicializa correctamente."""
        assert metrics_extension.app == mock_app
        assert metrics_extension.settings == mock_settings
    
    def test_setup_with_metrics_enabled(self, metrics_extension, mock_app):
        """Verifica que la extensión configura correctamente la aplicación cuando las métricas están activadas."""
        # Configurar
        mock_app.include_router = MagicMock()
        
        # Ejecutar
        metrics_extension.setup()
        
        # Verificar
        mock_app.include_router.assert_called_once()
    
    def test_setup_with_metrics_disabled(self, mock_app):
        """Verifica que la extensión no configura la aplicación cuando las métricas están desactivadas."""
        # Configurar
        mock_settings = MagicMock(spec=RecommenderSettings)
        mock_settings.use_metrics = False
        metrics_extension = MetricsExtension(mock_app, mock_settings)
        mock_app.include_router = MagicMock()
        
        # Ejecutar
        metrics_extension.setup()
        
        # Verificar
        mock_app.include_router.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint_integration(self):
        """Prueba de integración para verificar que el endpoint de métricas se registra correctamente."""
        # Crear una app real de FastAPI
        app = FastAPI()
        
        # Configurar settings
        settings = MagicMock(spec=RecommenderSettings)
        settings.use_metrics = True
        settings.api_key = "test-api-key-123"  # Añadir API key para autenticación
        
        # Mockear security.py para permitir solicitudes de prueba
        with patch('src.api.security.get_api_key') as mock_get_api_key:
            # Configurar el mock para no requerir autenticación
            mock_get_api_key.return_value = "test-api-key-123"
            
            # Mockear recommendation_metrics
            mock_metrics = MagicMock()
            mock_metrics.get_aggregated_metrics.return_value = {
                "total_requests": 10,
                "avg_response_time_ms": 50.0,
                "success_rate": 0.95,
            }
            
            # Utilizar patch para reemplazar el import de recommendation_metrics
            with patch('src.api.core.metrics.recommendation_metrics', mock_metrics):
                # Crear y configurar la extensión
                metrics_extension = MetricsExtension(app, settings)
                metrics_extension.setup()
                
                # Crear cliente de prueba
                client = TestClient(app)
                # Añadir header de autenticación
                client.headers = {"X-API-Key": "test-api-key-123"}
                
                # Realiza solicitud al endpoint de métricas
                response = client.get("/v1/metrics")
                
                # Verificar respuesta
                assert response.status_code == 200
                data = response.json()
                assert "total_requests" in data
                assert data["total_requests"] == 10
                assert "avg_response_time_ms" in data
                assert data["avg_response_time_ms"] == 50.0
    
    def test_custom_metrics_context_manager(self, metrics_extension):
        """Verifica que el context manager para medir tiempo funciona correctamente."""
        # Este test solo aplica si la extensión tiene un context manager para métricas
        if not hasattr(metrics_extension, 'measure_time'):
            pytest.skip("La extensión no implementa el context manager measure_time")
        
        # Ejecutar
        with metrics_extension.measure_time("test_operation") as timer:
            # Simular operación
            pass
        
        # Verificar (dependerá de la implementación específica)
        assert timer.duration > 0, "El timer no registró duración"


# Implementar clase de test para crear una extensión personalizada
class TestCustomExtension:
    """Clase de prueba para demostrar cómo se puede probar una extensión personalizada."""
    
    class CustomExtension:
        """Extensión de ejemplo para pruebas."""
        
        def __init__(self, app, settings):
            self.app = app
            self.settings = settings
            self.is_setup = False
        
        def setup(self):
            """Configura la extensión."""
            if not hasattr(self.settings, 'use_custom_extension') or not self.settings.use_custom_extension:
                return
            
            self.is_setup = True
            router = APIRouter()
            
            @router.get("/v1/custom")
            def custom_endpoint():
                return {"message": "Custom endpoint working"}
            
            self.app.include_router(router)
    
    @pytest.fixture
    def custom_app(self):
        """Fixture para una aplicación FastAPI para pruebas."""
        return FastAPI()
    
    @pytest.fixture
    def custom_settings(self):
        """Fixture para configuración con extensión personalizada habilitada."""
        settings = MagicMock()
        settings.use_custom_extension = True
        return settings
    
    def test_custom_extension_setup(self, custom_app, custom_settings):
        """Verifica que la extensión personalizada se configura correctamente."""
        # Crear extensión
        extension = self.CustomExtension(custom_app, custom_settings)
        
        # Ejecutar setup
        extension.setup()
        
        # Verificar
        assert extension.is_setup is True
        
        # Verificar endpoint en la aplicación
        client = TestClient(custom_app)
        response = client.get("/v1/custom")
        assert response.status_code == 200
        assert response.json() == {"message": "Custom endpoint working"}
    
    def test_custom_extension_disabled(self, custom_app):
        """Verifica que la extensión personalizada no se configura cuando está deshabilitada."""
        # Crear configuración con extensión deshabilitada
        settings = MagicMock()
        settings.use_custom_extension = False
        
        # Crear extensión
        extension = self.CustomExtension(custom_app, settings)
        
        # Ejecutar setup
        extension.setup()
        
        # Verificar
        assert extension.is_setup is False
        
        # Verificar que el endpoint no existe
        client = TestClient(custom_app)
        response = client.get("/v1/custom")
        assert response.status_code == 404
