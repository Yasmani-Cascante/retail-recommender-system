"""
Script para importar productos a Google Retail API usando la estructura correcta
"""
import asyncio
import os
import logging
from dotenv import load_dotenv
from src.api.core.store import init_shopify
from google.cloud import retail_v2

# Configurar logging detallado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("import_log.txt")
    ]
)

# Función para convertir un producto de Shopify al formato de Google Retail API
def convert_product(product):
    try:
        # Extracción segura de datos con valores predeterminados
        product_id = str(product.get("id", ""))
        title = product.get("title", "")
        
        # Asegurar que el ID sea válido
        if not product_id:
            logging.warning(f"Producto sin ID válido: {title}")
            return None
        
        # Construcción del objeto Product con valores mínimos requeridos
        retail_product = retail_v2.Product(
            id=product_id,
            title=title,
            availability="IN_STOCK"
        )
        
        return retail_product
        
    except Exception as e:
        logging.error(f"Error al convertir producto {product.get('id', 'unknown')}: {str(e)}")
        return None

async def main():
    # Cargar variables de entorno
    load_dotenv(override=True)
    
    # Establecer variables explícitamente
    os.environ["GOOGLE_LOCATION"] = "global"
    os.environ["GOOGLE_CATALOG"] = "default_catalog"
    
    # Mostrar configuración
    project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
    location = os.getenv("GOOGLE_LOCATION")
    catalog = os.getenv("GOOGLE_CATALOG")
    
    logging.info(f"Configuración actual:")
    logging.info(f"- GOOGLE_PROJECT_NUMBER: {project_number}")
    logging.info(f"- GOOGLE_LOCATION: {location}")
    logging.info(f"- GOOGLE_CATALOG: {catalog}")
    
    # Inicializar cliente de Retail API
    product_client = retail_v2.ProductServiceClient()
    
    # Obtener productos de Shopify
    client = init_shopify()
    products = []
    
    if client:
        logging.info("Cliente Shopify inicializado correctamente")
        try:
            products = client.get_products()
            logging.info(f"Obtenidos {len(products)} productos de Shopify")
        except Exception as e:
            logging.error(f"Error al obtener productos de Shopify: {str(e)}")
    
    if not products:
        # Usar datos de muestra
        logging.info("Usando datos de muestra...")
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        products = SAMPLE_PRODUCTS
    
    # Convertir productos
    retail_products = []
    for product in products[:5]:  # Solo importar los primeros 5 para prueba
        retail_product = convert_product(product)
        if retail_product:
            retail_products.append(retail_product)
    
    logging.info(f"Se convirtieron {len(retail_products)} productos")
    
    # Construir la ruta del catálogo
    parent = f"projects/{project_number}/locations/{location}/catalogs/{catalog}/branches/default_branch"
    
    # Estructura de la solicitud segun la última versión de la API
    product_inline_source = retail_v2.ProductInlineSource(products=retail_products)
    input_config = retail_v2.ImportProductsInputConfig(product_inline_source=product_inline_source)
    
    try:
        # Importar productos
        logging.info(f"Importando productos a: {parent}")
        
        import_request = retail_v2.ImportProductsRequest(
            parent=parent,
            input_config=input_config,
            reconciliation_mode=retail_v2.ImportProductsRequest.ReconciliationMode.INCREMENTAL
        )
        
        operation = product_client.import_products(request=import_request)
        result = operation.result()
        
        logging.info(f"Importación exitosa: {result}")
        return True
        
    except Exception as e:
        logging.error(f"Error al importar productos: {str(e)}")
        return False

if __name__ == "__main__":
    asyncio.run(main())
