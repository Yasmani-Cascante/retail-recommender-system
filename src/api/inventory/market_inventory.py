# src/api/inventory/market_inventory.py
"""
Market Inventory Manager - Gestión de Inventario por Mercado
==========================================================

Gestor especializado para manejar inventario específico por mercado,
incluyendo reglas de negocio, restricciones regionales y configuraciones
específicas por país/región.

Author: Technical Team
Version: 1.0.0
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import json
from datetime import datetime, timedelta

from .inventory_service import InventoryService, InventoryInfo, InventoryStatus
from .availability_checker import AvailabilityChecker

logger = logging.getLogger(__name__)

class MarketAvailabilityRule(str, Enum):
    """Reglas de disponibilidad por mercado"""
    GLOBAL_AVAILABLE = "global_available"      # Disponible en todos los mercados
    MARKET_RESTRICTED = "market_restricted"    # Restringido a mercados específicos
    REGION_BLOCKED = "region_blocked"          # Bloqueado en ciertas regiones
    CUSTOM_RULE = "custom_rule"               # Regla personalizada
    
class MarketTier(str, Enum):
    """Tiers de mercado para diferentes tratamientos"""
    TIER_1 = "tier_1"  # Mercados principales (US, EU)
    TIER_2 = "tier_2"  # Mercados secundarios (MX, CA)
    TIER_3 = "tier_3"  # Mercados emergentes
    
@dataclass
class MarketInventoryConfig:
    """Configuración de inventario específica por mercado"""
    market_id: str
    tier: MarketTier
    currency: str
    default_availability: bool
    low_stock_threshold: int
    out_of_stock_threshold: int
    enable_backorders: bool
    shipping_restrictions: List[str]
    availability_rules: Dict[str, Any]
    priority_level: int = 1
    last_updated: float = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = time.time()

@dataclass
class MarketInventoryStatus:
    """Estado de inventario específico para un mercado"""
    product_id: str
    market_id: str
    is_available: bool
    availability_rule: MarketAvailabilityRule
    stock_level: int
    reserved_stock: int
    available_stock: int
    market_restrictions: List[str]
    estimated_delivery_days: Optional[int]
    supplier_availability: Dict[str, bool]
    last_updated: float
    
class MarketInventoryManager:
    """
    Gestor de inventario específico por mercado que maneja reglas de negocio,
    restricciones regionales y configuraciones específicas.
    """
    
    def __init__(self, inventory_service: InventoryService):
        self.inventory_service = inventory_service
        self.availability_checker = AvailabilityChecker(inventory_service)
        
        # Configuraciones por mercado
        self.market_configs = self._initialize_market_configs()
        
        # Cache para reglas de mercado
        self.market_rules_cache = {}
        self.cache_ttl = 3600  # 1 hora
        
        logger.info("🌍 MarketInventoryManager initialized")
    
    def _initialize_market_configs(self) -> Dict[str, MarketInventoryConfig]:
        """Inicializar configuraciones por mercado"""
        
        configs = {
            "US": MarketInventoryConfig(
                market_id="US",
                tier=MarketTier.TIER_1,
                currency="USD",
                default_availability=True,
                low_stock_threshold=10,
                out_of_stock_threshold=0,
                enable_backorders=True,
                shipping_restrictions=[],
                availability_rules={
                    "allow_preorders": True,
                    "show_out_of_stock": True,
                    "enable_waitlist": True
                },
                priority_level=1
            ),
            
            "ES": MarketInventoryConfig(
                market_id="ES",
                tier=MarketTier.TIER_1,
                currency="EUR",
                default_availability=True,
                low_stock_threshold=5,
                out_of_stock_threshold=0,
                enable_backorders=True,
                shipping_restrictions=["dangerous_goods"],
                availability_rules={
                    "allow_preorders": True,
                    "show_out_of_stock": True,
                    "enable_waitlist": True,
                    "eu_compliance_required": True
                },
                priority_level=1
            ),
            
            "MX": MarketInventoryConfig(
                market_id="MX",
                tier=MarketTier.TIER_2,
                currency="MXN",
                default_availability=True,
                low_stock_threshold=8,
                out_of_stock_threshold=0,
                enable_backorders=False,
                shipping_restrictions=["electronics", "food_items"],
                availability_rules={
                    "allow_preorders": False,
                    "show_out_of_stock": False,
                    "enable_waitlist": False,
                    "local_fulfillment_only": True
                },
                priority_level=2
            ),
            
            "CA": MarketInventoryConfig(
                market_id="CA",
                tier=MarketTier.TIER_1,
                currency="CAD",
                default_availability=True,
                low_stock_threshold=8,
                out_of_stock_threshold=0,
                enable_backorders=True,
                shipping_restrictions=["controlled_substances"],
                availability_rules={
                    "allow_preorders": True,
                    "show_out_of_stock": True,
                    "enable_waitlist": True,
                    "bilingual_required": True
                },
                priority_level=1
            ),
            
            "DEFAULT": MarketInventoryConfig(
                market_id="DEFAULT",
                tier=MarketTier.TIER_3,
                currency="USD",
                default_availability=True,
                low_stock_threshold=5,
                out_of_stock_threshold=0,
                enable_backorders=False,
                shipping_restrictions=["all_restricted"],
                availability_rules={
                    "allow_preorders": False,
                    "show_out_of_stock": False,
                    "enable_waitlist": False
                },
                priority_level=3
            )
        }
        
        return configs
    
    async def check_market_availability(
        self,
        product_id: str,
        market_id: str,
        include_restrictions: bool = True
    ) -> MarketInventoryStatus:
        """
        Verificar disponibilidad específica para un mercado con reglas de negocio.
        
        Args:
            product_id: ID del producto
            market_id: Mercado a verificar  
            include_restrictions: Si incluir verificación de restricciones
            
        Returns:
            Estado completo de inventario para el mercado
        """
        try:
            # 1. Obtener configuración del mercado
            market_config = self.get_market_config(market_id)
            
            # 2. Obtener información base de inventario
            inventory_info = await self.inventory_service.check_product_availability(
                product_id, market_id
            )
            
            # 3. Aplicar reglas específicas del mercado
            market_status = await self._apply_market_rules(
                product_id, market_id, inventory_info, market_config, include_restrictions
            )
            
            logger.debug(f"Market availability for {product_id} in {market_id}: {market_status.is_available}")
            return market_status
            
        except Exception as e:
            logger.error(f"Error checking market availability for {product_id} in {market_id}: {e}")
            # Fallback con configuración segura
            return await self._create_fallback_market_status(product_id, market_id)
    
    async def check_multiple_markets_availability(
        self,
        product_id: str,
        market_ids: List[str],
        include_restrictions: bool = True
    ) -> Dict[str, MarketInventoryStatus]:
        """
        Verificar disponibilidad en múltiples mercados para un producto.
        
        Args:
            product_id: ID del producto
            market_ids: Lista de mercados a verificar
            include_restrictions: Si incluir verificación de restricciones
            
        Returns:
            Estado de disponibilidad por mercado
        """
        try:
            # Ejecutar verificaciones en paralelo
            tasks = [
                self.check_market_availability(product_id, market_id, include_restrictions)
                for market_id in market_ids
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Procesar resultados
            market_statuses = {}
            for i, result in enumerate(results):
                market_id = market_ids[i]
                
                if isinstance(result, Exception):
                    logger.warning(f"Error checking {product_id} in {market_id}: {result}")
                    market_statuses[market_id] = await self._create_fallback_market_status(product_id, market_id)
                else:
                    market_statuses[market_id] = result
            
            return market_statuses
            
        except Exception as e:
            logger.error(f"Error in multi-market availability check: {e}")
            # Fallback para todos los mercados
            return {
                market_id: await self._create_fallback_market_status(product_id, market_id)
                for market_id in market_ids
            }
    
    async def filter_products_by_market_availability(
        self,
        products: List[Dict],
        market_id: str,
        availability_rule: Optional[MarketAvailabilityRule] = None
    ) -> List[Dict]:
        """
        Filtrar productos basado en disponibilidad específica del mercado.
        
        Args:
            products: Lista de productos a filtrar
            market_id: Mercado para filtrar
            availability_rule: Regla específica a aplicar
            
        Returns:
            Lista filtrada de productos disponibles en el mercado
        """
        try:
            # Extraer IDs de productos
            product_ids = [
                product.get("id") or product.get("product_id")
                for product in products
                if product.get("id") or product.get("product_id")
            ]
            
            if not product_ids:
                return products
            
            # Verificar disponibilidad por mercado para cada producto
            filtered_products = []
            
            for product in products:
                product_id = product.get("id") or product.get("product_id")
                
                if not product_id:
                    continue
                
                try:
                    market_status = await self.check_market_availability(product_id, market_id)
                    
                    # Aplicar filtros según disponibilidad y reglas
                    if self._should_include_product(market_status, availability_rule):
                        # Enriquecer producto con información de mercado
                        enriched_product = await self._enrich_product_with_market_info(
                            product, market_status
                        )
                        filtered_products.append(enriched_product)
                        
                except Exception as e:
                    logger.warning(f"Error filtering product {product_id}: {e}")
                    # En caso de error, incluir producto con fallback optimista
                    filtered_products.append(product)
            
            logger.info(f"Filtered {len(filtered_products)}/{len(products)} products for market {market_id}")
            return filtered_products
            
        except Exception as e:
            logger.error(f"Error in market filtering: {e}")
            # Retornar productos originales si falla el filtrado
            return products
    
    def get_market_config(self, market_id: str) -> MarketInventoryConfig:
        """Obtener configuración para un mercado específico"""
        return self.market_configs.get(market_id, self.market_configs["DEFAULT"])
    
    def get_supported_markets(self) -> List[str]:
        """Obtener lista de mercados soportados"""
        return [market_id for market_id in self.market_configs.keys() if market_id != "DEFAULT"]
    
    def get_market_priority_order(self) -> List[str]:
        """Obtener mercados ordenados por prioridad"""
        markets_with_priority = [
            (market_id, config.priority_level)
            for market_id, config in self.market_configs.items()
            if market_id != "DEFAULT"
        ]
        
        # Ordenar por prioridad (menor número = mayor prioridad)
        sorted_markets = sorted(markets_with_priority, key=lambda x: x[1])
        return [market_id for market_id, _ in sorted_markets]
    
    async def _apply_market_rules(
        self,
        product_id: str,
        market_id: str,
        inventory_info: InventoryInfo,
        market_config: MarketInventoryConfig,
        include_restrictions: bool
    ) -> MarketInventoryStatus:
        """Aplicar reglas específicas del mercado al inventario"""
        
        # Determinar disponibilidad base
        base_availability = inventory_info.status in [
            InventoryStatus.AVAILABLE,
            InventoryStatus.LOW_STOCK
        ]
        
        # Aplicar reglas del mercado
        is_available = base_availability
        availability_rule = MarketAvailabilityRule.GLOBAL_AVAILABLE
        market_restrictions = []
        
        # 1. Verificar restricciones de shipping
        if include_restrictions:
            # Aquí se implementarían las verificaciones reales de restricciones
            # Por ahora, simulamos algunas restricciones básicas
            product_category = "general"  # En producción, esto vendría del producto
            
            if product_category in market_config.shipping_restrictions:
                market_restrictions.append(f"shipping_restricted_{product_category}")
                if market_config.tier == MarketTier.TIER_3:
                    is_available = False
                    availability_rule = MarketAvailabilityRule.REGION_BLOCKED
        
        # 2. Aplicar reglas específicas de disponibilidad
        if inventory_info.status == InventoryStatus.OUT_OF_STOCK:
            if not market_config.availability_rules.get("show_out_of_stock", True):
                is_available = False
                availability_rule = MarketAvailabilityRule.MARKET_RESTRICTED
        
        # 3. Verificar backorders
        if inventory_info.status == InventoryStatus.OUT_OF_STOCK and market_config.enable_backorders:
            is_available = True  # Permitir bajo backorder
            availability_rule = MarketAvailabilityRule.CUSTOM_RULE
            market_restrictions.append("backorder_only")
        
        # 4. Calcular días estimados de entrega
        estimated_delivery = self._calculate_estimated_delivery(market_config, inventory_info.status)
        
        # 5. Información de proveedores (simulada)
        supplier_availability = {
            "primary_supplier": is_available,
            "backup_supplier": inventory_info.status != InventoryStatus.DISCONTINUED
        }
        
        return MarketInventoryStatus(
            product_id=product_id,
            market_id=market_id,
            is_available=is_available,
            availability_rule=availability_rule,
            stock_level=inventory_info.quantity,
            reserved_stock=inventory_info.reserved_quantity,
            available_stock=inventory_info.available_quantity,
            market_restrictions=market_restrictions,
            estimated_delivery_days=estimated_delivery,
            supplier_availability=supplier_availability,
            last_updated=time.time()
        )
    
    def _calculate_estimated_delivery(self, market_config: MarketInventoryConfig, status: InventoryStatus) -> Optional[int]:
        """Calcular días estimados de entrega basado en mercado y estado"""
        
        base_delivery_days = {
            MarketTier.TIER_1: 2,  # 2 días para mercados principales
            MarketTier.TIER_2: 5,  # 5 días para mercados secundarios  
            MarketTier.TIER_3: 10  # 10 días para mercados emergentes
        }
        
        base_days = base_delivery_days.get(market_config.tier, 7)
        
        # Ajustar según estado de inventario
        if status == InventoryStatus.OUT_OF_STOCK:
            if market_config.enable_backorders:
                return base_days + 7  # 7 días adicionales para backorder
            else:
                return None  # No disponible para entrega
        elif status == InventoryStatus.LOW_STOCK:
            return base_days + 1  # 1 día adicional para stock bajo
        else:
            return base_days
    
    def _should_include_product(
        self,
        market_status: MarketInventoryStatus,
        availability_rule: Optional[MarketAvailabilityRule]
    ) -> bool:
        """Determinar si un producto debe incluirse según las reglas"""
        
        # Si no hay regla específica, usar disponibilidad base
        if not availability_rule:
            return market_status.is_available
        
        # Aplicar regla específica
        if availability_rule == MarketAvailabilityRule.GLOBAL_AVAILABLE:
            return market_status.is_available
        elif availability_rule == MarketAvailabilityRule.MARKET_RESTRICTED:
            return market_status.is_available and not market_status.market_restrictions
        elif availability_rule == MarketAvailabilityRule.REGION_BLOCKED:
            return False  # Nunca incluir productos bloqueados regionalmente
        elif availability_rule == MarketAvailabilityRule.CUSTOM_RULE:
            # Lógica personalizada
            return market_status.is_available
        
        return market_status.is_available
    
    async def _enrich_product_with_market_info(
        self,
        product: Dict,
        market_status: MarketInventoryStatus
    ) -> Dict:
        """Enriquecer producto con información específica del mercado"""
        
        enriched_product = product.copy()
        
        # Añadir información de mercado
        enriched_product.update({
            "market_availability": {
                market_status.market_id: market_status.is_available
            },
            "market_stock_level": market_status.available_stock,
            "market_restrictions": market_status.market_restrictions,
            "estimated_delivery_days": market_status.estimated_delivery_days,
            "availability_rule": market_status.availability_rule.value,
            "supplier_info": market_status.supplier_availability,
            "market_last_updated": market_status.last_updated
        })
        
        # Información adicional específica del mercado
        market_config = self.get_market_config(market_status.market_id)
        enriched_product.update({
            "market_tier": market_config.tier.value,
            "market_currency": market_config.currency,
            "backorder_enabled": market_config.enable_backorders
        })
        
        return enriched_product
    
    async def _create_fallback_market_status(
        self,
        product_id: str,
        market_id: str
    ) -> MarketInventoryStatus:
        """Crear estado de mercado de fallback optimista"""
        
        market_config = self.get_market_config(market_id)
        
        return MarketInventoryStatus(
            product_id=product_id,
            market_id=market_id,
            is_available=market_config.default_availability,
            availability_rule=MarketAvailabilityRule.GLOBAL_AVAILABLE,
            stock_level=15,  # Stock optimista
            reserved_stock=0,
            available_stock=15,
            market_restrictions=[],
            estimated_delivery_days=self._calculate_estimated_delivery(
                market_config, InventoryStatus.AVAILABLE
            ),
            supplier_availability={"fallback": True},
            last_updated=time.time()
        )
    
    async def get_market_inventory_summary(self, market_ids: List[str]) -> Dict[str, Any]:
        """Generar resumen de inventario por mercados"""
        
        summary = {
            "markets_analyzed": market_ids,
            "summary_by_market": {},
            "overall_stats": {
                "total_markets": len(market_ids),
                "tier_1_markets": 0,
                "tier_2_markets": 0,
                "tier_3_markets": 0
            },
            "generated_at": time.time()
        }
        
        for market_id in market_ids:
            market_config = self.get_market_config(market_id)
            
            summary["summary_by_market"][market_id] = {
                "tier": market_config.tier.value,
                "currency": market_config.currency,
                "default_availability": market_config.default_availability,
                "enables_backorders": market_config.enable_backorders,
                "restrictions_count": len(market_config.shipping_restrictions),
                "priority_level": market_config.priority_level
            }
            
            # Contar por tiers
            if market_config.tier == MarketTier.TIER_1:
                summary["overall_stats"]["tier_1_markets"] += 1
            elif market_config.tier == MarketTier.TIER_2:
                summary["overall_stats"]["tier_2_markets"] += 1
            else:
                summary["overall_stats"]["tier_3_markets"] += 1
        
        return summary

# Factory function
def create_market_inventory_manager(inventory_service: InventoryService) -> MarketInventoryManager:
    """Factory para crear MarketInventoryManager"""
    return MarketInventoryManager(inventory_service)
