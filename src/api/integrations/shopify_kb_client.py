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
"""

import logging
import hmac
import hashlib
import asyncio 
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

from src.api.integrations.shopify_client import ShopifyIntegration
from src.api.core.models.kb_models import (
    ShopifyPage,
    ShopifyPagesResponse,
    ShopifyPageResponse,
    ShopifyPageTranslation
)

logger = logging.getLogger(__name__)


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
        
        logger.info("ShopifyKBClient initialized")
        logger.info(f"Webhook validation: {'enabled' if webhook_secret else 'disabled'}")
    
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
            logger.warning(f"Page {page.id}: kb_metadata is not a dict")
            return False
        
        if "sub_intent" not in kb_metadata:
            logger.warning(f"Page {page.id}: kb_metadata missing sub_intent")
            return False
        
        # Check body_html is not empty
        if not page.body_html or page.body_html.strip() == "":
            logger.info(f"Skipping page {page.id} ({page.title}): empty body_html")
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
        logger.info(f"Fetching KB pages (limit={limit})")
        
        # Step 1: Fetch all pages from Shopify
        all_pages = await self.get_pages(limit=limit)
        # all_pages = await asyncio.to_thread(self.get_pages, limit)
        logger.info(f"Retrieved {len(all_pages)} total pages from Shopify")
        
        # Step 2: Parse pages to Pydantic models
        parsed_pages = []
        for page_data in all_pages:
            try:
                page = ShopifyPage(**page_data)
                parsed_pages.append(page)
            except Exception as e:
                logger.error(f"Failed to parse page {page_data.get('id')}: {e}")
                continue
        
        # ✨ OPTIMIZATION: Step 3: Fetch ALL metafields in PARALLEL
        logger.info(f"Fetching metafields for {len(parsed_pages)} pages (PARALLEL)...")
        
        # Create tasks for all metafields fetches
        metafields_tasks = [
            self.get_page_metafields(page.id) 
            for page in parsed_pages
        ]
        
        # Execute all tasks in parallel
        # return_exceptions=True ensures one error doesn't break everything
        all_metafields = await asyncio.gather(*metafields_tasks, return_exceptions=True)
        
        # Step 4: Filter KB pages and handle results
        kb_pages = []
        skipped = 0
        invalid = 0
        
        for page, metafields in zip(parsed_pages, all_metafields):
            # Handle exceptions from gather
            if isinstance(metafields, Exception):
                logger.error(f"Failed to fetch metafields for page {page.id}: {metafields}")
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
                    logger.warning(
                        f"Invalid KB page (Page ID {page.id}): Missing sub_intent"
                    )
                    invalid += 1
                    continue
            
            kb_pages.append((page, metafields))
        
        logger.info(
            f"Filtered KB pages: {len(kb_pages)} KB pages, "
            f"{skipped} skipped (non-KB), {invalid} invalid"
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
            logger.info(f"Fetching page {page_id}")
            
            response = self._make_request_with_retry(url)
            data = response.json()
            
            # Shopify returns: {"page": {...}}
            page_data = data.get("page")
            if not page_data:
                logger.error(f"No page data in response for page {page_id}")
                return None
            
            page = ShopifyPage(**page_data)
            logger.info(f"Successfully fetched page {page_id}: {page.title}")
            
            return page
            
        except Exception as e:
            logger.error(f"Error fetching page {page_id}: {e}")
            return None
    
    async def get_pages(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict]:
        """
        Wrapper for parent class get_products() but for pages.
        
        Note: Shopify Admin API doesn't have a /pages endpoint with pagination
        like /products. We use the parent's pagination logic and adapt it.
        
        For now, we'll implement a simple version that fetches all pages.

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
                logger.info(f"Fetching pages from: {url}")
                
                # response = self._make_request_with_retry(url)
                # ✅ Execute in thread pool
                response = await asyncio.to_thread(
                    self._make_request_with_retry, 
                    url
                )
                data = response.json()
                pages = data.get("pages", [])
                
                if pages:
                    all_pages.extend(pages)
                    logger.info(f"Fetched {len(pages)} pages, total: {len(all_pages)}")
                    
                    # Check limit
                    if limit and len(all_pages) >= limit:
                        all_pages = all_pages[:limit]
                        break
                else:
                    break
                
                # Next page
                url = self._get_next_page_url(response)
            
            logger.info(f"Total pages fetched: {len(all_pages)}")
            return all_pages
            
        except Exception as e:
            logger.error(f"Error fetching pages: {e}")
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
            logger.debug(f"Fetching metafields for page {page_id}")
            
            # ✅ OPTIMIZATION: Execute sync call in thread pool
            # This allows true parallelization with asyncio.gather()
            response = await asyncio.to_thread(
                self._make_request_with_retry, 
                url
            )
            data = response.json()
            
            # Parse metafields into dict
            metafields_dict = {}
            
            for mf in data.get("metafields", []):
                # ... resto del código sin cambios (líneas 282-319)
                namespace = mf.get("namespace")
                key = mf.get("key")
                value = mf.get("value")
                mf_type = mf.get("type")
                
                # Skip if missing required fields
                if not namespace or not key:
                    logger.warning(f"Metafield missing namespace or key: {mf}")
                    continue
                
                # Create composite key (namespace.key)
                composite_key = f"{namespace}.{key}"
                
                # Parse JSON values
                if mf_type in ['json', 'json_string']:
                    try:
                        import json
                        value = json.loads(value) if isinstance(value, str) else value
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"Failed to parse JSON metafield {composite_key} "
                            f"for page {page_id}: {e}"
                        )
                        pass
                
                metafields_dict[composite_key] = value
            
            logger.debug(
                f"Found {len(metafields_dict)} metafields for page {page_id}: "
                f"{list(metafields_dict.keys())}"
            )
            
            return metafields_dict
            
        except Exception as e:
            logger.error(f"Error fetching metafields for page {page_id}: {e}")
            return {}
    
    # ──────────────────────────────────────────────────────────────────────
    # TRANSLATIONS API
    # ──────────────────────────────────────────────────────────────────────
    
    def get_page_translations(
        self,
        page_id: int
    ) -> Dict[str, str]:
        """
        Fetch all translations for a page.
        
        Uses Shopify Translations API (part of Markets).
        
        Args:
            page_id: Shopify Page ID
            
        Returns:
            Dict mapping language code to translated content:
            {
                "es": "<h2>Política de Devoluciones</h2>...",
                "en": "<h2>Return Policy</h2>...",
                "pt": "<h2>Política de Devoluções</h2>..."
            }
            
        Example:
            >>> translations = client.get_page_translations(123456789)
            >>> print(translations.get("en"))
        """
        try:
            url = f"{self.api_url}/pages/{page_id}/translations.json"
            logger.info(f"Fetching translations for page {page_id}")
            
            response = self._make_request_with_retry(url)
            data = response.json()
            
            # Parse translations
            translations = {}
            translation_list = data.get("translations", [])
            
            for trans_data in translation_list:
                try:
                    trans = ShopifyPageTranslation(**trans_data)
                    
                    # We only care about body_html translations
                    if trans.key == "body_html":
                        translations[trans.locale] = trans.value
                        
                except Exception as e:
                    logger.warning(f"Failed to parse translation: {e}")
                    continue
            
            logger.info(
                f"Found {len(translations)} translations for page {page_id}: "
                f"{list(translations.keys())}"
            )
            
            return translations
            
        except Exception as e:
            logger.error(f"Error fetching translations for page {page_id}: {e}")
            return {}
    
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
            
        Example:
            >>> # In FastAPI webhook handler:
            >>> @app.post("/webhooks/shopify/pages/update")
            >>> async def handle_page_update(request: Request):
            >>>     body = await request.body()
            >>>     hmac_header = request.headers.get("X-Shopify-Hmac-SHA256")
            >>>     
            >>>     if not client.validate_webhook(body, hmac_header):
            >>>         raise HTTPException(401, "Invalid webhook signature")
            >>>     
            >>>     # Process webhook...
        """
        if not self.webhook_secret:
            logger.warning(
                "Webhook secret not configured! "
                "Skipping HMAC validation (NOT RECOMMENDED for production)"
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
            logger.error(
                f"Invalid webhook HMAC! "
                f"Expected: {computed_hmac[:10]}..., "
                f"Got: {hmac_header[:10]}..."
            )
        
        return is_valid    

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
