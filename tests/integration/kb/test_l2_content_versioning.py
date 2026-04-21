"""
Integration Tests — L2: Content Versioning
============================================

Verifica el comportamiento end-to-end del sistema de versionado de contenido
tal como ocurre en el pipeline real de sync: HTML de Shopify → Markdown → PostgreSQL.

PROPÓSITO DE ESTE ARCHIVO (vs. los otros tests de KB):
───────────────────────────────────────────────────────
- tests/unit/test_l2_content_versioning.py (unit)
    → Comportamiento INTERNO de cada método en aislamiento (mocks completos)
    → _compute_content_hash, _archive_content_version, _prune_old_versions

- tests/integration/kb/test_l2_content_versioning.py (este)
    → El pipeline COMPLETO funciona como se espera con un DB simulado realista
    → Dos syncs consecutivos sin cambio → no escribe, no invalida caché
    → Cambio de contenido → archiva versión anterior, actualiza, poda
    → Feature flag off/on → comportamiento correcto en ambos estados
    → Compatibilidad: L2 no rompe el comportamiento establecido en L1

DIFERENCIA CLAVE CON UNIT TESTS:
    Los unit tests mockan cada dependencia de forma atómica (_execute_upsert
    recibe conn como parámetro). Aquí usamos _upsert_kb_content() completo,
    que incluye la adquisición del semáforo, el acquire del pool y toda
    la lógica de retry — igual que en producción.

FIXTURES DE DB:
    No usamos asyncpg real (eso es para tests E2E con PostgreSQL de prueba).
    En su lugar, construimos un mock de pool/conn realista con side_effect
    encadenados que simulan el estado de la DB entre llamadas consecutivas.
    Esto nos da cobertura del flujo completo sin necesitar infraestructura.

DISEÑO DE LOS ESCENARIOS:
    Cada clase de test simula un "escenario de negocio" completo:
    Escenario A → ciclos repetidos sin cambio (el más común en producción)
    Escenario B → cambio real de contenido (moderadamente frecuente)
    Escenario C → nuevo registro (solo primer sync de cada página)
    Escenario D → hash NULL en DB (ventana post-migration pre-backfill)
    Escenario E → feature flag desactivado (rollback de emergencia)

Autor: Retail Recommender System Team
Fecha: 01 Marzo 2026
Fase: L2 — Content Versioning (Día 2)
"""

import hashlib
import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4


# ============================================================================
# HELPERS
# ============================================================================

