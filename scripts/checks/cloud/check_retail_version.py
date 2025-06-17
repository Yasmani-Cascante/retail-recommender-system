"""
Script para verificar la versión de google-cloud-retail
"""
import pkg_resources
import google.cloud.retail_v2

try:
    # Obtener la versión instalada
    version = pkg_resources.get_distribution("google-cloud-retail").version
    print(f"Versión de google-cloud-retail: {version}")
    
    # Mostrar métodos disponibles en CatalogServiceClient
    print("\nMétodos disponibles en CatalogServiceClient:")
    client = google.cloud.retail_v2.CatalogServiceClient()
    methods = [method for method in dir(client) if not method.startswith('_')]
    for method in methods:
        print(f"- {method}")
    
    print("\nMétodos disponibles en ServingConfigServiceClient:")
    serving_client = google.cloud.retail_v2.ServingConfigServiceClient()
    serving_methods = [method for method in dir(serving_client) if not method.startswith('_')]
    for method in serving_methods:
        print(f"- {method}")
        
except Exception as e:
    print(f"Error: {str(e)}")
