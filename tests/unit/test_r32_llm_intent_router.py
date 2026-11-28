"""
R-32 M4 (27/11/2026): capa de rescate del enrutado de intencion con LLM
=======================================================================

Que protege este fichero
------------------------
1. EL PROMPT MEDIDO: el prompt de produccion es byte a byte el "v3" medido en el
   laboratorio (sha256 8691b753...). Si alguien lo edita sin volver a medir, falla.
2. EL DISPARADOR T1: el LLM solo se consulta para lo que hoy acabaria en el menu de
   ayuda (INFORMATIONAL + "unknown" + confianza >= umbral). Nada mas se toca.
3. NUNCA PEOR QUE HOY: "none", respuestas no validas, tiempo agotado, errores o la
   capa apagada dejan el resultado exactamente como estaba (el menu de ayuda).
4. METRICA Y LOG: cada decision se cuenta en recommender_llm_route_total
   {use="intent_router"} y se registra con el token `intent_llm_router`, sin el texto
   del cliente.
4b. CORTE AUTOMATICO (28/11/2026): tras N fallos seguidos no se llama al LLM durante
   el tiempo de espera; luego una sola llamada de prueba decide si se reanuda.
5. HANDLER: con la capa encendida, un mensaje "sin tema" llega a la pagina que eligio
   el LLM; con la capa apagada, al menu como antes.

Sin red: el cliente del LLM se sustituye por uno falso en todas las pruebas.
Evidencia y criterio: DCT_Fidelidad_Reformulacion_KB_23112026.md, 7.21-7.28.
"""

import asyncio
import logging
import sys
import types
from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY

from src.api.core import llm_intent_router as router
from src.api.core.intent_types import (
    InformationalSubIntent,
    IntentDetectionResult,
    IntentType,
    KnowledgeBaseAnswer,
)
from src.api.core.llm_routes import (
    LLM_ROUTES_BY_USE,
    ROUTE_ROUTER_BREAKER_OPEN,
    ROUTE_ROUTER_FAILED,
    ROUTE_ROUTER_NO_LABEL,
    ROUTE_ROUTER_PRODUCT_SEARCH,
    ROUTE_ROUTER_TOPIC,
    USE_INTENT_ROUTER,
)

# sha256 del prompt v3 medido el 27/11 (r32_m4_llm.py --prompt v3; DCT 7.26-7.27)
LAB_PROMPT_V3_SHA256 = "8691b7537ae8d5876915ef3df6b7e00fd58f574736451204af74e0b133ef7c21"


# ─── Utilidades ────────────────────────────────────────────────────────────────

def route_count(route: str) -> float:
    """Valor actual de recommender_llm_route_total{use="intent_router", route}."""
    value = REGISTRY.get_sample_value("recommender_llm_route_total", {"use": USE_INTENT_ROUTER, "route": route})
    return value or 0.0


def unknown_result(confidence: float = 0.9) -> IntentDetectionResult:
    """Resultado que hoy acaba en el menu de ayuda: informativo y sin tema."""
    return IntentDetectionResult(
        primary_intent=IntentType.INFORMATIONAL,
        sub_intent="unknown",
        confidence=confidence,
        reasoning="test: ML classification",
        matched_patterns=[],
    )


class FakeRouterClient:
    """Sustituto de UnifiedLLMClient: devuelve `content`, tarda `delay` s o lanza `error`."""

    def __init__(self, content="policy_warranty", delay=0.0, error=None):
        self.content, self.delay, self.error = content, delay, error
        self.calls = []

    async def complete(self, system, user):
        self.calls.append((system, user))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=self.content, model="openai/gpt-4.1-mini", input_tokens=400, output_tokens=3)


@pytest.fixture(autouse=True)
def closed_breaker(monkeypatch):
    """Cada prueba empieza con el corte cerrado y la configuracion por defecto (3 fallos, 60 s)."""
    monkeypatch.delenv("INTENT_ROUTER_BREAKER_FAILURES", raising=False)
    monkeypatch.delenv("INTENT_ROUTER_BREAKER_COOLDOWN_S", raising=False)
    router.reset_breaker()
    yield
    router.reset_breaker()


