"""
Shopify Knowledge Base Client
==============================

Extension of ShopifyIntegration specifically for Knowledge Base Pages API.

This client handles:
1. Fetching KB pages (tagged with "kb")
2. Getting page translations (Shopify Markets)
3. Parsing KB metadata from tags
4. Webhook HMAC validation

Author: Retail Recommender System Team
Date: 2026-01-11
Version: H1 - Structured Logging Migration
"""

import structlog  # ✅ H1: Structured Logging Migration
import hmac
import hashlib
import asyncio 
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta

from src.api.integrations.shopify_client import ShopifyIntegration
from src.api.core.models.kb_models import (
    ShopifyPage,
    ShopifyPagesResponse,
    ShopifyPageResponse,
    ShopifyPageTranslation
)

logger = structlog.get_logger(__name__)  # ✅ H1: Structured Logging Migration


# ══════════════════════════════════════════════════════════════════════════
# KB METADATA PARSER
# ══════════════════════════════════════════════════════════════════════════

class KBMetadataParser:
    """
    Parses Knowledge Base metadata from Shopify Page tags.
    
    Tag Format:
    -----------
    Tags are comma-separated. For KB pages:
    
    ["kb", "sub_intent", "category"]
    
    Examples:
    - "kb, policy_return, general"        → sub_intent="policy_return", category="general"
    - "kb, policy_return, ZAPATOS"        → sub_intent="policy_return", category="ZAPATOS"
    - "kb, product_material, VESTIDOS"    → sub_intent="product_material", category="VESTIDOS"
    - "kb, policy_shipping"               → sub_intent="policy_shipping", category=None
    
    The first tag MUST be "kb" to identify KB pages.
    """
    
    @staticmethod
    def parse_tags(tags: str) -> Dict[str, Optional[str]]:
        """
        Parse KB metadata from Shopify tags.
        
        Args:
            tags: Comma-separated tags string from Shopify
            
        Returns:
            Dict with:
            - is_kb_page: bool (True if first tag is "kb")
            - sub_intent: str or None
            - category: str or None
            
        Examples:
            >>> parse_tags("kb, policy_return, ZAPATOS")
            {"is_kb_page": True, "sub_intent": "policy_return", "category": "ZAPATOS"}
            
            >>> parse_tags("kb, policy_shipping")
            {"is_kb_page": True, "sub_intent": "policy_shipping", "category": None}
            
            >>> parse_tags("blog, news")
            {"is_kb_page": False, "sub_intent": None, "category": None}
        """
        if not tags:
            return {
                "is_kb_page": False,
                "sub_intent": None,
                "category": None
            }
        
        # Parse tags into list
        tag_list = [tag.strip().lower() for tag in tags.split(",")]
        
        # Check if first tag is "kb"
        is_kb_page = len(tag_list) > 0 and tag_list[0] == "kb"
        
        if not is_kb_page:
            return {
                "is_kb_page": False,
                "sub_intent": None,
                "category": None
            }
        
        # Extract sub_intent (second tag)
        sub_intent = tag_list[1] if len(tag_list) > 1 else None
        
        # Extract category (third tag) - keep original case for category
        category = None
        if len(tag_list) > 2:
            # Re-parse to get original case for category
            original_tags = [tag.strip() for tag in tags.split(",")]
            category = original_tags[2] if len(original_tags) > 2 else None
        
        return {
            "is_kb_page": is_kb_page,
            "sub_intent": sub_intent,
            "category": category
        }
    
    @staticmethod
    def validate_metadata(metadata: Dict[str, Optional[str]]) -> Tuple[bool, Optional[str]]:
        """
        Validate KB metadata.
        
        Args:
            metadata: Parsed metadata from parse_tags()
            
        Returns:
            (is_valid, error_message)
            
        Validation rules:
        - Must be a KB page (is_kb_page=True)
        - Must have sub_intent
        """
        if not metadata.get("is_kb_page"):
            return False, "Not a KB page (missing 'kb' tag)"
        
        if not metadata.get("sub_intent"):
            return False, "Missing sub_intent (second tag)"
        
        return True, None


