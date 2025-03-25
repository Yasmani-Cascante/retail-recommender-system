"""
Script para probar la importación de productos a Google Retail API
"""
import asyncio
import os
import logging
from dotenv import load_dotenv
from src.api.core.store import init_shopify
from src.recommenders.retail_api import RetailAPIRecommender

# Configurar logging detallado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("import_log.txt")
    ]
)

async def main():
    # Cargar variables de entorno
    load_dotenv(override=True)
    
    # Establecer variables explícitamente
    os.environ["GOOGLE_LOCATION"] = "global"
    os.environ["GOOGLE_CATALOG"] = "default_catalog"
    os.environ["GOOGLE_SERVING_CONFIG"] = "default_recommendation_config"
    
    # Mostrar configuración
    project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
    location = os.getenv("GOOGLE_LOCATION")
    catalog = os.getenv("GOOGLE_CATALOG")
    serving_config = os.getenv("GOOGLE_SERVING_CONFIG")
    
    logging.info(f"Configuración actual:")
    logging.info(f"- GOOGLE_PROJECT_NUMBER: {project_number}")
    logging.info(f"- GOOGLE_LOCATION: {location}")
    logging.info(f"- GOOGLE_CATALOG: {catalog}")
    logging.info(f"- GOOGLE_SERVING_CONFIG: {serving_config}")
    
    # Inicializar cliente de Retail API
    retail_recommender = RetailAPIRecommender(
        project_number=project_number,
        location=location,
        catalog=catalog,
        serving_config_id=serving_config
    )
    
    # Obtener productos de Shopify
    client = init_shopify()
    if client:
        logging.info("✅ Cliente Shopify inicializado correctamente")
        try:
            products = client.get_products()
            logging.info(f"✅ Obtenidos {len(products)} productos de Shopify")
            
            if products:
                # Mostrar ejemplo del primer producto
                logging.debug(f"Ejemplo de producto: {products[0]}")
                
                # Intentar importar productos
                logging.info("Importando productos a Google Retail API...")
                result = await retail_recommender.import_catalog(products)
                
                logging.info(f"Resultado de importación: {result}")
                return result
            else:
                logging.error("❌ No se obtuvieron productos de Shopify")
        except Exception as e:
            logging.error(f"❌ Error al obtener productos de Shopify: {str(e)}")
    else:
        logging.error("❌ No se pudo inicializar el cliente Shopify")
        
        # Intentar usar datos de muestra
        logging.info("Usando datos de muestra...")
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        
        logging.info(f"Importando {len(SAMPLE_PRODUCTS)} productos de muestra...")
        result = await retail_recommender.import_catalog(SAMPLE_PRODUCTS)
        
        logging.info(f"Resultado de importación: {result}")
        return result

if __name__ == "__main__":
    asyncio.run(main())
