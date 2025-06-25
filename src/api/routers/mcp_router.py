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
    """Obtiene el cliente MCP global"""
    # Importar la instancia global desde main_unified_redis
    from src.api import main_unified_redis
    
    # Verificar si hay una instancia MCP global disponible
    if hasattr(main_unified_redis, 'mcp_recommender') and main_unified_redis.mcp_recommender:
        if hasattr(main_unified_redis.mcp_recommender, 'mcp_client'):
            return main_unified_redis.mcp_recommender.mcp_client
    
    # Fallback a crear uno nuevo si no hay instancia global
    from src.api.factories import MCPFactory
    return MCPFactory.create_mcp_client()

def get_market_manager():
    """Obtiene el gestor de mercados global"""
    # Importar la instancia global desde main_unified_redis
    from src.api import main_unified_redis
    
    # Verificar si hay una instancia MCP global disponible
    if hasattr(main_unified_redis, 'mcp_recommender') and main_unified_redis.mcp_recommender:
        if hasattr(main_unified_redis.mcp_recommender, 'market_manager'):
            return main_unified_redis.mcp_recommender.market_manager
    
    # Fallback a crear uno nuevo si no hay instancia global
    from src.api.factories import MCPFactory
    return MCPFactory.create_market_manager()

def get_market_cache():
    """Obtiene el cache market-aware global"""
    # Importar la instancia global desde main_unified_redis
    from src.api import main_unified_redis
    
    # Verificar si hay una instancia MCP global disponible
    if hasattr(main_unified_redis, 'mcp_recommender') and main_unified_redis.mcp_recommender:
        if hasattr(main_unified_redis.mcp_recommender, 'market_cache'):
            return main_unified_redis.mcp_recommender.market_cache
    
    # Fallback a crear uno nuevo si no hay instancia global
    from src.api.factories import MCPFactory
    return MCPFactory.create_market_cache()

def get_mcp_recommender():
    """Obtiene el recomendador MCP-aware global (ya entrenado)"""
    # CORREGIDO: Usar la instancia global que ya está entrenada
    from src.api import main_unified_redis
    
    # Verificar si hay una instancia MCP global disponible
    if hasattr(main_unified_redis, 'mcp_recommender') and main_unified_redis.mcp_recommender:
        logger.info("Usando recomendador MCP global (ya entrenado)")
        return main_unified_redis.mcp_recommender
    
    # Si no hay instancia global, loggear advertencia y retornar None
    logger.warning("No hay instancia global de mcp_recommender disponible")
    return None

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
        
        # IMPORTANTE: Modificación para asegurar que la consulta esté disponible para el fallback
        # Pasar la consulta directamente como campo adicional en el diccionario de request
        # Esto asegurará que el fallback pueda usarla cuando no hay recomendaciones
        request_dict = request.dict()
        request_dict['query'] = conversation.query  # Agregar consulta directamente al request
        logger.info(f"Agregando consulta al request: {conversation.query}")
        
        # Obtener recomendaciones MCP
        response_dict = await mcp_recommender.get_recommendations(request_dict)
        
        # Transformar recomendaciones a formato API
        simplified_recs = []
        
        # Adaptación para manejar tanto objetos Pydantic como diccionarios
        if hasattr(response_dict, 'recommendations'):  # Es un objeto Pydantic
            recommendations = response_dict.recommendations
            ai_response = response_dict.ai_response
            conversation_session = response_dict.conversation_session
            metadata = response_dict.metadata
        else:  # Es un diccionario
            recommendations = response_dict.get("recommendations", [])
            ai_response = response_dict.get("ai_response")
            conversation_session = response_dict.get("conversation_session")
            metadata = response_dict.get("metadata", {})
        
        for rec in recommendations:
            # Verificar si rec es un objeto RecommendationMCP o un diccionario
            if hasattr(rec, 'product'):  # Es un objeto Pydantic
                product = rec.product
                simplified_recs.append({
                    "id": product.id,
                    "title": product.localized_title or product.title,
                    "description": product.localized_description or product.description,
                    "price": product.market_price,
                    "currency": product.currency,
                    "score": rec.market_score,
                    "reason": rec.reason,
                    "images": product.images,
                    "market_adapted": True,
                    "viability_score": rec.viability_score
                })
            else:  # Es un diccionario
                product = rec.get("product", {})
                simplified_recs.append({
                    "id": product.get("id"),
                    "title": product.get("localized_title") or product.get("title"),
                    "description": product.get("localized_description") or product.get("description", ""),
                    "price": product.get("market_price"),
                    "currency": product.get("currency"),
                    "score": rec.get("market_score"),
                    "reason": rec.get("reason"),
                    "images": product.get("images", []),
                    "market_adapted": True,
                    "viability_score": rec.get("viability_score"),
                    "source": rec.get("metadata", {}).get("source", "unknown")  # Añadir origen de la recomendación
                })
        
        # Construir respuesta
        return {
            "answer": ai_response or "I've found some recommendations that might interest you.",
            "recommendations": simplified_recs,
            "metadata": {
                "market_id": conversation.market_id,
                "intent_processed": True,
                "source": "mcp_conversation",
                **metadata
            },
            "session_id": conversation_session or context.session_id,
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
        
        # Convertir a dict para asegurar compatibilidad con mecanismo de fallback
        request_dict = request.dict()
        
        # Obtener recomendaciones
        response_dict = await mcp_recommender.get_recommendations(request_dict)
        
        # Adaptación para manejar tanto objetos Pydantic como diccionarios
        if hasattr(response_dict, 'recommendations'):  # Es un objeto Pydantic
            recommendations = response_dict.recommendations
            market_context = response_dict.market_context
        else:  # Es un diccionario
            recommendations = response_dict.get("recommendations", [])
            market_context = response_dict.get("market_context", {})
        
        # Transformar para API
        simplified_recs = []
        for rec in recommendations:
            # Verificar si rec es un objeto RecommendationMCP o un diccionario
            if hasattr(rec, 'product'):  # Es un objeto Pydantic
                product = rec.product
                simplified_recs.append({
                    "id": product.id,
                    "title": product.localized_title or product.title,
                    "price": product.market_price,
                    "currency": product.currency,
                    "score": rec.market_score,
                    "reason": rec.reason,
                    "market_adapted": True,
                    "source": getattr(rec, 'metadata', {}).get("source", "unknown")  # Añadir origen de la recomendación
                })
            else:  # Es un diccionario
                product = rec.get("product", {})
                simplified_recs.append({
                    "id": product.get("id"),
                    "title": product.get("localized_title") or product.get("title"),
                    "price": product.get("market_price"),
                    "currency": product.get("currency"),
                    "score": rec.get("market_score"),
                    "reason": rec.get("reason"),
                    "market_adapted": True,
                    "source": rec.get("metadata", {}).get("source", "unknown")  # Añadir origen de la recomendación
                })
        
        return {
            "product_id": product_id,
            "market_id": market_id,
            "recommendations": simplified_recs,
            "metadata": {
                "total_recommendations": len(simplified_recs),
                "market_context": market_context,
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
