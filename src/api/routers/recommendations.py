from fastapi import APIRouter, HTTPException, Depends, Query, Header, Request
from typing import List, Optional, Dict
from src.api.security import get_current_user
from src.api.core.recommenders import hybrid_recommender, content_recommender, retail_recommender
from src.api.core.store import get_shopify_client
from src.api.core.metrics import recommendation_metrics, time_function
import math
import logging
import time


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
    request: Request,
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    current_user: str = Depends(get_current_user)
):
    start_time = time.time()
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
            n_recommendations=n,
            exclude_seen=True  # Excluir productos vistos por defecto
        )
        
        # Registrar métricas
        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000
        
        # Registrar métricas para esta solicitud
        recommendation_metrics.record_recommendation_request(
            request_data={
                "product_id": product_id,
                "n": n,
                "content_weight": content_weight,
                "exclude_seen": True
            },
            recommendations=recommendations,
            response_time_ms=response_time_ms,
            user_id=user_id or "anonymous",
            product_id=product_id
        )
        
        response = {
            "product": {
                "id": product.get('id'),
                "title": product.get('title')
            },
            "recommendations": recommendations,
            "metadata": {
                "content_weight": content_weight,
                "total_recommendations": len(recommendations),
                "took_ms": response_time_ms,
                "source": "hybrid_tfidf_product"
            }
        }
        
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error getting recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Listar clientes
@router.get("/customers/")
async def get_customers(
    current_user: str = Depends(get_current_user)
):
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
            
        customers = client.get_customers()
        
        if not customers:
            logging.warning("No customers found")
            return {
                "total": 0,
                "customers": []
            }
            
        return {
            "total": len(customers),
            "customers": customers
        }
    except Exception as e:
        logging.error(f"Error fetching customers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Recomendaciones por usuario
@router.get("/recommendations/user/{user_id}")
async def get_user_recommendations(
    request: Request,
    user_id: str,
    n: Optional[int] = Query(5, gt=0, le=20),
    current_user: str = Depends(get_current_user)
):
    start_time = time.time()
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
        
        logging.info(f"Getting recommendations for user {user_id}")
        
        # Obtener productos y órdenes del usuario
        all_products = client.get_products()
        user_orders = client.get_orders_by_customer(user_id)
        
        if not user_orders:
            logging.info(f"No order history found for user {user_id}")
        else:
            logging.info(f"Found {len(user_orders)} orders for user {user_id}")
        
        # Entrenar el recomendador con productos actuales
        content_recommender.fit(all_products)
        
        # Importar productos a Google Cloud Retail API
        try:
            logging.info("Importing products to Google Cloud Retail API")
            import_result = await retail_recommender.import_catalog(all_products)
            logging.info(f"Import result: {import_result}")
        except Exception as e:
            logging.error(f"Error importing products: {e}")
        
        # Obtener recomendaciones
        logging.info("Getting recommendations from hybrid recommender")
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=n,
            exclude_seen=True  # Excluir productos vistos por defecto
        )
        
        if not recommendations:
            logging.warning(f"No recommendations generated for user {user_id}")
            
        # Registrar métricas
        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000
        
        # Registrar métricas para esta solicitud
        recommendation_metrics.record_recommendation_request(
            request_data={
                "n": n,
                "exclude_seen": True
            },
            recommendations=recommendations,
            response_time_ms=response_time_ms,
            user_id=user_id,
            product_id=None
        )
        
        return {
            "recommendations": recommendations,
            "metadata": {
                "user_id": user_id,
                "total_recommendations": len(recommendations),
                "total_orders": len(user_orders),
                "source": "hybrid_tfidf_user",
                "took_ms": response_time_ms
            }
        }
    except Exception as e:
        logging.error(f"Error getting recommendations for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting recommendations: {str(e)}"
        )

# Registrar eventos de usuario
@router.post("/events/user/{user_id}")
async def record_user_event(
    user_id: str,
    event_type: str = Query(..., description="Tipo de evento (detail-page-view, add-to-cart, purchase-complete, etc.)"),
    product_id: Optional[str] = None,
    recommendation_id: Optional[str] = Query(None, description="ID de la recomendación si el producto fue recomendado"),
    current_user: str = Depends(get_current_user)
):
    """
    Registra eventos de usuario para mejorar las recomendaciones futuras.
    
    Tipos de eventos válidos:
    - detail-page-view: Vista de detalle del producto
    - add-to-cart: Añadir al carrito
    - purchase-complete: Compra completada
    - home-page-view: Vista de página principal
    - category-page-view: Vista de página de categoría
    - search: Búsqueda de productos
    """
    start_time = time.time()
    try:
        # Validar tipo de evento
        valid_event_types = [
            "detail-page-view", "add-to-cart", "purchase-complete", 
            "home-page-view", "category-page-view", "search"
        ]
        
        # Mapeo de tipos alternativos
        event_type_mapping = {
            "view": "detail-page-view",
            "detail-page": "detail-page-view",
            "add": "add-to-cart",
            "cart": "add-to-cart",
            "purchase": "purchase-complete",
            "buy": "purchase-complete",
            "checkout": "purchase-complete",
            "home": "home-page-view",
            "category": "category-page-view",
            "promo": "category-page-view"
        }
        
        # Convertir tipos alternativos a tipos estándar
        if event_type in event_type_mapping:
            mapped_event_type = event_type_mapping[event_type]
            logging.info(f"Mapeando tipo de evento alternativo '{event_type}' a '{mapped_event_type}'")
            event_type = mapped_event_type
        
        # Si sigue sin ser válido, usar detail-page-view por defecto
        if event_type not in valid_event_types:
            logging.warning(f"Tipo de evento no válido '{event_type}', usando 'detail-page-view'")
            event_type = "detail-page-view"
        
        # Registrar evento en Retail API
        result = await hybrid_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id,
            recommendation_id=recommendation_id
        )
        
        # Registrar métrica de interacción
        recommendation_metrics.record_user_interaction(
            user_id=user_id,
            product_id=product_id,
            event_type=event_type,
            recommendation_id=recommendation_id
        )
        
        # Añadir información útil a la respuesta
        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000
        
        return {
            "status": "success",
            "message": "Event recorded",
            "event_type": event_type,
            "detail": {
                "user_id": user_id,
                "event_type": event_type,
                "product_id": product_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%f"),
                "note": "El evento fue registrado correctamente y ayudará a mejorar las recomendaciones futuras."
            }
        }
        
    except Exception as e:
        logging.error(f"Error al registrar evento de usuario: {str(e)}")
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


# Obtener métricas del sistema de recomendaciones
@router.get("/metrics")
async def get_recommendation_metrics(
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene métricas agregadas sobre la calidad y rendimiento del sistema de recomendaciones.
    """
    try:
        # Obtener métricas agregadas
        metrics = recommendation_metrics.get_aggregated_metrics()
        
        # Analizar archivo de métricas si existe
        file_metrics = {}
        try:
            from src.api.core.metrics import analyze_metrics_file
            file_analysis = analyze_metrics_file()
            if file_analysis.get("status") == "success":
                file_metrics = file_analysis
        except Exception as file_error:
            logging.warning(f"No se pudo analizar el archivo de métricas: {str(file_error)}")
        
        return {
            "status": "success",
            "realtime_metrics": metrics,
            "historical_metrics": file_metrics,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    except Exception as e:
        logging.error(f"Error al obtener métricas: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener métricas: {str(e)}"
        )