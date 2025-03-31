"""
Versión Stage 2 con recomendador basado en contenido.
Implementa la funcionalidad del recomendador basado en contenido.
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
content_recommender = None

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
SAMPLE_PRODUCTS = [
    {
        "id": "1",
        "title": "Smartphone XYZ",
        "description": "Un potente smartphone con la última tecnología y pantalla OLED de alta resolución.",
        "price": 799.99,
        "category": "Electronics"
    },
    {
        "id": "2",
        "title": "Laptop Pro",
        "description": "Laptop ultraligera con procesador de última generación y excelente duración de batería.",
        "price": 1299.99,
        "category": "Electronics"
    },
    {
        "id": "3",
        "title": "Auriculares Inalámbricos",
        "description": "Auriculares con cancelación de ruido y sonido de alta fidelidad para una experiencia inmersiva.",
        "price": 249.99,
        "category": "Electronics"
    },
    {
        "id": "4",
        "title": "Tablet Mini",
        "description": "Tablet compacta ideal para leer y navegar, con pantalla retina y procesador rápido.",
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
    # Intentar cargar más datos de muestra si están disponibles
    from src.api.core.sample_data import SAMPLE_PRODUCTS as SP
    if SP and len(SP) > len(SAMPLE_PRODUCTS):
        SAMPLE_PRODUCTS = SP
        logging.info(f"Datos de muestra extendidos pre-cargados: {len(SAMPLE_PRODUCTS)} productos")
except Exception as e:
    logging.warning(f"Usando datos de muestra básicos: {str(e)}")

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
        "startup_duration": f"{startup_time:.2f}s" if startup_time else "unknown",
        "version": "Stage 2 (Content-Based Recommender)"
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
        "version": "Stage 2",
        "recommenders": ["content-based"]
    }

# Endpoint de productos (disponible siempre)
@app.get("/v1/products/")
def get_products():
    """Obtiene la lista de productos."""
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

# Endpoint para recomendaciones basadas en contenido
@app.get("/v1/recommendations/content/{product_id}")
def get_content_recommendations(
    product_id: str, 
    n: int = 5,
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
        # Usar el recomendador basado en contenido real
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

# Función para cargar modelos en segundo plano con fases incrementales
def load_models_background():
    """
    Carga los modelos por fases para permitir depuración precisa.
    """
    global model_loaded, is_loading, startup_exception, startup_time, initialization_phase, content_recommender
    
    start_total = time.time()
    is_loading = True
    
    try:
        # FASE 1: Cargar e inicializar recomendador basado en contenido
        initialization_phase = "1_content_recommender"
        logging.info(f"FASE 1: Cargando recomendador basado en contenido...")
        
        try:
            # Importar el recomendador simplificado que no depende de modelos externos
            from src.recommenders.simple_content_based import SimpleContentRecommender
            content_recommender = SimpleContentRecommender()
            logging.info("✅ Recomendador simplificado creado correctamente")
            
            # Entrenar el recomendador con datos de muestra
            content_recommender.fit(SAMPLE_PRODUCTS)
            logging.info(f"✅ Recomendador entrenado con {len(SAMPLE_PRODUCTS)} productos")
        except Exception as e:
            logging.error(f"❌ Error cargando recomendador basado en contenido: {str(e)}")
            logging.error(traceback.format_exc())
            raise
            
        # FASE 2: Verificar funcionamiento
        initialization_phase = "2_verify_recommendations"
        logging.info(f"FASE 2: Verificando funcionamiento...")
        
        try:
            # Probar el recomendador con un producto
            test_product_id = SAMPLE_PRODUCTS[0]["id"]
            recommendations = content_recommender.recommend(test_product_id, 2)
            logging.info(f"✅ Prueba de recomendación exitosa: {len(recommendations)} recomendaciones para producto {test_product_id}")
        except Exception as e:
            logging.error(f"❌ Error en verificación: {str(e)}")
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
    uvicorn.run("main_stage2:app", host="0.0.0.0", port=port, log_level="info")
