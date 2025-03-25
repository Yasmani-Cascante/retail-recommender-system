"""
Script simplificado para crear una configuración de servicio en Google Cloud Retail API
"""
from google.cloud import retail_v2

def create_serving_config():
    # Crear cliente
    client = retail_v2.ServingConfigServiceClient()
    
    # Construir la ruta del catálogo
    parent = "projects/178362262166/locations/global/catalogs/default_catalog"
    
    # Crear configuración simplificada
    serving_config = retail_v2.ServingConfig()
    serving_config.display_name = "Default Recommendation Config"
    serving_config.model_id = "default_recommendation"  # Campo requerido para recomendaciones
    
    # Añadir solution_types si está disponible
    try:
        # Intentar usar enumeración
        serving_config.solution_types = [retail_v2.SolutionType.SOLUTION_TYPE_RECOMMENDATION]
    except (AttributeError, TypeError):
        # Fallback a string si la enumeración no está disponible
        print("Usando string para solution_types en lugar de enumeración")
        serving_config.solution_types = ["recommendation"]
    
    # Intentar crear la configuración
    try:
        print(f"Creando configuración en: {parent}")
        # Crear la solicitud
        request = retail_v2.CreateServingConfigRequest(
            parent=parent,
            serving_config=serving_config,
            serving_config_id="default_recommendation_config"
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
    create_serving_config()
