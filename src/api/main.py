from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.middleware.logging import LoggingMiddleware
from src.api.routers import recommendations
from src.api.core.recommenders import content_recommender, retail_recommender
from src.api.core.store import init_shopify, get_shopify_client
import os
from dotenv import load_dotenv
load_dotenv()
import logging
import time

# Configurar logging con más detalle
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cargar variables de entorno
load_dotenv()

# Registrar inicio de la aplicación
logging.info("🚀 Starting Retail Recommender API...")
logging.info(f"ENV: GOOGLE_PROJECT_NUMBER: {'set' if os.getenv('GOOGLE_PROJECT_NUMBER') else 'not set'}")
logging.info(f"ENV: GOOGLE_LOCATION: {os.getenv('GOOGLE_LOCATION', 'not set')}")
logging.info(f"ENV: GOOGLE_CATALOG: {os.getenv('GOOGLE_CATALOG', 'not set')}")
logging.info(f"ENV: GOOGLE_SERVING_CONFIG: {os.getenv('GOOGLE_SERVING_CONFIG', 'not set')}")
logging.info(f"ENV: SHOPIFY_SHOP_URL: {'set' if os.getenv('SHOPIFY_SHOP_URL') else 'not set'}")
logging.info(f"ENV: PORT: {os.getenv('PORT', '8080')}")

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

# Añadir middleware de logging
app.add_middleware(LoggingMiddleware)

# Ruta Health check para confirmar que la aplicación está funcionando
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API is running"}

# Startup Event
@app.on_event("startup")
async def startup_event():
    try:
        # Iniciar temporizador para medir el tiempo de startup
        start_time = time.time()
        
        # Inicializar cliente de Shopify
        shop_url = os.getenv("SHOPIFY_SHOP_URL")
        access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        
        logging.debug(f"SHOPIFY_SHOP_URL: {'configurado' if shop_url else 'no configurado'}")
        logging.debug(f"SHOPIFY_ACCESS_TOKEN: {'configurado' if access_token else 'no configurado'}")

        client = init_shopify()
        
        logging.info("🔄 Loading products...")
        
        # Usar datos de muestra para acelerar el inicio
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        products = SAMPLE_PRODUCTS
        logging.info(f"Loaded {len(SAMPLE_PRODUCTS)} sample products")
        
        # Solo intentar conectar a Shopify y Retail API si no estamos en Cloud Run (evitar timeouts)
        # o si explícitamente está habilitado
        if os.getenv("ENABLE_EXTERNAL_SERVICES", "False").lower() == "true":
            if client:
                logging.info("🔄 Initializing Shopify client...")
                try:
                    shopify_products = client.get_products()
                    logging.info(f"✅ Retrieved {len(shopify_products)} products from Shopify")
                    
                    if shopify_products:
                        products = shopify_products
                        logging.debug(f"First product sample: {products[0]}")
                    else:
                        logging.warning("⚠️ No products retrieved from Shopify")
                        
                except Exception as e:
                    logging.error(f"❌ Error connecting to Shopify: {str(e)}")
            
            # Intentar importar productos a Retail API
            try:
                await retail_recommender.import_catalog(products)
                logging.info("✅ Products imported to Retail API successfully")
            except Exception as e:
                logging.error(f"❌ Error importing to Retail API: {str(e)}")

        # Entrenar recomendador basado en contenido siempre
        try:
            content_recommender.fit(products)
            logging.info("✅ Content-based recommender trained successfully")
        except Exception as e:
            logging.error(f"❌ Error training content recommender: {str(e)}")

        # Reportar tiempo de inicio
        end_time = time.time()
        startup_time = end_time - start_time
        logging.info(f"✅ Application startup completed in {startup_time:.2f} seconds")

    except Exception as e:
        logging.error(f"❌ Critical error during startup: {str(e)}")
        # No bloquear el inicio por errores

# Incluir routers
app.include_router(recommendations.router, prefix="/v1")