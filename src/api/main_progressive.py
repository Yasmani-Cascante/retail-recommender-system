"""
Versión progresiva del API con carga diferida.
Implementa un enfoque de inicio progresivo para mejorar la fiabilidad del despliegue
en Cloud Run y otros entornos serverless.
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import time
import threading
import logging
from typing import List, Dict, Optional

# Configurar logging con más detalle
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Variables globales para controlar estado
model_loaded = False
is_loading = False
startup_exception = None
startup_time = None

# Aplicación FastAPI con carga progresiva
app = FastAPI(
    title="Retail Recommender API (Progressive)",
    description="Versión con carga progresiva para Cloud Run",
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

# Definir algunos datos de muestra
SAMPLE_PRODUCTS = [
    {
        "id": "1",
        "title": "T-Shirt",
        "description": "Basic cotton t-shirt",
        "price": 19.99,
        "category": "Clothing"
    },
    {
        "id": "2",
        "title": "Jeans",
        "description": "Comfortable denim jeans",
        "price": 49.99,
        "category": "Clothing"
    },
    {
        "id": "3",
        "title": "Sneakers",
        "description": "Casual sneakers",
        "price": 79.99,
        "category": "Footwear"
    }
]

# Verificación de salud (responde inmediatamente)
@app.get("/health")
def health_check():
    """
    Endpoint para health checks que siempre responde rápidamente.
    Esto permite que Cloud Run considere la aplicación como disponible
    mientras se cargan los modelos en segundo plano.
    """
    return {
        "status": "healthy", 
        "model_loaded": model_loaded,
        "startup_time": startup_time if startup_time else "not_started"
    }

# Ruta raíz
@app.get("/")
def read_root():
    """
    Endpoint raíz que proporciona información sobre el estado de inicialización.
    Inicia la carga del modelo en segundo plano si aún no ha comenzado.
    """
    if startup_exception:
        return {
            "status": "error", 
            "message": "Error durante inicialización", 
            "error": str(startup_exception),
            "model_loaded": model_loaded
        }
    
    if not model_loaded:
        if is_loading:
            return {
                "status": "initializing", 
                "message": "El sistema está cargando los modelos...",
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
        "message": "Welcome to the Retail Recommender API (Progressive)",
        "version": "0.5.0",
        "endpoints": [
            "/health",
            "/v1/",
            "/v1/products/",
            "/v1/recommendations/product/{product_id}"
        ]
    }

# Router para API v1
@app.get("/v1/")
def api_root():
    """Endpoint raíz de la API v1."""
    if not model_loaded:
        if startup_exception:
            return {
                "status": "error", 
                "message": "Error durante inicialización", 
                "error": str(startup_exception)
            }
        return {
            "status": "initializing", 
            "message": "El sistema está cargando, por favor intente más tarde."
        }
    
    return {
        "status": "ready",
        "message": "Welcome to the Retail Recommender API",
        "version": "0.5.0"
    }

# Verifica si el modelo está cargado
def check_model_loaded():
    """
    Dependencia para verificar si el modelo está cargado.
    Se utiliza en rutas que requieren que el modelo esté disponible.
    """
    if not model_loaded:
        if startup_exception:
            raise HTTPException(
                status_code=500, 
                detail=f"Error en inicialización: {str(startup_exception)}"
            )
        raise HTTPException(
            status_code=503, 
            detail="El sistema está inicializándose. Inténtelo de nuevo más tarde."
        )
    return True

# Listado de productos
@app.get("/v1/products/")
def get_products(loaded: bool = Depends(check_model_loaded)):
    """Obtiene la lista de productos."""
    return {"products": SAMPLE_PRODUCTS}

# Recomendaciones
@app.get("/v1/recommendations/product/{product_id}")
def get_product_recommendations(
    product_id: str, 
    loaded: bool = Depends(check_model_loaded)
):
    """
    Obtiene recomendaciones basadas en un producto.
    Requiere que el modelo esté cargado.
    """
    # Simular recomendaciones
    recommendations = [p for p in SAMPLE_PRODUCTS if p["id"] != product_id][:2]
    
    return {
        "product_id": product_id,
        "recommendations": recommendations,
        "model_status": "fully_loaded" if model_loaded else "initializing"
    }

# Función para cargar modelos en segundo plano
def load_models_background():
    """
    Carga los modelos y realiza la inicialización en segundo plano.
    Esta versión simplemente simula una carga lenta para demostrar el concepto.
    """
    global model_loaded, is_loading, startup_exception, startup_time
    
    try:
        is_loading = True
        startup_time = time.time()
        logging.info("Iniciando carga de modelos (simulada)...")
        
        # Simulación de carga de modelos
        for i in range(5):
            logging.info(f"Cargando modelos... {i*20}%")
            time.sleep(2)  # Simular tiempo de carga
        
        # Marcar como cargado
        model_loaded = True
        end_time = time.time()
        startup_time = end_time - startup_time
        logging.info(f"✅ Sistema inicializado completamente en {startup_time:.2f} segundos")
        
    except Exception as e:
        logging.error(f"❌ Error durante la inicialización: {str(e)}")
        startup_exception = e
    finally:
        is_loading = False

# Punto de inicio para Cloud Run
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main_progressive:app", host="0.0.0.0", port=port)
