"""
Tests de sync_single_page(): idiomas publicados (R-13b) e invalidacion de Redis (R-15).

R-13b (22/11/2026), la sincronizacion incremental usa los idiomas publicados en Shopify:
    - los idiomas salen de la tienda (get_translation_locales), no de KB_SYNC_LANGUAGES;
    - si falta la traduccion de un idioma publicado, la fila NO se escribe (antes se
      guardaba el texto en espanol etiquetado como ese idioma: R-12) y se avisa;
    - nunca se borra una fila: get_page_translations() devuelve {} tambien cuando falla.
R-15 (22/11/2026), la sincronizacion incremental no invalidaba Redis:
    - tras escribir cada idioma se borra su clave "kb:{sub_intent}:{idioma}:{categoria}".

COMO SE AISLA (sin PostgreSQL, sin Redis, sin Shopify)
------------------------------------------------------
* El cliente de Shopify es un MagicMock con los metodos async como AsyncMock.
* _upsert_kb_content se sustituye por un AsyncMock: aqui interesa QUE se escribe
  (idioma, contenido), no como (eso lo cubren los tests de L2).
* _invalidate_cache NO se sustituye: se ejecuta el real contra un Redis falso, para
  comprobar la clave exacta que lee knowledge_base_v2 (_build_cache_key).
* Los logs se capturan con structlog.testing.capture_logs().

CONTROL NEGATIVO: contra el codigo anterior (lista KB_SYNC_LANGUAGES, texto en espanol
como respaldo, sin invalidacion) fallan los tests marcados con [R-13b] y [R-15].
"""

import types
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from src.api.services.shopify_kb_sync import ShopifyKBSyncService

PAGE_ID = 158935941429
BODY_ES = "<h2>Devoluciones</h2><p>Plazo de 30 dias.</p>"
BODY_EN = "<h2>Returns</h2><p>30 days.</p>"
BODY_FR = "<h2>Retours</h2><p>30 jours.</p>"
BODY_DE = "<h2>Rueckgabe</h2><p>30 Tage.</p>"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_shopify(published, translations, locales_error=None):
    """
    Cliente de Shopify falso.

    Args:
        published: idiomas de traduccion publicados (lo que devuelve get_translation_locales).
        translations: {idioma: html} que devuelve get_page_translations (solo los que existen).
        locales_error: si se indica, get_translation_locales lanza esta excepcion.
    """
    shopify = MagicMock()
    shopify.shop_url = "ai-shoppings.myshopify.com"
    # get_page_by_id es sincrono (sync_single_page lo llama con asyncio.to_thread).
    shopify.get_page_by_id = MagicMock(return_value=types.SimpleNamespace(
        id=PAGE_ID, handle="como-devolver-un-producto",
        title="Como devolver un producto?", body_html=BODY_ES,
    ))
    shopify.get_page_metafields = AsyncMock(return_value={
        "custom.kb_metadata": {"sub_intent": "policy_return", "language": "es"},
    })
    if locales_error is not None:
        shopify.get_translation_locales = AsyncMock(side_effect=locales_error)
    else:
        shopify.get_translation_locales = AsyncMock(return_value=list(published))
    shopify.get_page_translations = AsyncMock(return_value=dict(translations))
    shopify.get_page_title_translation = AsyncMock(side_effect=lambda pid, lang: f"titulo-{lang}")
    return shopify


def _make_service(shopify, redis_delete=None):
    """Servicio real con PostgreSQL sustituido y un Redis falso que registra los borrados."""
    redis = MagicMock()
    redis.delete = redis_delete or AsyncMock(return_value=True)
    service = ShopifyKBSyncService(shopify_client=shopify, db_pool=MagicMock(), redis_service=redis)
    service._upsert_kb_content = AsyncMock(return_value=None)
    return service, redis


def _written(service):
    """Idiomas escritos en kb_contents, en orden, con su contenido Markdown."""
    return [(c.kwargs["language"], c.kwargs["content"]) for c in service._upsert_kb_content.await_args_list]


def _deleted_keys(redis):
    return [c.args[0] for c in redis.delete.await_args_list]


def _events(cap_logs, name):
    return [e for e in cap_logs if e.get("event") == name]


# ---------------------------------------------------------------------------
# Idiomas publicados (R-13b)
# ---------------------------------------------------------------------------

