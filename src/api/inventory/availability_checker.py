# src/api/inventory/availability_checker.py
"""
Availability Checker - Verificador de Disponibilidad Rápida
==========================================================

Checker ligero y rápido para verificaciones de disponibilidad
en tiempo real durante conversaciones y recomendaciones.

Author: Technical Team
Version: 1.0.0
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any
import random

from .inventory_service import InventoryService, InventoryInfo, InventoryStatus

logger = logging.getLogger(__name__)

class AvailabilityChecker:
    """
    Checker rápido de disponibilidad optimizado para uso en tiempo real
    """
    
    def __init__(self, inventory_service: InventoryService):
        self.inventory_service = inventory_service
        self.quick_cache = {}  # Cache en memoria para checks rápidos
        self.cache_ttl = 60    # 1 minuto para cache rápido
        
        logger.info("⚡ AvailabilityChecker initialized")
    
    async def quick_availability_check(
        self, 
        product_id: str, 
        market_id: str = "US"
    ) -> bool:
        """
        Verificación rápida de disponibilidad (solo True/False).
        Optimizada para uso en tiempo real.
        
        Args:
            product_id: ID del producto
            market_id: Mercado a verificar
            
        Returns:
            True si está disponible, False si no
        """
        try:
            # 1. Check cache rápido en memoria
            cache_key = f"{product_id}:{market_id}"
            if cache_key in self.quick_cache:
                cached_result, cached_time = self.quick_cache[cache_key]
                if time.time() - cached_time < self.cache_ttl:
                    return cached_result
            
            # 2. Obtener información completa
            inventory_info = await self.inventory_service.check_product_availability(
                product_id, market_id
            )
            
            # 3. Determinar disponibilidad
            is_available = inventory_info.status in [
                InventoryStatus.AVAILABLE,
                InventoryStatus.LOW_STOCK
            ]
            
            # 4. Cachear resultado
            self.quick_cache[cache_key] = (is_available, time.time())
            
            # 5. Limpiar cache viejo
            await self._cleanup_quick_cache()
            
            return is_available
            
        except Exception as e:
            logger.warning(f"Error in quick availability check for {product_id}: {e}")
            # Fallback optimista
            return True
    
    async def bulk_availability_check(
        self,
        product_ids: List[str],
        market_id: str = "US"
    ) -> Dict[str, bool]:
        """
        Verificación rápida de disponibilidad para múltiples productos.
        
        Args:
            product_ids: Lista de IDs de productos
            market_id: Mercado a verificar
            
        Returns:
            Diccionario con disponibilidad por producto_id
        """
        try:
            # Ejecutar checks en paralelo
            tasks = [
                self.quick_availability_check(product_id, market_id)
                for product_id in product_ids
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Procesar resultados
            availability_map = {}
            for i, result in enumerate(results):
                product_id = product_ids[i]
                
                if isinstance(result, Exception):
                    logger.warning(f"Error checking availability for {product_id}: {result}")
                    availability_map[product_id] = True  # Fallback optimista
                else:
                    availability_map[product_id] = result
            
            logger.debug(f"Bulk availability check: {sum(availability_map.values())}/{len(product_ids)} available")
            return availability_map
            
        except Exception as e:
            logger.error(f"Error in bulk availability check: {e}")
            # Fallback optimista para todos
            return {product_id: True for product_id in product_ids}
    
    async def filter_available_products(
        self,
        products: List[Dict],
        market_id: str = "US",
        include_low_stock: bool = True
    ) -> List[Dict]:
        """
        Filtrar productos para incluir solo los disponibles.
        
        Args:
            products: Lista de productos a filtrar
            market_id: Mercado a verificar
            include_low_stock: Si incluir productos con stock bajo
            
        Returns:
            Lista filtrada de productos disponibles
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
            
            # Verificar disponibilidad
            availability_map = await self.bulk_availability_check(product_ids, market_id)
            
            # Filtrar productos disponibles
            available_products = []
            for product in products:
                product_id = product.get("id") or product.get("product_id")
                
                if product_id and availability_map.get(product_id, True):
                    available_products.append(product)
            
            logger.info(f"Filtered {len(available_products)}/{len(products)} available products")
            return available_products
            
        except Exception as e:
            logger.error(f"Error filtering available products: {e}")
            # Retornar todos los productos si falla el filtrado
            return products
    
    async def get_availability_summary_for_recommendations(
        self,
        recommendations: List[Dict],
        market_id: str = "US"
    ) -> Dict[str, Any]:
        """
        Generar resumen de disponibilidad para lista de recomendaciones.
        
        Args:
            recommendations: Lista de recomendaciones
            market_id: Mercado a analizar
            
        Returns:
            Resumen con estadísticas de disponibilidad
        """
        try:
            # Extraer productos de recomendaciones
            products = []
            for rec in recommendations:
                if isinstance(rec, dict):
                    # Podría ser recomendación con producto embebido
                    if "product" in rec:
                        products.append(rec["product"])
                    elif "id" in rec or "product_id" in rec:
                        products.append(rec)
            
            if not products:
                return {
                    "total_recommendations": len(recommendations),
                    "products_checked": 0,
                    "available_count": 0,
                    "availability_rate": 0.0,
                    "all_available": False
                }
            
            # Verificar disponibilidad
            product_ids = [
                product.get("id") or product.get("product_id")
                for product in products
                if product.get("id") or product.get("product_id")
            ]
            
            availability_map = await self.bulk_availability_check(product_ids, market_id)
            
            # Calcular estadísticas
            available_count = sum(availability_map.values())
            total_products = len(product_ids)
            
            summary = {
                "total_recommendations": len(recommendations),
                "products_checked": total_products,
                "available_count": available_count,
                "unavailable_count": total_products - available_count,
                "availability_rate": available_count / total_products if total_products > 0 else 0.0,
                "all_available": available_count == total_products,
                "market_id": market_id,
                "check_timestamp": time.time()
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating availability summary: {e}")
            return {
                "total_recommendations": len(recommendations),
                "products_checked": 0,
                "available_count": 0,
                "availability_rate": 0.0,
                "all_available": False,
                "error": str(e)
            }
    
    async def _cleanup_quick_cache(self):
        """Limpiar entradas viejas del cache rápido"""
        try:
            current_time = time.time()
            keys_to_remove = []
            
            for key, (_, cached_time) in self.quick_cache.items():
                if current_time - cached_time > self.cache_ttl:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self.quick_cache[key]
            
            if keys_to_remove:
                logger.debug(f"Cleaned {len(keys_to_remove)} old cache entries")
                
        except Exception as e:
            logger.warning(f"Error cleaning quick cache: {e}")
    
    def clear_cache(self):
        """Limpiar todo el cache rápido"""
        self.quick_cache.clear()
        logger.info("Quick cache cleared")

# Factory function
def create_availability_checker(inventory_service: InventoryService) -> AvailabilityChecker:
    """Factory para crear AvailabilityChecker"""
    return AvailabilityChecker(inventory_service)
