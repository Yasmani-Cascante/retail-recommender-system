from fastapi import FastAPI, HTTPException, Header, Query
from typing import List, Dict, Optional
from src.recommenders.content_based import ContentBasedRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from src.recommenders.hybrid import HybridRecommender
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = FastAPI(
    title="Retail Recommender API",
    description="API para sistema de recomendaciones híbrido de retail usando Google Cloud Retail API",
    version="0.3.0"
)

# Configuración de Google Cloud Retail API
GOOGLE_PROJECT_NUMBER = os.getenv("GOOGLE_PROJECT_NUMBER")
GOOGLE_LOCATION = os.getenv("GOOGLE_LOCATION", "global")
GOOGLE_CATALOG = os.getenv("GOOGLE_CATALOG", "default_catalog")
GOOGLE_SERVING_CONFIG = os.getenv("GOOGLE_SERVING_CONFIG", "default_config")

# Instanciar recomendadores
content_recommender = ContentBasedRecommender()
retail_recommender = RetailAPIRecommender(
    project_number=GOOGLE_PROJECT_NUMBER,
    location=GOOGLE_LOCATION,
    catalog=GOOGLE_CATALOG,
    serving_config_id=GOOGLE_SERVING_CONFIG
)
hybrid_recommender = HybridRecommender(
    content_recommender=content_recommender,
    retail_recommender=retail_recommender,
    content_weight=0.5
)

# Datos de ejemplo de ropa
SAMPLE_PRODUCTS = [
    {
        "id": "1",
        "name": "Jeans Slim Fit Premium",
        "description": "Jeans ajustados de algodón premium, perfectos para un look casual y moderno. Disponible en azul oscuro con acabado desgastado sutil. Corte que estiliza la figura y proporciona máxima comodidad.",
        "price": 79.99,
        "category": "Pantalones",
        "attributes": {
            "material": "98% Algodón, 2% Elastano",
            "style": "Slim Fit",
            "occasion": ["Casual", "Semi-formal"],
            "color": "Azul oscuro"
        }
    },
    {
        "id": "2",
        "name": "Camisa Oxford Clásica",
        "description": "Camisa Oxford de corte regular en algodón puro. Perfecta para ocasiones formales o casuales. Diseño clásico con botones en el cuello y acabado de alta calidad que asegura durabilidad.",
        "price": 59.99,
        "category": "Camisas",
        "attributes": {
            "material": "100% Algodón",
            "style": "Regular Fit",
            "occasion": ["Formal", "Business", "Casual"],
            "color": "Blanco"
        }
    },
    {
        "id": "3",
        "name": "Vestido Floral Verano",
        "description": "Vestido ligero con estampado floral, perfecto para días soleados. Diseño midi con vuelo y cintura elástica que favorece todo tipo de siluetas. Tejido fresco y transpirable.",
        "price": 89.99,
        "category": "Vestidos",
        "attributes": {
            "material": "100% Viscosa",
            "style": "A-Line",
            "occasion": ["Casual", "Vacation"],
            "color": "Multicolor"
        }
    },
    {
        "id": "4",
        "name": "Blazer Estructurado",
        "description": "Blazer elegante de corte moderno con hombreras suaves. Ideal para looks profesionales y eventos formales. Forro interior completo y botones premium.",
        "price": 129.99,
        "category": "Chaquetas",
        "attributes": {
            "material": "95% Poliéster, 5% Elastano",
            "style": "Fitted",
            "occasion": ["Formal", "Business"],
            "color": "Negro"
        }
    },
    {
        "id": "5",
        "name": "Suéter Cashmere Cuello Alto",
        "description": "Suéter de cashmere puro con cuello alto. Extraordinariamente suave y cálido, perfecto para el invierno. Tejido de primera calidad que mantiene su forma lavado tras lavado.",
        "price": 149.99,
        "category": "Sweaters",
        "attributes": {
            "material": "100% Cashmere",
            "style": "Turtleneck",
            "occasion": ["Casual", "Semi-formal"],
            "color": "Gris melange"
        }
    },
    {
        "id": "6",
        "name": "Falda Plisada Midi",
        "description": "Falda plisada a media pierna con cintura elástica. Movimiento elegante y caída perfecta. Versátil para combinar con cualquier top y perfecta para todas las temporadas.",
        "price": 69.99,
        "category": "Faldas",
        "attributes": {
            "material": "100% Poliéster",
            "style": "Pleated",
            "occasion": ["Formal", "Casual", "Office"],
            "color": "Navy"
        }
    },
    {
        "id": "7",
        "name": "Camiseta Básica Premium",
        "description": "Camiseta básica de algodón peinado de alta calidad. Corte relajado pero favorecedor, perfecta como prenda básica o para layering. Cuello redondo reforzado.",
        "price": 29.99,
        "category": "Camisetas",
        "attributes": {
            "material": "100% Algodón Peinado",
            "style": "Regular",
            "occasion": ["Casual"],
            "color": "Blanco"
        }
    },
    {
        "id": "8",
        "name": "Pantalón Chino Slim",
        "description": "Pantalón chino de corte slim en algodón stretch. Versátil y cómodo, ideal para el día a día en la oficina o salidas casuales. Acabado suave al tacto y resistente a las arrugas.",
        "price": 69.99,
        "category": "Pantalones",
        "attributes": {
            "material": "97% Algodón, 3% Elastano",
            "style": "Slim Fit",
            "occasion": ["Casual", "Business Casual"],
            "color": "Beige"
        }
    },
    {
        "id": "9",
        "name": "Blusa Seda Elegante",
        "description": "Blusa de seda natural con detalle de lazo en el cuello. Corte fluido que favorece todo tipo de siluetas. Perfecta para eventos especiales o para elevar un look de oficina.",
        "price": 109.99,
        "category": "Blusas",
        "attributes": {
            "material": "100% Seda",
            "style": "Bow-neck",
            "occasion": ["Formal", "Business", "Evening"],
            "color": "Marfil"
        }
    },
    {
        "id": "10",
        "name": "Chaqueta Vaquera Vintage",
        "description": "Chaqueta vaquera con lavado vintage y detalles desgastados. Corte clásico ligeramente oversized. Perfecta para dar un toque casual a cualquier outfit.",
        "price": 89.99,
        "category": "Chaquetas",
        "attributes": {
            "material": "100% Algodón",
            "style": "Oversized",
            "occasion": ["Casual"],
            "color": "Azul medio"
        }
    }
    
]