@pytest.fixture
def fake_client(monkeypatch):
    """Instala un cliente falso como singleton del modulo y enciende la capa."""
    monkeypatch.setenv("INTENT_ROUTER_ENABLED", "true")
    monkeypatch.delenv("INTENT_ROUTER_TIMEOUT_S", raising=False)

    def _install(**kwargs):
        client = FakeRouterClient(**kwargs)
        monkeypatch.setattr(router, "_router_client", client)
        return client
    return _install


# ============================================================================
# 1. El prompt es el medido
# ============================================================================

class TestPromptIsTheMeasuredOne:

    def test_prompt_sha256_matches_lab_v3(self):
        assert router.ROUTER_PROMPT_SHA256 == LAB_PROMPT_V3_SHA256

    def test_topic_labels_are_knowledge_base_sub_intents(self):
        # Cada tema que el LLM puede elegir tiene que existir como pagina (enum de la KB);
        # si no, el handler pediria una pagina inexistente.
        kb_values = {member.value for member in InformationalSubIntent}
        assert router.ROUTER_KB_TOPICS <= kb_values
        assert len(router.ROUTER_KB_TOPICS) == 11
        assert "unknown" not in router.ROUTER_KB_TOPICS and "general_faq" not in router.ROUTER_KB_TOPICS

    def test_router_routes_are_registered_for_the_metric(self):
        assert set(LLM_ROUTES_BY_USE[USE_INTENT_ROUTER]) == {
            ROUTE_ROUTER_TOPIC, ROUTE_ROUTER_PRODUCT_SEARCH, ROUTE_ROUTER_NO_LABEL, ROUTE_ROUTER_FAILED,
            ROUTE_ROUTER_BREAKER_OPEN}


# ============================================================================
# 2. Lectura de la respuesta (identica al laboratorio)
# ============================================================================

class TestParseRouterLabel:

    @pytest.mark.parametrize("text, expected", [
        ("policy_warranty", "policy_warranty"),
        ("  Policy_Warranty.\n", "policy_warranty"),       # espacios, mayusculas, punto final
        ("`product_search`", "product_search"),            # acentos graves
        ('"none"', "none"),
        ("label: account_orders", "account_orders"),       # una sola etiqueta como palabra suelta
        ("product_warranty", "invalid"),                   # etiqueta inventada (vista el 27/11)
        ("policy_return or policy_warranty", "invalid"),   # dos etiquetas -> ambigua
        ("", "invalid"),
        (None, "invalid"),
    ])
    def test_labels(self, text, expected):
        assert router.parse_router_label(text) == expected


# ============================================================================
# 3. Disparador T1: solo lo que hoy acaba en el menu
# ============================================================================

class TestShouldRescue:

    def test_informational_unknown_above_threshold_is_rescued(self):
        assert router.should_rescue(unknown_result(0.9), 0.7) is True
        assert router.should_rescue(unknown_result(0.5), 0.5) is True    # umbral 0.5 (ml_fallback / miniml)

    def test_below_threshold_is_not_rescued(self):
        # Por debajo del umbral el handler ya lo manda a productos: no es el menu.
        assert router.should_rescue(unknown_result(0.69), 0.7) is False

    @pytest.mark.parametrize("primary, sub", [
        (IntentType.INFORMATIONAL, "policy_return"),     # ya tiene pagina
        (IntentType.TRANSACTIONAL, "product_search"),    # compra
        (IntentType.GREETING, None),                     # saludo (R-36 es otro cambio)
    ])
    def test_other_results_are_not_rescued(self, primary, sub):
        result = IntentDetectionResult(primary_intent=primary, sub_intent=sub, confidence=0.95,
                                       reasoning="test", matched_patterns=[])
        assert router.should_rescue(result, 0.7) is False

    def test_none_is_not_rescued(self):
        assert router.should_rescue(None, 0.7) is False


# ============================================================================
# 4. Aplicar la decision
# ============================================================================

