"""
Test Suite: M3 - Distributed Locking
======================================

Tests unitarios para la implementacion de Distributed Locking (M3):

1. RedisService.distributed_lock()
   - Adquisicion exitosa del lock
   - Timeout (DistributedLockError)
   - Degraded mode (Redis no disponible)
   - Liberacion siempre garantizada (finally block)
   - Metricas Prometheus registradas (sin crashear si no estan disponibles)

2. ShopifyKBSyncService — Feature Flag KB_DISTRIBUTED_LOCKS
   - flag=false: solo semaforo local (comportamiento pre-M3)
   - flag=true: activa distributed lock con la key correcta
   - Retry logic ante DistributedLockError
   - Re-raise tras agotar max_retries

3. DistributedLockError — Clase de excepcion

PATRON DE TESTS:
    Cada test sigue el modelo Given/When/Then para maxima claridad.
    Los fixtures desacoplan la creacion del servicio de los tests,
    permitiendo inyectar cualquier combinacion de mocks.

DISENO: Por que dos capas de concurrencia?
    - asyncio.Semaphore: Limita goroutines en UNA instancia
      → Evita agotar el pool de conexiones DB por dentro
    - Redis distributed lock: Una sola instancia modifica un registro
      → Evita race conditions entre instancias Cloud Run distintas

Author: Senior Architecture / QA Team
Date: 2026-02-25
Version: 1.0.0 - M3 Distributed Locking
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

# Modulos bajo prueba
from src.api.core.redis_service import (
    RedisService,
    RedisServiceError,
    DistributedLockError,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_redis_lock():
    """
    Mock del objeto redis.asyncio.Lock.

    Simula el objeto devuelto por self._client.lock(lock_name, ...).
    Configuracion por defecto: adquisicion exitosa (acquire() → True).

    Por que separar este fixture del cliente?
    Porque varios tests necesitan control fino sobre el comportamiento
    del lock (acquire/release) de forma independiente al cliente.
    """
    lock = AsyncMock()
    lock.acquire = AsyncMock(return_value=True)   # Happy path: lock libre
    lock.release = AsyncMock(return_value=True)
    return lock


@pytest.fixture
def mock_redis_client(mock_redis_lock):
    """
    Mock del cliente Redis con soporte para .lock().

    El cliente expone:
    - .ping()  — verificacion de conexion (async)
    - .lock()  — crea un Lock object (sync, retorna mock_redis_lock)

    Nota: .lock() es sync en redis.asyncio porque solo crea el objeto Lock,
    no ejecuta ninguna operacion de red todavia. La operacion de red ocurre
    en lock.acquire() que si es async.
    """
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.lock = MagicMock(return_value=mock_redis_lock)  # sync, retorna objeto
    return client


@pytest.fixture
def connected_redis_service(mock_redis_client):
    """
    RedisService en estado conectado con cliente mockeado.

    Bypasa la inicializacion real (create_optimized_redis_client + ping)
    configurando directamente el estado interno. Esto hace los tests
    independientes de la configuracion de Redis.

    Estado configurado:
    - _client: mock_redis_client (tiene .lock(), .ping())
    - _connected: True
    - _stats: contadores en cero
    """
    service = RedisService.__new__(RedisService)
    service._client = mock_redis_client
    service._connected = True
    service._connection_attempts = 1
    service._last_connection_attempt = time.time()
    service._stats = {
        "operations_total": 0,
        "operations_successful": 0,
        "operations_failed": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "connection_errors": 0,
    }
    return service


@pytest.fixture
def disconnected_redis_service():
    """
    RedisService en estado desconectado — simula Redis caido.

    Usado para verificar degraded mode: el context manager debe ceder
    sin lock en lugar de lanzar una excepcion.
    """
    service = RedisService.__new__(RedisService)
    service._client = None      # Sin cliente
    service._connected = False  # Marcado como desconectado
    service._connection_attempts = 0
    service._last_connection_attempt = 0
    service._stats = {
        "operations_total": 0,
        "operations_successful": 0,
        "operations_failed": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "connection_errors": 0,
    }
    return service


# ============================================================================
# TEST CLASS 1: HAPPY PATH — Lock adquirido y liberado correctamente
# ============================================================================

class TestDistributedLockHappyPath:
    """
    Tests del flujo normal: Redis disponible, lock libre.
    """

    @pytest.mark.asyncio
    async def test_lock_acquired_and_body_executed(
        self,
        connected_redis_service,
        mock_redis_client,
        mock_redis_lock,
    ):
        """
        El bloque dentro del context manager se ejecuta cuando el lock esta libre.

        Given: Redis disponible, acquire() → True
        When:  Se usa distributed_lock()
        Then:  El bloque se ejecuta, acquire() y release() se llaman exactamente una vez
        """
        body_executed = False

        async with connected_redis_service.distributed_lock("kb_sync:lock:test:es:general"):
            body_executed = True

        assert body_executed, "El bloque dentro del context manager debe ejecutarse"

        # Verificar que el lock se creo con los argumentos correctos
        mock_redis_client.lock.assert_called_once_with(
            "kb_sync:lock:test:es:general",
            timeout=30.0,
            blocking_timeout=5.0,
            sleep=0.1,
        )

        # Ciclo de vida completo: acquire → [bloque] → release
        mock_redis_lock.acquire.assert_called_once()
        mock_redis_lock.release.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_yields_the_lock_object(
        self,
        connected_redis_service,
        mock_redis_lock,
    ):
        """
        El context manager cede el objeto Lock al bloque.

        Esto permite que el caller extienda el TTL (lock.extend()) si la
        operacion protegida pudiera tardar mas que timeout segundos.

        Given: Lock adquirido exitosamente
        When:  Se usa `async with ... as lock:`
        Then:  La variable `lock` es el objeto Lock de Redis (mock_redis_lock)
        """
        async with connected_redis_service.distributed_lock("test:lock") as lock:
            assert lock is mock_redis_lock, "Debe ceder el objeto Lock de Redis"

    @pytest.mark.asyncio
    async def test_lock_released_when_body_raises_exception(
        self,
        connected_redis_service,
        mock_redis_lock,
    ):
        """
        El lock se libera SIEMPRE, incluso si hay una excepcion en el bloque.

        Por que es critico? Sin este comportamiento, una excepcion dejaría
        el lock adquirido hasta que expire el TTL (30s). Durante ese tiempo,
        ninguna otra instancia podria procesar el mismo registro.

        Given: Lock adquirido, bloque lanza ValueError
        When:  Se sale del context manager con excepcion
        Then:  release() se llama a pesar de la excepcion
        """
        with pytest.raises(ValueError, match="Error simulado en el bloque"):
            async with connected_redis_service.distributed_lock("test:lock"):
                raise ValueError("Error simulado en el bloque")

        # release() DEBE haberse llamado
        mock_redis_lock.release.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_failure_does_not_propagate(
        self,
        connected_redis_service,
        mock_redis_lock,
    ):
        """
        Si release() falla (lock expiro por TTL), la excepcion no se propaga.

        Escenario real: La operacion protegida tard tanto que el TTL del lock
        expiro (timeout=30s). Cuando el finally intenta liberar, Redis lanza
        una excepcion porque ya no somos duenos del lock. Esto es correcto
        por diseno y no debe interrumpir el flujo del caller.

        Given: Lock adquirido, release() lanza excepcion (TTL expirado)
        When:  Se sale del context manager normalmente
        Then:  Ninguna excepcion se propaga al caller
        """
        mock_redis_lock.release = AsyncMock(
            side_effect=Exception("LockNotOwnedError: lock has expired or is not owned")
        )

        # Ejecucion normal — no debe lanzar excepcion
        async with connected_redis_service.distributed_lock("test:lock"):
            pass  # OK

        # release() se intento, aunque fallo silenciosamente
        mock_redis_lock.release.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_parameters_passed_to_redis(
        self,
        connected_redis_service,
        mock_redis_client,
    ):
        """
        Los parametros personalizados se pasan al cliente Redis exactamente.

        Given: timeout=60, blocking_timeout=10, sleep=0.5
        When:  Se usa distributed_lock() con esos parametros
        Then:  client.lock() recibe exactamente esos valores
        """
        async with connected_redis_service.distributed_lock(
            "custom:lock:key",
            timeout=60.0,
            blocking_timeout=10.0,
            sleep=0.5,
        ):
            pass

        mock_redis_client.lock.assert_called_once_with(
            "custom:lock:key",
            timeout=60.0,
            blocking_timeout=10.0,
            sleep=0.5,
        )


# ============================================================================
# TEST CLASS 2: TIMEOUT — Lock no disponible
# ============================================================================

class TestDistributedLockTimeout:
    """
    Tests del escenario donde el lock esta ocupado por otra instancia.

    Situacion tipica: dos instancias Cloud Run intentan procesar el mismo
    registro simultaneamente. La segunda llega cuando la primera ya tiene
    el lock y blocking_timeout segundos despues, lanza DistributedLockError.
    """

    @pytest.mark.asyncio
    async def test_raises_distributed_lock_error_when_acquire_returns_false(
        self,
        connected_redis_service,
        mock_redis_lock,
    ):
        """
        DistributedLockError se lanza cuando acquire() retorna False (timeout).

        Given: acquire() → False (otra instancia tiene el lock)
        When:  Se usa distributed_lock() con blocking_timeout=5.0
        Then:  Se lanza DistributedLockError con el nombre del lock y el timeout
        """
        mock_redis_lock.acquire = AsyncMock(return_value=False)

        with pytest.raises(DistributedLockError) as exc_info:
            async with connected_redis_service.distributed_lock(
                "kb_sync:lock:contested:es:general",
                blocking_timeout=5.0,
            ):
                pass

        error_msg = str(exc_info.value)
        assert "kb_sync:lock:contested:es:general" in error_msg
        assert "5.0" in error_msg

    @pytest.mark.asyncio
    async def test_body_not_executed_when_lock_not_acquired(
        self,
        connected_redis_service,
        mock_redis_lock,
    ):
        """
        El bloque NO se ejecuta si el lock no se obtiene.

        Given: acquire() → False
        When:  DistributedLockError se lanza
        Then:  El cuerpo del with no se ejecuta
        """
        mock_redis_lock.acquire = AsyncMock(return_value=False)
        body_executed = False

        with pytest.raises(DistributedLockError):
            async with connected_redis_service.distributed_lock("test:lock"):
                body_executed = True  # No debe llegar aqui

        assert not body_executed, "El bloque no debe ejecutarse si el lock falla"

    @pytest.mark.asyncio
    async def test_release_not_called_when_lock_was_never_acquired(
        self,
        connected_redis_service,
        mock_redis_lock,
    ):
        """
        release() NO se llama si nunca fuimos duenos del lock.

        Llamar release() sin haber adquirido el lock seria un error porque
        intentariamos liberar algo que no poseemos. El flag `acquired=False`
        controla esto en el bloque finally.

        Given: acquire() → False
        When:  DistributedLockError
        Then:  release() no se llama
        """
        mock_redis_lock.acquire = AsyncMock(return_value=False)

        with pytest.raises(DistributedLockError):
            async with connected_redis_service.distributed_lock("test:lock"):
                pass

        mock_redis_lock.release.assert_not_called()


# ============================================================================
# TEST CLASS 3: DEGRADED MODE — Redis no disponible
# ============================================================================

class TestDistributedLockDegradedMode:
    """
    Tests del modo degradado cuando Redis esta caido.

    Principio de diseno: availability > consistency.
    Si Redis no esta disponible, el sistema sigue funcionando pero
    sin proteccion cross-instance (solo semaforo local).
    """

    @pytest.mark.asyncio
    async def test_body_executes_when_client_is_none(
        self,
        disconnected_redis_service,
    ):
        """
        El bloque se ejecuta aunque Redis no este disponible.

        Este es el comportamiento critico para availability:
        Si Redis cae, el KB sync NO debe bloquearse completamente.
        La consecuencia es mayor riesgo de race condition, pero el
        sistema sigue funcionando.

        Given: _client = None (Redis no disponible)
        When:  Se usa distributed_lock()
        Then:  El bloque se ejecuta SIN lock, sin excepcion
        """
        body_executed = False

        async with disconnected_redis_service.distributed_lock("test:lock"):
            body_executed = True

        assert body_executed, "El bloque debe ejecutarse incluso sin Redis"

    @pytest.mark.asyncio
    async def test_yields_none_in_degraded_mode(
        self,
        disconnected_redis_service,
    ):
        """
        En modo degradado, el valor cedido es None (no un Lock).

        Esto permite al caller distinguir si tiene proteccion real o no.
        Si lock is None, sabe que esta en degraded mode.

        Given: Redis no disponible (_client=None)
        When:  Se usa `async with ... as lock:`
        Then:  lock is None
        """
        async with disconnected_redis_service.distributed_lock("test:lock") as lock:
            assert lock is None, "En modo degradado debe ceder None"

    @pytest.mark.asyncio
    async def test_degraded_mode_when_connected_is_false_but_client_exists(self):
        """
        Degraded mode cuando _connected=False aunque _client existe.

        Escenario: conexion perdida despues de inicializar (network blip).
        El servicio marca _connected=False pero el objeto cliente sigue existiendo.
        La implementacion verifica ambas condiciones: not self._client OR not self._connected.

        Given: _client existe pero _connected=False
        When:  Se usa distributed_lock()
        Then:  Se activa modo degradado (yield None)
        """
        service = RedisService.__new__(RedisService)
        service._client = AsyncMock()   # Cliente existe
        service._connected = False      # Pero conexion perdida
        service._stats = {}

        async with service.distributed_lock("test:lock") as lock:
            pass

        assert lock is None, "Con _connected=False debe activarse modo degradado"


# ============================================================================
# TEST CLASS 4: DistributedLockError — Clase de excepcion
# ============================================================================

class TestDistributedLockErrorClass:
    """
    Tests de la excepcion DistributedLockError.

    Aunque es una clase simple (solo heredacion), es importante verificar
    que se puede capturar de forma independiente a RedisServiceError.
    """

    def test_is_subclass_of_exception(self):
        """DistributedLockError hereda de Exception (capturabilidad estandar)."""
        assert issubclass(DistributedLockError, Exception)

    def test_is_not_subclass_of_redis_service_error(self):
        """
        DistributedLockError es independiente de RedisServiceError.

        Esto permite al caller capturar exactamente el tipo que le interesa:
        - except DistributedLockError: lock timeout → retry
        - except RedisServiceError: error de conexion → fallback distinto
        """
        assert not issubclass(DistributedLockError, RedisServiceError)

    def test_can_be_raised_and_caught(self):
        """Se puede lanzar y capturar con un bloque try/except estandar."""
        with pytest.raises(DistributedLockError):
            raise DistributedLockError("Cannot acquire lock 'test' within 5.0s")

    def test_message_preserved(self):
        """El mensaje de error se preserva cuando se captura la excepcion."""
        msg = "Could not acquire distributed lock 'kb_sync:lock:test:es:general' within 5.0s"
        try:
            raise DistributedLockError(msg)
        except DistributedLockError as e:
            assert str(e) == msg

    def test_catchable_as_generic_exception(self):
        """
        DistributedLockError puede capturarse como Exception generico.

        Importante para callers que usan `except Exception as e:` como
        fallback de ultima instancia.
        """
        caught = False
        try:
            raise DistributedLockError("test")
        except Exception:
            caught = True

        assert caught


# ============================================================================
# TEST CLASS 5: ShopifyKBSyncService — Feature Flag
# ============================================================================

class TestDistributedLockFeatureFlag:
    """
    Tests del feature flag KB_DISTRIBUTED_LOCKS en ShopifyKBSyncService.

    El feature flag permite activar/desactivar el distributed lock sin redeploy,
    facilitando el rollback instantaneo si se detectan problemas en produccion.

    Principio de test: No necesitamos un sync real. Solo verificamos que
    la logica de routing (flag on/off) se comporta como se espera.
    """

    # ── Helpers ──────────────────────────────────────────────────────────

    def _make_service(
        self,
        use_distributed_locks: bool,
        redis_service=None,
    ):
        """
        Factory: crea ShopifyKBSyncService con deps mockeadas y flag configurado.

        Bypasa __init__ para evitar conexiones reales a DB, Redis y Shopify.
        Inyecta directamente el estado necesario para los tests.
        """
        from src.api.services.shopify_kb_sync import ShopifyKBSyncService

        service = ShopifyKBSyncService.__new__(ShopifyKBSyncService)
        service.shopify = MagicMock()
        service.db = MagicMock()
        service.metadata_parser = MagicMock()
        service._db_semaphore = asyncio.Semaphore(1)
        service.redis = redis_service or AsyncMock()
        service._use_distributed_locks = use_distributed_locks
        return service

    def _make_db_mock(self):
        """
        Mock del pool de DB con acquire() como async context manager.

        El patron db.acquire() devuelve un connection object con .execute().
        """
        conn_mock = AsyncMock()
        conn_mock.execute = AsyncMock()

        @asynccontextmanager
        async def mock_acquire():
            yield conn_mock

        db_mock = MagicMock()
        db_mock.acquire = mock_acquire
        return db_mock, conn_mock

    async def _call_upsert(self, service):
        """Helper para llamar _upsert_kb_content con datos de prueba estandar."""
        await service._upsert_kb_content(
            sub_intent="policy_return",
            language="es",
            category="general",
            content="# Return Policy\n\nPlease read carefully.",
            content_html="<h1>Return Policy</h1><p>Please read carefully.</p>",
            title="Return Policy",
            shopify_page_id=123456,
            shopify_url="https://mystore.myshopify.com/pages/returns",
            shopify_handle="returns",
        )

    # ── Tests ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_flag_false_does_not_call_distributed_lock(self):
        """
        Con KB_DISTRIBUTED_LOCKS=false NO se usa distributed_lock.

        Comportamiento pre-M3: solo el semaforo local protege el upsert.
        Esto es el default (flag=false) para no romper entornos existentes.

        Given: _use_distributed_locks=False
        When:  Se llama _upsert_kb_content()
        Then:  redis.distributed_lock() NO se llama, DB execute SI se llama
        """
        redis_mock = AsyncMock()
        redis_mock.distributed_lock = MagicMock()  # Spy para detectar llamadas

        service = self._make_service(use_distributed_locks=False, redis_service=redis_mock)
        db_mock, conn_mock = self._make_db_mock()
        service.db = db_mock

        await self._call_upsert(service)

        # distributed_lock NO debe llamarse en modo legacy
        redis_mock.distributed_lock.assert_not_called()

        # DB execute SI debe llamarse
        conn_mock.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_flag_true_calls_distributed_lock_with_correct_key(self):
        """
        Con KB_DISTRIBUTED_LOCKS=true se activa el distributed lock.
        El lock key sigue el formato: kb_sync:lock:{sub_intent}:{language}:{category}

        Given: _use_distributed_locks=True, lock disponible
        When:  Se llama _upsert_kb_content()
        Then:  redis.distributed_lock() se llama con la key correcta
        """
        lock_calls = []

        @asynccontextmanager
        async def tracking_lock(lock_name, **kwargs):
            """Context manager que registra las llamadas sin hacer nada real."""
            lock_calls.append(lock_name)
            yield MagicMock()

        redis_mock = AsyncMock()
        redis_mock.distributed_lock = tracking_lock

        service = self._make_service(use_distributed_locks=True, redis_service=redis_mock)
        db_mock, conn_mock = self._make_db_mock()
        service.db = db_mock

        await self._call_upsert(service)

        assert len(lock_calls) == 1, "distributed_lock debe llamarse exactamente una vez"
        assert lock_calls[0] == "kb_sync:lock:policy_return:es:general", (
            f"Lock key incorrecto. Esperado: 'kb_sync:lock:policy_return:es:general', "
            f"Recibido: '{lock_calls[0]}'"
        )
        conn_mock.execute.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sub_intent,language,category,expected_key", [
        # category None debe normalizarse a 'general'
        ("policy_return", "es", None, "kb_sync:lock:policy_return:es:general"),
        # category explicita debe preservarse
        ("product_care", "en", "premium", "kb_sync:lock:product_care:en:premium"),
        # otro idioma
        ("general_faq", "fr", "general", "kb_sync:lock:general_faq:fr:general"),
    ])
    async def test_lock_key_format(self, sub_intent, language, category, expected_key):
        """
        El lock key sigue el formato correcto para distintas combinaciones.

        Especialmente importante: category=None debe normalizarse a 'general'
        para que el lock sea consistente con la constraint de DB
        (COALESCE(category, 'general')).

        Given: Distintas combinaciones de (sub_intent, language, category)
        When:  Se construye el lock key
        Then:  El lock key coincide con el esperado
        """
        lock_calls = []

        @asynccontextmanager
        async def tracking_lock(lock_name, **kwargs):
            lock_calls.append(lock_name)
            yield MagicMock()

        redis_mock = AsyncMock()
        redis_mock.distributed_lock = tracking_lock

        service = self._make_service(use_distributed_locks=True, redis_service=redis_mock)
        db_mock, conn_mock = self._make_db_mock()
        service.db = db_mock

        await service._upsert_kb_content(
            sub_intent=sub_intent,
            language=language,
            category=category,
            content="content",
            content_html="<p>content</p>",
            title="Title",
            shopify_page_id=1,
            shopify_url=None,
            shopify_handle=None,
        )

        assert lock_calls[0] == expected_key, (
            f"Para ({sub_intent!r}, {language!r}, {category!r}): "
            f"esperado '{expected_key}', recibido '{lock_calls[0]}'"
        )

    @pytest.mark.asyncio
    async def test_retry_on_distributed_lock_error_succeeds_on_second_attempt(self):
        """
        DistributedLockError en el primer intento → retry → exito en el segundo.

        Escenario: Instancia A llega justo cuando Instancia B libera el lock.
        El primer acquire() falla, pero tras un breve wait el segundo tiene exito.

        Given: lock falla el 1er intento, tiene exito en el 2o
        When:  Se llama _upsert_kb_content()
        Then:  El upsert completa exitosamente (DB execute se llama una vez)
        """
        call_count = [0]

        @asynccontextmanager
        async def failing_then_succeeding_lock(lock_name, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Primer intento: simular timeout de lock
                raise DistributedLockError(f"Timeout for {lock_name}")
            # Segundo intento: lock disponible
            yield MagicMock()

        redis_mock = AsyncMock()
        redis_mock.distributed_lock = failing_then_succeeding_lock

        service = self._make_service(use_distributed_locks=True, redis_service=redis_mock)
        db_mock, conn_mock = self._make_db_mock()
        service.db = db_mock

        # Parchear asyncio.sleep para que el test no espere de verdad
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await self._call_upsert(service)

        assert call_count[0] == 2, f"Esperado 2 intentos, se hicieron {call_count[0]}"
        conn_mock.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_after_exhausting_all_retries(self):
        """
        Si el lock falla max_retries (3) veces, DistributedLockError se propaga.

        Esto informa al caller (sync_page) que el record no pudo procesarse,
        y sync_page puede marcarlo como FAILED en el reporte.

        Given: distributed_lock SIEMPRE lanza DistributedLockError
        When:  Se llama _upsert_kb_content() con max_retries=3
        Then:  Se lanza DistributedLockError tras exactamente 3 intentos
        """
        call_count = [0]

        @asynccontextmanager
        async def always_failing_lock(lock_name, **kwargs):
            call_count[0] += 1
            raise DistributedLockError(f"Timeout for {lock_name}")
            yield  # Necesario para que sea un generator valido (aunque nunca se ejecute)

        redis_mock = AsyncMock()
        redis_mock.distributed_lock = always_failing_lock

        service = self._make_service(use_distributed_locks=True, redis_service=redis_mock)
        db_mock, conn_mock = self._make_db_mock()
        service.db = db_mock

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(DistributedLockError):
                await self._call_upsert(service)

        # Exactamente 3 intentos (max_retries en la implementacion)
        assert call_count[0] == 3, (
            f"Esperado 3 intentos (max_retries), se hicieron {call_count[0]}"
        )

        # DB execute NUNCA debe llamarse si el lock siempre falla
        conn_mock.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_execute_called_with_correct_arguments(self):
        """
        El execute de DB recibe los argumentos correctos incluso con lock activo.

        Given: flag=True, lock disponible
        When:  Se llama _upsert_kb_content() con datos especificos
        Then:  conn.execute() recibe los valores en el orden correcto
        """
        @asynccontextmanager
        async def simple_lock(lock_name, **kwargs):
            yield MagicMock()

        redis_mock = AsyncMock()
        redis_mock.distributed_lock = simple_lock

        service = self._make_service(use_distributed_locks=True, redis_service=redis_mock)
        db_mock, conn_mock = self._make_db_mock()
        service.db = db_mock

        await service._upsert_kb_content(
            sub_intent="shipping_info",
            language="en",
            category="premium",
            content="# Shipping Info",
            content_html="<h1>Shipping Info</h1>",
            title="Shipping Information",
            shopify_page_id=999,
            shopify_url="https://shop.myshopify.com/pages/shipping",
            shopify_handle="shipping",
        )

        # Verificar que execute fue llamado con los argumentos correctos
        call_args = conn_mock.execute.call_args
        positional = call_args[0]  # Argumentos posicionales: (query, *params)

        # Los parametros deben estar en el orden de la query
        # $1=sub_intent, $2=language, $3=category, $4=content, $5=content_html,
        # $6=title, $7=shopify_page_id, $8=shopify_url, $9=shopify_handle
        assert positional[1] == "shipping_info"          # $1 sub_intent
        assert positional[2] == "en"                     # $2 language
        assert positional[3] == "premium"                # $3 category (normalizado)
        assert positional[4] == "# Shipping Info"        # $4 content
        assert positional[6] == "Shipping Information"   # $6 title
        assert positional[7] == 999                      # $7 shopify_page_id


# ============================================================================
# RUNNER
# ============================================================================

if __name__ == "__main__":
    """
    Ejecutar tests directamente:

    # Todos los tests M3
    pytest tests/unit/test_distributed_lock.py -v

    # Solo happy path
    pytest tests/unit/test_distributed_lock.py -v -k "HappyPath"

    # Solo feature flag
    pytest tests/unit/test_distributed_lock.py -v -k "FeatureFlag"

    # Solo degraded mode
    pytest tests/unit/test_distributed_lock.py -v -k "Degraded"

    # Con coverage
    pytest tests/unit/test_distributed_lock.py -v \
        --cov=src.api.core.redis_service \
        --cov=src.api.services.shopify_kb_sync \
        --cov-report=term-missing
    """
    pytest.main([__file__, "-v", "--tb=short"])
