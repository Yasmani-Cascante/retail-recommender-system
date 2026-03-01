"""
Knowledge Base Test Fixtures
============================

Proporciona fixtures reutilizables para tests de KB v2 Multi-Language.
Incluye mocks de Shopify API, datos de prueba y utilities.

Fecha: 31 Enero 2026
Propósito: Facilitar testing de sincronización, cache y edge cases

Changelog:
- L1 Fix: Agregado mock de get_page_title_translation() que faltaba.
  Sin este mock, AsyncMock() retornaba un MagicMock genérico (truthy)
  en lugar de None/str, causando que las traducciones EN se perdieran
  silenciosamente por el except Exception: continue en sync_page().
"""

import pytest
from typing import Dict, List, Optional
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import asyncpg

from src.api.core.config import get_settings


# ============================================================================
# MOCK DATA - Shopify Pages
# ============================================================================

MOCK_SHOPIFY_PAGES = [
    {
        "id": 158838489397,
        "title": "Política de Devoluciones",
        "handle": "politica-de-devoluciones",
        "body_html": "<h2>Política de Devoluciones</h2><p>Aceptamos devoluciones dentro de 30 días...</p>",
        "created_at": "2025-01-10T10:00:00Z",
        "updated_at": "2025-01-15T10:00:00Z",
        "published_at": "2025-01-15T10:00:00Z",
        "metafields": [
            {"key": "kb_sub_intent", "value": "policy_return"},
            {"key": "kb_category", "value": "general"}
        ]
    },
    {
        "id": 158888198453,
        "title": "Cuidado de Productos",
        "handle": "cuidado-de-productos",
        "body_html": "<h2>Cuidado de Productos</h2><p>Para mantener tus productos en óptimas condiciones...</p>",
        "created_at": "2025-01-10T10:00:00Z",
        "updated_at": "2025-01-15T10:00:00Z",
        "published_at": "2025-01-15T10:00:00Z",
        "metafields": [
            {"key": "kb_sub_intent", "value": "product_care"},
            {"key": "kb_category", "value": "general"}
        ]
    },
    {
        "id": 158886101301,
        "title": "Métodos de Pago",
        "handle": "metodos-de-pago",
        "body_html": "<h2>Métodos de Pago</h2><p>Aceptamos las siguientes formas de pago...</p>",
        "created_at": "2025-01-10T10:00:00Z",
        "updated_at": "2025-01-15T10:00:00Z",
        "published_at": "2025-01-15T10:00:00Z",
        "metafields": [
            {"key": "kb_sub_intent", "value": "policy_payment"},
            {"key": "kb_category", "value": "general"}
        ]
    }
]

# ============================================================================
# MOCK DATA - Shopify Translations
# ============================================================================

# Estructura: {page_id: {locale: {title, body_html}}}
# - El idioma "es" es el idioma base (contenido original de Shopify).
# - Los otros locales son traducciones. Si no existe un locale,
#   la página no tiene traducción para ese idioma (caso policy_payment).
MOCK_SHOPIFY_TRANSLATIONS = {
    158838489397: {  # policy_return — tiene ES y EN
        "es": {
            "title": "Política de Devoluciones",
            "body_html": "<h2>Política de Devoluciones</h2><p>Aceptamos devoluciones dentro de 30 días...</p>"
        },
        "en": {
            "title": "Return Policy",
            "body_html": "<h2>Return Policy</h2><p>We accept returns within 30 days...</p>"
        }
    },
    158888198453: {  # product_care — tiene ES y EN
        "es": {
            "title": "Cuidado de Productos",
            "body_html": "<h2>Cuidado de Productos</h2><p>Para mantener tus productos...</p>"
        },
        "en": {
            "title": "Product Care",
            "body_html": "<h2>Product Care</h2><p>To keep your products in optimal condition...</p>"
        }
    },
    158886101301: {  # policy_payment — SOLO ES, sin EN (traducción parcial)
        "es": {
            "title": "Métodos de Pago",
            "body_html": "<h2>Métodos de Pago</h2><p>Aceptamos las siguientes formas de pago...</p>"
        }
        # NO tiene "en" — caso de prueba para traducciones parciales.
        # sync_page() debe crear el registro ES y NO crear el registro EN.
    }
}

# ============================================================================
# MOCK DATA - Expected PostgreSQL Records
# ============================================================================

