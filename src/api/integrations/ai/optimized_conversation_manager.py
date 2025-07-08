# src/api/integrations/ai/optimized_conversation_manager.py
"""
ConversationAIManager optimizado con circuit breakers, caching y mejoras de rendimiento.
Esta versión extiende el ConversationAIManager existente para la Fase 0 de consolidación.
"""

import asyncio
import logging
import time
import json
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from anthropic import Anthropic
import httpx
from cachetools import TTLCache
# aioredis removed - using redis.asyncio via RedisClient
from src.api.core.redis_client import RedisClient

from .ai_conversation_manager import ConversationAIManager, ConversationContext

logger = logging.getLogger(__name__)

class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open"""
    pass

class ConversationCircuitBreaker:
    """
    Circuit breaker específico para llamadas de conversación AI.
    Protege contra fallos en cascade de Claude API.
    """
    
    def __init__(
        self, 
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        # Estado del circuit breaker
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
        logger.info(f"Circuit breaker initialized: threshold={failure_threshold}, timeout={recovery_timeout}s")
    
    async def call(self, func, *args, **kwargs):
        """
        Ejecuta función protegida por circuit breaker.
        
        Args:
            func: Función a ejecutar
            *args, **kwargs: Argumentos para la función
            
        Returns:
            Resultado de la función
            
        Raises:
            CircuitBreakerError: Si el circuit breaker está abierto
        """
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
                self.success_count = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise CircuitBreakerError("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
            
        except Exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Determina si es momento de intentar resetear el circuit breaker"""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.recovery_timeout
    
    def _on_success(self):
        """Maneja éxito en la operación"""
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info("Circuit breaker CLOSED - recovered successfully")
        else:
            self.failure_count = max(0, self.failure_count - 1)
    
    def _on_failure(self):
        """Maneja fallo en la operación"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPEN - failure threshold reached ({self.failure_count})")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del circuit breaker"""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "time_since_last_failure": time.time() - self.last_failure_time if self.last_failure_time else None
        }

