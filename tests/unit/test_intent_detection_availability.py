import logging

import pytest

from src.api.core.intent_detection import detect_intent
from src.api.core.intent_types import IntentType


@pytest.mark.parametrize(
    ("query", "expected_sub_intent"),
    [
        ("¿está disponible?", "product_availability"),
        ("Tienen este articulo en stock?", "product_availability"),
        ("Este producto esta disponible?", "product_availability"),
        ("Lo tiene en stock?", "product_availability"),
        ("hay stock?", "product_availability"),
        ("sigue disponible", "product_availability"),
    ],
)
def test_short_availability_queries_are_informational(query, expected_sub_intent):
    result = detect_intent(query)

    assert result.primary_intent == IntentType.INFORMATIONAL
    assert result.sub_intent == expected_sub_intent
    assert result.confidence >= 0.7
    assert result.reasoning == f"Question + {expected_sub_intent} keywords"


@pytest.mark.parametrize(
    ("query", "expected_sub_intent"),
    [
        ("¿Qué tallas tienen?", "product_sizing"),
        ("What sizes do they have?", "product_sizing"),
        ("¿Está disponible en mi talla?", "product_sizing"),
        ("¿Qué talla me recomiendas?", "product_sizing"),
    ],
)
def test_sizing_queries_do_not_regress_to_availability(query, expected_sub_intent):
    result = detect_intent(query)

    assert result.primary_intent == IntentType.INFORMATIONAL
    assert result.sub_intent == expected_sub_intent
    assert result.confidence >= 0.7


@pytest.mark.parametrize(
    "query",
    [
        "tienen vestidos negros",
        "do you have dresses",
        "quiero ver productos disponibles",
    ],
)
def test_generic_possessive_or_browsing_queries_do_not_trigger_availability(query):
    result = detect_intent(query)

    assert not (
        result.primary_intent == IntentType.INFORMATIONAL
        and result.sub_intent == "product_availability"
    )


@pytest.mark.parametrize(
    "query",
    [
        "¿está disponible?",
        "Tienen este articulo en stock?",
        "Este producto esta disponible?",
        "Lo tiene en stock?",
    ],
)
def test_short_availability_queries_do_not_hit_default_fallback(query, caplog):
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="src.api.core.intent_detection"):
        detect_intent(query)

    assert "No clear pattern match, defaulting to TRANSACTIONAL" not in caplog.text