EXPECTED_DB_RECORDS = [
    # Español (default)
    {
        "sub_intent": "policy_return",
        "language": "es",
        "category": "general",
        "title": "Política de Devoluciones",
        "shopify_page_id": 158838489397,
        "content_preview": "Aceptamos devoluciones dentro de 30 días"
    },
    # Inglés
    {
        "sub_intent": "policy_return",
        "language": "en",
        "category": "general",
        "title": "Return Policy",
        "shopify_page_id": 158838489397,
        "content_preview": "We accept returns within 30 days"
    },
    # Product care - ES
    {
        "sub_intent": "product_care",
        "language": "es",
        "category": "general",
        "title": "Cuidado de Productos",
        "shopify_page_id": 158888198453,
        "content_preview": "Para mantener tus productos"
    },
    # Product care - EN
    {
        "sub_intent": "product_care",
        "language": "en",
        "category": "general",
        "title": "Product Care",
        "shopify_page_id": 158888198453,
        "content_preview": "To keep your products in optimal condition"
    },
    # Policy payment - SOLO ES (no EN)
    {
        "sub_intent": "policy_payment",
        "language": "es",
        "category": "general",
        "title": "Métodos de Pago",
        "shopify_page_id": 158886101301,
        "content_preview": "Aceptamos las siguientes formas de pago"
    }
    # NOTE: NO hay registro EN para policy_payment — caso de prueba
]

# ============================================================================
# FIXTURES - Mock Shopify Client
# ============================================================================

@pytest.fixture
def mock_shopify_kb_client():
    """
    Mock de ShopifyKBClient que simula respuestas de Shopify API.

    Métodos mockeados:
    - get_kb_pages()              → List[Tuple[ShopifyPage, Dict]]
    - get_page_translations()     → Dict[str, str]  (locale → body_html)
    - get_page_title_translation() → Optional[str]  ← FIX L1: faltaba este mock
    - shop_url                    → str              (atributo, no método)

    Por qué get_page_title_translation() es crítico:
    ─────────────────────────────────────────────────
    sync_page() llama este método para CADA locale de traducción:

        translated_title = await self.shopify.get_page_title_translation(page.id, locale)
        final_title = translated_title if translated_title else page.title

    Sin el mock explícito, AsyncMock() retorna un MagicMock genérico (objeto truthy).
    El check `if translated_title` evalúa True, y el MagicMock se pasa como título
    al upsert. Esto puede:
      a) Causar un TypeError en asyncpg (tipo incorrecto para columna title)
      b) Ser silenciado por `except Exception: continue` en el loop de traducciones
    En ambos casos, el registro EN nunca llega a la DB → test falla con "got 3 records".
    """
    from src.api.core.models.kb_models import ShopifyPage

    mock = AsyncMock()

    # ── get_kb_pages() ───────────────────────────────────────────────────────
    # Retorna lista de tuplas (ShopifyPage, metafields_dict) como el método real.
    async def mock_get_kb_pages(limit=None, validate_metadata=True):
        """Mock get_kb_pages con formato correcto (tuplas)"""
        result = []

        for page_data in MOCK_SHOPIFY_PAGES:
            # Instanciar ShopifyPage con todos los campos requeridos por Pydantic
            page = ShopifyPage(
                id=page_data["id"],
                title=page_data["title"],
                handle=page_data["handle"],
                body_html=page_data["body_html"],
                created_at=page_data["created_at"],
                updated_at=page_data["updated_at"],
                published_at=page_data["published_at"],
                tags=""  # Tags no se usan en KB; se usan los metafields
            )

            # Construir el dict de metafields en el formato que el servicio espera:
            # {"custom.kb_metadata": {"sub_intent": ..., "category": ..., "language": ...}}
            metafields = {"custom.kb_metadata": {}}
            for field in page_data.get("metafields", []):
                if field["key"] == "kb_sub_intent":
                    metafields["custom.kb_metadata"]["sub_intent"] = field["value"]
                elif field["key"] == "kb_category":
                    metafields["custom.kb_metadata"]["category"] = field["value"]
            # Idioma base siempre "es" (contenido original de la tienda)
            metafields["custom.kb_metadata"]["language"] = "es"

            result.append((page, metafields))

        return result

    mock.get_kb_pages = AsyncMock(side_effect=mock_get_kb_pages)

    # ── get_page_translations() ──────────────────────────────────────────────
    # Retorna {locale: body_html} con los locales de traducción (excluye ES,
    # que ya fue procesado como idioma base en sync_page()).
    async def mock_get_translations(page_id: int) -> Dict[str, str]:
        """
        Retorna traducciones como {locale: body_html}.

        Excluye el idioma base "es" porque sync_page() ya lo procesó en
        el Paso 1 (Sync DEFAULT LANGUAGE). Si se incluyera "es" aquí,
        se procesaría dos veces y el test de upsert fallaría.
        """
        translations_data = MOCK_SHOPIFY_TRANSLATIONS.get(page_id, {})
        result = {}
        for lang, data in translations_data.items():
            if lang != "es":  # Excluir idioma base — ya sincronizado
                result[lang] = data.get("body_html", "")
        return result

    mock.get_page_translations = AsyncMock(side_effect=mock_get_translations)

    # ── get_page_title_translation() ─────────────────────────────────────────
    # ✅ FIX L1: Este mock faltaba. Sin él, el servicio recibía un MagicMock
    # genérico como título, causando que los registros EN se perdieran.
    #
    # Contrato:
    # - Retorna str si hay título traducido para (page_id, locale)
    # - Retorna None si NO hay traducción → sync_page() usa título original como fallback
    async def mock_get_title_translation(page_id: int, locale: str) -> Optional[str]:
        """
        Retorna el título traducido para (page_id, locale) si existe en MOCK_SHOPIFY_TRANSLATIONS.

        Ejemplos:
          mock_get_title_translation(158838489397, "en") → "Return Policy"
          mock_get_title_translation(158886101301, "en") → None  (policy_payment sin EN)
          mock_get_title_translation(999999, "en")       → None  (page_id desconocida)
        """
        translations_data = MOCK_SHOPIFY_TRANSLATIONS.get(page_id, {})
        locale_data = translations_data.get(locale, {})
        # .get("title", None) retorna None explícitamente si el locale no existe,
        # replicando el comportamiento de la API real cuando no hay traducción.
        return locale_data.get("title", None)

    mock.get_page_title_translation = AsyncMock(side_effect=mock_get_title_translation)

    # ── shop_url ─────────────────────────────────────────────────────────────
    # Atributo string (no método async). sync_page() y sync_single_page() usan:
    #   shopify_url = f"https://{self.shopify.shop_url}/pages/{page.handle}"
    # Sin este atributo, se usaría el MagicMock de AsyncMock, generando una URL inválida.
    mock.shop_url = "test-store.myshopify.com"

    return mock


