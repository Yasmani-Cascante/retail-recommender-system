from fastapi import APIRouter, HTTPException, Depends, Query, Header
from typing import List, Optional, Dict
from src.api.security import get_current_user
from src.api.core.recommenders import hybrid_recommender, content_recommender
from src.api.core.store import get_shopify_client
import math
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)

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
def get_products(
    page: int = Query(1, gt=0),
    page_size: int = Query(50, gt=0, le=100)
):
    """
    Obtiene la lista de productos con paginación.
    """
    client = get_shopify_client()
    if client:
        try:
            all_products = client.get_products()
            total = len(all_products)
            total_pages = math.ceil(total / page_size)
            
            start = (page - 1) * page_size
            end = start + page_size
            
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "products": all_products[start:end]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    from src.api.core.sample_data import SAMPLE_PRODUCTS
    return {
        "total": len(SAMPLE_PRODUCTS),
        "page": 1,
        "page_size": len(SAMPLE_PRODUCTS),
        "total_pages": 1,
        "products": SAMPLE_PRODUCTS
    }

# Recomendaciones por producto
@router.get("/recommendations/{product_id}")
async def get_recommendations(
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    current_user: str = Depends(get_current_user)
):
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
        
        # Obtener productos
        all_products = client.get_products()
        
        # Encontrar el producto específico
        product = next(
            (p for p in all_products if str(p.get('id')) == str(product_id)),
            None
        )
        
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product ID {product_id} not found"
            )
            
        # Entrenar el recomendador si es necesario
        content_recommender.fit(all_products)
        
        # Obtener recomendaciones
        hybrid_recommender.content_weight = content_weight
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id or "anonymous",
            product_id=str(product_id),
            n_recommendations=n
        )
        
        return {
            "product": {
                "id": product.get('id'),
                "title": product.get('title')
            },
            "recommendations": recommendations,
            "metadata": {
                "content_weight": content_weight,
                "total_recommendations": len(recommendations)
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error getting recommendations: {str(e)}")
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
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
            
        logging.info(f"Fetching products for category: {category}")
        products = client.get_products()
        logging.info(f"Retrieved {len(products)} total products")
        
        category_products = [
            p for p in products 
            if p.get("product_type", "").lower() == category.lower()
        ]
        
        logging.info(f"Found {len(category_products)} products in category {category}")
        
        if not category_products:
            raise HTTPException(
                status_code=404,
                detail=f"No products found in category: {category}"
            )
        return category_products
    except Exception as e:
        logging.error(f"Error in category search: {str(e)}")
        if 'products' in locals():
            sample_product = products[0] if products else None
            logging.error(f"Sample product structure: {sample_product}")
        raise HTTPException(status_code=500, detail=str(e))

# Búsqueda de productos
@router.get("/products/search/")
def search_products(
    q: str = Query(..., description="Texto a buscar en nombre o descripción"),
    current_user: str = Depends(get_current_user)
):
    """
    Busca productos por nombre o descripción.
    """
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
            
        all_products = client.get_products()
        logging.info(f"Got {len(all_products)} products from Shopify")
        if all_products:
            logging.info(f"Sample product structure: {all_products[0]}")
            
        q = q.lower()
        matching_products = []
        
        for product in all_products:
            name = str(product.get("title", ""))
            desc = str(product.get("body_html", ""))
            
            if q in name.lower() or q in desc.lower():
                matching_products.append(product)
        
        return matching_products
    except Exception as e:
        logging.error(f"Error searching products: {str(e)}")
        logging.error(f"Products structure: {all_products if 'all_products' in locals() else 'Not loaded'}")
        raise HTTPException(status_code=500, detail=str(e))