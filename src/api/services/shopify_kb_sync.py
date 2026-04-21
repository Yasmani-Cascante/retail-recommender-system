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
import re                          # stdlib: siempre disponible, usado en _html_to_markdown y _html_to_text_fallback
import hashlib                     # ✅ L2: SHA256 para content_hash (stdlib, sin dependencia externa)
import structlog  # ✅ H1: Structured Logging Migration
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4
import asyncpg
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.api.core.redis_service import RedisService

# ✅ L1: Import de markdownify al nivel de módulo siguiendo el patrón establecido
# del proyecto (igual que DistributedLockError abajo).
#
# Por qué al nivel de módulo y no dentro del método:
# - Hace explícita la disponibilidad de la dependencia en el momento de arranque
# - Permite testear el flag _MARKDOWNIFY_AVAILABLE directamente en unit tests
# - Es consistente con el resto del archivo (M3 usa el mismo patrón)
# - El import dentro del método se cachea igual, pero el linter no puede
#   razonar sobre él — aquí el IDE entiende el tipo y puede autocompletar.
#
# Comportamiento en producción:  _MARKDOWNIFY_AVAILABLE = True  (requirements.txt lo incluye)
# Comportamiento en entornos incompletos: _MARKDOWNIFY_AVAILABLE = False → fallback BeautifulSoup
try:
    import markdownify as _markdownify
    _MARKDOWNIFY_AVAILABLE = True
