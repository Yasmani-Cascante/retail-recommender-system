"""
Script mejorado para probar la importación de productos a Google Retail API
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
        logging.FileHandler("import_fixed_log.txt")
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
                
                # Verificar ID válido
                if not product_id:
                    logging.warning(f"Producto sin ID válido: {title}")
                    continue
                
                # Crear producto
                retail_product = retail_v2.Product(
                    id=product_id,
                    title=title,
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
                
                # Crear objetos para la importación
                product_inline_source = retail_v2.ProductInlineSource(products=batch)
                input_config = retail_v2.ImportProductsInputConfig(product_inline_source=product_inline_source)
                
                # Crear la solicitud
                import_request = retail_v2.ImportProductsRequest(
                    parent=parent,
                    input_config=input_config,
                    reconciliation_mode="INCREMENTAL"  # Usar string en lugar de enum
                )
                
                # Ejecutar la operación
                operation = product_client.import_products(request=import_request)
                result = operation.result()
                
                logging.info(f"Lote {i+1} importado correctamente: {result}")
                success_count += len(batch)
                
            except Exception as e:
                logging.error(f"Error al importar lote {i+1}: {str(e)}")
        
        return {
            "status": "success" if success_count > 0 else "error",
            "products_imported": success_count,
            "total_products": len(products)
        }
    
    except Exception as e:
        logging.error(f"Error general en importación: {str(e)}")
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
