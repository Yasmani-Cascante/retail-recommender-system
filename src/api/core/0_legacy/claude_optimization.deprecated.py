"""
Claude API Optimization Module
=============================

Optimización directa de las llamadas a Claude API para reducir latencia
de 1.6s+ a <1s mediante prompts optimizados y configuraciones mejoradas.

Version: 1.0.0 - Claude API Speed Optimization  
Date: 2025-09-02
"""

import time
import logging
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ClaudeOptimizationConfig:
    """Configuración optimizada para llamadas Claude"""
    max_tokens: int = 300      # Reducido de 800-1000
    temperature: float = 0.3   # Reducido de 0.7-0.8 para respuestas más rápidas  
    timeout: float = 1.5       # Timeout agresivo
    use_fast_model: bool = True # Usar Haiku cuando sea posible

class ClaudePersonalizationOptimizer:
    """
    Optimizador específico para personalización Claude.
    
    Estrategias de optimización:
    1. Prompts más cortos y focalizados
    2. Modelo Haiku para casos simples
    3. Timeout agresivo con fallback
    4. Pre-computed context templates
    """
    
    def __init__(self, claude_client=None):
        self.claude = claude_client
        self.optimization_config = ClaudeOptimizationConfig()
        self.template_cache = {}
        self.stats = {
            "fast_calls": 0,
            "slow_calls": 0,
            "avg_response_time": 0.0,
            "timeout_fallbacks": 0
        }
    
    async def generate_optimized_personalization(
        self,
        user_context: Dict[str, Any],
        recommendations: List[Dict[str, Any]],
        query: str,
        market_id: str = "US"
    ) -> Dict[str, Any]:
        """
        Genera personalización optimizada con múltiples estrategias de speed.
        """
        start_time = time.time()
        
        try:
            # Estrategia 1: Determinar complejidad
            complexity_score = self._assess_complexity(user_context, recommendations, query)
            
            if complexity_score < 0.3:
                # Caso simple - usar template pre-computed
                result = await self._generate_template_response(
                    user_context, recommendations, query, market_id
                )
                self.stats["fast_calls"] += 1
                logger.info(f"⚡ Used template response ({(time.time() - start_time)*1000:.1f}ms)")
                
            elif complexity_score < 0.7:
                # Caso medio - usar Haiku con prompt corto
                result = await self._generate_haiku_response(
                    user_context, recommendations, query, market_id
                )
                self.stats["fast_calls"] += 1
                logger.info(f"🚀 Used Haiku model ({(time.time() - start_time)*1000:.1f}ms)")
                
            else:
                # Caso complejo - usar Sonnet con timeout agresivo
                result = await self._generate_sonnet_response_optimized(
                    user_context, recommendations, query, market_id
                )
                self.stats["slow_calls"] += 1
                logger.info(f"🧠 Used Sonnet optimized ({(time.time() - start_time)*1000:.1f}ms)")
                
            # Actualizar estadísticas
            response_time = (time.time() - start_time) * 1000
            self._update_stats(response_time)
            
            return result
            
        except asyncio.TimeoutError:
            logger.warning("⏰ Claude optimization timeout - using fast fallback")
            self.stats["timeout_fallbacks"] += 1
            return await self._generate_fast_fallback(recommendations, query, market_id)
            
        except Exception as e:
            logger.error(f"❌ Claude optimization error: {e}")
            return await self._generate_fast_fallback(recommendations, query, market_id)
    
    def _assess_complexity(
        self, 
        user_context: Dict[str, Any], 
        recommendations: List[Dict[str, Any]], 
        query: str
    ) -> float:
        """
        Evalúa la complejidad de la personalización requerida.
        
        Returns:
            float: 0.0 (simple) to 1.0 (complex)
        """
        complexity = 0.0
        
        # Factores de complejidad
        if len(query.split()) > 10:
            complexity += 0.2  # Query larga
            
        if len(recommendations) > 3:
            complexity += 0.2  # Muchas recomendaciones
            
        if len(user_context.get("conversation_history", [])) > 5:
            complexity += 0.3  # Historial largo
            
        if user_context.get("market_id", "US") != "US":
            complexity += 0.2  # Mercado no-US requiere más personalización
            
        if any("price" in rec.get("title", "").lower() for rec in recommendations):
            complexity += 0.1  # Productos con precio requieren más context
            
        return min(complexity, 1.0)
    
    async def _generate_template_response(
        self,
        user_context: Dict[str, Any],
        recommendations: List[Dict[str, Any]], 
        query: str,
        market_id: str
    ) -> Dict[str, Any]:
        """
        Genera respuesta usando templates pre-computed (más rápido).
        """
        # Template simple para casos comunes
        template_key = f"{market_id}_{len(recommendations)}_general"
        
        if template_key in self.template_cache:
            template = self.template_cache[template_key]
        else:
            template = self._create_response_template(market_id, len(recommendations))
            self.template_cache[template_key] = template
        
        # Personalizar template con datos específicos
        personalized_response = template.format(
            product_count=len(recommendations),
            first_product=recommendations[0].get("title", "product") if recommendations else "product",
            query_focus=query[:30] + "..." if len(query) > 30 else query
        )
        
        return {
            "personalized_response": personalized_response,
            "personalized_recommendations": recommendations,
            "personalization_metadata": {
                "strategy_used": "template_optimized",
                "personalization_score": 0.7,
                "optimization_method": "pre_computed_template",
                "processing_time_ms": (time.time() - time.time()) * 1000  # Will be updated by caller
            }
        }
    
    async def _generate_haiku_response(
        self,
        user_context: Dict[str, Any],
        recommendations: List[Dict[str, Any]],
        query: str,
        market_id: str
    ) -> Dict[str, Any]:
        """
        Genera respuesta usando Claude Haiku (modelo más rápido).
        """
        # Prompt ultra-corto para Haiku
        short_prompt = f"""
Query: {query[:50]}
Products: {[r.get('title', '')[:20] for r in recommendations[:2]]}
Market: {market_id}

Generate a brief, personalized recommendation (max 100 words):"""
        
        try:
            response = await asyncio.wait_for(
                self.claude.messages.create(
                    model="claude-3-haiku-20240307",  # Modelo más rápido
                    system="You are a helpful shopping assistant. Be concise and specific.",
                    messages=[{"role": "user", "content": short_prompt}],
                    max_tokens=200,  # Reducido
                    temperature=0.3   # Menos creatividad = más rápido
                ),
                timeout=1.0  # Timeout muy agresivo para Haiku
            )
            
            return {
                "personalized_response": response.content[0].text,
                "personalized_recommendations": recommendations,
                "personalization_metadata": {
                    "strategy_used": "haiku_optimized",
                    "personalization_score": 0.8,
                    "optimization_method": "fast_model_short_prompt",
                    "model_used": "claude-3-haiku-20240307"
                }
            }
            
        except asyncio.TimeoutError:
            logger.warning("Haiku timeout - using fallback")
            return await self._generate_fast_fallback(recommendations, query, market_id)
    
    async def _generate_sonnet_response_optimized(
        self,
        user_context: Dict[str, Any],
        recommendations: List[Dict[str, Any]],
        query: str,
        market_id: str
    ) -> Dict[str, Any]:
        """
        Genera respuesta usando Sonnet pero con prompt optimizado.
        """
        # Prompt optimizado para Sonnet (más corto que el original)
        optimized_prompt = f"""
User query: "{query}"
Market: {market_id}
Top recommendations: {[{'title': r.get('title', ''), 'price': r.get('price', 'N/A')} for r in recommendations[:3]]}

Provide a personalized response (max 150 words) explaining why these products match the user's needs."""
        
        try:
            response = await asyncio.wait_for(
                self.claude.messages.create(
                    model="claude-sonnet-4-20250514",
                    system="You are an expert product recommender. Be specific, concise, and helpful.",
                    messages=[{"role": "user", "content": optimized_prompt}],
                    max_tokens=300,  # Reducido de 800+
                    temperature=0.4   # Ligeramente reducido
                ),
                timeout=1.5  # Timeout muy agresivo
            )
            
            return {
                "personalized_response": response.content[0].text,
                "personalized_recommendations": recommendations,
                "personalization_metadata": {
                    "strategy_used": "sonnet_optimized",
                    "personalization_score": 0.9,
                    "optimization_method": "short_prompt_aggressive_timeout",
                    "model_used": "claude-sonnet-4-20250514"
                }
            }
            
        except asyncio.TimeoutError:
            logger.warning("Sonnet optimized timeout - using fallback")
            return await self._generate_fast_fallback(recommendations, query, market_id)
    
    async def _generate_fast_fallback(
        self,
        recommendations: List[Dict[str, Any]],
        query: str,
        market_id: str
    ) -> Dict[str, Any]:
        """
        Fallback ultra-rápido sin Claude API.
        """
        fallback_responses = {
            "US": "I found {count} great products for your search: '{query}'. These items are popular and well-reviewed.",
            "ES": "Encontré {count} productos excelentes para tu búsqueda: '{query}'. Estos artículos son populares y bien valorados.",
            "MX": "Encontré {count} productos increíbles para tu búsqueda: '{query}'. Estos artículos tienen excelentes reseñas."
        }
        
        template = fallback_responses.get(market_id, fallback_responses["US"])
        response = template.format(
            count=len(recommendations),
            query=query[:50] + "..." if len(query) > 50 else query
        )
        
        return {
            "personalized_response": response,
            "personalized_recommendations": recommendations,
            "personalization_metadata": {
                "strategy_used": "fast_fallback",
                "personalization_score": 0.5,
                "optimization_method": "no_claude_api_call",
                "fallback_reason": "timeout_or_error"
            }
        }
    
    def _create_response_template(self, market_id: str, product_count: int) -> str:
        """
        Crea templates pre-computados para respuestas comunes.
        """
        templates = {
            "US": "Perfect! I found {product_count} items that match your search for '{query_focus}'. The {first_product} looks especially promising based on your preferences.",
            "ES": "¡Perfecto! Encontré {product_count} artículos que coinciden con tu búsqueda de '{query_focus}'. El {first_product} se ve especialmente prometedor según tus preferencias.",
            "MX": "¡Excelente! Encontré {product_count} productos que coinciden con tu búsqueda de '{query_focus}'. El {first_product} parece especialmente adecuado para ti."
        }
        return templates.get(market_id, templates["US"])
    
    def _update_stats(self, response_time: float):
        """
        Actualiza estadísticas de performance.
        """
        if self.stats["avg_response_time"] == 0:
            self.stats["avg_response_time"] = response_time
        else:
            self.stats["avg_response_time"] = (
                self.stats["avg_response_time"] * 0.8 + response_time * 0.2
            )
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas de optimización.
        """
        total_calls = self.stats["fast_calls"] + self.stats["slow_calls"]
        fast_ratio = self.stats["fast_calls"] / total_calls if total_calls > 0 else 0
        
        return {
            "fast_call_ratio": f"{fast_ratio:.1%}",
            "avg_response_time_ms": f"{self.stats['avg_response_time']:.1f}",
            "total_calls": total_calls,
            "timeout_fallbacks": self.stats["timeout_fallbacks"],
            "performance_target": "<1000ms average"
        }

# Global optimizer instance  
claude_optimizer = None

def get_claude_optimizer(claude_client=None):
    """
    Factory function para obtener instancia del optimizador.
    """
    global claude_optimizer
    if claude_optimizer is None:
        claude_optimizer = ClaudePersonalizationOptimizer(claude_client)
    return claude_optimizer
