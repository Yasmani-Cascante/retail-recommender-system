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
Version: M3 - Distributed Locking

Changelog:
- H1: Structured Logging Migration
- M1: Configurable concurrency (asyncio.Semaphore)
- M2: Prometheus Metrics
- M3: Distributed Locking via Redis (cross-instance race condition prevention)
"""

import os
import structlog  # ✅ H1: Structured Logging Migration
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4
import asyncpg
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.api.core.redis_service import RedisService

# ✅ M3: Import DistributedLockError para manejo tipado del timeout de lock
# Se importa aqui para que sea visible en el tipo hint y el manejo de errores.
# Si redis_service no esta disponible en runtime, el import falla silenciosamente
# porque RedisService se importa bajo TYPE_CHECKING (solo para type hints).
try:
    from src.api.core.redis_service import DistributedLockError
except ImportError:
    # Fallback: Definir localmente si el modulo no esta disponible
    # Esto permite que los tests unitarios que mockean redis_service
    # sigan funcionando sin necesitar el modulo real.
    class DistributedLockError(Exception):  # type: ignore[no-redef]
        """Fallback local de DistributedLockError para entornos sin Redis."""
        pass

from src.api.integrations.shopify_kb_client import ShopifyKBClient, KBMetadataParser
from src.api.core.models.kb_models import (
    ShopifyPage,
    KBContent,
    KBContentCreate,
    KBSyncMetadata,
    KBSyncReport,
    SyncStatus
)

from src.api.core.prometheus_metrics import (
    kb_sync_operations_total,
    kb_sync_duration_seconds,
    kb_sync_semaphore_size
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
        
        # ✅ M1 OPTIMIZATION: Configurable concurrency via environment variable
        # Default: 1 (safe, proven behavior from production)
        # Recommended: 5-10 depending on DB pool size (see M1 analysis)
        # Max safe: pool_size - 2 (reserve connections for other operations)
        import os
        semaphore_size = int(os.getenv("KB_SYNC_SEMAPHORE_SIZE", "1"))
        
        # Validation: Ensure positive value
        if semaphore_size < 1:
            logger.warning(
                "invalid_semaphore_size_configured",
                requested_size=semaphore_size,
                fallback_size=1,
                reason="must_be_positive_integer"
            )
            semaphore_size = 1
        
        # Validation: Warn if value seems too high (potential connection pool exhaustion)
        if semaphore_size > 15:
            logger.warning(
                "high_semaphore_size_configured",
                configured_size=semaphore_size,
                recommendation="verify_db_pool_size",
                max_safe_value="pool_size_minus_2"
            )
        
        self._db_semaphore = asyncio.Semaphore(semaphore_size)
        
        # ✅ M1+M2: Track semaphore size in Prometheus
        try:
            from src.api.core.prometheus_metrics import kb_sync_semaphore_size
            kb_sync_semaphore_size.set(semaphore_size)
            logger.debug(
                "prometheus_metric_set",
                metric="kb_sync_semaphore_size",
                value=semaphore_size
            )
        except ImportError:
            logger.debug("prometheus_metrics_not_available", metric="kb_sync_semaphore_size")
        
        # ✅ M3: Feature flag para Distributed Locking
        # Permite activar/desactivar el distributed lock via variable de entorno.
        # Esto facilita el rollback instantaneo sin redeploy si hay problemas.
        #
        # Para activar:    KB_DISTRIBUTED_LOCKS=true
        # Para desactivar: KB_DISTRIBUTED_LOCKS=false  (comportamiento pre-M3)
        #
        # CUANDO USAR:
        # - Staging/Prod con multiples instancias Cloud Run: true
        # - Instancia unica o tests: false (semáforo local es suficiente)
        self._use_distributed_locks = os.getenv("KB_DISTRIBUTED_LOCKS", "false").lower() in (
            "true", "1", "yes", "on"
        )

        # ✅ M4: Lista de idiomas configurados para sincronización incremental (webhooks).
        #
        # sync_single_page() usa esta lista para saber qué idiomas iterar al hacer
        # fetch y upsert de cada traducción. Se configura via env var para flexibilidad
        # sin necesidad de redeploy al agregar un mercado nuevo.
        #
        # Variable: KB_SYNC_LANGUAGES (comma-separated)
        # Default:  "es,en"  (español = idioma base, inglés = traducción principal)
        # Ejemplo:  KB_SYNC_LANGUAGES=es,en,pt,fr
        #
        # NOTA: El idioma base ("es") debe incluirse siempre. Es el contenido original
        # de Shopify que se sincroniza en sync_page() como default_language.
        raw_languages = os.getenv("KB_SYNC_LANGUAGES", "es,en")
        self._configured_languages: List[str] = [
            lang.strip() for lang in raw_languages.split(",") if lang.strip()
        ]

        # ✅ H1: Structured logging for initialization with M1+M2+M3+M4 metrics
        logger.info(
            "service_initialized",
            service="ShopifyKBSyncService",
            max_concurrent_syncs=semaphore_size,
            semaphore_size=semaphore_size,
            configured_via="env_var" if os.getenv("KB_SYNC_SEMAPHORE_SIZE") else "default",
            distributed_locks_enabled=self._use_distributed_locks,
            optimization_phase="M1+M2+M3+M4",
            configured_languages=self._configured_languages,
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
            
            # ✅ M2: Track en Prometheus
            try:
                from src.api.core.prometheus_metrics import (
                    kb_sync_operations_total,
                    kb_sync_duration_seconds
                )
                kb_sync_operations_total.labels(status="success").inc()
                kb_sync_duration_seconds.observe(report.duration_seconds)
                logger.debug(
                    "prometheus_metrics_recorded",
                    operation="kb_sync",
                    status="success",
                    duration_seconds=round(report.duration_seconds, 2)
                )
            except ImportError:
                logger.debug("prometheus_metrics_not_available", operation="kb_sync")

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
            
            # ✅ M2: Track failure en Prometheus
            try:
                from src.api.core.prometheus_metrics import kb_sync_operations_total
                kb_sync_operations_total.labels(status="failed").inc()
                logger.debug(
                    "prometheus_metric_recorded",
                    operation="kb_sync",
                    status="failed"
                )
            except ImportError:
                logger.debug("prometheus_metrics_not_available", operation="kb_sync_failure")
            
            return report
    

    async def sync_single_page(self, page_id: int) -> dict:
        """
        ✅ M4 — Sincroniza una única página de Shopify a la KB.

        Punto de entrada para el incremental sync disparado por webhooks.
        Reemplaza sync_all_pages() para actualizaciones individuales, logrando
        latencia <400ms en lugar de ~10s del full sync.

        ESTRATEGIA DE SINCRONIZACIÓN:
        ─────────────────────────────
        1. Fetch de la página por ID (get_page_by_id, async via asyncio.to_thread)
        2. Fetch de metafields para validar que sea una página KB
        3. Fetch de todas las traducciones disponibles vía get_page_translations()
        4. Para cada idioma configurado (KB_SYNC_LANGUAGES):
           - Si hay traduccion: usar traduccion
           - Si no: usar contenido original (fallback seguro)
        5. Upsert en PostgreSQL (protegido por M3 distributed_lock si aplica)
        6. Retornar resumen con idiomas sincronizados y errores

        INTEGRACIÓN CON FASES PREVIAS:
        ─────────────────────────────────
        - M1 (Semáforo): _upsert_kb_content usa self._db_semaphore internamente
        - M3 (Distributed Lock): _upsert_kb_content usa distributed_lock si KB_DISTRIBUTED_LOCKS=true
        - M4 (Webhooks): Este método es el corazón del incremental sync

        Args:
            page_id: ID numérico de la página Shopify a sincronizar.

        Returns:
            dict con resultado de la operación:
            {
                "status": "synced" | "partial" | "skipped" | "error",
                "page_id": int,
                "handle": str,
                "languages_synced": [str, ...],
                "errors": [{"language": str, "error": str}, ...]
            }

        Raises:
            ValueError: Si page_id no existe en Shopify.
        """
        logger.info("sync_single_page_started", page_id=page_id)

        # ── PASO 1: Fetch página desde Shopify ────────────────────────────────
        # get_page_by_id() es síncrono (usa _make_request_with_retry internamente).
        # asyncio.to_thread() lo ejecuta en un thread pool para no bloquear el event loop.
        page = await asyncio.to_thread(self.shopify.get_page_by_id, page_id)

        if not page:
            # La página no existe o fue eliminada en Shopify
            logger.warning("sync_single_page_not_found", page_id=page_id)
            raise ValueError(f"Page {page_id} not found in Shopify")

        # ── PASO 2: Fetch y validar metafields KB ─────────────────────────────
        # get_page_metafields() ya es async y retorna {"custom.kb_metadata": {...}}
        metafields = await self.shopify.get_page_metafields(page_id)
        kb_metadata = metafields.get("custom.kb_metadata", {})

        if not kb_metadata or not kb_metadata.get("sub_intent"):
            # Página existe pero no es una página KB (sin metafield necesario)
            logger.info(
                "sync_single_page_skipped_no_kb_metadata",
                page_id=page_id,
                handle=page.handle,
                reason="missing_custom_kb_metadata_or_sub_intent",
            )
            return {
                "status": "skipped",
                "page_id": page_id,
                "handle": page.handle,
                "reason": "no_kb_metadata",
                "languages_synced": [],
                "errors": [],
            }

        sub_intent: str = kb_metadata["sub_intent"]
        category: Optional[str] = kb_metadata.get("category")
        # El idioma base del contenido original almacenado en Shopify (ej. "es")
        default_language: str = kb_metadata.get("language", "es")

        # URL canónica de la página en Shopify
        shopify_url = f"https://{self.shopify.shop_url}/pages/{page.handle}"

        # ── PASO 3: Fetch de todas las traducciones disponibles en una sola llamada ──
        # get_page_translations() devuelve {locale: html_string, ...}.
        # Incluye solo locales con traducción activa; no incluye el idioma base.
        try:
            translations: Dict[str, str] = await self.shopify.get_page_translations(page_id)
        except Exception as e:
            logger.warning(
                "sync_single_page_translations_fetch_failed",
                page_id=page_id,
                error=str(e),
                fallback="using_original_content_only",
            )
            translations = {}

        # ── PASO 4: Sincronizar cada idioma configurado ───────────────────────
        # self._configured_languages viene de KB_SYNC_LANGUAGES env var.
        # Ejemplo: ["es", "en"] cuando KB_SYNC_LANGUAGES="es,en"
        synced_languages: List[str] = []
        errors: List[Dict] = []

        for language in self._configured_languages:
            try:
                if language == default_language:
                    # ── Idioma base: contenido original de Shopify ─────────────
                    html_content = page.body_html or ""
                    title = page.title
                else:
                    # ── Idioma de traducción ───────────────────────────────────
                    # Si Shopify no tiene traducción, usamos el contenido original
                    # como fallback (mejor tener contenido en idioma incorrecto
                    # que no tener contenido para esa entrada KB).
                    html_content = translations.get(language, page.body_html or "")

                    # Fetch título traducido (retorna None si no existe → fallback al original)
                    try:
                        translated_title = await self.shopify.get_page_title_translation(
                            page_id, language
                        )
                        title = translated_title if translated_title else page.title
                    except Exception:
                        # Fallo en fetch de título no debe cancelar el sync del contenido
                        title = page.title

                # Convertir HTML a Markdown para almacenamiento en KB
                markdown_content = self._html_to_markdown(html_content)

                # Upsert en PostgreSQL.
                # Aplica M1 (semáforo local) + M3 (distributed_lock) internamente.
                await self._upsert_kb_content(
                    sub_intent=sub_intent,
                    language=language,
                    category=category,
                    content=markdown_content,
                    content_html=html_content,
                    title=title,
                    shopify_page_id=page_id,
                    shopify_url=shopify_url,
                    shopify_handle=page.handle,
                )

                synced_languages.append(language)

                logger.info(
                    "sync_single_page_language_synced",
                    page_id=page_id,
                    language=language,
                    sub_intent=sub_intent,
                    category=category,
                )

            except Exception as e:
                logger.error(
                    "sync_single_page_language_error",
                    page_id=page_id,
                    language=language,
                    sub_intent=sub_intent,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                errors.append({"language": language, "error": str(e)})

        # ── PASO 5: Construir y retornar resultado ────────────────────────────
        if not errors:
            status = "synced"
        elif synced_languages:
            status = "partial"  # Algunos idiomas OK, algunos fallaron
        else:
            status = "error"    # Todos los idiomas fallaron

        result = {
            "status": status,
            "page_id": page_id,
            "handle": page.handle,
            "sub_intent": sub_intent,
            "languages_synced": synced_languages,
            "errors": errors,
        }

        logger.info(
            "sync_single_page_completed",
            page_id=page_id,
            status=status,
            languages_count=len(synced_languages),
            errors_count=len(errors),
        )

        return result


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
        """
        ✅ M3 - Upsert KB content con Distributed Locking + retry logic.

        ESTRATEGIA DE CONCURRENCIA (dos capas complementarias):

        Capa 1 - asyncio.Semaphore (intra-instancia):
            Limita cuantas coroutines dentro de la MISMA instancia pueden
            hacer operaciones de DB simultaneamente.
            Evita: pool exhaustion en una sola instancia.

        Capa 2 - Redis Distributed Lock (cross-instance, M3):
            Solo UNA instancia puede modificar el mismo registro (sub_intent +
            language + category) a la vez, sin importar cuantas instancias
            Cloud Run esten corriendo.
            Evita: race conditions que causen duplicados o datos corruptos.

        MODO DEGRADADO:
            Si KB_DISTRIBUTED_LOCKS=false o Redis no esta disponible,
            solo aplica el semaforo local (comportamiento pre-M3).

        LOCK KEY FORMAT:
            "kb_sync:lock:{sub_intent}:{language}:{normalized_category}"
            Ejemplo: "kb_sync:lock:policy_return:es:general"
            La granularidad por registro garantiza que syncs de diferentes
            sub_intents corren en paralelo (no bloquean entre si).
        """
        normalized_category = category if category is not None else 'general'

        # ✅ M3: Construir lock key unico por registro de KB
        # Formato: kb_sync:lock:{sub_intent}:{language}:{category}
        # Esto garantiza que solo se bloquea el acceso al mismo registro exacto,
        # no a todos los registros de un sub_intent o idioma.
        lock_key = f"kb_sync:lock:{sub_intent}:{language}:{normalized_category}"

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

        max_retries = 3
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                # ── CAPA 1: Semaforo local (intra-instancia) ──────────────────
                # Controla cuantas goroutines en ESTA instancia entran al bloque
                # de DB al mismo tiempo. Se adquiere primero para no agotar
                # las conexiones del pool mientras se espera el lock de Redis.
                async with self._db_semaphore:

                    if self._use_distributed_locks:
                        # ── CAPA 2 (M3): Distributed lock cross-instance ──────
                        # Solo una instancia de Cloud Run puede ejecutar el upsert
                        # para este (sub_intent, language, category) a la vez.
                        # Si el lock no se obtiene en blocking_timeout segundos,
                        # DistributedLockError es capturada en el except abajo
                        # y se hace retry con backoff exponencial.
                        async with self.redis.distributed_lock(
                            lock_name=lock_key,
                            timeout=30.0,        # TTL del lock en Redis (safety net)
                            blocking_timeout=5.0  # Espera maxima para obtener el lock
                        ):
                            async with self.db.acquire() as conn:
                                await conn.execute(
                                    query, sub_intent, language, normalized_category,
                                    content, content_html, title,
                                    shopify_page_id, shopify_url, shopify_handle
                                )
                                logger.debug(
                                    "kb_content_upserted",
                                    sub_intent=sub_intent,
                                    language=language,
                                    category=normalized_category,
                                    shopify_page_id=shopify_page_id,
                                    distributed_lock_used=True  # ✅ M3: Trazabilidad
                                )
                                return
                    else:
                        # ── MODO LEGACY (pre-M3): Solo semaforo local ───────
                        # Comportamiento identico a M1+M2.
                        # Usado cuando KB_DISTRIBUTED_LOCKS=false (default)
                        # o cuando Redis no esta disponible.
                        async with self.db.acquire() as conn:
                            await conn.execute(
                                query, sub_intent, language, normalized_category,
                                content, content_html, title,
                                shopify_page_id, shopify_url, shopify_handle
                            )
                            logger.debug(
                                "kb_content_upserted",
                                sub_intent=sub_intent,
                                language=language,
                                category=normalized_category,
                                shopify_page_id=shopify_page_id,
                                distributed_lock_used=False  # ✅ M3: Trazabilidad
                            )
                            return

            except DistributedLockError as e:
                # ✅ M3: El lock no se pudo obtener en el tiempo limite.
                # Esto indica que otra instancia esta procesando el mismo registro.
                # Politica: retry con backoff exponencial (igual que deadlock).
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(
                        "kb_upsert_lock_timeout_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        lock_key=lock_key,
                        retry_delay_seconds=wait_time,
                        note="another_instance_may_be_processing_same_record"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                # Si ya agotamos retries, loguear y re-raise
                logger.error(
                    "kb_upsert_lock_timeout_exhausted",
                    sub_intent=sub_intent,
                    language=language,
                    category=normalized_category,
                    lock_key=lock_key,
                    max_retries=max_retries,
                    error=str(e)
                )
                raise

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
    
    async def delete_kb_for_page(self, page_id: int) -> dict:
        """
        ✅ M4 — Elimina todos los registros KB de una página eliminada en Shopify.

        Método PÚBLICO llamado por ShopifyWebhookHandler cuando recibe
        un webhook de topic "pages/delete".

        Delega a _delete_page() (implementación interna) y convierte
        KBSyncMetadata en un dict más conveniente para el handler.

        Args:
            page_id: ID de la página Shopify eliminada

        Returns:
            dict con resultado:
            {
                "status": "deleted" | "error",
                "page_id": int,
                "records_deleted": int,   # Número de filas eliminadas en DB
            }
        """
        metadata = await self._delete_page(page_id)

        if metadata.status == SyncStatus.SUCCESS:
            return {
                "status": "deleted",
                "page_id": page_id,
                # _delete_page() no retorna conteo directamente; el log lo captura.
                # Ponemos 0 como placeholder — el log estructurado tiene el conteo real.
                "records_deleted": 0,
            }
        else:
            return {
                "status": "error",
                "page_id": page_id,
                "error": metadata.last_error,
            }

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
    Background job para sincronizar KB content desde Shopify periódicamente.

    ESTRATEGIA M4 — POLLING INCREMENTAL POR updated_at
    ─────────────────────────────────────────────────────
    Dado que Shopify NO soporta webhooks para el recurso Pages (investigado
    Feb 2026), este job implementa la alternativa: polling inteligente.

    En lugar de hacer full sync cada ciclo (descarga TODAS las páginas),
    compara el timestamp del último sync exitoso contra el campo updated_at
    de cada página en Shopify. Solo sincroniza las que cambiaron.

    VENTAJAS vs. full sync:
    - Full sync: descarga N páginas × metafields + traducciones cada 5 min
    - Incremental: en ciclos sin cambios, 0 páginas procesadas (1 llamada API)
    - Latencia: 0 a KB_SYNC_INTERVAL_MINUTES (default: 5 min)
    - Para contenido KB (políticas, FAQ) esta latencia es completamente aceptable.

    FLUJO:
    1. Primer ciclo: full sync (establece baseline)
    2. Ciclos siguientes: get_pages() → filtrar páginas donde updated_at > last_sync
    3. Para cada página modificada: sync_single_page() (ya implementado, M4)
    """
    
    def __init__(
        self,
        sync_service: ShopifyKBSyncService,
        interval_minutes: int = 5
    ):
        """
        Inicializa el background sync job con soporte de polling incremental.

        Args:
            sync_service: Servicio de sync configurado (ShopifyKBSyncService)
            interval_minutes: Intervalo entre ciclos de polling en minutos.
                              Configurable vía KB_SYNC_INTERVAL_MINUTES.
        """
        self.sync_service = sync_service
        self.interval_minutes = interval_minutes
        self.running = False
        self.task: Optional[asyncio.Task] = None

        # ── Estado del polling incremental ───────────────────────────────────
        # _last_sync_at: Timestamp del último sync EXITOSO.
        # Inicialmente None → primer ciclo hace full sync para establecer
        # el baseline. Ciclos posteriores usan este timestamp para filtrar
        # solo páginas modificadas después de él.
        self._last_sync_at: Optional[datetime] = None

        # ── Contadores de estadísticas para observabilidad ─────────────────
        self._total_cycles: int = 0           # Ciclos ejecutados
        self._incremental_cycles: int = 0     # Ciclos incrementales (no full)
        self._full_sync_cycles: int = 0       # Ciclos de full sync
        self._pages_synced_total: int = 0     # Páginas sincronizadas acumuladas

        logger.info(
            "background_sync_job_initialized",
            service="KBBackgroundSyncJob",
            interval_minutes=interval_minutes,
            strategy="incremental_polling_by_updated_at",
            note="shopify_pages_webhooks_not_supported",
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
        """
        Loop principal de sync con estrategia incremental por updated_at.

        CICLO 1 (primer arranque):
            self._last_sync_at is None → full sync (sync_all_pages)
            Establece baseline y guarda el timestamp en self._last_sync_at

        CICLOS 2+ (incrementales):
            1. get_pages() → lista de TODAS las páginas de Shopify (solo metadata)
            2. Filtrar las que tienen updated_at > self._last_sync_at
            3. Para cada página modificada: sync_single_page(page_id)
            4. Si no hay cambios: 0 operaciones de DB (solo 1 llamada API)

        NOTA SOBRE EFICIENCIA:
            get_pages() descarga metadata de todas las páginas (sin body_html).
            La Shopify Pages API no tiene filtro ?updated_at_min= en la versión
            REST actual, por lo que la comparación se hace del lado del cliente.
            Con 50-100 páginas, este enfoque es completamente viable.
            Si el catálogo crece a 1000+ páginas, considerar GraphQL con cursor.
        """
        while self.running:
            cycle_start = datetime.utcnow()
            self._total_cycles += 1

            try:
                is_first_cycle = self._last_sync_at is None

                if is_first_cycle:
                    # ── FULL SYNC (solo primer ciclo) ────────────────────────
                    logger.info(
                        "kb_sync_cycle_started",
                        cycle=self._total_cycles,
                        mode="full_sync",
                        reason="first_cycle_or_no_previous_timestamp",
                    )
                    self._full_sync_cycles += 1

                    report = await self.sync_service.sync_all_pages()
                    self._pages_synced_total += report.successful

                    # Guardar timestamp solo si el sync fue exitoso
                    if report.successful > 0 or report.total_pages == 0:
                        self._last_sync_at = cycle_start

                    logger.info(
                        "kb_sync_cycle_completed",
                        cycle=self._total_cycles,
                        mode="full_sync",
                        successful=report.successful,
                        total_pages=report.total_pages,
                        failed=report.failed,
                        duration_seconds=round(report.duration_seconds, 1),
                        last_sync_at=self._last_sync_at.isoformat() if self._last_sync_at else None,
                    )

                else:
                    # ── POLLING INCREMENTAL (ciclos 2+) ─────────────────────
                    logger.info(
                        "kb_sync_cycle_started",
                        cycle=self._total_cycles,
                        mode="incremental",
                        since=self._last_sync_at.isoformat(),
                    )
                    self._incremental_cycles += 1

                    # Paso 1: Obtener lista de páginas (sin body_html para ser liviano)
                    all_pages_raw = await self.sync_service.shopify.get_pages()

                    # Paso 2: Filtrar las modificadas desde el último sync
                    # updated_at viene como string ISO de Shopify: "2026-02-27T18:00:00-05:00"
                    changed_pages = []
                    for page_data in all_pages_raw:
                        updated_at_str = page_data.get("updated_at")
                        if not updated_at_str:
                            continue
                        try:
                            # Parsear timestamp de Shopify (puede tener offset de zona horaria)
                            # Normalizamos a UTC para comparación consistente
                            from datetime import timezone
                            updated_at = datetime.fromisoformat(
                                updated_at_str.replace("Z", "+00:00")
                            ).astimezone(timezone.utc).replace(tzinfo=None)

                            if updated_at > self._last_sync_at:
                                changed_pages.append(page_data)
                        except (ValueError, TypeError) as e:
                            # No bloquear el ciclo por un timestamp malformado
                            logger.warning(
                                "kb_sync_timestamp_parse_error",
                                page_id=page_data.get("id"),
                                updated_at_str=updated_at_str,
                                error=str(e),
                            )
                            continue

                    pages_synced = 0
                    errors = 0

                    if not changed_pages:
                        # Sin cambios: ciclo sin trabajo (el más común en producción)
                        logger.info(
                            "kb_sync_cycle_no_changes",
                            cycle=self._total_cycles,
                            total_pages_checked=len(all_pages_raw),
                            since=self._last_sync_at.isoformat(),
                        )
                    else:
                        logger.info(
                            "kb_sync_incremental_changes_detected",
                            changed_pages=len(changed_pages),
                            total_pages_checked=len(all_pages_raw),
                            page_ids=[p.get("id") for p in changed_pages],
                        )

                        # Paso 3: Sincronizar cada página modificada
                        for page_data in changed_pages:
                            page_id = page_data.get("id")
                            if not page_id:
                                continue
                            try:
                                result = await self.sync_service.sync_single_page(page_id)
                                if result["status"] in ("synced", "partial"):
                                    pages_synced += 1
                            except Exception as e:
                                logger.error(
                                    "kb_sync_incremental_page_error",
                                    page_id=page_id,
                                    error=str(e),
                                    error_type=type(e).__name__,
                                )
                                errors += 1

                    self._pages_synced_total += pages_synced

                    # Avanzar el cursor solo si el ciclo terminó sin error crítico
                    self._last_sync_at = cycle_start

                    duration = (datetime.utcnow() - cycle_start).total_seconds()
                    logger.info(
                        "kb_sync_cycle_completed",
                        cycle=self._total_cycles,
                        mode="incremental",
                        pages_checked=len(all_pages_raw),
                        pages_changed=len(changed_pages),
                        pages_synced=pages_synced,
                        errors=errors,
                        duration_seconds=round(duration, 1),
                        total_pages_synced_all_time=self._pages_synced_total,
                    )

            except Exception as e:
                # Error inesperado: no avanzar self._last_sync_at para que
                # el siguiente ciclo reintente desde el mismo punto.
                logger.error(
                    "kb_sync_cycle_failed",
                    cycle=self._total_cycles,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                    note="last_sync_timestamp_not_advanced",
                )

            # Dormir hasta el siguiente ciclo
            await asyncio.sleep(self.interval_minutes * 60)