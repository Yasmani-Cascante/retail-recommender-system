
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
import os
import logging
import time
import json

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Importar componentes
from src.recommenders.precomputed_recommender import PrecomputedEmbeddingRecommender
from src.api.core.cache import RedisCache
from src.api.core.background_tasks import BackgroundTaskManager

# Inicializar app
app = FastAPI(
    title="Retail Recommender API (Cached)",
    description="API para sistema de recomendaciones con caché distribuida",
    version="0.5.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar componentes
recommender = PrecomputedEmbeddingRecommender()
cache = RedisCache()
task_manager = None

# Variable global para medir tiempo de inicialización
startup_time = None

@app.on_event("startup")
async def startup_event():
    global task_manager, startup_time
    
    start_time = time.time()
    logging.info("🚀 Iniciando API con caché distribuida...")
    
    # Cargar embeddings precomputados
    logging.info("📊 Cargando embeddings precomputados...")
    success = recommender.fit()
    
    if success:
        logging.info("✅ Embeddings precomputados cargados correctamente")
    else:
        logging.error("❌ Error cargando embeddings precomputados")
    
    # Inicializar y arrancar administrador de tareas en segundo plano si hay caché y recomendador
    if cache.client and recommender.embeddings is not None:
        task_manager = BackgroundTaskManager(recommender, cache)
        await task_manager.start()
        logging.info("✅ Administrador de tareas en segundo plano iniciado")
    else:
        logging.warning("⚠️ Caché o recomendador no disponibles, tareas en segundo plano deshabilitadas")
    
    end_time = time.time()
    startup_time = end_time - start_time
    logging.info(f"✅ Startup completado en {startup_time:.2f} segundos")

@app.on_event("shutdown")
async def shutdown_event():
    global task_manager
    if task_manager:
        task_manager.is_running = False
        logging.info("🛑 Deteniendo tareas en segundo plano...")

@app.get("/health")
async def health_check():
    """
    Endpoint para verificar el estado del sistema.
    Incluye información sobre el recomendador, caché y tareas en segundo plano.
    """
    # Obtener stats de cada componente
    cache_stats = await cache.get_stats() if cache.client else {"available": False}
    task_stats = await task_manager.get_stats() if task_manager else {"is_running": False}
    
    return {
        "status": "healthy", 
        "version": "0.5.0",
        "startup_time": startup_time,
        "components": {
            "recommender": {
                "available": recommender.embeddings is not None,
                "product_count": len(recommender.product_ids) if recommender.product_ids else 0
            },
            "cache": cache_stats,
            "background_tasks": task_stats
        }
    }

@app.get("/")
def read_root():
    """Endpoint raíz con información básica de la API"""
    return {
        "message": "Retail Recommender API con caché distribuida",
        "version": "0.5.0",
        "status": "ready" if recommender.embeddings is not None else "initializing",
        "cache_available": cache.client is not None,
        "background_tasks": task_manager is not None and task_manager.is_running
    }

@app.get("/v1/")
def api_root():
    """Endpoint raíz de la API v1"""
    return {
        "message": "V1 API con caché distribuida",
        "version": "0.5.0"
    }

async def compute_and_cache_recommendations(product_id: str, n: int, cache_key: str):
    """
    Tarea en segundo plano para calcular y guardar recomendaciones en caché.
    
    Args:
        product_id: ID del producto base para las recomendaciones
        n: Número de recomendaciones a generar
        cache_key: Clave para guardar en caché
    """
    try:
        recommendations = recommender.recommend(product_id, n)
        await cache.set(
            cache_key,
            {
                "product_id": product_id,
                "recommendations": recommendations,
                "count": len(recommendations),
                "cached_at": time.time()
            },
            expiration=86400  # 24 horas
        )
        logging.info(f"Recomendaciones guardadas en caché para producto {product_id}")
    except Exception as e:
        logging.error(f"Error en tarea en segundo plano para producto {product_id}: {str(e)}")

@app.get("/v1/recommendations/content/{product_id}")
async def get_content_recommendations(product_id: str, n: int = 5, background_tasks: BackgroundTasks = None):
    """
    Obtiene recomendaciones basadas en contenido para un producto, con caché.
    
    Args:
        product_id: ID del producto base para las recomendaciones
        n: Número de recomendaciones a devolver
        background_tasks: Inyección de BackgroundTasks para tareas asíncronas
        
    Returns:
        dict: Recomendaciones para el producto
    """
    # Verificar caché primero
    cache_key = f"recommendations:content:{product_id}:{n}"
    cached_result = await cache.get(cache_key) if cache.client else None
    
    if cached_result:
        logging.info(f"Usando recomendaciones en caché para producto {product_id}")
        return cached_result
    
    try:
        # Calcular recomendaciones
        recommendations = recommender.recommend(product_id, n)
        result = {
            "product_id": product_id,
            "recommendations": recommendations,
            "count": len(recommendations),
            "source": "computed"
        }
        
        # Guardar en caché para futuras solicitudes
        if cache.client and background_tasks:
            background_tasks.add_task(
                compute_and_cache_recommendations,
                product_id, n, cache_key
            )
        
        return result
    except Exception as e:
        logging.error(f"Error en recomendaciones para producto {product_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/products/")
def get_products(page: int = 1, page_size: int = 10):
    """
    Obtiene una lista paginada de productos.
    
    Args:
        page: Número de página
        page_size: Tamaño de la página
        
    Returns:
        dict: Productos paginados
    """
    if not recommender.product_metadata:
        return {"products": [], "total": 0, "page": page, "page_size": page_size}
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    products_page = recommender.product_metadata[start_idx:end_idx]
    
    return {
        "products": products_page,
        "total": len(recommender.product_metadata),
        "page": page,
        "page_size": page_size
    }

@app.get("/v1/products/{product_id}")
def get_product(product_id: str):
    """
    Obtiene detalles de un producto específico.
    
    Args:
        product_id: ID del producto
        
    Returns:
        dict: Detalles del producto
    """
    product = recommender.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Producto {product_id} no encontrado")
    return product

@app.post("/v1/cache/flush")
async def flush_cache():
    """
    Limpia toda la caché (solo para desarrollo/depuración).
    
    Returns:
        dict: Resultado de la operación
    """
    if not cache.client:
        raise HTTPException(status_code=503, detail="Caché no disponible")
        
    success = await cache.flush()
    return {
        "success": success,
        "message": "Caché limpiada correctamente" if success else "Error limpiando caché"
    }

# Punto de inicio para ejecución directa (útil para desarrollo local)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main_cached:app", host="0.0.0.0", port=port)
