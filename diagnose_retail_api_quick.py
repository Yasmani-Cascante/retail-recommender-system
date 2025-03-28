"""
Script para diagnosticar rápidamente problemas con Google Cloud Retail API
"""
import os
import logging
from dotenv import load_dotenv
from google.cloud import retail_v2

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def quick_diagnose():
    """Realiza un diagnóstico rápido de la configuración de Google Cloud Retail API"""
    # Cargar variables de entorno
    load_dotenv()
    
    # Obtener configuración
    project_number = os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    catalog = os.getenv("GOOGLE_CLOUD_RETAIL_CATALOG", "default_catalog")
    
    logging.info(f"Configuración actual:")
    logging.info(f"- Project Number: {project_number}")
    logging.info(f"- Location: {location}")
    logging.info(f"- Catalog: {catalog}")
    
    # Verificar versión de la biblioteca
    try:
        import pkg_resources
        retail_version = pkg_resources.get_distribution("google-cloud-retail").version
        logging.info(f"Versión de google-cloud-retail: {retail_version}")
    except Exception as e:
        logging.error(f"Error al verificar versión: {str(e)}")
    
    # Verificar credenciales
    try:
        logging.info("Verificando clientes de Retail API...")
        
        # Intentar crear clientes
        product_client = retail_v2.ProductServiceClient()
        
        # Verificar catálogo
        branch_path = f"projects/{project_number}/locations/{location}/catalogs/{catalog}/branches/default_branch"
        logging.info(f"Verificando catálogo: {branch_path}")
        
        # Intentar listar productos (limitado a 1)
        try:
            request = retail_v2.ListProductsRequest(parent=branch_path, page_size=1)
            products = list(product_client.list_products(request=request))
            if products:
                logging.info(f"✅ Se encontraron productos en el catálogo")
                logging.info(f"Ejemplo: {products[0].id} - {products[0].title}")
            else:
                logging.warning("⚠️ No se encontraron productos en el catálogo")
        except Exception as e:
            logging.error(f"❌ Error al listar productos: {str(e)}")
    
    except Exception as e:
        logging.error(f"Error general: {str(e)}")

if __name__ == "__main__":
    quick_diagnose()
