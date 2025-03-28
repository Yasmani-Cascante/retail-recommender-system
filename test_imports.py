#!/usr/bin/env python3
"""
Script para probar las importaciones correctas de Google Cloud Retail API.
"""
import os
import sys
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_imports():
    """Verifica las importaciones correctas para Google Cloud Retail API."""
    try:
        # Importaciones básicas
        logging.info("Verificando importaciones básicas...")
        from google.cloud import retail_v2
        logging.info("✅ Importado google.cloud.retail_v2")
        
        # Importaciones específicas
        logging.info("Verificando importaciones específicas...")
        try:
            from google.cloud.retail_v2.types import InputConfig, GcsSource
            logging.info("✅ Importadas correctamente InputConfig y GcsSource")
        except ImportError as e:
            logging.error(f"❌ Error importando InputConfig, GcsSource: {e}")
            # Intentar alternativas
            try:
                logging.info("Intentando rutas alternativas...")
                from google.cloud.retail_v2.types.import_config import InputConfig, GcsSource
                logging.info("✅ Importadas desde import_config: InputConfig y GcsSource")
            except ImportError as e:
                logging.error(f"❌ Error importando desde import_config: {e}")
        
        # Verificar ImportProductsRequest
        try:
            from google.cloud.retail_v2.types import ImportProductsRequest
            logging.info("✅ Importado ImportProductsRequest")
            
            # Crear una instancia para ver atributos
            request = ImportProductsRequest()
            logging.info(f"Atributos de ImportProductsRequest: {dir(request)[:10]}...")
            logging.info(f"¿Tiene InputConfig como atributo? {'input_config' in dir(request)}")
            
            # Verificar si tiene InputConfig como clase anidada
            has_nested_input_config = hasattr(ImportProductsRequest, 'InputConfig')
            logging.info(f"¿Tiene InputConfig como clase anidada? {has_nested_input_config}")
            
        except Exception as e:
            logging.error(f"❌ Error con ImportProductsRequest: {e}")
        
        # Explorar estructuras de la API para encontrar InputConfig
        logging.info("Explorando estructuras de API disponibles...")
        modules = [
            'google.cloud.retail_v2.types',
            'google.cloud.retail_v2.types.import_config',
            'google.cloud.retail_v2.types.catalog',
            'google.cloud.retail_v2.types.common'
        ]
        
        for module_name in modules:
            try:
                module = __import__(module_name, fromlist=[''])
                classes = [c for c in dir(module) if not c.startswith('_')]
                logging.info(f"Clases en {module_name}: {classes[:5]}...")
            except ImportError:
                logging.warning(f"No se pudo importar {module_name}")
                
        return True
            
    except Exception as e:
        logging.error(f"Error general en test_imports: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