async def test_all_published_languages_are_synced_with_their_own_text():
    """Con es/en/fr publicados y traducidos se escriben los tres, cada uno con su texto."""
    service, _ = _make_service(_make_shopify(["en", "fr"], {"en": BODY_EN, "fr": BODY_FR}))
    result = await service.sync_single_page(PAGE_ID)

    written = _written(service)
    assert [lang for lang, _ in written] == ["es", "en", "fr"]
    assert "Devoluciones" in written[0][1]
    assert "Returns" in written[1][1]
    assert "Retours" in written[2][1]
    assert result["status"] == "synced"
    assert result["languages_synced"] == ["es", "en", "fr"]
    assert result["languages_skipped"] == []


async def test_missing_translation_is_not_written_and_is_reported():
    """[R-13b] fr publicado sin traduccion: no se escribe (antes: texto en espanol como 'fr')."""
    service, _ = _make_service(_make_shopify(["en", "fr"], {"en": BODY_EN}))
    with structlog.testing.capture_logs() as cap_logs:
        result = await service.sync_single_page(PAGE_ID)

    assert [lang for lang, _ in _written(service)] == ["es", "en"]
    assert result["status"] == "synced"
    assert result["languages_skipped"] == ["fr"]
    missing = _events(cap_logs, "kb_translation_missing")
    assert len(missing) == 1 and missing[0]["language"] == "fr"
    assert missing[0]["log_level"] == "warning"


async def test_empty_translations_never_write_spanish_as_translation():
    """[R-13b] {} (sin traducciones o fallo tragado por el cliente): solo se escribe el idioma base."""
    service, _ = _make_service(_make_shopify(["en", "fr"], {}))
    result = await service.sync_single_page(PAGE_ID)

    written = _written(service)
    assert [lang for lang, _ in written] == ["es"]
    assert result["languages_skipped"] == ["en", "fr"]
    # Ninguna fila de traduccion lleva el texto en espanol.
    assert all(lang == "es" for lang, content in written if "Devoluciones" in content)


async def test_new_published_language_is_synced_without_configuration(monkeypatch):
    """[R-13b] Un idioma recien publicado en Shopify (de) se sincroniza sin tocar configuracion."""
    monkeypatch.delenv("KB_SYNC_LANGUAGES", raising=False)
    service, _ = _make_service(_make_shopify(["en", "fr", "de"], {"en": BODY_EN, "fr": BODY_FR, "de": BODY_DE}))
    result = await service.sync_single_page(PAGE_ID)
    assert result["languages_synced"] == ["es", "en", "fr", "de"]


async def test_kb_sync_languages_env_var_is_ignored(monkeypatch):
    """[R-13b] La variable retirada ya no limita los idiomas (antes "es" dejaba fuera en y fr)."""
    monkeypatch.setenv("KB_SYNC_LANGUAGES", "es")
    service, _ = _make_service(_make_shopify(["en", "fr"], {"en": BODY_EN, "fr": BODY_FR}))
    result = await service.sync_single_page(PAGE_ID)
    assert result["languages_synced"] == ["es", "en", "fr"]


async def test_locales_fetch_failure_syncs_only_default_language():
    """[R-13b] Si Shopify no dice que idiomas publica: solo el idioma base, con aviso."""
    shopify = _make_shopify([], {"en": BODY_EN}, locales_error=RuntimeError("shopify caido"))
    service, _ = _make_service(shopify)
    with structlog.testing.capture_logs() as cap_logs:
        result = await service.sync_single_page(PAGE_ID)

    assert [lang for lang, _ in _written(service)] == ["es"]
    assert result["status"] == "synced"
    failed = _events(cap_logs, "sync_single_page_locales_fetch_failed")
    assert len(failed) == 1 and failed[0]["fallback"] == "default_language_only"


async def test_no_row_is_ever_deleted():
    """[R-13b] Ni con traducciones ausentes ni con fallos se borra nada de kb_contents."""
    service, _ = _make_service(_make_shopify(["en", "fr"], {}))
    service._delete_page = AsyncMock()
    service.delete_kb_for_page = AsyncMock()
    await service.sync_single_page(PAGE_ID)
    service._delete_page.assert_not_awaited()
    service.delete_kb_for_page.assert_not_awaited()


async def test_service_init_logs_language_source_instead_of_configured_list():
    """[R-13b] El log de arranque ya no anuncia una lista manual de idiomas."""
    with structlog.testing.capture_logs() as cap_logs:
        _make_service(_make_shopify([], {}))
    init = _events(cap_logs, "service_initialized")
    assert init and init[0]["language_source"] == "shopify_published_locales"
    assert "configured_languages" not in init[0]


# ---------------------------------------------------------------------------
# Invalidacion de Redis (R-15)
# ---------------------------------------------------------------------------

