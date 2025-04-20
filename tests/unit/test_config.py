"""
Pruebas unitarias para el sistema de configuración centralizado.

Este módulo contiene pruebas para verificar que el sistema de configuración
carga correctamente variables de entorno y proporciona valores por defecto adecuados.
"""

import os
import pytest
from src.api.core.config import get_settings, RecommenderSettings

def test_config_default_values():
    """Verifica que los valores por defecto se cargan correctamente."""
    # Guardar variables de entorno originales
    original_env = dict(os.environ)
    
    # Limpiar variables de entorno para prueba
    os.environ.clear()
    
    # Obtener configuración con valores por defecto
    # Nota: Como get_settings usa lru_cache, debemos reinstanciar directamente para pruebas
    settings = RecommenderSettings()
    
    # Verificar valores por defecto
    assert settings.app_name == "Retail Recommender API"
    assert settings.app_version == "1.0.0"
    assert settings.debug is False
    assert settings.use_metrics is True
    assert settings.exclude_seen_products is True
    assert settings.validate_products is True
    assert settings.use_fallback is True
    assert settings.default_currency == "COP"
    
    # Restaurar variables de entorno
    os.environ.clear()
    os.environ.update(original_env)

def test_config_from_environment():
    """Verifica que las variables de entorno sobrescriben los valores por defecto."""
    # Guardar variables de entorno originales
    original_env = dict(os.environ)
    
    # Configurar variables de entorno para prueba
    os.environ.update({
        "APP_NAME": "Test App",
        "DEBUG": "true",
        "METRICS_ENABLED": "false",
        "EXCLUDE_SEEN_PRODUCTS": "false",
        "DEFAULT_CURRENCY": "USD"
    })
    
    # Forzar recarga de configuración (ya que está cacheada)
    settings = RecommenderSettings()
    
    # Verificar valores cargados desde variables de entorno
    assert settings.app_name == "Test App"
    assert settings.debug is True
    assert settings.use_metrics is False
    assert settings.exclude_seen_products is False
    assert settings.default_currency == "USD"
    
    # Restaurar variables de entorno
    os.environ.clear()
    os.environ.update(original_env)

def test_required_settings():
    """Verifica que se manejan correctamente las variables requeridas."""
    # Guardar variables de entorno originales
    original_env = dict(os.environ)
    
    # Configurar solo variables obligatorias
    os.environ.clear()
    os.environ.update({
        "GOOGLE_PROJECT_NUMBER": "test-project-123",
        "API_KEY": "test-api-key"
    })
    
    # Obtener configuración
    settings = RecommenderSettings()
    
    # Verificar valores requeridos
    assert settings.google_project_number == "test-project-123"
    assert settings.api_key == "test-api-key"
    
    # Verificar valores por defecto para opcionales
    assert settings.google_location == "global"
    assert settings.google_catalog == "default_catalog"
    assert settings.google_serving_config == "default_recommendation_config"
    
    # Restaurar variables de entorno
    os.environ.clear()
    os.environ.update(original_env)

def test_boolean_settings():
    """Verifica que los valores booleanos se interpretan correctamente desde variables de entorno."""
    # Guardar variables de entorno originales
    original_env = dict(os.environ)
    
    # Varios valores que deberían interpretarse como True
    for true_value in ["true", "True", "TRUE", "1", "yes", "Y"]:
        os.environ.clear()
        os.environ["DEBUG"] = true_value
        settings = RecommenderSettings()
        assert settings.debug is True, f"El valor '{true_value}' debería interpretarse como True"
        
    # Varios valores que deberían interpretarse como False
    for false_value in ["false", "False", "FALSE", "0", "no", "N"]:
        os.environ.clear()
        os.environ["DEBUG"] = false_value
        settings = RecommenderSettings()
        assert settings.debug is False, f"El valor '{false_value}' debería interpretarse como False"
    
    # Restaurar variables de entorno
    os.environ.clear()
    os.environ.update(original_env)

def test_config_cache():
    """Verifica que la configuración se cachea correctamente."""
    # Llamar a get_settings() varias veces debería devolver la misma instancia
    settings1 = get_settings()
    settings2 = get_settings()
    
    # Verificar que son el mismo objeto (por identidad, no solo igualdad)
    assert settings1 is settings2