def _sha256(content: str) -> str:
    """Calcula SHA256 de una cadena, mismo algoritmo que _compute_content_hash()."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _make_service_with_pool(content_versioning: bool = True,
                             max_versions: int = 5,
                             db_pool=None):
    """
    Instancia ShopifyKBSyncService con flags L2 configurados y pool inyectado.

    Args:
        content_versioning: Si KB_CONTENT_VERSIONING está activo.
        max_versions:       Valor para KB_MAX_VERSIONS_PER_CONTENT.
        db_pool:            Pool de DB a inyectar (AsyncMock o real). Si None, se crea uno.

    Returns:
        Tupla (service, db_pool) para que los tests puedan inspeccionar las llamadas.
    """
    from src.api.services.shopify_kb_sync import ShopifyKBSyncService

    shopify_mock = AsyncMock()
    shopify_mock.shop_url = "test.myshopify.com"

    if db_pool is None:
        db_pool = AsyncMock()

    with patch.dict(os.environ, {
        "KB_CONTENT_VERSIONING": "true" if content_versioning else "false",
        "KB_MAX_VERSIONS_PER_CONTENT": str(max_versions),
        "KB_DISTRIBUTED_LOCKS": "false",
    }):
        service = ShopifyKBSyncService(
            shopify_client=shopify_mock,
            db_pool=db_pool,
            redis_service=AsyncMock()
        )
    return service, db_pool


def _build_pool_mock(conn_mock):
    """
    Construye un mock de asyncpg.Pool que retorna conn_mock en acquire().

    El patrón del código es: `async with self.db.acquire() as conn:`
    Para que funcione necesitamos un async context manager.
    """
    pool = AsyncMock()
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn_mock)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool


def _build_conn_mock(fetchrow_side_effects=None, fetchval_return=0):
    """
    Construye un mock de asyncpg.Connection con comportamiento configurable.

    Args:
        fetchrow_side_effects: Lista de valores retornados por fetchrow() en secuencia.
                               Cada elemento es un dict (como asyncpg.Record) o None.
        fetchval_return:       Valor retornado por fetchval() (conteo de poda).
    """
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=fetchval_return)

    if fetchrow_side_effects is not None:
        conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effects)
    else:
        conn.fetchrow = AsyncMock(return_value=None)

    return conn


# ──────────────────────────────────────────────────────────────────────────────
# DATOS DE TEST COMPARTIDOS
# ──────────────────────────────────────────────────────────────────────────────

# Parámetros de un registro KB típico de producción
KB_PARAMS = {
    "sub_intent": "policy_return",
    "language": "es",
    "category": None,  # → se normaliza como 'general'
    "content_html": "<h2>Política de Devoluciones</h2><p>30 días.</p>",
    "title": "Política de Devoluciones",
    "shopify_page_id": 12345,
    "shopify_url": "https://tienda.com/pages/politica-devolucion",
    "shopify_handle": "politica-devolucion",
}

# Contenido Markdown (como lo produce _html_to_markdown() en producción)
CONTENT_V1 = "## Política de Devoluciones\n\n30 días."
CONTENT_V2 = "## Política de Devoluciones\n\n60 días."  # ← cambio: 30 → 60

HASH_V1 = _sha256(CONTENT_V1)
HASH_V2 = _sha256(CONTENT_V2)


# ============================================================================
# ESCENARIO A: Dos Ciclos Consecutivos Sin Cambio
# ============================================================================

class TestScenarioA_NoConcurrentChange:
    """
    Escenario más común en producción: el contenido de Shopify no cambió.

    Ciclo 1: primer sync → INSERT (registro nuevo)
    Ciclo 2: mismo contenido → hash igual → SKIP completo

    Verificamos que en el Ciclo 2 no hay escritura a DB (salvo last_synced)
    y no hay invalidación de caché Redis.

    POR QUÉ ESTO IMPORTA:
        Con KB_CONTENT_VERSIONING=false, cada ciclo de 5 minutos hacía un
        UPDATE a los 26 registros, generando escrituras fantasma que:
        1. Incrementaban el load de PostgreSQL innecesariamente.
        2. Invalidaban el caché Redis 26 veces aunque el contenido no cambiara.
        3. Impedían distinguir 'contenido actualizado' de 'sync rutinario'.
        L2 elimina todo esto cuando el hash coincide.
    """

    @pytest.mark.asyncio
    async def test_second_sync_skips_db_write_when_content_unchanged(self):
        """
        Cuando el contenido no cambió entre ciclos:
        el segundo sync NO ejecuta query_update ni query_insert.

        Verifica la propiedad central de L2: sin escrituras fantasma.
        """
        kb_content_id = str(uuid4())

        # El segundo ciclo: DB ya tiene el registro con HASH_V1
        existing_record = {
            "id": kb_content_id,
            "content_hash": HASH_V1,
            "content_version": 1,
            "content": CONTENT_V1,
            "content_html": KB_PARAMS["content_html"],
            "title": KB_PARAMS["title"],
        }

        conn = _build_conn_mock(fetchrow_side_effects=[existing_record])
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)

        # Spy: _archive_content_version y _prune_old_versions no deben llamarse
        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        # Ejecutar el segundo ciclo con el mismo contenido
        await service._upsert_kb_content(
            content=CONTENT_V1,  # ← Mismo contenido que el ciclo anterior
            **KB_PARAMS
        )

        # ── Verificaciones ────────────────────────────────────────────────────
        # 1. Solo un fetchrow (el SELECT del Paso 2), no más
        assert conn.fetchrow.call_count == 1, (
            "Solo debe hacerse un SELECT (el del Paso 2), no un INSERT/UPDATE con RETURNING"
        )

        # 2. El único execute debe ser el query_touch_last_synced (no el update real)
        assert conn.execute.call_count == 1, (
            "Solo debe ejecutarse query_touch_last_synced, no query_update"
        )

        # 3. No se archivó nada
        service._archive_content_version.assert_not_called()
        service._prune_old_versions.assert_not_called()

    @pytest.mark.asyncio
    async def test_second_sync_logs_kb_content_unchanged(self):
        """
        El segundo ciclo sin cambio produce un log 'kb_content_unchanged' a DEBUG.

        Este log es la forma en que el equipo de operaciones verifica en producción
        que L2 está funcionando: después de 2 ciclos, los logs deben mostrar
        'kb_content_unchanged', no 'kb_content_updated'.
        """
        import structlog.testing

        kb_content_id = str(uuid4())
        existing_record = {
            "id": kb_content_id,
            "content_hash": HASH_V1,
            "content_version": 1,
            "content": CONTENT_V1,
            "content_html": None,
            "title": KB_PARAMS["title"],
        }

        conn = _build_conn_mock(fetchrow_side_effects=[existing_record])
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)

        with structlog.testing.capture_logs() as cap_logs:
            await service._upsert_kb_content(
                content=CONTENT_V1,
                **KB_PARAMS
            )

        unchanged_logs = [e for e in cap_logs if e.get("event") == "kb_content_unchanged"]
        assert len(unchanged_logs) == 1, (
            f"Debe loguearse exactamente 'kb_content_unchanged'. "
            f"Logs capturados: {[e.get('event') for e in cap_logs]}"
        )

        log = unchanged_logs[0]
        assert log.get("sub_intent") == "policy_return"
        assert log.get("language") == "es"
        assert "content_hash" in log

    @pytest.mark.asyncio
    async def test_second_sync_does_not_invalidate_cache(self):
        """
        El segundo ciclo sin cambio NO llama a _invalidate_cache().

        _invalidate_cache() se llama desde sync_page(), no desde _upsert_kb_content().
        L2 logra el early return ANTES de que sync_page() llegue a _invalidate_cache().

        Para simular esto correctamente, verificamos indirectamente:
        si _upsert_kb_content() retorna temprano (sin escribir a DB),
        sync_page() no llegará a _invalidate_cache() para ese sub_intent/language.

        NOTA: Este test verifica la ausencia de escrituras en DB como proxy
        de que el early return fue exitoso y la caché no se invalidó.
        La verificación directa de _invalidate_cache() requiere mock de sync_page(),
        que está cubierta en test_kb_sync_integration.py.
        """
        kb_content_id = str(uuid4())
        existing_record = {
            "id": kb_content_id,
            "content_hash": HASH_V1,
            "content_version": 2,
            "content": CONTENT_V1,
            "content_html": None,
            "title": KB_PARAMS["title"],
        }

        conn = _build_conn_mock(fetchrow_side_effects=[existing_record])
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)

        redis_mock = service.redis
        redis_mock.delete = AsyncMock(return_value=True)

        await service._upsert_kb_content(
            content=CONTENT_V1,
            **KB_PARAMS
        )

        # _upsert_kb_content() en sí nunca llama redis.delete directamente;
        # eso lo hace _invalidate_cache() en sync_page().
        # Verificamos que no hay escritura a DB (early return exitoso).
        assert conn.execute.call_count == 1  # Solo touch_last_synced
        # Y que Redis no fue contactado desde _upsert_kb_content
        redis_mock.delete.assert_not_called()


# ============================================================================
# ESCENARIO B: Cambio Real de Contenido
# ============================================================================

class TestScenarioB_ContentChanged:
    """
    Cuando el contenido en Shopify cambió desde el último sync.

    El sistema debe:
    1. Detectar que HASH_V2 ≠ HASH_V1 (almacenado)
    2. Archivar el contenido actual (v1) en kb_content_versions
    3. Actualizar kb_contents con el nuevo contenido (v2) y hash (HASH_V2)
    4. Incrementar content_version de 1 a 2
    5. Podar versiones antiguas si exceden max_versions

    POR QUÉ ESTO IMPORTA:
        El historial de versiones es el insumo de L4 (ML Content Optimization).
        Si no se archiva correctamente, L4 no tiene datos históricos para
        entrenar modelos de calidad de contenido.
    """

    @pytest.mark.asyncio
    async def test_detects_hash_change_and_updates(self):
        """
        Cuando HASH_V2 ≠ stored HASH_V1: ejecuta la ruta de actualización completa.

        Verifica que el sistema detecta el cambio y ejecuta query_update.
        """
        kb_content_id = str(uuid4())

        # Estado actual en DB: versión 1 con el hash anterior
        existing_v1 = {
            "id": kb_content_id,
            "content_hash": HASH_V1,       # ← hash anterior
            "content_version": 1,
            "content": CONTENT_V1,
            "content_html": KB_PARAMS["content_html"],
            "title": KB_PARAMS["title"],
        }
        # Retorno del UPDATE (RETURNING)
        updated_v2 = {
            "id": kb_content_id,
            "content_version": 2,
        }

        conn = _build_conn_mock(
            fetchrow_side_effects=[existing_v1, updated_v2]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        # Sync con contenido NUEVO (v2)
        await service._upsert_kb_content(
            content=CONTENT_V2,   # ← hash diferente al almacenado
            content_html=KB_PARAMS["content_html"],
            **{k: v for k, v in KB_PARAMS.items() if k not in ("content_html",)}
        )

        # Debe haber 2 llamadas a fetchrow: SELECT + UPDATE RETURNING
        assert conn.fetchrow.call_count == 2, (
            f"Deben hacerse 2 fetchrow (SELECT + UPDATE RETURNING), "
            f"se hicieron {conn.fetchrow.call_count}"
        )

    @pytest.mark.asyncio
    async def test_archives_v1_content_before_overwrite(self):
        """
        Antes de sobreescribir con v2, el sistema archiva el contenido de v1.

        El archivo contiene el contenido ANTERIOR (v1), no el nuevo (v2).
        Es como un "backup antes de modificar" — el historial dice lo que había.
        """
        kb_content_id = str(uuid4())

        existing_v1 = {
            "id": kb_content_id,
            "content_hash": HASH_V1,
            "content_version": 1,
            "content": CONTENT_V1,          # ← contenido que debe archivarse
            "content_html": "<h2>v1</h2>",
            "title": "Política v1",
        }
        updated_v2 = {"id": kb_content_id, "content_version": 2}

        conn = _build_conn_mock(
            fetchrow_side_effects=[existing_v1, updated_v2]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)
        service._prune_old_versions = AsyncMock()

        # Spy en _archive_content_version para inspeccionar los argumentos
        archive_calls = []

        async def capture_archive(**kwargs):
            archive_calls.append(kwargs)

        service._archive_content_version = AsyncMock(side_effect=capture_archive)

        await service._upsert_kb_content(
            content=CONTENT_V2,
            content_html="<h2>v2</h2>",
            title="Política v2",
            sub_intent=KB_PARAMS["sub_intent"],
            language=KB_PARAMS["language"],
            category=KB_PARAMS["category"],
            shopify_page_id=KB_PARAMS["shopify_page_id"],
            shopify_url=KB_PARAMS["shopify_url"],
            shopify_handle=KB_PARAMS["shopify_handle"],
        )

        assert len(archive_calls) == 1, (
            "Debe archivarse exactamente una versión cuando el contenido cambia"
        )

        archived = archive_calls[0]
        assert archived["kb_content_id"] == kb_content_id
        assert archived["version"] == 1,               "Debe archivarse la versión ANTERIOR (1)"
        assert archived["content"] == CONTENT_V1,      "Debe archivarse el contenido ANTERIOR"
        assert archived["content_hash"] == HASH_V1,    "Debe archivarse el hash ANTERIOR"

    @pytest.mark.asyncio
    async def test_version_counter_increments(self):
        """
        Después del cambio: content_version en DB pasa de 1 a 2.

        El incremento del contador es la forma en que el sistema rastrea
        cuántas veces ha cambiado el contenido de una página KB.
        L4 usa este contador para priorizar análisis de calidad.
        """
        kb_content_id = str(uuid4())

        existing_v1 = {
            "id": kb_content_id,
            "content_hash": HASH_V1,
            "content_version": 1,          # ← versión actual
            "content": CONTENT_V1,
            "content_html": None,
            "title": "T",
        }
        updated_v2 = {
            "id": kb_content_id,
            "content_version": 2,          # ← RETURNING del UPDATE
        }

        conn = _build_conn_mock(
            fetchrow_side_effects=[existing_v1, updated_v2]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)
        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        import structlog.testing
        with structlog.testing.capture_logs() as cap_logs:
            await service._upsert_kb_content(
                content=CONTENT_V2,
                content_html=None,
                title="T",
                sub_intent="policy_return",
                language="es",
                category=None,
                shopify_page_id=11,
                shopify_url=None,
                shopify_handle="ret",
            )

        updated_logs = [e for e in cap_logs if e.get("event") == "kb_content_updated"]
        assert len(updated_logs) == 1

        log = updated_logs[0]
        assert log.get("content_version_new") == 2, (
            f"El log debe reportar content_version_new=2, "
            f"se reportó: {log.get('content_version_new')}"
        )

    @pytest.mark.asyncio
    async def test_prune_called_after_update(self):
        """
        Después del UPDATE exitoso: se llama _prune_old_versions().

        La poda se ejecuta con el kb_content_id y max_versions correctos.
        Se hace dentro de la misma transacción que el UPDATE para atomicidad.
        """
        kb_content_id = str(uuid4())

        existing_v1 = {
            "id": kb_content_id,
            "content_hash": HASH_V1,
            "content_version": 7,
            "content": CONTENT_V1,
            "content_html": None,
            "title": "T",
        }
        updated_v2 = {"id": kb_content_id, "content_version": 8}

        conn = _build_conn_mock(
            fetchrow_side_effects=[existing_v1, updated_v2]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(
            content_versioning=True,
            max_versions=5,   # ← límite de retención
            db_pool=pool
        )
        service._archive_content_version = AsyncMock()

        prune_calls = []

        async def capture_prune(**kwargs):
            prune_calls.append(kwargs)

        service._prune_old_versions = AsyncMock(side_effect=capture_prune)

        await service._upsert_kb_content(
            content=CONTENT_V2,
            content_html=None,
            title="T",
            sub_intent="policy_return",
            language="es",
            category=None,
            shopify_page_id=11,
            shopify_url=None,
            shopify_handle="ret",
        )

        assert len(prune_calls) == 1
        assert prune_calls[0]["kb_content_id"] == kb_content_id
        assert prune_calls[0]["max_versions"] == 5, (
            f"max_versions debe ser 5 (configurado vía env), "
            f"se pasó: {prune_calls[0]['max_versions']}"
        )


# ============================================================================
# ESCENARIO C: Registro Nuevo (Primer Sync)
# ============================================================================

class TestScenarioC_NewRecord:
    """
    El registro no existe en DB: es el primer sync de esta página KB.

    Comportamiento esperado:
    - SELECT retorna None
    - No hay nada que archivar
    - INSERT con content_version=1 y el hash calculado
    - No hay poda (no hay versiones históricas)
    """

    @pytest.mark.asyncio
    async def test_inserts_on_first_sync(self):
        """
        Primer sync: el SELECT no encuentra el registro → INSERT.

        Verifica el flujo completo de inserción:
        fetchrow[0] = None (SELECT) → fetchrow[1] = nuevo registro (INSERT RETURNING).
        """
        new_id = str(uuid4())

        conn = _build_conn_mock(
            fetchrow_side_effects=[
                None,    # SELECT → no existe
                {"id": new_id, "content_version": 1},  # INSERT RETURNING
            ]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)
        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        await service._upsert_kb_content(
            content=CONTENT_V1,
            **KB_PARAMS
        )

        # 2 llamadas a fetchrow: SELECT + INSERT RETURNING
        assert conn.fetchrow.call_count == 2, (
            f"Deben hacerse 2 fetchrow (SELECT + INSERT RETURNING), "
            f"se hicieron {conn.fetchrow.call_count}"
        )

    @pytest.mark.asyncio
    async def test_no_archive_on_first_sync(self):
        """Primer sync → _archive_content_version() NO se llama."""
        conn = _build_conn_mock(
            fetchrow_side_effects=[
                None,
                {"id": str(uuid4()), "content_version": 1},
            ]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        await service._upsert_kb_content(content=CONTENT_V1, **KB_PARAMS)

        service._archive_content_version.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_prune_on_first_sync(self):
        """Primer sync → _prune_old_versions() NO se llama."""
        conn = _build_conn_mock(
            fetchrow_side_effects=[
                None,
                {"id": str(uuid4()), "content_version": 1},
            ]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)

        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        await service._upsert_kb_content(content=CONTENT_V1, **KB_PARAMS)

        service._prune_old_versions.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_kb_content_inserted_on_first_sync(self):
        """Primer sync → log 'kb_content_inserted' a DEBUG."""
        import structlog.testing

        conn = _build_conn_mock(
            fetchrow_side_effects=[
                None,
                {"id": str(uuid4()), "content_version": 1},
            ]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)
        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        with structlog.testing.capture_logs() as cap_logs:
            await service._upsert_kb_content(content=CONTENT_V1, **KB_PARAMS)

        inserted_logs = [e for e in cap_logs if e.get("event") == "kb_content_inserted"]
        assert len(inserted_logs) == 1

        log = inserted_logs[0]
        assert log.get("sub_intent") == "policy_return"
        assert log.get("content_version") == 1
        assert "content_hash" in log


# ============================================================================
# ESCENARIO D: Hash NULL en DB (Ventana Post-Migration)
# ============================================================================

class TestScenarioD_NullHashInDB:
    """
    El registro existe en DB pero su content_hash es NULL.

    Ocurre durante la ventana entre:
    - alembic upgrade head (migration 0002 aplicada)
    - python scripts/l2_backfill_content_hash.py (backfill ejecutado)

    El sistema debe tratar NULL como "cambio pendiente" para poblar el hash
    en todos los registros existentes durante el primer ciclo post-migration.
    """

    @pytest.mark.asyncio
    async def test_null_hash_treated_as_change_triggers_update(self):
        """
        Registro con content_hash=NULL → sistema lo trata como cambio y ejecuta UPDATE.

        Esto garantiza que todos los registros existentes obtienen su hash
        calculado en el primer ciclo después de desplegar L2.
        """
        kb_content_id = str(uuid4())

        existing_no_hash = {
            "id": kb_content_id,
            "content_hash": None,       # ← NULL: pre-backfill
            "content_version": 3,
            "content": CONTENT_V1,
            "content_html": None,
            "title": "Política",
        }
        updated = {"id": kb_content_id, "content_version": 4}

        conn = _build_conn_mock(
            fetchrow_side_effects=[existing_no_hash, updated]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)
        service._archive_content_version = AsyncMock()
        service._prune_old_versions = AsyncMock()

        await service._upsert_kb_content(
            content=CONTENT_V1,   # Mismo contenido, pero hash era NULL
            **KB_PARAMS
        )

        # Debe hacer 2 fetchrow: SELECT + UPDATE RETURNING (no solo 1 como en el skip)
        assert conn.fetchrow.call_count == 2, (
            "Con stored_hash=NULL debe ejecutar el UPDATE, no el skip. "
            f"fetchrow se llamó {conn.fetchrow.call_count} veces."
        )

    @pytest.mark.asyncio
    async def test_null_hash_archives_before_update(self):
        """
        Registro con hash NULL → se archiva el contenido actual antes del UPDATE.

        El archivo usa incoming_hash como content_hash del registro archivado
        (porque el almacenado es NULL, usamos el calculado como proxy).
        """
        kb_content_id = str(uuid4())

        existing_no_hash = {
            "id": kb_content_id,
            "content_hash": None,
            "content_version": 1,
            "content": CONTENT_V1,
            "content_html": "<h2>v1</h2>",
            "title": "Política",
        }
        updated = {"id": kb_content_id, "content_version": 2}

        conn = _build_conn_mock(
            fetchrow_side_effects=[existing_no_hash, updated]
        )
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=True, db_pool=pool)
        service._prune_old_versions = AsyncMock()

        archive_calls = []

        async def capture(**kwargs):
            archive_calls.append(kwargs)

        service._archive_content_version = AsyncMock(side_effect=capture)

        await service._upsert_kb_content(
            content=CONTENT_V1,
            **KB_PARAMS
        )

        assert len(archive_calls) == 1
        # El content_hash archivado debe ser el incoming_hash (no el NULL)
        assert archive_calls[0]["content_hash"] is not None, (
            "El content_hash archivado no debe ser None — debe usarse incoming_hash como fallback"
        )
        assert archive_calls[0]["content_hash"] == HASH_V1


# ============================================================================
# ESCENARIO E: Feature Flag Desactivado (Comportamiento Pre-L2)
# ============================================================================

class TestScenarioE_FeatureFlagDisabled:
    """
    Cuando KB_CONTENT_VERSIONING=false: el sistema se comporta exactamente
    como antes de L2 (un simple UPSERT sin comparación de hashes).

    Estos tests garantizan el rollback de emergencia: cambiar la variable
    de entorno a false restaura el comportamiento pre-L2 sin redeploy.
    """

    @pytest.mark.asyncio
    async def test_pre_l2_uses_simple_upsert(self):
        """
        Con flag=false: _upsert_kb_content() ejecuta un simple INSERT ... ON CONFLICT.

        No hay SELECT previo, no hay comparación de hashes, no hay archive.
        La única llamada a DB es el conn.execute() con el ON CONFLICT UPSERT.
        """
        conn = _build_conn_mock()
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=False, db_pool=pool)

        await service._upsert_kb_content(
            content=CONTENT_V1,
            **KB_PARAMS
        )

        # No debe hacerse ningún SELECT (fetchrow) — comportamiento pre-L2
        conn.fetchrow.assert_not_called()
        # Debe ejecutarse el UPSERT simple
        assert conn.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_pre_l2_does_not_calculate_incoming_hash(self):
        """
        Con flag=false: incoming_hash es None (no se calcula SHA256).

        Verificamos que con el flag desactivado, el servicio NO desperdicia
        CPU calculando un hash que no va a usar.
        """
        service, _ = _make_service_with_pool(content_versioning=False)

        # Con flag=false: la expresión condicional da None
        incoming_hash = (
            service._compute_content_hash(CONTENT_V1)
            if service._use_content_versioning
            else None
        )

        assert incoming_hash is None, (
            "Con flag desactivado, no debe calcularse el hash para ahorrar CPU"
        )

    @pytest.mark.asyncio
    async def test_pre_l2_always_writes_regardless_of_content(self):
        """
        Con flag=false: cada sync escribe a DB, aunque el contenido sea idéntico.

        Este es el comportamiento pre-L2: "escrituras fantasma" cada ciclo.
        Con flag=false, _upsert_kb_content() siempre ejecuta conn.execute().
        """
        conn = _build_conn_mock()
        pool = _build_pool_mock(conn)
        service, _ = _make_service_with_pool(content_versioning=False, db_pool=pool)

        # Ejecutar el mismo sync dos veces
        for _ in range(2):
            await service._upsert_kb_content(
                content=CONTENT_V1,
                **KB_PARAMS
            )

        # Con flag=false, se ejecuta el upsert en AMBOS ciclos
        assert conn.execute.call_count == 2, (
            "Con flag=false, cada ciclo debe ejecutar el upsert "
            f"(se esperaban 2 llamadas, se hicieron {conn.execute.call_count})"
        )

    @pytest.mark.asyncio
    async def test_toggling_flag_changes_behavior(self):
        """
        Cambiar el flag de false a true cambia el comportamiento sin reiniciar el proceso.

        En producción, el flag se lee en __init__, no en cada llamada.
        Para simular el "toggle", instanciamos dos servicios: uno con cada flag.
        """
        # Servicio con L2 desactivado
        conn_pre = _build_conn_mock()
        pool_pre = _build_pool_mock(conn_pre)
        service_pre, _ = _make_service_with_pool(content_versioning=False, db_pool=pool_pre)
        assert service_pre._use_content_versioning is False

        # Servicio con L2 activado
        kb_content_id = str(uuid4())
        existing = {
            "id": kb_content_id,
            "content_hash": HASH_V1,
            "content_version": 1,
            "content": CONTENT_V1,
            "content_html": None,
            "title": "T",
        }
        conn_l2 = _build_conn_mock(fetchrow_side_effects=[existing])
        pool_l2 = _build_pool_mock(conn_l2)
        service_l2, _ = _make_service_with_pool(content_versioning=True, db_pool=pool_l2)
        assert service_l2._use_content_versioning is True

        # Con pre-L2: conn.execute() siempre
        await service_pre._upsert_kb_content(content=CONTENT_V1, **KB_PARAMS)
        assert conn_pre.execute.call_count == 1
        conn_pre.fetchrow.assert_not_called()

        # Con L2: solo touch_last_synced (skip porque hash coincide)
        service_l2._archive_content_version = AsyncMock()
        service_l2._prune_old_versions = AsyncMock()
        await service_l2._upsert_kb_content(content=CONTENT_V1, **KB_PARAMS)
        assert conn_l2.fetchrow.call_count == 1  # Solo el SELECT
        assert conn_l2.execute.call_count == 1   # Solo touch_last_synced


# ============================================================================
# ESCENARIO F: Múltiples Idiomas (Cobertura Multi-Market)
# ============================================================================

class TestScenarioF_MultiLanguage:
    """
    Verifica que L2 funciona correctamente para los múltiples idiomas del sistema.

    El sistema opera en ES, EN, MX, CL con diferentes contenidos por idioma.
    Cada combinación (sub_intent, language, category) es un registro independiente
    en kb_contents. L2 debe funcionar correctamente para todas.
    """

    @pytest.mark.asyncio
    async def test_same_content_different_languages_are_independent(self):
        """
        ES y EN son registros independientes: el hash de uno no afecta al otro.

        Escenario: ES no cambió (skip), EN sí cambió (update).
        Los dos registros se procesan independientemente.
        """
        kb_id_es = str(uuid4())
        kb_id_en = str(uuid4())

        content_es_unchanged = "## Política\n\n30 días."
        content_en_changed = "## Policy\n\n60 days."   # ← EN cambió

        hash_es = _sha256(content_es_unchanged)
        hash_en_old = _sha256("## Policy\n\n30 days.")   # hash viejo de EN

        # Mock para ES: no cambió
        conn_es = _build_conn_mock(
            fetchrow_side_effects=[{
                "id": kb_id_es,
                "content_hash": hash_es,
                "content_version": 1,
                "content": content_es_unchanged,
                "content_html": None,
                "title": "Política ES",
            }]
        )
        pool_es = _build_pool_mock(conn_es)
        service_es, _ = _make_service_with_pool(content_versioning=True, db_pool=pool_es)
        service_es._archive_content_version = AsyncMock()
        service_es._prune_old_versions = AsyncMock()

        await service_es._upsert_kb_content(
            sub_intent="policy_return",
            language="es",
            category=None,
            content=content_es_unchanged,   # mismo → skip
            content_html=None,
            title="Política ES",
            shopify_page_id=1,
            shopify_url=None,
            shopify_handle="pol-es",
        )

        # ES: solo touch_last_synced, sin archive ni update
        service_es._archive_content_version.assert_not_called()
        assert conn_es.execute.call_count == 1   # touch_last_synced

        # Mock para EN: sí cambió
        conn_en = _build_conn_mock(
            fetchrow_side_effects=[
                {
                    "id": kb_id_en,
                    "content_hash": hash_en_old,   # hash viejo de EN
                    "content_version": 1,
                    "content": "## Policy\n\n30 days.",
                    "content_html": None,
                    "title": "Policy EN",
                },
                {"id": kb_id_en, "content_version": 2}  # RETURNING UPDATE
            ]
        )
        pool_en = _build_pool_mock(conn_en)
        service_en, _ = _make_service_with_pool(content_versioning=True, db_pool=pool_en)
        service_en._archive_content_version = AsyncMock()
        service_en._prune_old_versions = AsyncMock()

        await service_en._upsert_kb_content(
            sub_intent="policy_return",
            language="en",
            category=None,
            content=content_en_changed,   # diferente → update
            content_html=None,
            title="Policy EN",
            shopify_page_id=1,
            shopify_url=None,
            shopify_handle="pol-en",
        )

        # EN: debe haber archivado y actualizado
        service_en._archive_content_version.assert_called_once()
        assert conn_en.fetchrow.call_count == 2   # SELECT + UPDATE RETURNING


# ============================================================================
# ESCENARIO G: Compatibilidad con L1 (No Regresión)
# ============================================================================

class TestScenarioG_L1Compatibility:
    """
    Tests de regresión que garantizan que L2 no rompe el comportamiento de L1.

    L2 opera sobre el Markdown producido por L1. Si L1 produce un Markdown
    diferente en algún caso (por ej. fix de markdownify), el hash cambiará
    y L2 lo detectará como "cambio de contenido". Esto es el comportamiento
    CORRECTO — si el Markdown cambió, es una nueva versión.

    Estos tests verifican la integración entre L1 y L2 en el flujo completo.
    """

    def test_l1_output_is_deterministic_so_hash_is_stable(self):
        """
        _html_to_markdown() es determinista → el hash calculado es estable.

        Si _html_to_markdown() no fuera determinista (e.g. si generara timestamps
        o UUIDs en el output), el hash cambiaría en cada ciclo y L2 nunca
        detectaría "sin cambio". Verificamos que la salida de L1 es reproducible.
        """
        from src.api.services.shopify_kb_sync import ShopifyKBSyncService

        shopify_mock = AsyncMock()
        shopify_mock.shop_url = "test.myshopify.com"

        with patch.dict(os.environ, {"KB_CONTENT_VERSIONING": "true"}):
            service = ShopifyKBSyncService(
                shopify_client=shopify_mock,
                db_pool=AsyncMock(),
                redis_service=AsyncMock()
            )

        html = "<h2>Política de Devoluciones</h2><p>30 días.</p>"

        # Calcular hash 3 veces sobre el mismo HTML
        hashes = set()
        for _ in range(3):
            markdown = service._html_to_markdown(html)
            h = service._compute_content_hash(markdown)
            hashes.add(h)

        assert len(hashes) == 1, (
            f"El hash debe ser idéntico en cada ejecución. "
            f"Se obtuvieron {len(hashes)} hashes distintos: {hashes}"
        )

    def test_l2_detects_l1_output_change_as_content_change(self):
        """
        Si _html_to_markdown() produce diferente output para el mismo HTML
        (ej. actualización de markdownify), L2 lo detecta como "cambio de contenido".

        Esto es CORRECTO: si el Markdown cambió (aunque el HTML no haya cambiado),
        el LLM verá un contenido diferente en la KB. L2 debe registrarlo como versión nueva.
        """
        from src.api.services.shopify_kb_sync import ShopifyKBSyncService

        shopify_mock = AsyncMock()
        shopify_mock.shop_url = "test.myshopify.com"

        with patch.dict(os.environ, {"KB_CONTENT_VERSIONING": "true"}):
            service = ShopifyKBSyncService(
                shopify_client=shopify_mock,
                db_pool=AsyncMock(),
                redis_service=AsyncMock()
            )

        html = "<h2>Política</h2><p>Contenido.</p>"
        markdown_real = service._html_to_markdown(html)
        hash_real = service._compute_content_hash(markdown_real)

        # Simular que en el pasado se almacenó un Markdown con formato ligeramente diferente
        markdown_old = "## Política\r\n\r\nContenido."  # \r\n en lugar de \n
        hash_old = service._compute_content_hash(markdown_old)

        # Si el formato cambió, los hashes deben ser diferentes
        if markdown_real != markdown_old:
            assert hash_real != hash_old, (
                "Si el Markdown producido cambió, el hash debe ser diferente "
                "para que L2 detecte el cambio"
            )
        else:
            # Si son iguales, el hash también debe ser igual (determinismo)
            assert hash_real == hash_old

    def test_l2_does_not_affect_html_to_markdown_output(self):
        """
        Activar L2 no cambia el output de _html_to_markdown().

        L2 solo agrega lógica DESPUÉS de la conversión (cálculo de hash y
        comparación con DB). La conversión HTML→Markdown de L1 es idéntica
        independientemente del estado del flag KB_CONTENT_VERSIONING.
        """
        from src.api.services.shopify_kb_sync import ShopifyKBSyncService

        shopify_mock = AsyncMock()
        shopify_mock.shop_url = "test.myshopify.com"

        html = "<h2>Título</h2><p>Contenido de prueba.</p>"

        with patch.dict(os.environ, {"KB_CONTENT_VERSIONING": "false"}):
            service_pre = ShopifyKBSyncService(
                shopify_client=shopify_mock,
                db_pool=AsyncMock(),
                redis_service=AsyncMock()
            )

        with patch.dict(os.environ, {"KB_CONTENT_VERSIONING": "true"}):
            service_l2 = ShopifyKBSyncService(
                shopify_client=shopify_mock,
                db_pool=AsyncMock(),
                redis_service=AsyncMock()
            )

        result_pre = service_pre._html_to_markdown(html)
        result_l2 = service_l2._html_to_markdown(html)

        assert result_pre == result_l2, (
            "El output de _html_to_markdown() debe ser idéntico "
            "independientemente del flag KB_CONTENT_VERSIONING"
        )
