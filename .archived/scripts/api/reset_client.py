"""
Script para reiniciar el cliente de Retail API con la configuración correcta
"""
import os
from dotenv import load_dotenv
from src.recommenders.retail_api import RetailAPIRecommender
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def reset_client():
    # Forzar la recarga de variables de entorno
    load_dotenv(override=True)
    
    # Mostrar valores actuales
    project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
    location = os.getenv("GOOGLE_LOCATION")
    catalog = os.getenv("GOOGLE_CATALOG")
    serving_config = os.getenv("GOOGLE_SERVING_CONFIG")
    
    print(f"Configuración actual:")
    print(f"- GOOGLE_PROJECT_NUMBER: {project_number}")
    print(f"- GOOGLE_LOCATION: {location}")
    print(f"- GOOGLE_CATALOG: {catalog}")
    print(f"- GOOGLE_SERVING_CONFIG: {serving_config}")
    
    # Crear cliente con valores explícitos
    client = RetailAPIRecommender(
        project_number=project_number,
        location=location,
        catalog=catalog,
        serving_config_id=serving_config
    )
    
    print(f"\nCliente inicializado con:")
    print(f"- project_number: {client.project_number}")
    print(f"- location: {client.location}")
    print(f"- catalog: {client.catalog}")
    print(f"- serving_config_id: {client.serving_config_id}")
    print(f"- placement: {client.placement}")
    
    # Verificar valores
    if client.location != "global":
        print(f"\n⚠️ ADVERTENCIA: La ubicación '{client.location}' no es 'global'")
        
    return client

if __name__ == "__main__":
    print("Reiniciando cliente de Retail API...")
    client = reset_client()
    print("Cliente reiniciado.")
