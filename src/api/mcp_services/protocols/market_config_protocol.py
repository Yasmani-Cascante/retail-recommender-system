"""Market Config Service Protocol"""

from typing import Protocol, Dict, Any
from ..models import MarketContext, MarketTier

class MarketConfigService(Protocol):
    """Protocol para Market Configuration Service (futuro microservicio)"""
    
    async def get_market_context(self, market_id: str) -> MarketContext:
        """Obtiene contexto completo del mercado"""
        ...
    
    async def get_market_tier(self, market_id: str) -> MarketTier:
        """Clasifica mercado por tier estratégico"""
        ...
    
    async def validate_market_availability(self, product_id: str, market_id: str) -> bool:
        """Valida disponibilidad de producto en mercado"""
        ...
