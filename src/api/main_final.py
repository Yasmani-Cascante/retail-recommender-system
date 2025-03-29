"""
Versión final con carga incremental de funcionalidades.
Implementa un enfoque de carga por fases para garantizar la inicialización correcta.
"""
import os
import time
import logging
import threading
import traceback
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from typing import List, Dict, Optional

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
initialization_phase = "not_started"  # Para seguimiento detallado

# Crear la aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API",
    description="API para sistema de recomendaciones híbrido de retail usando Google Cloud Retail API",
    version="1.0.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de logging (añadido al inicio)
try:
    # Intentamos cargar el middleware real si está disponible
    try:
        from src.api.middleware.logging import LoggingMiddleware
        app.add_middleware(LoggingMiddleware)
        logging.info("✅ Middleware de logging añadido correctamente")
    except ImportError:
        logging.info("Middleware personalizado no disponible, usando middleware estándar")
        import time
        
        # Middleware simple para logging si no está disponible el real
        @app.middleware("http")
        async def log_requests(request, call_next):
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time
            logging.info(f"Path: {request.url.path}, Time: {process_time:.4f}s")
            return response
            
        logging.info("✅ Middleware simple añadido como alternativa")
except Exception as e:
    logging.warning(f"⚠️ Error con middleware: {str(e)}")

# Definir datos de muestra como fallback
SAMPLE_PRODUCTS = []

try:
    from src.api.core.sample_data import SAMPLE_PRODUCTS as SP
    SAMPLE_PRODUCTS = SP
    logging.info(f"Datos de muestra pre-cargados: {len(SAMPLE_PRODUCTS)} productos")
except Exception as e:
    logging.warning(f"No se pudieron pre-cargar los datos de muestra: {str(e)}")

# Ruta básica que siempre responde (para health checks)
@app.get("/health")
def health_check():
    """Endpoint para health checks que siempre responde rápidamente."""
    return {
        "status": "healthy", 
        "model_loaded": model_loaded,
        "initialization_phase": initialization_phase,
        "startup_time": startup_time if startup_time else "not_started"
    }

# Ruta raíz con información detallada
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
        "startup_duration": f"{startup_time:.2f}s" if startup_time else "unknown"
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
        "version": "1.0.0"
    }

# Endpoint de productos simplificado (pre-registrado para responder de inmediato)
@app.get("/v1/products/")
def get_products():
    """Obtiene la lista de productos (versión simplificada)."""
    # Responde con datos de muestra incluso durante la carga
    return {"products": SAMPLE_PRODUCTS[:10] if SAMPLE_PRODUCTS else []}

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
                detail=f"Error en inicialización: {str(startup_exception)} (fase: {initialization_phase})"
            )
        raise HTTPException(
            status_code=503, 
            detail=f"El sistema está inicializándose (fase: {initialization_phase}). Inténtelo de nuevo más tarde."
        )
    return True

# Función para cargar modelos en segundo plano con fases incrementales
def load_models_background():
    """
    Carga los modelos por fases para permitir depuración precisa.
    """
    global model_loaded, is_loading, startup_exception, startup_time, initialization_phase, SAMPLE_PRODUCTS
    
    start_total = time.time()
    is_loading = True
    
    try:
        # FASE 1: Cargar módulos básicos y registrar endpoints directamente
        initialization_phase = "1_basic_modules"
        logging.info(f"FASE 1: Cargando módulos básicos...")
        
        try:
            # Registrar endpoints directamente para asegurar funcionalidad básica
            @app.get("/v1/products/")
            def get_products_direct():
                """Obtiene la lista de productos (versión simplificada directa)."""
                return {"products": SAMPLE_PRODUCTS[:10]}
                
            @app.get("/v1/recommendations/simple/{product_id}")
            def get_simple_recommendations_direct(product_id: str):
                """Obtiene recomendaciones simples (versión directa)."""
                # Simular recomendaciones sin usar modelos pesados
                recommendations = [p for p in SAMPLE_PRODUCTS if p["id"] != product_id][:2]
                
                return {
                    "product_id": product_id,
                    "recommendations": recommendations,
                    "message": "These are mock recommendations (Final)"
                }
                
            logging.info("✅ Endpoints básicos registrados correctamente")
            
            # En esta versión simplificada, no importamos los routers reales todavía
            logging.info("✅ Módulos básicos cargados")
            
        except Exception as e:
            logging.error(f"❌ Error en FASE 1: {str(e)}")
            logging.error(traceback.format_exc())
            raise
            
        # FASE 2: Comprobar conexiones externas (simulación)
        initialization_phase = "2_check_connections"
        logging.info(f"FASE 2: Comprobando conexiones externas (simulación)...")
        
        try:
            # Simulamos comprobar conexiones externas
            time.sleep(1)  # Simulamos algo de trabajo
            logging.info("✅ Conexiones externas verificadas (simulación)")
            
        except Exception as e:
            logging.error(f"❌ Error en FASE 2: {str(e)}")
            logging.error(traceback.format_exc())
            logging.warning("⚠️ Continuando a pesar del error...")
            
        # FASE 3: Finalización
        initialization_phase = "3_finalization"
        logging.info(f"FASE 3: Finalizando inicialización...")
        
        # Marcamos como completada la carga
        model_loaded = True
        end_time = time.time()
        startup_time = end_time - start_total
        initialization_phase = "complete"
        logging.info(f"✅ Sistema inicializado en {startup_time:.2f}s")
        
    except Exception as e:
        logging.error(f"❌ Error fatal durante la inicialización: {str(e)}")
        logging.error(traceback.format_exc())
        startup_exception = e
    finally:
        is_loading = False

# Punto de entrada para ejecución directa
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    logging.info(f"Iniciando servidor en puerto {port}...")
    uvicorn.run("main_final:app", host="0.0.0.0", port=port, log_level="info")
