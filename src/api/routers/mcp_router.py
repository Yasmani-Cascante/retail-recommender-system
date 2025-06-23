# src/api/routers/mcp_router.py
import time
import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel

from src.api.security import get_current_user
from src.api.mcp.client.mcp_client import MCPClient
from src.api.mcp.adapters.market_manager import MarketContextManager
from src.cache.market_aware.market_cache import MarketAwareProductCache
from src.api.mcp.models.mcp_models import (
    ConversationContext, MCPRecommendationRequest, MCPRecommendationResponse,
    MarketID, IntentType
)

logger = logging.getLogger(__name__)

# Modelos de datos para la API
class ConversationRequest(BaseModel):
    """Modelo para peticiones de conversación con MCP"""
    query: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    market_id: str = "default"
    language: str = "en"
    product_id: Optional[str] = None
    n_recommendations: int = 5

class ConversationResponse(BaseModel):
    """Modelo para respuestas conversacionales"""
    answer: str
    recommendations: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    session_id: str
    took_ms: float = 0.0

class MarketSupportedResponse(BaseModel):
    """Modelo para respuesta de mercados soportados"""
    markets: List[Dict[str, Any]]
    default_market: str
    total: int

# Crear router MCP
router = APIRouter(
    prefix="/v1/mcp",
    tags=["Market Context Protocol"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "No encontrado"}},
)

# Factorías e instancias necesarias para MCP
def get_mcp_client():
    """Factory para cliente MCP"""
    from src.api.factories import MCPFactory
    return MCPFactory.create_mcp_client()

def get_market_manager():
    """Factory para gestor de mercados"""
    from src.api.factories import MCPFactory
    return MCPFactory.create_market_manager()

def get_market_cache():
    """Factory para cache market-aware"""
    from src.api.factories import MCPFactory
    return MCPFactory.create_market_cache()

def get_mcp_recommender():
    """Factory para recomendador MCP-aware"""
    from src.api.factories import MCPFactory
    return MCPFactory.create_mcp_recommender()

@router.post("/conversation", response_model=ConversationResponse)
async def process_conversation(
    conversation: ConversationRequest,
    current_user: str = Depends(get_current_user)
):
    """
    Endpoint para procesamiento conversacional MCP
    """
    start_time = time.time()
    
    try:
        # Obtener componentes necesarios
        mcp_client = get_mcp_client()
        mcp_recommender = get_mcp_recommender()
        
        if not mcp_client:
            raise HTTPException(status_code=503, detail="MCP client not initialized")
        
        if not mcp_recommender:
            raise HTTPException(status_code=503, detail="MCP recommender not initialized")
        
        # Crear contexto de conversación
        context = ConversationContext(
            session_id=conversation.session_id or f"session_{int(time.time())}",
            user_id=conversation.user_id or "anonymous",
            query=conversation.query,
            market_id=conversation.market_id,
            language=conversation.language
        )
        
        # Crear request para MCP
        request = MCPRecommendationRequest(
            user_id=conversation.user_id or "anonymous",
            session_id=conversation.session_id,
            market_id=conversation.market_id,
            product_id=conversation.product_id,
            conversation_context=context,
            n_recommendations=conversation.n_recommendations,
            include_conversation_response=True
        )
        
        # Obtener recomendaciones MCP
        response: MCPRecommendationResponse = await mcp_recommender.get_recommendations(request)
        
        # Transformar recomendaciones a formato API
        simplified_recs = []
        for rec in response.recommendations:
            simplified_recs.append({
                "id": rec.product.id,
                "title": rec.product.localized_title or rec.product.title,
                "description": rec.product.localized_description or rec.product.description,
                "price": rec.product.market_price,
                "currency": rec.product.currency,
                "score": rec.market_score,
                "reason": rec.reason,
                "images": rec.product.images,
                "market_adapted": True,
                "viability_score": rec.viability_score
            })
        
        # Construir respuesta
        return {
            "answer": response.ai_response or "I've found some recommendations that might interest you.",
            "recommendations": simplified_recs,
            "metadata": {
                "market_id": conversation.market_id,
                "intent_processed": True,
                "source": "mcp_conversation",
                **response.metadata
            },
            "session_id": response.conversation_session or context.session_id,
            "took_ms": (time.time() - start_time) * 1000
        }
        
    except Exception as e:
        logger.error(f"Error processing MCP conversation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing conversation: {str(e)}"
        )

