# src/cache/market_aware/market_cache.py
"""
Market-aware cache implementation para MCP integration.
Esta implementación proporciona caché segmentada por mercado.
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import datetime


if TYPE_CHECKING:
    from src.api.core.redis_service import RedisService
    from src.api.core.product_cache import ProductCache

# CORREGIDO: Importar y adaptar RedisCache para uso asíncrono
# try:
#     from src.api.core.cache import get_redis_client, AsyncRedisWrapper, get_async_redis_wrapper
# except ImportError as e:
#     logging.error(f"Error importando cache: {e}")
#     get_redis_client = None
#     AsyncRedisWrapper = None
#     get_async_redis_wrapper = None

logger = logging.getLogger(__name__)

class MarketAwareProductCache:
    """
    Sistema de caché que segmenta datos por mercado.
    Implementa estrategias específicas para multi-market commerce.
    """
    
    def __init__(
        self, 
        redis_service: 'RedisService',
        base_product_cache: Optional['ProductCache'] = None,
        default_ttl: int = 3600
    ):
        """
        Initialize Market-Aware Product Cache with Redis enterprise service.
        
        Args:
            redis_service: RedisService instance (from ServiceFactory).
                        Handles graceful degradation internally.
            base_product_cache: Optional ProductCache instance for fallback.
            default_ttl: Default TTL in seconds (default: 3600 = 1 hour)
        
        Architecture:
            - ALWAYS use ServiceFactory.get_market_cache_service() to obtain instances
            - RedisService manages connection, pooling, and graceful degradation internally
            - No fallback needed - service layer handles all error cases
            
        Author: Senior Architecture Team
        Version: 2.0.0 - Enterprise Migration
        Date: 2025-11-29
        """
        self.redis = redis_service
        self.base_product_cache = base_product_cache
        self.cache_prefix = "market_cache:"
        self.default_ttl = default_ttl
        
        self.stats = {
            "hits": 0,
            "misses": 0,
            "market_segments": set(),
            "total_requests": 0
        }
        
        logger.info(
            f"✅ MarketAwareProductCache initialized with RedisService (enterprise) | "
            f"Default TTL: {default_ttl}s"
        )
    
    async def get_product(self, product_id: str, market_id: str = "default") -> Optional[Dict]:
        """
        Obtener producto con contexto de mercado.
        
        Args:
            product_id: ID del producto
            market_id: ID del mercado
            
        Returns:
            Dict con datos del producto adaptados al mercado
        """
        self.stats["total_requests"] += 1
        self.stats["market_segments"].add(market_id)
        
        cache_key = f"{self.cache_prefix}{market_id}:product:{product_id}"
        
        try:
            # cached_data = await self.redis.get(cache_key)
            cached_data = await self.redis.get_json(cache_key)
            
            if cached_data:
                self.stats["hits"] += 1
                logger.debug(f"Cache hit para producto {product_id} en mercado {market_id}")
                return cached_data
            else:
                self.stats["misses"] += 1
                logger.debug(f"Cache miss para producto {product_id} en mercado {market_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error obteniendo producto del market cache: {e}")
            return None
    
    async def set_product(self, product_id: str, product_data: Dict, market_id: str = "default", ttl: Optional[int] = None) -> bool:
        """
        Guardar producto con contexto de mercado.
        
        Args:
            product_id: ID del producto
            product_data: Datos del producto
            market_id: ID del mercado
            ttl: Tiempo de vida en segundos
            
        Returns:
            bool: True si se guardó correctamente
        """
        cache_key = f"{self.cache_prefix}{market_id}:product:{product_id}"
        ttl = ttl or self.default_ttl
        
        try:
            # Agregar metadata de mercado
            enriched_data = {
                **product_data,
                "_market_cache_metadata": {
                    "market_id": market_id,
                    "cached_at": datetime.utcnow().isoformat(),
                    "ttl": ttl
                }
            }
            
            # success = await self.redis.set(cache_key, enriched_data, expiration=ttl)
            success = await self.redis.set_json(cache_key, enriched_data, ttl=ttl)
            if success:
                logger.debug(f"Producto {product_id} guardado en cache para mercado {market_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error guardando producto en market cache: {e}")
            return False
    
    async def invalidate_product(self, product_id: str, market_id: Optional[str] = None) -> int:
        """
        Invalidar producto en caché.
        
        Args:
            product_id: ID del producto
            market_id: ID del mercado (None para todos los mercados)
            
        Returns:
            int: Número de entradas invalidadas
        """
        if market_id:
            # Invalidar en mercado específico
            cache_key = f"{self.cache_prefix}{market_id}:product:{product_id}"
            success = await self.redis.delete(cache_key)
            return 1 if success else 0
        else:
            # Invalidar en todos los mercados
            # En implementación completa, usaríamos patrón de keys
            # Por ahora, simulamos invalidación en mercados conocidos
            markets = ["default", "US", "ES", "MX", "CL"]
            invalidated = 0
            
            for market in markets:
                cache_key = f"{self.cache_prefix}{market}:product:{product_id}"
                if await self.redis.delete(cache_key):
                    invalidated += 1
            
            logger.info(f"Producto {product_id} invalidado en {invalidated} mercados")
            return invalidated
    
    async def warm_cache_for_market(self, market_id: str, product_ids: List[str]) -> int:
        """
        Pre-cargar caché para un mercado específico.
        
        Args:
            market_id: ID del mercado
            product_ids: Lista de IDs de productos a pre-cargar
            
        Returns:
            int: Número de productos pre-cargados exitosamente
        """
        logger.info(f"Iniciando pre-carga de caché para mercado {market_id} con {len(product_ids)} productos")
        
        warmed_count = 0
        
        # En implementación completa, esto obtendría datos reales
        # Por ahora, creamos datos simulados para demostración
        for product_id in product_ids:
            mock_product = {
                "id": product_id,
                "title": f"Product {product_id}",
                "market_id": market_id,
                "warmup_data": True,
                "warmed_at": datetime.utcnow().isoformat()
            }
            
            if await self.set_product(product_id, mock_product, market_id):
                warmed_count += 1
        
        logger.info(f"Pre-carga completada: {warmed_count}/{len(product_ids)} productos cargados para mercado {market_id}")
        return warmed_count
    
    async def get_cache_stats(self, market_id: Optional[str] = None) -> Dict:
        """
        Obtener estadísticas del caché.
        
        Args:
            market_id: ID del mercado (None para estadísticas globales)
            
        Returns:
            Dict con estadísticas
        """
        stats = {
            "total_requests": self.stats["total_requests"],
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "hit_ratio": self.stats["hits"] / max(self.stats["total_requests"], 1),
            "market_segments": len(self.stats["market_segments"]),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if market_id:
            stats["market_id"] = market_id
            # En implementación completa, esto obtendría stats específicos del mercado
            stats["market_specific"] = True
        
        return stats
    
    async def invalidate_market(self, market_id: str, entity_type: Optional[str] = None) -> bool:
        """
        Invalidar caché completa de un mercado.
        
        Args:
            market_id: ID del mercado
            entity_type: Tipo de entidad (None para todas)
            
        Returns:
            bool: True si se invalidó correctamente
        """
        logger.info(f"Invalidando caché para mercado {market_id}, tipo: {entity_type or 'all'}")
        
        try:
            # En implementación completa, esto usaría Redis SCAN con patrón
            # Por ahora, simulamos la invalidación
            pattern = f"{self.cache_prefix}{market_id}:*"
            
            if entity_type:
                pattern = f"{self.cache_prefix}{market_id}:{entity_type}:*"
            
            logger.info(f"Simulando invalidación con patrón: {pattern}")
            
            # Remover mercado de stats
            if market_id in self.stats["market_segments"]:
                self.stats["market_segments"].discard(market_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error invalidando caché para mercado {market_id}: {e}")
            return False
    
    async def health_check(self) -> Dict:
        """
        Verificar estado del caché market-aware.
        
        Returns:
            Dict con estado del caché
        """
        status = {
            "status": "operational" if self.redis else "unavailable",
            "redis_connected": bool(self.redis),
            "market_segments_active": len(self.stats["market_segments"]),
            "total_requests_processed": self.stats["total_requests"],
            "cache_hit_ratio": self.stats["hits"] / max(self.stats["total_requests"], 1)
        }
        
        # Test básico de conectividad
        if self.redis:
            try:
                test_key = f"{self.cache_prefix}health_check"
                await self.redis.set(test_key, {"test": True}, expiration=60)
                test_result = await self.redis.get(test_key)
                status["test_write_read"] = test_result is not None
                await self.redis.delete(test_key)
            except Exception as e:
                status["test_write_read"] = False
                status["test_error"] = str(e)
        
        return status
