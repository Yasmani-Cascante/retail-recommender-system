"""
Script actualizado para verificar la configuración de Google Cloud Retail API
Utilizando métodos disponibles en la versión actual de google-cloud-retail
"""
import os
import sys
from google.cloud import retail_v2
from google.api_core.exceptions import NotFound, PermissionDenied, InvalidArgument
import argparse

def list_catalogs(project_number, location):
    """
    Lista todos los catálogos disponibles en el proyecto
    """
    client = retail_v2.CatalogServiceClient()
    
    # Construir la ruta del proyecto
    parent = f"projects/{project_number}/locations/{location}"
    
    print(f"Listando catálogos en: {parent}")
    
    try:
        # Intentar listar los catálogos
        request = retail_v2.ListCatalogsRequest(parent=parent)
        response = client.list_catalogs(request=request)
        
        print("\n✅ CATÁLOGOS ENCONTRADOS:")
        catalogs = list(response)
        
        if not catalogs:
            print("No se encontraron catálogos en este proyecto/ubicación")
            return False, []
            
        for catalog in catalogs:
            print(f"- {catalog.name}")
            
        return True, catalogs
        
    except Exception as e:
        print(f"\n❌ ERROR: No se pudieron listar los catálogos")
        print(f"Detalles del error: {str(e)}")
        return False, []

def verify_catalog_exists(project_number, location, catalog_id):
    """
    Verifica si un catálogo específico existe
    """
    found_catalogs, catalogs = list_catalogs(project_number, location)
    
    if not found_catalogs:
        return False
    
    full_catalog_path = f"projects/{project_number}/locations/{location}/catalogs/{catalog_id}"
    
    for catalog in catalogs:
        if catalog.name == full_catalog_path:
            print(f"\n✅ CATÁLOGO ENCONTRADO: {catalog_id}")
            return True
    
    print(f"\n❌ El catálogo '{catalog_id}' no fue encontrado en esta ubicación")
    return False

def list_serving_configs(project_number, location, catalog_id):
    """
    Lista todas las configuraciones de servicio en un catálogo
    """
    client = retail_v2.ServingConfigServiceClient()
    
    # Construir la ruta del catálogo
    parent = f"projects/{project_number}/locations/{location}/catalogs/{catalog_id}"
    
    print(f"Listando configuraciones en: {parent}")
    
    try:
        # Intentar listar las configuraciones
        request = retail_v2.ListServingConfigsRequest(parent=parent)
        serving_configs = client.list_serving_configs(request=request)
        
        print("\n✅ CONFIGURACIONES ENCONTRADAS:")
        configs = list(serving_configs)
        
        if not configs:
            print("No se encontraron configuraciones en este catálogo")
            return False, []
            
        for config in configs:
            print(f"- {config.name}")
            print(f"  Display Name: {config.display_name}")
            print(f"  Model ID: {config.model_id if hasattr(config, 'model_id') else 'N/A'}")
            print()
            
        return True, configs
        
    except Exception as e:
        print(f"\n❌ ERROR: No se pudieron listar las configuraciones")
        print(f"Detalles del error: {str(e)}")
        return False, []

def verify_serving_config(project_number, location, catalog_id, config_id):
    """
    Verifica si una configuración específica existe
    """
    client = retail_v2.ServingConfigServiceClient()
    
    # Construir la ruta completa de la configuración
    name = f"projects/{project_number}/locations/{location}/catalogs/{catalog_id}/servingConfigs/{config_id}"
    
    print(f"Verificando configuración: {name}")
    
    try:
        # Intentar obtener la configuración
        request = retail_v2.GetServingConfigRequest(name=name)
        config = client.get_serving_config(request=request)
        
        print("\n✅ CONFIGURACIÓN ENCONTRADA:")
        print(f"Nombre: {config.name}")
        print(f"Display Name: {config.display_name}")
        print(f"Model ID: {config.model_id if hasattr(config, 'model_id') else 'N/A'}")
        
        # Mostrar tipos de solución si están disponibles
        if hasattr(config, 'solution_types') and config.solution_types:
            print(f"Tipos de solución: {config.solution_types}")
        
        return True, config
        
    except NotFound:
        print(f"\n❌ La configuración '{config_id}' no fue encontrada")
        return False, None
        
    except Exception as e:
        print(f"\n❌ ERROR: No se pudo verificar la configuración")
        print(f"Detalles del error: {str(e)}")
        return False, None

