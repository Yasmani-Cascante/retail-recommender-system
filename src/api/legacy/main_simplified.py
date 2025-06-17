
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
import time
from typing import List, Dict, Optional
import json

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Importar recomendador simplificado
from src.recommenders.simple_tfidf_recommender import SimpleTFIDFRecommender

# Inicializar app
app = FastAPI(
    title="Retail Recommender API (Simplified)",
    description="API para sistema de recomendaciones simplificado",
    version="0.7.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar recomendador
recommender = SimpleTFIDFRecommender()

# Variable para medir tiempo de inicialización
startup_time = None

# Datos de muestra para caso de fallo
SAMPLE_PRODUCTS = [
    {
        "id": "1",
        "title": "T-Shirt",
        "body_html": "Basic cotton t-shirt",
        "price": 19.99,
        "product_type": "Clothing",
        "variants": [{"price": "19.99"}]
    },
    {
        "id": "2",
        "title": "Jeans",
        "body_html": "Comfortable denim jeans",
        "price": 49.99,
        "product_type": "Clothing",
        "variants": [{"price": "49.99"}]
    },
    {
        "id": "3",
        "title": "Sneakers",
        "body_html": "Casual sneakers",
        "price": 79.99,
        "product_type": "Footwear",
        "variants": [{"price": "79.99"}]
    },
    {
        "id": "4",
        "title": "Hoodie",
        "body_html": "Warm winter hoodie",
        "price": 39.99,
        "product_type": "Clothing",
        "variants": [{"price": "39.99"}]
    },
    {
        "id": "5",
        "title": "Backpack",
        "body_html": "Durable backpack for daily use",
        "price": 59.99,
        "product_type": "Accessories",
        "variants": [{"price": "59.99"}]
    }
]

@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicación"""
    global startup_time
    
    start_time = time.time()
    logging.info("🚀 Iniciando API simplificada...")
    
    # Intentar cargar productos de Shopify
    try:
        from src.api.core.store import init_shopify
        
        client = init_shopify()
        if client:
            logging.info("✅ Cliente Shopify inicializado correctamente")
            products = client.get_products()
            logging.info(f"✅ {len(products)} productos cargados desde Shopify")
        else:
            logging.warning("⚠️ No se pudo inicializar cliente Shopify, usando datos de muestra")
            products = SAMPLE_PRODUCTS
    except Exception as e:
        logging.error(f"❌ Error cargando productos: {str(e)}")
        logging.warning("⚠️ Usando datos de muestra")
        products = SAMPLE_PRODUCTS
    
    # Entrenar recomendador
    logging.info("⏳ Entrenando recomendador TF-IDF...")
    success = recommender.fit(products)
    
    if success:
        logging.info("✅ Recomendador TF-IDF entrenado correctamente")
    else:
        logging.error("❌ Error entrenando recomendador TF-IDF")
    
    end_time = time.time()
    startup_time = end_time - start_time
    logging.info(f"✅ Startup completado en {startup_time:.2f} segundos")

@app.get("/health")
def health_check():
    """
    Endpoint para verificar el estado del sistema.
    Incluye información sobre el recomendador.
    """
    return {
        "status": "healthy", 
        "version": "0.7.0",
        "startup_time": startup_time,
        "recommender": {
            "initialized": recommender.tfidf_matrix is not None,
            "product_count": len(recommender.product_ids) if recommender.product_ids else 0,
            "type": "TF-IDF (simplified)"
        }
    }

@app.get("/")
def read_root():
    """Endpoint raíz con información básica de la API"""
    return {
        "message": "Retail Recommender API (Simplified)",
        "version": "0.7.0",
        "status": "ready" if recommender.tfidf_matrix is not None else "initializing",
        "endpoints": [
            "/health",
            "/v1/",
            "/v1/products/",
            "/v1/recommendations/content/{product_id}"
        ]
    }

@app.get("/v1/")
def api_root():
    """Endpoint raíz de la API v1"""
    return {
        "message": "V1 API simplificada",
        "version": "0.7.0"
    }

@app.get("/v1/recommendations/content/{product_id}")
def get_content_recommendations(product_id: str, n: int = 5):
    """
    Obtiene recomendaciones basadas en contenido para un producto.
    
    Args:
        product_id: ID del producto base para las recomendaciones
        n: Número de recomendaciones a devolver
        
    Returns:
        dict: Recomendaciones para el producto
    """
    try:
        # Verificar que el recomendador esté inicializado
        if not recommender.tfidf_matrix:
            raise HTTPException(
                status_code=503,
                detail="Recomendador no inicializado"
            )
        
        # Obtener recomendaciones
        recommendations = recommender.recommend(product_id, n)
        
        # Si no hay recomendaciones, devolver error
        if not recommendations:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontraron recomendaciones para el producto {product_id}"
            )
        
        return {
            "product_id": product_id,
            "recommendations": recommendations,
            "count": len(recommendations)
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error en recomendaciones para producto {product_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/products/")
def get_products(page: int = 1, page_size: int = 10):
    """
    Obtiene una lista paginada de productos.
    
    Args:
        page: Número de página
        page_size: Tamaño de la página
        
    Returns:
        dict: Productos paginados
    """
    # Verificar que haya productos
    if not recommender.product_data:
        return {"products": [], "total": 0, "page": page, "page_size": page_size}
    
    # Calcular índices de paginación
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    # Obtener página de productos
    products_page = recommender.product_data[start_idx:end_idx]
    
    return {
        "products": products_page,
        "total": len(recommender.product_data),
        "page": page,
        "page_size": page_size
    }

@app.get("/v1/products/{product_id}")
def get_product(product_id: str):
    """
    Obtiene detalles de un producto específico.
    
    Args:
        product_id: ID del producto
        
    Returns:
        dict: Detalles del producto
    """
    product = recommender.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product

# Punto de inicio para ejecución directa (útil para desarrollo local)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main_simplified:app", host="0.0.0.0", port=port)
