"""
Script para probar la importación de un lote pequeño de productos al catálogo
"""
import os
import asyncio
import logging
from dotenv import load_dotenv
from src.recommenders.retail_api import RetailAPIRecommender
from src.api.core.sample_data import SAMPLE_PRODUCTS

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_small_import():
    """Prueba la importación de un pequeño lote de productos"""
    # Cargar variables de entorno
    load_dotenv()
    
    # Obtener configuración
    project_number = os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    catalog = os.getenv("GOOGLE_CLOUD_RETAIL_CATALOG", "default_catalog")
    serving_config = os.getenv("GOOGLE_CLOUD_RETAIL_SERVING_CONFIG", "default_recommendation_config")
    
    logging.info(f"Configuración:")
    logging.info(f"- Project Number: {project_number}")
    logging.info(f"- Location: {location}")
    logging.info(f"- Catalog: {catalog}")
    logging.info(f"- Serving Config: {serving_config}")
    
    # Crear recomendador de Retail API
    retail_recommender = RetailAPIRecommender(
        project_number=project_number,
        location=location,
        catalog=catalog,
        serving_config_id=serving_config
    )
    
    # Tomar solo 5 productos para la prueba
    test_products = SAMPLE_PRODUCTS[:5]
    logging.info(f"Probando importación con {len(test_products)} productos de muestra")
    
    # Importar productos
    result = await retail_recommender.import_catalog(test_products)
    
    logging.info(f"Resultado de la importación:")
    for key, value in result.items():
        logging.info(f"- {key}: {value}")
    
    return result

if __name__ == "__main__":
    asyncio.run(test_small_import())
