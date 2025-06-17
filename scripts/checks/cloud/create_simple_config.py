"""
Script simplificado para crear una configuración de servicio en Google Cloud Retail API
"""
from google.cloud import retail_v2

def create_simple_serving_config():
    # Crear cliente
    client = retail_v2.ServingConfigServiceClient()
    
    # Construir la ruta del catálogo
    parent = "projects/178362262166/locations/global/catalogs/default_catalog"
    
    # Crear configuración mínima sin model_id
    serving_config = retail_v2.ServingConfig()
    serving_config.display_name = "Basic Search Config"
    
    # Intentar crear la configuración
    try:
        print(f"Creando configuración básica en: {parent}")
        # Crear la solicitud
        request = retail_v2.CreateServingConfigRequest(
            parent=parent,
            serving_config=serving_config,
            serving_config_id="default_search_config"
        )
        
        # Enviar la solicitud
        response = client.create_serving_config(request=request)
        print("\n✅ CONFIGURACIÓN CREADA EXITOSAMENTE:")
        print(f"Nombre: {response.name}")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: No se pudo crear la configuración")
        print(f"Detalles del error: {str(e)}")
        return False

if __name__ == "__main__":
    create_simple_serving_config()