class TestApplyRouterDecision:

    def test_topic_keeps_informational_and_sets_page(self):
        original = unknown_result(0.82)
        decision = router.RouterDecision(label="policy_warranty", route=ROUTE_ROUTER_TOPIC, elapsed_ms=800)
        new = router.apply_router_decision(original, decision)
        assert (new.primary_intent, new.sub_intent, new.confidence) == (IntentType.INFORMATIONAL, "policy_warranty", 0.82)
        assert new.reasoning.startswith("LLM router (R-32 M4): topic=policy_warranty")
        assert original.sub_intent == "unknown"   # el original no se modifica

    def test_product_search_becomes_transactional(self):
        decision = router.RouterDecision(label="product_search", route=ROUTE_ROUTER_PRODUCT_SEARCH, elapsed_ms=800)
        new = router.apply_router_decision(unknown_result(0.82), decision)
        assert (new.primary_intent, new.sub_intent, new.confidence) == (IntentType.TRANSACTIONAL, "product_search", 0.82)

    @pytest.mark.parametrize("decision", [
        router.RouterDecision(label="none", route=ROUTE_ROUTER_NO_LABEL, elapsed_ms=700),
        router.RouterDecision(label="invalid", route=ROUTE_ROUTER_NO_LABEL, elapsed_ms=700),
        router.RouterDecision(label="", route=ROUTE_ROUTER_FAILED, elapsed_ms=3000, error="TimeoutError"),
        # defensa: un tema que no es pagina nunca se aplica, aunque el camino diga "topic"
        router.RouterDecision(label="general_faq", route=ROUTE_ROUTER_TOPIC, elapsed_ms=700),
    ])
    def test_everything_else_keeps_the_menu(self, decision):
        original = unknown_result()
        assert router.apply_router_decision(original, decision) is original


# ============================================================================
# 5. Llamada al LLM: decisiones, tiempo agotado, errores, metrica y log
# ============================================================================

class TestClassifyUnknownRoute:

    @pytest.mark.parametrize("content, label, route", [
        ("policy_warranty", "policy_warranty", ROUTE_ROUTER_TOPIC),
        ("product_search", "product_search", ROUTE_ROUTER_PRODUCT_SEARCH),
        ("none", "none", ROUTE_ROUTER_NO_LABEL),
        ("product_warranty", "invalid", ROUTE_ROUTER_NO_LABEL),
    ])
    async def test_decision_and_metric(self, fake_client, content, label, route):
        client = fake_client(content=content)
        before = route_count(route)
        decision = await router.classify_unknown_route("se me rompio la cremallera, ¿me la cambian?")
        assert (decision.label, decision.route) == (label, route)
        assert route_count(route) == before + 1
        # Se envia el prompt medido como sistema y el mensaje del cliente tal cual
        assert client.calls == [(router.ROUTER_SYSTEM_PROMPT, "se me rompio la cremallera, ¿me la cambian?")]

    async def test_timeout_keeps_menu_and_never_raises(self, fake_client, monkeypatch):
        fake_client(content="policy_warranty", delay=0.5)
        monkeypatch.setenv("INTENT_ROUTER_TIMEOUT_S", "0.05")
        before = route_count(ROUTE_ROUTER_FAILED)
        decision = await router.classify_unknown_route("hola")
        assert decision.route == ROUTE_ROUTER_FAILED and decision.label == ""
        assert decision.elapsed_ms < 400       # corto por el limite, no por la respuesta lenta
        assert route_count(ROUTE_ROUTER_FAILED) == before + 1

    async def test_client_error_keeps_menu_and_never_raises(self, fake_client):
        fake_client(error=RuntimeError("HTTP 503 con datos que no deben ir al log"))
        decision = await router.classify_unknown_route("hola")
        assert (decision.route, decision.error) == (ROUTE_ROUTER_FAILED, "RuntimeError")

    async def test_missing_api_key_keeps_menu(self, monkeypatch):
        # Sin cliente creado y sin clave: UnifiedLLMClient lanza ValueError al crearse -> failed.
        monkeypatch.setattr(router, "_router_client", None)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        decision = await router.classify_unknown_route("hola")
        assert decision.route == ROUTE_ROUTER_FAILED

    async def test_log_has_token_and_no_customer_text(self, fake_client, caplog):
        fake_client(content="account_orders")
        secret_text = "mi pedido 12345 a nombre de Maria Perez no llega"
        with caplog.at_level(logging.INFO, logger=router.logger.name):
            await router.classify_unknown_route(secret_text)
        lines = [r.getMessage() for r in caplog.records if "intent_llm_router route=" in r.getMessage()]
        assert len(lines) == 1
        assert "route=topic label=account_orders" in lines[0]
        assert f"query_chars={len(secret_text)}" in lines[0]
        assert "Maria" not in lines[0] and "12345" not in lines[0]

    @pytest.mark.parametrize("raw, expected", [("", 3.0), ("abc", 3.0), ("0", 3.0), ("-1", 3.0), ("1.5", 1.5)])
    def test_timeout_setting(self, monkeypatch, raw, expected):
        monkeypatch.setenv("INTENT_ROUTER_TIMEOUT_S", raw)
        assert router._router_timeout_s() == expected


