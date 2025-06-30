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
        # Obtener componentes necesarios con manejo robusto
        mcp_client = None
        mcp_recommender = None
        
        try:
            mcp_client = get_mcp_client()
            mcp_recommender = get_mcp_recommender()
        except Exception as e:
            logger.warning(f"Error getting MCP components: {e}")
        
        # Si no hay componentes MCP, usar fallback directo
        if not mcp_client or not mcp_recommender:
            logger.info("Using direct fallback to hybrid recommender")
            from src.api import main_unified_redis
            if hasattr(main_unified_redis, 'hybrid_recommender') and main_unified_redis.hybrid_recommender:
                try:
                    fallback_recs = await main_unified_redis.hybrid_recommender.get_recommendations(
                        user_id=conversation.user_id or "anonymous",
                        product_id=conversation.product_id,
                        n_recommendations=conversation.n_recommendations
                    )
                    
                    return {
                        "answer": f"Based on your query '{conversation.query}', I found {len(fallback_recs)} recommendations using our base system.",
                        "recommendations": fallback_recs,
                        "metadata": {
                            "market_id": conversation.market_id,
                            "source": "hybrid_fallback",
                            "query_processed": conversation.query,
                            "mcp_available": False
                        },
                        "session_id": f"session_{int(time.time())}",
                        "took_ms": (time.time() - start_time) * 1000
                    }
                except Exception as e:
                    logger.error(f"Fallback recommender also failed: {e}")
            
            # Si todo falla, devolver respuesta mínima
            return {
                "answer": f"I'm sorry, I'm having trouble processing your query '{conversation.query}' right now. Please try again later.",
                "recommendations": [],
                "metadata": {
                    "market_id": conversation.market_id,
                    "source": "error_fallback",
                    "query_processed": conversation.query,
                    "mcp_available": False
                },
                "session_id": f"session_{int(time.time())}",
                "took_ms": (time.time() - start_time) * 1000
            }
        
        # Crear contexto de conversación
        context = ConversationContext(
            session_id=conversation.session_id or f"session_{int(time.time())}",
            user_id=conversation.user_id or "anonymous",
            query=conversation.query,
            market_id=conversation.market_id,
            language=conversation.language
        )
        
        # ✅ Validación de parámetros de entrada
        # Evitar que se pasen strings literales como IDs
        validated_user_id = conversation.user_id
        if not validated_user_id or validated_user_id.lower() in ['string', 'null', 'undefined', 'none']:
            validated_user_id = "anonymous"
            
        validated_product_id = conversation.product_id
        if validated_product_id and validated_product_id.lower() in ['string', 'null', 'undefined', 'none']:
            validated_product_id = None
            
        # Loggear la información de la consulta para debugging
        logger.info(f"Processing conversation query: {conversation.query}")
        logger.info(f"User: {validated_user_id}, Market: {conversation.market_id}, Product: {validated_product_id}")
        
        # ✅ CORRECCIÓN: Obtener recomendaciones MCP con timeout y fallback robusto
        import asyncio
        
        try:
            # Envolver la llamada en un timeout para evitar bloqueos indefinidos
            response_dict = await asyncio.wait_for(
                mcp_recommender.get_recommendations(
                    user_id=validated_user_id,
                    product_id=validated_product_id,
                    conversation_context={
                        "query": conversation.query,
                        "session_id": conversation.session_id,
                        "market_id": conversation.market_id,
                        "language": conversation.language
                    },
                    n_recommendations=conversation.n_recommendations,
                    market_id=conversation.market_id
                ),
                timeout=5.0  # Timeout más agresivo de 5 segundos
            )
            logger.info("MCP recommender responded successfully")
            
        except asyncio.TimeoutError:
            logger.warning("MCP recommender timed out, using base recommender fallback")
            # Fallback al recomendador base si MCP se cuelga
            from src.api import main_unified_redis
            if hasattr(main_unified_redis, 'hybrid_recommender') and main_unified_redis.hybrid_recommender:
                response_dict = await main_unified_redis.hybrid_recommender.get_recommendations(
                    user_id=validated_user_id,
                    product_id=validated_product_id,
                    n_recommendations=conversation.n_recommendations
                )
            else:
                # Fallback final: lista vacía
                response_dict = []
                
        except Exception as e:
            logger.error(f"Error in MCP recommender, using base recommender fallback: {e}")
            # Fallback al recomendador base si MCP falla
            from src.api import main_unified_redis
            if hasattr(main_unified_redis, 'hybrid_recommender') and main_unified_redis.hybrid_recommender:
                response_dict = await main_unified_redis.hybrid_recommender.get_recommendations(
                    user_id=validated_user_id,
                    product_id=validated_product_id,
                    n_recommendations=conversation.n_recommendations
                )
            else:
                # Fallback final: lista vacía
                response_dict = []
        
        # ✅ Manejo robusto de la respuesta del mcp_recommender
        # El método puede retornar List[Dict] o Dict según el contexto
        if isinstance(response_dict, list):
            # Es una lista directa de recomendaciones
            recommendations = response_dict
            ai_response = None
            conversation_session = None
            metadata = {}
            logger.info(f"Received direct list response with {len(recommendations)} recommendations")
        elif isinstance(response_dict, dict):
            # Es un diccionario con estructura completa
            if hasattr(response_dict, 'recommendations'):  # Es un objeto Pydantic
                recommendations = response_dict.recommendations
                ai_response = response_dict.ai_response
                conversation_session = response_dict.conversation_session
                metadata = response_dict.metadata
            else:  # Es un diccionario simple
                recommendations = response_dict.get("recommendations", [])
                ai_response = response_dict.get("ai_response")
                conversation_session = response_dict.get("conversation_session")
                metadata = response_dict.get("metadata", {})
            logger.info(f"Received dict response with {len(recommendations)} recommendations")
        else:
            # Tipo inesperado, usar valores por defecto
            logger.warning(f"Unexpected response type: {type(response_dict)}. Using fallback values.")
            recommendations = []
            ai_response = None
            conversation_session = None
            metadata = {}
        
        # ✅ Validación y corrección de recomendaciones vacías
        def validate_and_fix_recommendations(recs_list):
            """Valida que las recomendaciones tengan datos reales y no estén vacías."""
            if not recs_list:
                return []
            
            # Verificar si las recomendaciones tienen datos válidos
            valid_recs = []
            for rec in recs_list:
                # Una recomendación es válida si tiene al menos ID y título
                if isinstance(rec, dict):
                    rec_id = rec.get("id")
                    rec_title = rec.get("title")
                    # Verificar que no sean None, cadenas vacías o "null"
                    if (rec_id and rec_id != "null" and str(rec_id).strip() and 
                        rec_title and rec_title != "null" and str(rec_title).strip()):
                        valid_recs.append(rec)
                elif hasattr(rec, 'product'):  # Objeto Pydantic
                    if hasattr(rec.product, 'id') and hasattr(rec.product, 'title'):
                        if rec.product.id and rec.product.title:
                            valid_recs.append(rec)
            
            return valid_recs
        
        # Validar recomendaciones recibidas
        valid_recommendations = validate_and_fix_recommendations(recommendations)
        
        # Si no hay recomendaciones válidas, usar fallback robusto
        if len(valid_recommendations) == 0:
            logger.warning("Recomendaciones MCP están vacías o inválidas, usando fallback al sistema base")
            
            # Intentar usar el hybrid_recommender directamente
            from src.api import main_unified_redis
            if hasattr(main_unified_redis, 'hybrid_recommender') and main_unified_redis.hybrid_recommender:
                try:
                    fallback_recs = await main_unified_redis.hybrid_recommender.get_recommendations(
                        user_id=validated_user_id,
                        product_id=validated_product_id,
                        n_recommendations=conversation.n_recommendations
                    )
                    valid_recommendations = fallback_recs
                    logger.info(f"Fallback hybrid_recommender devolvio {len(valid_recommendations)} recomendaciones")
                except Exception as e:
                    logger.error(f"Error en fallback hybrid_recommender: {e}")
            
            # Si aún no hay recomendaciones, intentar con TF-IDF directamente
            if len(valid_recommendations) == 0:
                try:
                    if hasattr(main_unified_redis, 'tfidf_recommender') and main_unified_redis.tfidf_recommender:
                        if main_unified_redis.tfidf_recommender.loaded and main_unified_redis.tfidf_recommender.product_data:
                            # Usar estrategia de fallback inteligente
                            from src.recommenders.improved_fallback_exclude_seen import ImprovedFallbackStrategies
                            
                            fallback_recs = await ImprovedFallbackStrategies.smart_fallback(
                                user_id=validated_user_id,
                                products=main_unified_redis.tfidf_recommender.product_data,
                                user_events=[],  # No tenemos eventos aqui
                                n=conversation.n_recommendations
                            )
                            valid_recommendations = fallback_recs
                            logger.info(f"Fallback TF-IDF devolvio {len(valid_recommendations)} recomendaciones")
                except Exception as e:
                    logger.error(f"Error en fallback TF-IDF: {e}")
        
        # Usar las recomendaciones válidas
        recommendations = valid_recommendations
        
        # ✅ CORRECCIÓN: Inicializar simplified_recs antes de usarla
        simplified_recs = []
        
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
        
        # Construir respuesta conversacional inteligente y robusta
        if not ai_response:
            if len(simplified_recs) == 0:
                ai_response = f"I apologize, but I couldn't find any products matching your query '{conversation.query}'. Could you try a different search or be more specific about what you're looking for?"
            elif len(simplified_recs) == 1:
                ai_response = f"Based on your query '{conversation.query}', I found 1 recommendation that might interest you."
            else:
                ai_response = f"Based on your query '{conversation.query}', I found {len(simplified_recs)} recommendations that might interest you."
        
        # Asegurar session_id válido
        final_session_id = conversation_session or context.session_id or f"session_{int(time.time())}"
        
        # Construir respuesta robusta
        response = {
            "answer": ai_response,
            "recommendations": simplified_recs,
            "metadata": {
                "market_id": conversation.market_id,
                "intent_processed": True,
                "source": "mcp_conversation_robust",
                "query_processed": conversation.query,
                "user_validated": validated_user_id,
                "product_validated": validated_product_id,
                "fallback_used": isinstance(response_dict, list) and len(response_dict) == 0,
                **metadata
            },
            "session_id": final_session_id,
            "took_ms": (time.time() - start_time) * 1000
        }
        
        logger.info(f"Conversation processed successfully in {response['took_ms']:.1f}ms")
        return response
        
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
        
        # ✅ Validación de parámetros de entrada
        # Evitar que se pasen strings literales como IDs
        validated_user_id = user_id
        if not validated_user_id or validated_user_id.lower() in ['string', 'null', 'undefined', 'none']:
            validated_user_id = "anonymous"
            
        validated_product_id = product_id
        if not validated_product_id or validated_product_id.lower() in ['string', 'null', 'undefined', 'none']:
            raise HTTPException(status_code=400, detail="Valid product_id is required")
            
        # Loggear información para debugging
        logger.info(f"Getting market recommendations - Product: {validated_product_id}, Market: {market_id}, User: {validated_user_id}")
        
        # ✅ CORRECCIÓN: Obtener recomendaciones con timeout y fallback robusto
        import asyncio
        
        try:
            # Envolver la llamada en un timeout para evitar bloqueos indefinidos
            response_dict = await asyncio.wait_for(
                mcp_recommender.get_recommendations(
                    user_id=validated_user_id,
                    product_id=validated_product_id,
                    n_recommendations=n,
                    market_id=market_id
                ),
                timeout=5.0  # Timeout más agresivo de 5 segundos
            )
            logger.info("MCP recommender responded successfully")
            
        except asyncio.TimeoutError:
            logger.warning("MCP recommender timed out, using base recommender fallback")
            # Fallback al recomendador base si MCP se cuelga
            from src.api import main_unified_redis
            if hasattr(main_unified_redis, 'hybrid_recommender') and main_unified_redis.hybrid_recommender:
                response_dict = await main_unified_redis.hybrid_recommender.get_recommendations(
                    user_id=validated_user_id,
                    product_id=validated_product_id,
                    n_recommendations=n
                )
            else:
                # Fallback final: lista vacía
                response_dict = []
                
        except Exception as e:
            logger.error(f"Error in MCP recommender, using base recommender fallback: {e}")
            # Fallback al recomendador base si MCP falla
            from src.api import main_unified_redis
            if hasattr(main_unified_redis, 'hybrid_recommender') and main_unified_redis.hybrid_recommender:
                response_dict = await main_unified_redis.hybrid_recommender.get_recommendations(
                    user_id=validated_user_id,
                    product_id=validated_product_id,
                    n_recommendations=n
                )
            else:
                # Fallback final: lista vacía
                response_dict = []
        
        # ✅ Manejo robusto de la respuesta del mcp_recommender  
        # El método puede retornar List[Dict] o Dict según el contexto
        if isinstance(response_dict, list):
            # Es una lista directa de recomendaciones
            recommendations = response_dict
            market_context = {}
            logger.info(f"Received direct list response with {len(recommendations)} recommendations")
        elif isinstance(response_dict, dict):
            # Es un diccionario con estructura completa
            if hasattr(response_dict, 'recommendations'):  # Es un objeto Pydantic
                recommendations = response_dict.recommendations
                market_context = response_dict.market_context
            else:  # Es un diccionario simple
                recommendations = response_dict.get("recommendations", [])
                market_context = response_dict.get("market_context", {})
            logger.info(f"Received dict response with {len(recommendations)} recommendations")
        else:
            # Tipo inesperado, usar valores por defecto
            logger.warning(f"Unexpected response type: {type(response_dict)}. Using fallback values.")
            recommendations = []
            market_context = {}
        
        # Transformar para API
        simplified_recs = []  # ✅ CORRECCIÓN: Inicializar simplified_recs antes de usarla
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
            "product_id": validated_product_id,
            "market_id": market_id,
            "recommendations": simplified_recs,
            "metadata": {
                "total_recommendations": len(simplified_recs),
                "market_context": market_context,
                "user_validated": validated_user_id,
                "product_validated": validated_product_id,
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
