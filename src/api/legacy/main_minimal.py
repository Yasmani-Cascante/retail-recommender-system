from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from typing import List, Dict, Optional

# Configurar logging con más detalle
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Aplicación FastAPI minimalista
app = FastAPI(
    title="Retail Recommender API (Minimal)",
    description="Versión simplificada para Cloud Run",
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

# Verificación de salud
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API is running"}

# Ruta raíz
@app.get("/")
def read_root():
    return {
        "message": "Welcome to the Retail Recommender API (Minimal Version)",
        "version": "0.4.0",
        "endpoints": [
            "/health",
            "/v1/",
            "/v1/products/",
            "/v1/recommendations/simple/{product_id}"
        ]
    }

# Definir algunos datos de muestra
SAMPLE_PRODUCTS = [
    {
        "id": "1",
        "title": "T-Shirt",
        "description": "Basic cotton t-shirt",
        "price": 19.99,
        "category": "Clothing"
    },
    {
        "id": "2",
        "title": "Jeans",
        "description": "Comfortable denim jeans",
        "price": 49.99,
        "category": "Clothing"
    },
    {
        "id": "3",
        "title": "Sneakers",
        "description": "Casual sneakers",
        "price": 79.99,
        "category": "Footwear"
    }
]

# Router simple
@app.get("/v1/")
def api_root():
    return {
        "message": "Welcome to the Retail Recommender API (Minimal)",
        "version": "0.4.0"
    }

# Listado de productos simplificado
@app.get("/v1/products/")
def get_products():
    return {"products": SAMPLE_PRODUCTS}

# Recomendaciones simplificadas
@app.get("/v1/recommendations/simple/{product_id}")
def get_simple_recommendations(product_id: str):
    # Simular recomendaciones sin usar modelos pesados
    recommendations = [p for p in SAMPLE_PRODUCTS if p["id"] != product_id][:2]
    
    return {
        "product_id": product_id,
        "recommendations": recommendations,
        "message": "These are mock recommendations for testing Cloud Run deployment"
    }

# Punto de inicio para Cloud Run
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main_minimal:app", host="0.0.0.0", port=port)
