from fastapi import APIRouter, HTTPException, Depends, Query, Header
from typing import List, Optional, Dict
from src.api.security import get_current_user
from src.api.core.recommenders import hybrid_recommender
from src.api.core.sample_data import SAMPLE_PRODUCTS

router = APIRouter()

# Ruta raíz
@router.get("/")
def read_root():
    return {
        "message": "Welcome to the Retail Recommender API",
        "version": "0.3.0",
        "docs_url": "/docs"
    }

# Listar productos
@router.get("/products/")
def get_products():
    """
    Obtiene la lista completa de productos disponibles.
    """
    return SAMPLE_PRODUCTS

# Recomendaciones por producto
@router.get("/recommendations/{product_id}")
async def get_recommendations(
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    current_user: str = Depends(get_current_user)
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

# Recomendaciones por usuario
@router.get("/recommendations/user/{user_id}")
async def get_user_recommendations(
    user_id: str,
    n: Optional[int] = Query(5, gt=0, le=20),
    current_user: str = Depends(get_current_user)
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

# Registrar eventos de usuario
@router.post("/events/user/{user_id}")
async def record_user_event(
    user_id: str,
    event_type: str = Query(..., description="Tipo de evento (view, add-to-cart, purchase)"),
    product_id: Optional[str] = None,
    current_user: str = Depends(get_current_user)
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

# Productos por categoría
@router.get("/products/category/{category}")
def get_products_by_category(
    category: str,
    current_user: str = Depends(get_current_user)
):
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

# Búsqueda de productos
@router.get("/products/search/")
def search_products(
    q: str = Query(..., description="Texto a buscar en nombre o descripción"),
    current_user: str = Depends(get_current_user)
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