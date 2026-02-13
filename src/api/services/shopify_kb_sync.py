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
Version: H1 - Structured Logging Migration
"""

import structlog  # ✅ H1: Structured Logging Migration
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4
import asyncpg
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.api.core.redis_service import RedisService

from src.api.integrations.shopify_kb_client import ShopifyKBClient, KBMetadataParser
from src.api.core.models.kb_models import (
    ShopifyPage,
    KBContent,
    KBContentCreate,
    KBSyncMetadata,
    KBSyncReport,
    SyncStatus
)

logger = structlog.get_logger(__name__)  # ✅ H1: Structured Logging Migration


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
        redis_service=redis_service
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
        redis_service: 'RedisService'
    ):
        """
        Initialize sync service.
        
        Args:
            shopify_client: Configured Shopify KB client
            db_pool: AsyncPG database connection pool
            redis_service: Redis ASYNC service (for cache invalidation)
        """
        self.shopify = shopify_client
        self.db = db_pool
        self.redis = redis_service
        self.metadata_parser = KBMetadataParser()
        
        # ✅ FIX: Semaphore to prevent race conditions
        # Limit concurrent DB operations to avoid lock conflicts
        self._db_semaphore = asyncio.Semaphore(1)  # Max 1 concurrent DB write
        
        # ✅ H1: Structured logging for initialization
        logger.info(
            "service_initialized",
            service="ShopifyKBSyncService",
            max_concurrent_syncs=1,
            semaphore_size=1
        )
    
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
        # ✅ H1: Pretty logs para humans (mantener UX)
        logger.info("=" * 70)
        logger.info("Starting FULL SYNC of KB pages from Shopify")
        logger.info("=" * 70)
        
        sync_started_at = datetime.utcnow()
        
        # ✅ H1: Structured event
        logger.info(
            "kb_sync_started",
            sync_type="full",
            validate_metadata=validate_metadata,
            started_at=sync_started_at.isoformat()
        )
        
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
            logger.info(
                "kb_sync_fetching_pages",
                step=1,
                step_name="fetch_pages_from_shopify"
            )
            kb_pages = await self.shopify.get_kb_pages(validate_metadata=validate_metadata)
            
            report.total_pages = len(kb_pages)
            
            # ✅ H1: Structured logging
            logger.info(
                "kb_pages_found",
                total_pages=report.total_pages
            )
            
            if report.total_pages == 0:
                # ✅ H1: Structured warning
                logger.warning(
                    "kb_pages_not_found",
                    source="shopify",
                    total_pages=0
                )
                report.sync_completed_at = datetime.utcnow()
                report.duration_seconds = (
                    report.sync_completed_at - sync_started_at
                ).total_seconds()
                return report
            
            # Step 2: Sync each page IN PARALLEL
            logger.info(
                "kb_sync_processing_pages",
                step=2,
                step_name="sync_to_buffer",
                execution_mode="parallel"
            )
            
            # ✨ OPTIMIZATION: Process all pages in parallel
            sync_tasks = []
            for i, (page, metafields) in enumerate(kb_pages, 1):
                # ✅ H1: Structured logging para cada página
                logger.info(
                    "page_queued_for_sync",
                    page_index=i,
                    total_pages=report.total_pages,
                    page_id=page.id,
                    page_title=page.title
                )
                sync_tasks.append(self.sync_page(page, metafields))
            
            # Execute all syncs in parallel
            logger.info(
                "kb_sync_tasks_executing",
                total_tasks=len(sync_tasks),
                execution_mode="parallel"
            )
            sync_results = await asyncio.gather(*sync_tasks, return_exceptions=True)
            
            # Process results
            for i, (page, result) in enumerate(zip([p for p, _ in kb_pages], sync_results), 1):
                try:
                    if isinstance(result, Exception):
                        # ✅ H1: Structured error logging
                        logger.error(
                            "page_sync_failed",
                            page_id=page.id,
                            error=str(result),
                            error_type=type(result).__name__
                        )
                        report.failed += 1
                        report.errors.append(f"Page {page.id}: {str(result)}")
                        
                        # Add failed metadata
                        report.details.append(KBSyncMetadata(
                            sub_intent="unknown",
                            language="unknown",
                            status=SyncStatus.FAILED,
                            last_error=str(result),
                            shopify_page_id=page.id
                        ))
                    else:
                        metadata = result
                        
                        if metadata.status == SyncStatus.SUCCESS:
                            report.successful += 1
                        elif metadata.status == SyncStatus.FAILED:
                            report.failed += 1
                            report.errors.append(metadata.last_error or "Unknown error")
                        else:
                            report.skipped += 1
                        
                        report.details.append(metadata)
                
                except Exception as e:
                    # ✅ H1: Structured error
                    logger.error(
                        "page_result_processing_error",
                        page_id=page.id,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    report.failed += 1
                    report.errors.append(f"Page {page.id}: {str(e)}")
            
            # Step 3: Final report
            report.sync_completed_at = datetime.utcnow()
            report.duration_seconds = (
                report.sync_completed_at - sync_started_at
            ).total_seconds()
            
            # ✅ H1: Pretty logs para humans
            logger.info("=" * 70)
            logger.info("SYNC COMPLETED")
            logger.info("=" * 70)
            
            # ✅ H1: Structured metrics para machines
            logger.info(
                "kb_sync_completed",
                total_pages=report.total_pages,
                successful=report.successful,
                failed=report.failed,
                skipped=report.skipped,
                duration_seconds=round(report.duration_seconds, 2),
                success_rate=round(
                    (report.successful / report.total_pages * 100) 
                    if report.total_pages > 0 else 0, 
                    1
                ),
                pages_per_second=round(
                    report.total_pages / report.duration_seconds, 
                    2
                ) if report.duration_seconds > 0 else 0
            )
            
            logger.info("=" * 70)
            
            return report
            
        except Exception as e:
            # ✅ H1: Structured error logging
            logger.error(
                "kb_sync_failed",
                sync_type="full",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            report.sync_completed_at = datetime.utcnow()
            report.duration_seconds = (
                report.sync_completed_at - sync_started_at
            ).total_seconds()
            report.errors.append(f"Full sync failed: {str(e)}")
            
            return report
    
    # ──────────────────────────────────────────────────────────────────────
    # SINGLE PAGE SYNC
    # ──────────────────────────────────────────────────────────────────────
    
    async def sync_page(
        self, 
        page: ShopifyPage, 
        metafields: Dict[str, Any]
    ) -> KBSyncMetadata:
        """
        Sync a single page with ALL its translations to PostgreSQL.
        
        Args:
            page: ShopifyPage object
            metafields: Metafields dict from get_page_metafields()
            
        Returns:
            KBSyncMetadata with sync status
        """
        try:
            # Extract KB metadata from metafields
            kb_metadata = metafields.get("custom.kb_metadata", {})
            
            if not kb_metadata:
                # ✅ H1: Structured error
                logger.error(
                    "page_missing_metadata",
                    page_id=page.id,
                    missing_field="kb_metadata",
                    page_title=page.title if hasattr(page, 'title') else None
                )
                return KBSyncMetadata(
                    sub_intent="unknown",
                    language="unknown",
                    status=SyncStatus.FAILED,
                    last_error="Missing kb_metadata metafield",
                    shopify_page_id=page.id
                )
            
            # Extract fields
            sub_intent = kb_metadata.get("sub_intent")
            category = kb_metadata.get("category")
            default_language = kb_metadata.get("language", "es")
            
            if not sub_intent:
                # ✅ H1: Structured error
                logger.error(
                    "page_invalid_metadata",
                    page_id=page.id,
                    validation_error="missing_sub_intent",
                    required_field="sub_intent"
                )
                return KBSyncMetadata(
                    sub_intent="unknown",
                    language=default_language,
                    status=SyncStatus.FAILED,
                    last_error="Missing sub_intent",
                    shopify_page_id=page.id
                )
            
            # ══════════════════════════════════════════════════════════════
            # STEP 1: Sync DEFAULT LANGUAGE (original content)
            # ══════════════════════════════════════════════════════════════
            markdown_content = self._html_to_markdown(page.body_html or "")
        
            await self._upsert_kb_content(
                sub_intent=sub_intent,
                language=default_language,
                category=category,
                content=markdown_content,
                content_html=page.body_html,
                title=page.title,
                shopify_page_id=page.id,
                shopify_url=f"https://{self.shopify.shop_url}/pages/{page.handle}",
                shopify_handle=page.handle
            )
            
            await self._invalidate_cache(sub_intent, default_language, category)
            
            # ✅ H1: Structured logging
            logger.info(
                "page_default_language_synced",
                page_id=page.id,
                language=default_language,
                sub_intent=sub_intent,
                category=category
            )
            
            # ══════════════════════════════════════════════════════════════
            # STEP 2: Fetch and sync TRANSLATIONS
            # ══════════════════════════════════════════════════════════════
            
            try:
                # Fetch all translations
                translations = await self.shopify.get_page_translations(page.id)
                
                if translations:
                    # ✅ H1: Structured logging
                    logger.info(
                        "page_translations_found",
                        page_id=page.id,
                        translation_count=len(translations),
                        languages=list(translations.keys())
                    )
                    
                    # Sync each translation
                    synced_languages = [default_language]
                    
                    for locale, translated_html in translations.items():
                        # Skip default language (already synced)
                        if locale == default_language:
                            continue
                        
                        try:
                            # Convert translated HTML to Markdown
                            translated_markdown = self._html_to_markdown(translated_html)
                            
                            # ✅ NUEVO: Fetch translated title
                            translated_title = await self.shopify.get_page_title_translation(
                                page.id, locale
                            )
                            
                            # Fallback to original title if translation not found
                            final_title = translated_title if translated_title else page.title
                            
                            # ✅ H1: Structured logging para debugging
                            logger.debug(
                                "page_translation_title_resolved",
                                page_id=page.id,
                                locale=locale,
                                original_title=page.title,
                                translated_title=translated_title,
                                final_title=final_title,
                                used_fallback=(translated_title is None)
                            )
                            
                            # ✅ CORRECTO: Usa título traducido o fallback
                            await self._upsert_kb_content(
                                sub_intent=sub_intent,
                                language=locale,
                                category=category,
                                content=translated_markdown,
                                content_html=translated_html,
                                title=final_title,  # ✅ Título traducido o fallback
                                shopify_page_id=page.id,
                                shopify_url=f"https://{self.shopify.shop_url}/pages/{page.handle}",
                                shopify_handle=page.handle
                            )
                            
                            # Invalidate cache for this language
                            await self._invalidate_cache(sub_intent, locale, category)
                            
                            synced_languages.append(locale)
                            
                            # ✅ H1: Structured logging
                            logger.info(
                                "page_translation_synced",
                                page_id=page.id,
                                language=locale,
                                sub_intent=sub_intent,
                                category=category
                            )
                            
                        except Exception as e:
                            # ✅ H1: Structured error
                            logger.error(
                                "page_translation_sync_failed",
                                page_id=page.id,
                                language=locale,
                                error=str(e),
                                error_type=type(e).__name__
                            )
                            continue
                    
                    # ✅ H1: Structured logging para éxito total
                    logger.info(
                        "page_sync_completed",
                        page_id=page.id,
                        page_title=page.title,
                        sub_intent=sub_intent,
                        languages_synced=synced_languages,
                        translation_count=len(synced_languages)
                    )
                    
                else:
                    # ✅ H1: Structured logging
                    logger.info(
                        "page_no_translations",
                        page_id=page.id,
                        default_language=default_language,
                        translation_count=0
                    )
                    
            except Exception as e:
                # ✅ H1: Structured warning
                logger.warning(
                    "page_translations_fetch_failed",
                    page_id=page.id,
                    error=str(e),
                    fallback="default_language_only"
                )
            
            # Return success metadata
            return KBSyncMetadata(
                sub_intent=sub_intent,
                language=default_language,
                category=category,
                status=SyncStatus.SUCCESS,
                last_synced=datetime.utcnow(),
                shopify_page_id=page.id
            )
            
        except Exception as e:
            # ✅ H1: Structured error con exc_info
            logger.error(
                "page_sync_error",
                page_id=page.id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            
            return KBSyncMetadata(
                sub_intent=kb_metadata.get("sub_intent", "unknown"),
                language=kb_metadata.get("language", "unknown"),
                status=SyncStatus.FAILED,
                last_error=str(e),
                shopify_page_id=page.id
            )
    
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
        """Upsert KB content with retry logic."""
        normalized_category = category if category is not None else 'general'
        
        query = """
        INSERT INTO kb_contents (
            sub_intent, language, category, content, content_html,
            title, shopify_page_id, shopify_url, shopify_handle,
            last_synced, created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW(), NOW()
        )
        ON CONFLICT (sub_intent, language, COALESCE(category, 'general'))
        DO UPDATE SET
            content = EXCLUDED.content,
            content_html = EXCLUDED.content_html,
            title = EXCLUDED.title,
            shopify_url = EXCLUDED.shopify_url,
            shopify_handle = EXCLUDED.shopify_handle,
            last_synced = NOW(),
            updated_at = NOW()
        """
        
        # Retry logic
        max_retries = 3
        retry_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                async with self._db_semaphore:
                    async with self.db.acquire() as conn:
                        await conn.execute(
                            query, sub_intent, language, normalized_category,
                            content, content_html, title,
                            shopify_page_id, shopify_url, shopify_handle
                        )
                        # ✅ H1: Structured debug logging
                        logger.debug(
                            "kb_content_upserted",
                            sub_intent=sub_intent,
                            language=language,
                            category=normalized_category,
                            shopify_page_id=shopify_page_id
                        )
                        return
                        
            except Exception as e:
                error_msg = str(e).lower()
                
                if any(x in error_msg for x in [
                    "another operation is in progress",
                    "deadlock detected",
                    "too many connections"
                ]):
                    if attempt < max_retries - 1:
                        # ✅ H1: Structured retry warning
                        logger.warning(
                            "kb_upsert_retry",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            error=str(e),
                            retry_delay_seconds=retry_delay * (attempt + 1)
                        )
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                
                # ✅ H1: Structured error
                logger.error(
                    "kb_upsert_failed",
                    sub_intent=sub_intent,
                    language=language,
                    category=normalized_category,
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise
    
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
        
        success = await self.redis.delete(cache_key)
        if success:
            # ✅ H1: Structured debug logging
            logger.debug(
                "cache_invalidated",
                cache_key=cache_key,
                sub_intent=sub_intent,
                language=language,
                category=category or 'general'
            )
    
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
        # ✅ H1: Structured logging
        logger.info(
            "webhook_received",
            topic=topic,
            page_id=page_id
        )
        
        if topic in ["pages/create", "pages/update"]:
            # Sync page
            return await self.sync_page(page_id)
        
        elif topic == "pages/delete":
            # Delete from buffer
            return await self._delete_page(page_id)
        
        else:
            # ✅ H1: Structured warning
            logger.warning(
                "webhook_unknown_topic",
                topic=topic,
                page_id=page_id
            )
            return KBSyncMetadata(
                sub_intent="unknown",
                language="unknown",
                status=SyncStatus.FAILED,
                last_error=f"Unknown topic: {topic}",
                shopify_page_id=page_id
            )
    
    async def _delete_page(self, page_id: int) -> KBSyncMetadata:
        """Delete page from buffer (webhook: pages/delete)."""
        # ✅ H1: Structured logging
        logger.info(
            "page_deletion_started",
            page_id=page_id,
            source="webhook"
        )
        
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
            
            # ✅ H1: Structured logging
            logger.info(
                "page_deleted",
                page_id=page_id,
                records_deleted=len(rows)
            )
            
            return KBSyncMetadata(
                sub_intent="deleted",
                language="n/a",
                status=SyncStatus.SUCCESS,
                shopify_page_id=page_id
            )
            
        except Exception as e:
            # ✅ H1: Structured error
            logger.error(
                "page_deletion_failed",
                page_id=page_id,
                error=str(e),
                error_type=type(e).__name__
            )
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
        
        # ✅ H1: Structured logging
        logger.info(
            "background_sync_job_initialized",
            service="KBBackgroundSyncJob",
            interval_minutes=interval_minutes
        )
    
    async def start(self) -> None:
        """Start background sync job."""
        if self.running:
            # ✅ H1: Structured warning
            logger.warning(
                "background_sync_job_already_running",
                service="KBBackgroundSyncJob"
            )
            return
        
        self.running = True
        self.task = asyncio.create_task(self._run())
        
        # ✅ H1: Structured logging
        logger.info(
            "background_sync_job_started",
            service="KBBackgroundSyncJob",
            interval_minutes=self.interval_minutes
        )
    
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
        
        # ✅ H1: Structured logging
        logger.info(
            "background_sync_job_stopped",
            service="KBBackgroundSyncJob"
        )
    
    async def _run(self) -> None:
        """Run sync loop."""
        while self.running:
            try:
                # ✅ H1: Structured logging
                logger.info(
                    "periodic_sync_started",
                    interval_minutes=self.interval_minutes
                )
                
                report = await self.sync_service.sync_all_pages()
                
                # ✅ H1: Structured metrics
                logger.info(
                    "periodic_sync_completed",
                    successful=report.successful,
                    total_pages=report.total_pages,
                    duration_seconds=round(report.duration_seconds, 1),
                    success_rate=round(
                        (report.successful / report.total_pages * 100) 
                        if report.total_pages > 0 else 0, 
                        1
                    )
                )
                
            except Exception as e:
                # ✅ H1: Structured error
                logger.error(
                    "periodic_sync_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True
                )
            
            # Sleep until next sync
            await asyncio.sleep(self.interval_minutes * 60)