async def test_each_written_language_invalidates_its_cache_key():
    """[R-15] Tras escribir cada idioma se borra su clave (la misma que lee knowledge_base_v2)."""
    service, redis = _make_service(_make_shopify(["en", "fr"], {"en": BODY_EN, "fr": BODY_FR}))
    await service.sync_single_page(PAGE_ID)
    assert _deleted_keys(redis) == [
        "kb:policy_return:es:general",
        "kb:policy_return:en:general",
        "kb:policy_return:fr:general",
    ]


async def test_skipped_language_does_not_touch_its_cache_key():
    """[R-15] Un idioma sin traduccion no se escribe y su clave no se toca."""
    service, redis = _make_service(_make_shopify(["en", "fr"], {"en": BODY_EN}))
    await service.sync_single_page(PAGE_ID)
    assert "kb:policy_return:fr:general" not in _deleted_keys(redis)


async def test_cache_key_matches_knowledge_base_reader():
    """[R-15] La clave que se borra es exactamente la que construye el lector del chat."""
    from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
    reader = ShopifyKnowledgeBase.__new__(ShopifyKnowledgeBase)  # sin __init__: solo la funcion pura
    service, redis = _make_service(_make_shopify(["en"], {"en": BODY_EN}))
    await service.sync_single_page(PAGE_ID)
    assert _deleted_keys(redis)[1] == reader._build_cache_key("policy_return", "en", None)


async def test_redis_failure_does_not_undo_the_database_write():
    """[R-15] Si Redis falla, la escritura cuenta como hecha y se avisa (la clave caducara sola)."""
    service, _ = _make_service(
        _make_shopify(["en"], {"en": BODY_EN}),
        redis_delete=AsyncMock(side_effect=ConnectionError("redis caido")),
    )
    with structlog.testing.capture_logs() as cap_logs:
        result = await service.sync_single_page(PAGE_ID)

    assert result["status"] == "synced"
    assert result["languages_synced"] == ["es", "en"]
    assert len(_events(cap_logs, "sync_single_page_cache_invalidation_failed")) == 2


# ---------------------------------------------------------------------------
# Regresion: lo que no cambia
# ---------------------------------------------------------------------------

async def test_page_without_kb_metadata_is_skipped_as_before():
    """Una pagina sin metadatos de la base de conocimiento se omite sin escribir nada."""
    shopify = _make_shopify(["en"], {"en": BODY_EN})
    shopify.get_page_metafields = AsyncMock(return_value={})
    service, redis = _make_service(shopify)
    result = await service.sync_single_page(PAGE_ID)
    assert result["status"] == "skipped"
    service._upsert_kb_content.assert_not_awaited()
    redis.delete.assert_not_awaited()


async def test_upsert_error_in_one_language_gives_partial_status_as_before():
    """Si falla la escritura de un idioma, los demas siguen y el estado es 'partial' (logica de estado
    sin cambios; con el codigo anterior falla solo porque fr no estaba en la lista "es,en")."""
    service, _ = _make_service(_make_shopify(["en", "fr"], {"en": BODY_EN, "fr": BODY_FR}))

    async def _fail_on_en(**kwargs):
        if kwargs["language"] == "en":
            raise RuntimeError("db caida")

    service._upsert_kb_content = AsyncMock(side_effect=_fail_on_en)
    result = await service.sync_single_page(PAGE_ID)
    assert result["status"] == "partial"
    assert result["languages_synced"] == ["es", "fr"]
    assert [e["language"] for e in result["errors"]] == ["en"]


# ---------------------------------------------------------------------------
# Cliente de Shopify: get_translation_locales()
# ---------------------------------------------------------------------------

async def test_client_get_translation_locales_returns_published_translation_locales():
    from src.api.integrations.shopify_kb_client import ShopifyKBClient
    client = ShopifyKBClient.__new__(ShopifyKBClient)  # sin __init__ (no hay red)
    client._get_shop_locales = AsyncMock(return_value=("es", ["en", "fr"]))
    assert await client.get_translation_locales() == ["en", "fr"]


async def test_client_get_translation_locales_propagates_errors():
    """No se traga el error: 'no hay idiomas' y 'no he podido saberlo' no se confunden."""
    from src.api.integrations.shopify_kb_client import ShopifyKBClient
    client = ShopifyKBClient.__new__(ShopifyKBClient)
    client._get_shop_locales = AsyncMock(side_effect=RuntimeError("graphql caido"))
    with pytest.raises(RuntimeError):
        await client.get_translation_locales()
