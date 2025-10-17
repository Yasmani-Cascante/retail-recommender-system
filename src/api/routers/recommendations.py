# src/api/routers/recommendations.py
"""
Recommendations Router - MIGRATED TO FASTAPI DEPENDENCY INJECTION
==================================================================

Este router proporciona endpoints para:
- Recomendaciones por producto
- Recomendaciones por usuario
- Registro de eventos de usuario
- Búsqueda y listado de productos

MIGRATION STATUS: ✅ Phase 2 Day 2 Complete
- Migrated from global imports to FastAPI DI
- Using dependency injection for all recommenders
- Backward compatible
- Zero breaking changes

Author: Senior Architecture Team
Version: 2.0.0 - FastAPI DI Migration
Date: 2025-10-16
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Header, Request
from typing import List, Optional, Dict
import math
import logging
import time

# ============================================================================
# FASTAPI DEPENDENCY INJECTION - NEW PATTERN
# ============================================================================

from src.api.dependencies import (
    get_tfidf_recommender,
    get_retail_recommender,
    get_hybrid_recommender
)

# Type hints for better IDE support
from src.recommenders.tfidf_recommender import TFIDFRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from src.api.core.hybrid_recommender import HybridRecommender

# ============================================================================
# LEGACY IMPORTS - KEPT FOR REFERENCE (can be removed after validation)
# ============================================================================

# ❌ OLD PATTERN: Global variable imports (DEPRECATED)
# from src.api.core.recommenders import hybrid_recommender, content_recommender, retail_recommender

# ============================================================================
# OTHER IMPORTS (unchanged)
# ============================================================================

from src.api.security import get_current_user
from src.api.core.store import get_shopify_client
from src.api.core.metrics import recommendation_metrics, time_function

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# SIMPLE ENDPOINTS (No changes needed - don't use recommenders)
# ============================================================================

@router.get("/")
def read_root():
    """
    Root endpoint - API information.
    
    Returns basic API information and version.
    """
    return {
        "message": "Welcome to the Retail Recommender API",
        "version": "2.0.0",  # ✅ Updated version (FastAPI DI)
        "docs_url": "/docs",
        "migration_status": "FastAPI Dependency Injection - Phase 2 Complete"
    }


@router.get("/products/")
def get_products(
    page: int = Query(1, gt=0),
    page_size: int = Query(50, gt=0, le=100)
):
    """
    Obtiene la lista de productos con paginación.
    
    Args:
        page: Número de página (empezando en 1)
        page_size: Cantidad de productos por página (máximo 100)
    
    Returns:
        Dict con total, page, page_size, total_pages, y lista de products
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


@router.get("/customers/")
async def get_customers(
    current_user: str = Depends(get_current_user)
):
    """
    Lista todos los clientes de Shopify.
    
    Returns:
        Dict con total y lista de customers
    """
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
            
        customers = client.get_customers()
        
        if not customers:
            logger.warning("No customers found")
            return {
                "total": 0,
                "customers": []
            }
            
        return {
            "total": len(customers),
            "customers": customers
        }
    except Exception as e:
        logger.error(f"Error fetching customers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/category/{category}")
