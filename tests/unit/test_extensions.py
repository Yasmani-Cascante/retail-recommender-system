"""
Pruebas unitarias para el sistema de extensiones.

Este módulo contiene pruebas para verificar que las extensiones se cargan y configuran
correctamente según la configuración del sistema.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from src.api.extensions.metrics_extension import MetricsExtension

@pytest.fixture
def mock_app():
    """Fixture para crear una aplicación FastAPI de prueba."""
    return MagicMock(spec=FastAPI)

@pytest.fixture
def mock_settings():
    """Fixture para simular la configuración con valores predeterminados."""
    settings = MagicMock()
    settings.use_metrics = True
    return settings

def test_metrics_extension_enabled(mock_app, mock_settings):
    """Prueba que la extensión de métricas se configura correctamente cuando está habilitada."""
    # Crear instancia de la extensión
    extension = MetricsExtension(mock_app, mock_settings)
    
    # Configurar la extensión
    extension.setup()
    
    # Verificar que se incluyó el router de métricas
    mock_app.include_router.assert_called_once()

def test_metrics_extension_disabled(mock_app, mock_settings):
    """Prueba que la extensión de métricas no se configura cuando está deshabilitada."""
    # Deshabilitar métricas
    mock_settings.use_metrics = False
    
    # Crear instancia de la extensión
    extension = MetricsExtension(mock_app, mock_settings)
    
    # Configurar la extensión
    extension.setup()
    
    # Verificar que no se incluyó el router de métricas
    mock_app.include_router.assert_not_called()

@pytest.mark.asyncio
async def test_metrics_endpoint_integration():
    """Prueba la integración de la extensión de métricas con FastAPI."""
    # Crear una aplicación FastAPI real para esta prueba
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    
    # Crear aplicación y configuración
    app = FastAPI()
    mock_settings = MagicMock()
    mock_settings.use_metrics = True
    
    # Configurar mock para recommendation_metrics
    with patch('src.api.extensions.metrics_extension.recommendation_metrics') as mock_metrics:
        # Configurar métricas simuladas para devolver
        mock_metrics.get_aggregated_metrics.return_value = {
            "total_requests": 100,
            "average_response_time_ms": 123.45,
            "recommendation_type_distribution": {
                "content": 0.6,
                "retail": 0.3,
                "fallback": 0.1
            }
        }
        
        # Crear y configurar la extensión
        extension = MetricsExtension(app, mock_settings)
        extension.setup()
        
        # Configurar la seguridad para pruebas
        with patch('src.api.extensions.metrics_extension.get_current_user', return_value="test_user"):
            # Crear cliente de prueba
            client = TestClient(app)
            
            # Probar el endpoint de métricas
            response = client.get("/v1/metrics")
            
            # Verificar respuesta
            assert response.status_code == 200
            assert "realtime_metrics" in response.json()
            metrics = response.json()["realtime_metrics"]
            assert metrics["total_requests"] == 100
            assert metrics["average_response_time_ms"] == 123.45
            assert "recommendation_type_distribution" in metrics

def test_extension_error_handling(mock_app, mock_settings):
    """Prueba que la extensión maneja errores correctamente."""
    # Crear instancia de la extensión
    extension = MetricsExtension(mock_app, mock_settings)
    
    # Simular un error al incluir el router
    mock_app.include_router.side_effect = Exception("Error de prueba")
    
    # La configuración debería manejar el error sin propagarlo
    with patch("src.api.extensions.metrics_extension.logger") as mock_logger:
        extension.setup()
        
        # Verificar que se registró el error
        mock_logger.error.assert_called()

def test_multiple_extensions(mock_app):
    """Prueba que múltiples extensiones pueden coexistir."""
    # Crear mocks para configuraciones
    settings_metrics = MagicMock()
    settings_metrics.use_metrics = True
    
    settings_other = MagicMock()
    settings_other.use_other_extension = True
    
    # Crear instancias de extensiones
    metrics_extension = MetricsExtension(mock_app, settings_metrics)
    
    # Mock para otra extensión
    other_extension = MagicMock()
    
    # Configurar extensiones
    metrics_extension.setup()
    other_extension.setup()
    
    # Verificar que ambas extensiones fueron configuradas
    assert mock_app.include_router.call_count == 1
    assert other_extension.setup.call_count == 1