@pytest.fixture
def mock_shopify_client_with_failures():
    """
    Mock de ShopifyKBClient que simula fallos de API.

    Simula:
    - Timeouts
    - 500 errors
    - Rate limiting

    Uso:
        async def test_sync_failure_handling(mock_shopify_client_with_failures):
            client = mock_shopify_client_with_failures
            with pytest.raises(TimeoutError):
                await client.get_kb_pages()
    """
    mock = AsyncMock()
    mock.get_kb_pages = AsyncMock(side_effect=TimeoutError("Shopify API timeout"))
    return mock


# ============================================================================
# FIXTURES - Mock Redis Service
# ============================================================================

@pytest.fixture
def mock_redis_service():
    """
    Mock de RedisService con tracking completo de operaciones de cache.

    Features:
    - _cache: dict interno que simula el almacenamiento Redis
    - delete_calls: lista acumulada de keys que se intentaron eliminar
    - get/set/delete: comportamiento equivalente al RedisService real

    Uso:
        async def test_cache_invalidation(mock_redis_service):
            redis = mock_redis_service
            await service.sync_all_pages()
            assert "kb:policy_return:es:general" in redis.delete_calls
    """
    mock = AsyncMock()

    # Storage interno — simula el espacio de nombres de Redis
    mock._cache = {}
    # Lista acumulada de keys eliminadas — usada por verify_cache_invalidation()
    mock.delete_calls = []

    async def mock_get(key: str) -> Optional[str]:
        return mock._cache.get(key)

    async def mock_set(key: str, value: str, ttl: int = None):
        mock._cache[key] = value

    async def mock_delete(key: str):
        # Registrar la key en delete_calls ANTES de eliminarla del cache,
        # para que verify_cache_invalidation() pueda verificar la llamada
        # incluso si la key no existía (lo que es válido — delete es idempotente).
        mock.delete_calls.append(key)
        if key in mock._cache:
            del mock._cache[key]
        # Retornar True simula el comportamiento de RedisService.delete()
        # cuando la key existe. El servicio usa `if success:` para loggear,
        # pero no depende del valor para el flujo principal.
        return True

    mock.get = AsyncMock(side_effect=mock_get)
    mock.set = AsyncMock(side_effect=mock_set)
    mock.delete = AsyncMock(side_effect=mock_delete)
    mock.ping = AsyncMock(return_value=True)

    return mock


