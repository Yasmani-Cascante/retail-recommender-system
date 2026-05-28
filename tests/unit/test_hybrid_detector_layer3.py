"""
Tests de integracion para la capa 3 (MiniLM) del HybridIntentDetector
======================================================================

Todos los tests son rapidos (usan mocks del modelo, sin descarga).
Verifican:
  - El trigger correcto de la capa 3
  - La degradacion graceful en todos los escenarios de fallo
  - El tracking de stats
  - La compatibilidad con el GUARD y la logica existente de capas 1+2

Ejecutar:
    pytest tests/unit/test_hybrid_detector_layer3.py -v

Dependencias:
    pip install pytest pytest-asyncio
"""

import os
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from dataclasses import dataclass
from typing import Optional

os.environ.setdefault("MINILM_BACKEND", "torch")
os.environ.setdefault("ML_INTENT_ENABLED", "true")
os.environ.setdefault("MINILM_INTENT_ENABLED", "true")
os.environ.setdefault("ML_CONFIDENCE_THRESHOLD", "0.8")
os.environ.setdefault("MINILM_TRIGGER_THRESHOLD", "0.60")
os.environ.setdefault("MINILM_MIN_CONFIDENCE", "0.50")

from src.api.ml.hybrid_detector import HybridIntentDetector, HybridIntentResult
from src.api.ml.miniml_classifier import MiniLMPrediction
from src.api.ml.intent_classifier import MLPrediction
from src.api.core.intent_detection import IntentDetectionResult
from src.api.core.intent_types import IntentType, InformationalSubIntent, TransactionalSubIntent


# ════════════════════════════════════════════════════════════════════
# HELPERS Y FACTORIES
# ════════════════════════════════════════════════════════════════════

def make_rule_result(
    primary: str = "transactional",
    sub: str = "product_search",
    confidence: float = 0.50,
    patterns: list = None,
) -> IntentDetectionResult:
    """Factory para IntentDetectionResult (resultado del rule-based)."""
    return IntentDetectionResult(
        primary_intent=IntentType(primary),
        sub_intent=sub,
        confidence=confidence,
        reasoning="test rule result",
        matched_patterns=patterns if patterns is not None else [],
    )


def make_ml_prediction(
    intent: str = "INFORMATIONAL",
    confidence: float = 0.55,
) -> MLPrediction:
    """Factory para MLPrediction (resultado de sklearn)."""
    return MLPrediction(
        intent=intent,
        confidence=confidence,
        probabilities={intent: confidence, "OTHER": 1 - confidence},
        inference_time_ms=0.16,
    )


def make_miniml_prediction(
    primary: str = "informational",
    sub: str = "policy_return",
    confidence: float = 0.72,
) -> MiniLMPrediction:
    """Factory para MiniLMPrediction (resultado de capa 3 MiniLM)."""
    full_label = f"{primary}/{sub}" if sub else primary
    return MiniLMPrediction(
        primary_intent=primary,
        sub_intent=sub,
        full_label=full_label,
        confidence=confidence,
        inference_time_ms=9.5,
    )


# ════════════════════════════════════════════════════════════════════
# FIXTURE PRINCIPAL: detector con mocks de capas 2 y 3
# ════════════════════════════════════════════════════════════════════

@pytest.fixture
def detector_with_mocks():
    """
    HybridIntentDetector con capas 2 y 3 mockeadas.
    Retorna el detector y los mocks para configurar el comportamiento
    en cada test individualmente.
    """
    detector = HybridIntentDetector()

    # Mock capa 1 (rule-based)
    mock_rule_based = MagicMock()
    detector.rule_based = mock_rule_based

    # Mock capa 2 (sklearn ML)
    mock_ml = MagicMock()
    mock_ml.is_loaded.return_value = True
    detector.ml_classifier = mock_ml
    detector.ml_enabled = True

    # Mock capa 3 (MiniLM)
    mock_miniml = MagicMock()
    mock_miniml.is_loaded.return_value = True
    detector.miniml_classifier = mock_miniml
    detector.miniml_enabled = True

    return detector, mock_rule_based, mock_ml, mock_miniml


# ════════════════════════════════════════════════════════════════════
# TESTS: TRIGGER DE CAPA 3
# ════════════════════════════════════════════════════════════════════