# ============================================================================
# 5b. Corte automatico (circuit breaker)
# ============================================================================

class FakeClock:
    """Reloj controlado por la prueba (sustituye a router._now)."""

    def __init__(self, start=1000.0):
        self.value = start

    def __call__(self):
        return self.value


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(router, "_now", fake)
    return fake


class TestCircuitBreaker:

    async def test_opens_after_three_consecutive_failures(self, fake_client, clock):
        client = fake_client(error=RuntimeError("OpenRouter caido"))
        for _ in range(3):
            assert (await router.classify_unknown_route("hola")).route == ROUTE_ROUTER_FAILED
        assert len(client.calls) == 3
        # Cuarto mensaje: corte abierto -> sin llamada, menu al instante, contado en la metrica
        before = route_count(ROUTE_ROUTER_BREAKER_OPEN)
        decision = await router.classify_unknown_route("hola")
        assert (decision.route, decision.elapsed_ms) == (ROUTE_ROUTER_BREAKER_OPEN, 0.0)
        assert len(client.calls) == 3
        assert route_count(ROUTE_ROUTER_BREAKER_OPEN) == before + 1

    async def test_a_response_resets_the_count(self, fake_client, clock):
        client = fake_client(error=RuntimeError("fallo"))
        await router.classify_unknown_route("a"); await router.classify_unknown_route("b")
        client.error, client.content = None, "none"        # "none" es una respuesta: no es un fallo
        assert (await router.classify_unknown_route("c")).route == ROUTE_ROUTER_NO_LABEL
        client.error = RuntimeError("fallo")
        await router.classify_unknown_route("d"); await router.classify_unknown_route("e")
        # 2 + respuesta + 2: nunca 3 seguidos -> el corte sigue cerrado
        assert (await router.classify_unknown_route("f")).route == ROUTE_ROUTER_FAILED
        assert len(client.calls) == 6

    async def test_invalid_answers_do_not_open_it(self, fake_client, clock):
        client = fake_client(content="no se que decir")
        for _ in range(5):
            assert (await router.classify_unknown_route("x")).route == ROUTE_ROUTER_NO_LABEL
        assert len(client.calls) == 5

    async def test_after_cooldown_one_trial_closes_it(self, fake_client, clock, caplog):
        client = fake_client(error=RuntimeError("fallo"))
        for _ in range(3):
            await router.classify_unknown_route("x")
        clock.value += 59.9                                 # aun dentro de los 60 s
        assert (await router.classify_unknown_route("x")).route == ROUTE_ROUTER_BREAKER_OPEN
        clock.value += 0.2                                  # pasados los 60 s: llamada de prueba
        client.error, client.content = None, "policy_return"
        with caplog.at_level(logging.INFO, logger=router.logger.name):
            assert (await router.classify_unknown_route("x")).route == ROUTE_ROUTER_TOPIC
        messages = [r.getMessage() for r in caplog.records]
        assert any("intent_llm_router_breaker state=half_open" in m for m in messages)
        assert any("intent_llm_router_breaker state=closed" in m for m in messages)
        # Cerrado: las siguientes llaman con normalidad
        assert (await router.classify_unknown_route("x")).route == ROUTE_ROUTER_TOPIC
        assert len(client.calls) == 5

    async def test_failed_trial_reopens_immediately(self, fake_client, clock, caplog):
        client = fake_client(error=RuntimeError("fallo"))
        for _ in range(3):
            await router.classify_unknown_route("x")
        clock.value += 61
        with caplog.at_level(logging.WARNING, logger=router.logger.name):
            assert (await router.classify_unknown_route("x")).route == ROUTE_ROUTER_FAILED   # la prueba falla
        assert any("state=open" in r.getMessage() and "trial=True" in r.getMessage() for r in caplog.records)
        assert (await router.classify_unknown_route("x")).route == ROUTE_ROUTER_BREAKER_OPEN  # 60 s mas
        assert len(client.calls) == 4

    async def test_only_one_trial_while_half_open(self, fake_client, clock):
        # Pasado el tiempo de espera llegan 3 mensajes a la vez: solo uno llama (la prueba),
        # los otros dos reciben el menu al instante en vez de esperar a un LLM que quiza siga caido.
        client = fake_client(error=RuntimeError("fallo"))
        for _ in range(3):
            await router.classify_unknown_route("x")
        clock.value += 61
        client.error, client.content, client.delay = None, "policy_return", 0.05
        routes = [d.route for d in await asyncio.gather(*(router.classify_unknown_route("x") for _ in range(3)))]
        assert sorted(routes) == sorted([ROUTE_ROUTER_TOPIC, ROUTE_ROUTER_BREAKER_OPEN, ROUTE_ROUTER_BREAKER_OPEN])
        assert len(client.calls) == 4

    async def test_limits_come_from_the_environment(self, fake_client, clock, monkeypatch):
        monkeypatch.setenv("INTENT_ROUTER_BREAKER_FAILURES", "1")
        monkeypatch.setenv("INTENT_ROUTER_BREAKER_COOLDOWN_S", "5")
        client = fake_client(error=RuntimeError("fallo"))
        await router.classify_unknown_route("x")                       # 1 fallo basta
        assert (await router.classify_unknown_route("x")).route == ROUTE_ROUTER_BREAKER_OPEN
        clock.value += 5.1
        client.error, client.content = None, "none"
        assert (await router.classify_unknown_route("x")).route == ROUTE_ROUTER_NO_LABEL
        assert len(client.calls) == 2

    @pytest.mark.parametrize("raw, failures, cooldown", [
        ("", 3, 60.0), ("abc", 3, 60.0), ("0", 3, 60.0), ("-2", 3, 60.0), ("5", 5, 5.0),
    ])
    def test_breaker_settings(self, monkeypatch, raw, failures, cooldown):
        monkeypatch.setenv("INTENT_ROUTER_BREAKER_FAILURES", raw)
        monkeypatch.setenv("INTENT_ROUTER_BREAKER_COOLDOWN_S", raw)
        assert (router._breaker_failure_limit(), router._breaker_cooldown_s()) == (failures, cooldown)


