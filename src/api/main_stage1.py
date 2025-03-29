"""
Versión Stage 1 con carga parcial de funcionalidades.
Implementa un enfoque progresivo para añadir capas de funcionalidad.
"""
import os
import time
import logging
import threading
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from dotenv import load_dotenv
from typing import List, Dict, Optional

# Cargar variables de entorno
load_dotenv()

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

# Crear la aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API",
    description="API para sistema de recomendaciones híbrido de retail usando Google Cloud Retail API",
    version="0.3.0"
)

# Configurar CORS (añadido al inicio)
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

# Middleware de logging (añadido al inicio)
try:
    # En la versión stage1 no importamos el middleware real para evitar dependencias
    # from src.api.middleware.logging import LoggingMiddleware
    # app.add_middleware(LoggingMiddleware)
    logging.info("Middleware de logging omitido en versión Stage 1")
except Exception as e:
    logging.warning(f"⚠️ Error con middleware: {str(e)}")

# Ruta básica que siempre responde (para health checks)
@app.get("/health")
def health_check():
    """
    Endpoint para health checks que siempre responde rápidamente.
    """
    return {
        "status": "healthy", 
        "model_loaded": model_loaded,
        "startup_time": startup_time if startup_time else "not_started"
    }

# Ruta raíz que informa del estado
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
                "message": "El sistema está cargando los modelos de ML...",
                "startup_time": startup_time if startup_time else "not_started"
            }
        else:
            # Iniciar carga en background si aún no se ha iniciado
            thread = threading.Thread(target=load_models_background)
            thread.daemon = True
            thread.start()
            return {"status": "starting", "message": "Iniciando carga de modelos de ML..."}
    
    return {"status": "ready", "message": "Sistema listo para recibir solicitudes"}

# Endpoint de la API v1
@app.get("/v1/")
def api_root():
    """
    Endpoint raíz de la API v1.
    """
    if startup_exception:
        return {
            "status": "error", 
            "message": "Error durante inicialización", 
            "error": str(startup_exception)
        }
    
    if not model_loaded:
        return {
            "status": "initializing", 
            "message": "El sistema está cargando, por favor intente más tarde."
        }
    
    return {
        "status": "ready",
        "message": "API lista para recibir solicitudes"
    }

# Verifica si el modelo está cargado para las rutas que lo requieren
def check_model_loaded():
    """
    Dependencia para verificar si el modelo está cargado.
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

# Función para cargar modelos en segundo plano
def load_models_background():
    """
    Carga los modelos y realiza la inicialización en segundo plano.
    Stage 1: Carga real de middleware y routers, pero usa datos de muestra.
    """
    global model_loaded, is_loading, startup_exception, startup_time
    
    try:
        is_loading = True
        startup_time = time.time()
        logging.info("Iniciando carga de modelos y configuración (Stage 1)...")
        
        # Importar los módulos
        try:
            # Middleware ya está cargado, solo simular la carga de routers
            logging.info("✅ Simulando carga de módulos para versión Stage 1")
            
            # No importamos los routers reales para evitar dependencias ML
            # from src.api.routers import recommendations
            
            # En su lugar, registramos algunos endpoints básicos directamente
            @app.get("/v1/products/")
            def get_products_direct(loaded: bool = Depends(check_model_loaded)):
                """Obtiene la lista de productos (versión simplificada directa)."""
                return {"products": SAMPLE_PRODUCTS}
                
            @app.get("/v1/recommendations/simple/{product_id}")
            def get_simple_recommendations_direct(product_id: str, loaded: bool = Depends(check_model_loaded)):
                """Obtiene recomendaciones simples (versión directa)."""
                # Simular recomendaciones sin usar modelos pesados
                recommendations = [p for p in SAMPLE_PRODUCTS if p["id"] != product_id][:2]
                
                return {
                    "product_id": product_id,
                    "recommendations": recommendations,
                    "message": "These are mock recommendations (Stage 1)"
                }
                
            logging.info("✅ Endpoints básicos registrados correctamente")
            
        except Exception as e:
            logging.error(f"❌ Error cargando módulos básicos: {str(e)}")
            raise
            
        # Cargar datos de muestra en lugar de conectar con servicios externos
        try:
            from src.api.core.sample_data import SAMPLE_PRODUCTS
            logging.info(f"✅ Datos de muestra cargados: {len(SAMPLE_PRODUCTS)} productos")
        except Exception as e:
            logging.error(f"❌ Error cargando datos de muestra: {str(e)}")
            raise
        
        # Completamos la carga simulada para Stage 1
        model_loaded = True
        end_time = time.time()
        startup_time = end_time - startup_time
        logging.info(f"✅ Sistema Stage 1 inicializado en {startup_time:.2f}s")
        
    except Exception as e:
        logging.error(f"❌ Error fatal durante la inicialización: {str(e)}")
        startup_exception = e
    finally:
        is_loading = False

# Punto de entrada para ejecución directa (para desarrollo)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    logging.info(f"Iniciando servidor en puerto {port}...")
    uvicorn.run("main_stage1:app", host="0.0.0.0", port=port, log_level="info")
