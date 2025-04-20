"""
Configuración de logging para pruebas del sistema de recomendaciones.

Este módulo proporciona configuración especializada de logging para entornos de prueba,
facilitando el diagnóstico y depuración durante la ejecución de pruebas.
"""

import logging
import os
import sys
from datetime import datetime

# Directorio para logs de pruebas
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "tests")

# Crear directorio de logs si no existe
os.makedirs(LOG_DIR, exist_ok=True)

# Nombres de los archivos de log
TIME_STR = datetime.now().strftime("%Y%m%d_%H%M%S")
DEBUG_LOG = os.path.join(LOG_DIR, f"test_debug_{TIME_STR}.log")
ERROR_LOG = os.path.join(LOG_DIR, f"test_error_{TIME_STR}.log")

# Configuración de formato para logs
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_test_logging(log_level=logging.DEBUG):
    """
    Configura el sistema de logging para pruebas con un nivel especificado.
    
    Args:
        log_level: Nivel de logging (default: DEBUG)
    """
    # Configurar logger principal
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Limpiar handlers existentes para evitar duplicados
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Handler para consola (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(console_handler)
    
    # Handler para archivo de debug
    debug_handler = logging.FileHandler(DEBUG_LOG, mode='w')
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(debug_handler)
    
    # Handler para archivo de errores
    error_handler = logging.FileHandler(ERROR_LOG, mode='w')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(error_handler)
    
    # Log inicial para verificar la configuración
    logging.info(f"Logging configurado para pruebas. Archivos: {DEBUG_LOG}, {ERROR_LOG}")
    
    return root_logger

def get_test_logger(name):
    """
    Obtiene un logger específico para el módulo de pruebas especificado.
    
    Args:
        name: Nombre del módulo de pruebas
        
    Returns:
        Logger configurado para el módulo
    """
    logger = logging.getLogger(f"test.{name}")
    return logger
