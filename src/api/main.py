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

# Startup Event
@app.on_event("startup")
async def startup_event():
    try:
        # Iniciar temporizador para medir el tiempo de startup
        start_time = time.time()
        
        # Inicializar cliente de Shopify
        shop_url = os.getenv("SHOPIFY_SHOP_URL")
        access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        
        # Verificar configuración de GCS
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        use_gcs = os.getenv("USE_GCS_IMPORT", "False").lower() == "true"
        
        logging.debug(f"SHOPIFY_SHOP_URL: {'configurado' if shop_url else 'no configurado'}")
        logging.debug(f"SHOPIFY_ACCESS_TOKEN: {'configurado' if access_token else 'no configurado'}")
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
                    logging.debug(f"First product sample: {products[0]}")
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

        # Registrar tiempo total de startup
        end_time = time.time()
        logging.info(f"✅ Startup completed in {end_time - start_time:.2f} seconds")

    except Exception as e:
        logging.error(f"❌ Critical error during startup: {str(e)}")
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        content_recommender.fit(SAMPLE_PRODUCTS)
        await retail_recommender.import_catalog(SAMPLE_PRODUCTS)

# Incluir routers
app.include_router(recommendations.router, prefix="/v1")