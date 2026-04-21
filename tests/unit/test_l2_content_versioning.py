"""
Unit Tests — L2: Content Versioning
=====================================

Tests unitarios para los 3 helpers privados y el flujo de _execute_upsert()
implementados en la fase L2 de ShopifyKBSyncService.

QUÉ SE PRUEBA:
    1. _compute_content_hash()  → determinismo, sensibilidad, formato SHA256
    2. _archive_content_version() → INSERT correcto en kb_content_versions
    3. _prune_old_versions()    → DELETE de versiones que exceden el límite
    4. _execute_upsert() rama pre-L2 → comportamiento idéntico al pre-L2
    5. _execute_upsert() rama L2 — hash sin cambio   → skip write + skip cache
    6. _execute_upsert() rama L2 — hash distinto    → archive + update + prune
    7. _execute_upsert() rama L2 — registro nuevo   → insert directo, sin archive
    8. _execute_upsert() rama L2 — hash NULL en DB  → trata como cambio (backfill)
    9. Feature flag KB_CONTENT_VERSIONING=false     → comportamiento pre-L2

QUÉ NO SE PRUEBA:
    - Integración con DB real (ver tests/integration/kb/test_l2_content_versioning.py)
    - Lógica de distributed lock (cubierta en test_distributed_lock.py)
    - Shopify API calls (mocks en kb_fixtures.py)

DISEÑO DE AISLAMIENTO:
    _execute_upsert() acepta una conexión asyncpg como argumento (conn), lo que
    permite reemplazarla con un AsyncMock. No necesitamos un pool real.
    _compute_content_hash() es método de instancia puro (sin IO).
    _archive_content_version() y _prune_old_versions() reciben conn directamente.

PATRÓN DE MOCK PARA asyncpg:
    asyncpg.Connection tiene métodos: execute(), fetchrow(), fetchval(), fetch().
    Los mockeamos individualmente según lo que el código bajo prueba llama.
    El context manager `async with self.db.acquire() as conn:` se mockea
    completando el patrón __aenter__ / __aexit__.

Autor: Retail Recommender System Team
Fecha: 01 Marzo 2026
Fase: L2 — Content Versioning
"""

import hashlib
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_service(content_versioning: bool = True, max_versions: int = 5):
    """
    Instancia ShopifyKBSyncService con mocks mínimos y el feature flag L2 configurado.

    Patching se hace a nivel de entorno para garantizar que el flag se lee
    del mismo lugar que en producción (os.getenv en __init__).

    Args:
        content_versioning: Valor para KB_CONTENT_VERSIONING env var.
        max_versions:       Valor para KB_MAX_VERSIONS_PER_CONTENT env var.

    Returns:
        ShopifyKBSyncService instanciado con mocks + feature flags configurados.
    """
    from src.api.services.shopify_kb_sync import ShopifyKBSyncService

    shopify_mock = AsyncMock()
    shopify_mock.shop_url = "test.myshopify.com"

    # db_pool mock: .acquire() retorna un context manager que da un AsyncMock
    # como conexión. Esto simula `async with pool.acquire() as conn:`.
    db_mock = AsyncMock()

    with patch.dict(os.environ, {
        "KB_CONTENT_VERSIONING": "true" if content_versioning else "false",
        "KB_MAX_VERSIONS_PER_CONTENT": str(max_versions),
        "KB_DISTRIBUTED_LOCKS": "false",  # Simplifica tests — lock local es suficiente
    }):
        service = ShopifyKBSyncService(
            shopify_client=shopify_mock,
            db_pool=db_mock,
            redis_service=AsyncMock()
        )

    return service, db_mock


def _make_conn_mock():
    """
    Crea un mock de asyncpg.Connection con los métodos más comunes.

    asyncpg.Connection es síncrona en la mayoría de operaciones pero
    asyncpg las expone como corrutinas. Por eso usamos AsyncMock.
    """
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    conn.fetch = AsyncMock(return_value=[])
    return conn


def _make_db_mock_with_conn(conn_mock):
    """
    Crea un pool mock que retorna conn_mock en el context manager acquire().

    El patrón en el código es:
        async with self.db.acquire() as conn:
            await conn.execute(...)

    Para que funcione con AsyncMock necesitamos que acquire() sea un
    context manager async que retorna conn_mock en __aenter__.
    """
    db_mock = AsyncMock()
    # acquire() retorna un context manager
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn_mock)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)
    db_mock.acquire = MagicMock(return_value=acquire_ctx)
    return db_mock


# ============================================================================
# GRUPO 1: _compute_content_hash()
# ============================================================================

