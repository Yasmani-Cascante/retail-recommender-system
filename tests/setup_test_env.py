"""
Script para configurar el entorno de pruebas para el sistema de recomendaciones.

Este script:
1. Carga variables de entorno desde .env.test
2. Configura logging para pruebas
3. Prepara directorios necesarios para las pruebas
"""

import os
import sys
import logging
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Configuración de logging para pruebas
def setup_test_logging():
    """Configura logging específico para pruebas con nivel DEBUG."""
    log_dir = Path("logs/tests")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "test_run.log"),
            logging.StreamHandler()
        ]
    )
    
    logging.info("Configuración de logging para pruebas completada")

# Cargar variables de entorno de prueba
def load_test_env():
    """Carga variables de entorno desde .env.test."""
    env_file = Path(".env.test")
    if env_file.exists():
        load_dotenv(env_file)
        logging.info(f"Variables de entorno cargadas desde {env_file}")
    else:
        logging.warning(f"Archivo {env_file} no encontrado. Usando valores por defecto.")

# Preparar directorios necesarios para pruebas
def prepare_test_directories():
    """Crea o limpia directorios necesarios para las pruebas."""
    # Directorio para datos de prueba
    test_data_dir = Path("data/test")
    test_data_dir.mkdir(parents=True, exist_ok=True)
    
    # Directorio para modelos de prueba
    test_models_dir = Path("data/test/models")
    test_models_dir.mkdir(parents=True, exist_ok=True)
    
    # Directorio para resultados de pruebas
    test_results_dir = Path("tests/results")
    if test_results_dir.exists():
        # Limpiar directorio de resultados anteriores
        shutil.rmtree(test_results_dir)
    test_results_dir.mkdir(parents=True, exist_ok=True)
    
    logging.info("Directorios de prueba preparados")

def setup_test_environment():
    """Configura todo el entorno de prueba."""
    setup_test_logging()
    load_test_env()
    prepare_test_directories()
    
    # Asegurar que src está en el PYTHONPATH
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    logging.info("Entorno de prueba configurado correctamente")
    
    return True

if __name__ == "__main__":
    # Ejecutar configuración si se llama directamente
    setup_test_environment()