@router.get("/markets", response_model=MarketSupportedResponse)
async def get_supported_markets(
    current_user: str = Depends(get_current_user)
):
    """
    Devuelve los mercados soportados y sus configuraciones
    """
    try:
        # Obtener gestor de mercados
        market_manager = get_market_manager()
        
        if not market_manager:
            raise HTTPException(status_code=503, detail="Market manager not initialized")
        
        # Obtener mercados soportados
        markets = await market_manager.get_supported_markets()
        
        # Simplificar para API
        market_info = []
        for market_id, config in markets.items():
            market_info.append({
                "id": market_id,
                "name": config.get("name", market_id),
                "currency": config.get("currency", "USD"),
                "language": config.get("language", "en"),
                "timezone": config.get("timezone", "UTC"),
                "enabled": config.get("enabled", True),
                "localization_available": bool(config.get("localization", {}))
            })
        
        return {
            "markets": market_info,
            "default_market": "default",
            "total": len(market_info)
        }
        
    except Exception as e:
        logger.error(f"Error retrieving supported markets: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving supported markets: {str(e)}"
        )

@router.get("/recommendations/{product_id}", response_model=Dict)
async def get_market_recommendations(
    product_id: str,
    market_id: str = Query(MarketID.DEFAULT, description="ID del mercado"),
    user_id: Optional[str] = Header(None),
    n: int = Query(5, gt=0, le=20),
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene recomendaciones basadas en producto adaptadas al mercado
    """
    start_time = time.time()
    
    try:
        # Obtener recomendador MCP
        mcp_recommender = get_mcp_recommender()
        
        if not mcp_recommender:
            raise HTTPException(status_code=503, detail="MCP recommender not initialized")
        
        # Crear request MCP
        request = MCPRecommendationRequest(
            user_id=user_id or "anonymous",
            market_id=market_id,
            product_id=product_id,
            n_recommendations=n,
            include_conversation_response=False
        )
        
        # Obtener recomendaciones
        response = await mcp_recommender.get_recommendations(request)
        
        # Transformar para API
        simplified_recs = []
        for rec in response.recommendations:
            simplified_recs.append({
                "id": rec.product.id,
                "title": rec.product.localized_title or rec.product.title,
                "price": rec.product.market_price,
                "currency": rec.product.currency,
                "score": rec.market_score,
                "reason": rec.reason,
                "market_adapted": True
            })
        
        return {
            "product_id": product_id,
            "market_id": market_id,
            "recommendations": simplified_recs,
            "metadata": {
                "total_recommendations": len(simplified_recs),
                "market_context": response.market_context,
                "took_ms": (time.time() - start_time) * 1000
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting market recommendations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting market recommendations: {str(e)}"
        )

@router.get("/cache/stats", response_model=Dict)
async def get_cache_stats(
    market_id: Optional[str] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene estadísticas del caché market-aware
    """
    try:
        market_cache = get_market_cache()
        
        if not market_cache:
            raise HTTPException(status_code=503, detail="Market cache not initialized")
        
        stats = await market_cache.get_cache_stats(market_id)
        
        return {
            "stats": stats,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting cache stats: {str(e)}"
        )

@router.post("/cache/warmup/{market_id}", response_model=Dict)
async def warmup_market_cache(
    market_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Inicia el proceso de pre-carga del caché para un mercado
    """
    try:
        market_cache = get_market_cache()
        
        if not market_cache:
            raise HTTPException(status_code=503, detail="Market cache not initialized")
        
        # Obtener productos prioritarios (implementación simple)
        # En producción, esto vendría de un análisis de popularidad
        from src.api.factories import RecommenderFactory
        base_recommender = RecommenderFactory.create_tfidf_recommender()
        
        if not base_recommender.loaded:
            raise HTTPException(
                status_code=503, 
                detail="Base recommender not loaded, cannot determine priority products"
            )
        
        # Usar top productos como prioritarios
        all_products = base_recommender.product_data
        priority_ids = [str(p.get('id')) for p in all_products[:100]]  # Top 100
        
        # Iniciar pre-carga en background
        import asyncio
        asyncio.create_task(
            market_cache.warm_cache_for_market(market_id, priority_ids)
        )
        
        return {
            "status": "warming",
            "market_id": market_id,
            "priority_products": len(priority_ids),
            "message": "Cache warming process started in background"
        }
        
    except Exception as e:
        logger.error(f"Error warming market cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error warming market cache: {str(e)}"
        )

@router.post("/cache/invalidate/{market_id}", response_model=Dict)
async def invalidate_market_cache(
    market_id: str,
    entity_type: Optional[str] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Invalida el caché de un mercado completo o por tipo de entidad
    """
    try:
        market_cache = get_market_cache()
        
        if not market_cache:
            raise HTTPException(status_code=503, detail="Market cache not initialized")
        
        await market_cache.invalidate_market(market_id, entity_type)
        
        return {
            "status": "success",
            "market_id": market_id,
            "entity_type": entity_type or "all",
            "message": f"Cache invalidated for market {market_id}"
        }
        
    except Exception as e:
        logger.error(f"Error invalidating market cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error invalidating market cache: {str(e)}"
        )
