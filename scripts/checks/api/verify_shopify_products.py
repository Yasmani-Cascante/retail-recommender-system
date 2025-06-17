#!/usr/bin/env python3
"""
Script para verificar el número de productos en Shopify y comprobar que podemos obtenerlos todos.
Este script ayuda a diagnosticar problemas de paginación en la integración con Shopify.
"""

import os
import sys
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

def verify_shopify_products():
    """Verifica el número de productos en Shopify y compara con los obtenidos."""
    try:
        # Obtener variables de configuración
        shopify_url = os.getenv("SHOPIFY_SHOP_URL")
        shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        
        if not all([shopify_url, shopify_token]):
            print("❌ Error: Faltan variables de entorno requeridas")
            print("   Verifica las variables SHOPIFY_SHOP_URL, SHOPIFY_ACCESS_TOKEN")
            return 1
        
        # Inicializar cliente de Shopify
        print("🔄 Inicializando cliente de Shopify...")
        shopify_client = ShopifyIntegration(
            shop_url=shopify_url,
            access_token=shopify_token
        )
        
        # Obtener el número total de productos
        print("🔄 Obteniendo el número total de productos...")
        product_count = shopify_client.get_product_count()
        print(f"ℹ️ La tienda tiene un total de {product_count} productos")
        
        # Obtener productos con la implementación corregida
        print("\n🔄 Obteniendo productos con la implementación corregida...")
        products = shopify_client.get_products()
        print(f"ℹ️ Obtenidos {len(products)} productos de {product_count} totales")
        
        # Verificar si obtuvimos todos los productos
        if len(products) < product_count:
            percentage = (len(products) / product_count) * 100
            print(f"⚠️ Solo estamos obteniendo el {percentage:.1f}% de los productos")
            print(f"   Faltantes: {product_count - len(products)} productos")
        else:
            print("✅ Estamos obteniendo todos los productos correctamente")
            
        # Mostrar algunos productos como muestra
        if products:
            print("\nℹ️ Muestra de productos obtenidos (primeros 5):")
            for i, product in enumerate(products[:5]):
                print(f"   {i+1}. ID: {product.get('id')}, Título: {product.get('title')}")
            
            if len(products) > 5:
                print(f"   ... y {len(products) - 5} productos más")
            
        return 0
            
    except Exception as e:
        print(f"❌ Error durante la verificación: {e}")
        return 1

if __name__ == "__main__":
    print("\n=== VERIFICACIÓN DE PRODUCTOS DE SHOPIFY ===\n")
    exit_code = verify_shopify_products()
    print("\n=== VERIFICACIÓN COMPLETADA ===\n")
    sys.exit(exit_code)
