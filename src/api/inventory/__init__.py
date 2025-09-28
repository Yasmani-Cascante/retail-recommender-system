# src/api/inventory/__init__.py
"""
Inventory Management Module
==========================

Módulo para gestión de inventario y disponibilidad de productos
en diferentes mercados.
"""

from .inventory_service import InventoryService, InventoryStatus, InventoryInfo
from .availability_checker import AvailabilityChecker
from .market_inventory import (
    MarketInventoryManager, 
    MarketInventoryConfig,
    MarketInventoryStatus,
    MarketAvailabilityRule,
    MarketTier
)

__all__ = [
    'InventoryService',
    'InventoryStatus',
    'InventoryInfo',
    'AvailabilityChecker',
    'MarketInventoryManager',
    'MarketInventoryConfig',
    'MarketInventoryStatus', 
    'MarketAvailabilityRule',
    'MarketTier'
]
