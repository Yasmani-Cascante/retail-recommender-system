#!/usr/bin/env python3
"""
🔍 DIAGNÓSTICO COMPLETO DE CONEXIÓN SHOPIFY
===========================================

Este script diagnostica paso a paso por qué la conexión con Shopify está fallando.
Ejecutar desde la raíz del proyecto: python diagnostic_shopify_connection.py
"""

import os
import sys
import logging
import traceback
import requests
from pathlib import Path

# Configurar logging detallado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def print_section(title):
    """Imprimir sección con formato"""
    print(f"\n{'='*60}")
    print(f"🔍 {title}")
    print('='*60)

def test_env_loading():
    """Test 1: Verificar carga de variables de entorno"""
    print_section("TEST 1: CARGA DE VARIABLES DE ENTORNO")
    
    try:
        # Intentar cargar .env
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ dotenv cargado exitosamente")
    except ImportError:
        print("⚠️ python-dotenv no disponible, usando variables del sistema")
    except Exception as e:
        print(f"❌ Error cargando .env: {e}")
    
    # Verificar variables específicas
    shop_url = os.getenv("SHOPIFY_SHOP_URL")
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    
    print(f"SHOPIFY_SHOP_URL: {shop_url}")
    print(f"SHOPIFY_ACCESS_TOKEN: {access_token[:10] + '...' if access_token else 'No encontrada'}")
    
    if shop_url and access_token:
        print("✅ Variables de entorno encontradas")
        return shop_url, access_token
    else:
        print("❌ Variables de entorno faltantes")
        return None, None

def test_imports():
    """Test 2: Verificar imports de módulos"""
    print_section("TEST 2: VERIFICACIÓN DE IMPORTS")
    
    try:
        # Test import del módulo store
        print("Importando src.api.core.store...")
        from src.api.core.store import init_shopify, get_shopify_client
        print("✅ src.api.core.store importado exitosamente")
        
        # Test import del cliente Shopify
        print("Importando src.api.integrations.shopify_client...")
        from src.api.integrations.shopify_client import ShopifyIntegration
        print("✅ src.api.integrations.shopify_client importado exitosamente")
        
        return True
    except Exception as e:
        print(f"❌ Error en imports: {e}")
        traceback.print_exc()
        return False

def test_shopify_client_creation(shop_url, access_token):
    """Test 3: Verificar creación del cliente Shopify"""
    print_section("TEST 3: CREACIÓN DEL CLIENTE SHOPIFY")
    
    try:
        from src.api.integrations.shopify_client import ShopifyIntegration
        
        print(f"Creando cliente con:")
        print(f"  - Shop URL: {shop_url}")
        print(f"  - Access Token: {access_token[:10]}...")
        
        client = ShopifyIntegration(shop_url=shop_url, access_token=access_token)
        print("✅ Cliente Shopify creado exitosamente")
        print(f"  - API URL: {client.api_url}")
        print(f"  - Headers configurados: {list(client.headers.keys())}")
        
        return client
    except Exception as e:
        print(f"❌ Error creando cliente: {e}")
        traceback.print_exc()
        return None

