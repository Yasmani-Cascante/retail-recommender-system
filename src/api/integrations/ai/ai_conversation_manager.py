# src/api/integrations/ai_conversation_manager.py
"""
Sistema de conversación AI híbrido con Claude como motor principal
y Perplexity como validación/testing.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
# from anthropic import Anthropic
from anthropic import AsyncAnthropic
import httpx
import time

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
        # self.claude = Anthropic(api_key=anthropic_api_key)
        self.claude = AsyncAnthropic(api_key=anthropic_api_key)
        self.perplexity_key = perplexity_api_key
        self.use_validation = use_perplexity_validation
        self.http_client = httpx.AsyncClient()
        
        # Métricas de rendimiento
        self.metrics = {
            "claude_calls": 0,
            "perplexity_calls": 0,
            "avg_latency": 0,
            "validation_matches": 0
        }
    
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
                    "model_used": claude_response.get("model", "claude-3-sonnet-20240229"),
                    "latency_ms": (time.time() - start_time) * 1000,
                    "tokens_used": claude_response.get("tokens", 0),
                    "validation_used": validation_result is not None,
                    "validation_score": validation_result.get("match_score") if validation_result else None
                }
            }
            
            # 5. Actualizar métricas
            self._update_metrics("claude", time.time() - start_time)
            
            logger.info(f"✅ Conversation processed successfully in {response['metadata']['latency_ms']:.0f}ms")
            return response
            
        except Exception as e:
            logger.error(f"Error en conversación AI: {e}")
            # Fallback a respuesta básica
            return self._fallback_response(user_message, context)
    
    def _build_commerce_system_prompt(self, context: ConversationContext) -> str:
        """
        Construir system prompt específico para commerce conversacional.
        Personalizado por mercado y contexto de usuario.
        """
        market_config = self._get_market_specific_config(context.market_id)
        
        system_prompt = f"""Eres un asistente de compras AI especializado en recomendaciones personalizadas para e-commerce.

CONTEXTO DEL MERCADO:
- Mercado: {context.market_id}
- Moneda: {context.currency}
- Preferencias culturales: {market_config.get('cultural_preferences', 'Estándar')}
- Idioma: {market_config.get('language', 'es')}

CONTEXTO DEL USUARIO:
- ID de usuario: {context.user_id}
- Perfil: {context.user_profile.get('summary', 'Usuario nuevo')}
- Historial de navegación reciente: {context.browsing_history[-5:] if context.browsing_history else 'Ninguno'}
- Productos en carrito: {len(context.cart_items)} items

CAPACIDADES ESPECÍFICAS:
1. Analizar intención de compra en lenguaje natural
2. Recomendar productos específicos con justificación
3. Considerar presupuesto, preferencias y contexto cultural
4. Mantener conversación natural y comercialmente relevante
5. Adaptar tono y recomendaciones al mercado local

FORMATO DE RESPUESTA:
- Respuesta conversacional natural
- Recomendaciones específicas si aplica
- Análisis de intención para sistema de recomendaciones
- Contexto actualizado para próxima interacción

REGLAS IMPORTANTES:
- Siempre considera el contexto cultural del mercado {context.market_id}
- Personaliza basado en historial y perfil del usuario
- Mantén un tono profesional pero amigable
- Si no tienes información suficiente, haz preguntas clarificadoras
- Prioriza recomendaciones disponibles en el mercado actual"""
        
        return system_prompt
    
    def _build_user_prompt(
        self, 
        user_message: str, 
        context: ConversationContext,
        include_recommendations: bool
    ) -> str:
        """Construir prompt de usuario enriquecido con contexto"""
        
        # Historial de conversación reciente
        recent_history = context.conversation_history[-3:] if context.conversation_history else []
        history_text = "\n".join([
            f"Usuario: {msg.get('user', '')}\nAsistente: {msg.get('assistant', '')}"
            for msg in recent_history
        ])
        
        # Información del carrito actual
        cart_info = ""
        if context.cart_items:
            cart_info = f"\nProductos en carrito actual:\n"
            for item in context.cart_items[:3]:  # Máximo 3 items
                cart_info += f"- {item.get('title', 'Producto')} (${item.get('price', 0)})\n"
        
        # Prompt principal
        user_prompt = f"""HISTORIAL DE CONVERSACIÓN RECIENTE:
{history_text if history_text else 'Nueva conversación'}

{cart_info}

MENSAJE ACTUAL DEL USUARIO:
{user_message}

INSTRUCCIONES:
1. Responde de manera conversacional y útil
2. Analiza la intención del usuario (búsqueda, comparación, compra, etc.)
{"3. Incluye recomendaciones específicas de productos si es relevante" if include_recommendations else "3. Enfócate en la conversación sin incluir recomendaciones específicas"}
4. Considera el contexto del mercado {context.market_id}
5. Mantén la personalización basada en el perfil del usuario

