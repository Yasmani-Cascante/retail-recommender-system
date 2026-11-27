# tests/unit/test_r32_routing_rules.py
"""
R-32 (27/11/2026) -- Preguntas de garantia, pedidos y materiales que no llegan a su documento.

Pruebas de las tres correcciones de la capa 1 (RuleBasedIntentDetector) y de lo que NO debe cambiar.
Se prueba solo la capa de reglas (sin sklearn ni MiniLM): rapido, determinista y sin modelos.

  M1  "garantia/warranty" ya no puntua en devoluciones (POLICY_RETURN).
  M2  Un verbo de compra generico (comprar/buy/purchase/take/get/pay) dentro de una PREGUNTA sobre un tema de
      politica o cuenta ya no convierte la consulta en busqueda de productos.
  M3  "pedido/order" ya no puntua en envios (POLICY_SHIPPING).
  No regresion: una peticion de compra con una palabra de material, o una frase que no es pregunta, sigue
  siendo TRANSACCIONAL.

Las frases son ilustrativas del mecanismo; la medicion del efecto esta en el DCT (bateria + preguntas nuevas).
"""

import pytest

from src.api.core.intent_detection import RuleBasedIntentDetector
from src.api.core.intent_types import IntentType


@pytest.fixture(scope="module")
def detector():
    # Instancia nueva (no el singleton) para que las metricas de otras pruebas no interfieran.
    return RuleBasedIntentDetector()


def _scores_by_sub_intent(detector, query):
    """Puntuacion de cada tema informacional con la misma formula que _detect_informational."""
    scores = {}
    for sub_intent, patterns in detector._compiled_patterns["informational"].items():
        keyword_hits = sum(1 for p in patterns["keywords"] if p.search(query))
        if not keyword_hits:
            continue
        score = 0.4 * keyword_hits
        if any(p.search(query) for p in patterns["question_words"]):
            score += 0.3
        if any(p.search(query) for p in patterns["negative_context"]):
            score += 0.2
        scores[sub_intent.value] = round(score, 2)
    return scores


# ─── M1: garantia ya no es palabra clave de devoluciones ─────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "¿La garantía cubre una cremallera rota?",
    "Is the warranty valid after 60 days?",
])
def test_m1_warranty_word_no_longer_scores_for_returns(detector, query):
    scores = _scores_by_sub_intent(detector, query)
    # Estas frases no tienen ninguna palabra de devolucion: antes "garantia/warranty" sumaba 0,4 en policy_return;
    # ahora devoluciones no puntua y garantia si.
    assert "policy_return" not in scores
    assert scores.get("policy_warranty", 0) >= 0.4


def test_m1_warranty_question_with_a_time_reference_is_not_routed_to_returns(detector):
    # Antes: devoluciones 0,8 (garantia + dias) frente a garantia 0,4 -> devoluciones con 0,8 (decidia la capa 1).
    result = detector.detect("Si un vestido se rompe a los 45 días, ¿me lo cambian por garantía?")
    assert result.sub_intent != "policy_return"


# ─── M3: pedido/order ya no es palabra clave de envios ───────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "¿Cómo sé en qué estado está mi pedido?",
    "How can I check the status of my order?",
])
def test_m3_order_status_question_goes_to_orders_not_shipping(detector, query):
    result = detector.detect(query)
    assert result.primary_intent == IntentType.INFORMATIONAL
    assert result.sub_intent == "account_orders"


def test_m3_shipping_question_still_goes_to_shipping(detector):
    # Control: las preguntas de envio siguen reconociendose sin "pedido/order"
    result = detector.detect("¿Cuánto cuesta el envío a domicilio?")
    assert result.sub_intent == "policy_shipping"


# ─── M2: verbo de compra generico en una pregunta de politica ────────────────────────────────────

@pytest.mark.parametrize("query, expected_topic", [
    ("Do I have to pay shipping to return something?", {"policy_return", "policy_shipping"}),
    ("Se me descosió una costura a la semana de comprar un vestido, ¿lo cubre la garantía?", {"policy_warranty"}),
    ("I want to cancel the purchase I made this morning, is it still possible?", {"account_orders"}),
])
def test_m2_purchase_verb_inside_a_policy_question_is_not_transactional(detector, query, expected_topic):
    result = detector.detect(query)
    # Ya no es TRANSACTIONAL: devuelve el tema de politica con confianza < 0,7 para que la capa 2 lo revise
    assert result.primary_intent == IntentType.INFORMATIONAL
    assert result.sub_intent in expected_topic
    assert result.confidence < 0.7


# ─── No regresion: las compras siguen siendo compras ─────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "Do you have cotton t-shirts I can buy?",   # material: palabra que tambien describe el producto
    "Where can I buy leather boots?",
    "Can I buy this jacket in black?",          # sin palabra de ningun tema informacional
])
def test_purchase_questions_with_product_words_stay_transactional(detector, query):
    result = detector.detect(query)
    assert result.primary_intent == IntentType.TRANSACTIONAL


def test_purchase_statement_that_is_not_a_question_stays_transactional(detector):
    # El cambio solo aplica a preguntas
    result = detector.detect("Quiero comprar un vestido rojo con envío gratis")
    assert result.primary_intent == IntentType.TRANSACTIONAL
