"""
Script de depuración para corregir problemas del catálogo en Google Cloud Retail API.
Esta versión incluye más información de depuración y manejo mejorado de errores.
"""

import os
import asyncio
import logging
import sys
import time
from dotenv import load_dotenv
from google.cloud import retail_v2
from google.api_core import exceptions

# Configurar logging con más detalle y salida a stdout
logging.basicConfig(
    level=logging.DEBUG,  # Cambio a DEBUG para más información
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Forzar salida a stdout
    ]
)
logger = logging.getLogger(__name__)

# Función simple que imprime directamente a stdout para garantizar visibilidad
def print_debug(message):
    print(f"DEBUG: {message}")
    sys.stdout.flush()  # Forzar flush para ver mensajes inmediatamente

async def verify_catalog():
    """
    Verifica la estructura básica del catálogo en Retail API.
    """
    try:
        print_debug("Iniciando verificación del catálogo...")
        
        # Cargar variables de entorno
        load_dotenv()
        
        # Obtener configuración
        project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
        location = os.getenv("GOOGLE_LOCATION", "global")
        catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
        
        if not project_number:
            print_debug("ERROR: No se encontró GOOGLE_PROJECT_NUMBER en las variables de entorno")
            return False
            
        print_debug(f"Configuración: Project={project_number}, Location={location}, Catalog={catalog}")
        
        # Construir rutas
        project_path = f"projects/{project_number}/locations/{location}"
        catalog_path = f"{project_path}/catalogs/{catalog}"
        
        print_debug(f"Inicializando clientes de API...")
        
        # Inicializar clientes
        catalog_client = retail_v2.CatalogServiceClient()
        product_client = retail_v2.ProductServiceClient()
        
        # Intentar inicializar cliente de configuración de serving (puede fallar en algunas versiones)
        try:
            serving_config_client = retail_v2.ServingConfigServiceClient()
            print_debug("Cliente ServingConfigServiceClient inicializado correctamente")
        except (AttributeError, ImportError) as e:
            print_debug(f"ADVERTENCIA: No se pudo inicializar ServingConfigServiceClient: {str(e)}")
            serving_config_client = None
        
        # Verificar catálogo listando todos los catálogos
        print_debug(f"Listando catálogos en {project_path}...")
        try:
            # Primer intento: listar catálogos
            catalogs = list(catalog_client.list_catalogs(parent=project_path))
            print_debug(f"Catálogos encontrados: {len(catalogs)}")
            
            # Verificar si nuestro catálogo está en la lista
            catalog_exists = False
            for catalog_item in catalogs:
                print_debug(f"Catálogo encontrado: {catalog_item.name}")
                if catalog_item.name == catalog_path:
                    catalog_exists = True
                    print_debug(f"✅ Nuestro catálogo encontrado: {catalog_path}")
                    break
                    
            if not catalog_exists:
                print_debug(f"⚠️ Nuestro catálogo no está en la lista, verificando individualmente")
        except Exception as list_error:
            print_debug(f"Error al listar catálogos: {str(list_error)}")
        
        # Verificar ramas listando productos por rama
        for branch_id in ["0", "1", "2", "default_branch"]:
            branch_path = f"{catalog_path}/branches/{branch_id}"
            print_debug(f"Verificando rama '{branch_id}': {branch_path}")
            
            try:
                # Intentar listar productos en la rama
                request = retail_v2.ListProductsRequest(
                    parent=branch_path,
                    page_size=1
                )
                
                # Ejecutar la solicitud con timeout
                print_debug(f"Ejecutando list_products en rama '{branch_id}'...")
                start_time = time.time()
                products = list(product_client.list_products(request=request))
                elapsed_time = time.time() - start_time
                
                # Verificar resultado
                print_debug(f"Solicitud completada en {elapsed_time:.2f} segundos")
                if products:
                    print_debug(f"✅ Rama '{branch_id}' existe y contiene {len(products)} productos")
                    print_debug(f"  - Producto encontrado: {products[0].id} - {products[0].title}")
                else:
                    print_debug(f"✅ Rama '{branch_id}' existe pero no contiene productos")
                    
            except Exception as e:
                print_debug(f"⚠️ Error al verificar rama '{branch_id}': {str(e)}")
        
        # Verificar configuración de serving si el cliente está disponible
        if serving_config_client:
            config_path = f"{catalog_path}/servingConfigs/default_recommendation_config"
            print_debug(f"Verificando configuración de serving: {config_path}")
            
            try:
                # Listar configuraciones
                configs = list(serving_config_client.list_serving_configs(parent=catalog_path))
                print_debug(f"Configuraciones de serving encontradas: {len(configs)}")
                
                for config in configs:
                    print_debug(f"Configuración: {config.name}")
                    
            except Exception as config_error:
                print_debug(f"⚠️ Error al verificar configuraciones de serving: {str(config_error)}")
        
        print_debug("Verificación básica completada")
        return True
        
    except Exception as e:
        print_debug(f"ERROR GENERAL: {str(e)}")
        import traceback
        print_debug(f"Detalles del error: {traceback.format_exc()}")
        return False

def main():
    """Función principal"""
    print_debug("Iniciando script de diagnóstico...")
    
    # Crear un nuevo event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Ejecutar verificación
        result = loop.run_until_complete(verify_catalog())
        # Cerrar el loop
        loop.close()
        
        if result:
            print_debug("✅ Verificación completada con éxito")
        else:
            print_debug("❌ Verificación completada con errores")
            
        return result
    except Exception as e:
        print_debug(f"ERROR EN MAIN: {str(e)}")
        import traceback
        print_debug(f"Detalles del error: {traceback.format_exc()}")
        
        # Intentar cerrar el loop si aún está abierto
        try:
            if loop and loop.is_running():
                loop.close()
        except:
            pass
            
        return False

if __name__ == "__main__":
    print_debug("Ejecutando script como programa principal")
    try:
        success = main()
        print_debug(f"Resultado final: {'Éxito' if success else 'Error'}")
    except Exception as final_error:
        print_debug(f"ERROR CRÍTICO: {str(final_error)}")
