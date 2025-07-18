#!/usr/bin/env python3
"""
Claude Fallback Manager - Maneja casos donde Claude API no está disponible
========================================================================

Este manager proporciona fallbacks cuando Claude API no tiene créditos.
"""

import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ClaudeFallbackManager:
    """Manager para manejar casos donde Claude API no está disponible"""
    
    def __init__(self):
        self.fallback_enabled = True
        self.fallback_responses = {
            "intent_analysis": {
                "type": "general",
                "confidence": 0.5,
                "attributes": [],
                "source": "fallback"
            },
            "conversation_response": "I'm here to help you find what you need. Could you tell me more about what you're looking for?",
            "recommendations": []
        }
    
    async def process_conversation_fallback(
        self, 
        user_message: str, 
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Procesar conversación usando fallback cuando Claude no está disponible"""
        
        logger.info(f"Using Claude fallback for: {user_message[:50]}...")
        
        # Análisis básico de intención usando keywords
        intent = self._analyze_intent_fallback(user_message)
        
        # Generar respuesta contextual
        response = self._generate_response_fallback(user_message, intent, context)
        
        return {
            "conversation_response": response,
            "intent_analysis": intent,
            "recommendations": [],
            "metadata": {
                "source": "claude_fallback",
                "timestamp": time.time(),
                "fallback_reason": "claude_api_unavailable"
            }
        }
    
    def _analyze_intent_fallback(self, user_message: str) -> Dict[str, Any]:
        """Análisis básico de intención usando keywords"""
        
        message_lower = user_message.lower()
        
        # Keywords para diferentes intenciones
        intent_keywords = {
            "search": ["busco", "quiero", "necesito", "looking for", "want", "need"],
            "recommendation": ["recomienda", "suggest", "recommend", "advice"],
            "purchase": ["comprar", "buy", "purchase", "price", "cost"],
            "comparison": ["compare", "difference", "vs", "versus", "mejor"],
            "help": ["help", "ayuda", "how", "como"]
        }
        
        # Detectar intención
        detected_intent = "general"
        confidence = 0.5
        
        for intent_type, keywords in intent_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                detected_intent = intent_type
                confidence = 0.7
                break
        
        return {
            "type": detected_intent,
            "confidence": confidence,
            "attributes": [],
            "source": "keyword_fallback"
        }
    
    def _generate_response_fallback(
        self, 
        user_message: str, 
        intent: Dict[str, Any], 
        context: Dict[str, Any] = None
    ) -> str:
        """Generar respuesta usando templates"""
        
        intent_type = intent.get("type", "general")
        
        responses = {
            "search": "I can help you find what you're looking for. Let me search our products for you.",
            "recommendation": "I'd be happy to recommend some products for you. What type of items are you interested in?",
            "purchase": "Great! I can help you with purchasing. What specific product would you like to buy?",
            "comparison": "I can help you compare different options. Which products would you like to compare?",
            "help": "I'm here to help! Feel free to ask me about products, recommendations, or anything else.",
            "general": "Hello! I'm here to help you find great products. What are you looking for today?"
        }
        
        return responses.get(intent_type, responses["general"])
    
    def is_claude_available(self) -> bool:
        """Check if Claude API is available (placeholder)"""
        # En un caso real, esto haría un test básico a Claude API
        return False  # Por ahora, asumimos que no está disponible
    
    def get_fallback_status(self) -> Dict[str, Any]:
        """Obtener status del fallback manager"""
        return {
            "fallback_enabled": self.fallback_enabled,
            "claude_available": self.is_claude_available(),
            "fallback_responses_count": len(self.fallback_responses),
            "timestamp": time.time()
        }

# Instance global
claude_fallback = ClaudeFallbackManager()