class TestLayer3Trigger:
    """Tests sobre cuando se activa (o no) la capa 3."""

    @pytest.mark.asyncio
    async def test_layer3_not_triggered_when_flag_off(self, detector_with_mocks):
        """Capa 3 NO se activa si MINILM_INTENT_ENABLED=false."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks
        detector.miniml_enabled = False

        # rule-based da confianza baja -> va a ML
        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        # ML da confianza baja (< 0.60, deberia activar capa 3)
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)

        result = await detector.detect("me pueden mandar hasta acá?")

        # MiniLM NO debe haber sido invocado
        mock_miniml.predict.assert_not_called()
        assert result.method_used != "miniml_semantic"

    @pytest.mark.asyncio
    async def test_layer3_not_triggered_when_ml_confident(self, detector_with_mocks):
        """Capa 3 NO se activa cuando ML tiene confianza >= MINILM_TRIGGER_THRESHOLD (0.60)."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        # ML confiado (>= 0.60) -> capa 3 no debe activarse
        mock_ml.predict.return_value = make_ml_prediction(intent="INFORMATIONAL", confidence=0.75)

        result = await detector.detect("¿cuál es la política de devolución?")

        mock_miniml.predict.assert_not_called()

    @pytest.mark.asyncio
    async def test_layer3_triggered_when_ml_low_confidence(self, detector_with_mocks):
        """Capa 3 SI se activa cuando la final_confidence < MINILM_TRIGGER_THRESHOLD."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        # rule-based: confianza baja, sin patrones (no activa fast-path ni GUARD)
        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        # ML: confianza baja -> final_confidence <= 0.55 < 0.60
        mock_ml.predict.return_value = make_ml_prediction(
            intent="INFORMATIONAL", confidence=0.45
        )
        # MiniLM: responde con buena confianza
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.72)

        result = await detector.detect("cuantos dias tengo para devolver?")

        mock_miniml.predict.assert_called_once()

    @pytest.mark.asyncio
    async def test_layer3_not_triggered_on_fast_path(self, detector_with_mocks):
        """Capa 3 NO se activa en el fast-path (rule_conf >= 0.8)."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        # rule-based muy confiado -> fast path, no invoca ML ni MiniLM
        mock_rule.detect.return_value = make_rule_result(
            primary="informational", sub="policy_return", confidence=0.90
        )

        result = await detector.detect("¿cuál es la política de devoluciones?")

        mock_ml.predict.assert_not_called()
        mock_miniml.predict.assert_not_called()
        assert result.method_used == "rule_based"

    @pytest.mark.asyncio
    async def test_layer3_not_triggered_when_guard_fires(self, detector_with_mocks):
        """
        Capa 3 NO debe activarse cuando el GUARD protege TRANSACTIONAL.
        Cuando el GUARD protege, retorna directamente sin llegar al bloque MiniLM.
        """
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        # rule-based: TRANSACTIONAL con patron real (activa GUARD)
        mock_rule.detect.return_value = make_rule_result(
            primary="transactional",
            sub="product_search",
            confidence=0.50,
            patterns=[r"\b(similar(?:es)?)\b"],  # patron real no vacio
        )
        # ML quiere cambiar a INFORMATIONAL -> GUARD lo bloquea
        mock_ml.predict.return_value = make_ml_prediction(
            intent="INFORMATIONAL", confidence=0.45
        )

        result = await detector.detect("Recoméndame similares")

        # GUARD retorna antes de llegar a capa 3
        mock_miniml.predict.assert_not_called()
        assert result.method_used == "rule_based"


# ════════════════════════════════════════════════════════════════════
# TESTS: RESULTADO DE CAPA 3
# ════════════════════════════════════════════════════════════════════

