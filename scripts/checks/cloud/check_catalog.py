"""
Script para verificar los productos en el catálogo de Google Retail API
"""
import os
import logging
from dotenv import load_dotenv
from google.cloud import retail_v2

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("catalog_check.txt")
    ]
)

def main():
    # Cargar variables de entorno
    load_dotenv(override=True)
    
    # Obtener configuración
    project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
    location = "global"  # Forzar ubicación global
    catalog = "default_catalog"  # Forzar catálogo predeterminado
    
    # Crear cliente
    client = retail_v2.ProductServiceClient()
    
    # Construir la ruta del catálogo
    parent = f"projects/{project_number}/locations/{location}/catalogs/{catalog}/branches/default_branch"
    
    logging.info(f"Verificando productos en: {parent}")
    
    try:
        # Listar productos
        request = retail_v2.ListProductsRequest(
            parent=parent,
            page_size=10  # Limitar a 10 productos para la verificación
        )
        
        try:
            product_iterator = client.list_products(request=request)
            products = list(product_iterator)
            
            if products:
                logging.info(f"Se encontraron {len(products)} productos en el catálogo")
                for i, product in enumerate(products):
                    logging.info(f"Producto {i+1}:")
                    logging.info(f"- ID: {product.id}")
                    logging.info(f"- Nombre: {product.title}")
                    if hasattr(product, 'categories') and product.categories:
                        logging.info(f"- Categorías: {product.categories}")
                    logging.info("---")
            else:
                logging.warning("No se encontraron productos en el catálogo")
                
            return products
            
        except Exception as e:
            logging.error(f"Error al listar productos: {str(e)}")
            
            # Intentar verificar la existencia del catálogo
            try:
                catalog_service = retail_v2.CatalogServiceClient()
                catalog_path = f"projects/{project_number}/locations/{location}/catalogs/{catalog}"
                logging.info(f"Verificando existencia del catálogo: {catalog_path}")
                
                # Listar catálogos para ver si existe
                catalogs_parent = f"projects/{project_number}/locations/{location}"
                catalog_request = retail_v2.ListCatalogsRequest(parent=catalogs_parent)
                catalogs = list(catalog_service.list_catalogs(request=catalog_request))
                
                logging.info(f"Catálogos disponibles: {[c.name for c in catalogs]}")
                return None
            except Exception as catalog_error:
                logging.error(f"Error al verificar catálogos: {str(catalog_error)}")
                return None
            
    except Exception as e:
        logging.error(f"Error al verificar productos: {str(e)}")
        return None

if __name__ == "__main__":
    main()
