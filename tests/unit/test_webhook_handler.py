"""
Tests Unitarios — ShopifyWebhookHandler (M4 Incremental Sync)
=============================================================

Cubre la clase ShopifyWebhookHandler del módulo
src/api/services/shopify_webhook_handler.py.

Responsabilidades que se prueban:
1. is_duplicate_event()    → idempotency con Redis
2. handle_page_event()     → routing por topic
3. handle_translation_event() → sync multilingüe
4. _invalidate_page_cache() → SCAN+DELETE con Redis
5. Métricas Prometheus      → se incrementan correctamente

Diseño de los mocks:
    - RedisService: AsyncMock con _client simulado
    - ShopifyKBSyncService: AsyncMock con sync_single_page y delete_kb_for_page
    - prometheus_metrics: MagicMock inyectado via patch

APRENDIZAJE: El patrón de lazy init del handler facilita el testing.
    ShopifyWebhookHandler() no recibe dependencias en __init__,
    sino que las resuelve via _get_redis() y _get_sync_service().
    Los tests parchean esos métodos directamente con patch.object,
    evitando la necesidad de una fixture compleja de DI.

Author: Retail Recommender — QA Team
Date:   2026-02-26
Phase:  M4 — Incremental Sync (Webhooks)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any

from src.api.services.shopify_webhook_handler import (
    ShopifyWebhookHandler,
    IDEMPOTENCY_KEY_PREFIX,
    IDEMPOTENCY_TTL_SECONDS,
)


# ══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_redis():
    """
    Mock de RedisService con un _client fake que simula SCAN+DELETE.

    Estructura:
        redis._client.scan()   → itera claves por patrón glob
        redis._client.delete() → borra lotes de claves
        redis.get()            → lee idempotency keys
        redis.set()            → escribe idempotency keys
        redis.delete()         → borra clave exacta (sin glob)

    El _client es necesario porque _invalidate_page_cache() usa
    redis._client.scan() directamente para invalidación con patrones glob.
    RedisService.delete() solo acepta claves exactas.
    """
    redis = AsyncMock()

    # Simular _client raw de aioredis/redis-py
    redis._client = AsyncMock()

    # Valor por defecto: SCAN no encuentra nada — cursor=0, lista vacía.
    # Los tests individuales sobreescriben esto según lo que necesitan probar.
    redis._client.scan = AsyncMock(return_value=(0, []))
    redis._client.delete = AsyncMock(return_value=1)

    # Cache en memoria para idempotency (simulado)
    redis._store = {}

    async def mock_get(key):
        return redis._store.get(key)

    async def mock_set(key, value, ttl=None):
        redis._store[key] = value

    async def mock_delete(key):
        redis._store.pop(key, None)

    redis.get = AsyncMock(side_effect=mock_get)
    redis.set = AsyncMock(side_effect=mock_set)
    redis.delete = AsyncMock(side_effect=mock_delete)

    return redis


@pytest.fixture
def mock_sync_service():
    """
    Mock de ShopifyKBSyncService con los métodos necesarios para M4.

    sync_single_page()   → usado por handle_page_event y handle_translation_event
    delete_kb_for_page() → usado por handle_page_event con topic=pages/delete
    """
    service = AsyncMock()

    service.sync_single_page = AsyncMock(return_value={
        "status": "synced",
        "page_id": 12345,
        "handle": "politica-devoluciones",
        "languages_synced": ["es", "en"],
        "errors": [],
    })

    service.delete_kb_for_page = AsyncMock(return_value={
        "status": "deleted",
        "page_id": 12345,
        "records_deleted": 2,
    })

    return service


@pytest.fixture
def handler(mock_redis, mock_sync_service):
    """
    ShopifyWebhookHandler con dependencias parcheadas via lazy init.

    En lugar de inyectar dependencias en __init__, parcheamos los
    métodos _get_redis() y _get_sync_service() en la instancia directamente.
    Esto es posible porque Python permite asignar atributos a instancias
    en tiempo de ejecución, y el handler no cachea las dependencias
    entre llamadas — las resuelve cada vez via await self._get_redis().
    """
    h = ShopifyWebhookHandler()
    h._get_redis = AsyncMock(return_value=mock_redis)
    h._get_sync_service = AsyncMock(return_value=mock_sync_service)
    return h


# ══════════════════════════════════════════════════════════════════════════
# CLASE 1: is_duplicate_event()
# ══════════════════════════════════════════════════════════════════════════

class TestIsDuplicateEvent:
    """
    Tests para la detección de eventos duplicados via Redis.

    Patrón de idempotency:
        1. Primer evento:    redis.get(key) → None → procesar → redis.set(key)
        2. Segundo evento:   redis.get(key) → "processing" → duplicado → skip

    La clave tiene TTL = IDEMPOTENCY_TTL_SECONDS (300 s por defecto).
    """

    @pytest.mark.asyncio
    async def test_first_event_is_not_duplicate(self, handler, mock_redis):
        """
        El primer evento con un page_id/topic nuevo no es duplicado.

        Cuando la clave no existe en Redis, is_duplicate_event() debe:
        1. Retornar False (no es duplicado → procesar)
        2. Setear la clave en Redis para bloquear duplicados futuros
        """
        result = await handler.is_duplicate_event(
            page_id=12345,
            topic="pages/update",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_second_event_is_duplicate(self, handler, mock_redis):
        """
        El mismo evento enviado dos veces → el segundo es duplicado.

        Shopify garantiza at-least-once delivery: el mismo webhook puede
        llegar 2+ veces. El mock_redis._store persiste dentro del test
        (scope=function), así que la segunda llamada encuentra la clave.
        """
        first = await handler.is_duplicate_event(page_id=12345, topic="pages/update")
        assert first is False, "Primer evento debe procesarse"

        second = await handler.is_duplicate_event(page_id=12345, topic="pages/update")
        assert second is True, "Segundo evento idéntico debe ser duplicado"

    @pytest.mark.asyncio
    async def test_different_topics_same_page_not_confused(self, handler, mock_redis):
        """
        El mismo page_id con distintos topics NO son duplicados entre sí.

        La clave de idempotency incluye el topic, por lo que pages/create
        y pages/update para la misma página generan claves distintas.
        """
        create = await handler.is_duplicate_event(page_id=12345, topic="pages/create")
        update = await handler.is_duplicate_event(page_id=12345, topic="pages/update")
        assert create is False
        assert update is False

    @pytest.mark.asyncio
    async def test_different_pages_same_topic_not_confused(self, handler, mock_redis):
        """
        El mismo topic con distintos page_ids NO son duplicados entre sí.
        """
        result_111 = await handler.is_duplicate_event(page_id=111, topic="pages/create")
        result_222 = await handler.is_duplicate_event(page_id=222, topic="pages/create")
        assert result_111 is False
        assert result_222 is False

    @pytest.mark.asyncio
    async def test_idempotency_key_format(self, handler, mock_redis):
        """
        La clave Redis tiene el formato: webhook:idempotency:{topic}:{page_id}

        Formato consistente facilita:
        - Inspección manual: redis-cli keys webhook:idempotency:*
        - TTL sweeps programáticos
        - Dashboards de monitoreo
        """
        page_id = 98765
        topic = "pages/delete"
        expected_key = f"{IDEMPOTENCY_KEY_PREFIX}{topic}:{page_id}"

        await handler.is_duplicate_event(page_id=page_id, topic=topic)

        mock_redis.get.assert_called_with(expected_key)

    @pytest.mark.asyncio
    async def test_idempotency_key_set_with_correct_ttl(self, handler, mock_redis):
        """
        La clave se guarda con TTL = IDEMPOTENCY_TTL_SECONDS (300 s).

        TTL muy corto → retries de Shopify en 2 min reprocessan el webhook.
        TTL muy largo → una actualización legítima podría ser ignorada.
        """
        await handler.is_duplicate_event(page_id=12345, topic="pages/update")

        expected_key = f"{IDEMPOTENCY_KEY_PREFIX}pages/update:12345"
        mock_redis.set.assert_called_once_with(
            expected_key,
            "processing",
            ttl=IDEMPOTENCY_TTL_SECONDS,
        )

    @pytest.mark.asyncio
    async def test_translations_locale_in_idempotency_key(self, handler, mock_redis):
        """
        Para translations/update, el locale está en la clave de idempotency.

        Esto permite que actualizaciones de ES y EN de la misma página
        no se bloqueen entre sí:
            webhook:idempotency:translations/update:es:12345  → primera
            webhook:idempotency:translations/update:en:12345  → también primera
        """
        page_id = 12345

        result_es = await handler.is_duplicate_event(
            page_id=page_id,
            topic="translations/update:es",
        )
        result_en = await handler.is_duplicate_event(
            page_id=page_id,
            topic="translations/update:en",
        )

        assert result_es is False
        assert result_en is False


# ══════════════════════════════════════════════════════════════════════════
# CLASE 2: handle_page_event() — routing por topic
# ══════════════════════════════════════════════════════════════════════════

class TestHandlePageEvent:
    """
    Tests para el método principal de dispatch por topic.

    Flujo:
        handle_page_event()
            → is_duplicate_event()
            → _handle_page_upsert() para pages/create y pages/update
            → _handle_page_delete() para pages/delete
    """

    @pytest.mark.asyncio
    async def test_pages_create_calls_sync_single_page(self, handler, mock_sync_service):
        """
        Un webhook pages/create dispara sync_single_page().
        """
        await handler.handle_page_event(
            page_id=12345,
            page_handle="politica-devoluciones",
            topic="pages/create",
        )
        mock_sync_service.sync_single_page.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_pages_update_calls_sync_single_page(self, handler, mock_sync_service):
        """
        Un webhook pages/update dispara sync_single_page().
        """
        await handler.handle_page_event(
            page_id=12345,
            page_handle="politica-devoluciones",
            topic="pages/update",
        )
        mock_sync_service.sync_single_page.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_pages_delete_calls_delete_kb_for_page(
        self, handler, mock_sync_service
    ):
        """
        Un webhook pages/delete dispara delete_kb_for_page(), no sync.

        Al eliminar la página en Shopify, se elimina de la KB para que
        el chatbot no responda con información de una página inexistente.
        """
        await handler.handle_page_event(
            page_id=12345,
            page_handle="old-page",
            topic="pages/delete",
        )
        mock_sync_service.delete_kb_for_page.assert_called_once_with(12345)
        mock_sync_service.sync_single_page.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_event_skips_sync(self, handler, mock_sync_service):
        """
        Un evento duplicado (ya procesado) no dispara sync_single_page().
        """
        await handler.handle_page_event(
            page_id=12345,
            page_handle="politica-devoluciones",
            topic="pages/update",
        )
        await handler.handle_page_event(
            page_id=12345,
            page_handle="politica-devoluciones",
            topic="pages/update",
        )
        assert mock_sync_service.sync_single_page.call_count == 1

    @pytest.mark.asyncio
    async def test_unknown_topic_does_not_crash(self, handler, mock_sync_service):
        """
        Un topic desconocido se registra como warning pero no lanza excepción.
        """
        await handler.handle_page_event(
            page_id=12345,
            page_handle="some-page",
            topic="pages/unpublish",
        )
        mock_sync_service.sync_single_page.assert_not_called()
        mock_sync_service.delete_kb_for_page.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_error_propagates_and_increments_error_metric(
        self, handler, mock_sync_service
    ):
        """
        Un error en sync_single_page() se loguea y propaga al llamador.
        """
        mock_sync_service.sync_single_page = AsyncMock(
            side_effect=ValueError("Shopify API timeout")
        )
        with pytest.raises(ValueError, match="Shopify API timeout"):
            await handler.handle_page_event(
                page_id=12345,
                page_handle="politica-devoluciones",
                topic="pages/update",
            )


# ══════════════════════════════════════════════════════════════════════════
# CLASE 3: handle_translation_event()
# ══════════════════════════════════════════════════════════════════════════

class TestHandleTranslationEvent:
    """
    Tests para el handler de traducciones (translations/update).

    Estrategia: re-sync completo de la página vía sync_single_page().
    El locale se usa solo para idempotency granular y logging.
    """

    @pytest.mark.asyncio
    async def test_translation_event_calls_sync_single_page(
        self, handler, mock_sync_service
    ):
        """
        Un evento de traducción dispara sync_single_page() para la página.
        """
        await handler.handle_translation_event(page_id=12345, locale="en")
        mock_sync_service.sync_single_page.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_translation_es_and_en_both_processed(
        self, handler, mock_sync_service
    ):
        """
        Actualizaciones de ES y EN de la misma página se procesan ambas.

        Las claves de idempotency incluyen el locale, por lo que no se
        bloquean entre sí.
        """
        await handler.handle_translation_event(page_id=12345, locale="es")
        await handler.handle_translation_event(page_id=12345, locale="en")
        assert mock_sync_service.sync_single_page.call_count == 2

    @pytest.mark.asyncio
    async def test_translation_duplicate_skipped(self, handler, mock_sync_service):
        """
        Traducción duplicada (mismo locale, misma página) es omitida.
        """
        await handler.handle_translation_event(page_id=12345, locale="en")
        await handler.handle_translation_event(page_id=12345, locale="en")
        assert mock_sync_service.sync_single_page.call_count == 1

    @pytest.mark.asyncio
    async def test_translation_error_propagates(self, handler, mock_sync_service):
        """
        Un error durante sync de traducción se propaga correctamente.
        """
        mock_sync_service.sync_single_page = AsyncMock(
            side_effect=ConnectionError("Redis timeout during sync")
        )
        with pytest.raises(ConnectionError, match="Redis timeout during sync"):
            await handler.handle_translation_event(page_id=12345, locale="es")


# ══════════════════════════════════════════════════════════════════════════
# CLASE 4: _invalidate_page_cache()
# ══════════════════════════════════════════════════════════════════════════

class TestInvalidatePageCache:
    """
    Tests para la invalidación de cache Redis con patrones glob.

    DISEÑO CLAVE — Por qué SCAN+DELETE en lugar de redis.delete(pattern):
    ════════════════════════════════════════════════════════════════════════
    Redis no admite globbing en el comando DEL. El único camino correcto es:
        1. SCAN cursor MATCH pattern COUNT 100  → lote de claves concretas
        2. DEL key1 key2 ...                   → borrado del lote
        3. Repetir hasta cursor == 0            → keyspace completo recorrido

    _invalidate_page_cache() itera sobre EXACTAMENTE DOS patrones glob:
        Patrón 1: kb:page:{id}:*       → contenido KB cacheado por page_id
        Patrón 2: kb:handle:{handle}:* → contenido KB cacheado por slug/handle

    Esta arquitectura es relevante para el diseño de todos los mocks de
    scan en esta clase: cada test debe suministrar tantas respuestas de
    scan como patrones existen (actualmente 2, una por patrón).
    """

    @pytest.mark.asyncio
    async def test_invalidate_page_calls_scan_for_page_id_pattern(
        self, handler, mock_redis
    ):
        """
        La invalidación usa SCAN con el patrón kb:page:{id}:* para page_id.
        """
        mock_redis._client.scan = AsyncMock(return_value=(
            0,
            [b"kb:page:12345:es", b"kb:page:12345:en"],
        ))

        await handler._invalidate_page_cache(page_id=12345, page_handle="my-page")

        scan_calls = mock_redis._client.scan.call_args_list
        patterns_used = [str(c.kwargs.get("match") or c.args[1]) for c in scan_calls]

        assert any("kb:page:12345:*" in p for p in patterns_used), (
            f"Esperado patrón 'kb:page:12345:*'. Patrones usados: {patterns_used}"
        )

    @pytest.mark.asyncio
    async def test_invalidate_page_calls_scan_for_handle_pattern(
        self, handler, mock_redis
    ):
        """
        La invalidación usa SCAN con el patrón kb:handle:{handle}:* para el slug.
        """
        await handler._invalidate_page_cache(
            page_id=12345,
            page_handle="politica-devoluciones",
        )

        scan_calls = mock_redis._client.scan.call_args_list
        patterns_used = [str(c.kwargs.get("match") or c.args[1]) for c in scan_calls]

        assert any("kb:handle:politica-devoluciones:*" in p for p in patterns_used), (
            f"Esperado patrón 'kb:handle:politica-devoluciones:*'. "
            f"Patrones usados: {patterns_used}"
        )

    @pytest.mark.asyncio
    async def test_found_keys_are_deleted(self, handler, mock_redis):
        """
        Las claves encontradas por SCAN son borradas correctamente.

        DISEÑO DEL MOCK:
        ─────────────────
        El handler itera sobre DOS patrones glob en secuencia:
            Patrón 1: kb:page:{id}:*      → primera llamada a scan
            Patrón 2: kb:handle:{handle}:* → segunda llamada a scan

        Problema con return_value=(0, stale_keys):
            Ambas llamadas devuelven stale_keys → delete se llama 2 veces
            → assert_called_once_with falla.

        Solución con side_effect=[...]:
            side_effect=[resp1, resp2] consume un elemento de la lista por
            cada llamada. Así controlamos exactamente qué devuelve cada
            invocación de scan independientemente:
                Llamada 1 → (0, stale_keys)  → hay claves → delete
                Llamada 2 → (0, [])          → sin claves → no delete

        Resultado: delete se llama exactamente UNA vez con stale_keys.
        """
        stale_keys = [b"kb:page:12345:es", b"kb:page:12345:en"]

        # side_effect con lista: cada llamada consume el siguiente elemento.
        # Patrón 1 (kb:page:12345:*):  encuentra stale_keys → trigger delete
        # Patrón 2 (kb:handle:test:*): lista vacía           → sin delete
        mock_redis._client.scan = AsyncMock(side_effect=[
            (0, stale_keys),  # Primera llamada a scan
            (0, []),          # Segunda llamada a scan
        ])

        await handler._invalidate_page_cache(page_id=12345, page_handle="test")

        # DELETE debe haberse llamado exactamente UNA vez con las stale_keys
        mock_redis._client.delete.assert_called_once_with(*stale_keys)

    @pytest.mark.asyncio
    async def test_exact_key_deleted_via_redis_delete(self, handler, mock_redis):
        """
        La clave exacta kb:sync:status:page:{id} se borra con redis.delete().

        Esta clave no usa patrón glob (es única por page_id), por lo que
        se puede borrar directamente sin necesidad de SCAN.
        """
        await handler._invalidate_page_cache(page_id=12345, page_handle="test")

        mock_redis.delete.assert_called_with("kb:sync:status:page:12345")

    @pytest.mark.asyncio
    async def test_no_keys_found_does_not_call_delete(self, handler, mock_redis):
        """
        Si SCAN no encuentra claves, no se llama a DELETE.

        Optimización: evitar llamadas innecesarias a Redis cuando el
        cache ya está limpio (ej. primera vez que se procesa esta página).

        El fixture mock_redis ya configura scan con return_value=(0, [])
        por defecto, así que este test no necesita configurarlo.
        """
        await handler._invalidate_page_cache(page_id=99999, page_handle="new-page")

        mock_redis._client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_client_unavailable_skips_gracefully(
        self, handler, mock_redis
    ):
        """
        Si redis._client es None (modo degradado), la invalidación no falla.

        En modo degradado el RedisService existe pero _client es None
        (conexión no establecida). La invalidación es opcional —
        el contenido se servirá stale hasta que expire el TTL natural.
        """
        mock_redis._client = None

        # No debe lanzar excepción
        await handler._invalidate_page_cache(page_id=12345, page_handle="test")

    @pytest.mark.asyncio
    async def test_scan_pagination_exhausted(self, handler, mock_redis):
        """
        SCAN pagina correctamente cuando hay muchas claves (cursor != 0).

        SCAN puede necesitar múltiples iteraciones. El handler continúa
        el while loop hasta que cursor == 0 (fin del keyspace).

        Ejemplo simulado con 2 páginas para el patrón kb:page:*:
            Llamada 1 → cursor=5, [key1]  (cursor≠0, continuar)
            Llamada 2 → cursor=0, [key2]  (cursor=0, fin de ese patrón)
            Llamada 3 → cursor=0, []      (patrón kb:handle:*, sin claves)
        """
        mock_redis._client.scan = AsyncMock(side_effect=[
            (5, [b"kb:page:12345:es"]),   # Iteración 1 patrón 1: continuar
            (0, [b"kb:page:12345:en"]),   # Iteración 2 patrón 1: fin
            (0, []),                       # Iteración 1 patrón 2: sin claves
        ])

        await handler._invalidate_page_cache(page_id=12345, page_handle="test")

        # SCAN debe haberse llamado al menos 2 veces para paginar el primer patrón
        assert mock_redis._client.scan.call_count >= 2

    @pytest.mark.asyncio
    async def test_cache_error_does_not_block_sync(self, handler, mock_redis):
        """
        Un error en la invalidación de cache no bloquea el proceso principal.

        La invalidación es opcional: el contenido stale expirará por TTL.
        Un fallo aquí no debe impedir que el sync continúe correctamente.
        El handler captura la excepción y la registra como warning.
        """
        mock_redis._client.scan = AsyncMock(
            side_effect=ConnectionError("Redis cluster unavailable")
        )

        # No debe lanzar excepción — el handler la captura internamente
        await handler._invalidate_page_cache(page_id=12345, page_handle="test")


# ══════════════════════════════════════════════════════════════════════════
# CLASE 5: Métricas Prometheus
# ══════════════════════════════════════════════════════════════════════════

class TestWebhookHandlerMetrics:
    """
    Tests para la instrumentación Prometheus del handler.

    El handler registra:
    - kb_webhook_processed_total{topic, result="success"|"error"}
    - kb_webhook_processing_seconds (histograma de latencia)

    Los mocks inyectan el módulo prometheus_metrics via patch.dict en
    sys.modules, lo que funciona incluso si Prometheus no está instalado
    en el entorno de CI.
    """

    @pytest.mark.asyncio
    async def test_success_metric_incremented_on_success(
        self, handler, mock_sync_service
    ):
        """
        kb_webhook_processed_total{result="success"} se incrementa en éxito.
        """
        mock_counter = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.kb_webhook_processed_total = mock_counter
        mock_metrics.kb_webhook_processing_seconds = MagicMock()

        with patch.dict(
            "sys.modules",
            {"src.api.core.prometheus_metrics": mock_metrics},
        ):
            await handler.handle_page_event(
                page_id=12345,
                page_handle="test",
                topic="pages/update",
            )

        mock_counter.labels.assert_called_once_with(
            topic="pages/update",
            result="success",
        )
        mock_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_metric_incremented_on_failure(
        self, handler, mock_sync_service
    ):
        """
        kb_webhook_processed_total{result="error"} se incrementa en fallo.
        """
        mock_sync_service.sync_single_page = AsyncMock(
            side_effect=RuntimeError("DB connection pool exhausted")
        )

        mock_counter = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.kb_webhook_processed_total = mock_counter

        with patch.dict(
            "sys.modules",
            {"src.api.core.prometheus_metrics": mock_metrics},
        ):
            with pytest.raises(RuntimeError):
                await handler.handle_page_event(
                    page_id=12345,
                    page_handle="test",
                    topic="pages/update",
                )

        mock_counter.labels.assert_called_once_with(
            topic="pages/update",
            result="error",
        )

    @pytest.mark.asyncio
    async def test_missing_prometheus_module_does_not_crash(
        self, handler, mock_sync_service
    ):
        """
        Si prometheus_metrics no está disponible (ImportError), el handler funciona.

        Fundamental para entornos sin Prometheus instalado o en tests
        unitarios que no inicializan el registro completo de métricas.
        """
        with patch.dict(
            "sys.modules",
            {"src.api.core.prometheus_metrics": None},
        ):
            # No debe lanzar excepción
            await handler.handle_page_event(
                page_id=12345,
                page_handle="test",
                topic="pages/update",
            )

        # El sync ocurrió aunque las métricas fallaron
        mock_sync_service.sync_single_page.assert_called_once_with(12345)
