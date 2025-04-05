"""
API principal para el sistema de recomendaciones con TF-IDF.

Esta versión de la API utiliza vectorización TF-IDF para ofrecer recomendaciones
basadas en contenido sin necesidad de cargar modelos ML pesados de transformer,
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

# Importar el recomendador TF-IDF
from src.recommenders.tfidf_recommender import TFIDFRecommender
from src.api.startup_helper import StartupManager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API",
    description="API para sistema de recomendaciones de retail usando vectorización TF-IDF",
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
recommender = TFIDFRecommender(model_path="data/tfidf_model.pkl")

# Crear gestor de arranque
startup_manager = StartupManager(startup_timeout=300.0)

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
    components: Dict[str, Any] = Field(description="Estado de los componentes")
    uptime_seconds: float = Field(description="Tiempo de funcionamiento en segundos")

# Variables para uptime
start_time = time.time()

async def load_sample_data():
    """Carga datos de muestra para el recomendador."""
    try:
        # Intento 1: Cargar desde datos de muestra en el módulo
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        if SAMPLE_PRODUCTS:
            logger.info(f"Cargados {len(SAMPLE_PRODUCTS)} productos de muestra")
            return SAMPLE_PRODUCTS
    except Exception as e:
        logger.warning(f"No se pudieron cargar productos de muestra desde código: {e}")
    
    # Datos mínimos de fallback
    minimal_products = [
        {
            "id": "product1",
            "title": "Camiseta básica",
            "body_html": "Camiseta de algodón de alta calidad.",
            "product_type": "Ropa"
        },
        {
            "id": "product2",
            "title": "Pantalón vaquero",
            "body_html": "Pantalón vaquero clásico de corte recto.",
            "product_type": "Ropa"
        },
        {
            "id": "product3",
            "title": "Zapatillas deportivas",
            "body_html": "Zapatillas para running con amortiguación.",
            "product_type": "Calzado"
        }
    ]
    logger.info(f"Usando {len(minimal_products)} productos mínimos de muestra")
    return minimal_products

async def load_recommender():
    """Carga y entrena el recomendador TF-IDF."""
    try:
        # Intentar cargar modelo pre-entrenado
        if os.path.exists("data/tfidf_model.pkl"):
            success = await recommender.load()
            if success:
                return True
        
        # Si no existe o falla, entrenar con datos de muestra
        products = await load_sample_data()
        success = await recommender.fit(products)
        return success
    except Exception as e:
        logger.error(f"Error cargando recomendador: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicación."""
    logger.info("🚀 Iniciando API de recomendaciones...")
    
    # Registrar componentes en el gestor de arranque
    startup_manager.register_component(
        name="recommender",
        loader=load_recommender,
        required=True
    )
    
    # Iniciar carga en segundo plano
    asyncio.create_task(startup_manager.start_loading())

@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Endpoint de verificación de salud del servicio."""
    recommender_status = await recommender.health_check()
    startup_status = startup_manager.get_status()
    
    return {
        "status": startup_status["status"],
        "components": {
            "recommender": recommender_status,
            "startup": startup_status
        },
        "uptime_seconds": time.time() - start_time
    }

@app.get("/v1/recommendations/content/{product_id}", response_model=RecommendationResponse)
async def get_content_recommendations(
    product_id: str,
    n: int = Query(5, gt=0, le=20, description="Número de recomendaciones"),
    background_tasks: BackgroundTasks = None
):
    """
    Obtiene recomendaciones basadas en similitud de contenido para un producto.
    """
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    # Obtener recomendaciones
    recommendations = []
    if recommender.loaded:
        recommendations = await recommender.get_recommendations(product_id, n)
    else:
        logger.warning("Recomendador no cargado completamente, devolviendo lista vacía")
    
    # Calcular tiempo de procesamiento
    processing_time_ms = (time.time() - start_processing) * 1000
    
    return {
        "recommendations": recommendations,
        "loading_complete": recommender.loaded,
        "source": "tfidf",
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
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    if not recommender.loaded:
        return {
            "products": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "loading_complete": False,
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
        "loading_complete": True
    }

@app.get("/v1/products/search/", response_model=Dict)
async def search_products(
    q: str = Query(..., min_length=1, description="Texto de búsqueda"),
    n: int = Query(10, gt=0, le=50, description="Número máximo de resultados")
):
    """
    Busca productos por texto utilizando similitud TF-IDF.
    """
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    if not recommender.loaded:
        return {
            "products": [],
            "total": 0,
            "query": q,
            "loading_complete": False,
            "message": "El buscador está cargando. Intente más tarde."
        }
    
    # Realizar búsqueda
    start_processing = time.time()
    results = await recommender.search_products(q, n)
    processing_time_ms = (time.time() - start_processing) * 1000
    
    return {
        "products": results,
        "total": len(results),
        "query": q,
        "loading_complete": True,
        "took_ms": processing_time_ms
    }

# Configuración para ejecutar con uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_tfidf:app", host="0.0.0.0", port=port, reload=True)
