"""
Versión Stage 2 con modo de depuración para cargar recomendador.
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

# Configurar logging con máximo detalle
logging.basicConfig(
    level=logging.DEBUG,  # Nivel DEBUG para ver todo
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cargar variables de entorno
load_dotenv()

# Variables globales para controlar estado
model_loaded = False
is_loading = False
startup_exception = None
startup_time = None
initialization_phase = "not_started"
content_recommender = None  # Referencia al recomendador
debug_info = {}  # Para almacenar información de depuración

# Crear la aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API - Debug Mode",
    description="Versión de depuración para solucionar problemas de carga",
    version="2.0.1"
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
    }
]

# Simulador de recomendador basado en contenido
class DummyRecommender:
    def __init__(self):
        self.products = []
        self.product_ids = []
        
    def fit(self, products):
        self.products = products
        self.product_ids = [str(p.get('id')) for p in products]
        logging.info(f"DummyRecommender entrenado con {len(products)} productos")
        
    def recommend(self, product_id, n_recommendations=5):
        if product_id not in self.product_ids:
            logging.warning(f"Producto {product_id} no encontrado, usando fallback")
            return self.products[:min(n_recommendations, len(self.products))]
            
        # Devolver otros productos distintos al solicitado
        return [p for p in self.products if str(p.get('id')) != product_id][:n_recommendations]

# Ruta para health check
@app.get("/health")
def health_check():
    """Endpoint para health checks con información detallada."""
    return {
        "status": "healthy", 
        "model_loaded": model_loaded,
        "initialization_phase": initialization_phase,
        "startup_time": startup_time if startup_time else "not_started",
        "debug_info": debug_info
    }

# Ruta raíz
@app.get("/")
def read_root():
    """Endpoint raíz con información detallada del estado."""
    global debug_info
    
    if startup_exception:
        error_info = {
            "error_type": type(startup_exception).__name__,
            "error_message": str(startup_exception),
            "traceback": debug_info.get("traceback", "No traceback available")
        }
        
        return {
            "status": "error", 
            "message": "Error durante inicialización", 
            "error_details": error_info,
            "phase": initialization_phase,
            "model_loaded": model_loaded,
            "debug_info": debug_info
        }
    
    if not model_loaded:
        if is_loading:
            return {
                "status": "initializing", 
                "message": f"El sistema está cargando (fase: {initialization_phase})...",
                "startup_time": startup_time if startup_time else "not_started",
                "debug_info": debug_info
            }
        else:
            # Iniciar carga en background si aún no se ha iniciado
            thread = threading.Thread(target=load_models_background)
            thread.daemon = True
            thread.start()
            return {
                "status": "starting", 
                "message": "Iniciando carga de modelos...",
                "debug_info": debug_info
            }
    
    return {
        "status": "ready", 
        "message": "Sistema listo para recibir solicitudes",
        "startup_duration": f"{startup_time:.2f}s" if startup_time else "unknown",
        "version": "Stage 2 - Debug Mode",
        "debug_info": debug_info
    }

# Endpoint de la API v1
@app.get("/v1/")
def api_root():
    """Endpoint raíz de la API v1."""
    return {
        "status": "ready" if model_loaded else "initializing",
        "message": "API en modo depuración",
        "version": "Stage 2 - Debug",
        "phase": initialization_phase
    }

# Endpoint para listar productos
@app.get("/v1/products/")
def get_products():
    """Lista los productos disponibles."""
    return {"products": SAMPLE_PRODUCTS}

# Endpoint para recomendaciones con modo de fallback
@app.get("/v1/recommendations/content/{product_id}")
def get_content_recommendations(product_id: str, n: int = 5):
    """
    Obtiene recomendaciones basadas en contenido o fallback.
    No requiere que el modelo esté cargado para funcionar.
    """
    global content_recommender
    
    if not model_loaded or content_recommender is None:
        # Modo fallback - recomendar productos aleatorios
        recommendations = [p for p in SAMPLE_PRODUCTS if p["id"] != product_id][:n]
        return {
            "product_id": product_id,
            "recommendations": recommendations,
            "recommender_type": "fallback",
            "message": f"Usando fallback porque el modelo no está cargado (fase: {initialization_phase})"
        }
    
    try:
        # Usar el recomendador real
        recommendations = content_recommender.recommend(product_id, n)
        return {
            "product_id": product_id,
            "recommendations": recommendations,
            "recommender_type": "content-based"
        }
    except Exception as e:
        logging.error(f"Error obteniendo recomendaciones: {str(e)}")
        # Fallback en caso de error
        fallback_recs = [p for p in SAMPLE_PRODUCTS if p["id"] != product_id][:n]
        return {
            "product_id": product_id,
            "recommendations": fallback_recs,
            "recommender_type": "fallback-error",
            "error": str(e)
        }

# Función para cargar modelos con depuración detallada
def load_models_background():
    """Carga los modelos con depuración detallada para identificar problemas."""
    global model_loaded, is_loading, startup_exception, startup_time, initialization_phase
    global content_recommender, debug_info
    
    start_total = time.time()
    is_loading = True
    
    try:
        logging.info("============ INICIANDO CARGA DE MODELOS (MODO DEBUG) ============")
        
        # FASE 1: Intentar cargar el recomendador real primero
        initialization_phase = "1_content_recommender"
        debug_info["phase_1_start"] = time.time()
        logging.info("FASE 1: Intentando cargar recomendador basado en contenido real...")
        
        try:
            # Intentar importar el recomendador real
            debug_info["phase_1_import_attempt"] = True
            
            try:
                logging.info("Intentando importar ContentBasedRecommender desde 'src.recommenders.content_based'...")
                from src.recommenders.content_based import ContentBasedRecommender
                debug_info["real_import_success"] = True
                
                logging.info("ContentBasedRecommender importado correctamente. Creando instancia...")
                content_recommender = ContentBasedRecommender()
                debug_info["real_recommender_instance_created"] = True
                
                logging.info("Entrenando recomendador con datos de muestra...")
                content_recommender.fit(SAMPLE_PRODUCTS)
                debug_info["real_recommender_trained"] = True
                
                logging.info("✅ Recomendador real entrenado correctamente")
            except ImportError as ie:
                debug_info["import_error"] = str(ie)
                debug_info["import_traceback"] = traceback.format_exc()
                logging.warning(f"No se pudo importar ContentBasedRecommender: {str(ie)}")
                raise
            except Exception as e:
                debug_info["recommender_error"] = str(e)
                debug_info["recommender_traceback"] = traceback.format_exc()
                logging.error(f"Error al crear/entrenar recomendador real: {str(e)}")
                raise
                
        except Exception as e:
            logging.warning(f"No se pudo cargar el recomendador real. Usando dummy: {str(e)}")
            debug_info["using_dummy_recommender"] = True
            
            # Crear un recomendador dummy como fallback
            content_recommender = DummyRecommender()
            content_recommender.fit(SAMPLE_PRODUCTS)
            logging.info("✅ Recomendador dummy creado como alternativa")
            
        debug_info["phase_1_complete"] = True
        debug_info["phase_1_time"] = time.time() - debug_info.get("phase_1_start", start_total)
            
        # FASE 2: Verificar funcionamiento básico
        initialization_phase = "2_verify_basic"
        debug_info["phase_2_start"] = time.time()
        logging.info("FASE 2: Verificando funcionamiento básico...")
        
        try:
            # Probar el recomendador con un producto de muestra
            test_id = "1"
            logging.info(f"Probando recomendador con producto ID: {test_id}")
            recs = content_recommender.recommend(test_id, 2)
            logging.info(f"Recomendaciones obtenidas: {len(recs)}")
            debug_info["test_recommendations"] = [r.get("id") for r in recs] if recs else []
            logging.info("✅ Prueba de recomendación exitosa")
        except Exception as e:
            debug_info["test_error"] = str(e)
            debug_info["test_traceback"] = traceback.format_exc()
            logging.error(f"Error en prueba de recomendación: {str(e)}")
            # No lanzamos error para continuar con el proceso
            
        debug_info["phase_2_complete"] = True
        debug_info["phase_2_time"] = time.time() - debug_info.get("phase_2_start", start_total)
            
        # FASE 3: Finalización exitosa
        initialization_phase = "3_finalization"
        debug_info["phase_3_start"] = time.time()
        logging.info("FASE 3: Finalizando inicialización...")
        
        # Marcamos como completa la carga
        model_loaded = True
        end_time = time.time()
        startup_time = end_time - start_total
        debug_info["total_startup_time"] = startup_time
        initialization_phase = "complete"
        logging.info(f"✅ Sistema inicializado en {startup_time:.2f}s")
        
    except Exception as e:
        logging.error(f"❌ ERROR FATAL en inicialización: {str(e)}")
        debug_info["fatal_error"] = str(e)
        debug_info["fatal_traceback"] = traceback.format_exc()
        startup_exception = e
    finally:
        is_loading = False
        logging.info("============ FINALIZADA CARGA DE MODELOS (MODO DEBUG) ============")

# Punto de entrada para ejecución directa
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    logging.info(f"Iniciando servidor en puerto {port}...")
    uvicorn.run("main_stage2_debug:app", host="0.0.0.0", port=port, log_level="debug")
