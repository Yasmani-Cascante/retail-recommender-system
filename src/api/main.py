from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.middleware.logging import LoggingMiddleware
from src.api.routers import recommendations
from src.api.core.recommenders import content_recommender, retail_recommender
from src.api.integrations.shopify_client import ShopifyIntegration
import os
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Cargar variables de entorno
load_dotenv()

app = FastAPI(
    title="Retail Recommender API",
    description="API para sistema de recomendaciones híbrido de retail usando Google Cloud Retail API",
    version="0.3.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Añadir middleware de logging
app.add_middleware(LoggingMiddleware)

# Inicializar cliente de Shopify
shopify_client = None

# Startup Event
@app.on_event("startup")
async def startup_event():
    try:
        global shopify_client
        # Inicializar cliente de Shopify
        shop_url = os.getenv("SHOPIFY_SHOP_URL")
        access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        
        if not shop_url or not access_token:
            logging.warning("Shopify credentials not found. Using sample data.")
            from src.api.core.sample_data import SAMPLE_PRODUCTS
            products = SAMPLE_PRODUCTS
        else:
            logging.info("Initializing Shopify client...")
            shopify_client = ShopifyIntegration(shop_url=shop_url, access_token=access_token)
            products = shopify_client.get_products()
            logging.info(f"Retrieved {len(products)} products from Shopify")

        # Entrenar recomendador basado en contenido
        content_recommender.fit(products)
        logging.info("Content-based recommender trained successfully")
        
        # Importar productos a Retail API
        await retail_recommender.import_catalog(products)
        logging.info("Products imported to Retail API successfully")

    except Exception as e:
        logging.error(f"Error during startup: {str(e)}")
        # En caso de error, usar datos de ejemplo
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        content_recommender.fit(SAMPLE_PRODUCTS)
        await retail_recommender.import_catalog(SAMPLE_PRODUCTS)

# Incluir routers
app.include_router(recommendations.router, prefix="/v1")