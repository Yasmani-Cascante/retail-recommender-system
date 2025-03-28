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
async def health_check():
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
async def read_root():
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
async def api_root():
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
        
        # Importar aquí los módulos para evitar carga al inicio
        from src.api.middleware.logging import LoggingMiddleware
        from src.api.routers import recommendations
        from src.api.core.recommenders import content_recommender, retail_recommender
        from src.api.core.store import init_shopify, get_shopify_client
        
        # Añadir middleware de logging
        app.add_middleware(LoggingMiddleware)
        
        # Incluir routers con la dependencia de verificación
        app.include_router(
            recommendations.router, 
            prefix="/v1", 
            dependencies=[Depends(check_model_loaded)]
        )
        
        # Inicializar cliente de Shopify
        shop_url = os.getenv("SHOPIFY_SHOP_URL")
        access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        
        # Verificar configuración de GCS
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        use_gcs = os.getenv("USE_GCS_IMPORT", "False").lower() == "true"
        
        logging.info(f"SHOPIFY_SHOP_URL: {'configurado' if shop_url else 'no configurado'}")
        logging.info(f"SHOPIFY_ACCESS_TOKEN: {'configurado' if access_token else 'no configurado'}")
        logging.info(f"GCS_BUCKET_NAME: {'configurado' if gcs_bucket else 'no configurado'}")
        logging.info(f"USE_GCS_IMPORT: {use_gcs}")

        client = init_shopify()
        
        if not client:
            logging.warning("⚠️ Shopify credentials not found. Using sample data.")
            from src.api.core.sample_data import SAMPLE_PRODUCTS
            products = SAMPLE_PRODUCTS
            logging.info(f"Loaded {len(SAMPLE_PRODUCTS)} sample products")
        else:
            logging.info("🔄 Initializing Shopify client...")
            try:
                products = client.get_products()
                logging.info(f"✅ Retrieved {len(products)} products from Shopify")
                
                if products:
                    logging.debug(f"First product sample: {products[0]['title'] if 'title' in products[0] else 'no title'}")
                else:
                    logging.warning("⚠️ No products retrieved from Shopify")
                    
            except Exception as e:
                logging.error(f"❌ Error connecting to Shopify: {str(e)}")
                logging.warning("⚠️ Falling back to sample data")
                from src.api.core.sample_data import SAMPLE_PRODUCTS
                products = SAMPLE_PRODUCTS

        # Entrenar recomendador basado en contenido
        try:
            content_recommender.fit(products)
            logging.info("✅ Content-based recommender trained successfully")
        except Exception as e:
            logging.error(f"❌ Error training content recommender: {str(e)}")
            raise

        # Importar productos a Retail API - ahora con soporte para GCS
        try:
            import_result = await retail_recommender.import_catalog(products)
            if import_result.get("status") == "success":
                if "gcs_uri" in import_result:
                    logging.info(f"✅ Products imported to Retail API via GCS: {import_result['gcs_uri']}")
                else:
                    logging.info("✅ Products imported to Retail API successfully via direct import")
                
                logging.info(f"✅ Imported {import_result.get('products_imported', 0)} products out of {import_result.get('total_products', 0)}")
            else:
                logging.warning(f"⚠️ Partial import to Retail API: {import_result}")
        except Exception as e:
            logging.error(f"❌ Error importing to Retail API: {str(e)}")
            # No relanzo esta excepción para permitir funcionamiento parcial
            
        model_loaded = True
        end_time = time.time()
        startup_time = end_time - startup_time
        logging.info(f"✅ Sistema inicializado completamente y listo para recibir solicitudes (tiempo: {startup_time:.2f}s)")
        
    except Exception as e:
        logging.error(f"❌ Error fatal durante la inicialización: {str(e)}")
        startup_exception = e
    finally:
        is_loading = False

# Punto de entrada para ejecución directa (para desarrollo)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main_optimized:app", host="0.0.0.0", port=port)
