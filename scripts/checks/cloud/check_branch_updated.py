"""
Script actualizado para verificar la estructura del catálogo y la rama "0" en Retail API
"""
import os
import logging
from dotenv import load_dotenv
from google.cloud import retail_v2

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def check_catalog_structure():
    """Verifica la estructura del catálogo y las ramas disponibles"""
    # Cargar variables de entorno
    load_dotenv()
    
    # Obtener configuración
    project_number = os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    catalog = os.getenv("GOOGLE_CLOUD_RETAIL_CATALOG", "default_catalog")
    
    logging.info(f"Verificando catálogo:")
    logging.info(f"- Project Number: {project_number}")
    logging.info(f"- Location: {location}")
    logging.info(f"- Catalog: {catalog}")
    
    try:
        # Crear cliente para el servicio de catálogos
        catalog_client = retail_v2.CatalogServiceClient()
        
        # Construir la ruta del catálogo
        catalog_path = f"projects/{project_number}/locations/{location}/catalogs/{catalog}"
        
        logging.info(f"Verificando existencia del catálogo: {catalog_path}")
        
        # Verificar si el catálogo existe
        try:
            catalog_info = catalog_client.get_catalog(name=catalog_path)
            logging.info(f"✅ Catálogo encontrado: {catalog_info.name}")
            
            # Listar catálogos para ver la estructura completa
            parent = f"projects/{project_number}/locations/{location}"
            catalogs = list(catalog_client.list_catalogs(parent=parent))
            logging.info(f"Catálogos disponibles en {parent}: {len(catalogs)}")
            for cat in catalogs:
                logging.info(f"  - {cat.name}")
        except Exception as e:
            logging.error(f"❌ Error al verificar catálogo: {str(e)}")
        
        # Verificar la rama 0 (podemos usar el servicio de productos para esto)
        product_client = retail_v2.ProductServiceClient()
        branch_0_path = f"{catalog_path}/branches/0"
        logging.info(f"\nVerificando rama '0': {branch_0_path}")
        
        try:
            # Intentar listar productos en la rama 0
            request = retail_v2.ListProductsRequest(
                parent=branch_0_path,
                page_size=1
            )
            products = list(product_client.list_products(request=request))
            if products:
                logging.info(f"✅ Rama '0' existe y contiene productos")
                logging.info(f"  - Ejemplo de producto: ID {products[0].id}, Título: {products[0].title}")
            else:
                logging.info(f"✅ Rama '0' existe pero no contiene productos")
        except Exception as e:
            logging.error(f"❌ Error al acceder a rama '0': {str(e)}")
        
        # Intentar con otras posibles ramas
        for branch_name in ["default_branch", "1", "2"]:
            branch_path = f"{catalog_path}/branches/{branch_name}"
            logging.info(f"\nVerificando rama '{branch_name}': {branch_path}")
            
            try:
                # Intentar listar productos en esta rama
                request = retail_v2.ListProductsRequest(
                    parent=branch_path,
                    page_size=1
                )
                products = list(product_client.list_products(request=request))
                if products:
                    logging.info(f"✅ Rama '{branch_name}' existe y contiene productos")
                else:
                    logging.info(f"✅ Rama '{branch_name}' existe pero no contiene productos")
            except Exception as e:
                logging.error(f"❌ Error al acceder a rama '{branch_name}': {str(e)}")
    
    except Exception as e:
        logging.error(f"Error general: {str(e)}")

if __name__ == "__main__":
    check_catalog_structure()