def create_serving_config(project_number, location, catalog_id, config_id):
    """
    Crea una configuración de servicio
    """
    client = retail_v2.ServingConfigServiceClient()
    
    # Construir la ruta del catálogo
    parent = f"projects/{project_number}/locations/{location}/catalogs/{catalog_id}"
    
    # Crear la configuración
    serving_config = retail_v2.ServingConfig(
        display_name="Default Recommendation Config",
        model_id="default_recommendation",
        price_reranking_level=retail_v2.ServingConfig.PriceRerankingLevel.NO_PRICE_RERANKING,
        diversity_level=retail_v2.ServingConfig.DiversityLevel.MEDIUM_DIVERSITY,
        # Usar enumeración para solution_types si está disponible
        solution_types=[retail_v2.SolutionType.SOLUTION_TYPE_RECOMMENDATION]
        if hasattr(retail_v2, 'SolutionType') else ['recommendation']
    )
    
    print(f"Creando configuración en: {parent}")
    
    try:
        # Intentar crear la configuración
        request = retail_v2.CreateServingConfigRequest(
            parent=parent,
            serving_config=serving_config,
            serving_config_id=config_id
        )
        response = client.create_serving_config(request=request)
        
        print("\n✅ CONFIGURACIÓN CREADA EXITOSAMENTE:")
        print(f"Nombre: {response.name}")
        return True, response
        
    except Exception as e:
        print(f"\n❌ ERROR: No se pudo crear la configuración")
        print(f"Detalles del error: {str(e)}")
        print("\nEsto puede deberse a que:")
        print("1. La configuración ya existe")
        print("2. No tienes permisos suficientes")
        print("3. El catálogo no existe")
        return False, None

def main():
    parser = argparse.ArgumentParser(description='Verificar configuración de Google Cloud Retail API')
    parser.add_argument('--project', type=str, default=os.getenv('GOOGLE_PROJECT_NUMBER', '178362262166'),
                        help='Número del proyecto de Google Cloud')
    parser.add_argument('--location', type=str, default=os.getenv('GOOGLE_LOCATION', 'us-central1'),
                        help='Ubicación de Google Cloud (default: us-central1)')
    parser.add_argument('--catalog', type=str, default=os.getenv('GOOGLE_CATALOG', 'retail_178362262166'),
                        help='ID del catálogo')
    parser.add_argument('--config-id', type=str, default=os.getenv('GOOGLE_SERVING_CONFIG', 'default_recommendation_config'),
                        help='ID de la configuración de servicio')
    parser.add_argument('--list-catalogs', action='store_true',
                        help='Listar todos los catálogos disponibles')
    parser.add_argument('--list-configs', action='store_true',
                        help='Listar todas las configuraciones disponibles')
    parser.add_argument('--create', action='store_true',
                        help='Crear la configuración si no existe')
    
    args = parser.parse_args()
    
    # Listar catálogos si se solicita
    if args.list_catalogs:
        list_catalogs(args.project, args.location)
        return
    
    # Verificar si el catálogo existe
    catalog_exists = verify_catalog_exists(args.project, args.location, args.catalog)
    
    if not catalog_exists:
        print("\n⚠️ No se puede continuar sin un catálogo válido")
        sys.exit(1)
    
    # Listar configuraciones si se solicita
    if args.list_configs:
        list_serving_configs(args.project, args.location, args.catalog)
        return
    
    # Verificar configuración específica
    config_exists, _ = verify_serving_config(
        args.project, args.location, args.catalog, args.config_id
    )
    
    # Crear la configuración si se solicita y no existe
    if args.create and not config_exists:
        print("\n🔧 Intentando crear la configuración...")
        create_serving_config(
            args.project, args.location, args.catalog, args.config_id
        )

if __name__ == "__main__":
    main()
