"""
Diversity-Aware Cache - Solución al Problema de Cache Hit Rate 0%
================================================================

Cache inteligente que PRESERVA diversificación mientras OPTIMIZA performance.

Key Innovations:
1. Product-specific exclusion hashing
2. Turn-aware cache keys
3. Dynamic TTL based on conversation velocity
4. Semantic intent extraction (no over-normalization)

Author: Senior Architecture Team
Version: 2.0.0 - Diversity-Aware Strategy
Date: 2025-10-04
"""

import json
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CacheMetrics:
    """Métricas de performance del cache"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_response_time_hit_ms: float = 0.0
    avg_response_time_miss_ms: float = 0.0
    diversification_preserved_count: int = 0
    
    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.cache_hits / self.total_requests) * 100
    
    def to_dict(self) -> Dict:
        return {
            "total_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate_percentage": round(self.hit_rate, 2),
            "avg_response_time_hit_ms": round(self.avg_response_time_hit_ms, 2),
            "avg_response_time_miss_ms": round(self.avg_response_time_miss_ms, 2),
            "diversification_preserved": self.diversification_preserved_count
        }


class DiversityAwareCache:
    """
    Cache que preserva diversificación conversacional mientras optimiza performance.
    
    Estrategia Multi-Dimensional:
    - User ID: Personalización por usuario
    - Semantic Intent: Intención específica (no genérica)
    - Turn Number: Diferencia initial vs follow-up
    - Excluded Products Hash: Hash de IDs específicos de productos mostrados
    - Market ID: Localización del usuario
    
    TTL Strategy:
    - Initial recommendations: 300s (estable)
    - Follow-up requests: 60s (conversation velocity)
    - High-engagement users: 30s (dynamic preferences)
    """
    
    def __init__(
        self, 
        redis_service=None,
        default_ttl: int = 300,
        enable_metrics: bool = True,
        product_categories: Optional[Dict[str, List[str]]] = None,
        local_catalog: Optional[Any] = None
    ):
        self.redis = redis_service
        self.default_ttl = default_ttl
        self.cache_prefix = "diversity_cache_v2"
        self.enable_metrics = enable_metrics
        self.metrics = CacheMetrics()
        # Allow injecting real product categories or a local_catalog to derive them
        self.product_categories: Optional[Dict[str, List[str]]] = product_categories
        self.local_catalog: Optional[Any] = local_catalog
        
        logger.info(f"✅ DiversityAwareCache initialized - TTL: {default_ttl}s, Metrics: {enable_metrics}")
    
    def _extract_semantic_intent(self, query: str) -> str:
        """
        Extrae intención semántica ESPECÍFICA del query.
        
        A diferencia de normalización genérica, preserva contexto específico.
        """
        query_lower = query.lower().strip()
        
        # ✅ CRÍTICO: Detectar follow-up con contexto de productos
        follow_up_indicators = ['more', 'different', 'other', 'else', 'another', 'similar']
        if any(word in query_lower for word in follow_up_indicators):
            # Extract specific intent from follow-up
            if 'category' in query_lower or 'type' in query_lower:
                return "follow_up_category"
            elif 'price' in query_lower or 'cheaper' in query_lower or 'expensive' in query_lower:
                return "follow_up_price"
            elif 'brand' in query_lower:
                return "follow_up_brand"
            else:
                return "follow_up_general"
        
        # ✅ NUEVO: Extraer categoría de producto para initial requests
        # Prefer injected categories, then derive from local_catalog, then fallback to built-in heuristics
        product_categories = self.product_categories
        if not product_categories and self.local_catalog:
            product_categories = self._load_categories_from_catalog()

        if not product_categories:
            # Built-in fallback keywords (kept for backward compatibility)
            product_categories = {
                'electronics': ['phone', 'laptop', 'computer', 'tablet', 'headphone', 'speaker', 'electronic'],
                'sports': ['fitness', 'running', 'yoga', 'gym', 'sport', 'athletic', 'exercise', 'workout'],
                'fashion': ['shirt', 'pants', 'dress', 'jacket', 'clothing', 'apparel'],
                'home': ['furniture', 'decor', 'kitchen', 'bedroom', 'living'],
                'beauty': ['makeup', 'skincare', 'cosmetic', 'beauty', 'hair']
            }

        for category, keywords in product_categories.items():
            # keywords could be a set/list of strings
            for keyword in keywords:
                if keyword and keyword in query_lower:
                    return f"initial_{category}"
        
        # ✅ General recommendations pero con tipo específico
        if any(word in query_lower for word in ['recommend', 'show', 'suggest']):
            return "initial_general_recommendation"
        
        # Prioritize explicit help/assist requests before generic search verbs
        if any(word in query_lower for word in ['help', 'assist', 'info']):
            return "information_request"

        if any(word in query_lower for word in ['search', 'find', 'look']):
            return "search_query"
        
        # Fallback: usar primeras 3-4 palabras significativas
        words = [w for w in query_lower.split() if len(w) > 3][:4]
        return "_".join(words) if words else "general_query"
    
    def _hash_product_list(self, product_ids: List[str]) -> str:
        """
        Genera hash único para lista de productos excluidos.
        
        ✅ CRÍTICO: Usa IDs específicos, no solo count
        """
        if not product_ids:
            return "no_exclusions"
        
        # Sort para consistencia (mismo set de productos = mismo hash)
        sorted_ids = sorted(set(str(pid) for pid in product_ids))
        products_string = ",".join(sorted_ids)
        
        # Hash MD5 para identificación compacta
        hash_obj = hashlib.md5(products_string.encode())
        return hash_obj.hexdigest()[:12]  # Primeros 12 caracteres suficientes

    def _load_categories_from_catalog(self) -> Dict[str, List[str]]:
        """
        Construye un mapping category -> keywords a partir del catálogo local (lazy).
        Espera que local_catalog tenga product_data: List[Dict] con keys 'product_type'/'category' y 'title'.
        """
        categories: Dict[str, Set[str]] = {}
        try:
            catalog = self.local_catalog
            if not catalog:
                return {}
            # soportar objeto con atributo product_data o método para listar productos
            products = getattr(catalog, 'product_data', None)
            if products is None and hasattr(catalog, 'list_products'):
                products = catalog.list_products()
            if not products:
                return {}
            for p in products:
                # soportar distintos shapes de producto
                ptype = (p.get('product_type') or p.get('category') or '').strip().lower()
                title = (p.get('title') or '').lower()
                if not ptype:
                    continue
                kws = categories.setdefault(ptype, set())
                kws.add(ptype)
                # agregar palabras significativas del título como keywords
                for w in title.split():
                    clean = w.strip('.,()[]{}"\'')
                    if len(clean) > 3:
                        kws.add(clean)
            # convertir sets a listas
            return {k: list(v) for k, v in categories.items()}
        except Exception:
            return {}
    
    def _generate_diversity_aware_key(
        self,
        user_id: str,
        query: str,
        context: Dict[str, Any]
    ) -> str:
        """
        ✅ NUEVA ESTRATEGIA: Cache key que preserva diversificación
        
        Key Components:
        - user: Usuario específico
        - intent: Intención semántica específica
        - turn: Número de turn en conversación
        - excluded: Hash de productos específicos mostrados
        - market: Market ID
        
        Resultado: Keys diferentes para contexts diferentes, preservando diversidad
        """
        # Extract components
        semantic_intent = self._extract_semantic_intent(query)
        turn_number = context.get("turn_number", 1)
        shown_products = context.get("shown_products", [])
        excluded_hash = self._hash_product_list(shown_products)
        market_id = context.get("market_id", "US")
        
        # Build key components dict
        key_components = {
            "user": user_id,
            "intent": semantic_intent,
            "turn": turn_number,
            "excluded": excluded_hash,
            "market": market_id
        }
        
        # Generate composite key
        key_string = json.dumps(key_components, sort_keys=True)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()[:16]
        
        # Full key with prefix
        cache_key = f"{self.cache_prefix}:{user_id}:{key_hash}"
        
        logger.debug(f"🔑 Cache key generated: {cache_key}")
        logger.debug(f"    Components: intent={semantic_intent}, turn={turn_number}, excluded_count={len(shown_products)}")
        
        return cache_key
    
    def _calculate_dynamic_ttl(self, context: Dict[str, Any]) -> int:
        """
        ✅ TTL dinámico basado en conversation velocity y engagement
        
        Strategy:
        - Initial (turn 1): 300s (estable, probabilidad alta de reutilización)
        - Active conversation (turn 2-5): 60s (contexto cambia)
        - High engagement: 30s (preferencias dinámicas)
        """
        turn_number = context.get("turn_number", 1)
        engagement_score = context.get("engagement_score", 0.5)
        
        if turn_number == 1:
            # Primera interacción - TTL largo
            return 300
        elif engagement_score > 0.8:
            # Usuario muy engaged - preferencias pueden cambiar rápido
            return 30
        else:
            # Conversación activa - TTL medio
            return 60
    
    async def get_cached_response(
        self,
        user_id: str,
        query: str,
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Intenta obtener respuesta desde cache con diversidad preservada.
        
        Returns:
            Cached response o None si no hay hit válido
        """
        start_time = time.time()
        self.metrics.total_requests += 1
        
        try:
            # Generate diversity-aware cache key
            cache_key = self._generate_diversity_aware_key(user_id, query, context)
            
            # Try Redis lookup
            if not self.redis:
                logger.warning("⚠️ Redis not available - cache disabled")
                self.metrics.cache_misses += 1
                return None
            
            cached_data = await self._get_from_redis(cache_key)
            
            if cached_data:
                # Cache HIT
                elapsed_ms = (time.time() - start_time) * 1000
                self.metrics.cache_hits += 1
                self._update_hit_metrics(elapsed_ms)
                
                logger.info(f"✅ Cache HIT - key: {cache_key[:30]}... ({elapsed_ms:.0f}ms)")
                
                # Parse and return
                response = json.loads(cached_data)
                response["_cache_hit"] = True
                response["_cache_key"] = cache_key
                response["_response_time_ms"] = elapsed_ms
                
                return response
            else:
                # Cache MISS
                elapsed_ms = (time.time() - start_time) * 1000
                self.metrics.cache_misses += 1
                self._update_miss_metrics(elapsed_ms)
                
                logger.debug(f"❌ Cache MISS - key: {cache_key[:30]}... ({elapsed_ms:.0f}ms)")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error in cache lookup: {e}")
            self.metrics.cache_misses += 1
            return None
    
    async def cache_response(
        self,
        user_id: str,
        query: str,
        context: Dict[str, Any],
        response: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cachea respuesta con TTL dinámico y validación de diversidad.
        
        Args:
            user_id: ID de usuario
            query: Query original
            context: Contexto conversacional
            response: Respuesta a cachear
            ttl: TTL opcional (usa dynamic si no se especifica)
            
        Returns:
            True si cacheado exitosamente, False si error
        """
        try:
            # Generate cache key
            cache_key = self._generate_diversity_aware_key(user_id, query, context)
            
            # Calculate TTL
            final_ttl = ttl if ttl is not None else self._calculate_dynamic_ttl(context)
            
            # Prepare cache entry
            cache_entry = {
                "user_id": user_id,
                "query": query,
                "response": response,
                "context_snapshot": {
                    "turn_number": context.get("turn_number", 1),
                    "market_id": context.get("market_id", "US"),
                    "shown_products_count": len(context.get("shown_products", []))
                },
                "cached_at": time.time(),
                "expires_at": time.time() + final_ttl,
                "ttl": final_ttl
            }
            
            # Serialize and cache
            cache_data = json.dumps(cache_entry)
            success = await self._set_in_redis(cache_key, cache_data, final_ttl)
            
            if success:
                logger.info(f"✅ Cached response - key: {cache_key[:30]}... TTL: {final_ttl}s")
                return True
            else:
                logger.warning(f"⚠️ Failed to cache response")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error caching response: {e}")
            return False
    
    async def invalidate_user_cache(self, user_id: str) -> int:
        """
        Invalida todo el cache de un usuario específico.
        
        Útil cuando usuario cambia preferencias o perfil.
        """
        try:
            pattern = f"{self.cache_prefix}:{user_id}:*"
            deleted_count = await self._delete_by_pattern(pattern)
            
            logger.info(f"✅ Invalidated {deleted_count} cache entries for user {user_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"❌ Error invalidating user cache: {e}")
            return 0
    
    def get_metrics(self) -> Dict[str, Any]:
        """Retorna métricas actuales del cache"""
        return self.metrics.to_dict()
    
    def reset_metrics(self):
        """Reset métricas (útil para testing)"""
        self.metrics = CacheMetrics()
        logger.info("📊 Cache metrics reset")
    
    # ========== REDIS HELPER METHODS ==========
    
    async def _get_from_redis(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        try:
            if hasattr(self.redis, 'get'):
                return await self.redis.get(key)
            elif hasattr(self.redis, '_client'):
                return await self.redis._client.get(key)
            else:
                logger.error("❌ Redis client has no get method")
                return None
        except Exception as e:
            logger.error(f"❌ Redis GET error: {e}")
            return None
    
    async def _set_in_redis(self, key: str, value: str, ttl: int) -> bool:
        """Set value in Redis with TTL"""
        try:
            if hasattr(self.redis, 'setex'):
                await self.redis.setex(key, ttl, value)
                return True
            elif hasattr(self.redis, '_client'):
                await self.redis._client.setex(key, ttl, value)
                return True
            else:
                logger.error("❌ Redis client has no setex method")
                return False
        except Exception as e:
            logger.error(f"❌ Redis SET error: {e}")
            return False
    
    async def _delete_by_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern"""
        try:
            # Try delete_pattern method first
            if hasattr(self.redis, 'delete_pattern'):
                return await self.redis.delete_pattern(pattern)
            
            # Try direct keys + delete
            if hasattr(self.redis, 'keys') and hasattr(self.redis, 'delete'):
                keys = await self.redis.keys(pattern)
                if keys:
                    return await self.redis.delete(*keys)
                return 0
            
            # Try via _client attribute
            if hasattr(self.redis, '_client'):
                client = self.redis._client
                if hasattr(client, 'keys') and hasattr(client, 'delete'):
                    keys = await client.keys(pattern)
                    if keys:
                        return await client.delete(*keys)
                    return 0
            
            logger.warning("⚠️ Redis client doesn't support pattern deletion")
            return 0
            
        except Exception as e:
            logger.error(f"❌ Redis DELETE error: {e}")
            return 0
    
    # ========== METRICS HELPER METHODS ==========
    
    def _update_hit_metrics(self, elapsed_ms: float):
        """Update metrics for cache hit"""
        if not self.enable_metrics:
            return
        
        # Running average
        total_hits = self.metrics.cache_hits
        if total_hits == 1:
            self.metrics.avg_response_time_hit_ms = elapsed_ms
        else:
            current_avg = self.metrics.avg_response_time_hit_ms
            self.metrics.avg_response_time_hit_ms = (
                (current_avg * (total_hits - 1) + elapsed_ms) / total_hits
            )
    
    def _update_miss_metrics(self, elapsed_ms: float):
        """Update metrics for cache miss"""
        if not self.enable_metrics:
            return
        
        # Running average
        total_misses = self.metrics.cache_misses
        if total_misses == 1:
            self.metrics.avg_response_time_miss_ms = elapsed_ms
        else:
            current_avg = self.metrics.avg_response_time_miss_ms
            self.metrics.avg_response_time_miss_ms = (
                (current_avg * (total_misses - 1) + elapsed_ms) / total_misses
            )


# ========== FACTORY FUNCTION ==========

async def create_diversity_aware_cache(
    redis_service=None,
    default_ttl: int = 300,
    product_categories: Optional[Dict[str, List[str]]] = None,
    product_cache: Optional[Any] = None,
    local_catalog: Optional[Any] = None
) -> DiversityAwareCache:
    """
    Factory function para crear DiversityAwareCache
    
    Usage:
        from src.api.core.diversity_aware_cache import create_diversity_aware_cache
        
        cache = await create_diversity_aware_cache(
            redis_service=redis_service,
            default_ttl=300
        )
    """
    # prefer explicit local_catalog -> product_cache.local_catalog -> None
    lc = local_catalog
    if product_cache and getattr(product_cache, "local_catalog", None):
        lc = product_cache.local_catalog

    cache = DiversityAwareCache(
        redis_service=redis_service,
        default_ttl=default_ttl,
        enable_metrics=True,
        product_categories=product_categories,
        local_catalog=lc
    )
    
    logger.info("✅ DiversityAwareCache created successfully")
    return cache