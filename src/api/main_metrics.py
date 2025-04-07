"""
Versión simplificada del archivo principal que incluye el router de métricas.
Esta versión se puede usar para probar rápidamente el endpoint de métricas sin 
tener que modificar todo el archivo principal.
"""

import os
import logging
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from src.api.security import get_api_key, get_current_user

# Importar el router de métricas
from src.api.metrics_router import router as metrics_router

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API Metrics",
    description="API para métricas del sistema de recomendaciones de retail",
    version="0.1.0"
)

# Agregar middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir el router de métricas
app.include_router(metrics_router)

@app.get("/", include_in_schema=False)
def read_root():
    return {
        "message": "Retail Recommender API Metrics",
        "version": "0.1.0",
        "status": "online",
        "docs_url": "/docs"
    }

@app.get("/health")
async def health_check():
    """Endpoint de verificación de salud del servicio."""
    return {
        "status": "ok",
        "components": {
            "metrics": {
                "status": "ok",
                "enabled": os.getenv("METRICS_ENABLED", "true").lower() == "true"
            }
        }
    }
