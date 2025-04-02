
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
import time
from typing import List, Dict, Optional
import json

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Importar recomendador precomputado
from src.recommenders.precomputed_recommender import PrecomputedEmbeddingRecommender

# Inicializar app
app = FastAPI(
    title="Retail Recommender API (Precomputed)",
    description="API para sistema de recomendaciones con embeddings pre-computados",
    version="0.4.0"
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
recommender = PrecomputedEmbeddingRecommender()

@app.on_event("startup")
async def startup_event():
    start_time = time.time()
    
    # Cargar embeddings precomputados
    logging.info("Cargando embeddings precomputados...")
    success = recommender.fit()
    
    if success:
        logging.info("✅ Embeddings precomputados cargados correctamente")
    else:
        logging.error("❌ Error cargando embeddings precomputados")
    
    end_time = time.time()
    logging.info(f"Startup completado en {end_time - start_time:.2f} segundos")

@app.get("/health")
def health_check():
    return {
        "status": "healthy", 
        "precomputed_recommender": recommender.embeddings is not None,
        "product_count": len(recommender.product_ids) if recommender.product_ids else 0
    }

@app.get("/")
def read_root():
    return {
        "message": "Retail Recommender API con embeddings precomputados",
        "version": "0.4.0",
        "status": "ready" if recommender.embeddings is not None else "initializing"
    }

@app.get("/v1/")
def api_root():
    return {
        "message": "V1 API con embeddings precomputados",
        "version": "0.4.0"
    }

@app.get("/v1/recommendations/content/{product_id}")
def get_content_recommendations(product_id: str, n: int = 5):
    try:
        recommendations = recommender.recommend(product_id, n)
        return {
            "product_id": product_id,
            "recommendations": recommendations,
            "count": len(recommendations)
        }
    except Exception as e:
        logging.error(f"Error en recomendaciones: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/products/")
def get_products(page: int = 1, page_size: int = 10):
    if not recommender.product_metadata:
        return {"products": [], "total": 0, "page": page, "page_size": page_size}
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    products_page = recommender.product_metadata[start_idx:end_idx]
    
    return {
        "products": products_page,
        "total": len(recommender.product_metadata),
        "page": page,
        "page_size": page_size
    }

@app.get("/v1/products/{product_id}")
def get_product(product_id: str):
    product = recommender.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product

# Punto de inicio para ejecución directa (útil para desarrollo local)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main_precomputed:app", host="0.0.0.0", port=port)