def test_http_connectivity(client):
    """Test 4: Verificar conectividad HTTP directa"""
    print_section("TEST 4: CONECTIVIDAD HTTP DIRECTA")
    
    if not client:
        print("❌ No hay cliente para probar")
        return False
    
    try:
        # Test básico de conectividad con requests
        test_url = f"{client.api_url}/shop.json"
        print(f"Probando conectividad a: {test_url}")
        
        response = requests.get(test_url, headers=client.headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        print(f"Status Text: {response.reason}")
        
        if response.status_code == 200:
            print("✅ Conectividad HTTP exitosa")
            shop_data = response.json()
            print(f"  - Tienda: {shop_data.get('shop', {}).get('name', 'N/A')}")
            print(f"  - Dominio: {shop_data.get('shop', {}).get('domain', 'N/A')}")
            return True
        elif response.status_code == 401:
            print("❌ Error de autenticación - Token inválido o expirado")
            return False
        elif response.status_code == 403:
            print("❌ Error de permisos - Token no tiene permisos necesarios")
            return False
        else:
            print(f"❌ Error HTTP: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Error: Timeout de conexión")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Error: No se puede conectar al servidor")
        return False
    except Exception as e:
        print(f"❌ Error de conectividad: {e}")
        traceback.print_exc()
        return False

def test_product_fetch(client):
    """Test 5: Verificar obtención de productos"""
    print_section("TEST 5: OBTENCIÓN DE PRODUCTOS")
    
    if not client:
        print("❌ No hay cliente para probar")
        return False
    
    try:
        print("Intentando obtener productos...")
        products = client.get_products()
        
        if products:
            print(f"✅ Productos obtenidos exitosamente: {len(products)}")
            if len(products) > 0:
                sample = products[0]
                print(f"  - Primer producto: {sample.get('title', 'Sin título')}")
                print(f"  - ID: {sample.get('id', 'Sin ID')}")
                print(f"  - Precio: {sample.get('variants', [{}])[0].get('price', 'Sin precio') if sample.get('variants') else 'Sin variantes'}")
            return True
        else:
            print("⚠️ No se encontraron productos (lista vacía)")
            return False
            
    except Exception as e:
        print(f"❌ Error obteniendo productos: {e}")
        traceback.print_exc()
        return False

def test_store_module():
    """Test 6: Verificar funciones del módulo store"""
    print_section("TEST 6: FUNCIONES DEL MÓDULO STORE")
    
    try:
        from src.api.core.store import init_shopify, get_shopify_client
        
        print("Probando init_shopify()...")
        client1 = init_shopify()
        
        if client1:
            print("✅ init_shopify() exitoso")
        else:
            print("❌ init_shopify() retornó None")
        
        print("Probando get_shopify_client()...")
        client2 = get_shopify_client()
        
        if client2:
            print("✅ get_shopify_client() exitoso")
            return client2
        else:
            print("❌ get_shopify_client() retornó None")
            return None
            
    except Exception as e:
        print(f"❌ Error en funciones store: {e}")
        traceback.print_exc()
        return None

def main():
    """Función principal de diagnóstico"""
    print("🔍 INICIANDO DIAGNÓSTICO COMPLETO DE SHOPIFY")
    print(f"Python: {sys.version}")
    print(f"Working Directory: {os.getcwd()}")
    
    # Test 1: Variables de entorno
    shop_url, access_token = test_env_loading()
    if not shop_url or not access_token:
        print("\n❌ DIAGNÓSTICO TERMINADO: Faltan variables de entorno")
        return
    
    # Test 2: Imports
    if not test_imports():
        print("\n❌ DIAGNÓSTICO TERMINADO: Error en imports")
        return
    
    # Test 3: Creación de cliente
    client = test_shopify_client_creation(shop_url, access_token)
    
    # Test 4: Conectividad HTTP
    http_success = test_http_connectivity(client)
    
    # Test 5: Obtención de productos (solo si HTTP funciona)
    if http_success and client:
        product_success = test_product_fetch(client)
    else:
        product_success = False
    
    # Test 6: Funciones del módulo store
    store_client = test_store_module()
    
    # Resumen final
    print_section("RESUMEN FINAL")
    print(f"✅ Variables de entorno: {'OK' if shop_url and access_token else 'FAIL'}")
    print(f"✅ Imports de módulos: {'OK' if client else 'FAIL'}")
    print(f"✅ Creación de cliente: {'OK' if client else 'FAIL'}")
    print(f"✅ Conectividad HTTP: {'OK' if http_success else 'FAIL'}")
    print(f"✅ Obtención de productos: {'OK' if product_success else 'FAIL'}")
    print(f"✅ Funciones store: {'OK' if store_client else 'FAIL'}")
    
    if product_success and store_client:
        print("\n🎉 ¡TODOS LOS TESTS EXITOSOS!")
        print("La integración con Shopify está funcionando correctamente.")
    else:
        print("\n⚠️ ALGUNOS TESTS FALLARON")
        print("Revisar los errores específicos arriba para solucionar.")

if __name__ == "__main__":
    main()