# ============================================================================
# FIXTURES - Database Utilities
# ============================================================================

@pytest.fixture
async def db_connection():
    """
    Conexión real a PostgreSQL para integration tests.

    IMPORTANTE: Usa la base de datos configurada en settings (normalmente
    la de desarrollo/test local). NO usa producción.

    Cleanup automático al finalizar cada test:
    - Elimina registros de las pages mock por shopify_page_id
    - Cierra la conexión

    Uso:
        async def test_sync_to_db(db_connection):
            records = await db_connection.fetch("SELECT * FROM kb_contents")
    """
    settings = get_settings()

    conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name
    )

    yield conn

    # Cleanup: eliminar solo los registros creados por los tests
    # (los IDs de las páginas mock son conocidos y constantes)
    await conn.execute("""
        DELETE FROM kb_contents
        WHERE shopify_page_id IN (158838489397, 158888198453, 158886101301)
    """)
    await conn.close()


@pytest.fixture
async def clean_kb_table(db_connection):
    """
    Limpia la tabla kb_contents antes del test y al finalizar.

    Uso:
        @pytest.mark.usefixtures("clean_kb_table")
        async def test_sync_from_scratch(db_connection):
            # Tabla está vacía garantizado al inicio
            ...
    """
    await db_connection.execute("DELETE FROM kb_contents")
    yield
    # db_connection fixture ya hace cleanup en su teardown


# ============================================================================
# FIXTURES - Expected Assertions
# ============================================================================

@pytest.fixture
def expected_cache_keys():
    """
    Lista de cache keys que DEBEN invalidarse después de un sync completo.

    Refleja exactamente los registros en EXPECTED_DB_RECORDS:
    - policy_return: ES + EN → 2 keys
    - product_care: ES + EN → 2 keys
    - policy_payment: solo ES → 1 key (sin EN por traducción parcial)
    Total: 5 keys
    """
    return [
        "kb:policy_return:es:general",
        "kb:policy_return:en:general",
        "kb:product_care:es:general",
        "kb:product_care:en:general",
        "kb:policy_payment:es:general",
        # kb:policy_payment:en:general NO debe aparecer — sin traducción EN
    ]


@pytest.fixture
def expected_db_count():
    """
    Counts esperados en DB después de sync completo de las 3 páginas mock.

    total: 5  (3 ES + 2 EN)
    es: 3     (policy_return, product_care, policy_payment)
    en: 2     (policy_return, product_care — NO policy_payment)
    """
    return {
        "total": 5,
        "es": 3,
        "en": 2,
        "policy_return": 2,   # ES + EN
        "product_care": 2,    # ES + EN
        "policy_payment": 1   # Solo ES
    }


# ============================================================================
# UTILITIES - Assertion Helpers
# ============================================================================

async def assert_kb_content_exists(
    conn: asyncpg.Connection,
    sub_intent: str,
    language: str,
    category: str = "general"
) -> bool:
    """
    Verifica que existe un registro en kb_contents con los parámetros dados.

    Returns:
        True si existe, False si no.
    """
    query = """
        SELECT COUNT(*)
        FROM kb_contents
        WHERE sub_intent = $1
          AND language = $2
          AND COALESCE(category, 'general') = $3
    """
    count = await conn.fetchval(query, sub_intent, language, category)
    return count > 0


async def get_kb_content(
    conn: asyncpg.Connection,
    sub_intent: str,
    language: str,
    category: str = "general"
) -> Optional[Dict]:
    """
    Obtiene un registro completo de kb_contents como dict.

    Returns:
        Dict con los datos del registro, o None si no existe.
    """
    query = """
        SELECT *
        FROM kb_contents
        WHERE sub_intent = $1
          AND language = $2
          AND COALESCE(category, 'general') = $3
    """
    row = await conn.fetchrow(query, sub_intent, language, category)
    return dict(row) if row else None


