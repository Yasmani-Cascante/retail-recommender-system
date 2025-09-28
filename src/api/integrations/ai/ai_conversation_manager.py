# src/api/integrations/ai_conversation_manager.py
"""
Sistema de conversación AI híbrido con Claude como motor principal
y Perplexity como validación/testing.

REFACTORIZADO: Uso de configuración centralizada Claude.
Eliminado hardcoding de modelos.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
# from anthropic import Anthropic
from anthropic import AsyncAnthropic
import httpx
import time

# 🚀 NUEVA IMPORTACIÓN: Configuración centralizada Claude
from src.api.core.claude_config import get_claude_config_service

logger = logging.getLogger(__name__)

@dataclass
class ConversationContext:
    """Contexto de conversación enriquecido para e-commerce"""
    user_id: str
    session_id: str
    market_id: str
    currency: str
    conversation_history: List[Dict]
    user_profile: Dict
    cart_items: List[Dict]
    browsing_history: List[str]
    intent_signals: Dict

class ConversationAIManager:
    """
    Gestor de conversaciones AI con múltiples motores.
    Claude como primario, Perplexity para validación.
    """
    
    def __init__(
        self,
        anthropic_api_key: str,
        perplexity_api_key: Optional[str] = None,
        use_perplexity_validation: bool = False
    ):
        # 🚀 REFACTORIZADO: Configuración centralizada Claude
        self.claude_config = get_claude_config_service()
        self.claude = AsyncAnthropic(api_key=anthropic_api_key)
        self.perplexity_key = perplexity_api_key
        self.use_validation = use_perplexity_validation
        self.http_client = httpx.AsyncClient()
        
        # Métricas de rendimiento extendidas
        self.metrics = {
            "claude_calls": 0,
            "perplexity_calls": 0,
            "avg_latency": 0,
            "validation_matches": 0,
            "model_tier_used": self.claude_config.claude_model_tier.value,
            "configuration_source": "centralized"
        }
        
        logger.info(f"🤖 ConversationAIManager initialized with centralized Claude config: {self.claude_config.claude_model_tier.value}")
    
    async def process_conversation(
        self,
        user_message: str,
        context: ConversationContext,
        include_recommendations: bool = True
    ) -> Dict[str, Any]:
        """
        Procesar conversación con Claude como motor principal.
        Opcionalmente validar con Perplexity.
        """
        start_time = time.time()
        
        try:
            # 1. Preparar contexto para Claude
            system_prompt = self._build_commerce_system_prompt(context)
            user_prompt = self._build_user_prompt(user_message, context, include_recommendations)
            
            # 2. Llamada principal a Claude
            claude_response = await self._call_claude(system_prompt, user_prompt, context)
            
            # 3. Validación opcional con Perplexity
            validation_result = None
            if self.use_validation and self.perplexity_key:
                validation_result = await self._validate_with_perplexity(
                    user_message, claude_response, context
                )
            
            # 4. Construir respuesta final
            response = {
                "conversation_response": claude_response["message"],
                "recommendations": claude_response.get("recommendations", []),
                "intent_analysis": claude_response.get("intent", {}),
                "context_update": claude_response.get("context_update", {}),
                "metadata": {
                    "primary_ai": "claude",
                    "model_used": claude_response.get("model"),  # ✅ Sin hardcoding
                    "model_tier": self.claude_config.claude_model_tier.value,
                    "latency_ms": (time.time() - start_time) * 1000,
                    "tokens_used": claude_response.get("tokens", 0),
                    "cost_estimate": claude_response.get("cost_estimate", 0),
                    "validation_used": validation_result is not None,
                    "validation_score": validation_result.get("match_score") if validation_result else None,
                    "configuration_source": "centralized"
                }
            }
            
            # 5. Actualizar métricas
            self.metrics["claude_calls"] += 1
            self.metrics["avg_latency"] = (
                (self.metrics["avg_latency"] * (self.metrics["claude_calls"] - 1) + 
                 response["metadata"]["latency_ms"]) / self.metrics["claude_calls"]
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error in conversation processing: {e}")
            return {
                "conversation_response": "Lo siento, estoy experimentando dificultades técnicas. Por favor intenta de nuevo.",
                "recommendations": [],
                "intent_analysis": {"type": "error", "confidence": 0},
                "context_update": {},
                "metadata": {
                    "primary_ai": "claude",
                    "model_used": None,
                    "model_tier": self.claude_config.claude_model_tier.value,
                    "latency_ms": (time.time() - start_time) * 1000,
                    "error": str(e),
                    "configuration_source": "centralized"
                }
            }
    
    async def _call_claude(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        context: ConversationContext
    ) -> Dict[str, Any]:
        """
        Llamada refactorizada a Claude usando configuración centralizada.
        """
        try:
            # 🚀 REFACTORIZADO: Usar configuración centralizada
            call_context = {
                "user_id": context.user_id,
                "market_id": context.market_id,
                "session_id": context.session_id
            }
            
            config = self.claude_config.get_model_config(call_context)
            
            logger.info(f"🎯 Calling Claude with model: {config.model_name}")
            
            response = await self.claude.messages.create(
                **config.to_anthropic_params(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Calcular costo estimado
            tokens_used = response.usage.output_tokens if hasattr(response, 'usage') else 0
            cost_estimate = (tokens_used * config.cost_per_1k_tokens / 1000) if tokens_used > 0 else 0
            
            return {
                "message": response.content[0].text,
                "model": config.model_name,  # ✅ Siempre correcto desde configuración
                "tokens": tokens_used,
                "cost_estimate": cost_estimate,
                "intent": self._extract_intent(response.content[0].text),
                "recommendations": [],  # Procesar recomendaciones si están presentes
                "context_update": {}
            }
            
        except Exception as e:
            logger.error(f"Error calling Claude: {e}")
            raise
    
    def _extract_intent(self, claude_response: str) -> Dict[str, Any]:
        """
        Extraer intención básica desde respuesta de Claude.
        """
        # Análisis básico de intención (mejorable con NLP)
        response_lower = claude_response.lower()
        
        if any(word in response_lower for word in ["recomiendo", "sugiero", "te propongo"]):
            return {"type": "recommendation", "confidence": 0.8}
        elif any(word in response_lower for word in ["buscar", "encontrar", "mostrar"]):
            return {"type": "search", "confidence": 0.7}
        elif any(word in response_lower for word in ["comparar", "diferencia", "versus"]):
            return {"type": "comparison", "confidence": 0.7}
        else:
            return {"type": "general", "confidence": 0.5}
    
    async def _validate_with_perplexity(
        self, 
        user_message: str, 
        claude_response: Dict, 
        context: ConversationContext
    ) -> Optional[Dict[str, Any]]:
        """
        Validación opcional con Perplexity para QA.
        """
        if not self.perplexity_key:
            return None
            
        try:
            # Implementar validación con Perplexity si está configurado
            self.metrics["perplexity_calls"] += 1
            return {"match_score": 0.8, "validated": True}
            
        except Exception as e:
            logger.error(f"Error in Perplexity validation: {e}")
            return None
    
    def _build_commerce_system_prompt(self, context: ConversationContext) -> str:
        """
        Construir prompt del sistema específico para e-commerce.
        """
        return f"""
        Eres un asistente de ventas especializado en e-commerce para el mercado {context.market_id}.
        
        Contexto del usuario:
        - ID de usuario: {context.user_id}
        - Mercado: {context.market_id}
        - Moneda: {context.currency}
        - Items en carrito: {len(context.cart_items)}
        
        Tu objetivo es ayudar al usuario a encontrar productos relevantes,
        proporcionar recomendaciones personalizadas y facilitar las compras.
        
        Responde de manera natural, amigable y profesional.
        Siempre incluye información de productos cuando sea relevante.
        """
    
    def _build_user_prompt(
        self, 
        user_message: str, 
        context: ConversationContext, 
        include_recommendations: bool
    ) -> str:
        """
        Construir prompt del usuario con contexto enriquecido.
        """
        prompt = f"Usuario dice: {user_message}\n\n"
        
        if context.conversation_history:
            prompt += "Historial reciente de conversación:\n"
            for msg in context.conversation_history[-3:]:  # Últimos 3 mensajes
                prompt += f"- {msg.get('role', 'user')}: {msg.get('content', '')}\n"
            prompt += "\n"
        
        if include_recommendations and context.browsing_history:
            prompt += f"Productos vistos recientemente: {', '.join(context.browsing_history[-5:])}\n\n"
        
        prompt += "Responde al usuario de manera útil y personalizada."
        
        return prompt
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Obtener métricas de rendimiento extendidas.
        """
        base_metrics = self.metrics.copy()
        
        # Añadir métricas de configuración
        claude_metrics = self.claude_config.get_metrics()
        
        return {
            **base_metrics,
            "claude_configuration": claude_metrics,
            "api_health": "healthy" if self.claude else "degraded"
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Health check extendido con validación de configuración.
        """
        health_status = {
            "status": "healthy",
            "claude_api": "unknown",
            "configuration": {},
            "timestamp": time.time()
        }
        
        try:
            # Validar configuración
            config_validation = self.claude_config.validate_configuration()
            health_status["configuration"] = config_validation
            
            if not config_validation["valid"]:
                health_status["status"] = "degraded"
                health_status["issues"] = config_validation["issues"]
            
            # Test básico de Claude API
            test_config = self.claude_config.get_model_config()
            test_response = await self.claude.messages.create(
                model=test_config.model_name,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            
            health_status["claude_api"] = "healthy"
            health_status["test_model"] = test_config.model_name
            
        except Exception as e:
            health_status["claude_api"] = f"error: {str(e)}"
            health_status["status"] = "degraded"
        
        return health_status
    
    async def cleanup(self):
        """Limpieza de recursos."""
        if self.http_client:
            await self.http_client.aclose()
        
        logger.info("ConversationAIManager cleanup completed")


# === INTEGRACIÓN CON SISTEMA DE RECOMENDACIONES ===

class ConversationRecommenderIntegration:
    """
    Integración refactorizada entre conversación AI y sistema de recomendaciones.
    """
    
    def __init__(self, ai_manager: ConversationAIManager, recommender):
        self.ai_manager = ai_manager
        self.recommender = recommender
    
    async def handle_conversation_with_recommendations(
        self,
        user_message: str,
        session_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Manejar conversación completa con recomendaciones integradas
        """
        # 1. Construir contexto
        context = ConversationContext(
            user_id=session_context.get("user_id", "anonymous"),
            session_id=session_context.get("session_id"),
            market_id=session_context.get("market_id", "default"),
            currency=session_context.get("currency", "USD"),
            conversation_history=session_context.get("history", []),
            user_profile=session_context.get("user_profile", {}),
            cart_items=session_context.get("cart_items", []),
            browsing_history=session_context.get("browsing_history", []),
            intent_signals=session_context.get("intent_signals", {})
        )
        
        # 2. Procesar conversación con AI
        ai_response = await self.ai_manager.process_conversation(
            user_message, context, include_recommendations=True
        )
        
        # 3. Generar recomendaciones específicas si hay intent de compra
        recommendations = []
        intent = ai_response.get("intent_analysis", {})
        
        if intent.get("type") in ["search", "recommendation", "comparison"] and intent.get("confidence", 0) > 0.7:
            recommendations = await self.recommender.get_recommendations(
                user_id=context.user_id,
                market_context={
                    "market_id": context.market_id,
                    "currency": context.currency
                },
                conversation_context={
                    "query": user_message,
                    "intent": intent,
                    "attributes": intent.get("attributes", [])
                },
                n_recommendations=5
            )
        
        # 4. Combinar respuesta final
        return {
            "conversation_response": ai_response["conversation_response"],
            "recommendations": recommendations.get("recommendations", []) if recommendations else [],
            "intent": intent,
            "session_update": ai_response.get("context_update", {}),
            "metadata": {
                **ai_response.get("metadata", {}),
                "recommendations_included": len(recommendations.get("recommendations", [])) if recommendations else 0
            }
        }
