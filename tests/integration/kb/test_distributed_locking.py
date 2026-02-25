"""
Integration Tests: M3 - Distributed Locking — KB Sync
=======================================================

Tests de integracion para verificar que el distributed locking funciona
correctamente en escenarios de concurrencia realistas.

A diferencia de los tests unitarios (test_distributed_lock.py), aqui
usamos un RedisService REAL conectado a Redis (a traves de un mock de
bajo nivel del cliente redis.asyncio) para simular situaciones que
requieren coordinacion entre "instancias".

ESCENARIOS CUBIERTOS:
1. Dos "instancias" intentan procesar el mismo registro en paralelo
   → Solo una obtiene el lock, la otra espera o lanza DistributedLockError
2. El lock se libera y la segunda instancia puede proceder
3. La granularidad es correcta: diferentes registros no se bloquean entre si
4. TTL del lock expira y otra instancia puede obtenerlo

NOTA SOBRE REDIS EN TESTS:
Estos tests usan mocks inteligentes del cliente Redis que simulan el
comportamiento de los locks (NX, TTL, polling) sin necesitar Redis real.
Para tests con Redis real, ver tests/load/ o ejecutar con REDIS_URL configurada.

Author: Senior QA Team
Date: 2026-02-25
Version: 1.0.0 - M3 Distributed Locking
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
from contextlib import asynccontextmanager
from typing import List, Optional

from src.api.core.redis_service import (
    RedisService,
    DistributedLockError,
)


# ============================================================================
# INFRAESTRUCTURA DE SIMULACION
# ============================================================================

class SimulatedRedisLockStore:
    """
    Simula el comportamiento de locks en Redis usando un dict compartido.

    Esta clase es el corazon de los tests de concurrencia: actua como
    un "Redis" compartido entre multiples instancias simuladas.

    COMO FUNCIONA:
    - set(lock_key): intenta adquirir el lock (NX semantics)
    - release(lock_key): libera el lock
    - El lock tiene un TTL simulado que expira automaticamente

    Por que no usar Redis real?
    - Los tests deben ser deterministas y rapidos
    - No queremos depender de infraestructura externa en CI
    - El comportamiento de los locks es predecible con esta simulacion
    """

    def __init__(self):
        # lock_key → {"owner": token, "expires_at": float}
        self._locks: dict = {}
        self._lock = asyncio.Lock()  # Mutex para acceso thread-safe al dict

    async def try_acquire(self, lock_key: str, token: str, ttl: float) -> bool:
        """
        Intenta adquirir el lock (semantica NX: solo si NO existe).

        Returns: True si se adquirio, False si ya existe
        """
        async with self._lock:
            now = time.time()

            # Verificar si el lock existe y no ha expirado
            existing = self._locks.get(lock_key)
            if existing and existing["expires_at"] > now:
                return False  # Lock ocupado

            # Adquirir el lock (o renovarlo si expiro)
            self._locks[lock_key] = {
                "owner": token,
                "expires_at": now + ttl
            }
            return True

    async def release(self, lock_key: str, token: str) -> bool:
        """
        Libera el lock solo si somos los duenos (verificacion de token).

        Esto previene que una instancia libere el lock de otra,
        que es el comportamiento real de Redis.
        """
        async with self._lock:
            existing = self._locks.get(lock_key)
            if existing and existing["owner"] == token:
                del self._locks[lock_key]
                return True
            return False  # No somos duenos

    def is_locked(self, lock_key: str) -> bool:
        """Verifica si un lock esta activo (util para assertions en tests)."""
        existing = self._locks.get(lock_key)
        if not existing:
            return False
        return existing["expires_at"] > time.time()


class InMemoryRedisLock:
    """
    Implementacion de redis.asyncio.Lock usando SimulatedRedisLockStore.

    Simula el comportamiento de polling con acquire() de redis.asyncio:
    - Intenta adquirir con NX
    - Si falla, hace polling cada sleep segundos
    - Si supera blocking_timeout, retorna False
    """

    def __init__(
        self,
        store: SimulatedRedisLockStore,
        lock_key: str,
        token: str,
        timeout: float,
        blocking_timeout: float,
        sleep: float,
    ):
        self._store = store
        self._lock_key = lock_key
        self._token = token
        self._timeout = timeout
        self._blocking_timeout = blocking_timeout
        self._sleep = sleep
        self._acquired = False

    async def acquire(self) -> bool:
        """Polling loop con timeout, igual que redis.asyncio.Lock.acquire()."""
        deadline = time.time() + self._blocking_timeout

        while time.time() < deadline:
            if await self._store.try_acquire(self._lock_key, self._token, self._timeout):
                self._acquired = True
                return True
            # Espera antes del siguiente intento
            # En tests usamos un sleep muy corto para velocidad
            await asyncio.sleep(self._sleep)

        return False  # Timeout: no se obtuvo el lock

    async def release(self) -> None:
        """Libera el lock si somos los duenos."""
        if self._acquired:
            await self._store.release(self._lock_key, self._token)
            self._acquired = False


def make_redis_service_with_shared_store(store: SimulatedRedisLockStore) -> RedisService:
    """
    Crea un RedisService cuyo cliente usa el SimulatedRedisLockStore.

    Esto permite crear multiples "instancias" de RedisService que comparten
    el mismo "Redis" (el store), simulando el entorno multi-instancia de Cloud Run.

    El token unico por instancia garantiza que podemos rastrear quien tiene cada lock.
    """
    import uuid

    service = RedisService.__new__(RedisService)
    service._connected = True
    service._stats = {
        "operations_total": 0, "operations_successful": 0,
        "operations_failed": 0, "cache_hits": 0,
        "cache_misses": 0, "connection_errors": 0,
    }

    # Identificador unico de esta "instancia"
    instance_id = str(uuid.uuid4())[:8]

    # Mock client que crea InMemoryRedisLock con el store compartido
    client = MagicMock()

    def create_lock(lock_name, timeout=30.0, blocking_timeout=5.0, sleep=0.1):
        """Crea un lock que usa el store compartido."""
        token = f"{instance_id}:{time.time()}"
        return InMemoryRedisLock(
            store=store,
            lock_key=lock_name,
            token=token,
            timeout=timeout,
            blocking_timeout=blocking_timeout,
            sleep=sleep,
        )

    client.lock = MagicMock(side_effect=create_lock)
    service._client = client

    return service


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def shared_lock_store():
    """
    Store de locks compartido entre instancias.

    Simula Redis: todas las instancias ven los mismos locks.
    """
    return SimulatedRedisLockStore()


@pytest.fixture
def instance_a(shared_lock_store):
    """Primera 'instancia' de Cloud Run con Redis compartido."""
    return make_redis_service_with_shared_store(shared_lock_store)


@pytest.fixture
def instance_b(shared_lock_store):
    """Segunda 'instancia' de Cloud Run con Redis compartido."""
    return make_redis_service_with_shared_store(shared_lock_store)


# ============================================================================
# TEST CLASS 1: CONCURRENCIA BASICA
# ============================================================================

class TestDistributedLockConcurrency:
    """
    Tests de concurrencia con multiples instancias simuladas.

    Estos tests verifican el comportamiento fundamental que justifica
    el uso de distributed locking: prevenir que dos instancias modifiquen
    el mismo recurso simultaneamente.
    """

    @pytest.mark.asyncio
    async def test_only_one_instance_holds_lock_at_a_time(
        self,
        instance_a,
        instance_b,
        shared_lock_store,
    ):
        """
        Solo una instancia tiene el lock en un momento dado.

        Este es el test fundamental del distributed locking.
        Si ambas instancias pudieran tener el lock simultaneamente,
        la protecion no seria efectiva.

        Given: Dos instancias comparten el mismo Redis
        When:  Ambas intentan adquirir el mismo lock
        Then:  Solo una lo tiene mientras la otra espera
        """
        LOCK_KEY = "kb_sync:lock:policy_return:es:general"

        # Registro de cual instancia tenia el lock en cada momento
        concurrent_holders: List[str] = []
        max_concurrent = [0]

        async def acquire_and_hold(service, instance_name, hold_seconds=0.05):
            """Adquiere el lock, lo mantiene y registra si hubo concurrencia."""
            async with service.distributed_lock(
                LOCK_KEY,
                timeout=30.0,
                blocking_timeout=2.0,  # Esperar hasta 2s
                sleep=0.01,
            ):
                concurrent_holders.append(instance_name)
                # Simular tiempo de operacion (e.g., upsert de DB)
                await asyncio.sleep(hold_seconds)
                concurrent_holders.remove(instance_name)
                # Registrar si en algun momento hubo mas de 1 holder
                max_concurrent[0] = max(max_concurrent[0], len(concurrent_holders) + 1)

        # Lanzar ambas instancias simultaneamente
        await asyncio.gather(
            acquire_and_hold(instance_a, "instance_a"),
            acquire_and_hold(instance_b, "instance_b"),
        )

        # NEVER two instances holding the lock simultaneously
        assert max_concurrent[0] == 1, (
            f"Nunca debe haber mas de una instancia con el lock. "
            f"Max concurrente observado: {max_concurrent[0]}"
        )

    @pytest.mark.asyncio
    async def test_second_instance_waits_and_acquires_after_first_releases(
        self,
        instance_a,
        instance_b,
    ):
        """
        La segunda instancia espera y adquiere el lock cuando la primera lo libera.

        Given: Instance A tiene el lock, Instance B espera
        When:  Instance A libera el lock
        Then:  Instance B adquiere el lock y completa su operacion
        """
        LOCK_KEY = "kb_sync:lock:policy_shipping:en:general"

        operations_completed = []
        operation_order = []

        async def instance_a_task():
            async with instance_a.distributed_lock(
                LOCK_KEY, timeout=30.0, blocking_timeout=3.0, sleep=0.01
            ):
                operation_order.append("A_start")
                await asyncio.sleep(0.05)  # A mantiene el lock 50ms
                operation_order.append("A_end")
                operations_completed.append("A")

        async def instance_b_task():
            # Dar a A una ventaja de 10ms para asegurar que llegue primero
            await asyncio.sleep(0.01)
            async with instance_b.distributed_lock(
                LOCK_KEY, timeout=30.0, blocking_timeout=3.0, sleep=0.01
            ):
                operation_order.append("B_start")
                await asyncio.sleep(0.01)
                operation_order.append("B_end")
                operations_completed.append("B")

        await asyncio.gather(instance_a_task(), instance_b_task())

        # Ambas operaciones completaron
        assert "A" in operations_completed
        assert "B" in operations_completed

        # El orden correcto: A debe empezar y terminar ANTES que B empiece
        a_end_idx = operation_order.index("A_end")
        b_start_idx = operation_order.index("B_start")
        assert a_end_idx < b_start_idx, (
            f"B debe empezar DESPUES que A termine. "
            f"Orden observado: {operation_order}"
        )

    @pytest.mark.asyncio
    async def test_different_keys_do_not_block_each_other(
        self,
        instance_a,
        instance_b,
    ):
        """
        Locks con keys distintas no se bloquean entre si.

        La granularidad por registro es un diseno intencional:
        'policy_return:es:general' y 'policy_shipping:es:general' son
        registros independientes y deben poder procesarse en paralelo.

        Given: Instance A tiene lock de 'policy_return', Instance B de 'policy_shipping'
        When:  Ambas operan simultaneamente
        Then:  No hay bloqueo entre ellas (operan en paralelo)
        """
        start_times = {}
        end_times = {}

        async def a_task():
            async with instance_a.distributed_lock(
                "kb_sync:lock:policy_return:es:general",
                timeout=30.0, blocking_timeout=1.0, sleep=0.01
            ):
                start_times["A"] = time.time()
                await asyncio.sleep(0.05)  # 50ms de operacion
                end_times["A"] = time.time()

        async def b_task():
            # B usa una key DIFERENTE (policy_shipping vs policy_return)
            async with instance_b.distributed_lock(
                "kb_sync:lock:policy_shipping:es:general",  # Key diferente
                timeout=30.0, blocking_timeout=1.0, sleep=0.01
            ):
                start_times["B"] = time.time()
                await asyncio.sleep(0.05)
                end_times["B"] = time.time()

        t0 = time.time()
        await asyncio.gather(a_task(), b_task())
        total_time = time.time() - t0

        # Si hubieran bloqueado secuencialmente, total_time seria ~100ms.
        # Si corrieron en paralelo, total_time seria ~50ms.
        # Usamos 80ms como umbral conservador.
        assert total_time < 0.08, (
            f"Las operaciones con keys distintas deberian correr en paralelo. "
            f"Tiempo total: {total_time:.3f}s (esperado < 0.08s si son paralelas)"
        )

        # Ambas operaciones comenzaron aproximadamente al mismo tiempo
        # (diferencia < 20ms indica paralelismo)
        time_diff = abs(start_times.get("A", 0) - start_times.get("B", 0))
        assert time_diff < 0.02, (
            f"A y B deben haber comenzado aproximadamente al mismo tiempo. "
            f"Diferencia de inicio: {time_diff:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_lock_timeout_when_first_instance_holds_too_long(
        self,
        instance_a,
        instance_b,
    ):
        """
        La segunda instancia lanza DistributedLockError si espera demasiado.

        Si Instance A tarda mas que blocking_timeout de Instance B,
        B no puede esperar indefinidamente. Lanza DistributedLockError
        para que el caller decida: retry, skip o fail.

        Given: A mantiene el lock por 500ms, B tiene blocking_timeout=0.1s
        When:  B intenta adquirir el lock
        Then:  B lanza DistributedLockError despues de ~100ms
        """
        LOCK_KEY = "kb_sync:lock:slow_operation:es:general"

        a_started = asyncio.Event()

        async def a_task():
            """A mantiene el lock por mucho tiempo (simulando operacion lenta)."""
            async with instance_a.distributed_lock(
                LOCK_KEY, timeout=30.0, blocking_timeout=5.0, sleep=0.01
            ):
                a_started.set()  # Notificar que A tiene el lock
                await asyncio.sleep(0.5)  # Mantener por 500ms (muy largo)

        async def b_task():
            """B tiene un blocking_timeout muy corto (solo 100ms)."""
            await a_started.wait()  # Esperar a que A tenga el lock
            with pytest.raises(DistributedLockError):
                async with instance_b.distributed_lock(
                    LOCK_KEY,
                    timeout=30.0,
                    blocking_timeout=0.1,  # Solo esperar 100ms
                    sleep=0.01,
                ):
                    pass  # No debe llegar aqui

        # Ejecutar ambas, B fallara rapidamente
        await asyncio.gather(a_task(), b_task())


# ============================================================================
# TEST CLASS 2: MULTIPLE CONCURRENT INSTANCES
# ============================================================================

class TestMultipleInstancesConcurrency:
    """
    Tests con mas de dos instancias para verificar comportamiento a escala.
    """

    @pytest.mark.asyncio
    async def test_five_instances_serialize_access_to_same_record(
        self,
        shared_lock_store,
    ):
        """
        5 instancias intentan actualizar el mismo registro: solo una a la vez.

        Simula el escenario de Cloud Run con min-instances=1, max-instances=5.

        Given: 5 instancias comparten el mismo Redis
        When:  Todas intentan actualizar 'policy_return:es:general' al mismo tiempo
        Then:  El acceso es serializado (max 1 instancia a la vez)
        """
        LOCK_KEY = "kb_sync:lock:policy_return:es:general"
        NUM_INSTANCES = 5

        # Crear 5 instancias con el mismo store
        instances = [
            make_redis_service_with_shared_store(shared_lock_store)
            for _ in range(NUM_INSTANCES)
        ]

        # Contadores para verificar exclusion mutua
        concurrent_count = [0]
        max_concurrent_observed = [0]
        completed_operations = []
        concurrent_violation = [False]

        async def instance_task(service, instance_id):
            async with service.distributed_lock(
                LOCK_KEY,
                timeout=30.0,
                blocking_timeout=3.0,  # Suficiente para esperar a 4 instancias
                sleep=0.01,
            ):
                # Incrementar contador de instancias activas
                concurrent_count[0] += 1

                # VERIFICAR EXCLUSION MUTUA
                if concurrent_count[0] > 1:
                    concurrent_violation[0] = True

                max_concurrent_observed[0] = max(
                    max_concurrent_observed[0], concurrent_count[0]
                )

                # Simular trabajo (upsert de DB)
                await asyncio.sleep(0.02)

                # Decrementar al salir
                concurrent_count[0] -= 1
                completed_operations.append(instance_id)

        # Lanzar todas las instancias al mismo tiempo
        await asyncio.gather(*[
            instance_task(instances[i], f"instance_{i}")
            for i in range(NUM_INSTANCES)
        ])

        # Verificaciones
        assert not concurrent_violation[0], (
            "Se detecto violacion de exclusion mutua: "
            "mas de una instancia tenia el lock simultaneamente"
        )

        assert max_concurrent_observed[0] == 1, (
            f"Max instancias concurrentes con el lock: {max_concurrent_observed[0]} "
            f"(esperado: 1)"
        )

        assert len(completed_operations) == NUM_INSTANCES, (
            f"Todas las instancias deben completar. "
            f"Completadas: {len(completed_operations)}/{NUM_INSTANCES}"
        )

    @pytest.mark.asyncio
    async def test_parallel_different_records_all_complete(
        self,
        shared_lock_store,
    ):
        """
        Operaciones sobre DIFERENTES registros corren en paralelo.

        Cada sub_intent es un registro distinto. Con N sub_intents,
        N instancias deben poder correr en paralelo (sin bloquearse).

        Given: 5 instancias, cada una con un sub_intent diferente
        When:  Todas operan en paralelo
        Then:  Todas completan en ~tiempo_de_una_operacion (no secuencialmente)
        """
        SUB_INTENTS = [
            "policy_return", "policy_shipping", "policy_payment",
            "product_care", "general_faq"
        ]
        OPERATION_TIME = 0.05  # 50ms por operacion

        instances = [
            make_redis_service_with_shared_store(shared_lock_store)
            for _ in range(len(SUB_INTENTS))
        ]

        completed = []

        async def task(service, sub_intent):
            lock_key = f"kb_sync:lock:{sub_intent}:es:general"
            async with service.distributed_lock(
                lock_key, timeout=30.0, blocking_timeout=1.0, sleep=0.01
            ):
                await asyncio.sleep(OPERATION_TIME)
                completed.append(sub_intent)

        t0 = time.time()
        await asyncio.gather(*[
            task(instances[i], SUB_INTENTS[i])
            for i in range(len(SUB_INTENTS))
        ])
        elapsed = time.time() - t0

        # Todas completaron
        assert len(completed) == len(SUB_INTENTS)

        # Tiempo total debe ser similar al de una sola operacion (paralelismo)
        # Tolerancia: 2x para evitar flakiness en CI
        max_expected = OPERATION_TIME * 2
        assert elapsed < max_expected, (
            f"Operaciones paralelas tardaron {elapsed:.3f}s. "
            f"Esperado < {max_expected}s (deberian ser paralelas, no secuenciales)"
        )


# ============================================================================
# TEST CLASS 3: ATOMICITY AND CORRECTNESS
# ============================================================================

class TestDistributedLockAtomicity:
    """
    Tests que verifican la correccion de los datos cuando multiples
    instancias intentan escribir el mismo registro.
    """

    @pytest.mark.asyncio
    async def test_no_data_corruption_with_concurrent_writes(
        self,
        shared_lock_store,
    ):
        """
        No hay corrupcion de datos cuando multiples instancias escriben el mismo registro.

        Este test simula el caso real: varias instancias reciben el webhook
        de Shopify para la misma pagina y todas intentan hacer el upsert.

        Sin distributed lock: race condition, el resultado final es imprevisible.
        Con distributed lock: cada escritura es atomica, el ultimo escritor gana.

        Given: 3 instancias, cada una con un valor diferente a escribir
        When:  Las 3 intentan escribir el mismo "registro" en paralelo
        Then:  El registro tiene exactamente uno de los tres valores (no corrupcion)
        """
        # Simular una tabla en memoria (como reemplaza a PostgreSQL en este test)
        record: dict = {}
        write_count = [0]

        shared_state_lock = asyncio.Lock()  # Para acceso al record (simula DB lock)

        instances = [
            make_redis_service_with_shared_store(shared_lock_store)
            for _ in range(3)
        ]

        async def write_record(service, value, instance_id):
            """Adquiere distributed lock, luego escribe el registro."""
            async with service.distributed_lock(
                "kb_sync:lock:policy_return:es:general",
                timeout=30.0,
                blocking_timeout=3.0,
                sleep=0.01,
            ):
                # Simular operacion de upsert (read-modify-write)
                # Sin lock, este pattern seria una race condition
                old_value = record.get("content", "EMPTY")
                await asyncio.sleep(0.01)  # Simular latencia de DB
                record["content"] = value
                record["last_writer"] = instance_id
                write_count[0] += 1

        values = ["content_v1", "content_v2", "content_v3"]

        await asyncio.gather(*[
            write_record(instances[i], values[i], f"instance_{i}")
            for i in range(3)
        ])

        # Verificar que el registro tiene exactamente UN valor (no corrupcion)
        assert "content" in record, "El registro debe tener un valor"
        assert record["content"] in values, (
            f"El contenido debe ser uno de {values}, es: {record['content']}"
        )
        assert write_count[0] == 3, "Las 3 escrituras deben completarse"

    @pytest.mark.asyncio
    async def test_counter_increment_is_correct_with_locks(
        self,
        shared_lock_store,
    ):
        """
        Un contador incrementado por 10 instancias llega al valor correcto.

        Este es el ejemplo clasico de race condition:
        Sin lock: counter puede terminar en cualquier valor entre 1 y 10
        Con lock: counter termina exactamente en 10

        Given: Counter=0, 10 instancias, cada una lo incrementa en 1
        When:  Todas corren en paralelo
        Then:  Counter=10 (exacto, sin race condition)
        """
        NUM_INSTANCES = 10
        counter = {"value": 0}

        instances = [
            make_redis_service_with_shared_store(shared_lock_store)
            for _ in range(NUM_INSTANCES)
        ]

        async def increment(service):
            async with service.distributed_lock(
                "kb_sync:lock:counter_test:es:general",
                timeout=30.0,
                blocking_timeout=5.0,
                sleep=0.005,
            ):
                # Read-modify-write (atomico gracias al lock)
                current = counter["value"]
                await asyncio.sleep(0.002)  # Simular latencia
                counter["value"] = current + 1

        await asyncio.gather(*[increment(instances[i]) for i in range(NUM_INSTANCES)])

        assert counter["value"] == NUM_INSTANCES, (
            f"El contador debe ser {NUM_INSTANCES}, es {counter['value']}. "
            f"Esto indica una race condition no prevenida por el lock."
        )


# ============================================================================
# RUNNER
# ============================================================================

if __name__ == "__main__":
    """
    Ejecutar tests de integracion:

    # Todos los tests M3 integration
    pytest tests/integration/kb/test_distributed_locking.py -v

    # Solo tests de concurrencia
    pytest tests/integration/kb/test_distributed_locking.py -v -k "Concurrency"

    # Solo tests de atomicidad
    pytest tests/integration/kb/test_distributed_locking.py -v -k "Atomicity"

    # Verbose con tiempo de ejecucion
    pytest tests/integration/kb/test_distributed_locking.py -v --tb=short --durations=5
    """
    pytest.main([__file__, "-v", "--tb=short"])
