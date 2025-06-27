# src/api/mcp/client/mcp_client_enhanced.py
"""
MCPClient mejorado con Circuit Breaker, caching local y fallback strategies

Esta implementación mejora el MCPClient original agregando:
- Circuit breaker patterns para resiliencia
- Local caching para reducir latencia HTTP
- Fallback algorithms para cuando MCP falla
- Métricas de rendimiento detalladas
"""

import asyncio
import httpx
import logging
import time
import json
import hashlib
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from cachetools import TTLCache
import uuid

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .mcp_client import MCPClient, MCPClientError

logger = logging.getLogger(__name__)

class MCPClientEnhanced(MCPClient):
    """
    Cliente MCP mejorado con circuit breaker, caching y fallbacks
    """
    
    def __init__(
        self,
        bridge_host: str = "localhost",
        bridge_port: int = 3001,
        timeout: int = 30,
        enable_circuit_breaker: bool = True,
        enable_local_cache: bool = True,
        cache_ttl: int = 300  # 5 minutos
    ):
        super().__init__(bridge_host, bridge_port, timeout)
        
        # Local caching para intent extraction
        self.enable_local_cache = enable_local_cache
        if enable_local_cache:
            self.intent_cache = TTLCache(maxsize=1000, ttl=cache_ttl)
            self.market_cache = TTLCache(maxsize=100, ttl=cache_ttl * 2)  # Market data cambia menos
            self.conversation_cache = TTLCache(maxsize=500, ttl=cache_ttl // 2)  # Conversations más frecuentes
            logger.info(f"Local caching enabled with TTL={cache_ttl}s")
        
        # Circuit breaker para operaciones HTTP
        if enable_circuit_breaker:
            self.circuit_breaker = CircuitBreaker(
                name="mcp_http_client",
                config=CircuitBreakerConfig(
                    failure_threshold=3,
                    timeout_seconds=30,
                    success_threshold=2,
                    max_timeout=timeout
                ),
                fallback_function=self._http_fallback
            )
            logger.info("Circuit breaker enabled for MCP operations")
        else:
            self.circuit_breaker = None
        
        # Métricas de rendimiento
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "fallback_used": 0,
            "average_response_time": 0.0,
            "last_request_time": None
        }
        
        # Fallback data para cuando MCP no está disponible
        self._fallback_intents = {
            "busco": {"type": "search", "confidence": 0.7},
            "quiero": {"type": "search", "confidence": 0.6},
            "necesito": {"type": "search", "confidence": 0.7},
            "comprar": {"type": "purchase_intent", "confidence": 0.8},
            "precio": {"type": "price_inquiry", "confidence": 0.8},
            "comparar": {"type": "comparison", "confidence": 0.7},
            "recomienda": {"type": "recommendation", "confidence": 0.8},
            "mejor": {"type": "recommendation", "confidence": 0.6}
        }
    
    async def extract_intent(self, conversation_context: dict) -> dict:
        """
        Extrae intención con circuit breaker y fallback local
        
        Args:
            conversation_context: Contexto de la conversación
            
        Returns:
            Diccionario con intención detectada
        """
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        query = conversation_context.get("query", "")
        cache_key = self._get_cache_key("intent", query)
        
        # Verificar caché local primero
        if self.enable_local_cache and cache_key in self.intent_cache:
            self.metrics["cache_hits"] += 1
            logger.debug(f"Intent cache hit for: {query[:50]}...")
            cached_result = self.intent_cache[cache_key]
            cached_result["cached"] = True
            cached_result["cache_hit"] = True
            return cached_result
        
        self.metrics["cache_misses"] += 1
        
        # Intentar vía MCP con circuit breaker
        if self.circuit_breaker:
            try:
                result = await self.circuit_breaker.call(
                    self._extract_intent_via_mcp,
                    conversation_context
                )
                
                # Guardar en caché si es exitoso
                if self.enable_local_cache:
                    self.intent_cache[cache_key] = result
                
                result["cached"] = False
                result["fallback_used"] = False
                
                # Actualizar métricas
                response_time = (time.time() - start_time) * 1000
                self._update_response_time_metric(response_time)
                
                return result
                
            except Exception as e:
                logger.warning(f"Circuit breaker failed for intent extraction: {e}")
                # Circuit breaker will use fallback automatically
                self.metrics["fallback_used"] += 1
                return await self._extract_intent_fallback(conversation_context)
        else:
            # Sin circuit breaker, intentar directo con fallback manual
            try:
                result = await self._extract_intent_via_mcp(conversation_context)
                
                if self.enable_local_cache:
                    self.intent_cache[cache_key] = result
                
                result["cached"] = False
                result["fallback_used"] = False
                return result
                
            except Exception as e:
                logger.warning(f"Direct MCP call failed: {e}")
                self.metrics["fallback_used"] += 1
                return await self._extract_intent_fallback(conversation_context)
    
    async def _extract_intent_via_mcp(self, conversation_context: dict) -> dict:
        """Extrae intención vía MCP (protegido por circuit breaker)"""
        try:
            # Usar método padre para análisis de intención
            result = await super().analyze_intent(
                conversation_context.get("query", ""),
                context=conversation_context
            )
            
            # Enriquecer resultado con metadata
            result.update({
                "timestamp": datetime.utcnow().isoformat(),
                "source": "mcp_bridge",
                "method": "analyze_intent"
            })
            
            return result
            
        except Exception as e:
            logger.error(f"MCP intent extraction failed: {e}")
            raise
    
    async def _extract_intent_fallback(self, conversation_context: dict) -> dict:
        """
        Extracción de intención usando algoritmos locales NLP básicos
        """
        query = conversation_context.get("query", "").lower()
        
        # Análisis básico de palabras clave
        detected_intent = "general"
        confidence = 0.5
        
        # Buscar patrones conocidos
        for keyword, intent_data in self._fallback_intents.items():
            if keyword in query:
                detected_intent = intent_data["type"]
                confidence = intent_data["confidence"]
                break
        
        # Análisis adicional para mejorar confianza
        if any(word in query for word in ["rápido", "urgente", "ahora"]):
            confidence += 0.1
        
        if any(word in query for word in ["barato", "económico", "precio"]):
            if detected_intent == "general":
                detected_intent = "price_inquiry"
                confidence = 0.7
        
        result = {
            "type": detected_intent,
            "confidence": min(confidence, 1.0),
            "query": conversation_context.get("query", ""),
            "timestamp": datetime.utcnow().isoformat(),
            "source": "local_nlp_fallback",
            "method": "keyword_analysis",
            "fallback_used": True,
            "keywords_found": [k for k in self._fallback_intents.keys() if k in query]
        }
        
        logger.info(f"Fallback intent detection: {detected_intent} (confidence: {confidence:.2f})")
        return result
    
    async def get_market_context(self, user_location: str) -> dict:
        """
        Obtiene contexto de mercado con caching y fallback
        """
        cache_key = self._get_cache_key("market", user_location)
        
        # Verificar caché
        if self.enable_local_cache and cache_key in self.market_cache:
            self.metrics["cache_hits"] += 1
            cached_result = self.market_cache[cache_key]
            cached_result["cached"] = True
            return cached_result
        
        self.metrics["cache_misses"] += 1
        
        # Intentar vía MCP
        if self.circuit_breaker:
            try:
                # Simulado: en implementación real haría call al bridge
                result = await self._get_market_context_via_mcp(user_location)
                
                if self.enable_local_cache:
                    self.market_cache[cache_key] = result
                
                return result
                
            except Exception as e:
                logger.warning(f"Market context MCP failed: {e}")
                return self._get_market_context_fallback(user_location)
        else:
            try:
                result = await self._get_market_context_via_mcp(user_location)
                if self.enable_local_cache:
                    self.market_cache[cache_key] = result
                return result
            except Exception as e:
                logger.warning(f"Market context failed: {e}")
                return self._get_market_context_fallback(user_location)
    
    async def _get_market_context_via_mcp(self, user_location: str) -> dict:
        """Obtiene contexto de mercado vía MCP"""
        # En implementación real, esto haría una llamada HTTP al bridge
        # Por ahora simulamos la respuesta
        await asyncio.sleep(0.1)  # Simular latencia de red
        
        return {
            "market_id": self._detect_market_from_location(user_location),
            "currency": "USD",
            "language": "en",
            "timezone": "UTC",
            "source": "mcp_bridge",
            "cached": False
        }
    
    def _get_market_context_fallback(self, user_location: str) -> dict:
        """Fallback para contexto de mercado"""
        market_id = self._detect_market_from_location(user_location)
        
        # Configuraciones de mercado por defecto
        market_configs = {
            "US": {"currency": "USD", "language": "en", "timezone": "America/New_York"},
            "ES": {"currency": "EUR", "language": "es", "timezone": "Europe/Madrid"},
            "MX": {"currency": "MXN", "language": "es", "timezone": "America/Mexico_City"},
            "default": {"currency": "USD", "language": "en", "timezone": "UTC"}
        }
        
        config = market_configs.get(market_id, market_configs["default"])
        
        return {
            "market_id": market_id,
            "source": "local_fallback",
            "cached": False,
            "fallback_used": True,
            **config
        }
    
    def _detect_market_from_location(self, location: str) -> str:
        """Detección básica de mercado por ubicación"""
        location_lower = location.lower()
        
        if any(country in location_lower for country in ["spain", "españa", "es"]):
            return "ES"
        elif any(country in location_lower for country in ["mexico", "méxico", "mx"]):
            return "MX"
        elif any(country in location_lower for country in ["chile", "cl"]):
            return "CL"
        elif any(country in location_lower for country in ["colombia", "co"]):
            return "CO"
        elif any(country in location_lower for country in ["usa", "us", "united states"]):
            return "US"
        else:
            return "default"
    
    async def capture_real_time_event(self, event: dict):
        """
        Captura eventos en tiempo real con circuit breaker
        """
        if self.circuit_breaker:
            try:
                return await self.circuit_breaker.call(
                    self._capture_event_via_mcp,
                    event
                )
            except Exception as e:
                logger.warning(f"Event capture failed: {e}")
                return await self._capture_event_fallback(event)
        else:
            try:
                return await self._capture_event_via_mcp(event)
            except Exception as e:
                logger.warning(f"Event capture failed: {e}")
                return await self._capture_event_fallback(event)
    
    async def _capture_event_via_mcp(self, event: dict):
        """Captura evento vía MCP"""
        # Implementación simulada
        await asyncio.sleep(0.05)  # Simular latencia
        
        return {
            "status": "captured",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "source": "mcp_bridge"
        }
    
    async def _capture_event_fallback(self, event: dict):
        """Fallback para captura de eventos"""
        # En fallback, simplemente loggeamos el evento
        logger.info(f"Event captured in fallback mode: {event.get('type', 'unknown')}")
        
        return {
            "status": "captured_fallback",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "source": "local_fallback",
            "note": "Event logged locally, sync to MCP when available"
        }
    
    async def _http_fallback(self, *args, **kwargs):
        """
        Fallback general para operaciones HTTP cuando circuit breaker está abierto
        """
        logger.warning("HTTP circuit breaker is open, using fallback")
        
        # Determinar tipo de operación por argumentos
        if len(args) > 0 and isinstance(args[0], dict):
            context = args[0]
            if "query" in context:
                return await self._extract_intent_fallback(context)
        
        # Fallback genérico
        return {
            "status": "fallback",
            "timestamp": datetime.utcnow().isoformat(),
            "source": "circuit_breaker_fallback"
        }
    
    def _get_cache_key(self, operation: str, data: str) -> str:
        """Genera clave de caché consistente"""
        return f"{operation}:{hashlib.md5(data.encode()).hexdigest()}"
    
    def _update_response_time_metric(self, response_time_ms: float):
        """Actualiza métrica de tiempo de respuesta promedio"""
        if self.metrics["average_response_time"] == 0:
            self.metrics["average_response_time"] = response_time_ms
        else:
            # Promedio móvil simple
            self.metrics["average_response_time"] = (
                self.metrics["average_response_time"] * 0.8 + response_time_ms * 0.2
            )
        
        self.metrics["last_request_time"] = datetime.utcnow().isoformat()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas de rendimiento del cliente"""
        cache_hit_ratio = 0.0
        total_cache_requests = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        if total_cache_requests > 0:
            cache_hit_ratio = self.metrics["cache_hits"] / total_cache_requests
        
        circuit_breaker_stats = {}
        if self.circuit_breaker:
            circuit_breaker_stats = self.circuit_breaker.get_stats()
        
        return {
            "client_metrics": self.metrics.copy(),
            "cache_hit_ratio": cache_hit_ratio,
            "circuit_breaker": circuit_breaker_stats,
            "cache_sizes": {
                "intent_cache": len(self.intent_cache) if self.enable_local_cache else 0,
                "market_cache": len(self.market_cache) if self.enable_local_cache else 0,
                "conversation_cache": len(self.conversation_cache) if self.enable_local_cache else 0
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check mejorado con métricas"""
        try:
            # Intentar health check del bridge
            base_health = await super().health_check()
            
            # Agregar métricas propias
            metrics = self.get_metrics()
            
            status = "healthy"
            if self.circuit_breaker and self.circuit_breaker.is_open:
                status = "degraded"
            
            return {
                **base_health,
                "enhanced_client": {
                    "status": status,
                    "metrics": metrics,
                    "features": {
                        "circuit_breaker": self.circuit_breaker is not None,
                        "local_cache": self.enable_local_cache
                    }
                }
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "enhanced_client": {
                    "status": "fallback_mode",
                    "metrics": self.get_metrics()
                }
            }
    
    async def reset_circuit_breaker(self):
        """Reset manual del circuit breaker"""
        if self.circuit_breaker:
            await self.circuit_breaker.reset()
            logger.info("Circuit breaker manually reset")
    
    def clear_cache(self):
        """Limpiar caché local"""
        if self.enable_local_cache:
            self.intent_cache.clear()
            self.market_cache.clear()
            self.conversation_cache.clear()
            logger.info("All local caches cleared")
    
    async def close(self):
        """Cerrar cliente con cleanup de recursos"""
        await super().close()
        if self.enable_local_cache:
            self.clear_cache()
        logger.info("MCPClientEnhanced closed successfully")