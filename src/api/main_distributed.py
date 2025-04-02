
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
import os
import logging
import time
import asyncio

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Importar componentes
from src.api.core.cache import RedisCache
from src.api.clients.grpc_client import RecommendationClient
from src.recommenders.precomputed_recommender import PrecomputedEmbeddingRecommender

# Inicializar app
app = FastAPI(
    title="Retail Recommender API (Distributed)",
    description="API para sistema de recomendaciones con arquitectura distribuida",
    version="0.6.0"
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
cache = RedisCache()
grpc_client = RecommendationClient()

# Inicializar recomendador local (como fallback)
local_recommender = PrecomputedEmbeddingRecommender()

# Variable global para medir tiempo de inicialización
startup_time = None

# Función para verificar API key
async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """
    Verifica la API key en los headers.
    
    Args:
        x_api_key: API key en el header X-API-Key
        
    Raises:
        HTTPException: Si la API key no es válida
    """
    expected_key = os.getenv("API_KEY")
    
    # Si no hay API key configurada, no hacer verificación
    if not expected_key:
        return
        
    # Verificar API key
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail="API key inválida o no proporcionada"
        )

@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicación"""
    global startup_time
    
    start_time = time.time()
    logging.info("🚀 Iniciando API con arquitectura distribuida...")
    
    # Inicializar cliente gRPC
    try:
        await grpc_client.connect()
    except Exception as e:
        logging.error(f"❌ Error inicializando cliente gRPC: {str(e)}")
    
    # Cargar recomendador local como fallback
    try:
        success = local_recommender.fit()
        if success:
            logging.info("✅ Recomendador local inicializado correctamente")
        else:
            logging.error("❌ Error inicializando recomendador local")
    except Exception as e:
        logging.error(f"❌ Error inicializando recomendador local: {str(e)}")
    
    end_time = time.time()
    startup_time = end_time - start_time
    logging.info(f"✅ Startup completado en {startup_time:.2f} segundos")

@app.get("/health")
async def health_check():
    """
    Endpoint para verificar el estado del sistema.
    Incluye información sobre todos los componentes.
    """
    # Obtener stats de cada componente
    cache_stats = await cache.get_stats() if cache.client else {"available": False}
    grpc_stats = await grpc_client.get_stats()
    
    return {
        "status": "healthy", 
        "version": "0.6.0",
        "startup_time": startup_time,
        "components": {
            "grpc_client": grpc_stats,
            "cache": cache_stats,
            "local_recommender": {
                "available": local_recommender.embeddings is not None,
                "product_count": len(local_recommender.product_ids) if local_recommender.product_ids else 0
            }
        }
    }

@app.get("/")
def read_root():
    """Endpoint raíz con información básica de la API"""
    return {
        "message": "Retail Recommender API con arquitectura distribuida",
        "version": "0.6.0",
        "status": "ready",
        "cache_available": cache.client is not None,
        "grpc_connected": grpc_client.is_connected,
        "local_recommender": local_recommender.embeddings is not None
    }

@app.get("/v1/")
def api_root():
    """Endpoint raíz de la API v1"""
    return {
        "message": "V1 API con arquitectura distribuida",
        "version": "0.6.0"
    }

@app.get("/v1/recommendations/content/{product_id}", dependencies=[Depends(verify_api_key)])
async def get_content_recommendations(product_id: str, n: int = 5, background_tasks: BackgroundTasks = None):
    """
    Obtiene recomendaciones basadas en contenido.
    Intenta primero con la caché, luego con gRPC, y finalmente con el recomendador local.
    
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
        cached_result["source"] = "cache"
        return cached_result
    
    # Si no hay caché, intentar con gRPC
    if grpc_client.is_connected:
        try:
            result = await grpc_client.get_content_recommendations(product_id, n)
            
            # Si hay éxito y caché disponible, guardar en caché
            if result["status"] == "success" and cache.client and background_tasks:
                background_tasks.add_task(
                    cache.set,
                    cache_key,
                    result,
                    expiration=86400  # 24 horas
                )
                
            return result
        except Exception as e:
            logging.error(f"Error en gRPC para producto {product_id}: {str(e)}")
            # Continuar con fallback
    
    # Si no hay gRPC o falló, usar recomendador local
    if local_recommender.embeddings is not None:
        try:
            recommendations = local_recommender.recommend(product_id, n)
            result = {
                "product_id": product_id,
                "recommendations": recommendations,
                "count": len(recommendations),
                "status": "success",
                "source": "local"
            }
            
            # Guardar en caché si está disponible
            if cache.client and background_tasks:
                background_tasks.add_task(
                    cache.set,
                    cache_key,
                    result,
                    expiration=86400  # 24 horas
                )
                
            return result
        except Exception as e:
            logging.error(f"Error en recomendador local para producto {product_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Si no hay recomendador local o falló, devolver error
    raise HTTPException(
        status_code=503, 
        detail="No hay servicios de recomendación disponibles"
    )

@app.get("/v1/recommendations/retail/{product_id}", dependencies=[Depends(verify_api_key)])
async def get_retail_recommendations(
    product_id: str, 
    n: int = 5, 
    user_id: Optional[str] = None, 
    background_tasks: BackgroundTasks = None
):
    """
    Obtiene recomendaciones de Retail API.
    
    Args:
        product_id: ID del producto base para las recomendaciones
        n: Número de recomendaciones a devolver
        user_id: ID del usuario (opcional)
        background_tasks: Inyección de BackgroundTasks para tareas asíncronas
        
    Returns:
        dict: Recomendaciones para el producto
    """
    # Usar ID de usuario o generar uno temporal
    user_id = user_id or f"anonymous_{time.time()}"
    
    # Verificar caché primero
    cache_key = f"recommendations:retail:{product_id}:{user_id}:{n}"
    cached_result = await cache.get(cache_key) if cache.client else None
    
    if cached_result:
        logging.info(f"Usando recomendaciones en caché para producto {product_id}")
        cached_result["source"] = "cache"
        return cached_result
    
    # Si no hay caché, intentar con gRPC
    if grpc_client.is_connected:
        try:
            result = await grpc_client.get_retail_recommendations(user_id, product_id, n)
            
            # Si hay éxito y caché disponible, guardar en caché
            if result["status"] == "success" and cache.client and background_tasks:
                background_tasks.add_task(
                    cache.set,
                    cache_key,
                    result,
                    expiration=3600  # 1 hora
                )
                
            return result
        except Exception as e:
            logging.error(f"Error en gRPC para retail recommendations: {str(e)}")
    
    # Si no hay gRPC o falló, devolver error
    raise HTTPException(
        status_code=503, 
        detail="Servicio de recomendaciones de Retail API no disponible"
    )

@app.get("/v1/recommendations/hybrid/{product_id}", dependencies=[Depends(verify_api_key)])
async def get_hybrid_recommendations(
    product_id: str, 
    n: int = 5, 
    user_id: Optional[str] = None, 
    content_weight: float = 0.5,
    background_tasks: BackgroundTasks = None
):
    """
    Obtiene recomendaciones híbridas (contenido + Retail API).
    
    Args:
        product_id: ID del producto base para las recomendaciones
        n: Número de recomendaciones a devolver
        user_id: ID del usuario (opcional)
        content_weight: Peso para recomendaciones basadas en contenido (0-1)
        background_tasks: Inyección de BackgroundTasks para tareas asíncronas
        
    Returns:
        dict: Recomendaciones híbridas para el producto
    """
    # Usar ID de usuario o generar uno temporal
    user_id = user_id or f"anonymous_{time.time()}"
    
    # Verificar caché primero
    cache_key = f"recommendations:hybrid:{product_id}:{user_id}:{n}:{content_weight}"
    cached_result = await cache.get(cache_key) if cache.client else None
    
    if cached_result:
        logging.info(f"Usando recomendaciones en caché para producto {product_id}")
        cached_result["source"] = "cache"
        return cached_result
    
    # Si no hay caché, intentar con gRPC
    if grpc_client.is_connected:
        try:
            result = await grpc_client.get_hybrid_recommendations(
                user_id, product_id, n, content_weight
            )
            
            # Si hay éxito y caché disponible, guardar en caché
            if result["status"] == "success" and cache.client and background_tasks:
                background_tasks.add_task(
                    cache.set,
                    cache_key,
                    result,
                    expiration=3600  # 1 hora
                )
                
            return result
        except Exception as e:
            logging.error(f"Error en gRPC para hybrid recommendations: {str(e)}")
    
    # Si no hay gRPC o falló, intentar con recomendador local
    # Pero necesitamos advertir que no tendremos la parte de Retail API
    if local_recommender.embeddings is not None:
        try:
            recommendations = local_recommender.recommend(product_id, n)
            result = {
                "product_id": product_id,
                "recommendations": recommendations,
                "count": len(recommendations),
                "status": "partial",
                "message": "Solo recomendaciones basadas en contenido disponibles",
                "source": "local"
            }
            
            return result
        except Exception as e:
            logging.error(f"Error en recomendador local para producto {product_id}: {str(e)}")
    
    # Si no hay recomendador local o falló, devolver error
    raise HTTPException(
        status_code=503, 
        detail="No hay servicios de recomendación disponibles"
    )

@app.post("/v1/events/user/{user_id}", dependencies=[Depends(verify_api_key)])
async def record_user_event(
    user_id: str, 
    event_type: str, 
    product_id: Optional[str] = None
):
    """
    Registra eventos de usuario para mejorar recomendaciones futuras.
    
    Args:
        user_id: ID del usuario
        event_type: Tipo de evento (view, add-to-cart, purchase)
        product_id: ID del producto (opcional)
        
    Returns:
        dict: Resultado del registro de evento
    """
    # Validar tipo de evento
    valid_events = ["view", "add-to-cart", "purchase", "detail-page-view"]
    if event_type not in valid_events:
        raise HTTPException(
            status_code=400, 
            detail=f"Tipo de evento inválido. Tipos válidos: {', '.join(valid_events)}"
        )
    
    # Si no hay cliente gRPC, devolver error
    if not grpc_client.is_connected:
        # Intentar conectar una vez más
        try:
            connected = await grpc_client.connect(force=True)
            if not connected:
                raise HTTPException(
                    status_code=503, 
                    detail="Servicio de registro de eventos no disponible"
                )
        except Exception:
            raise HTTPException(
                status_code=503, 
                detail="Servicio de registro de eventos no disponible"
            )
    
    # Registrar evento mediante gRPC
    result = await grpc_client.record_user_event(user_id, event_type, product_id)
    
    # Si hay error, devolver error
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result

@app.get("/v1/products/", dependencies=[Depends(verify_api_key)])
def get_products(page: int = 1, page_size: int = 10):
    """
    Obtiene una lista paginada de productos.
    
    Args:
        page: Número de página
        page_size: Tamaño de la página
        
    Returns:
        dict: Productos paginados
    """
    # Verificar si hay recomendador local (tiene el catálogo)
    if not local_recommender.product_metadata:
        raise HTTPException(
            status_code=503,
            detail="Catálogo de productos no disponible"
        )
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    products_page = local_recommender.product_metadata[start_idx:end_idx]
    
    return {
        "products": products_page,
        "total": len(local_recommender.product_metadata),
        "page": page,
        "page_size": page_size
    }

@app.get("/v1/products/{product_id}", dependencies=[Depends(verify_api_key)])
def get_product(product_id: str):
    """
    Obtiene detalles de un producto específico.
    
    Args:
        product_id: ID del producto
        
    Returns:
        dict: Detalles del producto
    """
    # Verificar si hay recomendador local
    if not local_recommender.product_metadata:
        raise HTTPException(
            status_code=503,
            detail="Catálogo de productos no disponible"
        )
    
    product = local_recommender.get_product_by_id(product_id)
    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"Producto {product_id} no encontrado"
        )
    
    return product

# Punto de inicio para ejecución directa (útil para desarrollo local)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main_distributed:app", host="0.0.0.0", port=port)
