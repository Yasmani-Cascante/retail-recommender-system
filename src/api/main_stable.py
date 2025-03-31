"""
Versión estable del sistema de recomendaciones híbrido.
Optimizada para despliegue confiable en Cloud Run.
"""
import os
import time
import logging
import threading
import traceback
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from typing import List, Dict, Optional, Union
from pydantic import BaseModel, Field

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Variables globales para controlar estado
model_loaded = False
is_loading = False
startup_exception = None
startup_time = None
initialization_phase = "not_started"

# Variables para recomendadores
content_recommender = None
retail_api_ready = False

# Crear la aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API - Stable",
    description="API para sistema de recomendaciones para retail",
    version="1.0.0-stable"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Definir datos de muestra
SAMPLE_PRODUCTS = [
    {
        "id": "1",
        "title": "Smartphone XYZ",
        "description": "Un potente smartphone con la última tecnología.",
        "price": 799.99,
        "category": "Electronics"
    },
    {
        "id": "2",
        "title": "Laptop Pro",
        "description": "Laptop ultraligera con procesador de última generación.",
        "price": 1299.99,
        "category": "Electronics"
    },
    {
        "id": "3",
        "title": "Auriculares Inalámbricos",
        "description": "Auriculares con cancelación de ruido y sonido de alta fidelidad.",
        "price": 249.99,
        "category": "Electronics"
    },
    {
        "id": "4",
        "title": "Tablet Mini",
        "description": "Tablet compacta ideal para leer y navegar.",
        "price": 399.99,
        "category": "Electronics"
    },
    {
        "id": "5",
        "title": "Reloj Inteligente",
        "description": "Smartwatch con monitoreo de salud, GPS y autonomía de 7 días.",
        "price": 299.99,
        "category": "Wearables"
    }
]

try:
    # Intentar cargar más datos de muestra
    from src.api.core.sample_data import SAMPLE_PRODUCTS as SP
    if SP and len(SP) > len(SAMPLE_PRODUCTS):
        SAMPLE_PRODUCTS = SP
        logging.info(f"Datos de muestra extendidos cargados: {len(SAMPLE_PRODUCTS)} productos")
except Exception as e:
    logging.warning(f"Usando datos de muestra básicos: {str(e)}")

# Ruta básica para health checks
@app.get("/health")
def health_check():
    """Endpoint para health checks que siempre responde rápidamente."""
    return {
        "status": "healthy", 
        "model_loaded": model_loaded,
        "initialization_phase": initialization_phase,
        "startup_time": startup_time if startup_time else "not_started"
    }

# Ruta raíz
@app.get("/")
def read_root():
    """Endpoint raíz con información sobre el estado del sistema."""
    if startup_exception:
        return {
            "status": "error", 
            "message": "Error durante inicialización", 
            "error": str(startup_exception),
            "phase": initialization_phase,
            "model_loaded": model_loaded
        }
    
    if not model_loaded:
        if is_loading:
            return {
                "status": "initializing", 
                "message": f"El sistema está cargando (fase: {initialization_phase})...",
                "startup_time": startup_time if startup_time else "not_started"
            }
        else:
            # Iniciar carga en background si aún no se ha iniciado
            thread = threading.Thread(target=load_models_background)
            thread.daemon = True
            thread.start()
            return {"status": "starting", "message": "Iniciando carga de modelos..."}
    
    return {
        "status": "ready", 
        "message": "Sistema listo para recibir solicitudes",
        "startup_duration": f"{startup_time:.2f}s" if startup_time else "unknown",
        "version": "1.0.0-stable",
        "api_features": [
            "Recomendaciones basadas en contenido",
            "Listado de productos",
            "Búsqueda de productos"
        ]
    }

# Endpoint de la API v1
@app.get("/v1/")
def api_root():
    """Endpoint raíz de la API v1."""
    if startup_exception:
        return {
            "status": "error", 
            "message": "Error durante inicialización", 
            "error": str(startup_exception)
        }
    
    if not model_loaded:
        return {
            "status": "initializing", 
            "message": f"El sistema está cargando (fase: {initialization_phase})..."
        }
    
    return {
        "status": "ready",
        "message": "API lista para recibir solicitudes",
        "version": "1.0.0-stable",
        "recommenders": ["content-based"]
    }

# Verifica si el modelo está cargado
def check_model_loaded():
    """Dependencia para verificar si el modelo está cargado."""
    if not model_loaded:
        if startup_exception:
            raise HTTPException(
                status_code=500, 
                detail=f"Error en inicialización: {str(startup_exception)}"
            )
        raise HTTPException(
            status_code=503, 
            detail=f"El sistema está inicializándose. Inténtelo de nuevo más tarde."
        )
    return True

