# src/api/mcp/client/mcp_client.py
"""
Cliente Python para comunicación con Node.js MCP Bridge

Implementa la clase MCPClient, que permite comunicarse de forma asíncrona con un servicio intermedio (Node.js MCP Bridge)
vía HTTP para operaciones conversacionales y de recomendación.

En resumen, este fichero proporciona la infraestructura para integrar capacidades conversacionales avanzadas 
y recomendaciones personalizadas, conectando el sistema principal con un servicio MCP externo y gestionando
la lógica de fallback y formato de respuestas.
"""

import asyncio
import httpx
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import uuid

logger = logging.getLogger(__name__)

class MCPClientError(Exception):
    """Excepción base para errores del cliente MCP"""
    pass

class MCPClient:
    """Cliente asíncrono para comunicación con Shopify MCP Bridge"""
    
    def __init__(
        self, 
        bridge_host: str = "localhost",
        bridge_port: int = 3001,
        timeout: int = 30
    ):
        self.base_url = f"http://{bridge_host}:{bridge_port}"
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        self._session_cache = {}
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def close(self):
        """Cerrar el cliente HTTP"""
        await self.client.aclose()
        
    async def health_check(self) -> Dict[str, Any]:
        """Verificar estado del MCP Bridge"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise MCPClientError(f"MCP Bridge health check failed: {e}")
            
    async def get_mcp_status(self) -> Dict[str, Any]:
        """Obtener estado detallado del MCP"""
        try:
            response = await self.client.get(f"{self.base_url}/api/mcp/status")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get MCP status: {e}")
            raise MCPClientError(f"Failed to get MCP status: {e}")
            
    async def process_conversation(
        self,
        query: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Procesar una consulta conversacional usando MCP
        
        Args:
            query: Consulta del usuario
            session_id: ID de sesión para mantener contexto
            context: Contexto adicional para la consulta
            
        Returns:
            Respuesta procesada por MCP
        """
        if not session_id:
            session_id = str(uuid.uuid4())
            
        payload = {
            "query": query,
            "sessionId": session_id,
            "context": context or {}
        }
        
        try:
            logger.info(f"Processing conversation: {query[:100]}...")
            
            response = await self.client.post(
                f"{self.base_url}/api/mcp/conversation",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Cache session info
            if session_id:
                self._session_cache[session_id] = {
                    "last_query": query,
                    "last_response": result.get("response"),
                    "timestamp": datetime.now().isoformat()
                }
            
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error in conversation: {e.response.status_code}")
            raise MCPClientError(f"Conversation failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Error processing conversation: {e}")
            raise MCPClientError(f"Conversation processing error: {e}")
            
    async def get_conversation_history(self, session_id: str) -> Dict[str, Any]:
        """Obtener historial de conversación"""
        try:
            response = await self.client.get(
                f"{self.base_url}/api/mcp/conversation/{session_id}"
            )
            
            if response.status_code == 404:
                return {"success": False, "error": "Conversation not found"}
                
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            raise MCPClientError(f"Failed to get conversation history: {e}")
            
    async def search_documentation(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Buscar en documentación de Shopify usando MCP
        
        Args:
            query: Término de búsqueda
            filters: Filtros adicionales para la búsqueda
            
        Returns:
            Resultados de búsqueda
        """
        payload = {
            "query": query,
            "filters": filters or {}
        }
        
        try:
            logger.info(f"Searching documentation: {query}")
            
            response = await self.client.post(
                f"{self.base_url}/api/mcp/search",
                json=payload
            )
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error searching documentation: {e}")
            raise MCPClientError(f"Documentation search failed: {e}")
            
    async def analyze_intent(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analizar intención del usuario
        
        Args:
            text: Texto a analizar
            context: Contexto adicional
            
        Returns:
            Intención detectada y confianza
        """
        payload = {
            "text": text,
            "context": context or {}
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/api/mcp/analyze-intent",
                json=payload
            )
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error analyzing intent: {e}")
            raise MCPClientError(f"Intent analysis failed: {e}")

class ShopifyMCPClient(MCPClient):
    """Cliente MCP específico para Shopify"""
    
    def __init__(self, shopify_url: str, bridge_host: str = "localhost", bridge_port: int = 3001):
        super().__init__(bridge_host, bridge_port)
        self.shopify_url = shopify_url
        self.initialized = False
        self.anthropic = None
        
    async def initialize(self) -> bool:
        """Inicializar cliente MCP para Shopify"""
        logger.info(f"Inicializando ShopifyMCPClient con URL: {self.shopify_url}")
        
        try:
            # Verificar estado del bridge
            health = await self.health_check()
            
            if health.get("status") == "healthy":
                logger.info("Bridge MCP activo y saludable")
                self.initialized = True
            else:
                logger.warning(f"Bridge MCP en estado degradado: {health}")
                self.initialized = False
                
            # Inicializar Anthropic para respuestas conversacionales
            try:
                import anthropic
                self.anthropic = anthropic.Anthropic()
                logger.info("Cliente Anthropic inicializado correctamente")
            except ImportError:
                logger.warning("Anthropic no disponible, usando respuestas conversacionales estándar")
                self.anthropic = None
            except Exception as e:
                logger.error(f"Error inicializando Anthropic: {e}")
                self.anthropic = None
                
            return self.initialized
        except Exception as e:
            logger.error(f"Error inicializando ShopifyMCPClient: {e}")
            return False
            
    async def get_market_products(self, market_id: str, product_ids: List[str]) -> List[Dict]:
        """Obtener productos para un mercado específico"""
        try:
            # En una implementación real, esto haría una llamada a Shopify
            # Para este ejemplo, simularemos los datos
            products = []
            
            for product_id in product_ids:
                # Simular datos de producto
                product = {
                    "id": product_id,
                    "title": f"Product {product_id}",
                    "description": f"Description for product {product_id}",
                    "price": float(hash(product_id) % 10000) / 100,
                    "currency": "USD"
                }
                
                # Adaptar para mercado
                if market_id == "ES":
                    product["currency"] = "EUR"
                    product["price"] = product["price"] * 0.85
                elif market_id == "MX":
                    product["currency"] = "MXN"
                    product["price"] = product["price"] * 17.5
                elif market_id == "CL":
                    product["currency"] = "CLP"
                    product["price"] = product["price"] * 930.0
                    
                products.append(product)
            
            return products
        except Exception as e:
            logger.error(f"Error obteniendo productos para mercado {market_id}: {e}")
            return []
    
    async def process_conversation_intent(self, query: str, market_context: Dict) -> Dict:
        """Procesar intención conversacional"""
        try:
            # Usar analyze_intent como base
            intent_data = await self.analyze_intent(query, market_context)
            
            # Enriquecer con contexto de mercado
            intent_data["market_id"] = market_context.get("market_id", "default")
            intent_data["timestamp"] = datetime.utcnow().isoformat()
            
            return intent_data
        except Exception as e:
            logger.error(f"Error procesando intención conversacional: {e}")
            return {
                "type": "general",
                "confidence": 0.5,
                "market_id": market_context.get("market_id", "default"),
                "error": str(e)
            }

# src/api/mcp/adapters/conversation_adapter.py
"""
Adaptador para integrar MCP con sistema de recomendaciones existente
"""

from typing import Dict, List, Optional, Any
import logging
from .mcp_client import MCPClient, MCPClientError

logger = logging.getLogger(__name__)

class ConversationAdapter:
    """
    Adaptador que conecta el sistema de recomendaciones con capacidades conversacionales MCP permitiendo:

    Analizar la intención del usuario.
    Procesar la conversación y obtener contexto.
    Generar recomendaciones basadas en la intención detectada.
    Formatear respuestas conversacionales naturales.
    Proveer un mecanismo de fallback si el MCP no está disponible.
    """
    
    def __init__(self, hybrid_recommender, mcp_client: MCPClient):
        self.hybrid_recommender = hybrid_recommender
        self.mcp_client = mcp_client
        
    async def process_conversational_request(
        self,
        user_query: str,
        user_id: str,
        session_id: Optional[str] = None,
        n_recommendations: int = 5
    ) -> Dict[str, Any]:
        """
        Procesar solicitud conversacional y generar recomendaciones
        
        Args:
            user_query: Consulta en lenguaje natural
            user_id: ID del usuario
            session_id: ID de sesión conversacional
            n_recommendations: Número de recomendaciones
            
        Returns:
            Respuesta estructurada con recomendaciones y contexto conversacional
        """
        try:
            # 1. Analizar intención del usuario
            intent_analysis = await self.mcp_client.analyze_intent(
                user_query,
                context={"user_id": user_id}
            )
            
            intent = intent_analysis.get("intent", "general")
            confidence = intent_analysis.get("confidence", 0.5)
            
            logger.info(f"Intent detected: {intent} (confidence: {confidence})")
            
            # 2. Procesar con MCP para contexto conversacional
            mcp_response = await self.mcp_client.process_conversation(
                user_query,
                session_id=session_id,
                context={
                    "user_id": user_id,
                    "intent": intent,
                    "timestamp": "now"
                }
            )
            
            # 3. Generar recomendaciones basadas en intención
            recommendations = await self._generate_intent_based_recommendations(
                intent, user_query, user_id, n_recommendations
            )
            
            # 4. Formatear respuesta conversacional
            conversational_response = self._format_conversational_response(
                user_query, intent, recommendations, mcp_response
            )
            
            return {
                "success": True,
                "conversational_response": conversational_response,
                "recommendations": recommendations,
                "intent": intent,
                "confidence": confidence,
                "session_id": mcp_response.get("sessionId"),
                "metadata": {
                    "processing_time": "calculated",
                    "mcp_used": True,
                    "source": "conversational_adapter"
                }
            }
            
        except MCPClientError as e:
            logger.error(f"MCP error in conversational request: {e}")
            # Fallback sin MCP
            return await self._fallback_recommendations(user_query, user_id, n_recommendations)
            
        except Exception as e:
            logger.error(f"Error in conversational request: {e}")
            raise
            
    async def _generate_intent_based_recommendations(
        self,
        intent: str,
        query: str,
        user_id: str,
        n_recommendations: int
    ) -> List[Dict[str, Any]]:
        """Generar recomendaciones basadas en intención detectada"""
        
        # Mapear intenciones a estrategias de recomendación
        if intent == "search":
            # Para búsquedas, usar el motor de búsqueda TF-IDF
            if hasattr(self.hybrid_recommender, 'content_recommender'):
                return await self.hybrid_recommender.content_recommender.search_products(
                    query, n_recommendations
                )
                
        elif intent == "recommend":
            # Para recomendaciones generales, usar híbrido
            return await self.hybrid_recommender.get_recommendations(
                user_id=user_id,
                n_recommendations=n_recommendations
            )
            
        elif intent == "compare":
            # Para comparaciones, obtener productos similares
            # Extraer nombres de productos del query si es posible
            return await self.hybrid_recommender.get_recommendations(
                user_id=user_id,
                n_recommendations=n_recommendations * 2  # Más productos para comparar
            )
            
        else:
            # Intención general, usar recomendaciones híbridas estándar
            return await self.hybrid_recommender.get_recommendations(
                user_id=user_id,
                n_recommendations=n_recommendations
            )
            
    def _format_conversational_response(
        self,
        user_query: str,
        intent: str,
        recommendations: List[Dict],
        mcp_response: Dict
    ) -> str:
        """Formatear respuesta conversacional natural"""
        
        if not recommendations:
            return "Lo siento, no pude encontrar productos que coincidan con tu búsqueda. ¿Podrías ser más específico?"
            
        # Plantillas de respuesta por intención
        response_templates = {
            "search": f"Encontré {len(recommendations)} productos que podrían interesarte:",
            "recommend": f"Basándome en tus preferencias, te recomiendo estos {len(recommendations)} productos:",
            "compare": f"Aquí tienes {len(recommendations)} opciones para comparar:",
            "general": f"Te sugiero echar un vistazo a estos {len(recommendations)} productos:"
        }
        
        intro = response_templates.get(intent, response_templates["general"])
        
        # Agregar información de productos top
        if recommendations:
            top_product = recommendations[0]
            intro += f" El más destacado es '{top_product.get('title', 'producto')}'"
            
        return intro
        
    async def _fallback_recommendations(
        self,
        query: str,
        user_id: str,
        n_recommendations: int
    ) -> Dict[str, Any]:
        """Recomendaciones de fallback cuando MCP no está disponible"""
        
        logger.warning("Using fallback recommendations (MCP unavailable)")
        
        # Usar sistema existente sin MCP
        recommendations = await self.hybrid_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=n_recommendations
        )
        
        return {
            "success": True,
            "conversational_response": f"Aquí tienes {len(recommendations)} recomendaciones para ti:",
            "recommendations": recommendations,
            "intent": "general",
            "confidence": 0.5,
            "session_id": None,
            "metadata": {
                "mcp_used": False,
                "source": "fallback_adapter"
            }
        }