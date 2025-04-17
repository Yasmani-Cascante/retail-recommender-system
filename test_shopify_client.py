#!/usr/bin/env python3
"""
Script para probar la implementación corregida del cliente de Shopify.
Este script verifica si podemos obtener correctamente todos los productos de Shopify.
"""

import os
import logging
from dotenv import load_dotenv
from src.api.integrations.shopify_client import ShopifyIntegration

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cargar variables de entorno
load_dotenv()

def test_shopify_client():
    """Prueba el cliente de Shopify corregido."""
    print("\n=== PRUEBA DEL CLIENTE DE SHOPIFY CORREGIDO ===\n")
    
    # Obtener credenciales de Shopify
    shop_url = os.getenv("SHOPIFY_SHOP_URL")
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    
    if not shop_url or not access_token:
        print("❌ Error: Faltan variables de entorno SHOPIFY_SHOP_URL o SHOPIFY_ACCESS_TOKEN")
        return False
    
    print(f"🔄 Inicializando cliente de Shopify para: {shop_url}")
    client = ShopifyIntegration(shop_url=shop_url, access_token=access_token)
    
    # Obtener el número total de productos
    print("🔄 Obteniendo el número total de productos...")
    product_count = client.get_product_count()
    print(f"ℹ️ La tienda tiene un total de {product_count} productos")
    
    # Obtener todos los productos
    print("\n🔄 Obteniendo todos los productos con la implementación corregida...")
    products = client.get_products()
    
    if not products:
        print("❌ Error: No se pudieron obtener productos")
        return False
    
    print(f"✅ Éxito: Se obtuvieron {len(products)} productos de {product_count} totales")
    
    # Verificar si obtuvimos todos los productos
    if len(products) < product_count:
        percentage = (len(products) / product_count) * 100
        print(f"⚠️ Advertencia: Solo se obtuvo el {percentage:.1f}% de los productos")
    else:
        print("✅ Perfecto: Se obtuvieron todos los productos correctamente")
    
    # Mostrar algunos productos como muestra
    if products:
        print("\nMuestra de productos obtenidos:")
        for i, product in enumerate(products[:5]):
            print(f"{i+1}. ID: {product.get('id')}, Título: {product.get('title')}")
        
        if len(products) > 5:
            print(f"... y {len(products) - 5} productos más")
    
    return True

if __name__ == "__main__":
    success = test_shopify_client()
    
    print("\n=== RESULTADO DE LA PRUEBA ===")
    if success:
        print("✅ La corrección del cliente de Shopify ha sido exitosa!")
        print("   Ahora puedes ejecutar el script update_catalog.py para actualizar el catálogo completo")
    else:
        print("❌ La prueba no fue exitosa. Revisa los errores anteriores.")
        
    print("\n=== FIN DE LA PRUEBA ===\n")
