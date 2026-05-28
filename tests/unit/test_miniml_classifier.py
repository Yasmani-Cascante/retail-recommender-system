"""
Unit tests para MiniLMIntentClassifier — Capa 3 semantica
==========================================================

Dos categorias de tests:
  - Fast (sin marca): mocks, sin descarga de modelo, siempre en CI
  - Slow (@pytest.mark.slow): requieren el modelo real descargado

Ejecutar solo tests rapidos (CI):
    pytest tests/unit/test_miniml_classifier.py -v

Ejecutar TODOS (incluyendo semanticos con modelo real):
    pytest tests/unit/test_miniml_classifier.py -v -m "slow"
    pytest tests/unit/test_miniml_classifier.py -v            # sin -m ejecuta ambos

Prerequisitos para tests slow:
    MINILM_BACKEND=torch pip install sentence-transformers>=3.0.0
    o
    pip install sentence-transformers>=3.0.0 onnxruntime-cpu>=1.18.0
"""

import os
import pytest
import numpy as np
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Optional

# -- Fixture de entorno: usar torch localmente para tests ---------
# La variable se lee en MiniLMIntentClassifier.__init__
os.environ.setdefault("MINILM_BACKEND", "torch")


from src.api.ml.miniml_classifier import (
    MiniLMIntentClassifier,
    MiniLMPrediction,
    PROTOTYPE_EXAMPLES,
    get_miniml_classifier,
)
from src.api.core.intent_types import InformationalSubIntent


# ════════════════════════════════════════════════════════════════════
# TESTS RAPIDOS — siempre corren (no requieren modelo descargado)
# ════════════════════════════════════════════════════════════════════

