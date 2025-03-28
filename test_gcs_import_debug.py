#!/usr/bin/env python3
"""
Script para probar la importación de productos vía GCS con depuración adicional.
"""
import os
import json
import asyncio
import logging
import traceback
import tempfile
from dotenv import load_dotenv
from src.recommenders.retail_api import RetailAPIRecommender
from src.api.core.sample_data import SAMPLE_PRODUCTS

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cargar variables de entorno
load_dotenv()

async def test_gcs_import():
    """Prueba la importación de productos vía GCS."""
    try:
        # Mostrar los datos de muestra
        logging.info(f"Muestra de datos de productos:")
        for i, product in enumerate(SAMPLE_PRODUCTS):
            logging.info(f"Producto {i+1}:")
            logging.info(f"- ID: {product.get('id')}")
            logging.info(f"- Nombre/Título: {product.get('name', product.get('title', 'Sin título'))}")
            logging.info(f"- Campos disponibles: {list(product.keys())}")
            logging.info(f"- Categoría: {product.get('category', product.get('product_type', 'Sin categoría'))}")
            # Solo para el primer producto, mostrar todo su contenido
            if i == 0:
                logging.info(f"Datos completos producto 1: {json.dumps(product, indent=2)}")
            logging.info("-" * 40)
            
        # Obtener variables de configuración
        project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
        location = os.getenv("GOOGLE_LOCATION", "global")
        catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
        
        if not project_number:
            raise ValueError("GOOGLE_PROJECT_NUMBER no está configurado")
            
        # Crear instancia del recomendador
        retail_recommender = RetailAPIRecommender(
            project_number=project_number,
            location=location,
            catalog=catalog
        )
        
        # Forzar el uso de GCS independientemente de la configuración
        os.environ["USE_GCS_IMPORT"] = "true"
        
        # Realizar importación
        logging.info("Iniciando prueba de importación vía GCS...")
        result = await retail_recommender.import_catalog(SAMPLE_PRODUCTS)
        
        # Mostrar resultado
        logging.info(f"Resultado de la importación: {result}")
        
        return result
    
    except Exception as e:
        logging.error(f"Error en prueba de importación: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return {"status": "error", "error": str(e)}
        
if __name__ == "__main__":
    asyncio.run(test_gcs_import())
