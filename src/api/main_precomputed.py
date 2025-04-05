"""
API principal para el sistema de recomendaciones con embeddings pre-computados.

Esta versión de la API utiliza embeddings pre-computados para ofrecer recomendaciones
basadas en contenido sin necesidad de cargar modelos ML completos en runtime,
permitiendo un arranque rápido y eficiente en entornos cloud.
"""

import os
import time
import logging
import asyncio
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, Header, Query, HTTPException, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Importar el recomendador pre-computado
from src.recommenders.precomputed_embedding_recommender import PrecomputedEmbeddingRecommender

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API",
    description="API para sistema de recomendaciones de retail usando embeddings pre-computados",
    version="0.4.0"
)

# Agregar middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Crear instancia del recomendador
recommender = PrecomputedEmbeddingRecommender()

# Carga inicial
loading_complete = False
loading_in_progress = False

async def load_recommender_background():
    """Carga el recomendador en segundo plano."""
    global loading_complete, loading_in_progress
    
    if loading_complete or loading_in_progress:
        return
    
    loading_in_progress = True
    
    try:
        logger.info("🚀 Iniciando carga de recomendador en segundo plano...")
        start_time = time.time()
        success = await recommender.load()
        elapsed = time.time() - start_time
        
        if success:
            logger.info(f"✓ Recomendador cargado exitosamente en {elapsed:.2f} segundos")
            loading_complete = True
        else:
            logger.error(f"✗ Error cargando recomendador ({elapsed:.2f} segundos)")
    except Exception as e:
        logger.error(f"Error inesperado cargando recomendador: {e}")
    finally:
        loading_in_progress = False

@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicación."""
    logger.info("🚀 Iniciando API de recomendaciones...")
    
    # Iniciar carga en segundo plano
    asyncio.create_task(load_recommender_background())

# Modelos de datos
class ProductModel(BaseModel):
    id: str
    title: str
    similarity_score: Optional[float] = None
    product_data: Dict[str, Any]

class RecommendationResponse(BaseModel):
    recommendations: List[ProductModel]
    loading_complete: bool = Field(description="Indica si la carga del recomendador ha finalizado")
    source: str = Field(description="Fuente de las recomendaciones")
    took_ms: float = Field(description="Tiempo de procesamiento en milisegundos")

class HealthStatus(BaseModel):
    status: str = Field(description="Estado general del servicio")
    recommender: Dict[str, Any] = Field(description="Estado del recomendador")
    uptime_seconds: float = Field(description="Tiempo de funcionamiento en segundos")
    loading_complete: bool = Field(description="Indica si la carga inicial ha finalizado")

# Variables para uptime
start_time = time.time()

@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Endpoint de verificación de salud del servicio."""
    recommender_status = await recommender.health_check()
    
    return {
        "status": "operational" if recommender_status["loaded"] else "initializing",
        "recommender": recommender_status,
        "uptime_seconds": time.time() - start_time,
        "loading_complete": loading_complete
    }

@app.get("/v1/recommendations/content/{product_id}", response_model=RecommendationResponse)
async def get_content_recommendations(
    product_id: str,
    n: int = Query(5, gt=0, le=20, description="Número de recomendaciones"),
    background_tasks: BackgroundTasks = None
):
    """
    Obtiene recomendaciones basadas en similitud de contenido para un producto.
    
    Si el recomendador no ha terminado de cargar, inicia la carga en segundo plano
    y devuelve un mensaje indicando que las recomendaciones estarán disponibles pronto.
    """
    start_processing = time.time()
    
    # Si no está cargado, iniciar carga en segundo plano
    if not loading_complete and not loading_in_progress:
        if background_tasks:
            background_tasks.add_task(load_recommender_background)
        else:
            asyncio.create_task(load_recommender_background())
    
    # Obtener recomendaciones
    recommendations = []
    if loading_complete:
        recommendations = await recommender.get_recommendations(product_id, n)
    
    # Calcular tiempo de procesamiento
    processing_time_ms = (time.time() - start_processing) * 1000
    
    return {
        "recommendations": recommendations,
        "loading_complete": loading_complete,
        "source": "precomputed_embeddings",
        "took_ms": processing_time_ms
    }

@app.get("/v1/products/", response_model=Dict)
async def get_products(
    page: int = Query(1, gt=0, description="Número de página"),
    page_size: int = Query(50, gt=0, le=100, description="Resultados por página")
):
    """
    Obtiene la lista de productos con paginación.
    """
    if not loading_complete:
        return {
            "products": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "loading_complete": loading_complete,
            "message": "El catálogo de productos está cargando. Intente más tarde."
        }
    
    # Calcular índices de paginación
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    # Obtener productos del recomendador
    all_products = recommender.product_data if recommender.product_data else []
    paginated_products = all_products[start_idx:end_idx]
    
    return {
        "products": paginated_products,
        "total": len(all_products),
        "page": page,
        "page_size": page_size,
        "loading_complete": loading_complete
    }

# Configuración para ejecutar con uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_precomputed:app", host="0.0.0.0", port=port, reload=True)