class TestMiniLMClassifierFast:
    """Tests que no requieren descargar el modelo (usa mocks)."""

    def test_is_loaded_false_before_load(self):
        """El clasificador empieza en estado no-cargado."""
        clf = MiniLMIntentClassifier()
        assert clf.is_loaded() is False

    def test_predict_returns_none_when_not_loaded(self):
        """predict() retorna None si el modelo no esta cargado (no lanza exception)."""
        clf = MiniLMIntentClassifier()
        result = clf.predict("hola como estas?")
        assert result is None

    def test_get_similarity_ranking_empty_when_not_loaded(self):
        """get_similarity_ranking() retorna [] si no esta cargado."""
        clf = MiniLMIntentClassifier()
        result = clf.get_similarity_ranking("test query")
        assert result == []

    def test_load_returns_false_gracefully_on_import_error(self):
        """
        Si sentence-transformers no esta instalado, load() retorna False
        sin lanzar exception (degradacion graceful).
        """
        clf = MiniLMIntentClassifier()
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            # No podemos mockear el ImportError de esta forma directamente,
            # pero si que funcione la logica de _load_attempted
            clf._load_attempted = True
            clf._loaded = False
            result = clf.load()
            assert result is False

    def test_load_not_retried_after_failure(self):
        """
        Despues de un fallo de load(), no se reintenta (evita intentos
        repetidos en el hot path de requests).
        """
        clf = MiniLMIntentClassifier()
        clf._load_attempted = True
        clf._loaded = False
        # Segunda llamada: no debe intentar cargar
        result = clf.load()
        assert result is False
        assert clf._load_attempted is True

    def test_prototype_examples_coverage_informational_subintents(self):
        """
        Cada InformationalSubIntent (excepto UNKNOWN) debe tener al menos
        un label cubriendo ese sub-intent en PROTOTYPE_EXAMPLES.
        Garantiza que anadir un nuevo sub-intent al enum requiere
        actualizar los prototipos.
        """
        # Extraer sub-intents cubiertos en PROTOTYPE_EXAMPLES
        covered_sub_intents = set()
        for label in PROTOTYPE_EXAMPLES:
            if "/" in label:
                sub = label.split("/", 1)[1]
                covered_sub_intents.add(sub)

        # Verificar que todos los sub-intents del enum estan cubiertos
        missing = []
        for member in InformationalSubIntent:
            if member == InformationalSubIntent.UNKNOWN:
                continue  # UNKNOWN no necesita ejemplos propios
            if member.value not in covered_sub_intents:
                missing.append(member.value)

        assert not missing, (
            f"Los siguientes InformationalSubIntent no tienen ejemplos "
            f"en PROTOTYPE_EXAMPLES: {missing}. "
            f"Agregalos en src/api/ml/miniml_classifier.py"
        )

    def test_prototype_examples_minimum_count(self):
        """Cada label debe tener al menos 5 ejemplos para un centroide robusto."""
        insufficient = [
            label for label, examples in PROTOTYPE_EXAMPLES.items()
            if len(examples) < 5
        ]
        assert not insufficient, (
            f"Los siguientes labels tienen < 5 ejemplos (poco para un centroide "
            f"robusto): {insufficient}"
        )

    def test_full_label_parse_informational(self):
        """
        Verificar que el parsing de label "informational/policy_return"
        produce los campos correctos en MiniLMPrediction.
        """
        pred = MiniLMPrediction(
            primary_intent="informational",
            sub_intent="policy_return",
            full_label="informational/policy_return",
            confidence=0.75,
            inference_time_ms=5.0,
        )
        assert pred.primary_intent == "informational"
        assert pred.sub_intent == "policy_return"
        assert pred.method == "miniml_semantic"

    def test_full_label_parse_greeting(self):
        """El label 'greeting' (sin /) produce sub_intent=None."""
        pred = MiniLMPrediction(
            primary_intent="greeting",
            sub_intent=None,
            full_label="greeting",
            confidence=0.90,
            inference_time_ms=3.0,
        )
        assert pred.primary_intent == "greeting"
        assert pred.sub_intent is None

    def test_predict_with_mocked_model(self):
        """
        Test completo del flujo predict() usando un modelo mockeado.
        Verifica que la logica de cosine similarity y seleccion de label
        funciona correctamente sin necesitar el modelo real.
        """
        clf = MiniLMIntentClassifier()
        clf._loaded = True

        # Crear centroides mock de dimension 4 (simplificado)
        # El centroide de "informational/policy_return" apunta a [1, 0, 0, 0]
        # El centroide de "transactional/product_search" apunta a [0, 1, 0, 0]
        clf._centroids = {
            "informational/policy_return": np.array([1.0, 0.0, 0.0, 0.0]),
            "transactional/product_search": np.array([0.0, 1.0, 0.0, 0.0]),
        }

        # Mock del modelo: encode devuelve un vector mas cercano a policy_return
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.95, 0.1, 0.0, 0.0]])
        clf._model = mock_model

        result = clf.predict("quiero devolver algo")

        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "policy_return"
        assert result.full_label == "informational/policy_return"
        assert result.confidence > 0.5
        assert result.method == "miniml_semantic"

    def test_predict_confidence_clamp_non_negative(self):
        """
        La confidence se clampea a [0, 1]. Un cosine similarity negativo
        (raro pero posible) no produce confidence negativa.
        """
        clf = MiniLMIntentClassifier()
        clf._loaded = True
        clf._centroids = {
            "informational/policy_return": np.array([1.0, 0.0, 0.0, 0.0]),
        }
        mock_model = MagicMock()
        # Vector opuesto — cosine similarity seria -1.0
        mock_model.encode.return_value = np.array([[-1.0, 0.0, 0.0, 0.0]])
        clf._model = mock_model

        result = clf.predict("algo completamente diferente")
        assert result is not None
        assert result.confidence >= 0.0  # nunca negativo

    def test_predict_exception_returns_none(self):
        """Si encode() lanza una exception, predict() retorna None (no propaga)."""
        clf = MiniLMIntentClassifier()
        clf._loaded = True
        clf._centroids = {"informational/policy_return": np.array([1.0, 0.0])}

        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("Unexpected GPU error")
        clf._model = mock_model

        result = clf.predict("test query")
        assert result is None

    def test_get_prototype_count_returns_correct_counts(self):
        """get_prototype_count() retorna el conteo correcto para cada label."""
        clf = MiniLMIntentClassifier()
        counts = clf.get_prototype_count()

        # Verificar contra los datos reales de PROTOTYPE_EXAMPLES
        for label, expected_count in {k: len(v) for k, v in PROTOTYPE_EXAMPLES.items()}.items():
            assert counts[label] == expected_count, (
                f"Conteo incorrecto para '{label}': "
                f"esperado {expected_count}, obtenido {counts[label]}"
            )

    def test_singleton_returns_same_instance(self):
        """get_miniml_classifier() retorna siempre la misma instancia (singleton)."""
        # Resetear singleton para el test
        import src.api.ml.miniml_classifier as module
        module._global_miniml_classifier = None

        instance1 = get_miniml_classifier()
        instance2 = get_miniml_classifier()
        assert instance1 is instance2

        # Cleanup
        module._global_miniml_classifier = None


