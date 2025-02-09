from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.middleware.logging import LoggingMiddleware
from src.api.routers import recommendations
from src.api.core.recommenders import content_recommender, retail_recommender
from src.api.core.sample_data import SAMPLE_PRODUCTS
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = FastAPI(
    title="Retail Recommender API",
    description="API para sistema de recomendaciones híbrido de retail usando Google Cloud Retail API",
    version="0.3.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Añadir middleware de logging
app.add_middleware(LoggingMiddleware)

# Startup Event
@app.on_event("startup")
async def startup_event():
    # Entrenar recomendador basado en contenido
    content_recommender.fit(SAMPLE_PRODUCTS)
    
    # Importar productos a Retail API
    await retail_recommender.import_catalog(SAMPLE_PRODUCTS)

# Incluir routers
app.include_router(recommendations.router, prefix="/v1")