"""
Shopify Knowledge Base Sync Service
====================================

Orchestrates synchronization of KB content from Shopify CMS to local buffer.

Responsibilities:
1. Fetch pages from Shopify API
2. Parse metadata (sub_intent, language, category)
3. Store in PostgreSQL buffer
4. Invalidate Redis cache
5. Handle errors and retry logic
6. Collect sync metrics

Author: Retail Recommender System Team
Date: 2026-01-11
"""

import logging
import asyncio
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from uuid import uuid4

import asyncpg
from redis import Redis

from src.api.integrations.shopify_kb_client import ShopifyKBClient, KBMetadataParser
from src.api.core.models.kb_models import (
    ShopifyPage,
    KBContent,
    KBContentCreate,
    KBSyncMetadata,
    KBSyncReport,
    SyncStatus
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# SYNC SERVICE
# ══════════════════════════════════════════════════════════════════════════

class ShopifyKBSyncService:
    """
    Shopify Knowledge Base Sync Service.
    
    Usage:
    ------
    ```python
    sync_service = ShopifyKBSyncService(
        shopify_client=shopify_client,
        db_pool=db_pool,
        redis_client=redis_client
    )
    
    # Full sync
    report = await sync_service.sync_all_pages()
    print(f"Synced {report.successful}/{report.total_pages} pages")
    
    # Single page sync
    metadata = await sync_service.sync_page(page_id=123456789)
    ```
    """
    
    def __init__(
        self,
        shopify_client: ShopifyKBClient,
        db_pool: asyncpg.Pool,
        redis_client: Redis
    ):
        """
        Initialize sync service.
        
        Args:
            shopify_client: Configured Shopify KB client
            db_pool: AsyncPG database connection pool
            redis_client: Redis client (for cache invalidation)
        """
        self.shopify = shopify_client
        self.db = db_pool
        self.redis = redis_client
        self.metadata_parser = KBMetadataParser()
        
        logger.info("ShopifyKBSyncService initialized")
    
    # ──────────────────────────────────────────────────────────────────────
    # FULL SYNC
    # ──────────────────────────────────────────────────────────────────────
    
    async def sync_all_pages(
        self,
        validate_metadata: bool = True
    ) -> KBSyncReport:
        """
        Sync all KB pages from Shopify to local buffer.
        
        This performs a full sync:
        1. Fetch all KB pages from Shopify
        2. Parse metadata
        3. Store in PostgreSQL
        4. Invalidate Redis cache
        5. Collect metrics
        
        Args:
            validate_metadata: Skip pages with invalid metadata
            
        Returns:
            KBSyncReport with results
            
        Example:
            >>> report = await sync_service.sync_all_pages()
            >>> print(f"Success rate: {report.successful / report.total_pages * 100:.1f}%")
        """
        logger.info("=" * 70)
        logger.info("Starting FULL SYNC of KB pages from Shopify")
        logger.info("=" * 70)
        
        sync_started_at = datetime.utcnow()
        report = KBSyncReport(
            total_pages=0,
            successful=0,
            failed=0,
            skipped=0,
            sync_started_at=sync_started_at,
            errors=[],
            details=[]
        )
        
        try:
            # Step 1: Fetch all KB pages from Shopify
            logger.info("Step 1: Fetching KB pages from Shopify...")
            kb_pages = self.shopify.get_kb_pages(validate_metadata=validate_metadata)
            
            report.total_pages = len(kb_pages)
            logger.info(f"Found {report.total_pages} KB pages")
            
            if report.total_pages == 0:
                logger.warning("No KB pages found in Shopify!")
                report.sync_completed_at = datetime.utcnow()
                report.duration_seconds = (
                    report.sync_completed_at - sync_started_at
                ).total_seconds()
                return report
            
            # Step 2: Sync each page
            logger.info("Step 2: Syncing pages to local buffer...")
            
            for i, page in enumerate(kb_pages, 1):
                logger.info(f"[{i}/{report.total_pages}] Processing page {page.id}: {page.title}")
                
                try:
                    metadata = await self.sync_page(page.id)
                    
                    if metadata.status == SyncStatus.SUCCESS:
                        report.successful += 1
                    elif metadata.status == SyncStatus.FAILED:
                        report.failed += 1
                        report.errors.append(metadata.last_error or "Unknown error")
                    else:
                        report.skipped += 1
                    
                    report.details.append(metadata)
                    
                except Exception as e:
                    logger.error(f"Failed to sync page {page.id}: {e}")
                    report.failed += 1
                    report.errors.append(f"Page {page.id}: {str(e)}")
                    
                    # Add failed metadata
                    report.details.append(KBSyncMetadata(
                        sub_intent="unknown",
                        language="unknown",
                        status=SyncStatus.FAILED,
                        last_error=str(e),
                        shopify_page_id=page.id
                    ))
            
            # Step 3: Final report
            report.sync_completed_at = datetime.utcnow()
            report.duration_seconds = (
                report.sync_completed_at - sync_started_at
            ).total_seconds()
            
            logger.info("=" * 70)
            logger.info("SYNC COMPLETED")
            logger.info("=" * 70)
            logger.info(f"Total pages: {report.total_pages}")
            logger.info(f"✅ Successful: {report.successful}")
            logger.info(f"❌ Failed: {report.failed}")
            logger.info(f"⏭️ Skipped: {report.skipped}")
            logger.info(f"⏱️ Duration: {report.duration_seconds:.2f}s")
            logger.info("=" * 70)
            
            return report
            
        except Exception as e:
            logger.error(f"FULL SYNC FAILED: {e}", exc_info=True)
            report.sync_completed_at = datetime.utcnow()
            report.duration_seconds = (
                report.sync_completed_at - sync_started_at
            ).total_seconds()
            report.errors.append(f"Full sync failed: {str(e)}")
            
            return report
    
    # ──────────────────────────────────────────────────────────────────────
    # SINGLE PAGE SYNC
    # ──────────────────────────────────────────────────────────────────────
    
    async def sync_page(self, page_id: int) -> KBSyncMetadata:
        """
        Sync a single page from Shopify to local buffer.
        
        Process:
        1. Fetch page from Shopify
        2. Parse metadata from tags
        3. Fetch translations (if any)
        4. Upsert to PostgreSQL (for each language)
        5. Invalidate Redis cache
        
        Args:
            page_id: Shopify Page ID
            
        Returns:
            KBSyncMetadata with sync result
            
        Example:
            >>> metadata = await sync_service.sync_page(123456789)
            >>> print(metadata.status)  # SUCCESS
        """
        logger.info(f"Syncing page {page_id}...")
        
        metadata = KBSyncMetadata(
            sub_intent="unknown",
            language="unknown",
            status=SyncStatus.PENDING,
            shopify_page_id=page_id
        )
        
        try:
            # Step 1: Fetch page from Shopify
            page = self.shopify.get_page_by_id(page_id)
            if not page:
                metadata.status = SyncStatus.FAILED
                metadata.last_error = "Page not found in Shopify"
                logger.error(f"Page {page_id} not found")
                return metadata
            
            # Step 2: Parse metadata from tags
            page_metadata = self.shopify.parse_kb_metadata(page)
            
            # Validate
            is_valid, error = self.metadata_parser.validate_metadata(page_metadata)
            if not is_valid:
                metadata.status = SyncStatus.FAILED
                metadata.last_error = f"Invalid metadata: {error}"
                logger.error(f"Invalid metadata for page {page_id}: {error}")
                return metadata
            
            sub_intent = page_metadata["sub_intent"]
            category = page_metadata.get("category")
            
            metadata.sub_intent = sub_intent
            metadata.category = category
            
            # Step 3: Fetch translations
            translations = self.shopify.get_page_translations(page_id)
            
            # Primary language (from page body_html)
            primary_language = "es"  # TODO: Detect from page or config
            translations[primary_language] = page.body_html
            
            # Step 4: Store each language version
            for language, content_html in translations.items():
                try:
                    # Convert HTML to Markdown (basic version)
                    # TODO: Use proper HTML→Markdown converter (markdownify, html2text)
                    content_markdown = self._html_to_markdown(content_html)
                    
                    await self._upsert_kb_content(
                        sub_intent=sub_intent,
                        language=language,
                        category=category,
                        content=content_markdown,
                        content_html=content_html,
                        title=page.title,
                        shopify_page_id=page.id,
                        shopify_url=f"https://{self.shopify.shop_url}/pages/{page.handle}",
                        shopify_handle=page.handle
                    )
                    
                    # Step 5: Invalidate Redis cache
                    await self._invalidate_cache(sub_intent, language, category)
                    
                    logger.info(
                        f"✅ Synced page {page_id} ({language}): "
                        f"{sub_intent}/{category or 'general'}"
                    )
                    
                except Exception as e:
                    logger.error(
                        f"Failed to store KB content (page {page_id}, lang {language}): {e}"
                    )
                    raise
            
            metadata.status = SyncStatus.SUCCESS
            metadata.language = primary_language
            metadata.last_synced = datetime.utcnow()
            
            return metadata
            
        except Exception as e:
            metadata.status = SyncStatus.FAILED
            metadata.last_error = str(e)
            logger.error(f"Failed to sync page {page_id}: {e}", exc_info=True)
            return metadata
    
    # ──────────────────────────────────────────────────────────────────────
    # DATABASE OPERATIONS
    # ──────────────────────────────────────────────────────────────────────
    
    async def _upsert_kb_content(
        self,
        sub_intent: str,
        language: str,
        category: Optional[str],
        content: str,
        content_html: str,
        title: Optional[str],
        shopify_page_id: int,
        shopify_url: Optional[str],
        shopify_handle: Optional[str]
    ) -> None:
        """
        Upsert KB content to PostgreSQL.
        
        Uses INSERT ... ON CONFLICT to handle both insert and update.
        """
        query = """
        INSERT INTO kb_contents (
            sub_intent,
            language,
            category,
            content,
            content_html,
            title,
            shopify_page_id,
            shopify_url,
            shopify_handle,
            last_synced
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, NOW()
        )
        ON CONFLICT (sub_intent, language, COALESCE(category, 'general'))
        DO UPDATE SET
            content = EXCLUDED.content,
            content_html = EXCLUDED.content_html,
            title = EXCLUDED.title,
            shopify_url = EXCLUDED.shopify_url,
            shopify_handle = EXCLUDED.shopify_handle,
            last_synced = NOW()
        """
        
        async with self.db.acquire() as conn:
            await conn.execute(
                query,
                sub_intent,
                language,
                category,
                content,
                content_html,
                title,
                shopify_page_id,
                shopify_url,
                shopify_handle
            )
        
        logger.debug(
            f"Upserted KB content: {sub_intent}/{language}/{category or 'general'}"
        )
    
    # ──────────────────────────────────────────────────────────────────────
    # CACHE INVALIDATION
    # ──────────────────────────────────────────────────────────────────────
    
    async def _invalidate_cache(
        self,
        sub_intent: str,
        language: str,
        category: Optional[str]
    ) -> None:
        """
        Invalidate Redis cache for specific KB content.
        
        Cache key format: "kb:{sub_intent}:{language}:{category or 'general'}"
        """
        cache_key = f"kb:{sub_intent}:{language}:{category or 'general'}"
        
        try:
            self.redis.delete(cache_key)
            logger.debug(f"Invalidated cache: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache {cache_key}: {e}")
            # Don't fail the sync if cache invalidation fails
    
    # ──────────────────────────────────────────────────────────────────────
    # WEBHOOK HANDLERS
    # ──────────────────────────────────────────────────────────────────────
    
    async def handle_page_webhook(
        self,
        page_id: int,
        topic: str
    ) -> KBSyncMetadata:
        """
        Handle Shopify page webhook.
        
        Topics:
        - pages/create: Sync new page
        - pages/update: Re-sync updated page
        - pages/delete: Remove from buffer
        
        Args:
            page_id: Shopify Page ID
            topic: Webhook topic
            
        Returns:
            KBSyncMetadata with result
        """
        logger.info(f"Handling webhook: {topic} (page {page_id})")
        
        if topic in ["pages/create", "pages/update"]:
            # Sync page
            return await self.sync_page(page_id)
        
        elif topic == "pages/delete":
            # Delete from buffer
            return await self._delete_page(page_id)
        
        else:
            logger.warning(f"Unknown webhook topic: {topic}")
            return KBSyncMetadata(
                sub_intent="unknown",
                language="unknown",
                status=SyncStatus.FAILED,
                last_error=f"Unknown topic: {topic}",
                shopify_page_id=page_id
            )
    
    async def _delete_page(self, page_id: int) -> KBSyncMetadata:
        """Delete page from buffer (webhook: pages/delete)."""
        logger.info(f"Deleting page {page_id} from buffer...")
        
        try:
            query = """
            DELETE FROM kb_contents
            WHERE shopify_page_id = $1
            RETURNING sub_intent, language, category
            """
            
            async with self.db.acquire() as conn:
                rows = await conn.fetch(query, page_id)
            
            # Invalidate cache for each deleted row
            for row in rows:
                await self._invalidate_cache(
                    row["sub_intent"],
                    row["language"],
                    row["category"]
                )
            
            logger.info(f"Deleted {len(rows)} KB content records for page {page_id}")
            
            return KBSyncMetadata(
                sub_intent="deleted",
                language="n/a",
                status=SyncStatus.SUCCESS,
                shopify_page_id=page_id
            )
            
        except Exception as e:
            logger.error(f"Failed to delete page {page_id}: {e}")
            return KBSyncMetadata(
                sub_intent="deleted",
                language="n/a",
                status=SyncStatus.FAILED,
                last_error=str(e),
                shopify_page_id=page_id
            )
    
    # ──────────────────────────────────────────────────────────────────────
    # UTILITY METHODS
    # ──────────────────────────────────────────────────────────────────────
    
    def _html_to_markdown(self, html: str) -> str:
        """
        Convert HTML to Markdown (basic version).
        
        TODO: Use proper library like markdownify or html2text for production.
        
        For now, this is a simple placeholder that strips HTML tags.
        """
        import re
        
        # Remove script and style tags completely
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        
        # Convert common tags
        html = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n', html, flags=re.DOTALL)
        html = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n', html, flags=re.DOTALL)
        html = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n', html, flags=re.DOTALL)
        html = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', html, flags=re.DOTALL)
        html = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', html, flags=re.DOTALL)
        html = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', html, flags=re.DOTALL)
        html = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', html, flags=re.DOTALL)
        html = re.sub(r'<br\s*/?>', '\n', html)
        html = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html, flags=re.DOTALL)
        
        # Remove remaining HTML tags
        html = re.sub(r'<[^>]+>', '', html)
        
        # Clean up whitespace
        html = re.sub(r'\n\n\n+', '\n\n', html)
        html = html.strip()
        
        return html


