"""
shopify_webhook_handler.py — Procesamiento de Webhooks de Shopify
===================================================================

╔══════════════════════════════════════════════════════════════════════════╗
║  NOTA PARA DESARROLLADORES — ESTADO ACTUAL (Feb 2026)                  ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Handler stateless que procesa el payload de un webhook DESPUÉS         ║
║  del ACK a Shopify (se ejecuta en FastAPI BackgroundTask).              ║
║                                                                          ║
║  ESTADO: PARCIALMENTE ACTIVO.                                           ║
║                                                                          ║
║  handle_translation_event() — ACTIVO                                   ║
║    Shopify SÍ emite translations/update cuando marketing actualiza      ║
║    una traducción de una página en Translate & Adapt. Este flujo        ║
║    funciona completamente hoy:                                           ║
║      Shopify → webhook → router → este handler → sync_single_page()     ║
║                                                                          ║
║  handle_page_event() — PREPARADO, NO ACTIVO AUN                        ║
║    Shopify NO emite pages/create, pages/update, pages/delete.           ║
║    El handler está completamente implementado y listo. Cuando           ║
║    Shopify agregue soporte, basta activar el registro en:               ║
║    shopify_webhook_registry.py → REQUIRED_WEBHOOKS                     ║
║    Mientras tanto, los cambios en páginas se detectan via polling       ║
║    incremental en KBBackgroundSyncJob (shopify_kb_sync.py).             ║
║                                                                          ║
║  DISEÑO IMPORTANTE — Lazy init:                                         ║
║    Las dependencias (Redis, ShopifyKBSyncService) se resuelven lazy     ║
║    en _get_redis() y _get_sync_service(). Esto hace el handler          ║
║    testeable sin necesitar el contexto completo de la app.              ║
║                                                                          ║
║  IDEMPOTENCY:                                                            ║
║    Shopify garantiza at-least-once delivery (el mismo webhook puede     ║
║    llegar 2+ veces). is_duplicate_event() usa Redis SET NX para         ║
║    detectar y descartar duplicados sin doble procesamiento.             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import structlog
import time
from typing import Optional

logger = structlog.get_logger(__name__)

# TTL del idempotency key en Redis (5 minutos)
# Shopify no reintenta con menos de 5 minutos de diferencia en condiciones normales
IDEMPOTENCY_TTL_SECONDS = 300

# Prefijo para idempotency keys en Redis
IDEMPOTENCY_KEY_PREFIX = "webhook:idempotency:"


class ShopifyWebhookHandler:
    """
    Maneja el procesamiento de webhooks de Shopify.
    
    Responsabilidades:
    1. Idempotency check (evitar doble procesamiento)
    2. Routing por topic (create/update/delete)
    3. Sync de página individual
    4. Invalidación de cache Redis
    5. Métricas de observabilidad
    
    Diseño:
    - Stateless: cada instancia se crea por request
    - Depends on: RedisService (idempotency), ShopifyKBSyncService (sync logic)
    - Integra con M3 (distributed_lock) vía _upsert_kb_content()
    """
    
    def __init__(self):
        # Dependencias se resuelven lazy para facilitar testing
        self._redis = None
        self._sync_service = None
    
    async def _get_redis(self):
        """Lazy init de RedisService (singleton)."""
        if not self._redis:
            from src.api.core.redis_service import get_redis_service
            self._redis = await get_redis_service()
        return self._redis
    
    async def _get_sync_service(self):
        """Lazy init de ShopifyKBSyncService."""
        if not self._sync_service:
            from src.api.services.shopify_kb_sync import ShopifyKBSyncService
            self._sync_service = ShopifyKBSyncService()
        return self._sync_service
    
    async def is_duplicate_event(
        self,
        page_id: int,
        topic: str,
        timestamp_ms: Optional[int] = None,
    ) -> bool:
        """
        Verifica si este evento ya fue procesado recientemente.
        
        Shopify garantiza at-least-once delivery, lo que significa que el
        mismo webhook puede llegar 2+ veces. Usamos Redis como store de
        idempotency keys para detectar duplicados.
        
        Key format: webhook:idempotency:{topic}:{page_id}
        Ejemplo:    webhook:idempotency:pages/update:12345
        
        Args:
            page_id: ID de la página
            topic: Topic del webhook (pages/create, pages/update, pages/delete)
            timestamp_ms: Timestamp del evento (opcional, para key más específica)
        
        Returns:
            True si el evento ya fue procesado (es duplicado)
            False si es nuevo y debe procesarse
        """
        redis = await self._get_redis()
        key = f"{IDEMPOTENCY_KEY_PREFIX}{topic}:{page_id}"
        
        # SET NX: solo setea si NO existe (operación atómica)
        # Si ya existe → duplicado (devuelve False en SETNX)
        # Si no existe → nuevo evento (setea y devuelve True en SETNX)
        existing = await redis.get(key)
        
        if existing:
            logger.info(
                "webhook_duplicate_detected",
                page_id=page_id,
                topic=topic,
                idempotency_key=key,
            )
            return True
        
        # Registrar que vamos a procesar este evento
        await redis.set(key, "processing", ttl=IDEMPOTENCY_TTL_SECONDS)
        return False
    
    async def handle_translation_event(
        self,
        page_id: int,
        locale: str,
    ) -> None:
        """
        Dispatcher para eventos de traducción (translations/update).

        Shopify emite este webhook cuando se edita una traducción de una
        página vía Shopify Markets / Translate & Adapt.

        Estrategia: re-sync completo de la página (todos los idiomas).
        Esto es equivalente a un pages/update — el contenido multilingüe
        se re-extrae en sync_single_page() junto con el contenido base.

        Idempotency key específica para translations:
            webhook:idempotency:translations/update:{page_id}:{locale}
        El locale se incluye para que actualizaciones simultáneas de
        distintos idiomas de la misma página no se bloqueen entre sí.

        Args:
            page_id: ID de la página cuya traducción fue actualizada
            locale: Código de idioma actualizado (ej. "en", "es", "pt")
        """
        start_time = time.time()
        # Topic sintético para idempotency y métricas
        topic = "translations/update"
        # Clave de idempotency incluye locale → traducciones distintas
        # de la misma página no se cancelan entre sí
        idempotency_topic = f"{topic}:{locale}"

        try:
            # ── Idempotency check ─────────────────────────────────────────
            if await self.is_duplicate_event(page_id, idempotency_topic):
                return

            logger.info(
                "webhook_translation_syncing",
                page_id=page_id,
                locale=locale,
            )

            # ── Sync: re-extraer todos los idiomas de la página ───────────
            # sync_single_page() ya obtiene las traducciones junto con el
            # contenido base → no necesitamos un método separado.
            sync_service = await self._get_sync_service()
            await sync_service.sync_single_page(page_id)

            # ── Cache invalidation ────────────────────────────────────────
            # No tenemos el handle aquí, usamos page_id como patrón base.
            # kb:page:{id}:* cubre todas las variantes de idioma.
            await self._invalidate_page_cache(page_id, page_handle="")

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "webhook_translation_processed",
                page_id=page_id,
                locale=locale,
                duration_ms=round(elapsed_ms, 2),
            )

            try:
                from src.api.core.prometheus_metrics import (
                    kb_webhook_processed_total,
                    kb_webhook_processing_seconds,
                )
                kb_webhook_processed_total.labels(topic=topic, result="success").inc()
                kb_webhook_processing_seconds.observe(elapsed_ms / 1000)
            except ImportError:
                pass

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "webhook_translation_failed",
                page_id=page_id,
                locale=locale,
                error=str(e),
                duration_ms=round(elapsed_ms, 2),
            )
            try:
                from src.api.core.prometheus_metrics import kb_webhook_processed_total
                kb_webhook_processed_total.labels(topic=topic, result="error").inc()
            except ImportError:
                pass
            raise

    async def handle_page_event(
        self,
        page_id: int,
        page_handle: str,
        topic: str,
    ) -> None:
        """
        Dispatcher principal para eventos de páginas.
        
        Mapea topic a handler específico:
        - pages/create → handle_page_upsert()
        - pages/update → handle_page_upsert()
        - pages/delete → handle_page_delete()
        
        Args:
            page_id: ID de la página afectada
            page_handle: Handle (slug), para logging y cache invalidation
            topic: Topic del webhook de Shopify
        """
        start_time = time.time()
        
        try:
            # ── Idempotency check ─────────────────────────────────────────
            if await self.is_duplicate_event(page_id, topic):
                return  # Ya procesado, salir silenciosamente
            
            # ── Routing por topic ─────────────────────────────────────────
            if topic in ("pages/create", "pages/update"):
                await self._handle_page_upsert(page_id, page_handle)
            elif topic == "pages/delete":
                await self._handle_page_delete(page_id, page_handle)
            else:
                logger.warning(
                    "webhook_unknown_topic",
                    topic=topic,
                    page_id=page_id,
                )
                return
            
            # ── Métricas ──────────────────────────────────────────────────
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "webhook_processed_successfully",
                page_id=page_id,
                topic=topic,
                duration_ms=round(elapsed_ms, 2),
            )
            
            try:
                from src.api.core.prometheus_metrics import (
                    kb_webhook_processed_total,
                    kb_webhook_processing_seconds,
                )
                kb_webhook_processed_total.labels(topic=topic, result="success").inc()
                kb_webhook_processing_seconds.observe(elapsed_ms / 1000)
            except ImportError:
                pass
        
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "webhook_processing_failed",
                page_id=page_id,
                topic=topic,
                error=str(e),
                duration_ms=round(elapsed_ms, 2),
            )
            try:
                from src.api.core.prometheus_metrics import kb_webhook_processed_total
                kb_webhook_processed_total.labels(topic=topic, result="error").inc()
            except ImportError:
                pass
            raise
    
    async def _handle_page_upsert(self, page_id: int, page_handle: str) -> None:
        """
        Sincroniza una página específica (create o update).
        
        Este método es el corazón del incremental sync:
        en lugar de sync_all_pages(), solo sincroniza la página afectada.
        
        Args:
            page_id: ID de la página a sincronizar
            page_handle: Handle, para cache invalidation
        """
        sync_service = await self._get_sync_service()
        
        logger.info(
            "webhook_syncing_page",
            page_id=page_id,
            page_handle=page_handle,
        )
        
        # sync_single_page() es el nuevo método que extraeremos de
        # sync_all_pages() en ShopifyKBSyncService
        await sync_service.sync_single_page(page_id)
        
        # Invalidar cache Redis para esta página
        await self._invalidate_page_cache(page_id, page_handle)
    
    async def _handle_page_delete(self, page_id: int, page_handle: str) -> None:
        """
        Elimina el contenido de KB para una página eliminada en Shopify.
        
        Args:
            page_id: ID de la página eliminada
            page_handle: Handle, para cache invalidation
        """
        sync_service = await self._get_sync_service()
        
        logger.info(
            "webhook_deleting_page",
            page_id=page_id,
            page_handle=page_handle,
        )
        
        await sync_service.delete_kb_for_page(page_id)
        await self._invalidate_page_cache(page_id, page_handle)
    
    async def _invalidate_page_cache(self, page_id: int, page_handle: str) -> None:
        """
        Invalida las entradas de cache Redis relacionadas con esta página.

        ──────────────────────────────────────────────────────────────────────
        Bug 3 FIX: SCAN + DELETE para patrones glob
        ──────────────────────────────────────────────────────────────────────
        El método RedisService.delete(key) solo acepta una clave EXACTA y
        llama internamente a self._client.delete(key). Pasarle un patrón glob
        como "kb:page:123:*" lo interpreta como nombre literal de clave, nunca
        encuentra ningún match y la invalidación falla silenciosamente.

        Redis no expone KEYS/DELETE con glob directamente por seguridad y
        performance en producción. La forma correcta es:
            1. SCAN cursor MATCH pattern COUNT 100  → obtiene lote de claves
            2. Si hay claves → DEL key1 key2 ...   → borra el lote
            3. Repetir hasta cursor == 0            → fin del espacio de claves

        SCAN es no-bloqueante (itera en chunks), seguro para producción.
        KEYS bloquearía Redis mientras itera todo el keyspace — NUNCA usar.

        Estructura del keyspace que invalidamos:
            kb:page:{id}:*           → contenido KB cacheado por page_id
            kb:handle:{handle}:*     → contenido KB cacheado por handle/slug
            kb:sync:status:page:{id} → estado de última sincronización (clave exacta)

        Args:
            page_id: ID de la página
            page_handle: Handle/slug de la página
        """
        redis = await self._get_redis()

        # ── Verificar que el cliente raw esté disponible ───────────────────
        # RedisService puede estar en modo degradado (_client = None) si Redis
        # no está disponible. En ese caso, no hay cache que invalidar.
        if not redis._client:
            logger.warning(
                "cache_invalidation_skipped_no_client",
                page_id=page_id,
                reason="redis_client_unavailable_degraded_mode",
            )
            return

        # ── Patrones glob que requieren SCAN ──────────────────────────────
        # Estas claves usan sufijo :* → no se pueden borrar con delete() exacto
        glob_patterns = [
            f"kb:page:{page_id}:*",
            f"kb:handle:{page_handle}:*",
        ]

        for pattern in glob_patterns:
            deleted_count = 0
            try:
                # Cursor inicial = 0 → inicio del recorrido del keyspace
                cursor = 0
                while True:
                    # SCAN devuelve (nuevo_cursor, [lista_de_claves])
                    # COUNT 100 es una *sugerencia* al servidor, no un límite estricto.
                    # Redis puede devolver más o menos claves por iteración.
                    cursor, keys = await redis._client.scan(
                        cursor=cursor,
                        match=pattern,
                        count=100,
                    )

                    if keys:
                        # DEL acepta múltiples claves en una sola llamada → eficiente
                        await redis._client.delete(*keys)
                        deleted_count += len(keys)

                    # cursor == 0 indica que el SCAN completó el recorrido completo
                    if cursor == 0:
                        break

                logger.debug(
                    "cache_pattern_invalidated",
                    pattern=pattern,
                    page_id=page_id,
                    keys_deleted=deleted_count,
                )

            except Exception as e:
                # La invalidación de cache NO debe bloquear el sync principal.
                # Un fallo aquí solo significa que se servirá contenido stale
                # hasta que expire el TTL natural de las claves.
                logger.warning(
                    "cache_invalidation_failed",
                    pattern=pattern,
                    page_id=page_id,
                    error=str(e),
                )

        # ── Clave exacta (sin glob) → delete() directamente ───────────────
        # kb:sync:status:page:{id} es una clave única sin variantes.
        # No necesita SCAN, se puede borrar con la interfaz normal de RedisService.
        exact_key = f"kb:sync:status:page:{page_id}"
        try:
            await redis.delete(exact_key)
            logger.debug(
                "cache_exact_key_invalidated",
                key=exact_key,
                page_id=page_id,
            )
        except Exception as e:
            logger.warning(
                "cache_invalidation_failed",
                key=exact_key,
                page_id=page_id,
                error=str(e),
            )

    # ══════════════════════════════════════════════════════════════════════
    # F-04 — Handler para customers/update
    # ══════════════════════════════════════════════════════════════════════

    async def handle_customer_event(
        self,
        customer_id: str,
        topic: str,
    ) -> None:
        """Invalida el cache de perfil de cliente cuando Shopify notifica un cambio.

        Cuando llega customers/create o customers/update, el perfil cacheado en Redis
        bajo 'mcp:customer:profile:{customer_id}' puede estar desactualizado
        (nueva compra, cambio de tags, etc.). Este handler lo elimina para que el
        siguiente request haga un fetch fresco desde Shopify.

        Idempotency: usa el mismo patron SET NX que el resto de handlers.
        El customer_id se trata como page_id a efectos de la clave de idempotencia.

        Args:
            customer_id: ID numerico del cliente en Shopify (str).
            topic: 'customers/create' o 'customers/update'.
        """
        start_time = time.time()

        try:
            # ── Idempotency check ─────────────────────────────────────────
            # Usamos customer_id como identificador (mismo patron que page_id)
            if await self.is_duplicate_event(int(customer_id), topic):
                return

            logger.info(
                "webhook_customer_invalidating_cache",
                customer_id=customer_id,
                topic=topic,
            )

            # ── Invalidar cache via CustomerProfileService ────────────────
            from src.api.factories.service_factory import ServiceFactory
            cps = await ServiceFactory.get_customer_profile_service()
            await cps.invalidate(customer_id)

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "webhook_customer_processed",
                customer_id=customer_id,
                topic=topic,
                duration_ms=round(elapsed_ms, 2),
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "webhook_customer_failed",
                customer_id=customer_id,
                topic=topic,
                error=str(e),
                duration_ms=round(elapsed_ms, 2),
            )
            # No re-raise: la invalidacion de cache no es critica.
            # El perfil stale expirara en 24 h por TTL.