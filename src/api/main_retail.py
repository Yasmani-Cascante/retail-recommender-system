"""
Versión con integración de Google Cloud Retail API.
Basada en la versión estable, pero añadiendo capacidades de recomendación basada en comportamiento.
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
retail_recommender = None
retail_api_ready = False

# Crear la aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API - Retail API",
    description="API para sistema de recomendaciones para retail con integración de Google Cloud Retail API",
    version="1.1.0"
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

# Modelos de datos para la API
class UserEvent(BaseModel):
    """Modelo para eventos de usuario."""
    event_type: str = Field(..., description="Tipo de evento (view, add-to-cart, purchase)")
    product_id: Optional[str] = Field(None, description="ID del producto relacionado con el evento")

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

# Ruta básica para health checks
@app.get("/health")
def health_check():
    """Endpoint para health checks que siempre responde rápidamente."""
    return {
        "status": "healthy", 
        "model_loaded": model_loaded,
        "initialization_phase": initialization_phase,
        "startup_time": startup_time if startup_time else "not_started",
        "retail_api_ready": retail_api_ready
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
    
    features = [
        "Recomendaciones basadas en contenido",
        "Listado de productos",
        "Búsqueda de productos"
    ]
    
    if retail_api_ready:
        features.extend([
            "Integración con Google Cloud Retail API", 
            "Recomendaciones personalizadas para usuarios",
            "Registro de eventos de usuario"
        ])
    
    return {
        "status": "ready", 
        "message": "Sistema listo para recibir solicitudes",
        "startup_duration": f"{startup_time:.2f}s" if startup_time else "unknown",
        "version": "1.1.0-retail",
        "api_features": features
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
    
    recommenders = ["content-based"]
    if retail_api_ready:
        recommenders.append("retail-api")
    
    return {
        "status": "ready",
        "message": "API lista para recibir solicitudes",
        "version": "1.1.0-retail",
        "recommenders": recommenders
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

# Endpoint para recomendaciones de Retail API (solo si está disponible)
@app.get("/v1/recommendations/retail/{product_id}", dependencies=[Depends(verify_api_key)])
async def get_retail_recommendations(
    product_id: str,
    n: int = Query(5, gt=0, le=20),
    user_id: Optional[str] = Header(None, alias="user-id"),
    loaded: bool = Depends(check_model_loaded)
):
    """
    Obtiene recomendaciones de Google Cloud Retail API.
    """
    global retail_recommender, retail_api_ready
    
    if not retail_api_ready or retail_recommender is None:
        return {
            "status": "error",
            "message": "Google Cloud Retail API no está disponible",
            "fallback": "Usa /v1/recommendations/content/{product_id} en su lugar"
        }
    
    # Usar ID de usuario aleatorio si no se proporciona
    if not user_id:
        user_id = f"anonymous_{int(time.time())}"
    
    try:
        # Obtener recomendaciones de Retail API
        recommendations = await retail_recommender.get_recommendations(
            user_id=user_id,
            product_id=product_id,
            n_recommendations=n
        )
        
        # Registrar evento de vista del producto
        try:
            await retail_recommender.record_user_event(
                user_id=user_id,
                event_type="detail-page-view",
                product_id=product_id
            )
        except Exception as e:
            logging.warning(f"No se pudo registrar evento de usuario: {str(e)}")
            
        if not recommendations:
            # Fallback a recomendaciones basadas en contenido
            content_recs = content_recommender.recommend(product_id, n)
            return {
                "product_id": product_id,
                "user_id": user_id,
                "recommendations": content_recs,
                "recommender_type": "content-based-fallback"
            }
            
        return {
            "product_id": product_id,
            "user_id": user_id,
            "recommendations": recommendations,
            "recommender_type": "retail-api"
        }
    except Exception as e:
        logging.error(f"Error al obtener recomendaciones de Retail API: {str(e)}")
        
        # Fallback a recomendaciones basadas en contenido
        try:
            content_recs = content_recommender.recommend(product_id, n)
            return {
                "product_id": product_id,
                "user_id": user_id,
                "recommendations": content_recs,
                "recommender_type": "content-based-fallback",
                "error": str(e)
            }
        except Exception as e2:
            logging.error(f"Error en fallback: {str(e2)}")
            
            # Fallback final a productos aleatorios
            fallback_products = [p for p in SAMPLE_PRODUCTS if p["id"] != product_id][:n]
            return {
                "product_id": product_id,
                "user_id": user_id,
                "recommendations": fallback_products,
                "recommender_type": "random-fallback",
                "error": f"{str(e)} | Fallback error: {str(e2)}"
            }

# Endpoint para recomendaciones basadas en usuario
@app.get("/v1/recommendations/user/{user_id}", dependencies=[Depends(verify_api_key)])
async def get_user_recommendations(
    user_id: str,
    n: int = Query(5, gt=0, le=20),
    loaded: bool = Depends(check_model_loaded)
):
    """
    Obtiene recomendaciones personalizadas para un usuario específico.
    Requiere Google Cloud Retail API.
    """
    global retail_recommender, retail_api_ready
    
    if not retail_api_ready or retail_recommender is None:
        return {
            "status": "error",
            "message": "Google Cloud Retail API no está disponible",
            "user_id": user_id,
            "recommendations": SAMPLE_PRODUCTS[:n]  # Fallback a productos de muestra
        }
    
    try:
        # Obtener recomendaciones de usuario
        recommendations = await retail_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=n
        )
        
        if not recommendations:
            # Fallback a productos populares
            return {
                "user_id": user_id,
                "recommendations": SAMPLE_PRODUCTS[:n],
                "recommender_type": "popular-fallback"
            }
            
        return {
            "user_id": user_id,
            "recommendations": recommendations,
            "recommender_type": "retail-api-user"
        }
    except Exception as e:
        logging.error(f"Error al obtener recomendaciones para usuario: {str(e)}")
        
        # Fallback a productos populares
        return {
            "user_id": user_id,
            "recommendations": SAMPLE_PRODUCTS[:n],
            "recommender_type": "popular-fallback",
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
    Requiere Google Cloud Retail API.
    """
    global retail_recommender, retail_api_ready
    
    if not retail_api_ready or retail_recommender is None:
        return {
            "status": "error",
            "message": "Google Cloud Retail API no está disponible",
            "user_id": user_id,
            "event_type": event_type,
            "product_id": product_id
        }
    
    try:
        # Validar tipo de evento
        valid_events = ["view", "detail-page-view", "add-to-cart", "purchase"]
        if event_type not in valid_events:
            event_type = "detail-page-view"  # Valor por defecto seguro
            
        # Registrar evento
        result = await retail_recommender.record_user_event(
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
    global content_recommender, retail_recommender, retail_api_ready
    
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
        
        # El recomendador basado en contenido es crítico, así que si falla, abortamos
        if content_recommender is None:
            raise ValueError("No se pudo inicializar el recomendador basado en contenido")
            
        # Fase 2: Inicializar Google Cloud Retail API
        initialization_phase = "2_retail_api"
        logging.info(f"FASE 2: Inicializando Google Cloud Retail API...")
        
        try:
            # Verificar configuración
            project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
            location = os.getenv("GOOGLE_LOCATION", "global")
            catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
            serving_config = os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
            
            if not project_number:
                logging.warning("⚠️ GOOGLE_PROJECT_NUMBER no configurado, Retail API no disponible")
                retail_api_ready = False
            else:
                # Importar el recomendador de Retail API
                from src.recommenders.retail_api import RetailAPIRecommender
                
                # Inicializar el recomendador
                retail_recommender = RetailAPIRecommender(
                    project_number=project_number,
                    location=location,
                    catalog=catalog,
                    serving_config_id=serving_config
                )
                logging.info("✅ Retail API Recommender inicializado correctamente")
                
                # Intentar importar el catálogo de productos
                try:
                    import asyncio
                    # Crear un nuevo event loop para operaciones asíncronas
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Ejecutar la importación de catálogo
                    import_result = loop.run_until_complete(
                        retail_recommender.import_catalog(SAMPLE_PRODUCTS)
                    )
                    
                    if import_result.get("status") == "success":
                        logging.info(f"✅ Catálogo importado a Retail API: {import_result.get('products_imported')} productos")
                        retail_api_ready = True
                    else:
                        logging.warning(f"⚠️ Importación parcial del catálogo: {import_result}")
                        # Aún consideramos que está disponible si hay algún producto importado
                        retail_api_ready = import_result.get("products_imported", 0) > 0
                except Exception as e:
                    logging.error(f"❌ Error importando catálogo a Retail API: {str(e)}")
                    logging.error(traceback.format_exc())
                    # No bloqueante, continuamos con funcionalidad reducida
                    retail_api_ready = False
        except Exception as e:
            logging.error(f"❌ Error inicializando Google Cloud Retail API: {str(e)}")
            logging.error(traceback.format_exc())
            retail_api_ready = False
            retail_recommender = None
            
        # Fase 3: Verificación final
        initialization_phase = "3_verification"
        logging.info(f"FASE 3: Verificación final...")
        
        # Verificar que todo esté funcionando correctamente
        if content_recommender and len(SAMPLE_PRODUCTS) > 0:
            sample_id = SAMPLE_PRODUCTS[0]["id"]
            test_recs = content_recommender.recommend(sample_id, 2)
            logging.info(f"✅ Prueba de recomendación de contenido exitosa: {len(test_recs)} resultados")
            
        # Sistema inicializado
        model_loaded = True
        end_time = time.time()
        startup_time = end_time - start_total
        initialization_phase = "complete"
        
        if retail_api_ready:
            logging.info(f"✅ Sistema inicializado completamente con Retail API en {startup_time:.2f}s")
        else:
            logging.info(f"✅ Sistema inicializado parcialmente (sin Retail API) en {startup_time:.2f}s")
        
    except Exception as e:
        logging.error(f"❌ Error fatal durante la inicialización: {str(e)}")
        logging.error(traceback.format_exc())
        startup_exception = e
    finally:
        is_loading = False

# Punto de entrada para ejecución directa
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8080"))
    logging.info(f"Iniciando servidor en puerto {port}...")
    uvicorn.run("main_retail:app", host="0.0.0.0", port=port, log_level="info")
