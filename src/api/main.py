from fastapi import FastAPI, HTTPException
from typing import List, Dict, Optional
from src.recommenders.content_based import ContentBasedRecommender

app = FastAPI(
    title="Retail Recommender API",
    description="API para sistema de recomendaciones de retail de ropa",
    version="0.1.0"
)

# Instanciar el recomendador
recommender = ContentBasedRecommender()

# Datos de ejemplo de ropa
SAMPLE_PRODUCTS = [
    {
        "id": "1",
        "name": "Jeans Slim Fit",
        "description": "Jeans ajustados de algodón premium, perfectos para un look casual y moderno. Disponible en azul oscuro con acabado desgastado sutil.",
        "price": 79.99,
        "category": "Pantalones",
        "attributes": {
            "material": "98% Algodón, 2% Elastano",
            "style": "Slim Fit",
            "occasion": ["Casual", "Semi-formal"]
        }
    },
    {
        "id": "2",
        "name": "Camisa Oxford Clásica",
        "description": "Camisa Oxford de corte regular en algodón puro. Perfecta para ocasiones formales o casuales. Diseño clásico con botones en el cuello.",
        "price": 59.99,
        "category": "Camisas",
        "attributes": {
            "material": "100% Algodón",
            "style": "Regular Fit",
            "occasion": ["Formal", "Business", "Casual"]
        }
    },
    {
        "id": "3",
        "name": "Vestido Floral Verano",
        "description": "Vestido ligero con estampado floral, perfecto para el verano. Diseño midi con cintura elástica y volantes en el bajo.",
        "price": 89.99,
        "category": "Vestidos",
        "attributes": {
            "material": "100% Viscosa",
            "style": "A-line",
            "occasion": ["Casual", "Vacaciones"]
        }
    },
    {
        "id": "4",
        "name": "Chaqueta Bomber",
        "description": "Chaqueta bomber ligera con cierre de cremallera. Ideal para looks urbanos y casuales. Incluye bolsillos laterales y puños elásticos.",
        "price": 119.99,
        "category": "Chaquetas",
        "attributes": {
            "material": "Poliéster",
            "style": "Bomber",
            "occasion": ["Casual", "Streetwear"]
        }
    },
    {
        "id": "5",
        "name": "Falda Plisada Midi",
        "description": "Falda plisada de largo midi en tejido ligero. Cintura elástica y diseño versátil que se adapta a cualquier ocasión.",
        "price": 69.99,
        "category": "Faldas",
        "attributes": {
            "material": "Poliéster Plisado",
            "style": "Pleated",
            "occasion": ["Formal", "Casual", "Office"]
        }
    },
    {
        "id": "6",
        "name": "Suéter Cuello Alto",
        "description": "Suéter de punto grueso con cuello alto. Perfecto para el invierno, confeccionado en lana merino de alta calidad.",
        "price": 89.99,
        "category": "Suéteres",
        "attributes": {
            "material": "100% Lana Merino",
            "style": "Turtleneck",
            "occasion": ["Casual", "Winter"]
        }
    }
]

# Entrenar el recomendador con los datos de ejemplo
recommender.fit(SAMPLE_PRODUCTS)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Retail Recommender API"}

@app.get("/products/")
def get_products():
    return SAMPLE_PRODUCTS

@app.get("/recommendations/{product_id}")
def get_recommendations(product_id: str, n: Optional[int] = 5):
    try:
        recommendations = recommender.recommend(product_id, n_recommendations=n)
        return recommendations
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products/category/{category}")
def get_products_by_category(category: str):
    category_products = [p for p in SAMPLE_PRODUCTS if p["category"].lower() == category.lower()]
    if not category_products:
        raise HTTPException(status_code=404, detail=f"No products found in category: {category}")
    return category_products

@app.get("/products/search/")
def search_products(q: str):
    """
    Busca productos por nombre o descripción
    """
    q = q.lower()
    matching_products = [
        p for p in SAMPLE_PRODUCTS 
        if q in p["name"].lower() or q in p["description"].lower()
    ]
    return matching_products