Proporciona tu respuesta en el siguiente formato JSON:
{{
    "message": "Tu respuesta conversacional aquí",
    "intent": {{
        "type": "search|recommendation|comparison|purchase|general",
        "confidence": 0.0-1.0,
        "attributes": ["atributos", "detectados"],
        "urgency": "low|medium|high"
    }},
    {"recommendations": [{"product_id": "id", "reason": "razón personalizada"}]," if include_recommendations else ""}
    "context_update": {{
        "user_interests": ["nuevos", "intereses"],
        "session_state": "browsing|considering|ready_to_buy"
    }}
}}"""
        
        return user_prompt
    
    async def _call_claude(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        context: ConversationContext
    ) -> Dict[str, Any]:
        """Llamada optimizada a Claude API"""
        
        try:
            message = await self.claude.messages.create(
                model="claude-3-sonnet-20240229",  # O claude-3-haiku para latencia
                max_tokens=2000,
                temperature=0.7,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Parsear respuesta JSON
            response_text = message.content[0].text
            
            try:
                import json
                parsed_response = json.loads(response_text)
            except json.JSONDecodeError:
                # Fallback si Claude no devuelve JSON válido
                parsed_response = {
                    "message": response_text,
                    "intent": {"type": "general", "confidence": 0.5},
                    "context_update": {}
                }
            
            # Enriquecer con metadata
            parsed_response.update({
                "model": "claude-3-sonnet-20240229",
                "tokens": message.usage.input_tokens + message.usage.output_tokens
            })
            
            self.metrics["claude_calls"] += 1
            return parsed_response
            
        except Exception as e:
            logger.error(f"Error en llamada a Claude: {e}")
            raise
    
    async def _validate_with_perplexity(
        self,
        user_message: str,
        claude_response: Dict,
        context: ConversationContext
    ) -> Optional[Dict]:
        """
        Validar respuesta de Claude con Perplexity.
        Útil para testing y benchmarking.
        """
        if not self.perplexity_key:
            return None
        
        try:
            # Prompt para Perplexity centrado en validación
            validation_prompt = f"""Como experto en e-commerce, valida si esta respuesta es apropiada:

Mensaje usuario: {user_message}
Respuesta AI: {claude_response.get('message', '')}
Mercado: {context.market_id}

¿Es la respuesta relevante, útil y apropiada para el contexto? Responde brevemente."""
            
            headers = {
                'Authorization': f'Bearer {self.perplexity_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'llama-3.1-sonar-small-128k-online',
                'messages': [
                    {'role': 'user', 'content': validation_prompt}
                ],
                'max_tokens': 200
            }
            
            response = await self.http_client.post(
                'https://api.perplexity.ai/chat/completions',
                headers=headers,
                json=payload,
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                validation_text = result['choices'][0]['message']['content']
                
                # Análisis simple de sentimiento para match score
                positive_indicators = ['apropiada', 'relevante', 'útil', 'correcto', 'bien']
                match_score = sum(1 for indicator in positive_indicators 
                                if indicator in validation_text.lower()) / len(positive_indicators)
                
                self.metrics["perplexity_calls"] += 1
                self.metrics["validation_matches"] += 1 if match_score > 0.6 else 0
                
                return {
                    "validation_text": validation_text,
                    "match_score": match_score,
                    "timestamp": time.time()
                }
            
        except Exception as e:
            logger.warning(f"Error en validación con Perplexity: {e}")
        
        return None
    
    def _get_market_specific_config(self, market_id: str) -> Dict:
        """Configuración específica por mercado"""
        configs = {
            "US": {
                "language": "en",
                "cultural_preferences": "Direct, efficiency-focused",
                "currency_symbol": "$"
            },
            "ES": {
                "language": "es", 
                "cultural_preferences": "Formal, relationship-oriented",
                "currency_symbol": "€"
            },
            "MX": {
                "language": "es",
                "cultural_preferences": "Warm, family-oriented", 
                "currency_symbol": "$"
            },
            "default": {
                "language": "es",
                "cultural_preferences": "Standard",
                "currency_symbol": "$"
            }
        }
        return configs.get(market_id, configs["default"])
    
    def _fallback_response(self, user_message: str, context: ConversationContext) -> Dict:
        """Respuesta de fallback cuando AI falla"""
        return {
            "conversation_response": f"Disculpa, estoy experimentando dificultades técnicas. ¿Puedes reformular tu pregunta?",
            "recommendations": [],
            "intent_analysis": {"type": "general", "confidence": 0.3},
            "context_update": {},
            "metadata": {
                "primary_ai": "fallback",
                "error": True
            }
        }
    
    def _update_metrics(self, ai_type: str, latency: float):
        """Actualizar métricas de rendimiento"""
        self.metrics[f"{ai_type}_calls"] += 1
        
        # Calcular latencia promedio
        total_calls = self.metrics["claude_calls"] + self.metrics["perplexity_calls"]
        if total_calls > 0:
            self.metrics["avg_latency"] = (
                (self.metrics["avg_latency"] * (total_calls - 1) + latency) / total_calls
            )
    
    async def get_performance_metrics(self) -> Dict:
        """Obtener métricas de rendimiento"""
        return {
            **self.metrics,
            "validation_accuracy": (
                self.metrics["validation_matches"] / max(self.metrics["perplexity_calls"], 1)
            ) if self.metrics["perplexity_calls"] > 0 else None
        }
    
    async def cleanup(self):
        """Limpieza de recursos"""
        await self.http_client.aclose()

# Ejemplo de uso en el sistema principal
class MCPConversationHandler:
    """Handler principal para conversaciones MCP"""
    
    def __init__(self, ai_manager: ConversationAIManager, recommender):
        self.ai_manager = ai_manager
        self.recommender = recommender
    
    async def handle_mcp_conversation(
        self, 
        user_message: str,
        session_context: Dict
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