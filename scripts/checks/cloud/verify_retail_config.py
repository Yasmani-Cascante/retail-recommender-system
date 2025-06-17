"""
Script para verificar la configuración de Google Cloud Retail API
"""
import os
from google.cloud import retail_v2
import argparse

def verify_serving_config(project_number, location, catalog, serving_config_id):
    """
    Verifica si una configuración de servicio existe y muestra sus detalles
    """
    client = retail_v2.ServingConfigServiceClient()
    
    # Construir la ruta de la configuración
    serving_config_path = client.serving_config_path(
        project=project_number,
        location=location,
        catalog=catalog,
        serving_config=serving_config_id
    )
    
    print(f"Verificando configuración en: {serving_config_path}")
    
    try:
        # Intentar obtener la configuración
        serving_config = client.get_serving_config(name=serving_config_path)
        print("\n✅ CONFIGURACIÓN ENCONTRADA")
        print(f"Nombre: {serving_config.name}")
        print(f"Display Name: {serving_config.display_name}")
        print(f"Tipos de solución: {serving_config.solution_types}")
        print(f"ID del modelo: {serving_config.model_id}")
        
        # Mostrar más detalles específicos según el tipo de configuración
        if hasattr(serving_config, 'price_reranking_level') and serving_config.price_reranking_level:
            print(f"Nivel de reordenamiento por precio: {serving_config.price_reranking_level}")
            
        if hasattr(serving_config, 'diversity_level') and serving_config.diversity_level:
            print(f"Nivel de diversidad: {serving_config.diversity_level}")
            
        return True, serving_config
        
    except Exception as e:
        print(f"\n❌ ERROR: No se pudo encontrar la configuración")
        print(f"Detalles del error: {str(e)}")
        return False, None

def list_all_serving_configs(project_number, location, catalog):
    """
    Lista todas las configuraciones de servicio disponibles en el catálogo
    """
    client = retail_v2.ServingConfigServiceClient()
    
    # Construir la ruta del catálogo padre
    parent = client.catalog_path(
        project=project_number,
        location=location,
        catalog=catalog
    )
    
    print(f"Listando todas las configuraciones en: {parent}")
    
    try:
        # Listar todas las configuraciones
        serving_configs = client.list_serving_configs(parent=parent)
        
        print("\n📋 CONFIGURACIONES DISPONIBLES:")
        for config in serving_configs:
            print(f"- {config.name} ({config.display_name})")
            
        return True, serving_configs
        
    except Exception as e:
        print(f"\n❌ ERROR: No se pudieron listar las configuraciones")
        print(f"Detalles del error: {str(e)}")
        return False, None

def verify_catalog(project_number, location, catalog):
    """
    Verifica si un catálogo existe y muestra sus detalles
    """
    client = retail_v2.CatalogServiceClient()
    
    # Construir la ruta del catálogo
    catalog_path = client.catalog_path(
        project=project_number,
        location=location,
        catalog=catalog
    )
    
    print(f"Verificando catálogo en: {catalog_path}")
    
    try:
        # Intentar obtener el catálogo
        catalog_info = client.get_catalog(name=catalog_path)
        print("\n✅ CATÁLOGO ENCONTRADO")
        print(f"Nombre: {catalog_info.name}")
        print(f"Display Name: {catalog_info.display_name}")
        return True, catalog_info
        
    except Exception as e:
        print(f"\n❌ ERROR: No se pudo encontrar el catálogo")
        print(f"Detalles del error: {str(e)}")
        return False, None

def create_default_serving_config(project_number, location, catalog, serving_config_id="default_recommendation_config"):
    """
    Crea una configuración de servicio predeterminada si no existe
    """
    client = retail_v2.ServingConfigServiceClient()
    
    # Construir la ruta del catálogo padre
    parent = client.catalog_path(
        project=project_number,
        location=location,
        catalog=catalog
    )
    
    # Definir la configuración de servicio
    serving_config = retail_v2.ServingConfig(
        display_name="Default Recommendation Configuration",
        solution_types=[retail_v2.SolutionType.SOLUTION_TYPE_RECOMMENDATION],
        model_id="default_recommendation",
        price_reranking_level=retail_v2.PriceRerankingLevel.NO_PRICE_RERANKING
    )
    
    print(f"Creando configuración en: {parent}")
    
    try:
        # Intentar crear la configuración
        response = client.create_serving_config(
            parent=parent,
            serving_config=serving_config,
            serving_config_id=serving_config_id
        )
        print("\n✅ CONFIGURACIÓN CREADA EXITOSAMENTE")
        print(f"Nombre: {response.name}")
        return True, response
        
    except Exception as e:
        print(f"\n❌ ERROR: No se pudo crear la configuración")
        print(f"Detalles del error: {str(e)}")
        return False, None

def main():
    # Configurar parser de argumentos
    parser = argparse.ArgumentParser(description='Verificar configuración de Google Cloud Retail API')
    parser.add_argument('--project', type=str, default=os.getenv('GOOGLE_PROJECT_NUMBER', '178362262166'),
                        help='Número del proyecto de Google Cloud')
    parser.add_argument('--location', type=str, default=os.getenv('GOOGLE_LOCATION', 'global'),
                        help='Ubicación de Google Cloud (por defecto: global)')
    parser.add_argument('--catalog', type=str, default=os.getenv('GOOGLE_CATALOG', 'retail_178362262166'),
                        help='ID del catálogo de Retail API')
    parser.add_argument('--config-id', type=str, default=os.getenv('GOOGLE_SERVING_CONFIG', 'default_recommendation_config'),
                        help='ID de la configuración de servicio')
    parser.add_argument('--create', action='store_true',
                        help='Crear la configuración si no existe')
    parser.add_argument('--list-configs', action='store_true',
                        help='Listar todas las configuraciones disponibles')
    
    args = parser.parse_args()
    
    # Verificar el catálogo primero
    catalog_exists, _ = verify_catalog(args.project, args.location, args.catalog)
    
    if not catalog_exists:
        print("\n⚠️ No se puede continuar sin un catálogo válido")
        return
    
    # Si se solicita listar configuraciones
    if args.list_configs:
        list_all_serving_configs(args.project, args.location, args.catalog)
    
    # Verificar la configuración de servicio
    config_exists, _ = verify_serving_config(args.project, args.location, args.catalog, args.config_id)
    
    # Crear la configuración si se solicita y no existe
    if args.create and not config_exists:
        print("\n🔧 Intentando crear la configuración...")
        create_default_serving_config(args.project, args.location, args.catalog, args.config_id)

if __name__ == "__main__":
    main()