# Endpoint de productos con paginación
@app.get("/v1/products/")
def get_products(
    page: int = Query(1, gt=0, description="Número de página"),
    page_size: int = Query(50, gt=0, le=100, description="Elementos por página")
):
    """Obtiene la lista de productos con paginación."""
    # Calcular índices para la paginación
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    # Obtener productos para la página actual
    paginated_products = SAMPLE_PRODUCTS[start_idx:end_idx]
    
    return {
        "products": paginated_products,
        "page": page,
        "page_size": page_size,
        "total": len(SAMPLE_PRODUCTS),
        "total_pages": (len(SAMPLE_PRODUCTS) + page_size - 1) // page_size
    }

# Endpoint para recomendaciones basadas en contenido
@app.get("/v1/recommendations/content/{product_id}")
def get_content_recommendations(
    product_id: str, 
    n: int = Query(5, gt=0, le=20, description="Número de recomendaciones"),
    loaded: bool = Depends(check_model_loaded)
):
    """
    Obtiene recomendaciones basadas en contenido para un producto específico.
    Requiere que el recomendador basado en contenido esté cargado.
    """
    global content_recommender
    
    if content_recommender is None:
        return {
            "product_id": product_id,
            "recommendations": [],
            "message": "Recomendador no disponible todavía"
        }
    
    try:
        # Usar el recomendador basado en contenido
        recommendations = content_recommender.recommend(product_id, n)
        return {
            "product_id": product_id,
            "recommendations": recommendations,
            "recommender_type": "content-based"
        }
    except Exception as e:
        logging.error(f"Error al obtener recomendaciones: {str(e)}")
        # Fallback a recomendaciones básicas si hay error
        fallback_products = [p for p in SAMPLE_PRODUCTS if p["id"] != product_id][:n]
        return {
            "product_id": product_id,
            "recommendations": fallback_products,
            "recommender_type": "fallback",
            "error": str(e)
        }

# Endpoint para búsqueda de productos
@app.get("/v1/products/search/")
def search_products(
    q: str = Query(..., min_length=2, description="Texto a buscar")
):
    """
    Busca productos por texto en título y descripción.
    """
    if not q or len(q) < 2:
        return {"products": [], "query": q, "count": 0}
        
    # Buscar en título y descripción
    q = q.lower()
    results = []
    
    for product in SAMPLE_PRODUCTS:
        title = product.get("title", "").lower()
        description = product.get("description", "").lower()
        
        if q in title or q in description:
            results.append(product)
            
    return {
        "products": results,
        "query": q,
        "count": len(results)
    }

# Función para cargar modelos en segundo plano
def load_models_background():
    """
    Carga los modelos en segundo plano.
    """
    global model_loaded, is_loading, startup_exception, startup_time, initialization_phase
    global content_recommender, retail_api_ready
    
    start_total = time.time()
    is_loading = True
    
    try:
        # Fase 1: Cargar recomendador basado en contenido
        initialization_phase = "1_content_recommender"
        logging.info(f"FASE 1: Cargando recomendador basado en contenido...")
        
        try:
            # Importar el recomendador simplificado
            from src.recommenders.simple_content_based import SimpleContentRecommender
            content_recommender = SimpleContentRecommender()
            logging.info("✅ Recomendador basado en contenido creado correctamente")
            
            # Entrenar el recomendador con datos de muestra
            content_recommender.fit(SAMPLE_PRODUCTS)
            logging.info(f"✅ Recomendador entrenado con {len(SAMPLE_PRODUCTS)} productos")
        except Exception as e:
            logging.error(f"❌ Error cargando recomendador basado en contenido: {str(e)}")
            logging.error(traceback.format_exc())
            raise
            
        # Fase 2: Verificar funcionamiento
        initialization_phase = "2_verification"
        logging.info(f"FASE 2: Verificando funcionamiento...")
        
        try:
            # Probar recomendador
            if content_recommender and len(SAMPLE_PRODUCTS) > 0:
                sample_id = SAMPLE_PRODUCTS[0]["id"]
                test_recs = content_recommender.recommend(sample_id, 2)
                logging.info(f"✅ Prueba de recomendación exitosa: {len(test_recs)} resultados")
        except Exception as e:
            logging.error(f"❌ Error en verificación: {str(e)}")
            logging.error(traceback.format_exc())
            # No bloqueante, continuamos
            
        # Sistema inicializado
        model_loaded = True
        end_time = time.time()
        startup_time = end_time - start_total
        initialization_phase = "complete"
        logging.info(f"✅ Sistema inicializado en {startup_time:.2f}s")
        
    except Exception as e:
        logging.error(f"❌ Error durante la inicialización: {str(e)}")
        logging.error(traceback.format_exc())
        startup_exception = e
    finally:
        is_loading = False

# Punto de entrada para ejecución directa
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8080"))
    logging.info(f"Iniciando servidor en puerto {port}...")
    uvicorn.run("main_stable:app", host="0.0.0.0", port=port, log_level="info")
