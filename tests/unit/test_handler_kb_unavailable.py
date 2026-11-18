"""
Tests del modo degradado de la base de conocimiento en el handler
(R-2 parte 2, 17/11/2026).

QUE SE PRUEBA
-------------
Cuando la intencion es INFORMATIVA y la base de conocimiento no puede responder,
get_mcp_conversation_recommendations() debe devolver un mensaje honesto en el
idioma del cliente, con enlace a la pagina de Shopify del tema, SIN productos,
y SIN usar nunca SimpleKnowledgeBase (contenido ficticio). Con respuesta
disponible, el comportamiento no cambia (regresion).

COMO SE AISLA (sin Redis, sin base de datos, sin arrancar la app)
------------------------------------------------------------------
* La deteccion de intencion se fija a INFORMATIONAL/policy_return (1.0):
  el test no depende de las reglas, que cambian con el tiempo.
* El gestor de estado de conversacion falla a proposito: el handler crea
  un contexto temporal (su camino de degradacion normal).
* `src.api.main_unified_redis` se sustituye por un objeto minimo con una base
  de conocimiento falsa. Asi NO se importa la app real, y se evita R-1 (la
  configuracion de structlog de los tests) y la cascada de arranque.
* `knowledge_base.get_knowledge_base` se convierte en una trampa: si alguien
  vuelve a llamarla, el test falla.
"""

import sys
import types

import pytest

from src.api.core.intent_types import (
    IntentDetectionResult,
    IntentType,
    InformationalSubIntent,
    KnowledgeBaseAnswer,
)

QUERY_EN = "What is your return policy?"


class FakeKB:
    """Base de conocimiento falsa con la misma firma que ShopifyKnowledgeBase.get_answer()."""

    def __init__(self, answer=None, exc=None):
        self.answer = answer
        self.exc = exc
        self.calls = []

    async def get_answer(self, sub_intent, language="es", category=None):
        self.calls.append((sub_intent, language, category))
        if self.exc is not None:
            raise self.exc
        return self.answer


@pytest.fixture
def install_kb(monkeypatch):
    """Prepara el entorno y devuelve una funcion para instalar la base de conocimiento falsa."""
    # 1. Deteccion de intencion activada, solo por reglas, con resultado fijo.
    monkeypatch.setenv("ENABLE_INTENT_DETECTION", "true")
    monkeypatch.setenv("ML_INTENT_ENABLED", "false")
    import src.api.core.intent_detection as intent_detection
    fixed = IntentDetectionResult(
        primary_intent=IntentType.INFORMATIONAL,
        sub_intent="policy_return",
        confidence=1.0,
        reasoning="test: resultado fijo",
        matched_patterns=[],
    )
    monkeypatch.setattr(intent_detection, "detect_intent", lambda query: fixed)

    # 2. Sin estado de conversacion: el handler usa un contexto temporal.
    import src.api.mcp.conversation_state_manager as csm

    async def _no_state_manager():
        raise RuntimeError("test: sin gestor de estado")

    monkeypatch.setattr(csm, "get_conversation_state_manager", _no_state_manager)

    # 3. Trampa: el respaldo antiguo con contenido ficticio no debe llamarse nunca.
    import src.api.core.knowledge_base as old_kb
    old_fallback_calls = []

    def _forbidden():
        # Se registra la llamada ANTES de lanzar: el handler antiguo capturaba
        # cualquier excepcion de este bloque, asi que lanzar no basta para detectarla.
        old_fallback_calls.append("get_knowledge_base")
        raise AssertionError("SimpleKnowledgeBase (contenido ficticio) no debe usarse")

    monkeypatch.setattr(old_kb, "get_knowledge_base", _forbidden)

    # 4. main_unified_redis falso (el handler lo importa con `from src.api import ...`).
    import src.api as api_package

    def _install(kb):
        state = types.SimpleNamespace(knowledge_base_v2=kb, knowledge_base=kb)
        fake_main = types.SimpleNamespace(
            app=types.SimpleNamespace(state=state),
            knowledge_base_v2=kb,
            knowledge_base=kb,
        )
        monkeypatch.setitem(sys.modules, "src.api.main_unified_redis", fake_main)
        monkeypatch.setattr(api_package, "main_unified_redis", fake_main, raising=False)

    _install.old_fallback_calls = old_fallback_calls
    return _install


async def _ask(language="en", query=QUERY_EN):
    from src.api.core.mcp_conversation_handler import get_mcp_conversation_recommendations
    return await get_mcp_conversation_recommendations(
        validated_user_id="test_user",
        validated_product_id=None,
        conversation_query=query,
        market_id="US",
        session_id="test_session_kb_unavailable",
        language=language,
    )


def _assert_honest_reply(response, language, reason):
    from src.api.core.localized_messages import kb_unavailable_message
    expected = kb_unavailable_message(language, "policy_return")
    assert response["type"] == "informational"
    assert response["answer"] == expected
    assert response["ai_response"] == expected
    assert response["recommendations"] == []
    assert "kb_document" not in response
    meta = response["metadata"]
    assert meta["knowledge_base_used"] is False
    assert meta["kb_unavailable"] is True
    assert meta["kb_unavailable_reason"] == reason
    assert meta["intent_detection"]["sub_intent"] == "policy_return"


async def test_no_answer_returns_honest_reply_in_english(install_kb):
    kb = FakeKB(answer=None)
    install_kb(kb)
    response = await _ask(language="en")
    _assert_honest_reply(response, "en", reason="no_answer")
    assert "/en/pages/como-devolver-un-producto" in response["answer"]
    # La consulta se hizo con el idioma del cliente y sin categoria.
    assert kb.calls == [(InformationalSubIntent.POLICY_RETURN, "en", None)]


async def test_no_instance_returns_honest_reply_without_old_fallback(install_kb):
    install_kb(None)  # sin base de conocimiento: la trampa de SimpleKnowledgeBase sigue armada
    response = await _ask(language="es")
    _assert_honest_reply(response, "es", reason="no_instance")
    assert "/pages/como-devolver-un-producto" in response["answer"]
    assert install_kb.old_fallback_calls == []  # nunca se llamo a SimpleKnowledgeBase


async def test_kb_exception_returns_honest_reply(install_kb):
    install_kb(FakeKB(exc=RuntimeError("test: base de datos caida")))
    response = await _ask(language="fr")
    _assert_honest_reply(response, "fr", reason="error")
    assert "/fr/pages/como-devolver-un-producto" in response["answer"]


async def test_answer_available_is_unchanged(install_kb, monkeypatch):
    """Regresion: con respuesta disponible se devuelve el documento tal cual, como antes."""
    import src.api.core.kb_contextualizer as kbc
    monkeypatch.setattr(kbc, "has_specific_entities", lambda **kwargs: False)
    document = "## Return policy\n\nTo return a product: contact us within 30 days."
    install_kb(FakeKB(answer=KnowledgeBaseAnswer(
        answer=document, sub_intent=InformationalSubIntent.POLICY_RETURN,
    )))
    response = await _ask(language="en")
    assert response["type"] == "informational"
    assert response["answer"] == document
    assert response["recommendations"] == []
    assert response["metadata"]["knowledge_base_used"] is True
    assert "kb_unavailable" not in response["metadata"]
