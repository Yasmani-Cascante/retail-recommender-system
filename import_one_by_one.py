"""
Script para importar productos uno por uno en lugar de en lotes
Esta alternativa es más lenta pero puede ser más confiable
"""
import os
import asyncio
import logging
import time
from dotenv import load_dotenv
from google.cloud import retail_v2
from google.cloud.retail_v2.types import Product, ImportProductsRequest
from google.cloud.retail_v2.types.import_config import ProductInputConfig, ProductInlineSource
from src.api.core.store import init_shopify, get_shopify_client
from src.api.core.sample_data import SAMPLE_PRODUCTS
from src.recommenders.retail_api import RetailAPIRecommender

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("one_by_one_import.log")
    ]
)

def convert_product_to_retail(product):
    """
    Convierte un producto de Shopify al formato de Google Retail API
    """
    try:
        product_id = str(product.get("id", ""))
        title = product.get("title", "")
        
        # Limpiar HTML de la descripción
        description = product.get("body_html", "")
        if description:
            # Eliminar etiquetas HTML comunes
            for tag in ["<p>", "</p>", "<br>", "<ul>", "</ul>", "<li>", "</li>", "<span>", "</span>", "<strong>", "</strong>"]:
                description = description.replace(tag, " ")
            # Eliminar atributos HTML
            import re
            description = re.sub(r'\s+', ' ', description).strip()
        
        # Extracción de precio del primer variante si existe
        price = 0.0
        if product.get("variants") and len(product["variants"]) > 0:
            price_str = product["variants"][0].get("price", "0")
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                price = 0.0
        
        # Categoría del producto
        category = product.get("product_type", "")
        
        # Asegurar que el ID sea válido
        if not product_id:
            logging.warning(f"Producto sin ID válido: {title}")
            return None
        
        # Construcción del objeto Product con valores mínimos requeridos
        retail_product = Product(
            id=product_id,
            title=title,
            availability="IN_STOCK"
        )
        
        # Agregar campos opcionales solo si tienen valores
        if description:
            retail_product.description = description
            
        if price > 0:
            retail_product.price_info = retail_v2.PriceInfo(
                price=price,
                original_price=price,
                currency_code="COP"
            )
            
        if category:
            retail_product.categories = [category]
        
        return retail_product
            
    except Exception as e:
        logging.error(f"Error al convertir producto {product.get('id', 'unknown')}: {str(e)}")
        return None

async def import_single_product(product_client, parent, retail_product, index, total):
    """
    Importa un solo producto al catálogo
    """
    try:
        logging.info(f"Importando producto {index}/{total}: {retail_product.id} - {retail_product.title}")
        
        # Crear objeto ProductInlineSource con un solo producto
        product_inline_source = ProductInlineSource(products=[retail_product])
        
        # Crear InputConfig
        input_config = ProductInputConfig(
            product_inline_source=product_inline_source
        )
        
        # Crear solicitud
        import_request = ImportProductsRequest(
            parent=parent,
            input_config=input_config,
            reconciliation_mode=retail_v2.types.ImportProductsRequest.ReconciliationMode.INCREMENTAL
        )
        
        # Ejecutar la operación
        operation = product_client.import_products(request=import_request)
        
        # Registrar ID de operación
        operation_id = "desconocido"
        if hasattr(operation, 'operation') and hasattr(operation.operation, 'name'):
            operation_id = operation.operation.name
            logging.info(f"Operación iniciada: {operation_id}")
        
        # No esperamos a que termine la operación, continuamos con el siguiente producto
        logging.info(f"Producto {index}/{total} en proceso de importación")
        return True
        
    except Exception as e:
        logging.error(f"Error al importar producto {index}/{total}: {str(e)}")
        return False

async def one_by_one_import():
    """
    Importa productos uno por uno al catálogo
    """
    # Cargar variables de entorno
    load_dotenv()
    
    # Obtener configuración
    project_number = os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    catalog = os.getenv("GOOGLE_CLOUD_RETAIL_CATALOG", "default_catalog")
    
    logging.info(f"Configuración:")
    logging.info(f"- Project Number: {project_number}")
    logging.info(f"- Location: {location}")
    logging.info(f"- Catalog: {catalog}")
    
    # Inicializar cliente
    product_client = retail_v2.ProductServiceClient()
    
    # Construir la ruta del catálogo - usando branch '0' (Default)
    parent = f"projects/{project_number}/locations/{location}/catalogs/{catalog}/branches/0"
    
    # Inicializar cliente de Shopify
    client = init_shopify()
    
    # Obtener productos
    if not client:
        logging.warning("⚠️ Shopify credentials not found. Using sample data.")
        products = SAMPLE_PRODUCTS
    else:
        try:
            products = client.get_products()
            logging.info(f"✅ Retrieved {len(products)} products from Shopify")
        except Exception as e:
            logging.error(f"❌ Error connecting to Shopify: {str(e)}")
            products = SAMPLE_PRODUCTS
    
    # Convertir productos al formato de Google Retail API
    retail_products = []
    skipped_products = 0
    
    for product in products:
        try:
            retail_product = convert_product_to_retail(product)
            if retail_product:
                retail_products.append(retail_product)
            else:
                skipped_products += 1
        except Exception as e:
            logging.error(f"Error al convertir producto {product.get('id', 'unknown')}: {str(e)}")
            skipped_products += 1
    
    logging.info(f"Se convirtieron {len(retail_products)} productos correctamente (ignorados: {skipped_products})")
    
    # Importar productos uno por uno
    success_count = 0
    for i, retail_product in enumerate(retail_products):
        result = await import_single_product(
            product_client=product_client,
            parent=parent,
            retail_product=retail_product,
            index=i+1,
            total=len(retail_products)
        )
        
        if result:
            success_count += 1
        
        # Pequeña pausa entre productos para no sobrecargar la API
        await asyncio.sleep(2)
    
    # Resultado final
    logging.info(f"Proceso completado:")
    logging.info(f"- Productos totales: {len(retail_products)}")
    logging.info(f"- Productos procesados: {success_count}")
    logging.info(f"- Productos ignorados inicialmente: {skipped_products}")
    
    return {
        "status": "success" if success_count > 0 else "error",
        "total_products": len(products),
        "products_converted": len(retail_products),
        "products_imported": success_count,
        "skipped_products": skipped_products
    }

if __name__ == "__main__":
    asyncio.run(one_by_one_import())