# Entrenar el recomendador basado en contenido e importar productos a Retail API
@app.on_event("startup")
async def startup_event():
    # Entrenar recomendador basado en contenido
    content_recommender.fit(SAMPLE_PRODUCTS)
    
    # Importar productos a Retail API
    await retail_recommender.import_catalog(SAMPLE_PRODUCTS)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to the Retail Recommender API",
        "version": "0.3.0",
        "docs_url": "/docs"
    }

@app.get("/products/")
def get_products():
    """
    Obtiene la lista completa de productos disponibles.
    """
    return SAMPLE_PRODUCTS

@app.get("/recommendations/{product_id}")
async def get_recommendations(
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0)
):
    """
    Obtiene recomendaciones híbridas para un producto.
    Si se proporciona user_id, incluye recomendaciones personalizadas.
    """
    try:
        # Ajustar el peso del contenido si se especifica
        hybrid_recommender.content_weight = content_weight
        
        # Obtener recomendaciones
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id or "anonymous",
            product_id=product_id,
            n_recommendations=n
        )
        
        return {
            "recommendations": recommendations,
            "metadata": {
                "content_weight": content_weight,
                "retail_weight": 1 - content_weight,
                "user_id": user_id or "anonymous",
                "total_recommendations": len(recommendations)
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/recommendations/user/{user_id}")
async def get_user_recommendations(
    user_id: str,
    n: Optional[int] = Query(5, gt=0, le=20)
):
    """
    Obtiene recomendaciones personalizadas para un usuario basadas en su historial.
    """
    try:
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=n
        )
        return {
            "recommendations": recommendations,
            "metadata": {
                "user_id": user_id,
                "total_recommendations": len(recommendations)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/events/user/{user_id}")
async def record_user_event(
    user_id: str,
    event_type: str = Query(..., description="Tipo de evento (view, add-to-cart, purchase)"),
    product_id: Optional[str] = None
):
    """
    Registra eventos de usuario para mejorar las recomendaciones futuras.
    """
    try:
        result = await hybrid_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products/category/{category}")
def get_products_by_category(category: str):
    """
    Obtiene productos filtrados por categoría.
    """
    category_products = [
        p for p in SAMPLE_PRODUCTS 
        if p["category"].lower() == category.lower()
    ]
    if not category_products:
        raise HTTPException(
            status_code=404,
            detail=f"No products found in category: {category}"
        )
    return category_products

@app.get("/products/search/")
def search_products(
    q: str = Query(..., description="Texto a buscar en nombre o descripción")
):
    """
    Busca productos por nombre o descripción.
    """
    q = q.lower()
    matching_products = [
        p for p in SAMPLE_PRODUCTS 
        if q in p["name"].lower() or q in p["description"].lower()
    ]
    return matching_products