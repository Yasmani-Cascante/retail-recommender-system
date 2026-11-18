"""
Tests de src/api/core/localized_messages.py (R-2 parte 2 + R-4, 17/11/2026).

Modulo puro (sin IO): estos tests no necesitan Redis, base de datos ni red.
"""

import pytest

from src.api.core.intent_types import InformationalSubIntent
from src.api.core import localized_messages as lm


# ---------------------------------------------------------------------------
# normalize_language
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("es", "es"), ("en", "en"), ("fr", "fr"), ("de", "de"), ("it", "it"),
    ("en-US", "en"), ("fr_CH", "fr"), ("DE", "de"), (" it ", "it"),
    (None, "es"), ("", "es"), ("pt", "es"), ("zz-ZZ", "es"), (123, "es"),
])
def test_normalize_language(raw, expected):
    assert lm.normalize_language(raw) == expected


# ---------------------------------------------------------------------------
# Paginas y enlaces
# ---------------------------------------------------------------------------

def test_every_sub_intent_has_a_page_and_titles_in_all_languages():
    """Los 13 temas del enum tienen pagina, y cada pagina tiene titulo en los 5 idiomas."""
    for sub_intent in InformationalSubIntent:
        assert sub_intent.value in lm.KB_PAGE_HANDLES, f"tema sin pagina: {sub_intent.value}"
    for handle in set(lm.KB_PAGE_HANDLES.values()) | {lm.DEFAULT_KB_PAGE_HANDLE}:
        assert set(lm.KB_PAGE_TITLES[handle]) == set(lm.SUPPORTED_LANGUAGES), handle


@pytest.mark.parametrize("language, expected", [
    ("es", "/pages/como-devolver-un-producto"),           # principal: sin prefijo
    ("en", "/en/pages/como-devolver-un-producto"),        # publicado
    ("fr", "/fr/pages/como-devolver-un-producto"),        # publicado
    ("de", "/pages/como-devolver-un-producto"),           # no publicado: pagina en espanol
    ("it", "/pages/como-devolver-un-producto"),           # no publicado: pagina en espanol
    ("en-GB", "/en/pages/como-devolver-un-producto"),
    (None, "/pages/como-devolver-un-producto"),
])
def test_kb_page_url_locale_prefix(language, expected):
    assert lm.kb_page_url("policy_return", language) == expected


def test_kb_page_url_accepts_enum_and_unknown_topics():
    assert lm.kb_page_url(InformationalSubIntent.POLICY_SHIPPING, "es") == "/pages/como-funcionan-los-envios"
    # Un tema que no existe no rompe el mensaje: va a preguntas frecuentes.
    assert lm.kb_page_url("tema_inexistente", "es") == "/pages/preguntas-frecuentes-faq"
    assert lm.kb_page_url(None, "en") == "/en/pages/preguntas-frecuentes-faq"


# ---------------------------------------------------------------------------
# Mensaje honesto (sin respuesta de la base de conocimiento)
# ---------------------------------------------------------------------------

def test_kb_unavailable_message_texts():
    assert lm.kb_unavailable_message("es", "policy_return") == (
        "Ahora mismo no puedo consultar esa información. Puedes verla en "
        "[Devoluciones](/pages/como-devolver-un-producto) o volver a preguntarme en unos minutos."
    )
    assert lm.kb_unavailable_message("en-US", "policy_payment") == (
        "I can't access that information right now. You can find it in "
        "[Payment methods](/en/pages/metodos-de-pago) or ask me again in a few minutes."
    )


@pytest.mark.parametrize("language", ["es", "en", "fr", "de", "it", None, "pt"])
@pytest.mark.parametrize("sub_intent", [s.value for s in InformationalSubIntent])
def test_kb_unavailable_message_always_has_a_markdown_link(language, sub_intent):
    msg = lm.kb_unavailable_message(language, sub_intent)
    url = lm.kb_page_url(sub_intent, language)
    assert f"]({url})" in msg
    assert "{" not in msg and "}" not in msg  # ninguna plantilla sin rellenar


def test_kb_unavailable_message_contains_no_invented_store_data():
    """El mensaje no afirma datos de la tienda (la leccion de R-2)."""
    for language in lm.SUPPORTED_LANGUAGES:
        msg = lm.kb_unavailable_message(language, "policy_payment")
        for forbidden in ("CLABE", "+52", "MXN", "@", "días hábiles"):
            assert forbidden not in msg


# ---------------------------------------------------------------------------
# Texto provisional (R-4) y emergencia
# ---------------------------------------------------------------------------

def test_no_products_placeholder_spanish_text_unchanged():
    """El texto en espanol es el mismo que habia antes del cambio."""
    assert lm.no_products_placeholder("es", False) == (
        "No he encontrado productos para esta búsqueda. ¿Quieres que te muestre otra cosa?"
    )
    assert lm.no_products_placeholder("es", True) == "Aquí tienes algunas opciones que pueden encajar."


def test_no_products_placeholder_follows_language():
    assert lm.no_products_placeholder("en", False).startswith("I couldn't find any products")
    assert lm.no_products_placeholder("fr", True).startswith("Voici quelques options")
    assert lm.no_products_placeholder("pt", False) == lm.no_products_placeholder("es", False)


def test_emergency_message_is_localized():
    assert lm.emergency_message("en").startswith("Sorry, something went wrong")
    assert lm.emergency_message("de").startswith("Entschuldigung")
    assert lm.emergency_message(None) == lm.emergency_message("es")


@pytest.mark.parametrize("language", ["es", "en", "fr", "de", "it"])
def test_all_templates_differ_between_languages(language):
    """Cada idioma tiene su propio texto (no hay copias accidentales de otro idioma)."""
    others = [l for l in lm.SUPPORTED_LANGUAGES if l != language]
    for fn in (lambda l: lm.no_products_placeholder(l, False),
               lambda l: lm.no_products_placeholder(l, True),
               lm.emergency_message,
               lambda l: lm.kb_unavailable_message(l, "policy_return")):
        assert all(fn(language) != fn(o) for o in others)
