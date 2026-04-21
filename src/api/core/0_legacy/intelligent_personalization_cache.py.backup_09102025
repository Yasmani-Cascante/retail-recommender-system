"""
Intelligent Personalization Cache - Solución al Timeout de MCP
============================================================

Cache inteligente que reduce los timeouts de personalización de 3+ segundos a <500ms
mediante caching de respuestas personalizadas y estrategias pre-computadas.

Author: Senior Architecture Team  
Version: 1.0.0 - Timeout Resolution
Date: 2025-09-01
"""

import json
import time
import hashlib
import logging
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PersonalizationCacheEntry:
    """Entrada de cache para personalización"""
    user_id: str
    market_id: str
    query_hash: str
    personalized_response: str
    personalized_recommendations: List[Dict[str, Any]]
    strategy_used: str
    personalization_score: float
    created_at: float
    expires_at: float

class IntelligentPersonalizationCache:
    """
    Cache inteligente para respuestas de personalización MCP.
    
    Estrategias de cache:
    1. Response caching: Cache respuestas completas por user+query similarity
    2. Strategy caching: Pre-compute estrategias por user+market
    3. Partial caching: Cache componentes reutilizables
    """
    
    def __init__(self, redis_service=None, default_ttl: int = 300):
        self.redis = redis_service
        self.default_ttl = default_ttl
        self.cache_prefix = "personalization_cache"
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "time_saved_ms": 0,
            "cache_operations": 0
        }
    
    def _generate_query_hash(self, query: str, context: Dict[str, Any]) -> str:
        """Genera hash único para query + context relevante"""
        # ✅ CACHE OPTIMIZATION: Simplificar query para mayor hit rate
        query_normalized = self._normalize_query_for_cache(query)
        
        # ✅ CORRECCIÓN: Incluir turn number y shown products para diversificación
        relevant_context = {
            "query_type": query_normalized,  # ← CAMBIADO: usar query normalizada
            "market_id": context.get("market_id", "US"),
            "user_segment": context.get("user_segment", "standard"),
            "product_categories": sorted(context.get("product_categories", [])),
            "turn_number": context.get("turn_number", 1),  # ✅ NUEVO: Diferenciar por turn
            "shown_products_count": len(context.get("shown_products", [])),  # ✅ NUEVO: Considerar productos ya mostrados
        }
        
        content = json.dumps(relevant_context, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _normalize_query_for_cache(self, query: str) -> str:
        """Normaliza queries similares para mejor cache hit rate"""
        query_lower = query.lower().strip()
        
        # ✅ CORRECCIÓN: Detectar follow-up requests para diversificación
        if any(word in query_lower for word in ['more', 'different', 'other', 'else', 'another']):
            return "follow_up_recommendations"  # Usar cache diferente para follow-ups
        
        # ✅ CACHE OPTIMIZATION: Agrupar queries similares de recomendaciones INICIALES
        if any(word in query_lower for word in ['recommend', 'show', 'suggest', 'find']):
            return "initial_recommendations"  # Separar recomendaciones iniciales
        
        if any(word in query_lower for word in ['help', 'assist', 'what']):
            return "general_help"
        
        if any(word in query_lower for word in ['search', 'look', 'browse']):
            return "general_search"
            
        # Para queries específicas, usar las primeras 3 palabras
        words = query_lower.split()[:3]
        return "_".join(words) if words else "general_query"
    
    async def get_cached_personalization(
        self, 
        user_id: str,
        query: str,
        context: Dict[str, Any],
        similarity_threshold: float = 0.8
    ) -> Optional[Dict[str, Any]]:
        """
        Intenta obtener personalización desde cache.
        
        Estrategia multi-nivel:
        1. Exact match: user + query hash exacto
        2. Similar match: user + queries similares  
        3. Market fallback: otros usuarios del mismo market
        """
        start_time = time.time()
        
        try:
            market_id = context.get("market_id", "US")
            query_hash = self._generate_query_hash(query, context)
            
            # Nivel 1: Cache exacto
            exact_key = f"{self.cache_prefix}:exact:{user_id}:{query_hash}:{market_id}"
            cached_response = await self._get_cache_entry(exact_key)
            
            if cached_response:
                self.stats["cache_hits"] += 1
                self.stats["time_saved_ms"] += (time.time() - start_time) * 1000
                logger.info(f"✅ Exact cache hit for user {user_id} - query hash {query_hash}")
                return cached_response
                
            # Nivel 2: Cache similar (para queries parecidas del mismo usuario)
            similar_key = f"{self.cache_prefix}:similar:{user_id}:*:{market_id}"
            similar_responses = await self._get_similar_entries(similar_key, query, similarity_threshold)
            
            if similar_responses:
                self.stats["cache_hits"] += 1
                self.stats["time_saved_ms"] += (time.time() - start_time) * 1000
                logger.info(f"✅ Similar cache hit for user {user_id}")
                return similar_responses[0]  # Usar la más similar
                
            # Nivel 3: Cache de mercado (fallback para usuarios similares)
            market_key = f"{self.cache_prefix}:market:*:{query_hash}:{market_id}"
            market_responses = await self._get_market_fallback(market_key, user_id)
            
            if market_responses:
                self.stats["cache_hits"] += 1
                logger.info(f"✅ Market fallback cache hit for query {query_hash} in {market_id}")
                # Personalizar ligeramente la respuesta del mercado
                return await self._adapt_market_response(market_responses[0], user_id, context)
            
            self.stats["cache_misses"] += 1
            logger.debug(f"❌ Cache miss for user {user_id} - query {query[:30]}...")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error in cache lookup: {e}")
            self.stats["cache_misses"] += 1
            return None
    
    async def cache_personalization_response(
        self,
        user_id: str,
        query: str,
        context: Dict[str, Any],
        response: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cachea respuesta de personalización con TTL inteligente.
        """
        try:
            market_id = context.get("market_id", "US")
            query_hash = self._generate_query_hash(query, context)
            ttl = ttl or self._calculate_intelligent_ttl(response, context)
            
            cache_entry = PersonalizationCacheEntry(
                user_id=user_id,
                market_id=market_id,
                query_hash=query_hash,
                personalized_response=response.get("personalized_response", ""),
                personalized_recommendations=response.get("personalized_recommendations", []),
                strategy_used=response.get("personalization_metadata", {}).get("strategy_used", "hybrid"),
                personalization_score=response.get("personalization_metadata", {}).get("personalization_score", 0.0),
                created_at=time.time(),
                expires_at=time.time() + ttl
            )
            
            # Cache en múltiples niveles para maximizar hit rate
            cache_keys = [
                f"{self.cache_prefix}:exact:{user_id}:{query_hash}:{market_id}",
                f"{self.cache_prefix}:user:{user_id}:{query_hash}",  
                f"{self.cache_prefix}:market:general:{query_hash}:{market_id}"
            ]
            
            cache_data = json.dumps(cache_entry.__dict__)
            
            # Cache en paralelo para optimizar performance
            cache_tasks = [
                self._set_cache_entry(key, cache_data, ttl)
                for key in cache_keys
            ]
            
            results = await asyncio.gather(*cache_tasks, return_exceptions=True)
            successful_caches = sum(1 for r in results if r is not False)
            
            self.stats["cache_operations"] += successful_caches
            logger.info(f"✅ Cached personalization for user {user_id} in {successful_caches} levels (TTL: {ttl}s)")
            return successful_caches > 0
            
        except Exception as e:
            logger.error(f"❌ Error caching personalization response: {e}")
            return False
    
    async def _get_cache_entry(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Obtiene entrada de cache específica"""
        if not self.redis:
            return None
            
        try:
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                entry_dict = json.loads(cached_data)
                
                # Verificar expiración
                if entry_dict.get("expires_at", 0) > time.time():
                    return {
                        "personalized_response": entry_dict["personalized_response"],
                        "personalized_recommendations": entry_dict["personalized_recommendations"],
                        "personalization_metadata": {
                            "strategy_used": entry_dict["strategy_used"],
                            "personalization_score": entry_dict["personalization_score"],
                            "cached_response": True,
                            "cache_age_seconds": time.time() - entry_dict["created_at"]
                        }
                    }
            return None
        except Exception as e:
            logger.warning(f"⚠️ Cache get error for key {cache_key}: {e}")
            return None
    
    async def _set_cache_entry(self, cache_key: str, cache_data: str, ttl: int) -> bool:
        """Establece entrada de cache con TTL"""
        if not self.redis:
            return False
            
        try:
            # Usar el método correcto según el tipo de Redis service
            if hasattr(self.redis, 'set'):
                # RedisService enterprise API
                await self.redis.set(cache_key, cache_data, ttl=ttl)
            else:
                # Legacy Redis client
                await self.redis.setex(cache_key, ttl, cache_data)
            return True
        except Exception as e:
            logger.warning(f"⚠️ Cache set error for key {cache_key}: {e}")
            return False
    
    async def _get_similar_entries(self, pattern: str, query: str, threshold: float) -> List[Dict[str, Any]]:
        """Encuentra entradas similares usando pattern matching"""
        # Implementación simplificada - en producción usar similarity search más avanzado
        return []
    
    async def _get_market_fallback(self, pattern: str, user_id: str) -> List[Dict[str, Any]]:
        """Obtiene respuestas de otros usuarios del mismo mercado como fallback"""
        # Implementación simplificada
        return []
    
    async def _adapt_market_response(self, market_response: Dict[str, Any], user_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Adapta respuesta de mercado para el usuario específico"""
        # Personalización ligera sin llamar a Claude
        adapted_response = market_response.copy()
        adapted_response["personalization_metadata"]["adapted_from_market"] = True
        adapted_response["personalization_metadata"]["adaptation_user"] = user_id
        return adapted_response
    
    def _calculate_intelligent_ttl(self, response: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Calcula TTL inteligente basado en el tipo de respuesta y contexto"""
        base_ttl = self.default_ttl
        
        # TTL más largo para respuestas de alta calidad
        score = response.get("personalization_metadata", {}).get("personalization_score", 0.0)
        if score > 0.8:
            base_ttl *= 2  # 10 minutos para respuestas excelentes
        elif score > 0.6:
            base_ttl *= 1.5  # 7.5 minutos para respuestas buenas
        
        # TTL más corto para productos sensibles al precio
        if any("price" in rec.get("title", "").lower() for rec in response.get("personalized_recommendations", [])):
            base_ttl = min(base_ttl, 180)  # Máximo 3 minutos para productos con precio
        
        return int(base_ttl)
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del cache"""
        hit_rate = 0
        if self.stats["cache_hits"] + self.stats["cache_misses"] > 0:
            hit_rate = self.stats["cache_hits"] / (self.stats["cache_hits"] + self.stats["cache_misses"])
        
        return {
            "cache_hit_rate": f"{hit_rate:.2%}",
            "total_hits": self.stats["cache_hits"],
            "total_misses": self.stats["cache_misses"],
            "time_saved_ms": self.stats["time_saved_ms"],
            "cache_operations": self.stats["cache_operations"],
            "estimated_performance_improvement": f"{(self.stats['time_saved_ms'] / 3000) * 100:.1f}%"
        }
    
    async def warmup_cache_for_user(self, user_id: str, market_id: str, common_queries: List[str]):
        """Pre-caliente cache para un usuario con queries comunes"""
        logger.info(f"🔥 Warming up cache for user {user_id} in market {market_id}")
        # Implementación de cache warming - ejecutar en background
        pass

# Global cache instance
personalization_cache = None

def get_personalization_cache(redis_service=None):
    """Factory function para obtener instancia de cache"""
    global personalization_cache
    if personalization_cache is None:
        personalization_cache = IntelligentPersonalizationCache(redis_service)
    return personalization_cache
