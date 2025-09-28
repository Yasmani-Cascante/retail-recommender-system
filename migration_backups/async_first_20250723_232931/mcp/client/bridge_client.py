# src/api/mcp/client/bridge_client.py
"""
Cliente Python para comunicación con Node.js MCP Bridge.
Reemplaza las simulaciones con llamadas HTTP reales al bridge.

Este cliente proporciona:
- Comunicación HTTP real con Node.js bridge
- Circuit breaker integration
- Retry logic robusto
- Caching inteligente
- Fallback strategies
"""

import asyncio
import httpx
import logging
import time
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = logging.getLogger(__name__)

class MCPBridgeError(Exception):
    """Exception específica para errores del MCP Bridge"""
    pass

class MCPBridgeClient:
    """
    Cliente Python para interactuar con Node.js MCP Bridge.
    Proporciona interfaz robusta con manejo de errores y fallbacks.
    """
    
    def __init__(
        self,
        bridge_host: str = "localhost",
        bridge_port: int = 3001,
        timeout: int = 10,
        enable_circuit_breaker: bool = True,
        max_retries: int = 3
    ):
        self.bridge_url = f"http://{bridge_host}:{bridge_port}"
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Cliente HTTP optimizado
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        
        # Circuit breaker para proteger contra fallos del bridge
        if enable_circuit_breaker:
            self.circuit_breaker = CircuitBreaker(
                name="mcp_bridge_client",
                config=CircuitBreakerConfig(
                    failure_threshold=3,
                    timeout_seconds=30,
                    success_threshold=2,
                    max_timeout=timeout
                ),
                fallback_function=self._fallback_handler
            )
        else:
            self.circuit_breaker = None
        
        # Métricas de rendimiento
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_latency": 0.0,
            "bridge_available": True,
            "last_health_check": None
        }
        
        logger.info(f"MCPBridgeClient initialized: {self.bridge_url}")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del Node.js bridge.
        
        Returns:
            Dict con estado de salud del bridge
        """
        try:
            start_time = time.time()
            
            response = await self.http_client.get(f"{self.bridge_url}/health")
            response.raise_for_status()
            
            health_data = response.json()
            latency = (time.time() - start_time) * 1000
            
            self.metrics["bridge_available"] = True
            self.metrics["last_health_check"] = time.time()
            
            return {
                "status": "healthy",
                "bridge_status": health_data.get("status", "unknown"),
                "mcp_connection": health_data.get("mcp_connection", "unknown"),
                "latency_ms": latency,
                "bridge_uptime": health_data.get("uptime", 0),
                "bridge_metrics": health_data.get("metrics", {}),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.metrics["bridge_available"] = False
            logger.error(f"Bridge health check failed: {e}")
            
            return {
                "status": "unhealthy",
                "error": str(e),
                "bridge_available": False,
                "timestamp": datetime.now().isoformat()
            }
    
    async def extract_intent(
        self, 
        query: str, 
        market_context: Optional[Dict] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Extrae intención del usuario usando Shopify MCP via bridge.
        
        Args:
            query: Mensaje del usuario
            market_context: Contexto del mercado
            conversation_history: Historial de conversación
            
        Returns:
            Dict con análisis de intención
        """
        payload = {
            "query": query,
            "market_context": market_context or {},
            "conversation_history": conversation_history or []
        }
        
        if self.circuit_breaker:
            return await self.circuit_breaker.call(
                self._make_bridge_request,
                "POST",
                "/mcp/extract-intent",
                payload
            )
        else:
            return await self._make_bridge_request("POST", "/mcp/extract-intent", payload)
    
    async def get_market_configuration(self, market_id: str) -> Dict[str, Any]:
        """
        Obtiene configuración específica del mercado.
        
        Args:
            market_id: ID del mercado (ej: "ES", "MX", "US")
            
        Returns:
            Dict con configuración del mercado
        """
        payload = {"market_id": market_id}
        
        if self.circuit_breaker:
            return await self.circuit_breaker.call(
                self._make_bridge_request,
                "POST",
                "/mcp/markets/get-config", 
                payload
            )
        else:
            return await self._make_bridge_request("POST", "/mcp/markets/get-config", payload)
    
    async def check_inventory_availability(
        self, 
        market_id: str, 
        product_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Verifica disponibilidad de inventario por mercado.
        
        Args:
            market_id: ID del mercado
            product_ids: Lista de IDs de productos
            
        Returns:
            Dict con disponibilidad por producto
        """
        payload = {
            "market_id": market_id,
            "product_ids": product_ids
        }
        
        if self.circuit_breaker:
            return await self.circuit_breaker.call(
                self._make_bridge_request,
                "POST",
                "/mcp/inventory/check-availability",
                payload
            )
        else:
            return await self._make_bridge_request("POST", "/mcp/inventory/check-availability", payload)
    
    async def _make_bridge_request(
        self, 
        method: str, 
        endpoint: str, 
        payload: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Realiza request HTTP al bridge con retry logic.
        
        Args:
            method: Método HTTP (GET, POST)
            endpoint: Endpoint del bridge
            payload: Datos a enviar
            
        Returns:
            Respuesta del bridge
            
        Raises:
            MCPBridgeError: Si el request falla después de reintentos
        """
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        url = f"{self.bridge_url}{endpoint}"
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"Bridge request attempt {attempt + 1}: {method} {endpoint}")
                
                if method.upper() == "GET":
                    response = await self.http_client.get(url, params=payload)
                elif method.upper() == "POST":
                    response = await self.http_client.post(url, json=payload)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                
                # Parse response
                response_data = response.json()
                
                # Update metrics
                latency = (time.time() - start_time) * 1000
                self._update_latency_metric(latency)
                self.metrics["successful_requests"] += 1
                
                logger.debug(f"Bridge request successful: {endpoint} ({latency:.2f}ms)")
                
                # Extract data from bridge response
                if response_data.get("success"):
                    return response_data
                else:
                    raise MCPBridgeError(f"Bridge returned error: {response_data.get('error', 'Unknown error')}")
                
            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(f"Bridge request timeout (attempt {attempt + 1}): {endpoint}")
                
            except httpx.HTTPStatusError as e:
                last_exception = e
                logger.warning(f"Bridge HTTP error (attempt {attempt + 1}): {e.response.status_code}")
                
                # Don't retry for client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    break
                    
            except Exception as e:
                last_exception = e
                logger.warning(f"Bridge request error (attempt {attempt + 1}): {e}")
            
            # Wait before retry (exponential backoff)
            if attempt < self.max_retries:
                wait_time = (2 ** attempt) * 0.5  # 0.5, 1, 2 seconds
                await asyncio.sleep(wait_time)
        
        # All attempts failed
        self.metrics["failed_requests"] += 1
        error_msg = f"Bridge request failed after {self.max_retries + 1} attempts: {endpoint}"
        logger.error(f"{error_msg}. Last error: {last_exception}")
        
        raise MCPBridgeError(f"{error_msg}. Last error: {last_exception}")
    
    async def _fallback_handler(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Manejador de fallback cuando el circuit breaker está abierto.
        
        Returns:
            Respuesta de fallback basada en el tipo de operación
        """
        logger.warning("Circuit breaker open, using fallback for MCP bridge")
        
        # Determinar tipo de operación basado en argumentos
        if len(args) >= 2:
            method = args[0]
            endpoint = args[1]
            payload = args[2] if len(args) > 2 else {}
            
            if "/extract-intent" in endpoint:
                return await self._fallback_intent_extraction(payload)
            elif "/get-config" in endpoint:
                return await self._fallback_market_config(payload)
            elif "/check-availability" in endpoint:
                return await self._fallback_inventory_check(payload)
        
        # Fallback genérico
        return {
            "success": True,
            "fallback": True,
            "message": "Using fallback due to bridge unavailability",
            "timestamp": datetime.now().isoformat()
        }
    
    async def _fallback_intent_extraction(self, payload: Dict) -> Dict[str, Any]:
        """Fallback para extracción de intención"""
        query = payload.get("query", "")
        
        # Análisis básico de keywords
        intent_type = "general"
        confidence = 0.5
        
        query_lower = query.lower()
        if any(word in query_lower for word in ["busco", "quiero", "necesito"]):
            intent_type = "search"
            confidence = 0.7
        elif any(word in query_lower for word in ["recomienda", "sugieres"]):
            intent_type = "recommendation"
            confidence = 0.7
        elif any(word in query_lower for word in ["comprar", "precio"]):
            intent_type = "purchase"
            confidence = 0.8
        
        return {
            "success": True,
            "intent": {
                "type": intent_type,
                "confidence": confidence,
                "attributes": [],
                "urgency": "medium",
                "source": "fallback_analysis",
                "fallback": True
            },
            "timestamp": datetime.now().isoformat()
        }
    
    async def _fallback_market_config(self, payload: Dict) -> Dict[str, Any]:
        """Fallback para configuración de mercado"""
        market_id = payload.get("market_id", "US")
        
        # Configuraciones básicas por mercado
        configs = {
            "US": {"currency": "USD", "language": "en", "timezone": "America/New_York"},
            "ES": {"currency": "EUR", "language": "es", "timezone": "Europe/Madrid"},
            "MX": {"currency": "MXN", "language": "es", "timezone": "America/Mexico_City"},
            "CO": {"currency": "COP", "language": "es", "timezone": "America/Bogota"},
            "CL": {"currency": "CLP", "language": "es", "timezone": "America/Santiago"}
        }
        
        config = configs.get(market_id, configs["US"])
        
        return {
            "success": True,
            "market_config": {
                "market_id": market_id,
                "currency": config["currency"],
                "primary_language": config["language"],
                "timezone": config["timezone"],
                "source": "fallback_config",
                "fallback": True
            },
            "timestamp": datetime.now().isoformat()
        }
    
    async def _fallback_inventory_check(self, payload: Dict) -> Dict[str, Any]:
        """Fallback para verificación de inventario"""
        product_ids = payload.get("product_ids", [])
        market_id = payload.get("market_id", "US")
        
        # Asumir disponibilidad básica para fallback
        availability = {}
        for product_id in product_ids:
            availability[product_id] = {
                "available": True,
                "quantity": 5,  # Cantidad conservadora
                "price": None,
                "estimated_delivery": "5-7 business days"
            }
        
        return {
            "success": True,
            "availability": availability,
            "market_id": market_id,
            "fallback": True,
            "timestamp": datetime.now().isoformat()
        }
    
    def _update_latency_metric(self, latency_ms: float):
        """Actualiza métrica de latencia promedio"""
        if self.metrics["average_latency"] == 0:
            self.metrics["average_latency"] = latency_ms
        else:
            # Promedio móvil exponencial
            alpha = 0.1
            self.metrics["average_latency"] = (
                (1 - alpha) * self.metrics["average_latency"] + alpha * latency_ms
            )
    
    async def get_metrics(self) -> Dict[str, Any]:
        """
        Obtiene métricas de rendimiento del cliente.
        
        Returns:
            Dict con métricas de rendimiento
        """
        success_rate = 0.0
        if self.metrics["total_requests"] > 0:
            success_rate = self.metrics["successful_requests"] / self.metrics["total_requests"]
        
        circuit_breaker_stats = {}
        if self.circuit_breaker:
            circuit_breaker_stats = self.circuit_breaker.get_stats()
        
        return {
            "client_metrics": self.metrics.copy(),
            "success_rate": success_rate,
            "circuit_breaker": circuit_breaker_stats,
            "bridge_url": self.bridge_url,
            "timeout_seconds": self.timeout,
            "max_retries": self.max_retries
        }
    
    async def close(self):
        """Cierra el cliente y limpia recursos"""
        await self.http_client.aclose()
        logger.info("MCPBridgeClient closed")

# Función de conveniencia para crear cliente configurado
def create_mcp_bridge_client(
    host: str = "localhost",
    port: int = 3001,
    timeout: int = 10,
    enable_circuit_breaker: bool = True
) -> MCPBridgeClient:
    """
    Crea un cliente MCP Bridge configurado.
    
    Args:
        host: Host del bridge
        port: Puerto del bridge
        timeout: Timeout en segundos
        enable_circuit_breaker: Si habilitar circuit breaker
        
    Returns:
        Cliente MCP Bridge configurado
    """
    return MCPBridgeClient(
        bridge_host=host,
        bridge_port=port,
        timeout=timeout,
        enable_circuit_breaker=enable_circuit_breaker
    )
