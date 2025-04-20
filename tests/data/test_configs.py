"""
Configuraciones de prueba para el sistema de recomendaciones.

Este módulo proporciona diferentes configuraciones para probar el comportamiento
del sistema con distintas características activadas/desactivadas.
"""

TEST_CONFIGS = {
    "full_features": {
        "METRICS_ENABLED": "true",
        "EXCLUDE_SEEN_PRODUCTS": "true",
        "VALIDATE_PRODUCTS": "true",
        "USE_FALLBACK": "true",
        "CONTENT_WEIGHT": "0.5",
        "DEBUG": "true"
    },
    "no_metrics": {
        "METRICS_ENABLED": "false",
        "EXCLUDE_SEEN_PRODUCTS": "true",
        "VALIDATE_PRODUCTS": "true",
        "USE_FALLBACK": "true",
        "CONTENT_WEIGHT": "0.5",
        "DEBUG": "true"
    },
    "no_exclusion": {
        "METRICS_ENABLED": "true",
        "EXCLUDE_SEEN_PRODUCTS": "false",
        "VALIDATE_PRODUCTS": "true",
        "USE_FALLBACK": "true",
        "CONTENT_WEIGHT": "0.5",
        "DEBUG": "true"
    },
    "content_only": {
        "METRICS_ENABLED": "true",
        "EXCLUDE_SEEN_PRODUCTS": "true",
        "VALIDATE_PRODUCTS": "true",
        "USE_FALLBACK": "true",
        "CONTENT_WEIGHT": "1.0",  # Solo recomendaciones basadas en contenido
        "DEBUG": "true"
    },
    "retail_only": {
        "METRICS_ENABLED": "true",
        "EXCLUDE_SEEN_PRODUCTS": "true",
        "VALIDATE_PRODUCTS": "true",
        "USE_FALLBACK": "true",
        "CONTENT_WEIGHT": "0.0",  # Solo recomendaciones de Retail API
        "DEBUG": "true"
    },
    "no_fallback": {
        "METRICS_ENABLED": "true",
        "EXCLUDE_SEEN_PRODUCTS": "true",
        "VALIDATE_PRODUCTS": "true",
        "USE_FALLBACK": "false",
        "CONTENT_WEIGHT": "0.5",
        "DEBUG": "true"
    },
    "no_validation": {
        "METRICS_ENABLED": "true",
        "EXCLUDE_SEEN_PRODUCTS": "true",
        "VALIDATE_PRODUCTS": "false",
        "USE_FALLBACK": "true",
        "CONTENT_WEIGHT": "0.5",
        "DEBUG": "true"
    },
    "minimal": {
        "METRICS_ENABLED": "false",
        "EXCLUDE_SEEN_PRODUCTS": "false",
        "VALIDATE_PRODUCTS": "false",
        "USE_FALLBACK": "false",
        "CONTENT_WEIGHT": "0.5",
        "DEBUG": "false"
    }
}

def get_config(config_name):
    """
    Obtiene una configuración específica por nombre.
    
    Args:
        config_name: Nombre de la configuración
        
    Returns:
        Dict: Configuración solicitada, o configuración 'full_features' si no existe
    """
    return TEST_CONFIGS.get(config_name, TEST_CONFIGS["full_features"])

def apply_config_to_env(config_name, env_dict=None):
    """
    Aplica una configuración a un diccionario de variables de entorno.
    
    Args:
        config_name: Nombre de la configuración a aplicar
        env_dict: Diccionario de variables de entorno a modificar (si es None, se crea uno nuevo)
        
    Returns:
        Dict: Diccionario de variables de entorno actualizado
    """
    config = get_config(config_name)
    
    if env_dict is None:
        env_dict = {}
        
    # Aplicar configuración
    for key, value in config.items():
        env_dict[key] = value
        
    return env_dict