class TestRescueIfUnknown:

    async def test_switched_off_never_calls_the_llm(self, fake_client, monkeypatch):
        client = fake_client(content="policy_warranty")
        monkeypatch.setenv("INTENT_ROUTER_ENABLED", "false")
        original = unknown_result()
        assert await router.rescue_if_unknown(original, "hola", 0.7) is original
        assert client.calls == []

    async def test_known_topic_never_calls_the_llm(self, fake_client):
        client = fake_client(content="policy_warranty")
        result = IntentDetectionResult(primary_intent=IntentType.INFORMATIONAL, sub_intent="policy_return",
                                       confidence=1.0, reasoning="test", matched_patterns=[])
        assert await router.rescue_if_unknown(result, "¿puedo devolverlo?", 0.7) is result
        assert client.calls == []

    async def test_unknown_is_rescued(self, fake_client):
        fake_client(content="product_material")
        new = await router.rescue_if_unknown(unknown_result(), "¿el poliester reciclado es resistente?", 0.7)
        assert (new.primary_intent, new.sub_intent) == (IntentType.INFORMATIONAL, "product_material")


# ============================================================================
# 6. Handler: el mensaje "sin tema" llega a la pagina elegida
#    (mismo aislamiento que test_handler_kb_unavailable.py: sin Redis, sin base de
#    datos, sin arrancar la app; intencion fijada a INFORMATIONAL/unknown 0,9)
# ============================================================================

class FakeKB:
    """Base de conocimiento falsa: guarda con que sub_intent se le pregunto."""

    def __init__(self):
        self.calls = []

    async def get_answer(self, sub_intent, language="es", category=None):
        self.calls.append(sub_intent)
        return KnowledgeBaseAnswer(answer=f"## Documento {sub_intent.value}", sub_intent=sub_intent)


