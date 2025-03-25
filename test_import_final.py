"""
Versión final para importar productos a Google Retail API
basada en la estructura real de la API versión 1.24.0
"""
import asyncio
import os
import logging
from dotenv import load_dotenv
from src.api.core.store import init_shopify
from google.cloud import retail_v2
from google.cloud.retail_v2.types.import_config import ProductInputConfig, ProductInlineSource
from google.cloud.retail_v2.types import ImportProductsRequest

# import google.cloud.retail_v2.types
# print(dir(google.cloud.retail_v2.types))

# Configurar logging detallado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("import_final_log.txt")
    ]
)

async def import_products(products):
    try:
        # Configuración
        project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
        location = "global"
        catalog = "default_catalog"
        
        # Inicializar cliente
        product_client = retail_v2.ProductServiceClient()
        
        # Construir la ruta del catálogo
        parent = f"projects/{project_number}/locations/{location}/catalogs/{catalog}/branches/default_branch"
        
        logging.info(f"Importando {len(products)} productos a: {parent}")
        
        # Convertir productos al formato de Google Retail API
        retail_products = []
        for product in products:
            try:
                # Extraer datos básicos
                product_id = str(product.get("id", ""))
                title = product.get("title", "")

                # Obtener categorías desde Shopify o asignar una por defecto
                categories = product.get("product_type", "")
                
                 # Si no hay categorías, asignar una por defecto o omitir el producto
                if not categories:
                    logging.warning(f"Producto {product_id} sin categorías. Se omite.")
                    continue  # O usar: categories = ["default"]

                # Verificar ID válido
                if not product_id:
                    logging.warning(f"Producto sin ID válido: {title}")
                    continue
                
                # Crear producto de Google Retail
                retail_product = retail_v2.Product(
                    id=product_id,
                    title=title,
                    categories=categories,
                    availability="IN_STOCK"
                )
                
                # Agregar a la lista
                retail_products.append(retail_product)
                
            except Exception as e:
                logging.error(f"Error al convertir producto {product.get('id', 'unknown')}: {str(e)}")
                continue
        
        logging.info(f"Se convirtieron {len(retail_products)} productos correctamente")
        
        # Importar en lotes
        batch_size = 100
        batches = [retail_products[i:i+batch_size] for i in range(0, len(retail_products), batch_size)]
        
        success_count = 0
        for i, batch in enumerate(batches):
            try:
                logging.info(f"Importando lote {i+1}/{len(batches)} ({len(batch)} productos)...")
                
                # Crear producto_inline_source
                product_inline_source = ProductInlineSource(products=batch)
                
                # Usar el método correcto para crear import_config
                import_config = ProductInputConfig(
                    product_inline_source=product_inline_source
                )
                
                # Crear la solicitud de importación
                import_request = ImportProductsRequest(
                    parent=parent,
                    input_config=import_config,
                    reconciliation_mode=retail_v2.types.ImportProductsRequest.ReconciliationMode.INCREMENTAL
                )
                
                # Ejecutar la operación
                operation = product_client.import_products(request=import_request)
                result = operation.result(300)  # Esperar hasta 5 minutos
                
                logging.info(f"Lote {i+1} importado correctamente: {result}")
                success_count += len(batch)
                
            except Exception as e:
                logging.error(f"Error al importar lote {i+1}: {str(e)}")
                import traceback
                logging.error(traceback.format_exc())
        
        return {
            "status": "success" if success_count > 0 else "error",
            "products_imported": success_count,
            "total_products": len(products)
        }
    
    except Exception as e:
        logging.error(f"Error general en importación: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return {"status": "error", "error": str(e)}

async def main():
    # Cargar variables de entorno
    load_dotenv(override=True)
    
    # Forzar variables
    os.environ["GOOGLE_LOCATION"] = "global"
    os.environ["GOOGLE_CATALOG"] = "default_catalog"
    
    # Obtener productos de Shopify
    client = init_shopify()
    if client:
        logging.info("Cliente Shopify inicializado correctamente")
        products = client.get_products()
        logging.info(f"Obtenidos {len(products)} productos de Shopify")
        
        # Importar productos
        result = await import_products(products)
        logging.info(f"Resultado de importación: {result}")
        return result
    else:
        logging.error("No se pudo inicializar el cliente Shopify")
        return {"status": "error", "error": "No se pudo inicializar Shopify"}

if __name__ == "__main__":
    asyncio.run(main())
