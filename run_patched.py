"""
Versión modificada de run.py que aplica un parche a RetailAPIRecommender
"""
import uvicorn
import os
import sys

# Establecer variables de entorno
os.environ["GOOGLE_LOCATION"] = "global"
os.environ["GOOGLE_CATALOG"] = "default_catalog"
os.environ["GOOGLE_SERVING_CONFIG"] = "default_recommendation_config"

# Aplicar el parche a RetailAPIRecommender
import patch_retail_api

if __name__ == "__main__":
    print("Iniciando aplicación con parche aplicado...")
    uvicorn.run("src.api.main:app", host="localhost", port=8000, reload=True)
