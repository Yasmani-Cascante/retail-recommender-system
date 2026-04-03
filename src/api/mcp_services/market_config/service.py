"""
Market Configuration Service
===========================

Service para gestión de configuraciones de mercado.
Preparado para extracción como microservicio independiente.
"""

from typing import Dict, Any
from ..models import MarketContext, MarketTier

class MarketConfigService:
    """Market Configuration Service Implementation"""
    
    def __init__(self):
        # FIX v2.1.0 (27/03/2026): Añadido "CL" (Chile, CLP).
        # CL es el mercado primario de AI-Shoppings.
        self.market_configs = {
            "US": MarketContext(
                market_id="US",
                currency="USD", 
                language="en",
                tier=MarketTier.TIER_1,
                cultural_preferences={
                    "communication_style": "direct",
                    "color_preferences": ["navy", "gray", "white"]
                },
                regulatory_requirements={
                    "tax_display": "exclusive", 
                    "return_policy_days": 30
                },
                conversation_style="professional_friendly",
                ai_personality="helpful_expert",
                local_events=["black_friday", "cyber_monday"]
            ),
            "ES": MarketContext(
                market_id="ES",
                currency="EUR",
                language="es", 
                tier=MarketTier.TIER_2,
                cultural_preferences={
                    "communication_style": "warm_personal",
                    "color_preferences": ["mediterranean_blue", "terracotta"]
                },
                regulatory_requirements={
                    "tax_display": "inclusive",
                    "return_policy_days": 14,
                    "gdpr_compliance": True
                },
                conversation_style="conversational_warm",
                ai_personality="friendly_local", 
                local_events=["rebajas_enero", "rebajas_julio"]
            ),
            "MX": MarketContext(
                market_id="MX",
                currency="MXN",
                language="es",
                tier=MarketTier.TIER_3,
                cultural_preferences={
                    "communication_style": "enthusiastic_personal",
                    "color_preferences": ["bright_colors", "festive"]
                },
                regulatory_requirements={
                    "tax_display": "inclusive",
                    "return_policy_days": 7
                },
                conversation_style="enthusiastic_helpful",
                ai_personality="energetic_local",
                local_events=["dia_muertos", "cinco_mayo"]
            ),
            # FIX v2.1.0 (27/03/2026): Chile — mercado primario de AI-Shoppings
            "CL": MarketContext(
                market_id="CL",
                currency="CLP",
                language="es",
                tier=MarketTier.TIER_2,
                cultural_preferences={
                    "communication_style": "warm_personal",
                    "color_preferences": ["neutral", "classic"],
                },
                regulatory_requirements={
                    "tax_display": "inclusive",  # IVA incluido en CLP
                    "return_policy_days": 10,    # Ley del Consumidor de Chile
                },
                conversation_style="conversational_warm",
                ai_personality="friendly_local",
                local_events=["cyber_monday_cl", "navidad"]
            ),
        }

    async def get_market_context(self, market_id: str) -> MarketContext:
        """Service boundary: Market configuration lookup"""
        return self.market_configs.get(market_id, self.market_configs["US"])
    
    async def get_market_tier(self, market_id: str) -> MarketTier:
        """Service boundary: Market tier classification"""
        context = await self.get_market_context(market_id)
        return context.tier
    

    
    async def get_market_currency(self, market_id: str) -> str:
        """Service boundary: Obtiene la moneda del mercado"""
        context = await self.get_market_context(market_id)
        return context.currency
    
    async def get_market_language(self, market_id: str) -> str:
        """Service boundary: Obtiene el idioma del mercado"""
        context = await self.get_market_context(market_id)
        return context.language
    
    async def get_market_tier_name(self, market_id: str) -> str:
        """Service boundary: Obtiene el tier del mercado como string"""
        context = await self.get_market_context(market_id)
        return context.tier.value
    async def validate_market_availability(self, product_id: str, market_id: str) -> bool:
        """Service boundary: Product availability validation"""
        # TODO: Implementar lógica específica por tier
        return True
