"""
Script para aplicar un parche a la clase RetailAPIRecommender
"""
import os
from src.recommenders.retail_api import RetailAPIRecommender

# Guardar el método __init__ original
original_init = RetailAPIRecommender.__init__

# Definir el nuevo método __init__
def patched_init(self, project_number, location, catalog="default_catalog", serving_config_id="default_recommendation_config"):
    # Forzar "global" como ubicación
    location = "global"
    
    # Forzar "default_catalog" como catálogo
    catalog = "default_catalog"
    
    # Llamar al método original con los valores corregidos
    original_init(self, project_number, location, catalog, serving_config_id)
    
    # Imprimir la configuración
    print(f"RetailAPIRecommender inicializado con ubicación forzada:")
    print(f"- project_number: {self.project_number}")
    print(f"- location: {self.location}")
    print(f"- catalog: {self.catalog}")
    print(f"- serving_config_id: {self.serving_config_id}")

# Aplicar el parche
RetailAPIRecommender.__init__ = patched_init

print("Parche aplicado a RetailAPIRecommender.__init__")