class TestLayer3Result:
    """Tests sobre el resultado cuando capa 3 se activa y gana."""

    @pytest.mark.asyncio
    async def test_method_used_is_miniml_semantic(self, detector_with_mocks):
        """Cuando MiniLM gana, method_used debe ser 'miniml_semantic'."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = make_miniml_prediction(
            primary="informational", sub="policy_return", confidence=0.72
        )

        result = await detector.detect("cuantos dias tengo para devolver?")

        assert result.method_used == "miniml_semantic"

    @pytest.mark.asyncio
    async def test_miniml_result_has_correct_sub_intent(self, detector_with_mocks):
        """MiniLM debe proveer el sub_intent correcto en el resultado."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.42)
        mock_miniml.predict.return_value = make_miniml_prediction(
            primary="informational", sub="policy_shipping", confidence=0.68
        )

        result = await detector.detect("me pueden mandar hasta Santiago?")

        assert result.primary_intent == "informational"
        assert result.sub_intent == "policy_shipping"

    @pytest.mark.asyncio
    async def test_miniml_confidence_used_in_result(self, detector_with_mocks):
        """La confidence del resultado debe ser la de MiniLM cuando gana."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        miniml_pred = make_miniml_prediction(confidence=0.77)
        mock_miniml.predict.return_value = miniml_pred

        result = await detector.detect("test query")

        assert result.confidence == pytest.approx(0.77, abs=0.01)

    @pytest.mark.asyncio
    async def test_miniml_reasoning_contains_key_info(self, detector_with_mocks):
        """El reasoning debe incluir info de las tres capas para debugging."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.72)

        result = await detector.detect("test query")

        assert "MiniLM" in result.reasoning or "miniml" in result.reasoning.lower()
        assert "layer-3" in result.reasoning or "capa 3" in result.reasoning.lower() or "semantic" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_greeting_sub_intent_is_none_or_unknown(self, detector_with_mocks):
        """
        Cuando MiniLM clasifica como greeting (sin sub-intent),
        sub_intent debe ser None o 'unknown', no lanzar AttributeError.
        """
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = MiniLMPrediction(
            primary_intent="greeting",
            sub_intent=None,  # sin sub-intent
            full_label="greeting",
            confidence=0.88,
            inference_time_ms=5.0,
        )

        result = await detector.detect("hola")

        assert result.primary_intent == "greeting"
        # sub_intent puede ser None o "unknown" pero no debe lanzar error
        assert result.sub_intent in (None, "unknown")


# ════════════════════════════════════════════════════════════════════
# TESTS: DEGRADACION GRACEFUL
# ════════════════════════════════════════════════════════════════════