@pytest.fixture
def handler_env(monkeypatch):
    """Prepara el handler con intencion fija 'sin tema' y una base de conocimiento falsa."""
    monkeypatch.setenv("ENABLE_INTENT_DETECTION", "true")
    monkeypatch.setenv("ML_INTENT_ENABLED", "false")
    import src.api.core.intent_detection as intent_detection
    monkeypatch.setattr(intent_detection, "detect_intent", lambda query: unknown_result(0.9))

    import src.api.mcp.conversation_state_manager as csm

    async def _no_state_manager():
        raise RuntimeError("test: sin gestor de estado")
    monkeypatch.setattr(csm, "get_conversation_state_manager", _no_state_manager)

    import src.api.core.kb_contextualizer as kbc
    monkeypatch.setattr(kbc, "has_specific_entities", lambda **kwargs: False)

    kb = FakeKB()
    import src.api as api_package
    state = types.SimpleNamespace(knowledge_base_v2=kb, knowledge_base=kb)
    fake_main = types.SimpleNamespace(app=types.SimpleNamespace(state=state), knowledge_base_v2=kb, knowledge_base=kb)
    monkeypatch.setitem(sys.modules, "src.api.main_unified_redis", fake_main)
    monkeypatch.setattr(api_package, "main_unified_redis", fake_main, raising=False)
    return kb


async def _ask(query="la cremallera se rompio al mes, ¿me la cambian?"):
    from src.api.core.mcp_conversation_handler import get_mcp_conversation_recommendations
    return await get_mcp_conversation_recommendations(
        validated_user_id="test_user", validated_product_id=None, conversation_query=query,
        market_id="US", session_id="test_session_r32_m4", language="es",
    )


async def test_handler_llm_topic_reaches_its_page(handler_env, fake_client):
    fake_client(content="policy_warranty")
    response = await _ask()
    assert handler_env.calls == [InformationalSubIntent.POLICY_WARRANTY]
    assert response["type"] == "informational"
    meta = response["metadata"]["intent_detection"]
    assert meta["sub_intent"] == "policy_warranty"
    assert meta["reasoning"].startswith("LLM router (R-32 M4)")


async def test_handler_switched_off_keeps_the_menu(handler_env, fake_client, monkeypatch):
    client = fake_client(content="policy_warranty")
    monkeypatch.setenv("INTENT_ROUTER_ENABLED", "false")
    await _ask()
    assert handler_env.calls == [InformationalSubIntent.UNKNOWN]   # el menu de ayuda, como antes
    assert client.calls == []


async def test_handler_breaker_open_keeps_the_menu_without_calling(handler_env, fake_client, monkeypatch):
    client = fake_client(content="policy_warranty")
    monkeypatch.setattr(router, "_breaker_open_until", router._now() + 60)   # corte abierto
    response = await _ask()
    assert handler_env.calls == [InformationalSubIntent.UNKNOWN]             # el menu, al instante
    assert client.calls == []
    assert response["type"] == "informational"


async def test_handler_llm_failure_keeps_the_menu(handler_env, fake_client):
    fake_client(error=RuntimeError("test: OpenRouter caido"))
    response = await _ask()
    assert handler_env.calls == [InformationalSubIntent.UNKNOWN]
    assert response["type"] == "informational"


class _StopAtProductBranch(BaseException):
    """Centinela: hereda de BaseException para que el `except Exception` del handler no la capture."""


async def test_handler_product_search_takes_the_product_branch(handler_env, fake_client, monkeypatch):
    # La busqueda de productos necesita servicios (Redis, catalogo, LLM del redactor) que la prueba
    # no debe tocar. Se detiene el handler JUSTO al entrar en la rama de compra: su log fijo
    # "TRANSACTIONAL intent detected" lanza una excepcion centinela. Asi se comprueba que el
    # mensaje sale de la rama informativa (sin consultar la base de conocimiento) sin ejecutar
    # nada del flujo de productos.
    import src.api.core.mcp_conversation_handler as handler_module
    real_logger = handler_module.logger

    class _LoggerProxy:
        def __getattr__(self, name):
            return getattr(real_logger, name)

        def info(self, msg, *args, **kwargs):
            if "TRANSACTIONAL intent detected" in str(msg):
                raise _StopAtProductBranch()
            return real_logger.info(msg, *args, **kwargs)

    monkeypatch.setattr(handler_module, "logger", _LoggerProxy())
    fake_client(content="product_search")
    with pytest.raises(_StopAtProductBranch):
        await _ask("ideas de regalo para mi papa, menos de 40")
    assert handler_env.calls == []   # no se consulto la base de conocimiento
