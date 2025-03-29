"""
Versión optimizada del punto de entrada principal con carga diferida.
Implementa un enfoque de inicio progresivo para mejorar la fiabilidad del despliegue
en Cloud Run y otros entornos serverless.
"""
import os
import time
import logging
import threading
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from dotenv import load_dotenv

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

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ruta básica que siempre responde (para health checks)
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
    
    return {"status": "ready", "message": "API lista para recibir solicitudes"}

# Verifica si el modelo está cargado para las rutas que lo requieren
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

# Función para cargar modelos en segundo plano
def load_models_background():
    """
    Carga los modelos y realiza la inicialización en segundo plano.
    Esto permite que la aplicación responda a los health checks mientras
    se realiza la carga pesada de modelos y datos.
    """
    global model_loaded, is_loading, startup_exception, startup_time
    
    try:
        is_loading = True
        startup_time = time.time()
        logging.info("Iniciando carga de modelos y configuración...")
        
        # Simulamos solo la carga básica para permitir que Cloud Run inicie correctamente
        # En una versión posterior implementaremos la carga real de modelos
        logging.info("Simulando carga de modelos para despliegue inicial...")
        
        # Marcamos como cargado para fines de prueba
        time.sleep(2)  # Breve pausa para simular algún trabajo
        model_loaded = True
        end_time = time.time()
        startup_time = end_time - startup_time
        logging.info(f"✅ Sistema inicializado (modo simulado) en {startup_time:.2f}s")
        
    except Exception as e:
        logging.error(f"❌ Error fatal durante la inicialización: {str(e)}")
        startup_exception = e
    finally:
        is_loading = False

# Punto de entrada para ejecución directa (para desarrollo)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    # Asegurarse de que el servidor responda inmediatamente
    logging.info(f"Iniciando servidor en puerto {port}...")
    uvicorn.run("main_optimized:app", host="0.0.0.0", port=port, log_level="info")