def get_products_by_category(
    category: str,
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene productos filtrados por categoría.
    
    Args:
        category: Nombre de la categoría a filtrar
    
    Returns:
        Lista de productos en la categoría
    """
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
            
        logger.info(f"Fetching products for category: {category}")
        products = client.get_products()
        logger.info(f"Retrieved {len(products)} total products")
        
        category_products = [
            p for p in products 
            if p.get("product_type", "").lower() == category.lower()
        ]
        
        logger.info(f"Found {len(category_products)} products in category {category}")
        
        if not category_products:
            raise HTTPException(
                status_code=404,
                detail=f"No products found in category: {category}"
            )
        return category_products
    except Exception as e:
        logger.error(f"Error in category search: {str(e)}")
        if 'products' in locals():
            sample_product = products[0] if products else None
            logger.error(f"Sample product structure: {sample_product}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/search/")
def search_products(
    q: str = Query(..., description="Texto a buscar en nombre o descripción"),
    current_user: str = Depends(get_current_user)
):
    """
    Busca productos por nombre o descripción.
    
    Args:
        q: Query string para búsqueda
    
    Returns:
        Lista de productos que coinciden con la búsqueda
    """
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
            
        all_products = client.get_products()
        logger.info(f"Got {len(all_products)} products from Shopify")
        if all_products:
            logger.info(f"Sample product structure: {all_products[0]}")
            
        q = q.lower()
        matching_products = []
        
        for product in all_products:
            name = str(product.get("title", ""))
            desc = str(product.get("body_html", ""))
            
            if q in name.lower() or q in desc.lower():
                matching_products.append(product)
        
        return matching_products
    except Exception as e:
        logger.error(f"Error searching products: {str(e)}")
        logger.error(f"Products structure: {all_products if 'all_products' in locals() else 'Not loaded'}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_recommendation_metrics(
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene métricas agregadas sobre la calidad y rendimiento del sistema de recomendaciones.
    
    Returns:
        Dict con métricas realtime e históricas
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
            logger.warning(f"No se pudo analizar el archivo de métricas: {str(file_error)}")
        
        return {
            "status": "success",
            "realtime_metrics": metrics,
            "historical_metrics": file_metrics,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    except Exception as e:
        logger.error(f"Error al obtener métricas: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener métricas: {str(e)}"
        )


# ============================================================================
# MIGRATED ENDPOINTS - USING FASTAPI DEPENDENCY INJECTION
# ============================================================================

@router.get("/recommendations/{product_id}")
async def get_recommendations(
    request: Request,
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    current_user: str = Depends(get_current_user),
    # ✅ NEW: FastAPI Dependency Injection
    tfidf_recommender: TFIDFRecommender = Depends(get_tfidf_recommender),
    hybrid_recommender: HybridRecommender = Depends(get_hybrid_recommender)
):
    """
    Obtiene recomendaciones para un producto específico.
    
    MIGRATED: ✅ Using FastAPI Dependency Injection (Phase 2)
    
    Args:
        request: FastAPI request object
        product_id: ID del producto para el cual se generan recomendaciones
        user_id: ID del usuario (opcional) para personalización
        n: Número de recomendaciones a retornar (1-20, default: 5)
        content_weight: Peso del content-based filtering (0-1, default: 0.5)
        current_user: Usuario autenticado (via Depends)
        tfidf_recommender: TF-IDF recommender (via Depends) ✅ NEW
        hybrid_recommender: Hybrid recommender (via Depends) ✅ NEW
    
    Returns:
        Dict con product info, recommendations, y metadata
    
    Notes:
        - Si user_id es provisto y válido, usa sistema híbrido completo
        - Si user_id no provisto o anonymous, usa solo TF-IDF (más eficiente)
        - Registra métricas de performance y calidad
    """
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
            
        # ✅ UPDATED: Usar tfidf_recommender inyectado (en lugar de content_recommender global)
        # Entrenar el recomendador si es necesario
        tfidf_recommender.fit(all_products)
        
        # ✅ LOGÍCA INTELIGENTE: Solo usar Google Retail API con usuarios reales identificados
        effective_user_id = user_id if user_id and user_id.strip() and user_id != "anonymous" else None
        
        if effective_user_id:
            logger.info(f"[HYBRID] Usuario identificado: {effective_user_id} - usando sistema híbrido completo")
            # ✅ UPDATED: Usar hybrid_recommender inyectado
            recommendations = await hybrid_recommender.get_recommendations(
                user_id=effective_user_id,
                product_id=str(product_id),
                n_recommendations=n,
                exclude_seen=True  # Excluir productos vistos por defecto
            )
        else:
            logger.info(f"[HYBRID] Usuario no identificado - usando solo TF-IDF para mayor eficiencia")
            # ✅ UPDATED: Usar tfidf_recommender inyectado
            # Solo usar recomendaciones basadas en contenido (más eficiente)
            content_recommendations = tfidf_recommender.get_recommendations(
                product_id=str(product_id), 
                n_recommendations=n
            )
            recommendations = content_recommendations
        
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
            user_id=effective_user_id or "anonymous",
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
                "source": "hybrid_tfidf_product",
                "di_migration": "phase2_complete"  # ✅ NEW: Migration flag
            }
        }
        
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations/user/{user_id}")
async def get_user_recommendations(
    request: Request,
    user_id: str,
    n: Optional[int] = Query(5, gt=0, le=20),
    current_user: str = Depends(get_current_user),
    # ✅ NEW: FastAPI Dependency Injection
    tfidf_recommender: TFIDFRecommender = Depends(get_tfidf_recommender),
    retail_recommender: RetailAPIRecommender = Depends(get_retail_recommender),
    hybrid_recommender: HybridRecommender = Depends(get_hybrid_recommender)
):
    """
    Obtiene recomendaciones personalizadas para un usuario específico.
    
    MIGRATED: ✅ Using FastAPI Dependency Injection (Phase 2)
    
    Args:
        request: FastAPI request object
        user_id: ID del usuario para recomendaciones personalizadas
        n: Número de recomendaciones a retornar (1-20, default: 5)
        current_user: Usuario autenticado (via Depends)
        tfidf_recommender: TF-IDF recommender (via Depends) ✅ NEW
        retail_recommender: Retail API recommender (via Depends) ✅ NEW
        hybrid_recommender: Hybrid recommender (via Depends) ✅ NEW
    
    Returns:
        Dict con recommendations y metadata (orders, source, timing)
    
    Notes:
        - Usa historial de órdenes para personalización
        - Importa catálogo a Google Cloud Retail API
        - Usa sistema híbrido para mejor calidad
        - Excluye productos ya vistos/comprados
    """
    start_time = time.time()
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
        
        logger.info(f"Getting recommendations for user {user_id}")
        
        # Obtener productos y órdenes del usuario
        all_products = client.get_products()
        user_orders = client.get_orders_by_customer(user_id)
        
        if not user_orders:
            logger.info(f"No order history found for user {user_id}")
        else:
            logger.info(f"Found {len(user_orders)} orders for user {user_id}")
        
        # ✅ UPDATED: Usar tfidf_recommender inyectado
        # Entrenar el recomendador con productos actuales
        tfidf_recommender.fit(all_products)
        
        # ✅ UPDATED: Usar retail_recommender inyectado
        # Importar productos a Google Cloud Retail API
        try:
            logger.info("Importing products to Google Cloud Retail API")
            import_result = await retail_recommender.import_catalog(all_products)
            logger.info(f"Import result: {import_result}")
        except Exception as e:
            logger.error(f"Error importing products: {e}")
        
        # ✅ UPDATED: Usar hybrid_recommender inyectado
        # Obtener recomendaciones
        logger.info("Getting recommendations from hybrid recommender")
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=n,
            exclude_seen=True  # Excluir productos vistos por defecto
        )
        
        if not recommendations:
            logger.warning(f"No recommendations generated for user {user_id}")
            
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
                "took_ms": response_time_ms,
                "di_migration": "phase2_complete"  # ✅ NEW: Migration flag
            }
        }
    except Exception as e:
        logger.error(f"Error getting recommendations for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting recommendations: {str(e)}"
        )


@router.post("/events/user/{user_id}")
async def record_user_event(
    user_id: str,
    event_type: str = Query(..., description="Tipo de evento (detail-page-view, add-to-cart, purchase-complete, etc.)"),
    product_id: Optional[str] = None,
    recommendation_id: Optional[str] = Query(None, description="ID de la recomendación si el producto fue recomendado"),
    current_user: str = Depends(get_current_user),
    # ✅ NEW: FastAPI Dependency Injection
    hybrid_recommender: HybridRecommender = Depends(get_hybrid_recommender)
):
    """
    Registra eventos de usuario para mejorar las recomendaciones futuras.
    
    MIGRATED: ✅ Using FastAPI Dependency Injection (Phase 2)
    
    Args:
        user_id: ID del usuario que genera el evento
        event_type: Tipo de evento a registrar
        product_id: ID del producto relacionado (opcional)
        recommendation_id: ID de recomendación si aplica (opcional)
        current_user: Usuario autenticado (via Depends)
        hybrid_recommender: Hybrid recommender (via Depends) ✅ NEW
    
    Returns:
        Dict con status, message, event details
    
    Tipos de eventos válidos:
        - detail-page-view: Vista de detalle del producto
        - add-to-cart: Añadir al carrito
        - purchase-complete: Compra completada
        - home-page-view: Vista de página principal
        - category-page-view: Vista de página de categoría
        - search: Búsqueda de productos
    
    Notes:
        - Acepta tipos alternativos y los mapea a tipos estándar
        - Registra en Google Cloud Retail API
        - Registra métricas locales
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
            logger.info(f"Mapeando tipo de evento alternativo '{event_type}' a '{mapped_event_type}'")
            event_type = mapped_event_type
        
        # Si sigue sin ser válido, usar detail-page-view por defecto
        if event_type not in valid_event_types:
            logger.warning(f"Tipo de evento no válido '{event_type}', usando 'detail-page-view'")
            event_type = "detail-page-view"
        
        # ✅ UPDATED: Usar hybrid_recommender inyectado
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
                "note": "El evento fue registrado correctamente y ayudará a mejorar las recomendaciones futuras.",
                "di_migration": "phase2_complete"  # ✅ NEW: Migration flag
            }
        }
        
    except Exception as e:
        logger.error(f"Error al registrar evento de usuario: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MODULE METADATA
# ============================================================================

__version__ = "2.0.0"
__author__ = "Senior Architecture Team"
__status__ = "Production - FastAPI DI Migration Complete"
__migration_date__ = "2025-10-16"