class OptimizedConversationAIManager(ConversationAIManager):
    """
    Versión optimizada del ConversationAIManager con:
    - Circuit breaker para llamadas Claude
    - Caching inteligente de respuestas
    - Connection pooling optimizado
    - Rate limiting
    - Fallback strategies robustas
    """
    
    def __init__(
        self,
        anthropic_api_key: str,
        perplexity_api_key: Optional[str] = None,
        use_perplexity_validation: bool = False,
        redis_client: Optional[RedisClient] = None,
        enable_circuit_breaker: bool = True,
        enable_caching: bool = True
    ):
        # Inicializar clase padre
        super().__init__(anthropic_api_key, perplexity_api_key, use_perplexity_validation)
        
        # Configuración de optimizaciones
        self.redis_client = redis_client
        self.enable_circuit_breaker = enable_circuit_breaker
        self.enable_caching = enable_caching
        
        # Circuit breaker para Claude API
        if enable_circuit_breaker:
            self.claude_circuit_breaker = ConversationCircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60,
                success_threshold=3
            )
            logger.info("Claude circuit breaker enabled")
        
        # Local cache para respuestas frecuentes
        if enable_caching:
            self.response_cache = TTLCache(maxsize=1000, ttl=1800)  # 30 min cache
            self.intent_cache = TTLCache(maxsize=500, ttl=900)      # 15 min cache
            logger.info("Local caching enabled")
        
        # Optimizar HTTP client para Claude
        self._optimize_http_client()
        
        # Métricas extendidas
        self.metrics.update({
            "cache_hits": 0,
            "cache_misses": 0,
            "circuit_breaker_trips": 0,
            "fallback_uses": 0,
            "optimization_enabled": True
        })
        
        logger.info("OptimizedConversationAIManager initialized successfully")
    
    def _optimize_http_client(self):
        """Optimiza el cliente HTTP para mejor rendimiento"""
        try:
            # Configurar connection pooling optimizado
            limits = httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30
            )
            
            timeout = httpx.Timeout(
                connect=10.0,
                read=30.0,
                write=10.0,
                pool=5.0
            )
            
            # Actualizar cliente HTTP de Claude
            if hasattr(self.claude, '_client') and hasattr(self.claude._client, '_client'):
                self.claude._client._client.close()
                self.claude._client._client = httpx.AsyncClient(
                    limits=limits,
                    timeout=timeout
                )
            
            # Actualizar nuestro cliente HTTP
            # No cerrar el cliente existente para evitar problemas en tests
            # El cliente se cerrara automaticamente al finalizar
            self.http_client = httpx.AsyncClient(
                limits=limits,
                timeout=timeout
            )
            
            logger.info("HTTP client optimized with connection pooling")
            
        except Exception as e:
            logger.warning(f"Failed to optimize HTTP client: {e}")
    
    async def process_conversation(
        self,
        user_message: str,
        context: ConversationContext,
        include_recommendations: bool = True
    ) -> Dict[str, Any]:
        """
        Versión optimizada del procesamiento de conversación.
        Incluye caching, circuit breaker y fallbacks.
        """
        start_time = time.time()
        
        try:
            # 1. Verificar caché local primero
            if self.enable_caching:
                cache_key = self._generate_cache_key(user_message, context)
                cached_response = self._get_from_cache(cache_key)
                
                if cached_response:
                    self.metrics["cache_hits"] += 1
                    cached_response["metadata"]["cached"] = True
                    cached_response["metadata"]["cache_hit_time"] = time.time()
                    logger.debug(f"Cache hit for conversation: {user_message[:50]}...")
                    return cached_response
                
                self.metrics["cache_misses"] += 1
            
            # 2. Verificar caché Redis si está disponible
            if self.redis_client and self.enable_caching:
                redis_cached = await self._get_from_redis_cache(cache_key)
                if redis_cached:
                    self.metrics["cache_hits"] += 1
                    redis_cached["metadata"]["cached"] = True
                    redis_cached["metadata"]["cache_source"] = "redis"
                    return redis_cached
            
            # 3. Procesar conversación con circuit breaker
            if self.enable_circuit_breaker:
                response = await self.claude_circuit_breaker.call(
                    self._process_conversation_protected,
                    user_message, context, include_recommendations
                )
            else:
                response = await self._process_conversation_protected(
                    user_message, context, include_recommendations
                )
            
            # 4. Guardar en caché si es exitoso
            if self.enable_caching and response.get("intent_analysis", {}).get("confidence", 0) > 0.7:
                self._save_to_cache(cache_key, response)
                
                if self.redis_client:
                    await self._save_to_redis_cache(cache_key, response)
            
            # 5. Actualizar métricas
            processing_time = (time.time() - start_time) * 1000
            response["metadata"]["processing_time_ms"] = processing_time
            response["metadata"]["optimized"] = True
            response["metadata"]["cached"] = False
            
            return response
            
        except CircuitBreakerError:
            self.metrics["circuit_breaker_trips"] += 1
            logger.warning("Circuit breaker is open, using fallback response")
            return await self._fallback_conversation_response(user_message, context)
            
        except Exception as e:
            logger.error(f"Error in optimized conversation processing: {e}")
            self.metrics["fallback_uses"] += 1
            return await self._fallback_conversation_response(user_message, context)
    
    async def _process_conversation_protected(
        self,
        user_message: str,
        context: ConversationContext,
        include_recommendations: bool
    ) -> Dict[str, Any]:
        """
        Procesamiento de conversación protegido por circuit breaker.
        Esta función será llamada a través del circuit breaker.
        """
        # Llamar al método padre con optimizaciones
        return await super().process_conversation(user_message, context, include_recommendations)
    
    def _generate_cache_key(self, user_message: str, context: ConversationContext) -> str:
        """Genera clave de caché consistente basada en mensaje y contexto"""
        # Incluir elementos relevantes del contexto para el cache key
        context_signature = {
            "market_id": context.market_id,
            "user_profile_hash": hashlib.md5(str(context.user_profile).encode()).hexdigest()[:8],
            "cart_items_count": len(context.cart_items),
            "conversation_length": len(context.conversation_history)
        }
        
        combined = f"{user_message}:{json.dumps(context_signature, sort_keys=True)}"
        return f"conv:{hashlib.md5(combined.encode()).hexdigest()}"
    
    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Obtiene respuesta del caché local"""
        if not self.enable_caching:
            return None
        
        try:
            return self.response_cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Error accessing local cache: {e}")
            return None
    
    def _save_to_cache(self, cache_key: str, response: Dict[str, Any]):
        """Guarda respuesta en caché local"""
        if not self.enable_caching:
            return
        
        try:
            # Solo cachear respuestas exitosas
            if response.get("intent_analysis", {}).get("confidence", 0) > 0.5:
                self.response_cache[cache_key] = response.copy()
        except Exception as e:
            logger.warning(f"Error saving to local cache: {e}")
    
    async def _get_from_redis_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Obtiene respuesta del caché Redis"""
        if not self.redis_client:
            return None
        
        try:
            cached_data = await self.redis_client.get(f"conversation:{cache_key}")
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Error accessing Redis cache: {e}")
        
        return None
    
    async def _save_to_redis_cache(self, cache_key: str, response: Dict[str, Any]):
        """Guarda respuesta en caché Redis"""
        if not self.redis_client:
            return
        
        try:
            await self.redis_client.set(
                f"conversation:{cache_key}",
                json.dumps(response),
                ex=1800  # 30 minutes TTL
            )
        except Exception as e:
            logger.warning(f"Error saving to Redis cache: {e}")
    
    async def _fallback_conversation_response(
        self, 
        user_message: str, 
        context: ConversationContext
    ) -> Dict[str, Any]:
        """
        Respuesta de fallback mejorada cuando Claude no está disponible.
        Incluye análisis básico de intención y respuesta contextualizada.
        """
        self.metrics["fallback_uses"] += 1
        
        # Análisis básico de intención usando palabras clave
        intent_analysis = self._basic_intent_analysis(user_message)
        
        # Generar respuesta contextualizada basada en el mercado
        market_config = self._get_market_specific_config(context.market_id)
        
        fallback_responses = {
            "search": f"Entiendo que buscas algo específico. Te ayudo a encontrar productos en {context.market_id}. ¿Puedes darme más detalles sobre lo que necesitas?",
            "recommendation": f"Perfecto, puedo recomendarte productos. Basándome en tu perfil, creo que te pueden interesar nuestras opciones disponibles en {context.currency}.",
            "comparison": "Te ayudo a comparar productos. ¿Cuáles específicamente te interesan?",
            "general": f"¡Hola! Estoy aquí para ayudarte a encontrar lo que necesitas. ¿En qué puedo asistirte hoy?"
        }
        
        response_text = fallback_responses.get(
            intent_analysis["type"], 
            fallback_responses["general"]
        )
        
        return {
            "conversation_response": response_text,
            "recommendations": [],
            "intent_analysis": intent_analysis,
            "context_update": {
                "user_interests": [],
                "session_state": "fallback_mode"
            },
            "metadata": {
                "primary_ai": "fallback",
                "model_used": "rule_based_fallback",
                "latency_ms": 50,  # Very fast fallback
                "tokens_used": 0,
                "validation_used": False,
                "optimized": True,
                "cached": False,
                "fallback_reason": "claude_api_unavailable",
                "market_config": market_config
            }
        }
    
    def _basic_intent_analysis(self, user_message: str) -> Dict[str, Any]:
        """Análisis básico de intención usando reglas simples"""
        message_lower = user_message.lower()
        
        # Palabras clave optimizadas con raíces de palabras
        intent_keywords = {
            "search": ["busco", "buscar", "quiero", "necesito", "buscando", "donde encuentro", "encontrar"],
            "recommendation": [
                "recomiend", "recomiénd", "recomend", 
                "sugier", "suger", "aconsejas", "aconsej",
                "mejor", "bueno", "buena"
            ],
            "comparison": ["compar", "diferencia", "cual es mejor", "versus", "vs", "entre"],
            "purchase": ["compr", "precio", "cuesta", "checkout", "carrito", "pagar"],
            "general": []
        }
        
        # Calcular scores por intención
        intent_scores = {}
        for intent_type, keywords in intent_keywords.items():
            score = sum(1 for keyword in keywords if keyword in message_lower)
            if score > 0:
                intent_scores[intent_type] = score / len(keywords) if keywords else 0
        
        # Determinar intención principal
        if intent_scores:
            primary_intent = max(intent_scores.keys(), key=lambda k: intent_scores[k])
            confidence = min(intent_scores[primary_intent] * 0.8, 0.9)  # Max 90% confidence for fallback
        else:
            primary_intent = "general"
            confidence = 0.5
        
        return {
            "type": primary_intent,
            "confidence": confidence,
            "attributes": [key for key, score in intent_scores.items() if score > 0],
            "urgency": "medium" if any(word in message_lower for word in ["urgente", "rapido", "ahora"]) else "low",
            "analysis_method": "keyword_based_fallback"
        }
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas de rendimiento extendidas"""
        base_metrics = await super().get_performance_metrics()
        
        # Añadir métricas de optimización
        optimization_metrics = {
            "cache_hit_ratio": self.metrics["cache_hits"] / max(
                self.metrics["cache_hits"] + self.metrics["cache_misses"], 1
            ),
            "circuit_breaker_stats": self.claude_circuit_breaker.get_stats() if self.enable_circuit_breaker else {},
            "fallback_usage_ratio": self.metrics["fallback_uses"] / max(
                self.metrics["claude_calls"] + self.metrics["fallback_uses"], 1
            ),
            "optimization_features": {
                "circuit_breaker_enabled": self.enable_circuit_breaker,
                "caching_enabled": self.enable_caching,
                "redis_cache_available": self.redis_client is not None,
                "http_pooling_enabled": True
            }
        }
        
        return {**base_metrics, **optimization_metrics}
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check extendido con estado de optimizaciones"""
        health_status = {
            "status": "healthy",
            "claude_api": "unknown",
            "optimization_features": {},
            "performance_metrics": {},
            "timestamp": time.time()
        }
        
        try:
            # Test básico de Claude API
            test_response = await self.claude.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            health_status["claude_api"] = "healthy"
            
        except Exception as e:
            health_status["claude_api"] = f"error: {str(e)}"
            health_status["status"] = "degraded"
        
        # Estado de optimizaciones
        health_status["optimization_features"] = {
            "circuit_breaker": {
                "enabled": self.enable_circuit_breaker,
                "state": self.claude_circuit_breaker.get_stats()["state"] if self.enable_circuit_breaker else "disabled"
            },
            "caching": {
                "local_enabled": self.enable_caching,
                "redis_enabled": self.redis_client is not None,
                "local_cache_size": len(self.response_cache) if self.enable_caching else 0
            }
        }
        
        # Métricas de rendimiento recientes
        health_status["performance_metrics"] = await self.get_performance_metrics()
        
        return health_status
    
    async def cleanup(self):
        """Limpieza extendida de recursos"""
        await super().cleanup()
        
        # Limpiar caches
        if self.enable_caching:
            self.response_cache.clear()
            self.intent_cache.clear()
        
        logger.info("OptimizedConversationAIManager cleanup completed")