class TestComputeContentHash:
    """
    Tests de _compute_content_hash() — SHA256 determinista del Markdown entrante.

    Este método es puro: dado el mismo input, siempre produce el mismo output.
    No tiene efectos secundarios ni dependencias externas.
    """

    def test_hash_is_deterministic(self):
        """
        La misma cadena siempre produce el mismo hash.

        Determinismo es la propiedad fundamental de un hash. Sin ella,
        la comparación stored_hash == incoming_hash nunca funcionaría.
        """
        service, _ = _make_service()
        content = "# Política de Devoluciones\n\nAceptamos devoluciones en 30 días."

        hash1 = service._compute_content_hash(content)
        hash2 = service._compute_content_hash(content)

        assert hash1 == hash2, (
            "El mismo contenido debe producir siempre el mismo hash SHA256"
        )

    def test_different_content_produces_different_hash(self):
        """
        Contenido distinto → hash distinto.

        Si dos contenidos distintos tuvieran el mismo hash (colisión),
        el sistema trataría un cambio real como si no hubiera cambio.
        SHA256 tiene probabilidad de colisión despreciable (~2^-256).
        """
        service, _ = _make_service()
        content_v1 = "# Política v1\n\nAceptamos devoluciones en 30 días."
        content_v2 = "# Política v2\n\nAceptamos devoluciones en 60 días."  # cambio: 30 → 60

        hash_v1 = service._compute_content_hash(content_v1)
        hash_v2 = service._compute_content_hash(content_v2)

        assert hash_v1 != hash_v2, (
            "Contenidos distintos deben producir hashes distintos. "
            f"Ambos produjeron: {hash_v1}"
        )

    def test_hash_length_is_64_chars(self):
        """
        SHA256 produce 64 caracteres hexadecimales (256 bits ÷ 4 bits/hex).

        La columna content_hash en la migración es VARCHAR(64).
        Un hash de diferente longitud causaría un error de truncamiento en DB.
        """
        service, _ = _make_service()
        hash_result = service._compute_content_hash("cualquier contenido")
        assert len(hash_result) == 64, (
            f"SHA256 debe tener 64 caracteres hex, got {len(hash_result)}: {hash_result}"
        )

    def test_hash_is_lowercase_hex(self):
        """
        El hash debe ser una cadena hexadecimal en minúsculas.

        hashlib.hexdigest() siempre retorna minúsculas. Verificamos para
        garantizar que las comparaciones == funcionen correctamente (case-sensitive).
        """
        service, _ = _make_service()
        hash_result = service._compute_content_hash("contenido de prueba")

        assert hash_result.isalnum(), "El hash debe ser alfanumérico"
        assert hash_result == hash_result.lower(), "El hash debe estar en minúsculas"
        # Verificar que solo contiene caracteres hex válidos
        int(hash_result, 16)  # Lanza ValueError si no es hex válido

    def test_hash_matches_manual_sha256(self):
        """
        El hash producido coincide con hashlib.sha256() calculado manualmente.

        Verifica que el algoritmo usado es exactamente SHA256 con codificación UTF-8,
        no MD5 ni otra variante. Esto garantiza compatibilidad con el backfill script
        que usa el mismo algoritmo.
        """
        service, _ = _make_service()
        content = "# Envíos Internacionales\n\nEntregamos en 5-7 días hábiles."

        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        actual = service._compute_content_hash(content)

        assert actual == expected, (
            f"El hash debe coincidir con SHA256 estándar.\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )

    def test_hash_sensitive_to_whitespace(self):
        """
        Un espacio adicional cambia el hash.

        Esto es el comportamiento correcto: si el contenido cambió (incluyendo
        whitespace), el hash debe cambiar para detectar la modificación.
        """
        service, _ = _make_service()
        hash1 = service._compute_content_hash("contenido")
        hash2 = service._compute_content_hash("contenido ")  # espacio extra

        assert hash1 != hash2, "El hash debe ser sensible a cambios de whitespace"

    def test_hash_handles_unicode(self):
        """
        Contenido con tildes, eñes y emojis produce hash válido sin excepción.

        El KB es principalmente en español — tildes y eñes son omnipresentes.
        La codificación UTF-8 en el hash garantiza que se manejan correctamente.
        """
        service, _ = _make_service()
        content_unicode = "# Política de Cambios y Devoluciones\n\n¿Tienes preguntas? ¡Contáctanos! 🛒"

        # No debe lanzar excepción
        hash_result = service._compute_content_hash(content_unicode)

        assert len(hash_result) == 64
        assert isinstance(hash_result, str)

    def test_empty_string_has_valid_hash(self):
        """
        La cadena vacía produce un hash válido (el SHA256 del string vacío).

        _html_to_markdown() puede retornar "" para páginas sin contenido.
        _upsert_kb_content() calcula el hash antes de llamar a _execute_upsert(),
        por lo que necesitamos que "" sea hasheable.
        """
        service, _ = _make_service()
        hash_empty = service._compute_content_hash("")

        assert len(hash_empty) == 64
        # SHA256 del string vacío es conocido
        expected = hashlib.sha256(b"").hexdigest()
        assert hash_empty == expected


# ============================================================================
# GRUPO 2: _archive_content_version()
# ============================================================================

class TestArchiveContentVersion:
    """
    Tests de _archive_content_version() — INSERT en kb_content_versions.

    Este método archiva el contenido ANTERIOR (pre-reemplazo) en la tabla
    de historial. Se llama en el Paso 4 del flujo de _execute_upsert().
    """

    @pytest.mark.asyncio
    async def test_archives_with_correct_parameters(self):
        """
        El INSERT se llama con todos los parámetros en el orden correcto.

        asyncpg recibe parámetros posicionales ($1, $2, ...), así que el orden
        importa. Verificamos que los valores llegan en la posición correcta.
        """
        service, _ = _make_service()
        conn = _make_conn_mock()

        kb_content_id = str(uuid4())
        version = 3
        content = "# Contenido antiguo\n\nEste contenido será archivado."
        content_html = "<h1>Contenido antiguo</h1>"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        title = "Política de Envío v3"
        sync_source = "background_sync"

        await service._archive_content_version(
            conn=conn,
            kb_content_id=kb_content_id,
            version=version,
            content=content,
            content_html=content_html,
            content_hash=content_hash,
            title=title,
            sync_source=sync_source,
        )

        # Verificar que conn.execute fue llamado una vez
        conn.execute.assert_called_once()
        call_args = conn.execute.call_args

        # Los parámetros posicionales del execute son: (query, $1, $2, ...)
        # Índices: 0=query, 1=kb_content_id, 2=version, 3=content,
        #          4=content_html, 5=content_hash, 6=title, 7=sync_source
        positional_args = call_args[0]

        assert positional_args[1] == kb_content_id, "kb_content_id debe ser $1"
        assert positional_args[2] == version,        "version debe ser $2"
        assert positional_args[3] == content,        "content debe ser $3"
        assert positional_args[4] == content_html,   "content_html debe ser $4"
        assert positional_args[5] == content_hash,   "content_hash debe ser $5"
        assert positional_args[6] == title,          "title debe ser $6"
        assert positional_args[7] == sync_source,    "sync_source debe ser $7"

    @pytest.mark.asyncio
    async def test_uses_on_conflict_do_nothing(self):
        """
        El INSERT usa ON CONFLICT DO NOTHING para seguridad en retries.

        Si un sync falla y se reintenta, el mismo (kb_content_id, version)
        podría intentar archivarse de nuevo. ON CONFLICT DO NOTHING lo ignora
        silenciosamente en lugar de fallar con un duplicate key error.
        """
        service, _ = _make_service()
        conn = _make_conn_mock()

        await service._archive_content_version(
            conn=conn,
            kb_content_id=str(uuid4()),
            version=1,
            content="contenido",
            content_html=None,
            content_hash="a" * 64,
            title=None,
            sync_source="background_sync",
        )

        # La query ejecutada debe contener ON CONFLICT DO NOTHING
        query = conn.execute.call_args[0][0]
        assert "ON CONFLICT" in query.upper()
        assert "DO NOTHING" in query.upper()

    @pytest.mark.asyncio
    async def test_accepts_none_content_html(self):
        """
        content_html puede ser None (cuando Shopify no devuelve HTML raw).

        La columna content_html es nullable en la tabla kb_content_versions.
        asyncpg acepta None como NULL en PostgreSQL.
        """
        service, _ = _make_service()
        conn = _make_conn_mock()

        # No debe lanzar excepción con content_html=None
        await service._archive_content_version(
            conn=conn,
            kb_content_id=str(uuid4()),
            version=1,
            content="contenido markdown",
            content_html=None,   # ← explícitamente None
            content_hash="b" * 64,
            title="Título",
            sync_source="background_sync",
        )

        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_sync_source_is_background_sync(self):
        """
        El parámetro sync_source tiene valor por defecto "background_sync".

        Si se llama sin especificar sync_source, debe usarse el default.
        """
        service, _ = _make_service()
        conn = _make_conn_mock()

        await service._archive_content_version(
            conn=conn,
            kb_content_id=str(uuid4()),
            version=1,
            content="contenido",
            content_html=None,
            content_hash="c" * 64,
            title=None,
            # sync_source no especificado → debe usar el default
        )

        positional_args = conn.execute.call_args[0]
        # El último argumento posicional es sync_source ($7)
        assert positional_args[7] == "background_sync"


# ============================================================================
# GRUPO 3: _prune_old_versions()
# ============================================================================

class TestPruneOldVersions:
    """
    Tests de _prune_old_versions() — DELETE de versiones antiguas.

    Este método asegura que la tabla kb_content_versions no crezca
    indefinidamente, conservando solo las N versiones más recientes.
    """

    @pytest.mark.asyncio
    async def test_calls_fetchval_with_correct_params(self):
        """
        La poda usa el kb_content_id y max_versions correctos.

        El método usa fetchval() (no execute()) porque retorna el conteo
        de filas borradas, lo cual usamos para el log.
        """
        service, _ = _make_service(max_versions=10)
        conn = _make_conn_mock()
        conn.fetchval = AsyncMock(return_value=0)  # 0 filas borradas

        kb_content_id = str(uuid4())
        await service._prune_old_versions(
            conn=conn,
            kb_content_id=kb_content_id,
            max_versions=10,
        )

        conn.fetchval.assert_called_once()
        call_args = conn.fetchval.call_args[0]

        assert call_args[1] == kb_content_id, "kb_content_id debe ser $1"
        assert call_args[2] == 10,            "max_versions debe ser $2"

    @pytest.mark.asyncio
    async def test_query_uses_cte_with_delete(self):
        """
        La query usa un CTE (WITH ... DELETE) para eficiencia.

        El patrón CTE con DELETE es más eficiente que dos queries separadas
        (SELECT ids_to_delete + DELETE WHERE id IN ...) porque evita un
        round-trip adicional a PostgreSQL.
        """
        service, _ = _make_service()
        conn = _make_conn_mock()
        conn.fetchval = AsyncMock(return_value=2)

        await service._prune_old_versions(
            conn=conn,
            kb_content_id=str(uuid4()),
            max_versions=5,
        )

        query = conn.fetchval.call_args[0][0]
        # Verificar presencia de elementos clave del CTE
        assert "WITH" in query.upper()
        assert "DELETE" in query.upper()
        assert "ORDER BY" in query.upper()
        assert "LIMIT" in query.upper()

    @pytest.mark.asyncio
    async def test_no_log_when_nothing_deleted(self):
        """
        Cuando fetchval retorna 0, no hay logs de poda (silencioso).

        El caso más común en producción: menos versiones que el máximo.
        Logear "0 filas borradas" en cada ciclo sería ruido innecesario.
        """
        import structlog.testing

        service, _ = _make_service()
        conn = _make_conn_mock()
        conn.fetchval = AsyncMock(return_value=0)  # Nada borrado

        # Capturamos los log events para verificar que no hay ruido
        with structlog.testing.capture_logs() as cap_logs:
            await service._prune_old_versions(
                conn=conn,
                kb_content_id=str(uuid4()),
                max_versions=5,
            )

        # No debe haber logs de poda cuando deleted=0
        prune_logs = [e for e in cap_logs if e.get("event") == "content_versions_pruned"]
        assert len(prune_logs) == 0, (
            "No debe loguearse nada cuando no se borran versiones"
        )

    @pytest.mark.asyncio
    async def test_logs_when_versions_deleted(self):
        """
        Cuando se borran versiones, se logea a nivel DEBUG con el conteo.
        """
        import structlog.testing

        service, _ = _make_service()
        conn = _make_conn_mock()
        conn.fetchval = AsyncMock(return_value=3)  # 3 versiones borradas

        kb_content_id = str(uuid4())

        with structlog.testing.capture_logs() as cap_logs:
            await service._prune_old_versions(
                conn=conn,
                kb_content_id=kb_content_id,
                max_versions=5,
            )

        prune_logs = [e for e in cap_logs if e.get("event") == "content_versions_pruned"]
        assert len(prune_logs) == 1

        log_entry = prune_logs[0]
        assert log_entry["versions_deleted"] == 3
        assert log_entry["max_versions_kept"] == 5


# ============================================================================
# GRUPO 4: _execute_upsert() — Rama Pre-L2 (Flag Desactivado)
# ============================================================================

class TestExecuteUpsertPreL2:
    """
    Tests de _execute_upsert() cuando KB_CONTENT_VERSIONING=false.

    Cuando el flag está desactivado, el método debe comportarse exactamente
    como antes de L2: un simple INSERT ... ON CONFLICT DO UPDATE sin ninguna
    lógica de comparación de hashes.
    """

    @pytest.mark.asyncio
    async def test_pre_l2_calls_execute_not_fetchrow(self):
        """
        Con flag desactivado: usa conn.execute() (el UPSERT simple),
        NO conn.fetchrow() (el SELECT + INSERT/UPDATE de L2).

        Esta es la diferencia de comportamiento observable entre pre-L2 y L2:
        pre-L2 no hace SELECT previo, L2 sí.
        """
        service, _ = _make_service(content_versioning=False)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        # Llamar _execute_upsert con incoming_hash=None (flag desactivado)
        await service._execute_upsert(
            sub_intent="policy_return",
            language="es",
            normalized_category="general",
            content="# Política\n\nContenido.",
            content_html="<h1>Política</h1>",
            title="Política de Devoluciones",
            shopify_page_id=12345,
            shopify_url="https://tienda.com/pages/politica",
            shopify_handle="politica-devoluciones",
            incoming_hash=None,   # ← None cuando flag=false
            query_insert="INSERT...",
            query_update="UPDATE...",
            query_touch_last_synced="UPDATE last_synced...",
            query_pre_l2="INSERT ... ON CONFLICT DO UPDATE ...",
            distributed_lock_used=False,
        )

        # Con flag desactivado: execute() para el UPSERT simple
        conn.execute.assert_called_once()
        # No debe haber SELECT (fetchrow) previo
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_pre_l2_uses_pre_l2_query(self):
        """
        Con flag desactivado: se usa query_pre_l2 (con ON CONFLICT DO UPDATE),
        no query_insert ni query_update.

        query_pre_l2 es el comportamiento original de M3. Cuando hay un
        cambio de contenido en producción (rollback de L2), volvemos a este.
        """
        service, _ = _make_service(content_versioning=False)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        marker = "UNIQUE_MARKER_PRE_L2"  # Identificador único en la query pre-L2

        await service._execute_upsert(
            sub_intent="policy_shipping",
            language="en",
            normalized_category="general",
            content="Shipping policy content.",
            content_html="<p>Shipping</p>",
            title="Shipping Policy",
            shopify_page_id=99999,
            shopify_url=None,
            shopify_handle="shipping",
            incoming_hash=None,
            query_insert="QUERY_INSERT",
            query_update="QUERY_UPDATE",
            query_touch_last_synced="QUERY_TOUCH",
            query_pre_l2=marker,  # ← Query distintiva
            distributed_lock_used=False,
        )

        # La query ejecutada debe ser query_pre_l2
        executed_query = conn.execute.call_args[0][0]
        assert executed_query == marker, (
            f"Con flag desactivado debe usarse query_pre_l2.\n"
            f"Se usó: {executed_query}"
        )


# ============================================================================
# GRUPO 5: _execute_upsert() — Hash Sin Cambio (Skip)
# ============================================================================

class TestExecuteUpsertHashUnchanged:
    """
    Tests del caso más importante de L2: cuando el hash no cambia, no se escribe.

    Este es el "camino feliz" en producción: la mayoría de ciclos de sync
    detectarán que el contenido no cambió y saltarán la escritura a DB.
    """

    @pytest.mark.asyncio
    async def test_skips_write_when_hash_unchanged(self):
        """
        Cuando stored_hash == incoming_hash: NO se llama query_update.

        El método debe retornar temprano después de actualizar last_synced,
        sin tocar content, updated_at ni content_version.
        """
        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        same_hash = "a" * 64
        existing_id = str(uuid4())

        # Simular que el registro existe en DB con el mismo hash
        conn.fetchrow = AsyncMock(return_value={
            "id": existing_id,
            "content_hash": same_hash,
            "content_version": 2,
            "content": "# Contenido existente",
            "content_html": "<h1>Existente</h1>",
            "title": "Título Existente",
        })

        await service._execute_upsert(
            sub_intent="policy_return",
            language="es",
            normalized_category="general",
            content="# Contenido existente",
            content_html="<h1>Existente</h1>",
            title="Título Existente",
            shopify_page_id=111,
            shopify_url=None,
            shopify_handle="politica",
            incoming_hash=same_hash,   # ← Mismo hash que en DB
            query_insert="QUERY_INSERT",
            query_update="QUERY_UPDATE",
            query_touch_last_synced="QUERY_TOUCH",
            query_pre_l2="QUERY_PRE_L2",
            distributed_lock_used=False,
        )

        # La query de actualización NO debe haberse ejecutado
        execute_calls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert "QUERY_UPDATE" not in execute_calls, (
            "No debe ejecutar query_update cuando el hash no cambió"
        )
        assert "QUERY_INSERT" not in execute_calls, (
            "No debe ejecutar query_insert cuando el hash no cambió"
        )

    @pytest.mark.asyncio
    async def test_touches_last_synced_when_hash_unchanged(self):
        """
        Cuando el hash no cambia: actualiza last_synced (sin tocar updated_at).

        El sistema de polling incremental usa last_synced para saber que
        el registro fue verificado. Sin esta actualización, podría
        considerar el registro como "no revisado" y re-sincronizarlo.
        """
        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        same_hash = "b" * 64
        conn.fetchrow = AsyncMock(return_value={
            "id": str(uuid4()),
            "content_hash": same_hash,
            "content_version": 1,
            "content": "contenido",
            "content_html": None,
            "title": "Título",
        })

        await service._execute_upsert(
            sub_intent="faq_payments",
            language="en",
            normalized_category="general",
            content="contenido",
            content_html=None,
            title="Título",
            shopify_page_id=222,
            shopify_url=None,
            shopify_handle="faq",
            incoming_hash=same_hash,
            query_insert="QUERY_INSERT",
            query_update="QUERY_UPDATE",
            query_touch_last_synced="QUERY_TOUCH_LAST_SYNCED_MARKER",
            query_pre_l2="QUERY_PRE_L2",
            distributed_lock_used=False,
        )

        # Debe haberse ejecutado QUERY_TOUCH para actualizar last_synced
        execute_calls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert "QUERY_TOUCH_LAST_SYNCED_MARKER" in execute_calls, (
            "Debe ejecutar query_touch_last_synced cuando el hash no cambió"
        )

    @pytest.mark.asyncio
    async def test_logs_kb_content_unchanged_at_debug(self):
        """
        Cuando el hash no cambia: log de evento 'kb_content_unchanged' a DEBUG.

        Este log es fundamental para validar que L2 funciona en producción:
        después de dos ciclos sin cambio, los logs deben mostrar
        kb_content_unchanged (no kb_content_updated).
        """
        import structlog.testing

        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        same_hash = "c" * 64
        conn.fetchrow = AsyncMock(return_value={
            "id": str(uuid4()),
            "content_hash": same_hash,
            "content_version": 5,
            "content": "contenido",
            "content_html": None,
            "title": "Título",
        })

        with structlog.testing.capture_logs() as cap_logs:
            await service._execute_upsert(
                sub_intent="policy_privacy",
                language="es",
                normalized_category="general",
                content="contenido",
                content_html=None,
                title="Título",
                shopify_page_id=333,
                shopify_url=None,
                shopify_handle="privacy",
                incoming_hash=same_hash,
                query_insert="I",
                query_update="U",
                query_touch_last_synced="T",
                query_pre_l2="P",
                distributed_lock_used=False,
            )

        unchanged_logs = [e for e in cap_logs if e.get("event") == "kb_content_unchanged"]
        assert len(unchanged_logs) == 1, (
            f"Debe loguearse exactamente un evento 'kb_content_unchanged'. "
            f"Logs capturados: {cap_logs}"
        )
        assert unchanged_logs[0].get("sub_intent") == "policy_privacy"

    @pytest.mark.asyncio
    async def test_does_not_call_archive_when_hash_unchanged(self):
        """
        Cuando el hash no cambia: no se archiva en kb_content_versions.

        No hay nada que archivar — el contenido no cambió.
        Archivar cuando no hay cambio introduciría ruido en el historial.
        """
        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        same_hash = "d" * 64
        conn.fetchrow = AsyncMock(return_value={
            "id": str(uuid4()),
            "content_hash": same_hash,
            "content_version": 3,
            "content": "contenido",
            "content_html": None,
            "title": "Título",
        })

        # Spy en _archive_content_version para verificar que NO se llama
        service._archive_content_version = AsyncMock()

        await service._execute_upsert(
            sub_intent="policy_terms",
            language="es",
            normalized_category="general",
            content="contenido",
            content_html=None,
            title="Título",
            shopify_page_id=444,
            shopify_url=None,
            shopify_handle="terms",
            incoming_hash=same_hash,
            query_insert="I",
            query_update="U",
            query_touch_last_synced="T",
            query_pre_l2="P",
            distributed_lock_used=False,
        )

        service._archive_content_version.assert_not_called()


# ============================================================================
# GRUPO 6: _execute_upsert() — Hash Distinto (Cambio Real)
# ============================================================================

class TestExecuteUpsertHashChanged:
    """
    Tests del caso de cambio real de contenido: hash entrante ≠ hash almacenado.

    Este es el flujo completo de 7 pasos: archivo del anterior → update → poda.
    """

    @pytest.mark.asyncio
    async def test_archives_previous_version_when_hash_changes(self):
        """
        Cuando el hash cambia: archiva la versión ACTUAL (antes de reemplazarla).

        _archive_content_version() recibe el contenido ANTERIOR (current),
        no el nuevo. El historial dice "qué había antes del cambio".
        """
        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        old_hash = "a" * 64
        new_hash = "b" * 64
        kb_content_id = str(uuid4())
        old_content = "# Política v1\n\nContenido antiguo."
        new_content = "# Política v2\n\nContenido nuevo."

        conn.fetchrow = AsyncMock(return_value={
            "id": kb_content_id,
            "content_hash": old_hash,
            "content_version": 2,
            "content": old_content,    # Contenido ANTERIOR
            "content_html": "<p>Antiguo</p>",
            "title": "Política v1",
        })
        # UPDATE retorna el nuevo estado
        conn.fetchrow.side_effect = [
            {  # Primera llamada: SELECT del estado actual
                "id": kb_content_id,
                "content_hash": old_hash,
                "content_version": 2,
                "content": old_content,
                "content_html": "<p>Antiguo</p>",
                "title": "Política v1",
            },
            {  # Segunda llamada: RETURNING del UPDATE
                "id": kb_content_id,
                "content_version": 3,
            }
        ]

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        await service._execute_upsert(
            sub_intent="policy_return",
            language="es",
            normalized_category="general",
            content=new_content,
            content_html="<p>Nuevo</p>",
            title="Política v2",
            shopify_page_id=555,
            shopify_url=None,
            shopify_handle="politica-retorno",
            incoming_hash=new_hash,   # ← Hash distinto al stored_hash
            query_insert="INSERT...",
            query_update="UPDATE...",
            query_touch_last_synced="TOUCH...",
            query_pre_l2="PRE_L2...",
            distributed_lock_used=False,
        )

        # _archive_content_version debe haberse llamado con el contenido ANTERIOR
        service._archive_content_version.assert_called_once()
        archive_kwargs = service._archive_content_version.call_args[1]

        assert archive_kwargs["kb_content_id"] == kb_content_id
        assert archive_kwargs["version"] == 2           # Versión ANTERIOR
        assert archive_kwargs["content"] == old_content  # Contenido ANTERIOR
        assert archive_kwargs["content_hash"] == old_hash

    @pytest.mark.asyncio
    async def test_executes_update_query_when_hash_changes(self):
        """
        Cuando el hash cambia: ejecuta query_update (no query_insert).

        El registro ya existe → UPDATE, no INSERT.
        """
        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        old_hash = "e" * 64
        new_hash = "f" * 64
        kb_content_id = str(uuid4())

        conn.fetchrow = AsyncMock(side_effect=[
            {  # SELECT
                "id": kb_content_id,
                "content_hash": old_hash,
                "content_version": 1,
                "content": "viejo",
                "content_html": None,
                "title": "Título",
            },
            {"id": kb_content_id, "content_version": 2},  # RETURNING de UPDATE
        ])

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        update_marker = "UPDATE_QUERY_UNIQUE_MARKER"

        await service._execute_upsert(
            sub_intent="policy_shipping",
            language="es",
            normalized_category="general",
            content="nuevo",
            content_html=None,
            title="Título",
            shopify_page_id=666,
            shopify_url=None,
            shopify_handle="shipping",
            incoming_hash=new_hash,
            query_insert="INSERT_MARKER",
            query_update=update_marker,
            query_touch_last_synced="TOUCH_MARKER",
            query_pre_l2="PRE_L2_MARKER",
            distributed_lock_used=False,
        )

        # La segunda llamada a fetchrow debe usar query_update
        second_call_query = conn.fetchrow.call_args_list[1][0][0]
        assert second_call_query == update_marker, (
            f"Debe usar query_update para registro existente con hash distinto. "
            f"Se usó: {second_call_query}"
        )

    @pytest.mark.asyncio
    async def test_calls_prune_after_update(self):
        """
        Después de un UPDATE exitoso: llama _prune_old_versions() con max_versions.

        La poda evita que la tabla de historial crezca indefinidamente.
        Se llama después del archive+update, no antes.
        """
        service, _ = _make_service(content_versioning=True, max_versions=5)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        old_hash = "g" * 64
        new_hash = "h" * 64
        kb_content_id = str(uuid4())

        conn.fetchrow = AsyncMock(side_effect=[
            {
                "id": kb_content_id,
                "content_hash": old_hash,
                "content_version": 4,
                "content": "viejo",
                "content_html": None,
                "title": "T",
            },
            {"id": kb_content_id, "content_version": 5},
        ])

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        await service._execute_upsert(
            sub_intent="faq_contact",
            language="en",
            normalized_category="general",
            content="nuevo contenido",
            content_html=None,
            title="T",
            shopify_page_id=777,
            shopify_url=None,
            shopify_handle="contact",
            incoming_hash=new_hash,
            query_insert="I",
            query_update="U",
            query_touch_last_synced="T",
            query_pre_l2="P",
            distributed_lock_used=False,
        )

        # _prune_old_versions debe haberse llamado con el kb_content_id correcto
        service._prune_old_versions.assert_called_once()
        prune_kwargs = service._prune_old_versions.call_args[1]

        assert prune_kwargs["kb_content_id"] == kb_content_id
        assert prune_kwargs["max_versions"] == 5


# ============================================================================
# GRUPO 7: _execute_upsert() — Registro Nuevo (INSERT)
# ============================================================================

class TestExecuteUpsertNewRecord:
    """
    Tests cuando el registro no existe en DB (primer sync de una página).
    """

    @pytest.mark.asyncio
    async def test_inserts_new_record_when_not_found(self):
        """
        Cuando el SELECT retorna None (registro no existe): usa query_insert.

        No hay nada que archivar ni comparar — es el primer sync de esta
        combinación (sub_intent, language, category).
        """
        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        new_hash = "i" * 64

        conn.fetchrow = AsyncMock(side_effect=[
            None,   # SELECT → registro no existe
            {"id": str(uuid4()), "content_version": 1},  # RETURNING de INSERT
        ])

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        insert_marker = "INSERT_QUERY_UNIQUE_MARKER"

        await service._execute_upsert(
            sub_intent="policy_new",
            language="fr",
            normalized_category="general",
            content="Nouveau contenu.",
            content_html="<p>Nouveau</p>",
            title="Nouvelle politique",
            shopify_page_id=888,
            shopify_url="https://tienda.com/pages/new",
            shopify_handle="new-policy",
            incoming_hash=new_hash,
            query_insert=insert_marker,
            query_update="UPDATE_MARKER",
            query_touch_last_synced="TOUCH_MARKER",
            query_pre_l2="PRE_L2_MARKER",
            distributed_lock_used=False,
        )

        # La segunda llamada a fetchrow debe usar query_insert
        second_call_query = conn.fetchrow.call_args_list[1][0][0]
        assert second_call_query == insert_marker, (
            f"Debe usar query_insert para registro nuevo. Se usó: {second_call_query}"
        )

    @pytest.mark.asyncio
    async def test_does_not_archive_for_new_record(self):
        """
        Para un registro nuevo: NO se llama _archive_content_version().

        No hay historial que archivar cuando el registro ni siquiera existía.
        """
        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        conn.fetchrow = AsyncMock(side_effect=[
            None,  # SELECT → no existe
            {"id": str(uuid4()), "content_version": 1},  # RETURNING INSERT
        ])

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        await service._execute_upsert(
            sub_intent="policy_cookies",
            language="de",
            normalized_category="general",
            content="Neue Inhalte.",
            content_html=None,
            title=None,
            shopify_page_id=999,
            shopify_url=None,
            shopify_handle="cookies",
            incoming_hash="j" * 64,
            query_insert="I",
            query_update="U",
            query_touch_last_synced="T",
            query_pre_l2="P",
            distributed_lock_used=False,
        )

        service._archive_content_version.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_prune_for_new_record(self):
        """
        Para un registro nuevo: NO se llama _prune_old_versions().

        No hay versiones históricas que podar en el primer sync.
        """
        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        conn.fetchrow = AsyncMock(side_effect=[
            None,
            {"id": str(uuid4()), "content_version": 1},
        ])

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        await service._execute_upsert(
            sub_intent="policy_cookies",
            language="de",
            normalized_category="general",
            content="Neue Inhalte.",
            content_html=None,
            title=None,
            shopify_page_id=999,
            shopify_url=None,
            shopify_handle="cookies",
            incoming_hash="k" * 64,
            query_insert="I",
            query_update="U",
            query_touch_last_synced="T",
            query_pre_l2="P",
            distributed_lock_used=False,
        )

        service._prune_old_versions.assert_not_called()


# ============================================================================
# GRUPO 8: _execute_upsert() — Hash NULL en DB (Backfill Pendiente)
# ============================================================================

class TestExecuteUpsertNullHashInDB:
    """
    Tests del caso de transición post-migration: registro existe pero sin hash.

    Después de aplicar la migración 0002, los registros existentes tienen
    content_hash = NULL. El backfill los llena, pero durante la ventana entre
    migration y backfill, el sistema debe tratar NULL como "cambio pendiente".
    """

    @pytest.mark.asyncio
    async def test_null_stored_hash_treated_as_change(self):
        """
        Si stored_hash es NULL en DB: trata el registro como si hubiera cambiado.

        Esto garantiza que el primer ciclo post-migration popule el hash
        en todos los registros existentes, incluso si el contenido no cambió.
        """
        service, _ = _make_service(content_versioning=True)
        conn = _make_conn_mock()
        db_mock = _make_db_mock_with_conn(conn)
        service.db = db_mock

        incoming_hash = "l" * 64
        kb_content_id = str(uuid4())

        conn.fetchrow = AsyncMock(side_effect=[
            {  # SELECT → registro existe pero sin hash (pre-backfill)
                "id": kb_content_id,
                "content_hash": None,   # ← NULL: pre-backfill
                "content_version": 1,
                "content": "contenido existente",
                "content_html": "<p>Existente</p>",
                "title": "Título",
            },
            {"id": kb_content_id, "content_version": 2},  # RETURNING UPDATE
        ])

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        update_marker = "UPDATE_MARKER_FOR_NULL_HASH"

        await service._execute_upsert(
            sub_intent="policy_return",
            language="es",
            normalized_category="general",
            content="contenido existente",
            content_html="<p>Existente</p>",
            title="Título",
            shopify_page_id=101,
            shopify_url=None,
            shopify_handle="return",
            incoming_hash=incoming_hash,
            query_insert="INSERT_MARKER",
            query_update=update_marker,
            query_touch_last_synced="TOUCH_MARKER",
            query_pre_l2="PRE_L2_MARKER",
            distributed_lock_used=False,
        )

        # Debe haber ejecutado query_update (no el skip de hash igual)
        second_call_query = conn.fetchrow.call_args_list[1][0][0]
        assert second_call_query == update_marker, (
            "Con stored_hash=NULL debe tratarse como cambio y ejecutar query_update"
        )


# ============================================================================
# GRUPO 9: Feature Flag KB_CONTENT_VERSIONING
# ============================================================================

class TestFeatureFlag:
    """
    Tests del feature flag KB_CONTENT_VERSIONING.

    El flag permite activar/desactivar L2 sin redeploy.
    Cuando está desactivado, el comportamiento debe ser idéntico al pre-L2.
    """

    def test_flag_false_by_default(self):
        """
        KB_CONTENT_VERSIONING por defecto es False (safe default).

        El comportamiento pre-L2 es el default para evitar romper producción
        al desplegar. L2 se activa explícitamente una vez probado.
        """
        from src.api.services.shopify_kb_sync import ShopifyKBSyncService

        shopify_mock = AsyncMock()
        shopify_mock.shop_url = "test.myshopify.com"

        # Aseguramos que KB_CONTENT_VERSIONING no esté en el entorno
        env_without_flag = {k: v for k, v in os.environ.items()
                            if k != "KB_CONTENT_VERSIONING"}

        with patch.dict(os.environ, env_without_flag, clear=True):
            service = ShopifyKBSyncService(
                shopify_client=shopify_mock,
                db_pool=AsyncMock(),
                redis_service=AsyncMock()
            )

        assert service._use_content_versioning is False, (
            "KB_CONTENT_VERSIONING debe ser False por defecto"
        )

    def test_flag_true_when_env_is_true(self):
        """KB_CONTENT_VERSIONING=true → _use_content_versioning = True"""
        service, _ = _make_service(content_versioning=True)
        assert service._use_content_versioning is True

    def test_flag_false_when_env_is_false(self):
        """KB_CONTENT_VERSIONING=false → _use_content_versioning = False"""
        service, _ = _make_service(content_versioning=False)
        assert service._use_content_versioning is False

    def test_max_versions_default_is_10(self):
        """KB_MAX_VERSIONS_PER_CONTENT por defecto es 10."""
        from src.api.services.shopify_kb_sync import ShopifyKBSyncService

        shopify_mock = AsyncMock()
        shopify_mock.shop_url = "test.myshopify.com"

        env_without_max = {k: v for k, v in os.environ.items()
                           if k not in ("KB_MAX_VERSIONS_PER_CONTENT",
                                        "KB_CONTENT_VERSIONING")}

        with patch.dict(os.environ, env_without_max, clear=True):
            service = ShopifyKBSyncService(
                shopify_client=shopify_mock,
                db_pool=AsyncMock(),
                redis_service=AsyncMock()
            )

        assert service._max_versions_per_content == 10

    def test_max_versions_configurable(self):
        """KB_MAX_VERSIONS_PER_CONTENT=25 → _max_versions_per_content = 25"""
        service, _ = _make_service(max_versions=25)
        assert service._max_versions_per_content == 25

    def test_incoming_hash_none_when_flag_disabled(self):
        """
        Cuando KB_CONTENT_VERSIONING=false: incoming_hash = None.

        _upsert_kb_content() calcula:
            incoming_hash = _compute_content_hash() if _use_content_versioning else None

        Con flag=false, no se desperdicia CPU calculando el hash.
        Y _execute_upsert() recibe None como incoming_hash, activando la rama pre-L2.
        """
        service, _ = _make_service(content_versioning=False)

        # _use_content_versioning es False: la expresión condicional da None
        incoming_hash = service._compute_content_hash("contenido") if service._use_content_versioning else None

        assert incoming_hash is None, (
            "Con flag desactivado, incoming_hash debe ser None "
            "(no desperdiciar CPU calculando hash)"
        )


# ============================================================================
# GRUPO 10: Tests de Regresión post-L2
# ============================================================================

class TestL2Regression:
    """
    Tests de regresión que garantizan que L2 no rompió el comportamiento de L1.

    L2 añade lógica ENCIMA de L1 (HTML→Markdown). Los métodos L1 deben
    seguir funcionando exactamente igual.
    """

    def test_compute_hash_method_exists(self):
        """_compute_content_hash() existe en ShopifyKBSyncService."""
        service, _ = _make_service()
        assert hasattr(service, "_compute_content_hash")
        assert callable(service._compute_content_hash)

    def test_archive_version_method_exists(self):
        """_archive_content_version() existe en ShopifyKBSyncService."""
        service, _ = _make_service()
        assert hasattr(service, "_archive_content_version")
        assert callable(service._archive_content_version)

    def test_prune_old_versions_method_exists(self):
        """_prune_old_versions() existe en ShopifyKBSyncService."""
        service, _ = _make_service()
        assert hasattr(service, "_prune_old_versions")
        assert callable(service._prune_old_versions)

    def test_execute_upsert_method_exists(self):
        """_execute_upsert() existe en ShopifyKBSyncService."""
        service, _ = _make_service()
        assert hasattr(service, "_execute_upsert")
        assert callable(service._execute_upsert)

    def test_l1_html_to_markdown_still_works(self):
        """L1: _html_to_markdown() sigue funcionando después de L2."""
        service, _ = _make_service()
        result = service._html_to_markdown("<h2>Título</h2><p>Contenido.</p>")
        assert "Título" in result
        assert "<h2>" not in result

    def test_service_initializes_with_l2_flags_in_logs(self):
        """
        El log de inicialización incluye los campos L2.

        El __init__ loguea content_versioning_enabled y max_versions_per_content.
        Este test verifica que el log estructurado incluye estos campos.
        """
        import structlog.testing

        from src.api.services.shopify_kb_sync import ShopifyKBSyncService

        shopify_mock = AsyncMock()
        shopify_mock.shop_url = "test.myshopify.com"

        with structlog.testing.capture_logs() as cap_logs:
            with patch.dict(os.environ, {
                "KB_CONTENT_VERSIONING": "true",
                "KB_MAX_VERSIONS_PER_CONTENT": "7",
            }):
                service = ShopifyKBSyncService(
                    shopify_client=shopify_mock,
                    db_pool=AsyncMock(),
                    redis_service=AsyncMock()
                )

        init_log = next(
            (e for e in cap_logs if e.get("event") == "service_initialized"),
            None
        )

        assert init_log is not None, "Debe loguearse 'service_initialized'"
        assert init_log.get("content_versioning_enabled") is True
        assert init_log.get("max_versions_per_content") == 7
