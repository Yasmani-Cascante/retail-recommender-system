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
Version: H1 - Structured Logging Migration
"""

import structlog  # ✅ H1: Structured Logging Migration
from typing import Optional, List
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

logger = structlog.get_logger(__name__)  # ✅ H1: Structured Logging Migration


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
            self.fallback_kb = None
            try:
                from src.api.core.knowledge_base import get_knowledge_base
                self.fallback_kb = get_knowledge_base()
                # ✅ H1: Structured logging
                logger.info(
                    "fallback_kb_enabled",
                    method="get_knowledge_base",
                    kb_type="hardcoded"
                )
            except Exception:
                try:
                    from src.api.core.knowledge_base import SimpleKnowledgeBase
                    self.fallback_kb = SimpleKnowledgeBase()
                    # ✅ H1: Structured logging
                    logger.info(
                        "fallback_kb_enabled",
                        method="SimpleKnowledgeBase",
                        kb_type="hardcoded"
                    )
                except Exception as e:
                    # ✅ H1: Structured warning
                    logger.warning(
                        "fallback_kb_import_failed",
                        error=str(e),
                        module="knowledge_base.py"
                    )
                    self.fallback_kb = None
        else:
            self.fallback_kb = None
        
        # ✅ H1: Structured logging para inicialización
        logger.info(
            "shopify_knowledge_base_initialized",
            service="ShopifyKnowledgeBase",
            cache_ttl_hours=cache_ttl_hours,
            buffer_max_age_hours=buffer_max_age_hours,
            fallback_enabled=enable_fallback,
            shopify_client_configured=self.shopify is not None
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
        Get Knowledge Base answer with triple-layer cache and language fallback.
        
        Fallback chain:
        1. Redis cache (fast, <1ms)
        2. PostgreSQL buffer (medium, <10ms)
        3. Shopify API (slow, 100-300ms)
        4. Language fallback (try es → en if requested language not found)
        5. Hardcoded KB (last resort, if enabled)
        
        Args:
            sub_intent: Informational intent
            language: Language code (es, en, pt, fr, etc.)
            category: Product category (ZAPATOS, VESTIDOS, etc)
            
        Returns:
            KnowledgeBaseAnswer or None
            
        Example:
            >>> answer = await kb.get_answer(
            >>>     sub_intent=InformationalSubIntent.POLICY_RETURN,
            >>>     language="fr",  # Falls back to 'es' if 'fr' not found
            >>>     category="ZAPATOS"
            >>> )
            >>> print(answer.answer)
        """
        sub_intent_str = sub_intent.value if hasattr(sub_intent, 'value') else str(sub_intent)
        
        # Try with requested language first
        result = await self._get_answer_single_language(
            sub_intent_str, 
            language, 
            category
        )
        
        if result:
            return result
        
        # ═══════════════════════════════════════════════════════════════════
        # LANGUAGE FALLBACK: Try alternative languages
        # ═══════════════════════════════════════════════════════════════════
        
        # Define fallback language chain
        fallback_languages = []
        if language not in ['es', 'en']:
            # If requested language is not es/en, try es first, then en
            fallback_languages = ['es', 'en']
            # ✅ H1: Structured logging
            logger.info(
                "kb_language_fallback_triggered",
                requested_language=language,
                fallback_chain=fallback_languages,
                sub_intent=sub_intent_str,
                category=category
            )
        elif language == 'en':
            # If requested en, try es as fallback
            fallback_languages = ['es']
            # ✅ H1: Structured logging
            logger.info(
                "kb_language_fallback_triggered",
                requested_language=language,
                fallback_chain=fallback_languages,
                sub_intent=sub_intent_str,
                category=category
            )
        # Note: If language == 'es', no fallback (es is the default)
        
        # Try each fallback language
        for fallback_lang in fallback_languages:
            # ✅ H1: Structured logging
            logger.info(
                "kb_trying_fallback_language",
                requested_language=language,
                fallback_language=fallback_lang,
                sub_intent=sub_intent_str,
                category=category
            )
            
            result = await self._get_answer_single_language(
                sub_intent_str,
                fallback_lang,
                category
            )
            
            if result:
                # ✅ H1: Structured logging
                logger.info(
                    "kb_language_fallback_success",
                    requested_language=language,
                    fallback_language=fallback_lang,
                    sub_intent=sub_intent_str,
                    category=category
                )
                return result
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 4: FALLBACK TO HARDCODED KB (Last resort)
        # ═══════════════════════════════════════════════════════════════════
        
        if self.enable_fallback and self.fallback_kb:
            # ✅ H1: Structured warning
            logger.warning(
                "kb_fallback_to_hardcoded",
                sub_intent=sub_intent_str,
                language=language,
                category=category or 'general',
                reason="all_layers_failed"
            )
            
            try:
                # Try to get from hardcoded KB
                # Note: Only pass sub_intent (other params may not be supported)
                fallback_answer = self.fallback_kb.get_answer(
                    sub_intent=sub_intent
                )
                
                if fallback_answer:
                    # ✅ H1: Structured logging
                    logger.info(
                        "kb_hardcoded_success",
                        sub_intent=sub_intent_str,
                        kb_type="hardcoded"
                    )
                    return fallback_answer
                    
            except Exception as e:
                # ✅ H1: Structured error
                logger.error(
                    "kb_hardcoded_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True
                )
        
        # ═══════════════════════════════════════════════════════════════════
        # NO ANSWER FOUND
        # ═══════════════════════════════════════════════════════════════════
        
        # ✅ H1: Structured warning
        logger.warning(
            "kb_no_answer_found",
            sub_intent=sub_intent_str,
            language=language,
            category=category or 'general',
            fallbacks_tried=["redis", "postgresql", "shopify_api", "language_fallback", "hardcoded"] if self.enable_fallback else ["redis", "postgresql", "shopify_api", "language_fallback"]
        )
        return None
    
    # ──────────────────────────────────────────────────────────────────────
    # INTERNAL HELPER - Single Language Query
    # ──────────────────────────────────────────────────────────────────────
    
    async def _get_answer_single_language(
        self,
        sub_intent_str: str,
        language: str,
        category: Optional[str]
    ) -> Optional[KnowledgeBaseAnswer]:
        """
        Get answer for a specific language without fallback.
        
        This is an internal helper method used by get_answer() to try
        each language in the fallback chain.
        
        Args:
            sub_intent_str: Sub-intent as string
            language: Language code to try
            category: Product category
            
        Returns:
            KnowledgeBaseAnswer or None
        """
        
        # ✅ H1: Structured logging
        logger.info(
            "kb_query",
            sub_intent=sub_intent_str,
            language=language,
            category=category
        )
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 1: REDIS CACHE (Hot, <1ms)
        # ═══════════════════════════════════════════════════════════════════
        
        try:
            cached = await self._get_from_cache(sub_intent_str, language, category)
            if cached:
                # ✅ H1: Structured logging
                logger.info(
                    "kb_cache_hit",
                    layer="redis",
                    sub_intent=sub_intent_str,
                    language=language,
                    category=category or 'general',
                    response_time_ms="<1"
                )
                return self._kb_answer_to_knowledge_base_answer(
                    cached, 
                    sub_intent=sub_intent_str,
                    cache_hit=True
                )
        except Exception as e:
            # ✅ H1: Structured warning
            logger.warning(
                "kb_cache_error",
                layer="redis",
                error=str(e),
                error_type=type(e).__name__
            )
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 2: POSTGRESQL BUFFER (Warm, <10ms)
        # ═══════════════════════════════════════════════════════════════════
        
        try:
            buffered = await self._get_from_buffer(sub_intent_str, language, category)
            
            if buffered:
                # Check if fresh (not stale)
                is_fresh = buffered.is_fresh(max_age_hours=self.buffer_max_age.total_seconds() / 3600)
                
                if is_fresh:
                    # ✅ H1: Structured logging
                    logger.info(
                        "kb_buffer_hit",
                        layer="postgresql",
                        sub_intent=sub_intent_str,
                        language=language,
                        category=category or 'general',
                        is_fresh=True,
                        response_time_ms="<10"
                    )
                    
                    # Store in Redis for next time
                    kb_answer = kb_content_to_answer(buffered, cache_hit=False)
                    await self._store_in_cache(sub_intent_str, language, category, kb_answer)
                    
                    return self._kb_answer_to_knowledge_base_answer(
                        kb_answer,
                        sub_intent=sub_intent_str,
                        cache_hit=False
                    )
                else:
                    # ✅ H1: Structured warning con cálculo de age
                    age_seconds = (datetime.utcnow() - buffered.last_synced).total_seconds()
                    logger.warning(
                        "kb_buffer_stale",
                        layer="postgresql",
                        sub_intent=sub_intent_str,
                        language=language,
                        category=category or 'general',
                        age_seconds=round(age_seconds, 2),
                        age_hours=round(age_seconds / 3600, 1)
                    )
                    # Continue to Layer 3 to refresh
        except Exception as e:
            # ✅ H1: Structured error
            logger.error(
                "kb_buffer_error",
                layer="postgresql",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
        
        # ═══════════════════════════════════════════════════════════════════
        # LAYER 3: SHOPIFY API (Cold, 100-300ms) - Only if configured
        # ═══════════════════════════════════════════════════════════════════
        
        if self.shopify:
            try:
                # ✅ H1: Structured logging
                logger.info(
                    "kb_shopify_fetch",
                    layer="shopify_api",
                    sub_intent=sub_intent_str,
                    language=language,
                    category=category or 'general'
                )
                
                # TODO: Implement direct Shopify fetch
                # For now, trigger background sync and use stale buffer
                # ✅ H1: Structured warning
                logger.warning(
                    "kb_shopify_fetch_not_implemented",
                    layer="shopify_api",
                    fallback="stale_buffer"
                )
                
                # Use stale buffer as last resort
                if buffered:
                    # ✅ H1: Structured logging
                    logger.info(
                        "kb_using_stale_buffer",
                        layer="postgresql",
                        reason="shopify_fetch_not_implemented"
                    )
                    kb_answer = kb_content_to_answer(buffered, cache_hit=False)
                    return self._kb_answer_to_knowledge_base_answer(
                        kb_answer,
                        sub_intent=sub_intent_str,
                        cache_hit=False
                    )
                    
            except Exception as e:
                # ✅ H1: Structured error
                logger.error(
                    "kb_shopify_error",
                    layer="shopify_api",
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True
                )
        
        # No answer found for this specific language
        return None


    async def _get_from_cache(
        self,
        sub_intent: str,
        language: str,
        category: Optional[str]
    ) -> Optional[KBAnswer]:
        """Get KB answer from Redis cache."""
        # Guard: Redis not available (None passed at init or not yet connected).
        # This is expected during startup race or degraded mode.
        # Return None silently to fall through to PostgreSQL buffer (Layer 2).
        if self.redis is None:
            return None

        cache_key = self._build_cache_key(sub_intent, language, category)
        
        try:
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                # Deserialize JSON
                data = json.loads(cached_data)
                return KBAnswer(**data)
             
            return None
            
        except Exception as e:
            # ✅ H1: Structured error
            logger.error(
                "kb_cache_get_error",
                cache_key=cache_key,
                error=str(e),
                error_type=type(e).__name__
            )
            return None
    
    async def _store_in_cache(
        self,
        sub_intent: str,
        language: str,
        category: Optional[str],
        answer: KBAnswer
    ) -> None:
        """Store KB answer in Redis cache."""
        # Guard: Redis not available -- skip silently.
        # Layer 2 (PostgreSQL) will still be used on the next request.
        if self.redis is None:
            return

        cache_key = self._build_cache_key(sub_intent, language, category)
        
        try:
            # Serialize to JSON
            data = answer.model_dump_json()
            
            # Store with TTL
            await self.redis.set(cache_key, data, self.cache_ttl_seconds)
            
            # ✅ H1: Structured debug logging
            logger.debug(
                "kb_cache_stored",
                cache_key=cache_key,
                ttl_seconds=self.cache_ttl_seconds,
                layer="redis"
            )
            
        except Exception as e:
            # ✅ H1: Structured error
            logger.error(
                "kb_cache_store_error",
                cache_key=cache_key,
                error=str(e),
                error_type=type(e).__name__
            )
    
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
            # ✅ H1: Structured error
            logger.error(
                "kb_buffer_get_error",
                sub_intent=sub_intent,
                language=language,
                category=category or 'general',
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return None
    
    # ──────────────────────────────────────────────────────────────────────
    # CONVERSION HELPERS
    # ──────────────────────────────────────────────────────────────────────
    
    def _kb_answer_to_knowledge_base_answer(
        self,
        kb_answer: KBAnswer,
        sub_intent: str,
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
            # ✅ H1: Structured warning
            logger.warning(
                "kb_unknown_sub_intent",
                sub_intent=sub_intent,
                fallback="UNKNOWN"
            )
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
            sub_intent=sub_intent_enum,
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

# ══════════════════════════════════════════════════════════════════════════
# LANGUAGE UTILITIES
# ══════════════════════════════════════════════════════════════════════════

def parse_accept_language(accept_language_header: str) -> list[tuple[str, float]]:
    """
    Parse Accept-Language header to extract language preferences.
    
    Args:
        accept_language_header: HTTP Accept-Language header value
                               Example: "es-MX,es;q=0.9,en;q=0.8"
    
    Returns:
        List of (language_code, quality) tuples sorted by quality (high to low)
        Example: [("es-MX", 1.0), ("es", 0.9), ("en", 0.8)]
    
    Examples:
        >>> parse_accept_language("es-MX,es;q=0.9,en;q=0.8")
        [('es-MX', 1.0), ('es', 0.9), ('en', 0.8)]
        
        >>> parse_accept_language("en")
        [('en', 1.0)]
    """
    if not accept_language_header:
        return []
    
    languages = []
    
    for lang_range in accept_language_header.split(','):
        lang_range = lang_range.strip()
        
        if ';q=' in lang_range:
            lang, quality_str = lang_range.split(';q=')
            try:
                quality = float(quality_str)
            except ValueError:
                quality = 1.0
        else:
            lang = lang_range
            quality = 1.0
        
        languages.append((lang.strip(), quality))
    
    # Sort by quality (descending)
    languages.sort(key=lambda x: x[1], reverse=True)
    
    return languages


def normalize_language_code(language_code: str) -> str:
    """
    Normalize language code to two-letter ISO 639-1 format.
    
    Args:
        language_code: Language code (e.g., "es-MX", "es", "en-US", "EN")
    
    Returns:
        Normalized two-letter lowercase code (e.g., "es", "en")
    
    Examples:
        >>> normalize_language_code("es-MX")
        'es'
        
        >>> normalize_language_code("EN-US")
        'en'
        
        >>> normalize_language_code("es")
        'es'
    """
    if not language_code:
        return "es"  # Default to Spanish
    
    # Extract primary language code (before hyphen if exists)
    primary_lang = language_code.split('-')[0].strip().lower()
    
    # Validate it's 2 or 3 letters (basic sanity check)
    if len(primary_lang) not in [2, 3]:
        return "es"  # Default fallback
    
    # Map 3-letter to 2-letter if needed (optional enhancement)
    lang_map = {
        "spa": "es",
        "eng": "en",
        "fra": "fr",
        # Add more as needed
    }
    
    return lang_map.get(primary_lang, primary_lang[:2])


def get_best_supported_language(
    accept_language_header: str,
    supported_languages: Optional[List[str]] = None
) -> str:
    """
    Extract the best supported language from Accept-Language header.
    
    This is a higher-level wrapper around parse_accept_language() that:
    1. Parses the header
    2. Filters for supported languages only
    3. Normalizes to 2-letter codes
    4. Returns the FIRST supported language
    
    Args:
        accept_language_header: HTTP Accept-Language header
                               Example: "en-US,en;q=0.9,es;q=0.8,fr;q=0.7"
        supported_languages: List of supported 2-letter codes
                            Default: ["es", "en"]
    
    Returns:
        str: Best supported language code ("es" or "en")
             Fallback to "es" if none supported
    
    Examples:
        >>> get_best_supported_language("en-US,en;q=0.9,es;q=0.8")
        'en'
        
        >>> get_best_supported_language("fr;q=0.9,es;q=0.8,en;q=0.7")
        'es'  # fr not supported, es is highest supported
        
        >>> get_best_supported_language("fr,de,pt")
        'es'  # no supported languages, fallback to es
    """
    if supported_languages is None:
        supported_languages = ["es", "en"]
    
    # Parse header
    parsed_languages = parse_accept_language(accept_language_header)
    
    # Empty header → fallback to Spanish
    if not parsed_languages:
        return "es"
    
    # Find first supported language
    for lang_code, _ in parsed_languages:
        # Normalize to 2-letter code
        normalized = normalize_language_code(lang_code)
        
        # Check if supported
        if normalized in supported_languages:
            return normalized
    
    # No supported language found → fallback to Spanish
    return "es"


__all__ = [
    "ShopifyKnowledgeBase",
    "parse_accept_language",
    "normalize_language_code",
    "get_best_supported_language"
]