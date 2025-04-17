#!/usr/bin/env python3
"""
Script para actualizar el catálogo completo de productos desde Shopify a Google Cloud Retail API.
Este script utiliza el cliente de Shopify mejorado que maneja correctamente la paginación.
"""

import os
import asyncio
import logging
from dotenv import load_dotenv
from src.recommenders.retail_api import RetailAPIRecommender
from src.api.integrations.shopify_client import ShopifyIntegration

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cargar variables de entorno
load_dotenv()

async def update_catalog():
    """Actualiza el catálogo completo de productos."""
    try:
        # Obtener variables de configuración
        shopify_url = os.getenv("SHOPIFY_SHOP_URL")
        shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
        location = os.getenv("GOOGLE_LOCATION", "global")
        catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
        branch = "0"  # La rama estándar para productos en Google Retail API
        
        if not all([shopify_url, shopify_token, project_number]):
            logging.error("Faltan variables de entorno requeridas")
            return {
                "status": "error", 
                "error": "Configuración incompleta. Verifica las variables SHOPIFY_SHOP_URL, SHOPIFY_ACCESS_TOKEN, GOOGLE_PROJECT_NUMBER"
            }
        
        # Inicializar cliente de Shopify
        logging.info("Inicializando cliente de Shopify...")
        shopify_client = ShopifyIntegration(
            shop_url=shopify_url,
            access_token=shopify_token
        )
        
        # Obtener el número total de productos
        product_count = shopify_client.get_product_count()
        logging.info(f"La tienda tiene un total de {product_count} productos")
        
        # Obtener todos los productos con paginación
        logging.info("Obteniendo todos los productos de Shopify...")
        all_products = shopify_client.get_products()
        
        logging.info(f"Se obtuvieron {len(all_products)} productos de Shopify")
        
        # Verificar que se obtuvieron todos los productos
        if len(all_products) < product_count:
            logging.warning(
                f"No se obtuvieron todos los productos. "
                f"Obtenidos: {len(all_products)}, Total: {product_count}."
            )
        
        # Inicializar recomendador Retail API
        logging.info("Inicializando cliente de Google Cloud Retail API...")
        retail_recommender = RetailAPIRecommender(
            project_number=project_number,
            location=location,
            catalog=catalog
        )
        
        # Nota: Ignoramos la verificación del CatalogManager ya que no es necesaria
        # La rama 0 se crea automáticamente por Google Cloud Retail API
        
        # Importar productos a Google Cloud Retail API
        logging.info(f"Importando {len(all_products)} productos a Google Cloud Retail API...")
        import_result = await retail_recommender.import_catalog(all_products)
        
        logging.info(f"Resultado de importación: {import_result}")
        
        return {
            "status": "success",
            "products_count": len(all_products),
            "import_result": import_result
        }
        
    except Exception as e:
        logging.error(f"Error durante la actualización del catálogo: {e}")
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    print("\n=== ACTUALIZACIÓN DEL CATÁLOGO DE PRODUCTOS ===\n")
    
    print("Este script obtendrá todos los productos de Shopify y los importará a Google Cloud Retail API.")
    print("El proceso puede tardar varios minutos dependiendo del tamaño del catálogo.")
    print("\nAsegúrate de tener configuradas las siguientes variables de entorno:")
    print("  - SHOPIFY_SHOP_URL")
    print("  - SHOPIFY_ACCESS_TOKEN")
    print("  - GOOGLE_PROJECT_NUMBER")
    print("  - GOOGLE_LOCATION (opcional, por defecto: global)")
    print("  - GOOGLE_CATALOG (opcional, por defecto: default_catalog)")
    
    confirmation = input("\n¿Deseas continuar? (s/n): ")
    if confirmation.lower() != 's':
        print("\nOperación cancelada.")
        exit(0)
    
    print("\nIniciando actualización del catálogo...\n")
    
    # Ejecutar la función de actualización
    result = asyncio.run(update_catalog())
    
    # Mostrar resultado
    if result.get("status") == "success":
        print("\n✅ Actualización del catálogo completada con éxito!")
        print(f"   - Productos importados: {result.get('products_count', 0)}")
        print(f"   - Resultado: {result.get('import_result', {}).get('status', 'unknown')}")
    else:
        print("\n❌ Error durante la actualización del catálogo")
        print(f"   - Error: {result.get('error', 'Desconocido')}")
        
    print("\n=== PROCESO FINALIZADO ===\n")