class TestLayer3GracefulDegradation:
    """Tests de degradacion cuando capa 3 no puede usarse."""

    @pytest.mark.asyncio
    async def test_falls_back_to_ml_when_miniml_confidence_too_low(
        self, detector_with_mocks
    ):
        """
        Cuando MiniLM da confianza < MINILM_MIN_CONFIDENCE (0.50),
        se usa el resultado de ML (no MiniLM).
        """
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(
            intent="INFORMATIONAL", confidence=0.45
        )
        # MiniLM con confianza insuficiente
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.35)

        result = await detector.detect("test ambiguous query")

        # MiniLM fue invocado pero resultado no se uso
        mock_miniml.predict.assert_called_once()
        # El resultado final NO es de MiniLM
        assert result.method_used == "ml_fallback"

    @pytest.mark.asyncio
    async def test_falls_back_to_ml_when_miniml_returns_none(
        self, detector_with_mocks
    ):
        """Cuando miniml_classifier.predict() retorna None, se usa ML."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = None  # MiniLM no puede predecir

        result = await detector.detect("test query")

        assert result.method_used != "miniml_semantic"

    @pytest.mark.asyncio
    async def test_falls_back_to_ml_when_miniml_raises_exception(
        self, detector_with_mocks
    ):
        """Cuando predict() lanza una exception, se usa ML (no se propaga el error)."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.side_effect = RuntimeError("Unexpected model error")

        # NO debe lanzar exception
        result = await detector.detect("test query")

        assert result is not None
        assert result.method_used != "miniml_semantic"

    @pytest.mark.asyncio
    async def test_falls_back_when_miniml_not_loaded(self, detector_with_mocks):
        """Cuando el modelo no pudo cargarse, se usa el resultado de ML."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        # MiniLM reporta que no esta cargado
        mock_miniml.is_loaded.return_value = False

        # Mockear _ensure_miniml_loaded para que retorne False
        original_method = detector._ensure_miniml_loaded
        detector._ensure_miniml_loaded = lambda: False

        result = await detector.detect("test query")

        # Ni siquiera se llama a predict() de MiniLM
        mock_miniml.predict.assert_not_called()
        assert result.method_used != "miniml_semantic"

        # Restaurar
        detector._ensure_miniml_loaded = original_method


# ════════════════════════════════════════════════════════════════════
# TESTS: TRACKING DE STATS
# ════════════════════════════════════════════════════════════════════

class TestLayer3Stats:
    """Tests para el tracking de estadisticas de la capa 3."""

    @pytest.mark.asyncio
    async def test_miniml_used_stat_increments_on_success(self, detector_with_mocks):
        """miniml_used debe incrementarse cuando MiniLM gana."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.72)

        initial_count = detector.stats["miniml_used"]
        await detector.detect("test query")
        assert detector.stats["miniml_used"] == initial_count + 1

    @pytest.mark.asyncio
    async def test_miniml_skipped_stat_increments_on_low_confidence(
        self, detector_with_mocks
    ):
        """miniml_skipped debe incrementarse cuando la confianza es insuficiente."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.30)  # baja

        initial_count = detector.stats["miniml_skipped"]
        await detector.detect("test query")
        assert detector.stats["miniml_skipped"] == initial_count + 1

    @pytest.mark.asyncio
    async def test_miniml_failed_stat_increments_on_exception(self, detector_with_mocks):
        """miniml_failed debe incrementarse cuando predict() lanza exception."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.side_effect = RuntimeError("GPU error")

        initial_count = detector.stats["miniml_failed"]
        await detector.detect("test query")
        assert detector.stats["miniml_failed"] == initial_count + 1

    @pytest.mark.asyncio
    async def test_get_stats_includes_miniml_percentage(self, detector_with_mocks):
        """get_stats() debe incluir miniml_percentage en el resultado."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.72)

        await detector.detect("test query 1")
        await detector.detect("test query 2")

        stats = detector.get_stats()
        assert "miniml_percentage" in stats
        assert "miniml_used" in stats
        assert "miniml_skipped" in stats
        assert "miniml_failed" in stats

    def test_reset_stats_clears_miniml_counters(self, detector_with_mocks):
        """reset_stats() debe limpiar los contadores de capa 3."""
        detector, _, _, _ = detector_with_mocks

        # Simular contadores no-cero
        detector.stats["miniml_used"] = 5
        detector.stats["miniml_skipped"] = 2
        detector.stats["miniml_failed"] = 1

        detector.reset_stats()

        assert detector.stats["miniml_used"] == 0
        assert detector.stats["miniml_skipped"] == 0
        assert detector.stats["miniml_failed"] == 0


# ════════════════════════════════════════════════════════════════════
# TESTS: COMPATIBILIDAD CON CAPAS EXISTENTES
# ════════════════════════════════════════════════════════════════════

class TestLayer3Compatibility:
    """Tests de compatibilidad de capa 3 con la logica existente de capas 1+2."""

    @pytest.mark.asyncio
    async def test_to_intent_detection_result_works_with_miniml_output(
        self, detector_with_mocks
    ):
        """
        to_intent_detection_result() debe funcionar sin error cuando
        method_used='miniml_semantic' (compatibilidad con el handler).
        """
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.72)

        hybrid_result = await detector.detect("test query")
        # Este metodo es el que usa el handler para convertir al formato estandar
        standard_result = hybrid_result.to_intent_detection_result()

        assert standard_result is not None
        assert hasattr(standard_result, "primary_intent")
        assert hasattr(standard_result, "sub_intent")
        assert hasattr(standard_result, "confidence")

    @pytest.mark.asyncio
    async def test_miniml_result_preserves_rule_matched_patterns(
        self, detector_with_mocks
    ):
        """
        El resultado de MiniLM debe preservar matched_patterns del rule-based
        (para debugging y para que el handler pueda loguear los patrones).
        """
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        original_patterns = [r"\b(devolver)\b"]
        mock_rule.detect.return_value = make_rule_result(
            confidence=0.50, patterns=original_patterns
        )
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.72)

        result = await detector.detect("test query")

        if result.method_used == "miniml_semantic":
            # MiniLM ganó, pero matched_patterns del rule-based se preservan
            assert result.matched_patterns == original_patterns

    @pytest.mark.asyncio
    async def test_ml_confidence_stored_in_result(self, detector_with_mocks):
        """
        ml_confidence debe almacenarse en el resultado incluso cuando MiniLM gana,
        para que los logs muestren la confianza de las tres capas.
        """
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.72)

        result = await detector.detect("test query")

        if result.method_used == "miniml_semantic":
            assert result.ml_confidence is not None
            assert result.ml_confidence == pytest.approx(0.45, abs=0.01)

    @pytest.mark.asyncio
    async def test_rule_based_confidence_stored_in_result(self, detector_with_mocks):
        """rule_based_confidence debe estar en el resultado de MiniLM."""
        detector, mock_rule, mock_ml, mock_miniml = detector_with_mocks

        mock_rule.detect.return_value = make_rule_result(confidence=0.50, patterns=[])
        mock_ml.predict.return_value = make_ml_prediction(confidence=0.45)
        mock_miniml.predict.return_value = make_miniml_prediction(confidence=0.72)

        result = await detector.detect("test query")

        if result.method_used == "miniml_semantic":
            assert result.rule_based_confidence == pytest.approx(0.50, abs=0.01)