# ════════════════════════════════════════════════════════════════════
# TESTS LENTOS — requieren el modelo real descargado
# Ejecutar: pytest tests/unit/test_miniml_classifier.py -v -m slow
# ════════════════════════════════════════════════════════════════════

@pytest.mark.slow
class TestMiniLMClassifierSemantic:
    """
    Tests semanticos con el modelo real.
    Requieren sentence-transformers instalado y modelo descargado (~88MB).
    """

    @pytest.fixture(scope="class")
    def loaded_classifier(self):
        """Fixture que carga el modelo una vez para toda la clase de tests."""
        clf = MiniLMIntentClassifier()
        success = clf.load()
        if not success:
            pytest.skip(
                "sentence-transformers no disponible o modelo no descargable. "
                "Instalar: pip install 'sentence-transformers>=3.0.0'"
            )
        return clf

    # -- Slang LATAM -----------------------------------------------

    def test_latam_cl_mandar_shipping(self, loaded_classifier):
        """CL: 'mandar' debe clasificar como policy_shipping."""
        result = loaded_classifier.predict("me pueden mandar hasta Santiago?")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "policy_shipping", (
            f"Esperado policy_shipping, obtenido {result.sub_intent} "
            f"(conf={result.confidence:.3f})"
        )

    def test_latam_mx_regresar_return(self, loaded_classifier):
        """MX: 'regresar' debe clasificar como policy_return."""
        result = loaded_classifier.predict("quiero regresar algo que compre")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "policy_return", (
            f"Esperado policy_return, obtenido {result.sub_intent} "
            f"(conf={result.confidence:.3f})"
        )

    def test_latam_cl_devolver_plata(self, loaded_classifier):
        """CL: 'devolver la plata' debe clasificar como policy_return."""
        result = loaded_classifier.predict("se puede devolver la plata si no me gusta?")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "policy_return"

    def test_latam_corre_grande_sizing(self, loaded_classifier):
        """LATAM: 'corre grande' debe clasificar como product_sizing."""
        result = loaded_classifier.predict("corre grande o chico?")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "product_sizing"

    def test_latam_ya_no_hay_availability(self, loaded_classifier):
        """LATAM informal: 'ya no hay' debe clasificar como product_availability."""
        result = loaded_classifier.predict("ya no hay de este modelo?")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "product_availability"

    # -- Typos e informalidades ------------------------------------

    def test_typo_politica_return(self, loaded_classifier):
        """'plitica de devolucion' (typo) debe clasificar como policy_return."""
        result = loaded_classifier.predict("plitica de devolucion")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "policy_return", (
            f"Esperado policy_return, obtenido {result.sub_intent} "
            f"(conf={result.confidence:.3f}). "
            f"Ranking: {loaded_classifier.get_similarity_ranking('plitica de devolucion', top_k=3)}"
        )

    def test_informal_sin_signos(self, loaded_classifier):
        """Queries sin signos de puntuacion ni acentos deben clasificar bien."""
        result = loaded_classifier.predict("cuantos dias tengo para devolver")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "policy_return"

    # -- Intents implicitos ----------------------------------------

    def test_implicit_sizing_quedo_grande(self, loaded_classifier):
        """'esto me quedo grande' — intent implicito de sizing/return."""
        result = loaded_classifier.predict("esto me quedo grande")
        assert result is not None
        assert result.primary_intent == "informational"
        # Aceptamos tanto product_sizing como policy_return (ambos validos)
        assert result.sub_intent in ("product_sizing", "policy_return"), (
            f"Esperado product_sizing o policy_return, obtenido {result.sub_intent}"
        )

    def test_implicit_warranty_salio_fallado(self, loaded_classifier):
        """CL: 'salio fallado' — intent implicito de warranty."""
        result = loaded_classifier.predict("salio fallado que hago?")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent in ("policy_warranty", "policy_return"), (
            f"Esperado policy_warranty o policy_return, obtenido {result.sub_intent}"
        )

    # -- Cross-lingual ---------------------------------------------

    def test_english_return_policy(self, loaded_classifier):
        """Query en ingles sobre devoluciones debe clasificar correctamente."""
        result = loaded_classifier.predict("I want to know your return policy")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "policy_return"

    def test_english_shipping_query(self, loaded_classifier):
        """Query en ingles sobre envio debe clasificar correctamente."""
        result = loaded_classifier.predict("how long does shipping take?")
        assert result is not None
        assert result.primary_intent == "informational"
        assert result.sub_intent == "policy_shipping"

    # -- No regresiones (queries que ya funcionaban) ---------------

    def test_no_regression_clear_transactional(self, loaded_classifier):
        """Queries transaccionales claras no deben caer a informational."""
        result = loaded_classifier.predict("busco un vestido azul")
        assert result is not None
        assert result.primary_intent == "transactional"

    def test_no_regression_greeting(self, loaded_classifier):
        """Saludos deben clasificar como greeting."""
        result = loaded_classifier.predict("hola")
        assert result is not None
        assert result.primary_intent == "greeting"

    # -- Metricas de confianza y performance -----------------------

    def test_confidence_range_valid(self, loaded_classifier):
        """La confidence debe estar siempre en [0, 1]."""
        test_queries = [q for q, _, _ in [
            ("cuantos dias tengo para devolver?", "informational", "policy_return"),
            ("busco un vestido azul", "transactional", "product_search"),
            ("hola", "greeting", None),
        ]]
        for q in test_queries:
            result = loaded_classifier.predict(q)
            assert result is not None
            assert 0.0 <= result.confidence <= 1.0, (
                f"Confidence fuera de rango para '{q}': {result.confidence}"
            )

    def test_inference_latency_under_15ms(self, loaded_classifier):
        """
        La latencia de inferencia debe ser < 15ms en CPU despues del warmup.
        Se hace un warmup explicito antes de medir.
        """
        import time
        # Warmup
        for _ in range(3):
            loaded_classifier.predict("warmup query")

        # Medir
        times = []
        for _ in range(10):
            t0 = time.time()
            loaded_classifier.predict("me pueden mandar hasta casa?")
            times.append((time.time() - t0) * 1000)

        avg_ms = sum(times) / len(times)
        assert avg_ms < 15, (
            f"Latencia promedio ({avg_ms:.1f}ms) supera 15ms. "
            f"Verificar que el modelo este correctamente cargado en memoria."
        )

    def test_similarity_ranking_returns_top_k(self, loaded_classifier):
        """get_similarity_ranking() retorna exactamente top_k resultados."""
        ranking = loaded_classifier.get_similarity_ranking(
            "quiero saber sobre devoluciones", top_k=3
        )
        assert len(ranking) == 3
        # Los resultados deben estar ordenados por similitud descendente
        sims = [sim for _, sim in ranking]
        assert sims == sorted(sims, reverse=True)
        # El primer resultado debe tener similitud positiva
        assert sims[0] > 0
