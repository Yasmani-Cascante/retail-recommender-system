"""
Paso 1 del plan de modelos (25/11/2026): configuracion por uso + metrica de caminos
==================================================================================

Que protege este fichero
------------------------
1. EQUIVALENCIA: con las variables nuevas ausentes o con el valor de hoy, cada uso
   envia exactamente la misma peticion que antes del cambio (modelo, max_tokens,
   temperatura). Los valores esperados estan escritos como literales a proposito:
   son los que el codigo enviaba con GPT4O_MINI_FALLBACK_CONFIG (y los 0.3 / 120
   fijados en kb_contextualizer.py y visual_search_router.py). Si alguien cambia un
   valor por defecto, estas pruebas fallan.
2. INDEPENDENCIA: cambiar el modelo de un uso no cambia el de los otros (el problema
   que motivo el paso 1: un dict compartido por cuatro usos).
3. METRICA: cada texto entregado incrementa recommender_llm_route_total con el camino
   correcto, y medir nunca rompe una respuesta.

Las pruebas leen el contador con REGISTRY.get_sample_value y comparan diferencias
(antes/despues), porque el contador es global al proceso de pytest.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import REGISTRY

from src.api.core import claude_config
from src.api.core import llm_routes
from src.api.core.llm_routes import (
    LLM_ROUTES_BY_USE,
    USE_KB_REFORMULATION,
    USE_PRODUCT_REDACTOR,
    USE_VISUAL_SEARCH_MESSAGE,
)

# Variables nuevas del paso 1 (deben coincidir con env-vars.yaml)
USE_ENV_VARS = (
    "KB_REFORMULATION_LLM_MODEL",
    "PRODUCT_REDACTOR_LLM_MODEL",
    "VISUAL_SEARCH_MESSAGE_LLM_MODEL",
)
TODAY_MODEL = "openai/gpt-4o-mini"


def route_count(use: str, route: str) -> float:
    """Valor actual de recommender_llm_route_total{use, route} (0.0 si no existe la serie)."""
    value = REGISTRY.get_sample_value("recommender_llm_route_total", {"use": use, "route": route})
    return value or 0.0


@pytest.fixture
def clean_use_env(monkeypatch):
    """Quita las tres variables nuevas: cada prueba parte del 'no configurado'."""
    for name in USE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class RecordingLLMClient:
    """
    Sustituto de UnifiedLLMClient: guarda con que parametros se creo y devuelve una
    respuesta fija (o lanza `error` si se le pasa). No hace llamadas de red.
    """
    created = []  # lista de dicts con los parametros de cada instancia creada

    def __init__(self, provider, model, max_tokens, temperature, *, content="texto del modelo", error=None):
        self.provider, self.model = provider, model
        self.max_tokens, self.temperature = max_tokens, temperature
        self._content, self._error = content, error
        RecordingLLMClient.created.append(
            {"provider": provider, "model": model, "max_tokens": max_tokens, "temperature": temperature}
        )

    async def complete(self, system, user):
        if self._error is not None:
            raise self._error
        return SimpleNamespace(content=self._content, model=self.model, input_tokens=10, output_tokens=5)


# ============================================================================
# 1. Configuracion por uso
# ============================================================================

class TestUseConfigDefaultsAreTodaysValues:
    """Equivalencia: sin variables, cada uso queda EXACTAMENTE como antes del cambio."""

    def test_kb_reformulation_defaults(self, clean_use_env):
        cfg = claude_config.get_kb_reformulation_llm_config()
        assert (cfg["provider"], cfg["model"], cfg["max_tokens"], cfg["temperature"]) == \
            ("openrouter", TODAY_MODEL, 300, 0.3)
        assert cfg["model_source"] == "default"
        assert cfg["use"] == USE_KB_REFORMULATION

    def test_product_redactor_defaults(self, clean_use_env):
        cfg = claude_config.get_product_redactor_llm_config()
        assert (cfg["provider"], cfg["model"], cfg["max_tokens"], cfg["temperature"]) == \
            ("openrouter", TODAY_MODEL, 300, 0.7)
        assert cfg["use"] == USE_PRODUCT_REDACTOR

    def test_visual_search_message_defaults(self, clean_use_env):
        cfg = claude_config.get_visual_search_message_llm_config()
        assert (cfg["provider"], cfg["model"], cfg["max_tokens"], cfg["temperature"]) == \
            ("openrouter", TODAY_MODEL, 120, 0.7)
        assert cfg["use"] == USE_VISUAL_SEARCH_MESSAGE

    def test_shared_dict_no_longer_exists(self):
        # El dict compartido se retira: si alguien lo vuelve a importar, falla aqui.
        assert not hasattr(claude_config, "GPT4O_MINI_FALLBACK_CONFIG")

    def test_use_names_match_llm_routes(self, clean_use_env):
        # Los nombres de uso de la configuracion y de la metrica son los mismos.
        uses = {
            claude_config.get_kb_reformulation_llm_config()["use"],
            claude_config.get_product_redactor_llm_config()["use"],
            claude_config.get_visual_search_message_llm_config()["use"],
        }
        assert uses == set(LLM_ROUTES_BY_USE)


class TestUseConfigFromEnvironment:

    def test_each_use_reads_only_its_own_variable(self, clean_use_env):
        clean_use_env.setenv("KB_REFORMULATION_LLM_MODEL", "openai/gpt-4.1-mini")
        kb = claude_config.get_kb_reformulation_llm_config()
        redactor = claude_config.get_product_redactor_llm_config()
        vs = claude_config.get_visual_search_message_llm_config()
        # Solo cambia el uso configurado; los otros siguen con el modelo de hoy
        assert (kb["model"], kb["model_source"]) == ("openai/gpt-4.1-mini", "env")
        assert (redactor["model"], redactor["model_source"]) == (TODAY_MODEL, "default")
        assert (vs["model"], vs["model_source"]) == (TODAY_MODEL, "default")
        # max_tokens y temperatura no dependen del modelo elegido
        assert (kb["max_tokens"], kb["temperature"]) == (300, 0.3)

    def test_value_is_stripped(self, clean_use_env):
        clean_use_env.setenv("PRODUCT_REDACTOR_LLM_MODEL", "  openai/gpt-4.1-mini \n")
        assert claude_config.get_product_redactor_llm_config()["model"] == "openai/gpt-4.1-mini"

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_value_falls_back_to_default(self, clean_use_env, blank):
        clean_use_env.setenv("VISUAL_SEARCH_MESSAGE_LLM_MODEL", blank)
        cfg = claude_config.get_visual_search_message_llm_config()
        assert (cfg["model"], cfg["model_source"]) == (TODAY_MODEL, "default")

    def test_read_on_every_call_not_frozen_at_import(self, clean_use_env):
        # Leccion del 21/03/2026: nada de caches a nivel de modulo.
        assert claude_config.get_kb_reformulation_llm_config()["model"] == TODAY_MODEL
        clean_use_env.setenv("KB_REFORMULATION_LLM_MODEL", "x/y")
        assert claude_config.get_kb_reformulation_llm_config()["model"] == "x/y"

    def test_returned_dict_is_a_fresh_copy(self, clean_use_env):
        # Un llamador que modifique su dict no contamina a otro uso ni a la siguiente llamada.
        first = claude_config.get_product_redactor_llm_config()
        first["model"] = "contaminado"
        assert claude_config.get_product_redactor_llm_config()["model"] == TODAY_MODEL

    def test_env_vars_yaml_declares_todays_model_for_every_use(self):
        # env-vars.yaml es la fuente de verdad de las variables planas en produccion.
        import pathlib
        import yaml
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        env = yaml.safe_load((repo_root / "env-vars.yaml").read_text(encoding="utf-8"))
        for name in USE_ENV_VARS:
            assert env.get(name) == TODAY_MODEL, name


class TestWarmupModels:

    def test_same_model_is_warmed_once(self, clean_use_env):
        # Hoy: una sola llamada de calentamiento, como antes del cambio.
        assert claude_config.get_openrouter_warmup_models() == [TODAY_MODEL]

    def test_two_different_models_are_both_warmed_in_order(self, clean_use_env):
        clean_use_env.setenv("KB_REFORMULATION_LLM_MODEL", "openai/gpt-4.1-mini")
        assert claude_config.get_openrouter_warmup_models() == ["openai/gpt-4.1-mini", TODAY_MODEL]

    def test_visual_search_model_is_not_in_startup_warmup(self, clean_use_env):
        # La busqueda visual tiene su propio calentamiento (warmup_vs_gpt4o_singleton).
        clean_use_env.setenv("VISUAL_SEARCH_MESSAGE_LLM_MODEL", "solo/busqueda-visual")
        assert "solo/busqueda-visual" not in claude_config.get_openrouter_warmup_models()


# ============================================================================
# 2. Metrica de caminos
# ============================================================================

class TestRecordLlmRoute:

    def test_all_valid_combinations_exist_from_start(self):
        # Pre-inicializadas a 0 al importar prometheus_metrics (necesario para la
        # exportacion a Cloud Monitoring, mismo patron que el resto de metricas).
        import src.api.core.prometheus_metrics as metrics_module
        assert metrics_module.llm_route_total is not None
        for use, routes in LLM_ROUTES_BY_USE.items():
            for route in routes:
                assert REGISTRY.get_sample_value(
                    "recommender_llm_route_total", {"use": use, "route": route}) is not None, (use, route)

    def test_valid_combination_increments_by_one(self):
        before = route_count(USE_PRODUCT_REDACTOR, "main_model")
        llm_routes.record_llm_route(USE_PRODUCT_REDACTOR, "main_model")
        assert route_count(USE_PRODUCT_REDACTOR, "main_model") == before + 1

    @pytest.mark.parametrize("use,route", [
        (USE_VISUAL_SEARCH_MESSAGE, "claude"),   # la busqueda visual no tiene escalon Claude
        (USE_PRODUCT_REDACTOR, "template"),      # el redactor no tiene plantilla
        ("uso_inventado", "main_model"),
        (USE_KB_REFORMULATION, "camino_inventado"),
    ])
    def test_unknown_combination_is_ignored_and_never_raises(self, use, route):
        llm_routes.record_llm_route(use, route)  # no debe lanzar
        assert REGISTRY.get_sample_value(
            "recommender_llm_route_total", {"use": use, "route": route}) is None

    def test_metric_failure_never_raises(self):
        # Si el contador falla, la respuesta al cliente no se entera.
        broken = MagicMock()
        broken.labels.side_effect = RuntimeError("prometheus roto")
        with patch("src.api.core.prometheus_metrics.llm_route_total", broken):
            llm_routes.record_llm_route(USE_KB_REFORMULATION, "main_model")


# ============================================================================
# 3. Reformulacion KB (kb_contextualizer.generate_contextual_answer)
# ============================================================================

@pytest.fixture
def kb_module(monkeypatch, clean_use_env):
    """kb_contextualizer con el camino de produccion de hoy y sin red."""
    import src.api.core.kb_contextualizer as kbc
    monkeypatch.setenv("LFM_KB_ENABLED", "false")
    monkeypatch.setenv("GPT4O_MINI_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("FORCE_GPT4O_MINI_FALLBACK", "false")
    monkeypatch.setattr(kbc, "_kb_gpt4o_mini_singleton", None)   # singleton nuevo en cada prueba
    RecordingLLMClient.created = []
    return kbc


def fake_anthropic(text="respuesta de Claude", error=None):
    client = MagicMock()
    if error is not None:
        client.messages.create = AsyncMock(side_effect=error)
    else:
        client.messages.create = AsyncMock(
            return_value=SimpleNamespace(content=[SimpleNamespace(text=text)]))
    return client


async def ask_kb(kbc, anthropic_client, **kwargs):
    return await kbc.generate_contextual_answer(
        query="¿Puedo devolver un producto?",
        kb_document="Devoluciones: contacta con atencion al cliente en 30 dias.",
        sub_intent="policy_return",
        language="es",
        anthropic_client=anthropic_client,
        **kwargs,
    )


class TestKbReformulationRoutes:

    async def test_main_model_answers_with_todays_request(self, kb_module, monkeypatch):
        monkeypatch.setattr(kb_module, "UnifiedLLMClient", RecordingLLMClient)
        before = route_count(USE_KB_REFORMULATION, "main_model")
        answer = await ask_kb(kb_module, fake_anthropic())
        assert answer == "texto del modelo"
        # Misma peticion que antes del cambio
        assert RecordingLLMClient.created == [
            {"provider": "openrouter", "model": TODAY_MODEL, "max_tokens": 300, "temperature": 0.3}]
        assert route_count(USE_KB_REFORMULATION, "main_model") == before + 1

    async def test_model_comes_from_its_own_variable(self, kb_module, monkeypatch):
        monkeypatch.setenv("KB_REFORMULATION_LLM_MODEL", "openai/gpt-4.1-mini")
        monkeypatch.setattr(kb_module, "UnifiedLLMClient", RecordingLLMClient)
        await ask_kb(kb_module, fake_anthropic())
        assert RecordingLLMClient.created[0]["model"] == "openai/gpt-4.1-mini"

    async def test_main_model_fails_then_claude_answers(self, kb_module, monkeypatch):
        failing = lambda **kw: RecordingLLMClient(**kw, error=RuntimeError("OpenRouter caido"))  # noqa: E731
        monkeypatch.setattr(kb_module, "UnifiedLLMClient", failing)
        before = route_count(USE_KB_REFORMULATION, "claude")
        answer = await ask_kb(kb_module, fake_anthropic(text="  respuesta de Claude  "))
        assert answer == "respuesta de Claude"
        assert route_count(USE_KB_REFORMULATION, "claude") == before + 1

    async def test_everything_fails_document_as_is(self, kb_module, monkeypatch):
        failing = lambda **kw: RecordingLLMClient(**kw, error=RuntimeError("OpenRouter caido"))  # noqa: E731
        monkeypatch.setattr(kb_module, "UnifiedLLMClient", failing)
        before = route_count(USE_KB_REFORMULATION, "document_as_is")
        answer = await ask_kb(kb_module, fake_anthropic(error=RuntimeError("modelo retirado")))
        assert answer is None   # el llamador sirve el documento tal cual
        assert route_count(USE_KB_REFORMULATION, "document_as_is") == before + 1

    async def test_out_of_stock_template_is_counted_as_template(self, kb_module, monkeypatch):
        monkeypatch.setattr(kb_module, "UnifiedLLMClient", RecordingLLMClient)
        # Forzar el bloque de disponibilidad para que exista availability_context
        monkeypatch.setattr(kb_module, "_build_availability_context_block", lambda **kw: "bloque")
        before = route_count(USE_KB_REFORMULATION, "template")
        answer = await kb_module.generate_contextual_answer(
            query="¿Hay stock?", kb_document="doc", sub_intent="product_availability",
            language="es", anthropic_client=fake_anthropic(),
            product_context={"title": "Vestido Azul", "variant_inventory": {"S": 0, "M": 0}},
        )
        assert "agotado" in answer
        assert RecordingLLMClient.created == []   # sin LLM
        assert route_count(USE_KB_REFORMULATION, "template") == before + 1

    async def test_no_anthropic_client_counts_document_as_is(self, kb_module, monkeypatch):
        # Comportamiento previo conservado: sin cliente Anthropic se sale antes de probar
        # el modelo principal (registrado en el DCT). La metrica lo hace visible.
        monkeypatch.setattr(kb_module, "UnifiedLLMClient", RecordingLLMClient)
        fake_factory = SimpleNamespace(get_mcp_recommender=AsyncMock(return_value=None))
        with patch("src.api.factories.service_factory.ServiceFactory", fake_factory):
            before = route_count(USE_KB_REFORMULATION, "document_as_is")
            assert await ask_kb(kb_module, None) is None
        assert RecordingLLMClient.created == []
        assert route_count(USE_KB_REFORMULATION, "document_as_is") == before + 1


# ============================================================================
# 4. Redactor de producto (MCPPersonalizationEngine)
# ============================================================================

@pytest.fixture
def redactor_engine(monkeypatch, clean_use_env):
    """Motor real con el camino de produccion de hoy (LFM apagado, modelo principal activo)."""
    from src.api.mcp.engines import mcp_personalization_engine as engine_module
    monkeypatch.setenv("LFM_MCP_ENABLED", "false")
    monkeypatch.setenv("GPT4O_MINI_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("FORCE_GPT4O_MINI_FALLBACK", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "clave-falsa-de-prueba")
    RecordingLLMClient.created = []
    monkeypatch.setattr(engine_module, "UnifiedLLMClient", RecordingLLMClient)

    claude_cfg = MagicMock()
    claude_cfg.get_model_config.return_value = SimpleNamespace(
        model_name="claude-modelo-de-prueba", max_tokens=200, temperature=0.7)
    with patch.object(engine_module, "get_claude_config_service", return_value=claude_cfg):
        engine = engine_module.MCPPersonalizationEngine(
            redis_service=AsyncMock(), anthropic_client=fake_anthropic(text="texto de Claude"),
            conversation_manager=AsyncMock(), state_manager=AsyncMock(),
        )
    # Aislar la generacion de texto: sin Shopify ni constructores de prompt reales
    engine._enrich_recommendations_lazy = AsyncMock()
    engine._build_personalized_system_prompt = lambda *a, **k: "sistema"
    engine._build_advanced_personalization_prompt = lambda *a, **k: "usuario"
    return engine


def redactor_context():
    mcp_context = SimpleNamespace(current_market_id="CL", current_product_context=None,
                                  current_query="vestido rojo", turns=[])
    return SimpleNamespace(mcp_context=mcp_context)


async def redact(engine):
    return await engine._generate_claude_personalized_response(
        redactor_context(), {"recommendations": []}, detected_language="es")


class TestProductRedactorRoutes:

    async def test_client_is_created_with_todays_request(self, redactor_engine):
        assert RecordingLLMClient.created == [
            {"provider": "openrouter", "model": TODAY_MODEL, "max_tokens": 300, "temperature": 0.7}]

    async def test_main_model_answers(self, redactor_engine):
        before = route_count(USE_PRODUCT_REDACTOR, "main_model")
        assert await redact(redactor_engine) == "texto del modelo"
        assert route_count(USE_PRODUCT_REDACTOR, "main_model") == before + 1

    async def test_main_model_fails_then_claude_answers(self, redactor_engine):
        redactor_engine._gpt4o_mini_client = RecordingLLMClient(
            "openrouter", TODAY_MODEL, 300, 0.7, error=RuntimeError("OpenRouter caido"))
        before = route_count(USE_PRODUCT_REDACTOR, "claude")
        assert await redact(redactor_engine) == "texto de Claude"
        assert route_count(USE_PRODUCT_REDACTOR, "claude") == before + 1

    async def test_everything_fails_generic_message(self, redactor_engine):
        redactor_engine._gpt4o_mini_client = RecordingLLMClient(
            "openrouter", TODAY_MODEL, 300, 0.7, error=RuntimeError("OpenRouter caido"))
        redactor_engine.claude = fake_anthropic(error=RuntimeError("modelo retirado"))
        before = route_count(USE_PRODUCT_REDACTOR, "generic_message")
        answer = await redact(redactor_engine)
        assert answer.startswith("Te ayudo a encontrar")
        assert route_count(USE_PRODUCT_REDACTOR, "generic_message") == before + 1

    async def test_generic_message_is_not_counted_as_claude(self, redactor_engine):
        redactor_engine._gpt4o_mini_client = RecordingLLMClient(
            "openrouter", TODAY_MODEL, 300, 0.7, error=RuntimeError("OpenRouter caido"))
        redactor_engine.claude = fake_anthropic(error=RuntimeError("modelo retirado"))
        claude_before = route_count(USE_PRODUCT_REDACTOR, "claude")
        await redact(redactor_engine)
        assert route_count(USE_PRODUCT_REDACTOR, "claude") == claude_before


# ============================================================================
# 5. Mensaje de busqueda visual (visual_search_router)
# ============================================================================

@pytest.fixture
def vs_module(monkeypatch, clean_use_env):
    import src.api.routers.visual_search_router as vsr
    monkeypatch.setenv("GPT4O_MINI_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "clave-falsa-de-prueba")
    monkeypatch.setattr(vsr, "_vs_gpt4o_client", None)   # singleton nuevo en cada prueba
    RecordingLLMClient.created = []
    # Sin motor MCP -> sin LFM (hoy LFM_MCP_ENABLED=false en produccion)
    fake_factory = SimpleNamespace(get_mcp_recommender=AsyncMock(return_value=None))
    monkeypatch.setattr("src.api.factories.service_factory.ServiceFactory", fake_factory)
    return vsr


PRODUCTS = [{"title": "Vestido Azul", "currency": "CLP", "price": 19990}]


class TestVisualSearchMessageRoutes:

    async def test_main_model_answers_with_todays_request(self, vs_module, monkeypatch):
        monkeypatch.setattr("src.api.core.llm_client.UnifiedLLMClient", RecordingLLMClient)
        before = route_count(USE_VISUAL_SEARCH_MESSAGE, "main_model")
        assert await vs_module._generate_visual_search_message(PRODUCTS, "es") == "texto del modelo"
        assert RecordingLLMClient.created == [
            {"provider": "openrouter", "model": TODAY_MODEL, "max_tokens": 120, "temperature": 0.7}]
        assert route_count(USE_VISUAL_SEARCH_MESSAGE, "main_model") == before + 1

    async def test_main_model_fails_no_message(self, vs_module, monkeypatch):
        failing = lambda **kw: RecordingLLMClient(**kw, error=RuntimeError("OpenRouter caido"))  # noqa: E731
        monkeypatch.setattr("src.api.core.llm_client.UnifiedLLMClient", failing)
        before = route_count(USE_VISUAL_SEARCH_MESSAGE, "no_message")
        assert await vs_module._generate_visual_search_message(PRODUCTS, "es") is None
        assert route_count(USE_VISUAL_SEARCH_MESSAGE, "no_message") == before + 1

    async def test_no_api_key_no_message(self, vs_module, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY")
        before = route_count(USE_VISUAL_SEARCH_MESSAGE, "no_message")
        assert await vs_module._generate_visual_search_message(PRODUCTS, "es") is None
        assert route_count(USE_VISUAL_SEARCH_MESSAGE, "no_message") == before + 1

    async def test_no_products_is_not_counted(self, vs_module):
        # Sin productos no se pide ningun texto: no es un intento del uso.
        totals_before = sum(route_count(USE_VISUAL_SEARCH_MESSAGE, r)
                            for r in LLM_ROUTES_BY_USE[USE_VISUAL_SEARCH_MESSAGE])
        assert await vs_module._generate_visual_search_message([], "es") is None
        totals_after = sum(route_count(USE_VISUAL_SEARCH_MESSAGE, r)
                           for r in LLM_ROUTES_BY_USE[USE_VISUAL_SEARCH_MESSAGE])
        assert totals_after == totals_before