# ══════════════════════════════════════════════════════════════════════════
# BACKGROUND SYNC JOB
# ══════════════════════════════════════════════════════════════════════════

class KBBackgroundSyncJob:
    """
    Background job to periodically sync KB content from Shopify.
    
    Runs every X minutes (configurable).
    Provides fallback to webhooks (in case webhook fails).
    """
    
    def __init__(
        self,
        sync_service: ShopifyKBSyncService,
        interval_minutes: int = 5
    ):
        """
        Initialize background sync job.
        
        Args:
            sync_service: Configured sync service
            interval_minutes: Sync interval in minutes
        """
        self.sync_service = sync_service
        self.interval_minutes = interval_minutes
        self.running = False
        self.task: Optional[asyncio.Task] = None
        
        logger.info(f"KBBackgroundSyncJob initialized (interval={interval_minutes}min)")
    
    async def start(self) -> None:
        """Start background sync job."""
        if self.running:
            logger.warning("Background sync job already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._run())
        logger.info("Background sync job started")
    
    async def stop(self) -> None:
        """Stop background sync job."""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Background sync job stopped")
    
    async def _run(self) -> None:
        """Run sync loop."""
        while self.running:
            try:
                logger.info("Starting periodic KB sync...")
                report = await self.sync_service.sync_all_pages()
                
                logger.info(
                    f"Periodic sync completed: {report.successful}/{report.total_pages} "
                    f"successful in {report.duration_seconds:.1f}s"
                )
                
            except Exception as e:
                logger.error(f"Periodic sync failed: {e}", exc_info=True)
            
            # Sleep until next sync
            await asyncio.sleep(self.interval_minutes * 60)