# ══════════════════════════════════════════════════════════════════════════
# SHOPIFY KB CLIENT
# ══════════════════════════════════════════════════════════════════════════

class ShopifyKBClient(ShopifyIntegration):
    """
    Shopify Knowledge Base Client.
    
    Extends ShopifyIntegration with KB-specific methods:
    - get_kb_pages(): Fetch all KB pages
    - get_page_by_id(): Fetch single page
    - get_page_translations(): Fetch translations for a page
    - parse_kb_metadata(): Parse KB metadata from tags
    """
    
    def __init__(self, shop_url: str, access_token: str, webhook_secret: Optional[str] = None):
        """
        Initialize Shopify KB Client.
        
        Args:
            shop_url: Shopify store URL (e.g., "tutienda.myshopify.com")
            access_token: Shopify Admin API access token
            webhook_secret: Webhook HMAC secret (for validation)
        """
        super().__init__(shop_url, access_token)
        self.webhook_secret = webhook_secret
        self.metadata_parser = KBMetadataParser()

        self._cached_locales: Optional[Tuple[str, List[str]]] = None
        self._locales_cache_expires_at: Optional[datetime] = None
        self._locales_cache_ttl = timedelta(hours=1)
        self._locales_cache_lock = asyncio.Lock()
        
        # ✅ H1: Structured logging
        logger.info(
            "shopify_kb_client_initialized",
            shop_url=shop_url,
            webhook_validation_enabled=webhook_secret is not None
        )
    
    # ──────────────────────────────────────────────────────────────────────
    # KB PAGES API
    # ──────────────────────────────────────────────────────────────────────
    def is_kb_page(self, page: ShopifyPage, metafields: Dict[str, Any]) -> bool:
        """
        Check if a Shopify page is a KB page using metafields.
        
        Args:
            page: ShopifyPage object
            metafields: Metafields dict from get_page_metafields()
            
        Returns:
            True if page has KB metadata
        """
        # Check for KB metadata metafield
        kb_metadata = metafields.get("custom.kb_metadata")
        
        if not kb_metadata:
            return False
        
        # Validate required fields
        if not isinstance(kb_metadata, dict):
            # ✅ H1: Structured warning
            logger.warning(
                "shopify_kb_metadata_invalid_type",
                page_id=page.id,
                actual_type=type(kb_metadata).__name__
            )
            return False
        
        if "sub_intent" not in kb_metadata:
            # ✅ H1: Structured warning
            logger.warning(
                "shopify_kb_metadata_missing_sub_intent",
                page_id=page.id,
                page_title=page.title
            )
            return False
        
        # Check body_html is not empty
        if not page.body_html or page.body_html.strip() == "":
            # ✅ H1: Structured info
            logger.info(
                "shopify_kb_page_skipped_empty_body",
                page_id=page.id,
                page_title=page.title
            )
            return False
        
        return True
    

    async def get_kb_pages(
        self,
        limit: Optional[int] = None,
        validate_metadata: bool = True
    ) -> List[Tuple[ShopifyPage, Dict[str, Any]]]:
        """
        Fetch all Knowledge Base pages from Shopify with their metafields.
        
        OPTIMIZED: Uses asyncio.gather() for parallel metafields fetching.
        
        Performance:
        - Sequential: O(n) where n = number of pages (~400ms per page)
        - Parallel: O(1) for metafields fetch (~400-500ms total)
        
        Returns:
            List of tuples: (ShopifyPage, metafields_dict)
        """
        # ✅ H1: Structured logging
        logger.info(
            "shopify_kb_pages_fetch_started",
            limit=limit,
            validate_metadata=validate_metadata
        )
        
        # Step 1: Fetch all pages from Shopify
        all_pages = await self.get_pages(limit=limit)
        
        # ✅ H1: Structured logging
        logger.info(
            "shopify_pages_retrieved",
            total_pages=len(all_pages)
        )
        
        # Step 2: Parse pages to Pydantic models
        parsed_pages = []
        parse_errors = 0
        
        for page_data in all_pages:
            try:
                page = ShopifyPage(**page_data)
                parsed_pages.append(page)
            except Exception as e:
                # ✅ H1: Structured error
                logger.error(
                    "shopify_page_parse_error",
                    page_id=page_data.get('id'),
                    error=str(e),
                    error_type=type(e).__name__
                )
                parse_errors += 1
                continue
        
        if parse_errors > 0:
            # ✅ H1: Structured warning
            logger.warning(
                "shopify_pages_parse_errors",
                total_errors=parse_errors
            )
        
        # ✨ OPTIMIZATION: Step 3: Fetch ALL metafields in PARALLEL
        # ✅ H1: Structured logging
        logger.info(
            "shopify_metafields_fetch_parallel",
            total_pages=len(parsed_pages)
        )
        
        # Create tasks for all metafields fetches
        metafields_tasks = [
            self.get_page_metafields(page.id) 
            for page in parsed_pages
        ]
        
        # Execute all tasks in parallel
        all_metafields = await asyncio.gather(*metafields_tasks, return_exceptions=True)
        
        # Step 4: Filter KB pages and handle results
        kb_pages = []
        skipped = 0
        invalid = 0
        metafield_errors = 0
        
        for page, metafields in zip(parsed_pages, all_metafields):
            # Handle exceptions from gather
            if isinstance(metafields, Exception):
                # ✅ H1: Structured error
                logger.error(
                    "shopify_metafields_fetch_error",
                    page_id=page.id,
                    error=str(metafields),
                    error_type=type(metafields).__name__
                )
                metafield_errors += 1
                invalid += 1
                continue
            
            # Check if it's a KB page
            if not self.is_kb_page(page, metafields):
                skipped += 1
                continue
            
            # Validate metadata if requested
            if validate_metadata:
                kb_metadata = metafields.get("custom.kb_metadata", {})
                
                if not kb_metadata.get("sub_intent"):
                    # ✅ H1: Structured warning
                    logger.warning(
                        "shopify_kb_invalid_missing_sub_intent",
                        page_id=page.id
                    )
                    invalid += 1
                    continue
            
            kb_pages.append((page, metafields))
        
        # ✅ H1: Structured logging con métricas completas
        logger.info(
            "shopify_kb_pages_filtered",
            kb_pages_count=len(kb_pages),
            skipped_non_kb=skipped,
            invalid_metadata=invalid,
            metafield_errors=metafield_errors,
            success_rate=round((len(kb_pages) / len(parsed_pages) * 100) if parsed_pages else 0, 1)
        )
        
        return kb_pages
    
    def get_page_by_id(self, page_id: int) -> Optional[ShopifyPage]:
        """
        Fetch a single page by ID.
        
        Args:
            page_id: Shopify Page ID
            
        Returns:
            ShopifyPage or None if not found
            
        Example:
            >>> page = client.get_page_by_id(123456789)
            >>> print(page.title)
        """
        try:
            url = f"{self.api_url}/pages/{page_id}.json"
            
            # ✅ H1: Structured logging
            logger.info(
                "shopify_page_fetch_by_id",
                page_id=page_id
            )
            
            response = self._make_request_with_retry(url)
            data = response.json()
            
            # Shopify returns: {"page": {...}}
            page_data = data.get("page")
            if not page_data:
                # ✅ H1: Structured error
                logger.error(
                    "shopify_page_no_data",
                    page_id=page_id
                )
                return None
            
            page = ShopifyPage(**page_data)
            
            # ✅ H1: Structured logging
            logger.info(
                "shopify_page_fetched",
                page_id=page_id,
                page_title=page.title
            )
            
            return page
            
        except Exception as e:
            # ✅ H1: Structured error
            logger.error(
                "shopify_page_fetch_error",
                page_id=page_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return None
    
    async def get_pages(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict]:
        """
        Async version with pagination.
        Args:
            limit: Max number of pages to fetch (None = all)
            offset: Offset for pagination (not used here)
            
        Returns:
            List of page dicts
        """
        try:
            all_pages = []
            url = f"{self.api_url}/pages.json?limit=250"
            
            while url:
                # ✅ H1: Structured debug
                logger.info(
                    "shopify_pages_fetching",
                    url=url
                )
                
                # Execute in thread pool
                response = await asyncio.to_thread(
                    self._make_request_with_retry, 
                    url
                )
                data = response.json()
                pages = data.get("pages", [])
                
                if pages:
                    all_pages.extend(pages)
                    
                    # ✅ H1: Structured info
                    logger.debug(
                        "shopify_pages_batch_fetched",
                        batch_size=len(pages),
                        total_accumulated=len(all_pages)
                    )
                    
                    # Check limit
                    if limit and len(all_pages) >= limit:
                        all_pages = all_pages[:limit]
                        break
                else:
                    break
                
                # Next page
                url = self._get_next_page_url(response)
            
            # ✅ H1: Structured logging final
            logger.info(
                "shopify_pages_fetch_completed",
                total_pages=len(all_pages)
            )
            return all_pages
            
        except Exception as e:
            # ✅ H1: Structured error
            logger.error(
                "shopify_pages_fetch_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return []
    
    async def get_page_metafields(self, page_id: int) -> Dict[str, Any]:
        """
        Fetch metafields for a specific page.
        
        OPTIMIZED: Uses asyncio.to_thread() to execute sync HTTP call
        in thread pool, enabling true parallelization with asyncio.gather().
        
        Args:
            page_id: Shopify Page ID
            
        Returns:
            Dict with metafields indexed by namespace.key
            Example: {"custom.kb_metadata": {"sub_intent": "policy_return", ...}}
        """
        try:
            # Build API URL
            url = f"{self.api_url}/pages/{page_id}/metafields.json"
            
            # ✅ H1: Structured debug
            # logger.debug(
            #     "shopify_metafields_fetching",
            #     page_id=page_id
            # )
            
            # Execute sync call in thread pool
            response = await asyncio.to_thread(
                self._make_request_with_retry, 
                url
            )
            data = response.json()
            
            # Parse metafields into dict
            metafields_dict = {}
            
            for mf in data.get("metafields", []):
                namespace = mf.get("namespace")
                key = mf.get("key")
                value = mf.get("value")
                mf_type = mf.get("type")
                
                # Skip if missing required fields
                if not namespace or not key:
                    # ✅ H1: Structured warning
                    logger.warning(
                        "shopify_metafield_missing_fields",
                        page_id=page_id,
                        metafield=mf
                    )
                    continue
                
                # Create composite key (namespace.key)
                composite_key = f"{namespace}.{key}"
                
                # Parse JSON values
                if mf_type in ['json', 'json_string']:
                    try:
                        import json
                        value = json.loads(value) if isinstance(value, str) else value
                    except json.JSONDecodeError as e:
                        # ✅ H1: Structured warning
                        logger.warning(
                            "shopify_metafield_json_parse_error",
                            page_id=page_id,
                            composite_key=composite_key,
                            error=str(e)
                        )
                        pass
                
                metafields_dict[composite_key] = value
            
            # ✅ H1: Structured debug
            # Log eliminado: información redundante
            # La información se agrega en shopify_kb_pages_filtered
            
            return metafields_dict
            
        except Exception as e:
            # ✅ H1: Structured error
            logger.error(
                "shopify_metafields_fetch_error",
                page_id=page_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return {}
    
    # ──────────────────────────────────────────────────────────────────────
    # TRANSLATIONS API
    # ──────────────────────────────────────────────────────────────────────
    
    async def get_page_translations(self, page_id: int) -> Dict[str, str]:
        """
        Fetch all translations for a page using GraphQL.
        
        OPTIMIZED VERSION:
        - Uses cached shopLocales (1 query vs 13 queries per sync)
        - Parallel translation fetch (for future multi-language support)
        
        Returns:
            Dict mapping language code to translated HTML:
            {"en": "<h2>Return Policy</h2>...", "pt": "<h2>Política...</h2>"}
        """
        try:
            # STEP 1: Get available shop locales (Uses cache)
            primary_locale, available_locales = await self._get_shop_locales()
            
            # If no translation locales available, return empty
            if not available_locales:
                # ✅ H1: Structured info
                logger.info(
                    "shopify_no_translation_locales",
                    page_id=page_id,
                    primary_locale=primary_locale
                )
                return {}
            
            # STEP 2: Query translations for each locale IN PARALLEL
            
            async def fetch_translation_for_locale(locale: str) -> tuple[str, Optional[str]]:
                """Fetch translation for a specific locale."""
                try:
                    # Build GraphQL query for specific locale
                    translation_query = """
                    query getPageTranslation($resourceId: ID!, $locale: String!) {
                    translatableResource(resourceId: $resourceId) {
                        resourceId
                        translations(locale: $locale) {
                        key
                        value
                        locale
                        }
                    }
                    }
                    """
                    
                    variables = {
                        "resourceId": f"gid://shopify/Page/{page_id}",
                        "locale": locale
                    }
                    
                    # ✅ H1: Structured debug
                    # Log eliminado: ruido excesivo (~26 veces por sync)
                    # La información se agrega en shopify_translations_fetched
                    
                    # Execute GraphQL query
                    data = await self._graphql_query_with_retry(translation_query, variables)

                    # Parse translations for this locale
                    resource = data.get("translatableResource", {})
                    translations_raw = resource.get("translations", [])
                    
                    # Filter only body_html translation
                    for trans in translations_raw:
                        if trans["key"] == "body_html" and trans["value"]:
                            # ✅ H1: Structured debug
                            # Log eliminado: información agregada en log final
                            return (locale, trans["value"])
                    
                    # No body_html translation found for this locale
                    # ✅ H1: Structured debug
                    # Log eliminado: ausencia de traducción no es relevante
                    return (locale, None)
                    
                except Exception as e:
                    # ✅ H1: Structured warning
                    logger.warning(
                        "shopify_translation_fetch_error",
                        page_id=page_id,
                        locale=locale,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    return (locale, None)
            
            # ✨ OPTIMIZATION: Execute all translation fetches in PARALLEL
            # ✅ H1: Structured debug
            # Log eliminado: información redundante (~13 veces por sync)
            
            # Create tasks for all locales
            translation_tasks = [
                fetch_translation_for_locale(locale) 
                for locale in available_locales
            ]
            
            # Execute all tasks in parallel
            translation_results = await asyncio.gather(*translation_tasks)
            
            # STEP 3: Build translations dict (filter out None values)
            translations = {}
            
            for locale, translated_html in translation_results:
                if translated_html is not None:
                    translations[locale] = translated_html
            
            # STEP 4: Log results and return
            if translations:
                # ✅ H1: Structured info
                logger.info(
                    "shopify_translations_fetched",
                    page_id=page_id,
                    translations_count=len(translations),
                    locales=list(translations.keys())
                )
            else:
                # ✅ H1: Structured info
                logger.info(
                    "shopify_no_translations_found",
                    page_id=page_id,
                    primary_locale=primary_locale
                )
            
            return translations
            
        except Exception as e:
            # ✅ H1: Structured error
            logger.error(
                "shopify_translations_fetch_error",
                page_id=page_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return {}
    
    async def get_page_title_translation(
        self, 
        page_id: int,
        locale: str
    ) -> Optional[str]:
        """
        Fetch translated title for a specific locale via Shopify Translation API.
        
        Args:
            page_id: Shopify Page ID
            locale: Language code (en, es, pt, etc.)
            
        Returns:
            Translated title string or None if not found
            
        Example:
            >>> title_es = await client.get_page_title_translation(123, "es")
            >>> print(title_es)  # "Política de Devoluciones"
            
            >>> title_en = await client.get_page_title_translation(123, "en")
            >>> print(title_en)  # "Return Policy"
        """
        try:
            # GraphQL query for title translation
            translation_query = """
            query getPageTitleTranslation($resourceId: ID!, $locale: String!) {
                translatableResource(resourceId: $resourceId) {
                    resourceId
                    translations(locale: $locale) {
                        key
                        value
                        locale
                    }
                }
            }
            """
            
            variables = {
                "resourceId": f"gid://shopify/Page/{page_id}",
                "locale": locale
            }
            
            # ✅ H1: Structured debug logging
            logger.debug(
                "shopify_title_translation_fetching",
                page_id=page_id,
                locale=locale
            )
            
            # Execute GraphQL query
            data = await self._graphql_query_with_retry(translation_query, variables)
            
            # Parse translations
            resource = data.get("translatableResource", {})
            translations = resource.get("translations", [])
            
            # Find title translation
            for trans in translations:
                if trans["key"] == "title" and trans["value"]:
                    # ✅ H1: Structured info logging
                    logger.info(
                        "shopify_title_translation_found",
                        page_id=page_id,
                        locale=locale,
                        title=trans["value"]
                    )
                    return trans["value"]
            
            # No title translation found
            # ✅ H1: Structured debug
            logger.debug(
                "shopify_title_translation_not_found",
                page_id=page_id,
                locale=locale,
                fallback="using_original_title"
            )
            return None
            
        except Exception as e:
            # ✅ H1: Structured warning
            logger.warning(
                "shopify_title_translation_fetch_failed",
                page_id=page_id,
                locale=locale,
                error=str(e),
                error_type=type(e).__name__,
                fallback="using_original_title"
            )
            return None


    # ──────────────────────────────────────────────────────────────────────
    # METADATA PARSING
    # ──────────────────────────────────────────────────────────────────────
    
    def parse_kb_metadata(self, page: ShopifyPage) -> Dict[str, Optional[str]]:
        """
        Parse KB metadata from Shopify Page tags.
        
        Args:
            page: ShopifyPage object
            
        Returns:
            Dict with is_kb_page, sub_intent, category
            
        Example:
            >>> page = client.get_page_by_id(123456789)
            >>> metadata = client.parse_kb_metadata(page)
            >>> print(metadata["sub_intent"])
            "policy_return"
        """
        return self.metadata_parser.parse_tags(page.tags or "")
    
    # ──────────────────────────────────────────────────────────────────────
    # WEBHOOK VALIDATION
    # ──────────────────────────────────────────────────────────────────────
    
    def validate_webhook(
        self,
        data: bytes,
        hmac_header: str
    ) -> bool:
        """
        Validate Shopify webhook HMAC signature.
        
        Security: ALWAYS validate webhooks in production to prevent
        unauthorized requests.
        
        Args:
            data: Raw request body (bytes)
            hmac_header: X-Shopify-Hmac-SHA256 header value
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            # ✅ H1: Structured warning
            logger.warning(
                "shopify_webhook_validation_disabled",
                reason="webhook_secret_not_configured"
            )
            return True
        
        # Compute HMAC
        computed_hmac = hmac.new(
            self.webhook_secret.encode('utf-8'),
            data,
            hashlib.sha256
        ).hexdigest()
        
        # Compare with provided HMAC (constant-time comparison)
        is_valid = hmac.compare_digest(computed_hmac, hmac_header)
        
        if not is_valid:
            # ✅ H1: Structured error
            logger.error(
                "shopify_webhook_invalid_hmac",
                expected_hmac_prefix=computed_hmac[:10],
                received_hmac_prefix=hmac_header[:10]
            )
        
        return is_valid    
    

    async def _get_shop_locales(self) -> Tuple[str, List[str]]:
        """
        Get shop locales with 1-hour in-memory cache.
        
        Thread-safe: Uses asyncio.Lock() to prevent race conditions
        when multiple coroutines call this method simultaneously.
        
        Returns:
            (primary_locale, available_translation_locales)
        """
        # FAST PATH: Check cache WITHOUT lock (optimization)
        now = datetime.utcnow()
        if (self._cached_locales and 
            self._locales_cache_expires_at and 
            now < self._locales_cache_expires_at):
            
            # ✅ H1: Structured info
            logger.debug(
                "shopify_locales_cache_hit",
                ttl_hours=self._locales_cache_ttl.total_seconds() / 3600
            )
            return self._cached_locales
        
        # SLOW PATH: Cache miss/expired - acquire lock
        async with self._locales_cache_lock:
            # Re-check cache INSIDE lock
            now = datetime.utcnow()
            if (self._cached_locales and 
                self._locales_cache_expires_at and 
                now < self._locales_cache_expires_at):
                
                # ✅ H1: Structured info
                logger.info(
                    "shopify_locales_cache_hit_after_lock",
                    populated_by="another_task"
                )
                return self._cached_locales
            
            # Only first coroutine reaches here - fetch fresh data
            # ✅ H1: Structured info
            logger.info(
                "shopify_locales_fetching",
                reason="cache_miss_or_expired"
            )
            
            locales_query = """
            query getShopLocales {
            shopLocales { locale primary published }
            }
            """
            
            data = await self._graphql_query(locales_query)
            
            # Parse locales
            available_locales = []
            primary_locale = None
            
            for shop_locale in data.get("shopLocales", []):
                locale = shop_locale["locale"]
                if shop_locale["primary"]:
                    primary_locale = locale
                elif shop_locale["published"]:
                    available_locales.append(locale)
            
            # Cache result
            result = (primary_locale, available_locales)
            self._cached_locales = result
            self._locales_cache_expires_at = now + self._locales_cache_ttl
            
            # ✅ H1: Structured info
            logger.info(
                "shopify_locales_cached",
                ttl_hours=self._locales_cache_ttl.total_seconds() / 3600,
                primary_locale=primary_locale,
                translation_locales=available_locales,
                translation_count=len(available_locales)
            )
            
            return result
    
    def invalidate_locales_cache(self) -> None:
        """Force refresh of cached locales on next call."""
        self._cached_locales = None
        self._locales_cache_expires_at = None
        
        # ✅ H1: Structured info
        logger.info("shopify_locales_cache_invalidated")

# ══════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION
# ══════════════════════════════════════════════════════════════════════════

def create_shopify_kb_client(
    shop_url: str,
    access_token: str,
    webhook_secret: Optional[str] = None
) -> ShopifyKBClient:
    """
    Factory function to create ShopifyKBClient.
    
    Args:
        shop_url: Shopify store URL
        access_token: Admin API access token
        webhook_secret: Webhook HMAC secret (optional)
        
    Returns:
        Configured ShopifyKBClient instance
        
    Example:
        >>> from src.api.core.config import settings
        >>> client = create_shopify_kb_client(
        >>>     shop_url=settings.SHOPIFY_SHOP_URL,
        >>>     access_token=settings.SHOPIFY_ACCESS_TOKEN,
        >>>     webhook_secret=settings.SHOPIFY_WEBHOOK_SECRET
        >>> )
    """
    return ShopifyKBClient(
        shop_url=shop_url,
        access_token=access_token,
        webhook_secret=webhook_secret
    )