"""
Implementación completa del sistema de recomendaciones híbrido.
Incluye integración con Google Cloud Retail API y recomendador híbrido.
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
initialization_phase = "not_started"  # Para seguimiento detallado

# Variables para recomendadores
content_recommender = None
retail_recommender = None
hybrid_recommender = None

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

# Definir datos de muestra
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

# Modelos de datos para la API
class UserEvent(BaseModel):
    """Modelo para eventos de usuario."""
    event_type: str = Field(..., description="Tipo de evento (view, add-to-cart, purchase)")
    product_id: Optional[str] = Field(None, description="ID del producto relacionado con el evento")
    
class RecommendationRequest(BaseModel):
    """Modelo para solicitudes de recomendación."""
    user_id: str = Field(..., description="ID del usuario")
    product_id: Optional[str] = Field(None, description="ID del producto base (opcional)")
    n: int = Field(5, description="Número de recomendaciones a obtener")
    content_weight: Optional[float] = Field(None, description="Peso para recomendaciones basadas en contenido (0-1)")

# Middleware para autenticación simple con API Key
async def verify_api_key(x_api_key: str = Header(None)):
    """
    Verifica la API Key proporcionada en el header.
    """
    expected_api_key = os.getenv("API_KEY")
    if not expected_api_key:
        # Si no está configurada, permitir acceso (solo para desarrollo)
        logging.warning("⚠️ API_KEY no configurada. Permitiendo acceso sin autenticación.")
        return True
        
    if x_api_key != expected_api_key:
        raise HTTPException(
            status_code=401,
            detail="API Key inválida"
        )
    return True

# Middleware de validación de configuración
async def verify_google_config():
    """
    Verifica que la configuración de Google Cloud esté completa.
    """
    project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
    location = os.getenv("GOOGLE_LOCATION")
    catalog = os.getenv("GOOGLE_CATALOG")
    
    if not all([project_number, location, catalog]):
        logging.warning("⚠️ Configuración de Google Cloud incompleta.")
        # No bloqueamos el acceso, solo advertimos
    return True

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
        "version": "1.0.0 (Completa)"
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
        "version": "1.0.0",
        "recommenders": ["content-based", "retail-api", "hybrid"]
    }

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

# Endpoint de productos (disponible siempre)
@app.get("/v1/products/")
def get_products(
    page: int = Query(1, gt=0, description="Número de página"),
    page_size: int = Query(50, gt=0, le=100, description="Elementos por página")
):
    """
    Obtiene la lista de productos con paginación.
    
    Args:
        page: Número de página (comenzando desde 1)
        page_size: Número de elementos por página (máximo 100)
    """
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

# Endpoint para recomendaciones híbridas basadas en producto
@app.get("/v1/recommendations/product/{product_id}", dependencies=[Depends(verify_api_key)])
async def get_recommendations(
    product_id: str,
    n: int = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0, le=1),
    user_id: Optional[str] = Header(None, alias="user-id"),
    loaded: bool = Depends(check_model_loaded)
):
    """
    Obtiene recomendaciones híbridas basadas en un producto específico.
    Combina recomendaciones basadas en contenido y en comportamiento.
    
    Args:
        product_id: ID del producto
        n: Número de recomendaciones (máximo 20)
        content_weight: Peso para las recomendaciones basadas en contenido (0-1)
        user_id: ID del usuario (opcional, en header)
    """
    global hybrid_recommender
    
    if hybrid_recommender is None:
        # Fallback si el recomendador híbrido no está disponible
        if content_recommender is not None:
            return get_content_recommendations(product_id, n)
        return {
            "product_id": product_id,
            "recommendations": [],
            "message": "Recomendador no disponible todavía"
        }
    
    # Usar ID de usuario aleatorio si no se proporciona
    if not user_id:
        user_id = f"anonymous_{int(time.time())}"
    
    try:
        # Obtener recomendaciones híbridas
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id,
            product_id=product_id,
            n_recommendations=n,
            content_weight=content_weight
        )
        
        # Registrar evento de vista del producto
        try:
            await hybrid_recommender.record_user_event(
                user_id=user_id,
                event_type="detail-page-view",
                product_id=product_id
            )
        except Exception as e:
            logging.warning(f"No se pudo registrar evento de usuario: {str(e)}")
            
        return {
            "product_id": product_id,
            "user_id": user_id,
            "recommendations": recommendations,
            "recommender_type": "hybrid",
            "content_weight": content_weight
        }
    except Exception as e:
        logging.error(f"Error al obtener recomendaciones híbridas: {str(e)}")
        # Fallback a recomendaciones de contenido
        if content_recommender is not None:
            return get_content_recommendations(product_id, n)
        
        # Fallback final a productos básicos
        fallback_products = [p for p in SAMPLE_PRODUCTS if p["id"] != product_id][:n]
        return {
            "product_id": product_id,
            "recommendations": fallback_products,
            "recommender_type": "fallback",
            "error": str(e)
        }

# Endpoint para recomendaciones basadas en usuario
@app.get("/v1/recommendations/user/{user_id}", dependencies=[Depends(verify_api_key)])
async def get_user_recommendations(
    user_id: str,
    n: int = Query(5, gt=0, le=20),
    loaded: bool = Depends(check_model_loaded)
):
    """
    Obtiene recomendaciones personalizadas para un usuario específico
    basadas en su comportamiento anterior.
    
    Args:
        user_id: ID del usuario
        n: Número de recomendaciones (máximo 20)
    """
    global retail_recommender
    
    if retail_recommender is None:
        return {
            "user_id": user_id,
            "recommendations": [],
            "message": "Recomendador no disponible todavía"
        }
    
    try:
        # Obtener recomendaciones de Retail API
        recommendations = await retail_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=n
        )
        
        if not recommendations:
            # Fallback a productos populares
            recommendations = SAMPLE_PRODUCTS[:n]
            return {
                "user_id": user_id,
                "recommendations": recommendations,
                "recommender_type": "fallback"
            }
            
        return {
            "user_id": user_id,
            "recommendations": recommendations,
            "recommender_type": "retail-api"
        }
    except Exception as e:
        logging.error(f"Error al obtener recomendaciones para usuario: {str(e)}")
        # Fallback a productos populares
        fallback_products = SAMPLE_PRODUCTS[:n]
        return {
            "user_id": user_id,
            "recommendations": fallback_products,
            "recommender_type": "fallback",
            "error": str(e)
        }

# Endpoint para registrar eventos de usuario
@app.post("/v1/events/user/{user_id}", dependencies=[Depends(verify_api_key)])
async def record_user_event(
    user_id: str,
    event_type: str = Query(..., description="Tipo de evento (view, add-to-cart, purchase)"),
    product_id: Optional[str] = Query(None),
    loaded: bool = Depends(check_model_loaded)
):
    """
    Registra eventos de usuario para mejorar las recomendaciones futuras.
    
    Args:
        user_id: ID del usuario
        event_type: Tipo de evento (view, add-to-cart, purchase)
        product_id: ID del producto relacionado con el evento (opcional)
    """
    global hybrid_recommender
    
    if hybrid_recommender is None:
        return {
            "status": "error",
            "message": "Servicio de eventos no disponible"
        }
    
    try:
        # Validar tipo de evento
        valid_events = ["view", "detail-page-view", "add-to-cart", "purchase"]
        if event_type not in valid_events:
            event_type = "detail-page-view"  # Valor por defecto seguro
            
        # Registrar evento
        result = await hybrid_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id
        )
        
        return {
            "status": "success",
            "message": "Evento registrado correctamente",
            "user_id": user_id,
            "event_type": event_type,
            "product_id": product_id
        }
    except Exception as e:
        logging.error(f"Error al registrar evento de usuario: {str(e)}")
        return {
            "status": "error",
            "message": f"Error al registrar evento: {str(e)}",
            "user_id": user_id,
            "event_type": event_type,
            "product_id": product_id
        }

# Función para cargar modelos en segundo plano con fases incrementales
def load_models_background():
    """
    Carga los modelos por fases para permitir depuración precisa.
    """
    global model_loaded, is_loading, startup_exception, startup_time, initialization_phase
    global content_recommender, retail_recommender, hybrid_recommender
    
    start_total = time.time()
    is_loading = True
    
    try:
        # FASE 1: Cargar e inicializar recomendador basado en contenido
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
            
        # FASE 2: Inicializar Google Cloud Retail API
        initialization_phase = "2_retail_api"
        logging.info(f"FASE 2: Inicializando Google Cloud Retail API...")
        
        try:
            # Obtener parámetros de configuración
            project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
            location = os.getenv("GOOGLE_LOCATION", "global")
            catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
            serving_config = os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
            
            if not project_number:
                raise ValueError("GOOGLE_PROJECT_NUMBER no está configurado en variables de entorno")
            
            # Importar e inicializar el recomendador Retail API
            from src.recommenders.retail_api import RetailAPIRecommender
            retail_recommender = RetailAPIRecommender(
                project_number=project_number,
                location=location,
                catalog=catalog,
                serving_config_id=serving_config
            )
            logging.info("✅ Recomendador Retail API inicializado correctamente")
            
            # Importar catálogo a Google Cloud Retail
            try:
                import_result = await retail_recommender.import_catalog(SAMPLE_PRODUCTS)
                if import_result.get("status") == "success":
                    logging.info(f"✅ Catálogo importado a Google Cloud Retail API: {import_result.get('products_imported')} productos")
                else:
                    logging.warning(f"⚠️ Importación parcial del catálogo: {import_result}")
            except Exception as e:
                logging.error(f"❌ Error importando catálogo a Google Cloud: {str(e)}")
                # Continuamos a pesar del error
                
        except Exception as e:
            logging.error(f"❌ Error inicializando Google Cloud Retail API: {str(e)}")
            logging.error(traceback.format_exc())
            logging.warning("⚠️ Continuando sin Google Cloud Retail API...")
            retail_recommender = None
            
        # FASE 3: Inicializar recomendador híbrido
        initialization_phase = "3_hybrid_recommender"
        logging.info(f"FASE 3: Inicializando recomendador híbrido...")
        
        try:
            # Importar el recomendador híbrido
            from src.recommenders.hybrid_simple import HybridRecommender
            
            # Si no se pudo inicializar Retail API, usar un mock
            if retail_recommender is None:
                class MockRetailRecommender:
                    async def get_recommendations(self, *args, **kwargs):
                        return []
                    async def record_user_event(self, *args, **kwargs):
                        return {"status": "success", "message": "Mock event"}
                    async def import_catalog(self, *args, **kwargs):
                        return {"status": "success", "message": "Mock import"}
                
                retail_recommender_impl = MockRetailRecommender()
                logging.warning("⚠️ Usando mock de Retail API para el recomendador híbrido")
            else:
                retail_recommender_impl = retail_recommender
            
            # Crear el recomendador híbrido
            hybrid_recommender = HybridRecommender(
                content_recommender=content_recommender,
                retail_recommender=retail_recommender_impl,
                content_weight=0.7  # Dar más peso al recomendador basado en contenido por defecto
            )
            logging.info("✅ Recomendador híbrido inicializado correctamente")
            
        except Exception as e:
            logging.error(f"❌ Error inicializando recomendador híbrido: {str(e)}")
            logging.error(traceback.format_exc())
            hybrid_recommender = None
            
        # Sistema inicializado (con posibles limitaciones)
        model_loaded = True
        end_time = time.time()
        startup_time = end_time - start_total
        initialization_phase = "complete"
        
        # Mensaje de resumen del estado
        if content_recommender and retail_recommender and hybrid_recommender:
            logging.info(f"✅ Sistema completamente inicializado en {startup_time:.2f}s")
        elif content_recommender:
            logging.info(f"✅ Sistema parcialmente inicializado (solo recomendador de contenido) en {startup_time:.2f}s")
        else:
            logging.warning(f"⚠️ Sistema inicializado con funcionalidad limitada en {startup_time:.2f}s")
        
    except Exception as e:
        logging.error(f"❌ Error fatal durante la inicialización: {str(e)}")
        logging.error(traceback.format_exc())
        startup_exception = e
    finally:
        is_loading = False
        
# Punto de entrada para ejecución directa
if __name__ == "__main__":
    import uvicorn
    import asyncio
    
    # Necesario para funciones async en la carga de modelos
    async def setup():
        # No hacer nada, solo para que el evento loop esté listo
        pass
    
    # Inicializar event loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup())
    
    # Iniciar servidor
    port = int(os.getenv("PORT", "8080"))
    logging.info(f"Iniciando servidor en puerto {port}...")
    uvicorn.run("main_complete:app", host="0.0.0.0", port=port, log_level="info")
