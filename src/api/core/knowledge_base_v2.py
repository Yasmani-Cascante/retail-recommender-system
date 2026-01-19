"""
Knowledge Base API v2 - Shopify CMS Integration
===============================================

Triple-layer cache architecture for Knowledge Base:
1. Redis Cache (hot, <1ms, 24h TTL)
2. PostgreSQL Buffer (warm, <10ms, 48h cache)
3. Shopify API (cold, 100-300ms, only if needed)

Backward compatible with knowledge_base.py (hardcoded fallback).

Author: Retail Recommender System Team
Date: 2026-01-11
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

import asyncpg

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.api.core.redis_service import RedisService

import json

from src.api.core.intent_types import InformationalSubIntent, KnowledgeBaseAnswer
from src.api.core.models.kb_models import (
    KBContent,
    KBAnswer,
    ContentFormat,
    kb_content_to_answer
)
from src.api.integrations.shopify_kb_client import ShopifyKBClient

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# SHOPIFY KNOWLEDGE BASE (v2)
# ══════════════════════════════════════════════════════════════════════════

class ShopifyKnowledgeBase:
    """
    Knowledge Base powered by Shopify CMS with triple-layer cache.
    
    Architecture:
    ------------
    ```
    User Request
         ↓
    Redis Cache (Layer 1: Hot, <1ms)
         ↓ Cache miss
    PostgreSQL Buffer (Layer 2: Warm, <10ms)
         ↓ Stale or miss
    Shopify API (Layer 3: Cold, 100-300ms)
         ↓ Update cache + buffer
    Return Answer
    ```
    
    Performance:
    -----------
    - Cache hit rate target: >95%
    - Average response time: <2ms (cache hit)
    - Shopify API calls: <0.01/sec (well below rate limit)
    
    Usage:
    ------
    ```python
    kb = ShopifyKnowledgeBase(
        db_pool=db_pool,
        redis_service=redis_service,
        shopify_client=shopify_client,
        cache_ttl_hours=24,
        buffer_max_age_hours=48
    )
    
    answer = await kb.get_answer(
        sub_intent=InformationalSubIntent.POLICY_RETURN,
        language="es",
        category="ZAPATOS"
    )
    
    if answer:
        print(answer.answer)  # Markdown content
    ```
    """
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis_service: 'RedisService',
        shopify_client: Optional[ShopifyKBClient] = None,
        cache_ttl_hours: int = 24,
        buffer_max_age_hours: int = 48,
        enable_fallback: bool = True
    ):
        """
        Initialize Shopify Knowledge Base.
        
        Args:
            db_pool: AsyncPG connection pool
            redis_service: RedisService client
            shopify_client: Shopify KB client (optional, for Layer 3)
            cache_ttl_hours: Redis cache TTL (hours)
            buffer_max_age_hours: PostgreSQL buffer staleness threshold (hours)
            enable_fallback: Enable fallback to hardcoded KB
        """
        self.db = db_pool
        self.redis = redis_service
        self.shopify = shopify_client
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self.buffer_max_age = timedelta(hours=buffer_max_age_hours)
        self.enable_fallback = enable_fallback
        
        # Fallback to hardcoded KB (backward compatibility)
        if enable_fallback:
            try:
                from src.api.core.knowledge_base import KnowledgeBase
                self.fallback_kb = KnowledgeBase()
                logger.info("Fallback KB (hardcoded) enabled")
            except ImportError:
                logger.warning("Could not import fallback KB (knowledge_base.py)")
                self.fallback_kb = None
        else:
            self.fallback_kb = None
        
        logger.info(
            f"ShopifyKnowledgeBase initialized: "
            f"cache_ttl={cache_ttl_hours}h, buffer_max_age={buffer_max_age_hours}h"
        )
    
    # ──────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────
    
    async def get_answer(
        self,
        sub_intent: InformationalSubIntent,
        language: str = "es",
        category: Optional[str] = None
    ) -> Optional[KnowledgeBaseAnswer]:
        """
        Get Knowledge Base answer with triple-layer cache.
        
        Fallback chain:
        1. Redis cache (fast, <1ms)
        2. PostgreSQL buffer (medium, <10ms)
        3. Shopify API (slow, 100-300ms)
        4. Hardcoded KB (last resort, if enabled)
        
        Args:
            sub_intent: Informational intent
            language: Language code (es, en, pt)
            category: Product category (ZAPATOS, VESTIDOS, etc)
            
        Returns:
            KnowledgeBaseAnswer or None
            
        Example:
            >>> answer = await kb.get_answer(
            >>>     sub_intent=InformationalSubIntent.POLICY_RETURN,
            >>>     language="es",
            >>>     category="ZAPATOS"
            >>> )
            >>> print(answer.answer)
        """
        sub_intent_str = sub_intent.value if hasattr(sub_intent, 'value') else str(sub_intent)
        
        logger.info(
            f"KB query: sub_intent={sub_intent_str}, "
            f"language={language}, category={category}"
        )
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 1: REDIS CACHE (Hot, <1ms)
        # ═══════════════════════════════════════════════════════════════════
        
        try:
            cached = await self._get_from_cache(sub_intent_str, language, category)
            if cached:
                logger.info(f"✅ Cache HIT (Redis): {sub_intent_str}/{language}/{category or 'general'}")
                return self._kb_answer_to_knowledge_base_answer(
                    cached, 
                    sub_intent=sub_intent_str,  # ✅ PASAR sub_intent
                    cache_hit=True
                )
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 2: POSTGRESQL BUFFER (Warm, <10ms)
        # ═══════════════════════════════════════════════════════════════════
        
        try:
            buffered = await self._get_from_buffer(sub_intent_str, language, category)
            
            if buffered:
                # Check if fresh (not stale)
                is_fresh = buffered.is_fresh(max_age_hours=self.buffer_max_age.total_seconds() / 3600)
                
                if is_fresh:
                    logger.info(
                        f"✅ Buffer HIT (PostgreSQL): {sub_intent_str}/{language}/{category or 'general'}"
                    )
                    
                    # Store in Redis for next time
                    kb_answer = kb_content_to_answer(buffered, cache_hit=False)
                    await self._store_in_cache(sub_intent_str, language, category, kb_answer)
                    
                    # return self._kb_answer_to_knowledge_base_answer(kb_answer, cache_hit=False)
                    return self._kb_answer_to_knowledge_base_answer(
                        kb_answer,
                        sub_intent=sub_intent_str,  # ✅ PASAR sub_intent
                        cache_hit=False
                    )
                else:
                    logger.warning(
                        f"⚠️ Buffer STALE (PostgreSQL): {sub_intent_str}/{language}/{category or 'general'} "
                        f"(age: {datetime.utcnow() - buffered.last_synced})"
                    )
                    # Continue to Layer 3 to refresh
        except Exception as e:
            logger.error(f"PostgreSQL buffer error: {e}", exc_info=True)
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 3: SHOPIFY API (Cold, 100-300ms) - Only if configured
        # ═══════════════════════════════════════════════════════════════════
        
        if self.shopify:
            try:
                logger.info(f"Fetching from Shopify API: {sub_intent_str}/{language}/{category or 'general'}")
                
                # TODO: Implement direct Shopify fetch
                # For now, trigger background sync and use stale buffer
                logger.warning("Direct Shopify fetch not implemented yet. Using stale buffer if available.")
                
                # Use stale buffer as last resort
                if buffered:
                    logger.info("Using STALE buffer (better than nothing)")
                    kb_answer = kb_content_to_answer(buffered, cache_hit=False)
                    # return self._kb_answer_to_knowledge_base_answer(kb_answer, cache_hit=False)
                    return self._kb_answer_to_knowledge_base_answer(
                            kb_answer,
                            sub_intent=sub_intent_str,  # ✅ PASAR sub_intent
                            cache_hit=False
                        )
                    
            except Exception as e:
                logger.error(f"Shopify API error: {e}", exc_info=True)
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 4: FALLBACK TO HARDCODED KB (Last resort)
        # ═══════════════════════════════════════════════════════════════════
        
        if self.enable_fallback and self.fallback_kb:
            logger.warning(
                f"⚠️ All layers failed. Falling back to hardcoded KB: "
                f"{sub_intent_str}/{language}/{category or 'general'}"
            )
            
            try:
                # Try to get from hardcoded KB
                # Note: This assumes knowledge_base.py has a compatible method
                fallback_answer = self.fallback_kb.get_answer(
                    sub_intent=sub_intent,
                    language=language,
                    category=category
                )
                
                if fallback_answer:
                    logger.info("✅ Fallback KB (hardcoded) returned answer")
                    return fallback_answer
                    
            except Exception as e:
                logger.error(f"Fallback KB error: {e}", exc_info=True)
        
        # ═══════════════════════════════════════════════════════════════════
        # NO ANSWER FOUND
        # ═══════════════════════════════════════════════════════════════════
        
        logger.warning(
            f"❌ No answer found for: {sub_intent_str}/{language}/{category or 'general'}"
        )
        return None
    
    # ──────────────────────────────────────────────────────────────────────
    # CACHE OPERATIONS (Layer 1: Redis)
    # ──────────────────────────────────────────────────────────────────────
    
    async def _get_from_cache(
        self,
        sub_intent: str,
        language: str,
        category: Optional[str]
    ) -> Optional[KBAnswer]:
        """Get KB answer from Redis cache."""
        cache_key = self._build_cache_key(sub_intent, language, category)
        
        try:
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                # Deserialize JSON
                data = json.loads(cached_data)
                return KBAnswer(**data)
             
            return None
            
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return None
    
    async def _store_in_cache(
        self,
        sub_intent: str,
        language: str,
        category: Optional[str],
        answer: KBAnswer
    ) -> None:
        """Store KB answer in Redis cache."""
        cache_key = self._build_cache_key(sub_intent, language, category)
        
        try:
            # Serialize to JSON
            data = answer.model_dump_json()
            
            # Store with TTL
            # await self.redis.set(
            #     key=cache_key,
            #     value=data,
            #     ttl=self.cache_ttl_seconds
            # )
            await self.redis.set(cache_key, data, self.cache_ttl_seconds)
            
            logger.debug(f"Stored in cache: {cache_key} (TTL={self.cache_ttl_seconds}s)")
            
        except Exception as e:
            logger.error(f"Error storing in cache: {e}")
    
    def _build_cache_key(
        self,
        sub_intent: str,
        language: str,
        category: Optional[str]
    ) -> str:
        """Build Redis cache key."""
        return f"kb:{sub_intent}:{language}:{category or 'general'}"
    
    # ──────────────────────────────────────────────────────────────────────
    # BUFFER OPERATIONS (Layer 2: PostgreSQL)
    # ──────────────────────────────────────────────────────────────────────
    
    async def _get_from_buffer(
        self,
        sub_intent: str,
        language: str,
        category: Optional[str]
    ) -> Optional[KBContent]:
        """Get KB content from PostgreSQL buffer."""
        query = """
        SELECT 
            id, sub_intent, language, category,
            content, content_html, title, meta_description,
            shopify_page_id, shopify_url, shopify_handle,
            last_synced, created_at, updated_at, cache_version,
            related_links, metadata
        FROM kb_contents
        WHERE 
            sub_intent = $1
            AND language = $2
            AND COALESCE(category, 'general') = $3
        """
        
        try:
            async with self.db.acquire() as conn:
                row = await conn.fetchrow(query, sub_intent, language, category or 'general')
            
            if row:
                # Convert to KBContent model
                return KBContent(
                    id=row['id'],
                    sub_intent=row['sub_intent'],
                    language=row['language'],
                    category=row['category'],
                    content=row['content'],
                    content_html=row['content_html'],
                    title=row['title'],
                    meta_description=row['meta_description'],
                    shopify_page_id=row['shopify_page_id'],
                    shopify_url=row['shopify_url'],
                    shopify_handle=row['shopify_handle'],
                    last_synced=row['last_synced'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    cache_version=row['cache_version'],
                    related_links=row['related_links'] or [],
                    metadata=row['metadata'] or {}
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting from buffer: {e}", exc_info=True)
            return None
    
    # ──────────────────────────────────────────────────────────────────────
    # CONVERSION HELPERS
    # ──────────────────────────────────────────────────────────────────────
    
    def _kb_answer_to_knowledge_base_answer(
    self,
    kb_answer: KBAnswer,
    sub_intent: str,  # ✅ NUEVO PARÁMETRO REQUERIDO
    cache_hit: bool = False
    ) -> KnowledgeBaseAnswer:
        """
        Convert KBAnswer (Shopify model) to KnowledgeBaseAnswer (system model).
        
        This maintains backward compatibility with the existing system.
        
        Args:
            kb_answer: KB answer from Shopify CMS
            sub_intent: The sub-intent value (policy_return, product_care, etc)
            cache_hit: Whether this was served from cache
            
        Returns:
            KnowledgeBaseAnswer compatible with system
        """
        from src.api.core.intent_types import InformationalSubIntent
        
        # ✅ Convert string to enum (with validation)
        try:
            sub_intent_enum = InformationalSubIntent(sub_intent)
        except ValueError:
            # Fallback to UNKNOWN if sub_intent is not in enum
            logger.warning(f"Unknown sub_intent '{sub_intent}', using UNKNOWN")
            sub_intent_enum = InformationalSubIntent.UNKNOWN
        
        # ✅ Convert related_links format if needed
        related_links_list = []
        if kb_answer.related_links:
            for link in kb_answer.related_links:
                if isinstance(link, dict):
                    # Already in correct format
                    related_links_list.append(link)
                elif hasattr(link, 'title') and hasattr(link, 'url'):
                    # Convert from KBAnswerLink model
                    related_links_list.append({
                        "title": link.title,
                        "url": link.url
                    })
        
        return KnowledgeBaseAnswer(
            answer=kb_answer.answer,
            sub_intent=sub_intent_enum,  # ✅ AGREGADO: Campo requerido
            sources=[],  # Default empty, can be populated later
            related_links=related_links_list if related_links_list else None
        )


# ══════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION
# ══════════════════════════════════════════════════════════════════════════

def create_shopify_knowledge_base(
    db_pool: asyncpg.Pool,
    redis_service: 'RedisService',
    shopify_client: Optional[ShopifyKBClient] = None,
    cache_ttl_hours: int = 24,
    buffer_max_age_hours: int = 48,
    enable_fallback: bool = True
) -> ShopifyKnowledgeBase:
    """
    Factory function to create ShopifyKnowledgeBase.
    
    Args:
        db_pool: AsyncPG connection pool
        redis_service: RedisService client
        shopify_client: Shopify KB client (optional)
        cache_ttl_hours: Redis cache TTL
        buffer_max_age_hours: PostgreSQL buffer staleness threshold
        enable_fallback: Enable fallback to hardcoded KB
        
    Returns:
        Configured ShopifyKnowledgeBase instance
        
    Example:
        >>> kb = create_shopify_knowledge_base(
        >>>     db_pool=db_pool,
        >>>     redis_service=redis_service,
        >>>     shopify_client=shopify_client
        >>> )
    """
    return ShopifyKnowledgeBase(
        db_pool=db_pool,
        redis_service=redis_service,
        shopify_client=shopify_client,
        cache_ttl_hours=cache_ttl_hours,
        buffer_max_age_hours=buffer_max_age_hours,
        enable_fallback=enable_fallback
    )
