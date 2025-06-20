# src/cache/market_aware/market_cache.py
import asyncio
import json
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from src.api.core.cache import get_redis_client
from src.api.mcp.models.mcp_models import (
    MarketID, CacheKey, MarketConfiguration, MarketProduct
)

logger = logging.getLogger(__name__)

class MarketAwareProductCache:
    """
    Sistema de caché avanzado segmentado por mercado con TTL diferenciado
    """
    
    def __init__(self):
        self.redis = get_redis_client()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "invalidations": 0
        }
        
        # TTL configurations por mercado y tipo de datos
        self.ttl_config = {
            MarketID.US: {
                "products": 3600,      # 1 hour - high volatility market
                "recommendations": 1800, # 30 minutes  
                "trending": 900,       # 15 minutes
                "availability": 300,   # 5 minutes
                "configuration": 86400  # 24 hours
            },
            MarketID.ES: {
                "products": 7200,      # 2 hours - more stable
                "recommendations": 3600, # 1 hour
                "trending": 1800,      # 30 minutes
                "availability": 600,   # 10 minutes
                "configuration": 86400
            },
            MarketID.MX: {
                "products": 5400,      # 1.5 hours
                "recommendations": 2700, # 45 minutes
                "trending": 1350,      # 22.5 minutes
                "availability": 450,   # 7.5 minutes
                "configuration": 86400
            },
            "default": {
                "products": 3600,
                "recommendations": 1800,
                "trending": 900,
                "availability": 300,
                "configuration": 86400
            }
        }
    
    async def get_market_product(self, product_id: str, market_id: str) -> Optional[MarketProduct]:
        """Obtener producto específico para mercado con fallback multi-level"""
        try:
            # Level 1: Market-specific cache
            cache_key = CacheKey(
                prefix="product",
                market_id=market_id,
                entity_id=product_id
            ).to_string()
            
            cached = await self.redis.get(cache_key)
            if cached:
                self._record_hit()
                data = json.loads(cached)
                return MarketProduct(**data)
            
            # Level 2: Global cache fallback
            global_key = f"product:global:{product_id}"
            cached_global = await self.redis.get(global_key)
            if cached_global:
                self._record_hit()
                data = json.loads(cached_global)
                # Adapt to market and cache
                adapted_product = await self._adapt_product_to_market(data, market_id)
                await self.set_market_product(product_id, market_id, adapted_product)
                return MarketProduct(**adapted_product)
                
            self._record_miss()
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving market product: {e}")
            self._record_miss()
            return None
    
    async def set_market_product(self, product_id: str, market_id: str, 
                                 product_data: Dict, ttl_override: Optional[int] = None):
        """Guardar producto en cache específico del mercado"""
        try:
            cache_key = CacheKey(
                prefix="product",
                market_id=market_id,
                entity_id=product_id
            ).to_string()
            
            # Get TTL for this market
            ttl = ttl_override or self._get_ttl(market_id, "products")
            
            # Store market-specific version
            await self.redis.setex(cache_key, ttl, json.dumps(product_data))
            
            # Also store in global cache with longer TTL for fallback
            global_key = f"product:global:{product_id}"
            await self.redis.setex(global_key, ttl * 2, json.dumps(product_data))
            
            self._record_set()
            logger.debug(f"Cached product {product_id} for market {market_id} with TTL {ttl}s")
            
        except Exception as e:
            logger.error(f"Error caching market product: {e}")
    
    async def get_market_recommendations(self, user_id: str, context_hash: str, 
                                         market_id: str) -> Optional[List[Dict]]:
        """Obtener recomendaciones cached para mercado específico"""
        try:
            cache_key = CacheKey(
                prefix="recs",
                market_id=market_id,
                entity_id=user_id,
                context_hash=context_hash
            ).to_string()
            
            cached = await self.redis.get(cache_key)
            if cached:
                self._record_hit()
                return json.loads(cached)
                
            self._record_miss()
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving market recommendations: {e}")
            self._record_miss()
            return None
    
    async def set_market_recommendations(self, user_id: str, context_hash: str,
                                         market_id: str, recommendations: List[Dict]):
        """Cache recomendaciones por mercado"""
        try:
            cache_key = CacheKey(
                prefix="recs",
                market_id=market_id,
                entity_id=user_id,
                context_hash=context_hash
            ).to_string()
            
            ttl = self._get_ttl(market_id, "recommendations")
            await self.redis.setex(cache_key, ttl, json.dumps(recommendations))
            
            self._record_set()
            logger.debug(f"Cached recommendations for user {user_id} in market {market_id}")
            
        except Exception as e:
            logger.error(f"Error caching market recommendations: {e}")
    
    async def warm_cache_for_market(self, market_id: str, priority_products: List[str]):
        """Pre-cargar cache para mercado específico con productos prioritarios"""
        logger.info(f"🔥 Warming cache for market {market_id} with {len(priority_products)} products")
        
        try:
            # Import here to avoid circular dependency
            from src.api.mcp.client.mcp_client import ShopifyMCPClient
            import os
            
            mcp_client = ShopifyMCPClient(os.getenv("SHOPIFY_SHOP_URL", ""))
            await mcp_client.initialize()
            
            # Process in batches to avoid overwhelming the API
            batch_size = 50
            successful_cached = 0
            
            for i in range(0, len(priority_products), batch_size):
                batch = priority_products[i:i+batch_size]
                
                try:
                    # Fetch market-specific product data
                    products_data = await mcp_client.get_market_products(
                        market_id=market_id,
                        product_ids=batch
                    )
                    
                    # Cache each product
                    for product in products_data:
                        await self.set_market_product(
                            product['id'], market_id, product
                        )
                        successful_cached += 1
                        
                    # Small delay between batches
                    await asyncio.sleep(0.1)
                    
                except Exception as batch_error:
                    logger.error(f"Error warming batch {i//batch_size + 1}: {batch_error}")
                    continue
                    
            logger.info(f"✅ Cache warming completed for market {market_id}. Cached {successful_cached} products.")
            
        except Exception as e:
            logger.error(f"❌ Error during cache warming for market {market_id}: {e}")
    
    async def invalidate_market(self, market_id: str, entity_type: Optional[str] = None):
        """Invalidar cache completo o específico de un mercado"""
        try:
            if entity_type:
                pattern = f"{entity_type}:{market_id}:*"
            else:
                pattern = f"*:{market_id}:*"
                
            keys = await self.redis.keys(pattern)
            
            if keys:
                await self.redis.delete(*keys)
                self.stats["invalidations"] += len(keys)
                logger.info(f"🗑️ Invalidated {len(keys)} cache keys for market {market_id}")
            else:
                logger.info(f"No cache keys found to invalidate for market {market_id}")
                
        except Exception as e:
            logger.error(f"Error invalidating market cache: {e}")
    
    async def invalidate_product(self, product_id: str, market_id: Optional[str] = None):
        """Invalidar cache de un producto específico"""
        try:
            if market_id:
                # Invalidate specific market
                pattern = f"product:{market_id}:{product_id}"
                keys = [pattern]
            else:
                # Invalidate across all markets
                pattern = f"product:*:{product_id}"
                keys = await self.redis.keys(pattern)
            
            if keys:
                await self.redis.delete(*keys)
                self.stats["invalidations"] += len(keys)
                logger.info(f"🗑️ Invalidated product {product_id} cache")
                
        except Exception as e:
            logger.error(f"Error invalidating product cache: {e}")
    
    async def get_cache_stats(self, market_id: Optional[str] = None) -> Dict[str, Any]:
        """Obtener estadísticas de cache por mercado o globales"""
        try:
            stats = {
                "global_stats": self.stats.copy(),
                "hit_ratio": self._calculate_hit_ratio(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if market_id:
                # Market-specific stats
                patterns = {
                    'products': f"product:{market_id}:*",
                    'recommendations': f"recs:{market_id}:*",
                    'trending': f"trending:{market_id}:*"
                }
                
                market_stats = {}
                for category, pattern in patterns.items():
                    keys = await self.redis.keys(pattern)
                    market_stats[f'{category}_count'] = len(keys)
                    
                    # Sample TTL for category
                    if keys:
                        sample_ttl = await self.redis.ttl(keys[0])
                        market_stats[f'{category}_avg_ttl'] = sample_ttl
                
                stats["market_stats"] = {market_id: market_stats}
            else:
                # All markets stats
                all_markets_stats = {}
                for market in [MarketID.US, MarketID.ES, MarketID.MX, "default"]:
                    market_stat = await self.get_cache_stats(market)
                    all_markets_stats[market] = market_stat.get("market_stats", {}).get(market, {})
                
                stats["all_markets"] = all_markets_stats
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check para el sistema de cache market-aware"""
        try:
            # Test Redis connectivity
            await self.redis.ping()
            
            # Get basic stats
            stats = await self.get_cache_stats()
            
            # Check if we have cached data
            total_keys = sum(
                len(await self.redis.keys(f"*:{market}:*")) 
                for market in [MarketID.US, MarketID.ES, MarketID.MX, "default"]
            )
            
            health_status = {
                "status": "healthy" if total_keys > 0 else "empty",
                "redis_connected": True,
                "total_cached_items": total_keys,
                "hit_ratio": stats["hit_ratio"],
                "cache_stats": stats["global_stats"]
            }
            
            return health_status
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "redis_connected": False,
                "error": str(e)
            }
    
    def _get_ttl(self, market_id: str, data_type: str) -> int:
        """Obtener TTL específico para mercado y tipo de dato"""
        market_config = self.ttl_config.get(market_id, self.ttl_config["default"])
        return market_config.get(data_type, 3600)
    
    async def _adapt_product_to_market(self, product_data: Dict, market_id: str) -> Dict:
        """Adaptar datos de producto para mercado específico"""
        try:
            # Load market configuration
            from src.api.mcp.adapters.market_manager import MarketContextManager
            market_manager = MarketContextManager()
            market_config = await market_manager.get_market_config(market_id)
            
            # Apply market-specific adaptations
            adapted = product_data.copy()
            
            # Currency conversion if needed
            if market_config.get("currency") != adapted.get("currency"):
                adapted["market_price"] = await self._convert_currency(
                    adapted.get("base_price", 0),
                    adapted.get("currency", "USD"),
                    market_config.get("currency", "USD")
                )
                adapted["currency"] = market_config.get("currency")
            
            # Add market metadata
            adapted["market_adapted"] = True
            adapted["market_id"] = market_id
            adapted["adapted_at"] = datetime.utcnow().isoformat()
            
            return adapted
            
        except Exception as e:
            logger.error(f"Error adapting product to market: {e}")
            return product_data
    
    async def _convert_currency(self, amount: float, from_currency: str, to_currency: str) -> float:
        """Simple currency conversion (implement with real rates)"""
        # This is a placeholder - implement with real currency conversion API
        conversion_rates = {
            ("USD", "EUR"): 0.85,
            ("USD", "MXN"): 18.0,
            ("EUR", "USD"): 1.18,
            ("EUR", "MXN"): 21.2,
            ("MXN", "USD"): 0.055,
            ("MXN", "EUR"): 0.047
        }
        
        if from_currency == to_currency:
            return amount
            
        rate = conversion_rates.get((from_currency, to_currency), 1.0)
        return round(amount * rate, 2)
    
    def _record_hit(self):
        """Registrar cache hit"""
        self.stats["hits"] += 1
    
    def _record_miss(self):
        """Registrar cache miss"""
        self.stats["misses"] += 1
    
    def _record_set(self):
        """Registrar cache set operation"""
        self.stats["sets"] += 1
    
    def _calculate_hit_ratio(self) -> float:
        """Calcular ratio de hits del cache"""
        total = self.stats["hits"] + self.stats["misses"]
        if total == 0:
            return 0.0
        return round(self.stats["hits"] / total, 4)
    
    def _generate_context_hash(self, context: Dict) -> str:
        """Generar hash único para contexto de recomendación"""
        # Sort keys for consistent hashing
        sorted_context = json.dumps(context, sort_keys=True)
        return hashlib.md5(sorted_context.encode()).hexdigest()[:16]