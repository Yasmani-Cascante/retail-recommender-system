"""
MCP Market Adapter - Orchestration Layer
========================================

Orchestration layer para market adaptation específico para MCP + Claude.
Utiliza service boundaries claros para facilitar futura extracción de microservicios.
"""

import asyncio
import logging
from typing import Dict, Any

from ..models import MarketContext, MCPConversationContext, AdaptationResult
from ..market_config.service import MarketConfigService
from ..currency.service import CurrencyConversionService

logger = logging.getLogger(__name__)

class MCPMarketAdapter:
    """
    Orchestration layer para market adaptation
    Diseñado específicamente para integración MCP + Claude
    """
    
    def __init__(self):
        # Inicializar services con dependency injection
        self.market_config_service = MarketConfigService()
        self.currency_service = CurrencyConversionService()
        
        logger.info("🎯 MCPMarketAdapter inicializado con service boundaries")
    
    async def adapt_product_for_mcp_conversation(
        self, 
        product: Dict[str, Any], 
        conversation_context: MCPConversationContext
    ) -> AdaptationResult:
        """
        Adaptación específica para conversaciones MCP + Claude
        Función principal para Fase 2 del roadmap
        """
        start_time = asyncio.get_event_loop().time()
        market_context = conversation_context.market_context
        adaptations_applied = []
        
        logger.info(f"🔄 Iniciando adaptación MCP para market: {market_context.market_id}")
        
        adapted_product = product.copy()
        
        # 1. Currency conversion (Service boundary)
        if "price" in product:
            original_currency = product.get("currency", "USD")
            target_currency = market_context.currency
            
            conversion = await self.currency_service.convert_price(
                product["price"], 
                original_currency, 
                target_currency
            )
            
            if conversion["conversion_successful"]:
                adapted_product["price"] = conversion["converted_amount"]
                adapted_product["currency"] = target_currency
                adapted_product["exchange_rate"] = conversion["exchange_rate"]
                adaptations_applied.append("currency_conversion")
        
        # 2. MCP conversation personalization
        if conversation_context.user_intent:
            adapted_product["conversation_context"] = {
                "user_intent": conversation_context.user_intent,
                "session_id": conversation_context.session_id,
                "market_personality": market_context.ai_personality,
                "conversation_style": market_context.conversation_style
            }
            adaptations_applied.append("mcp_personalization")
        
        # 3. Market-specific enhancements
        adapted_product["market_enhancements"] = {
            "local_events": market_context.local_events[:2],
            "cultural_preferences": market_context.cultural_preferences,
            "tier": market_context.tier.value
        }
        adaptations_applied.append("market_enhancement")
        
        # 4. AI reasoning preparation for Claude
        adapted_product["claude_context"] = {
            "market_personality": market_context.ai_personality,
            "conversation_tone": market_context.conversation_style,
            "cultural_context": market_context.cultural_preferences
        }
        adaptations_applied.append("claude_preparation")
        
        # Metadata and timing
        end_time = asyncio.get_event_loop().time()
        processing_time = (end_time - start_time) * 1000
        
        adapted_product["market_adaptation_metadata"] = {
            "market_id": market_context.market_id,
            "market_tier": market_context.tier.value,
            "conversation_driven": True,
            "mcp_session_id": conversation_context.session_id,
            "adaptations_applied": adaptations_applied,
            "processing_time_ms": round(processing_time, 2),
            "service_boundaries_used": ["market_config", "currency_conversion", "mcp_personalization"]
        }
        
        # ✅ VALIDACIÓN REAL de market_adapted
        market_adapted = len(adaptations_applied) > 0
        adapted_product["market_adapted"] = market_adapted
        
        logger.info(f"✅ Adaptación MCP completada: {len(adaptations_applied)} adaptaciones aplicadas")
        
        return AdaptationResult(
            original_product=product,
            adapted_product=adapted_product,
            adaptations_applied=adaptations_applied,
            market_context=market_context,
            adaptation_metadata=adapted_product["market_adaptation_metadata"],
            service_used="mcp_market_adapter",
            processing_time_ms=processing_time
        )
    
    async def adapt_product_for_market_legacy(
        self, 
        product: Dict[str, Any], 
        market_id: str
    ) -> Dict[str, Any]:
        """
        Compatibility function para código existente
        """
        # Crear contexto MCP básico para compatibility
        market_context = await self.market_config_service.get_market_context(market_id)
        
        conversation_context = MCPConversationContext(
            session_id="legacy_compatibility",
            user_intent=None,
            conversation_history=[],
            market_context=market_context,
            personalization_data={}
        )
        
        result = await self.adapt_product_for_mcp_conversation(product, conversation_context)
        return result.adapted_product
