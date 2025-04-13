#!/usr/bin/env python3
"""
Script simplificado para probar la corrección del error de 'availability'
"""
import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from src.recommenders.retail_api import RetailAPIRecommender

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cargar variables de entorno
load_dotenv()

# Datos de productos de prueba simplificados
TEST_PRODUCTS = [
    {
        "id": "test_product_1",
        "title": "Producto de Prueba 1",
        "body_html": "Descripción del producto de prueba 1",
        "product_type": "Categoría de Prueba",
        "variants": [{"price": "10.99"}]
    },
    {
        "id": "test_product_2",
        "title": "Producto de Prueba 2",
        "body_html": "Descripción del producto de prueba 2",
        "product_type": "Categoría de Prueba",
        "variants": [{"price": "15.99"}]
    }
]

async def test_import():
    """Prueba la importación de productos después de la corrección."""
    try:
        # Obtener variables de configuración
        project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
        location = os.getenv("GOOGLE_LOCATION", "global")
        catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
        
        if not project_number:
            logging.error("GOOGLE_PROJECT_NUMBER no está configurado en las variables de entorno")
            return {"status": "error", "error": "Configuración incompleta"}
        
        # Crear instancia del recomendador
        retail_recommender = RetailAPIRecommender(
            project_number=project_number,
            location=location,
            catalog=catalog
        )
        
        # Verificar la implementación corriente mediante debug
        # Crear un producto de prueba y verificar su serialización
        logging.info("Analizando la implementación actual...")
        
        # Convertir un producto para examinar los detalles
        retail_product = retail_recommender._convert_product_to_retail(TEST_PRODUCTS[0])
        
        if retail_product:
            logging.info(f"Product ID: {retail_product.id}")
            logging.info(f"Availability value: {retail_product.availability}")
            logging.info(f"Availability type: {type(retail_product.availability)}")
            logging.info(f"Availability str: {str(retail_product.availability)}")
            
            # Intentar simular la serialización
            retail_product_dict = {
                "id": retail_product.id,
                "title": retail_product.title,
                "availability": "IN_STOCK",  # VALOR CORREGIDO MANUALMENTE
                "categories": list(retail_product.categories) if hasattr(retail_product, 'categories') else ["General"]
            }
            
            # Mostrar la versión serializada
            logging.info(f"Product dict (serialized): {json.dumps(retail_product_dict)}")
        
        # Forzar el uso de GCS para la prueba
        os.environ["USE_GCS_IMPORT"] = "true"
        
        # Iniciar la importación
        logging.info("Iniciando importación de prueba...")
        result = await retail_recommender.import_catalog(TEST_PRODUCTS)
        
        # Mostrar resultado
        logging.info(f"Resultado de importación: {result}")
        
        if result.get("status") == "success":
            logging.info("✅ Prueba exitosa. La corrección ha funcionado.")
        else:
            logging.warning("❌ La prueba falló. Revisa los errores.")
        
        return result
        
    except Exception as e:
        logging.error(f"Error durante la prueba: {e}")
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    asyncio.run(test_import())