async def count_kb_records_by_language(
    conn: asyncpg.Connection,
    language: str
) -> int:
    """
    Cuenta registros en kb_contents filtrados por idioma.

    Returns:
        Número de registros para ese idioma.
    """
    query = "SELECT COUNT(*) FROM kb_contents WHERE language = $1"
    return await conn.fetchval(query, language)


# ============================================================================
# UTILITIES - Cache Verification
# ============================================================================

def verify_cache_invalidation(
    mock_redis: AsyncMock,
    expected_keys: List[str]
) -> bool:
    """
    Verifica que TODAS las keys esperadas fueron invalidadas (llamadas a delete()).

    No falla si hay keys extra invalidadas — solo verifica que las esperadas estén.

    Args:
        mock_redis:    Mock de RedisService con atributo delete_calls (List[str])
        expected_keys: Keys que DEBEN aparecer en delete_calls

    Returns:
        True si todas las expected_keys están en delete_calls, False si falta alguna.
    """
    deleted_keys = set(mock_redis.delete_calls)
    expected_keys_set = set(expected_keys)

    missing_keys = expected_keys_set - deleted_keys
    extra_keys = deleted_keys - expected_keys_set

    if missing_keys:
        print(f"⚠️  Keys NO invalidadas (faltantes): {missing_keys}")
        return False

    if extra_keys:
        # Informativo únicamente — no es error tener invalidaciones adicionales
        print(f"ℹ️  Keys invalidadas extras (no esperadas, OK): {extra_keys}")

    return True


# ============================================================================
# UTILITIES - Mock Helpers
# ============================================================================

def create_mock_db_pool(db_connection):
    """
    Crea un asyncpg.Pool mock con soporte de context manager asíncrono.

    asyncpg.Pool.acquire() se usa como `async with pool.acquire() as conn:`.
    Un AsyncMock simple no soporta esto — se necesita un @asynccontextmanager real.

    Args:
        db_connection: Conexión real de asyncpg para los tests

    Returns:
        AsyncMock configurado con acquire() como context manager válido.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_acquire():
        yield db_connection

    db_pool = AsyncMock()
    db_pool.acquire = mock_acquire
    return db_pool


# ============================================================================
# FIXTURES - Sync Service with Mocks
# ============================================================================

@pytest.fixture
async def kb_sync_service_with_mocks(
    mock_shopify_kb_client,
    mock_redis_service,
    db_connection
):
    """
    ShopifyKBSyncService configurado con mocks para integration tests.

    Conecta:
    - mock_shopify_kb_client  → simula Shopify API (get_kb_pages, translations, etc.)
    - mock_redis_service      → simula Redis (tracking de delete_calls)
    - db_connection           → conexión REAL a PostgreSQL (integration test real)

    El db_pool usa un asynccontextmanager para replicar el comportamiento de
    asyncpg.Pool.acquire() que el servicio usa internamente.

    Uso:
        async def test_full_sync(kb_sync_service_with_mocks):
            service = kb_sync_service_with_mocks
            report = await service.sync_all_pages()
            assert report.successful == 3
    """
    from src.api.services.shopify_kb_sync import ShopifyKBSyncService
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_acquire():
        """Context manager que expone la conexión real de test."""
        yield db_connection

    db_pool = AsyncMock()
    db_pool.acquire = mock_acquire  # Función CM, no AsyncMock — compatibilidad con async with

    service = ShopifyKBSyncService(
        shopify_client=mock_shopify_kb_client,
        db_pool=db_pool,
        redis_service=mock_redis_service
    )

    return service


# ============================================================================
# EXPORT ALL
# ============================================================================

__all__ = [
    # Mock data
    "MOCK_SHOPIFY_PAGES",
    "MOCK_SHOPIFY_TRANSLATIONS",
    "EXPECTED_DB_RECORDS",

    # Fixtures - Mocks
    "mock_shopify_kb_client",
    "mock_shopify_client_with_failures",
    "mock_redis_service",

    # Fixtures - Database
    "db_connection",
    "clean_kb_table",

    # Fixtures - Expected values
    "expected_cache_keys",
    "expected_db_count",

    # Utilities - Assertions
    "assert_kb_content_exists",
    "get_kb_content",
    "count_kb_records_by_language",
    "verify_cache_invalidation",
    "create_mock_db_pool",

    # Fixtures - Services
    "kb_sync_service_with_mocks"
]
