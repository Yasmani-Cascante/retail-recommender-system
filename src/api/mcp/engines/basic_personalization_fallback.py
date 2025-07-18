#!/usr/bin/env python3
"""
Basic Personalization Fallback
==============================

Fallback básico para cuando el personalization engine completo no está disponible.
"""

import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class BasicPersonalizationFallback:
    """Fallback básico para personalización cuando el engine completo falla"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.enabled = True
        self.fallback_strategies = ["basic", "simple", "rule_based"]
        
        logger.info("BasicPersonalizationFallback initialized")
    
    async def generate_personalized_response(
        self, 
        mcp_context=None,
        recommendations=None,
        strategy=None
    ) -> Dict[str, Any]:
        """Generar respuesta personalizada básica"""
        
        # Respuesta básica
        basic_response = {
            "personalized_response": {
                "response": "I'd be happy to help you find what you're looking for!"
            },
            "personalized_recommendations": recommendations[:5] if recommendations else [],
            "personalization_metadata": {
                "strategy_used": "basic_fallback",
                "personalization_score": 0.5,
                "confidence": 0.6,
                "fallback": True,
                "timestamp": time.time()
            },
            "conversation_enhancement": {
                "context_aware": False,
                "cultural_adaptation": False,
                "behavioral_learning": False
            }
        }
        
        return basic_response
    
    async def get_available_strategies(self) -> List[str]:
        """Obtener estrategias disponibles"""
        return self.fallback_strategies
    
    async def initialize(self):
        """Inicializar engine (no-op para fallback)"""
        logger.info("BasicPersonalizationFallback initialization complete")
        return True
    
    def get_personalization_metrics(self) -> Dict[str, Any]:
        """Obtener métricas básicas"""
        return {
            "engine_type": "basic_fallback",
            "strategies_available": len(self.fallback_strategies),
            "fallback_mode": True,
            "initialized": self.enabled
        }
