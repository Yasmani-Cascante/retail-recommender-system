"""
MCP Services Protocols
=====================

Protocols que definen los contratos para futuros microservicios.
Estos protocols facilitan la extracción de services independientes.
"""

from .market_config_protocol import MarketConfigService
from .currency_protocol import CurrencyConversionService  
from .localization_protocol import LocalizationService
from .mcp_personalization_protocol import MCPPersonalizationService

__all__ = [
    "MarketConfigService",
    "CurrencyConversionService", 
    "LocalizationService",
    "MCPPersonalizationService"
]