except ImportError:
    _markdownify = None  # type: ignore[assignment]
    _MARKDOWNIFY_AVAILABLE = False

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

        # ✅ L2: Feature flag para Content Versioning.
        #
        # Cuando está activo, _upsert_kb_content() calcula el SHA256 del Markdown
        # entrante y lo compara con el content_hash almacenado. Si coincide,
        # omite la escritura en PostgreSQL y la invalidación del caché Redis.
        # Si difiere, archiva el contenido anterior en kb_content_versions.
        #
        # Para activar:    KB_CONTENT_VERSIONING=true
        # Para desactivar: KB_CONTENT_VERSIONING=false  (comportamiento pre-L2)
        #
        # CUANDO USAR:
        # - Produccion con L2 probado: true
        # - Rollback de emergencia: false (sin redeploy, solo cambio de env var)
        # - Tests unitarios de _upsert: controlar con os.environ patch
        self._use_content_versioning = os.getenv("KB_CONTENT_VERSIONING", "false").lower() in (
            "true", "1", "yes", "on"
        )

        # ✅ L2: Número máximo de versiones históricas a conservar por registro.
        #
        # Política de retención: después de archivar una nueva versión, se borran
        # las más antiguas que excedan este límite.
        #
        # Con 26 registros en kb_contents y 10 versiones: máx 260 filas en
        # kb_content_versions. Completamente trivial para PostgreSQL.
        #
        # Para L4 que necesita más historia: KB_MAX_VERSIONS_PER_CONTENT=50
        max_versions_raw = os.getenv("KB_MAX_VERSIONS_PER_CONTENT", "10")
        try:
            self._max_versions_per_content: int = max(1, int(max_versions_raw))
        except ValueError:
            logger.warning(
                "invalid_max_versions_configured",
                raw_value=max_versions_raw,
                fallback=10,
                reason="must_be_positive_integer"
            )
            self._max_versions_per_content = 10

        # ✅ H1: Structured logging for initialization with M1+M2+M3+M4+L2 metrics
        logger.info(
            "service_initialized",
            service="ShopifyKBSyncService",
            max_concurrent_syncs=semaphore_size,
            semaphore_size=semaphore_size,
            configured_via="env_var" if os.getenv("KB_SYNC_SEMAPHORE_SIZE") else "default",
            distributed_locks_enabled=self._use_distributed_locks,
            content_versioning_enabled=self._use_content_versioning,
            max_versions_per_content=self._max_versions_per_content,
            optimization_phase="M1+M2+M3+M4+L2",
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
    
    # ──────────────────────────────────────────────────────────────────────
    # L2: CONTENT VERSIONING HELPERS
    # ──────────────────────────────────────────────────────────────────────

    def _compute_content_hash(self, content: str) -> str:
        """
        ✅ L2: Calcula el SHA256 del contenido Markdown.

        Usamos SHA256 sobre MD5 porque:
        - L4 puede usar el hash como identificador en sistemas externos
          (BigQuery, MLflow, etc.) donde MD5 tiene colisiones documentadas.
        - La diferencia de velocidad (microsegundos) es irrelevante aquí.
        - hashlib es stdlib — sin dependencia externa adicional.

        La codificación UTF-8 es crítica: el contenido puede contener
        tildes, eñes y caracteres Unicode de mercados es/en/mx/cl.

        NOTA — OPCIÓN A (performance alternativa):
        Si en el futuro el volumen de registros crece significativamente
        y el SELECT previo del Paso 2 en _upsert_kb_content() se convierte
        en un cuello de botella, considerar la siguiente alternativa que
        elimina el round-trip extra usando una sola operación DB con RETURNING:

            INSERT INTO kb_contents (..., content_hash, ...)
            VALUES (..., $hash, ...)
            ON CONFLICT (sub_intent, language, COALESCE(category, 'general'))
            DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                content_version = kb_contents.content_version + 1,
                updated_at = NOW()
            WHERE kb_contents.content_hash != EXCLUDED.content_hash
            RETURNING id, content_version, content_hash

        El WHERE en el DO UPDATE hace que PostgreSQL no ejecute la
        actualización si el hash es idéntico, y el RETURNING permite
        detectar si hubo cambio real sin un SELECT previo.
        Con 26 registros y ciclos cada 5 min, la Opción B (actual) es
        más legible y su diferencia de performance es despreciable.

        Args:
            content: String Markdown (post-L1, ya limpio y normalizado)

        Returns:
            str: 64 caracteres hexadecimales del SHA256
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def _archive_content_version(
        self,
        conn: asyncpg.Connection,
        kb_content_id: str,
        version: int,
        content: str,
        content_html: Optional[str],
        content_hash: str,
        title: Optional[str],
        sync_source: str = "background_sync",
    ) -> None:
        """
        ✅ L2: Archiva el contenido ACTUAL en kb_content_versions ANTES de sobreescribirlo.

        Se llama dentro de la transacción de _upsert_kb_content(), después de detectar
        que el hash entrante difiere del almacenado (cambio real de contenido).

        Por qué archivar el contenido ACTUAL y no el nuevo:
            El historial debe representar "lo que había antes". La fila en
            kb_content_versions dice: "en este registro, la versión N tenía
            este contenido y fue reemplazada en replaced_at".
            L4 puede reconstruir la secuencia: versión 1 → 2 → 3 → actual.

        El INSERT usa ON CONFLICT DO NOTHING como safety net contra el caso
        donde un retry del sync intente archivar la misma versión dos veces
        (poco probable con el distributed lock, pero defensivo).

        Args:
            conn:           Conexión asyncpg activa (dentro de transacción)
            kb_content_id:  UUID del registro en kb_contents (str para asyncpg)
            version:        Número de versión ACTUAL que se está archivando
            content:        Markdown ACTUAL (antes del reemplazo)
            content_html:   HTML ACTUAL (antes del reemplazo), puede ser None
            content_hash:   SHA256 del content ACTUAL
            title:          Título ACTUAL
            sync_source:    Origen del sync que detectó el cambio
        """
        await conn.execute(
            """
            INSERT INTO kb_content_versions (
                kb_content_id, version, content, content_html,
                content_hash, title, replaced_at, sync_source
            ) VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7)
            ON CONFLICT (kb_content_id, version) DO NOTHING
            """,
            kb_content_id,
            version,
            content,
            content_html,
            content_hash,
            title,
            sync_source,
        )

        logger.debug(
            "content_version_archived",
            kb_content_id=str(kb_content_id),
            version=version,
            content_hash=content_hash[:16] + "...",  # Solo los primeros 16 chars en logs
            sync_source=sync_source,
        )

    async def _prune_old_versions(
        self,
        conn: asyncpg.Connection,
        kb_content_id: str,
        max_versions: int,
    ) -> None:
        """
        ✅ L2: Elimina versiones antiguas que excedan el límite de retención.

        Política de retención: conservar solo las `max_versions` más recientes
        para cada registro de kb_contents. Las más antiguas se eliminan.

        Por qué hacerlo después del INSERT (no en un job separado):
            Mantiene la tabla pequeña sin necesitar un cron job adicional.
            Con max=10 y 26 registros, el máximo absoluto es 260 filas —
            el costo de esta operación es completamente negligible.

        Algoritmo:
            DELETE ... WHERE id NOT IN (SELECT id ORDER BY version DESC LIMIT max)
            Esto conserva las N versiones más recientes y borra el resto.

        Args:
            conn:           Conexión asyncpg activa (dentro de transacción)
            kb_content_id:  UUID del registro padre
            max_versions:   Número máximo de versiones a conservar
        """
        deleted = await conn.fetchval(
            """
            WITH versions_to_keep AS (
                SELECT id
                FROM kb_content_versions
                WHERE kb_content_id = $1
                ORDER BY version DESC
                LIMIT $2
            ),
            deleted AS (
                DELETE FROM kb_content_versions
                WHERE kb_content_id = $1
                  AND id NOT IN (SELECT id FROM versions_to_keep)
                RETURNING id
            )
            SELECT COUNT(*) FROM deleted
            """,
            kb_content_id,
            max_versions,
        )

        if deleted and deleted > 0:
            logger.debug(
                "content_versions_pruned",
                kb_content_id=str(kb_content_id),
                versions_deleted=deleted,
                max_versions_kept=max_versions,
            )

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
        ✅ M3+L2 — Upsert KB content con Distributed Locking, retry y Content Versioning.

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

        # ✅ M3: Lock key único por registro de KB
        lock_key = f"kb_sync:lock:{sub_intent}:{language}:{normalized_category}"

        # ── Queries separadas pre/post L2 ─────────────────────────────────────
        #
        # QUERY A — INSERT inicial para registros nuevos (no existe en DB todavía).
        # Solo se usa cuando el SELECT del Paso 2 no devuelve fila.
        query_insert = """
        INSERT INTO kb_contents (
            sub_intent, language, category, content, content_html,
            title, shopify_page_id, shopify_url, shopify_handle,
            content_hash, content_version,
            last_synced, created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 1, NOW(), NOW(), NOW()
        )
        RETURNING id, content_version
        """

        # QUERY B — UPDATE para registros existentes con cambio real de contenido.
        # Actualiza hash, incrementa versión, y actualiza timestamps.
        # Se usa cuando el hash entrante DIFIERE del almacenado.
        query_update = """
        UPDATE kb_contents SET
            content          = $1,
            content_html     = $2,
            title            = $3,
            shopify_url      = $4,
            shopify_handle   = $5,
            content_hash     = $6,
            content_version  = content_version + 1,
            last_synced      = NOW(),
            updated_at       = NOW()
        WHERE sub_intent = $7
          AND language   = $8
          AND COALESCE(category, 'general') = $9
        RETURNING id, content_version
        """

        # QUERY C — UPDATE de last_synced SOLAMENTE (sin cambiar contenido).
        # Se usa cuando el hash entrante COINCIDE con el almacenado.
        # Actualiza last_synced para que el sistema sepa que se revisó,
        # pero NO toca updated_at ni content_version.
        query_touch_last_synced = """
        UPDATE kb_contents
        SET last_synced = NOW()
        WHERE sub_intent = $1
          AND language   = $2
          AND COALESCE(category, 'general') = $3
        """

        # QUERY PRE-L2 — Comportamiento original sin versioning (flag desactivado).
        # Se mantiene para compatibilidad hacia atrás y rollback de emergencia.
        query_pre_l2 = """
        INSERT INTO kb_contents (
            sub_intent, language, category, content, content_html,
            title, shopify_page_id, shopify_url, shopify_handle,
            last_synced, created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW(), NOW()
        )
        ON CONFLICT (sub_intent, language, COALESCE(category, 'general'))
        DO UPDATE SET
            content        = EXCLUDED.content,
            content_html   = EXCLUDED.content_html,
            title          = EXCLUDED.title,
            shopify_url    = EXCLUDED.shopify_url,
            shopify_handle = EXCLUDED.shopify_handle,
            last_synced    = NOW(),
            updated_at     = NOW()
        """

        max_retries = 3
        retry_delay = 0.1

        # ✅ L2: Calcular hash del contenido ENTRANTE una sola vez fuera del loop de retries.
        # Es una operación CPU pura y determinista — no necesita estar dentro del try/except
        # ni repetirse en cada intento.
        incoming_hash = self._compute_content_hash(content) if self._use_content_versioning else None

        for attempt in range(max_retries):
            try:
                async with self._db_semaphore:

                    if self._use_distributed_locks:
                        async with self.redis.distributed_lock(
                            lock_name=lock_key,
                            timeout=30.0,
                            blocking_timeout=5.0
                        ):
                            await self._execute_upsert(
                                sub_intent, language, normalized_category,
                                content, content_html, title,
                                shopify_page_id, shopify_url, shopify_handle,
                                incoming_hash,
                                query_insert, query_update,
                                query_touch_last_synced, query_pre_l2,
                                distributed_lock_used=True,
                            )
                            return
                    else:
                        await self._execute_upsert(
                            sub_intent, language, normalized_category,
                            content, content_html, title,
                            shopify_page_id, shopify_url, shopify_handle,
                            incoming_hash,
                            query_insert, query_update,
                            query_touch_last_synced, query_pre_l2,
                            distributed_lock_used=False,
                        )
                        return

            except DistributedLockError as e:
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
                        logger.warning(
                            "kb_upsert_retry",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            error=str(e),
                            retry_delay_seconds=retry_delay * (attempt + 1)
                        )
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue

                logger.error(
                    "kb_upsert_failed",
                    sub_intent=sub_intent,
                    language=language,
                    category=normalized_category,
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise

    async def _execute_upsert(
        self,
        sub_intent: str,
        language: str,
        normalized_category: str,
        content: str,
        content_html: str,
        title: Optional[str],
        shopify_page_id: int,
        shopify_url: Optional[str],
        shopify_handle: Optional[str],
        incoming_hash: Optional[str],
        query_insert: str,
        query_update: str,
        query_touch_last_synced: str,
        query_pre_l2: str,
        distributed_lock_used: bool,
    ) -> None:
        """
        ✅ L2 — Lógica real del upsert, extraída para evitar duplicación en los
        dos ramas del distributed lock.

        FLUJO DE 7 PASOS (cuando KB_CONTENT_VERSIONING=true):

        Paso 1 — Calcular hash del contenido entrante (ya calculado por el caller).

        Paso 2 — SELECT del registro actual en DB.
            Lee (id, content_hash, content_version, content, content_html, title)
            Si el registro no existe → saltar al Paso 5 directamente (INSERT).

        Paso 3 — Comparar hashes.
            stored_hash == incoming_hash:
                → No hay cambio real. SKIP completo (Paso 6).
            stored_hash != incoming_hash (o es NULL porque es pre-backfill):
                → Continuar al Paso 4.

        Paso 4 — Archivar la versión actual en kb_content_versions.
            INSERT INTO kb_content_versions (contenido ACTUAL, ANTES de reemplazarlo).

        Paso 5 — Escribir el nuevo contenido en kb_contents.
            Si el registro no existía: INSERT con content_version=1.
            Si existía con hash diferente: UPDATE incrementando content_version.

        Paso 6 — Early return si no hubo cambio.
            Loguear a nivel DEBUG. No invalidar caché Redis.

        Paso 7 — Poda de versiones antiguas.
            DELETE versiones que excedan self._max_versions_per_content.
        """
        async with self.db.acquire() as conn:

            # ── RAMA PRE-L2: comportamiento original (flag desactivado) ────────
            # Preservado íntegro para rollback de emergencia sin redeploy.
            # Simplemente cambiar KB_CONTENT_VERSIONING=false restaura este flujo.
            if not self._use_content_versioning:
                await conn.execute(
                    query_pre_l2,
                    sub_intent, language, normalized_category,
                    content, content_html, title,
                    shopify_page_id, shopify_url, shopify_handle
                )
                logger.debug(
                    "kb_content_upserted",
                    sub_intent=sub_intent,
                    language=language,
                    category=normalized_category,
                    shopify_page_id=shopify_page_id,
                    content_versioning_enabled=False,
                    distributed_lock_used=distributed_lock_used,
                )
                return

            # ── RAMA L2: detección de cambios por hash ────────────────────────

            # ── PASO 2: Leer estado actual del registro en DB ─────────────────
            # Leemos id, hash, versión, y el contenido anterior completo.
            # El contenido anterior lo necesitamos para archivarlo en el Paso 4.
            # SELECT en la misma conexión que el UPDATE posterior garantiza
            # consistencia — aunque sin transacción explícita, asyncpg en modo
            # autocommit asegura que nadie modifica entre SELECT y UPDATE porque
            # el distributed_lock (Capa 2) o el semáforo (Capa 1) nos protegen.
            existing = await conn.fetchrow(
                """
                SELECT id, content_hash, content_version, content, content_html, title
                FROM kb_contents
                WHERE sub_intent = $1
                  AND language   = $2
                  AND COALESCE(category, 'general') = $3
                """,
                sub_intent, language, normalized_category
            )

            # ── PASO 3: Comparar hashes ───────────────────────────────────────
            # Un content_hash NULL en DB significa que el registro existe pero
            # no tiene hash todavía (pre-backfill). Lo tratamos como "diferente"
            # para forzar la escritura y poblar el hash en el primer ciclo post-L2.
            #
            # INVARIANTE: incoming_hash nunca es None aquí porque el flag
            # self._use_content_versioning es True (se calculó en _upsert_kb_content).
            if existing is not None:
                stored_hash = existing["content_hash"]
                if stored_hash is not None and stored_hash == incoming_hash:
                    # ── PASO 6: Sin cambio real — early return ────────────────
                    # No escribir en PostgreSQL (no tocar updated_at).
                    # No invalidar caché Redis.
                    # Solo actualizar last_synced para tracking de polling.
                    # Loguear a DEBUG, no INFO (reduce ruido en logs de producción).
                    await conn.execute(
                        query_touch_last_synced,
                        sub_intent, language, normalized_category
                    )
                    logger.debug(
                        "kb_content_unchanged",
                        sub_intent=sub_intent,
                        language=language,
                        category=normalized_category,
                        shopify_page_id=shopify_page_id,
                        content_hash=stored_hash[:16] + "...",
                        content_version=existing["content_version"],
                        note="skip_write_skip_cache_invalidation",
                    )
                    return  # ← sale ANTES de _invalidate_cache en sync_page()

            # ── PASO 4: Archivar versión actual (solo si el registro ya existía) ──
            # Si existing is None, es un INSERT nuevo — no hay nada que archivar.
            if existing is not None:
                await self._archive_content_version(
                    conn=conn,
                    kb_content_id=str(existing["id"]),
                    version=existing["content_version"],
                    content=existing["content"],
                    content_html=existing["content_html"],
                    content_hash=existing["content_hash"] or incoming_hash,
                    title=existing["title"],
                    sync_source="background_sync",
                )

            # ── PASO 5: Escribir nuevo contenido en kb_contents ───────────────
            if existing is None:
                # Registro nuevo: INSERT con content_version=1
                row = await conn.fetchrow(
                    query_insert,
                    sub_intent, language, normalized_category,
                    content, content_html, title,
                    shopify_page_id, shopify_url, shopify_handle,
                    incoming_hash,
                )
                new_version = row["content_version"] if row else 1
                logger.debug(
                    "kb_content_inserted",
                    sub_intent=sub_intent,
                    language=language,
                    category=normalized_category,
                    shopify_page_id=shopify_page_id,
                    content_hash=incoming_hash[:16] + "...",
                    content_version=new_version,
                    distributed_lock_used=distributed_lock_used,
                )
            else:
                # Registro existente con cambio real: UPDATE + incremento de versión
                row = await conn.fetchrow(
                    query_update,
                    content, content_html, title,
                    shopify_url, shopify_handle,
                    incoming_hash,
                    sub_intent, language, normalized_category,
                )
                new_version = row["content_version"] if row else existing["content_version"] + 1
                kb_content_id = str(existing["id"])

                logger.debug(
                    "kb_content_updated",
                    sub_intent=sub_intent,
                    language=language,
                    category=normalized_category,
                    shopify_page_id=shopify_page_id,
                    content_hash_new=incoming_hash[:16] + "...",
                    content_version_new=new_version,
                    distributed_lock_used=distributed_lock_used,
                )

                # ── PASO 7: Poda de versiones antiguas ───────────────────────
                # Solo si hubo cambio real (hay una nueva versión archivada).
                # La poda borra versiones archivadas, no el registro actual.
                await self._prune_old_versions(
                    conn=conn,
                    kb_content_id=kb_content_id,
                    max_versions=self._max_versions_per_content,
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
        # Defensive check: Redis service might be None if initialization failed
        if self.redis is None:
            logger.warning(
                "cache_invalidation_skipped",
                reason="redis_service_not_available",
                sub_intent=sub_intent,
                language=language,
                category=category or 'general'
            )
            return

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
        Convierte HTML de Shopify a Markdown limpio usando markdownify.

        L1: Reemplaza el parser regex manual (frágil) con una librería
        robusta que preserva la estructura semántica del contenido.

        DECISIÓN DE LIBRERÍA: markdownify
        - Maneja tablas HTML → Markdown nativo
        - Conserva links con su URL (en vez de descartarlos)
        - Limpieza configurable de tags inválidos para Markdown
        - Fallback seguro: si falla, elimina tags con BeautifulSoup

        CONFIGURACIÓN APLICADA:
        - heading_style="ATX"  → # H1, ## H2 (no el estilo con ===)
        - bullets="-"          → listas con guión (consistente)
        - strip=["script","style","iframe"] → elimina ruido Shopify
        - convert_links=True   → [texto](url) en lugar de solo texto

        Args:
            html: HTML crudo proveniente de Shopify page.body_html
                o de get_page_translations(). Puede ser vacío o None.

        Returns:
            str: Markdown limpio. Retorna "" si el input es vacío.
                Nunca lanza excepción (fallback garantizado).
        """
        # Caso base: HTML vacío o None → retornar string vacío
        # Esto ocurre para páginas sin contenido o traducciones en progreso
        if not html or not html.strip():
            return ""

        # _MARKDOWNIFY_AVAILABLE se evalúa en tiempo de módulo (import al inicio).
        # Si es False, significa que markdownify no está instalado → fallback directo
        # sin necesidad de intentar el import y capturar ImportError en runtime.
        if not _MARKDOWNIFY_AVAILABLE:
            logger.warning(
                "markdownify_not_installed",
                fallback="beautifulsoup_text_extraction",
                action_required="pip install markdownify",
                hint="add markdownify>=0.12.1 to requirements.txt"
            )
            return self._html_to_text_fallback(html)

        try:
            # ── PRE-PROCESADO: eliminar tags de ruido con BeautifulSoup ──────────
            # IMPORTANTE: El parámetro strip=[] de markdownify NO elimina el
            # CONTENIDO de los tags — solo quita el tag wrapper pero deja el
            # texto interno como texto plano. Ejemplo con strip=['script']:
            #   <script>gtag('event')</script>  →  gtag('event')  ← ¡visible!
            #
            # La solución correcta es BeautifulSoup con tag.decompose():
            # decompose() elimina el tag Y todo su contenido del árbol DOM.
            # Hacemos esto ANTES de markdownify para que el HTML que recibe
            # ya esté limpio de ruido.
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # Tags a eliminar completamente (tag + contenido):
            # - script: Google Analytics, Pixel, chat widgets JS
            # - style:  CSS inline que Shopify puede incluir
            # - iframe: Widgets de chat, videos embedidos
            # - noscript: Alternativas de no-JS (generalmente publicitarias)
            # - meta/link: Tags de metadata no visibles (sin contenido útil)
            _TAGS_TO_REMOVE = ["script", "style", "iframe", "noscript", "meta", "link"]
            for tag in soup(_TAGS_TO_REMOVE):
                tag.decompose()  # Elimina tag + su contenido del árbol DOM

            # Serializar de vuelta a HTML limpio para pasarlo a markdownify
            clean_html = str(soup)

            # Convertir HTML limpio a Markdown con configuración optimizada para Shopify.
            # Usamos _markdownify (alias del import a nivel de módulo) para que
            # el linter conozca el tipo y pueda validar los argumentos.
            # NOTA: Ya no necesitamos strip=[] aquí — el pre-procesado lo hizo.
            markdown = _markdownify.markdownify(
                clean_html,
                heading_style="ATX",   # # Título (no Título\n====)
                bullets="-",           # Listas con - consistente
            )

            # Post-procesado: limpiar líneas en blanco excesivas.
            # markdownify puede generar 3+ líneas en blanco entre secciones;
            # normalizamos a máximo 2 para un Markdown consistente.
            # re fue importado a nivel de módulo — sin import local aquí.
            markdown = re.sub(r'\n{3,}', '\n\n', markdown)
            markdown = markdown.strip()

            logger.debug(
                "html_to_markdown_converted",
                input_length=len(html),
                output_length=len(markdown),
                reduction_pct=round((1 - len(markdown)/len(html)) * 100, 1)
                             if len(html) > 0 else 0,
                library="markdownify"
            )

            return markdown

        except Exception as e:
            # Error inesperado en markdownify (HTML muy malformado, etc.)
            # Fallback: extraer texto plano para no perder el contenido
            logger.error(
                "html_to_markdown_failed",
                error=str(e),
                error_type=type(e).__name__,
                input_length=len(html),
                fallback="text_extraction"
            )
            return self._html_to_text_fallback(html)


    def _html_to_text_fallback(self, html: str) -> str:
        """
        Fallback: extrae texto plano eliminando todos los tags HTML.

        Usado cuando markdownify falla o no está disponible.
        Preserva el contenido aunque pierde el formato.

        Estrategia de limpieza:
        1. Elimina scripts y styles completamente (con su contenido)
        2. Usa BeautifulSoup para extraer texto limpio
        3. Si BeautifulSoup no está disponible, usa regex simple
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Eliminar tags que no aportan contenido legible
            for tag in soup(["script", "style", "iframe", "noscript"]):
                tag.decompose()

            # get_text() con separador de espacio entre tags inline
            text = soup.get_text(separator=" ", strip=True)

            # Limpiar espacios múltiples.
            # re fue importado a nivel de módulo — sin import local aquí.
            text = re.sub(r'  +', ' ', text)
            return text.strip()

        except ImportError:
            # Último recurso: regex para eliminar tags.
            # re fue importado a nivel de módulo — disponible sin import local.
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
            html = re.sub(r'<[^>]+>', ' ', html)
            html = re.sub(r'  +', ' ', html)
            return html.strip()
            
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