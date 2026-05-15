"""
Hybrid Intent Detector
=======================

Combina rule-based intent detection + ML fallback + MiniLM semantico
para maxima accuracy con minima latencia.

Arquitectura de 3 capas:
  Capa 1: RuleBasedIntentDetector  — < 1ms, determinista, 0 dependencias
  Capa 2: sklearn TF-IDF + LR     — 0.16ms, 96.26% acc, lightweight
  Capa 3: MiniLM multilingual     — ~10ms, semantica cross-lingual

Flujo de despacho:
  rule_conf >= 0.8        -> usar rule-based (fast path)
  rule_conf < 0.8         -> sklearn ML (capa 2)
    ml_conf >= 0.60       -> usar ML result
    ml_conf < 0.60        -> MiniLM semantico (capa 3)  [NUEVO]
      miniml_conf >= 0.50 -> usar MiniLM result
      miniml_conf < 0.50  -> degradar a ML result (graceful)

La capa 3 resuelve misclasificaciones por:
  - Slang LATAM ("mandar" vs "enviar", "regresar" vs "devolver")
  - Typos e informalidades sin keywords exactas
  - Intents implicitos ("esto me quedo grande" -> sizing/return)
  - Queries cross-lingual ("I want to return this vestido")

Autor: Retail Recommender Engineering
Fecha: 09 Enero 2026 | Capa 3 agregada: Mayo 2026
"""

import os
import logging
import time
from typing import Optional
from dataclasses import dataclass, asdict

from src.api.core.intent_detection import (
    get_intent_detector,
    IntentDetectionResult
)
from src.api.ml.intent_classifier import get_ml_classifier, MLPrediction

logger = logging.getLogger(__name__)


@dataclass
class HybridIntentResult:
    """
    Resultado de detección híbrida
    
    Extiende IntentDetectionResult con metadata adicional
    """
    # Campos heredados de IntentDetectionResult
    primary_intent: str
    sub_intent: str
    confidence: float
    reasoning: str
    matched_patterns: list
    product_context: dict
    
    # Campos adicionales para híbrido
    method_used: str  # "rule_based" | "ml_fallback" | "miniml_semantic"
    rule_based_confidence: float  # Confidence del rule-based
    ml_confidence: Optional[float] = None  # Confidence del ML (si se usó)
    total_time_ms: float = 0.0  # Tiempo total de detección
    
    def to_intent_detection_result(self) -> IntentDetectionResult:
        """
        Convierte a IntentDetectionResult estándar
        (para compatibilidad con código existente)
        """
        return IntentDetectionResult(
            primary_intent=self.primary_intent,
            sub_intent=self.sub_intent,
            confidence=self.confidence,
            reasoning=self.reasoning,
            matched_patterns=self.matched_patterns,
            product_context=self.product_context
        )


class HybridIntentDetector:
    """
    Detector híbrido: Rule-based + ML fallback
    
    Características:
    - Optimizado para latencia (rule-based primero)
    - Alta accuracy (ML para casos difíciles)
    - Feature flag para enable/disable ML
    - Graceful degradation si ML falla
    - Logging detallado para análisis
    
    Configuración vía variables de entorno:
    - ML_INTENT_ENABLED: "true"/"false" (default: "false")
    - ML_CONFIDENCE_THRESHOLD: 0.0-1.0 (default: 0.8)
    
    Ejemplo de uso:
    ```python
    detector = HybridIntentDetector()
    
    result = await detector.detect("¿puedo devolver un vestido?")
    # → HybridIntentResult con intent, confidence, method_used, etc.
    
    # Convertir a formato estándar si necesario
    standard_result = result.to_intent_detection_result()
    ```
    """
    
    def __init__(self):
        """
        Inicializa detector híbrido
        
        Carga configuración de environment variables.
        """
        # Rule-based detector (siempre activo)
        self.rule_based = get_intent_detector()
        
        # ML classifier capa 2 (lazy load)
        self.ml_classifier = None
        
        # MiniLM classifier capa 3 (lazy load) [NUEVO]
        # Solo se instancia si MINILM_INTENT_ENABLED=true
        self.miniml_classifier = None
        
        # Configuración capas 1+2 (sin cambios)
        self.ml_enabled = os.getenv("ML_INTENT_ENABLED", "false").lower() == "true"
        self.confidence_threshold = float(os.getenv("ML_CONFIDENCE_THRESHOLD", "0.8"))
        
        # Configuración capa 3 [NUEVO]
        # MINILM_INTENT_ENABLED: activa la capa 3 (default: off)
        # MINILM_TRIGGER_THRESHOLD: umbral de ml_conf bajo el cual se invoca MiniLM
        # MINILM_MIN_CONFIDENCE: minimo cosine similarity para aceptar resultado MiniLM
        self.miniml_enabled = os.getenv("MINILM_INTENT_ENABLED", "false").lower() == "true"
        self.miniml_trigger_threshold = float(os.getenv("MINILM_TRIGGER_THRESHOLD", "0.60"))
        self.miniml_min_confidence = float(os.getenv("MINILM_MIN_CONFIDENCE", "0.50"))
        
        # Estadísticas (para análisis y monitoreo)
        self.stats = {
            "total_queries": 0,
            "rule_based_used": 0,
            "ml_used": 0,
            "ml_failed": 0,
            "miniml_used": 0,    # [NUEVO] queries resueltas por capa 3
            "miniml_skipped": 0, # [NUEVO] capa 3 invocada pero conf < miniml_min_confidence
            "miniml_failed": 0,  # [NUEVO] errores en capa 3 (exception)
        }
        
        logger.info(
            f"HybridIntentDetector initialized "
            f"(ML enabled: {self.ml_enabled}, threshold: {self.confidence_threshold}, "
            f"MiniLM enabled: {self.miniml_enabled}, "
            f"trigger: {self.miniml_trigger_threshold}, "
            f"min_conf: {self.miniml_min_confidence})"
        )
    
    def _ensure_ml_loaded(self) -> bool:
        """
        Asegura que ML classifier está cargado (lazy load)
        
        Returns:
            True si ML está disponible, False si no
        """
        if not self.ml_enabled:
            return False
        
        if self.ml_classifier is None:
            self.ml_classifier = get_ml_classifier()
        
        # Intentar cargar si no está cargado
        if not self.ml_classifier.is_loaded():
            success = self.ml_classifier.load()
            if not success:
                logger.warning("ML classifier failed to load, will use rule-based only")
                return False
        
        return True

    def _ensure_miniml_loaded(self) -> bool:
        """
        Asegura que MiniLM classifier (capa 3) esta cargado (lazy load).

        Sigue el mismo patron que _ensure_ml_loaded() pero para la
        capa semantica. Si MINILM_INTENT_ENABLED=false o la carga
        falla, retorna False sin lanzar excepciones.

        El primer llamado con ML_INTENT_ENABLED=true puede tardar
        ~3-5s (carga del modelo + precomputo de centroides).
        Los llamados subsecuentes son instantaneos (is_loaded()=True).

        Returns:
            True si MiniLM esta disponible, False si no (degradacion graceful).
        """
        # Verificar feature flag primero (cero overhead si esta apagado)
        if not self.miniml_enabled:
            return False

        # Instanciar singleton solo cuando realmente se necesita
        if self.miniml_classifier is None:
            from src.api.ml.miniml_classifier import get_miniml_classifier  # noqa: PLC0415
            self.miniml_classifier = get_miniml_classifier()

        # Cargar modelo si todavia no esta cargado
        if not self.miniml_classifier.is_loaded():
            success = self.miniml_classifier.load()
            if not success:
                logger.warning(
                    "MiniLM classifier failed to load, will use ML-only result"
                )
                return False

        return True
    
    async def detect(self, query: str, user_id: Optional[str] = None) -> HybridIntentResult:
        """
        Detecta intent usando estrategia híbrida
        
        Flujo:
        1. Rule-based (siempre)
        2. Si confidence < threshold AND ML enabled → ML fallback
        3. Retorna mejor resultado
        
        Args:
            query: Query del usuario
            user_id: ID del usuario (opcional, para logging)
        
        Returns:
            HybridIntentResult con intent detectado
        """
        start_time = time.time()
        self.stats["total_queries"] += 1
        
        # FASE 1: Rule-based (siempre ejecutar primero)
        rule_result = self.rule_based.detect(query)
        rule_confidence = rule_result.confidence
        
        # Logging detallado para debugging
        logger.debug(
            f"Rule-based: intent={rule_result.primary_intent} "
            f"sub={rule_result.sub_intent} confidence={rule_confidence:.3f}"
        )
        
        # Si alta confidence O ML disabled → usar rule-based
        if rule_confidence >= self.confidence_threshold or not self.ml_enabled:
            self.stats["rule_based_used"] += 1
            total_time = (time.time() - start_time) * 1000
            
            return HybridIntentResult(
                primary_intent=rule_result.primary_intent,
                sub_intent=rule_result.sub_intent,
                confidence=rule_confidence,
                reasoning=rule_result.reasoning,
                matched_patterns=rule_result.matched_patterns,
                product_context=rule_result.product_context,
                method_used="rule_based",
                rule_based_confidence=rule_confidence,
                ml_confidence=None,
                total_time_ms=total_time
            )
        
        # FASE 2: ML fallback para casos ambiguos
        logger.debug(
            f"Low confidence ({rule_confidence:.3f}), attempting ML fallback..."
        )
        
        # Asegurar que ML está cargado
        if not self._ensure_ml_loaded():
            # ML no disponible, usar rule-based
            logger.warning("ML not available, using rule-based result")
            self.stats["rule_based_used"] += 1
            total_time = (time.time() - start_time) * 1000
            
            return HybridIntentResult(
                primary_intent=rule_result.primary_intent,
                sub_intent=rule_result.sub_intent,
                confidence=rule_confidence,
                reasoning=f"{rule_result.reasoning} (ML unavailable)",
                matched_patterns=rule_result.matched_patterns,
                product_context=rule_result.product_context,
                method_used="rule_based",
                rule_based_confidence=rule_confidence,
                ml_confidence=None,
                total_time_ms=total_time
            )
        
        # Predicción ML
        try:
            ml_prediction: Optional[MLPrediction] = self.ml_classifier.predict(query)
            
            if ml_prediction is None:
                # ML falló, usar rule-based
                logger.warning("ML prediction returned None, using rule-based")
                self.stats["ml_failed"] += 1
                self.stats["rule_based_used"] += 1
                total_time = (time.time() - start_time) * 1000
                
                return HybridIntentResult(
                    primary_intent=rule_result.primary_intent,
                    sub_intent=rule_result.sub_intent,
                    confidence=rule_confidence,
                    reasoning=f"{rule_result.reasoning} (ML failed)",
                    matched_patterns=rule_result.matched_patterns,
                    product_context=rule_result.product_context,
                    method_used="rule_based",
                    rule_based_confidence=rule_confidence,
                    ml_confidence=None,
                    total_time_ms=total_time
                )
            
            # ML exitoso - usar resultado ML

            # GUARD: Si el rule-based ya detecto TRANSACTIONAL con patron real,
            # el ML NO puede cambiarlo a INFORMATIONAL.
            # Distincion:
            #   fallback default -> confidence == 0.5 Y matched_patterns == []
            #   patron real      -> confidence >= 0.5 Y matched_patterns != []
            #
            # FIX (12/04/2026): El GUARD tiene una excepcion para verbos genericos.
            # Verbos como 'necesito', 'quiero', 'want', 'need' son keywords TRANSACCIONALES
            # pero son extremadamente genericos — aparecen en queries que claramente son
            # informacionales ('necesito saber mi talla', 'quiero entender el envio').
            # Cuando el rule-based matchea SOLO un verbo generico (confidence==0.5,
            # matched_patterns contiene exactamente uno de estos verbos), y el ML
            # tiene alta confianza en INFORMATIONAL (>= 0.75), es seguro permitir el override.
            # Sin esta excepcion, el GUARD bloquea el ML y queries validas van a productos.
            _GENERIC_TRANSACTIONAL_VERBS = {
                'necesito', 'quiero', 'need', 'want', 'me interesa'
            }
            _is_only_generic_verb = (
                rule_result.matched_patterns
                and len(rule_result.matched_patterns) == 1
                and any(
                    verb in rule_result.matched_patterns[0].lower()
                    for verb in _GENERIC_TRANSACTIONAL_VERBS
                )
                and rule_confidence == 0.5  # confidence minima = solo un patron matcheado
            )

            is_rule_based_transactional = (
                str(rule_result.primary_intent).upper() in ('TRANSACTIONAL', 'INTENTTYPE.TRANSACTIONAL')
                and rule_result.matched_patterns  # lista no vacia = patron real matcheado
                and not _is_only_generic_verb  # excepcion: verbo generico + ML alta confianza
            )
            ml_wants_informational = ml_prediction.intent.upper() == 'INFORMATIONAL'

            if is_rule_based_transactional and ml_wants_informational:
                logger.info(
                    f'GUARD: ML quiso cambiar TRANSACTIONAL a INFORMATIONAL '
                    f'pero rule-based tenia patron real (patterns={rule_result.matched_patterns}). '
                    f'Manteniendo TRANSACTIONAL. ML confidence fue {ml_prediction.confidence:.3f}'
                )
                self.stats['rule_based_used'] += 1
                total_time = (time.time() - start_time) * 1000
                return HybridIntentResult(
                    primary_intent=rule_result.primary_intent,
                    sub_intent=rule_result.sub_intent,
                    confidence=rule_result.confidence,
                    reasoning=(
                        f'Rule-based TRANSACTIONAL protected from ML override '
                        f'(ML said {ml_prediction.intent} @ {ml_prediction.confidence:.2f})'
                    ),
                    matched_patterns=rule_result.matched_patterns,
                    product_context=rule_result.product_context,
                    method_used='rule_based',
                    rule_based_confidence=rule_result.confidence,
                    ml_confidence=ml_prediction.confidence,
                    total_time_ms=total_time
                )

            self.stats["ml_used"] += 1
            total_time = (time.time() - start_time) * 1000
            
            logger.info(
                f"ML fallback: intent={ml_prediction.intent} "
                f"confidence={ml_prediction.confidence:.3f} "
                f"(rule-based was {rule_confidence:.3f})"
            )
            
            # ✅ FIX: Convertir ML intent (uppercase) a lowercase para Pydantic validation
            # ML classifier retorna "INFORMATIONAL" o "TRANSACTIONAL" (uppercase)
            # pero IntentDetectionResult espera "informational" o "transactional" (lowercase)
            ml_intent_lowercase = ml_prediction.intent.lower()
            
            # ✅ FIX 2: Si ML cambia el intent, necesitamos asignar sub_intent compatible
            # ML solo clasifica INFORMATIONAL vs TRANSACTIONAL
            # Si ML dice INFORMATIONAL pero rule-based dijo TRANSACTIONAL,
            # el sub_intent será TransactionalSubIntent (incompatible)
            if ml_intent_lowercase != rule_result.primary_intent.lower():
                # ML cambió el intent → asignar sub_intent por defecto
                if ml_intent_lowercase == "informational":
                    # Default para INFORMATIONAL: unknown (sub_intent genérico)
                    # El knowledge base determinará el tipo específico
                    ml_sub_intent = "unknown"
                else:
                    # Default para TRANSACTIONAL: product_search
                    ml_sub_intent = "product_search"
                
                logger.info(
                    f"ML changed intent from {rule_result.primary_intent} to {ml_intent_lowercase}, "
                    f"updating sub_intent from {rule_result.sub_intent} to {ml_sub_intent}"
                )
            else:
                # ML confirmó el intent → mantener sub_intent original
                ml_sub_intent = rule_result.sub_intent
            
            # FIX (12/04/2026): Cuando ML y rule-based coinciden en el MISMO intent,
            # usar la confianza MAS ALTA de ambos, no la del ML.
            #
            # PROBLEMA ORIGINAL: El ML ejecuta porque rule_confidence (0.70) < threshold (0.80).
            # El ML confirma INFORMATIONAL pero con confianza 0.514.
            # El codigo retornaba confidence=0.514 (ML), que luego cae bajo el threshold
            # del handler (0.70) y se clasifica como TRANSACTIONAL. Resultado incorrecto.
            #
            # RAZONAMIENTO: El ML fue llamado como "desempate" para queries ambiguas.
            # Si ambos sistemas coinciden en el intent, la evidencia combinada deberia
            # aumentar la confianza, no reducirla. Usar max() es la decision correcta:
            #   - Rule-based: 0.70 (patron real matcheado)
            #   - ML: 0.514 (clasificador estadistico confirma)
            #   - max(0.70, 0.514) = 0.70 → pasa el threshold 0.70 correctamente
            #
            # Si ML dice DISTINTO intent al rule-based, no aplica max() —
            # en ese caso el ML esta haciendo un override real, y su confianza
            # debe usarse tal cual para que el handler decida.
            intents_agree = (ml_intent_lowercase == rule_result.primary_intent.lower())
            final_confidence = (
                max(rule_confidence, ml_prediction.confidence)
                if intents_agree
                else ml_prediction.confidence
            )
            final_reasoning = (
                f"ML confirmed rule-based ({ml_intent_lowercase}, "
                f"max confidence: rule={rule_confidence:.2f} ml={ml_prediction.confidence:.2f})"
                if intents_agree
                else f"ML classification (rule-based: {rule_confidence:.2f})"
            )

            if intents_agree and ml_prediction.confidence < rule_confidence:
                logger.info(
                    f"ML confirmed same intent ({ml_intent_lowercase}), "
                    f"keeping rule-based confidence {rule_confidence:.2f} "
                    f"over ML confidence {ml_prediction.confidence:.2f}"
                )

            # ===========================================================
            # CAPA 3: MiniLM semantico (NUEVO — Mayo 2026)
            # ===========================================================
            # Se activa cuando ml_confidence < miniml_trigger_threshold
            # (default 0.60), lo que indica que sklearn tambien tiene
            # baja certeza y el query puede ser slang/typo/cross-lingual.
            #
            # Importante: se evalua DESPUES del calculo de final_confidence
            # (intents_agree + max()) para usar el mejor valor disponible
            # de sklearn como referencia de comparacion. Si final_confidence
            # ya supero el threshold, MiniLM no se invoca.
            # ===========================================================
            if (
                final_confidence < self.miniml_trigger_threshold
                and self._ensure_miniml_loaded()
            ):
                try:
                    miniml_pred = self.miniml_classifier.predict(query)

                    if (
                        miniml_pred is not None
                        and miniml_pred.confidence >= self.miniml_min_confidence
                    ):
                        # MiniLM tiene confianza suficiente -> usar su resultado
                        self.stats["miniml_used"] += 1
                        total_time = (time.time() - start_time) * 1000

                        logger.info(
                            f"MINIML: capa 3 activa "
                            f"label={miniml_pred.full_label} "
                            f"conf={miniml_pred.confidence:.3f} "
                            f"(ml fue {ml_intent_lowercase}@{ml_prediction.confidence:.3f}, "
                            f"rule fue {rule_result.primary_intent}@{rule_confidence:.3f})"
                        )

                        return HybridIntentResult(
                            primary_intent=miniml_pred.primary_intent,
                            sub_intent=miniml_pred.sub_intent or "unknown",
                            confidence=miniml_pred.confidence,
                            reasoning=(
                                f"MiniLM semantic layer-3 "
                                f"(label={miniml_pred.full_label}, "
                                f"cosine={miniml_pred.confidence:.2f}, "
                                f"rule={rule_confidence:.2f}, "
                                f"ml={ml_prediction.confidence:.2f})"
                            ),
                            matched_patterns=rule_result.matched_patterns,
                            product_context=rule_result.product_context,
                            method_used="miniml_semantic",
                            rule_based_confidence=rule_confidence,
                            ml_confidence=ml_prediction.confidence,
                            total_time_ms=total_time,
                        )
                    else:
                        # MiniLM invocado pero confianza insuficiente
                        # -> dejar que el flujo continue al return de ML
                        self.stats["miniml_skipped"] += 1
                        logger.debug(
                            f"MINIML: confianza insuficiente "
                            f"({miniml_pred.confidence if miniml_pred else 'None':.3f} "
                            f"< {self.miniml_min_confidence}), usando resultado ML"
                        )

                except Exception as miniml_exc:
                    # Degradacion graceful: fallo en capa 3 no bloquea la respuesta
                    self.stats["miniml_failed"] += 1
                    logger.error(
                        f"MINIML: exception en capa 3: {miniml_exc}",
                        exc_info=True,
                    )

            # Usar intent ML con sub_intent compatible
            return HybridIntentResult(
                primary_intent=ml_intent_lowercase,  # ✅ FIXED: lowercase
                sub_intent=ml_sub_intent,  # ✅ FIXED: compatible con primary_intent
                confidence=final_confidence,  # ✅ FIX: max cuando coinciden
                reasoning=final_reasoning,
                matched_patterns=rule_result.matched_patterns,
                product_context=rule_result.product_context,
                method_used="ml_fallback",
                rule_based_confidence=rule_confidence,
                ml_confidence=ml_prediction.confidence,
                total_time_ms=total_time
            )
            
        except Exception as e:
            # Exception en ML, usar rule-based
            logger.error(f"ML prediction exception: {e}", exc_info=True)
            self.stats["ml_failed"] += 1
            self.stats["rule_based_used"] += 1
            total_time = (time.time() - start_time) * 1000
            
            return HybridIntentResult(
                primary_intent=rule_result.primary_intent,
                sub_intent=rule_result.sub_intent,
                confidence=rule_confidence,
                reasoning=f"{rule_result.reasoning} (ML exception)",
                matched_patterns=rule_result.matched_patterns,
                product_context=rule_result.product_context,
                method_used="rule_based",
                rule_based_confidence=rule_confidence,
                ml_confidence=None,
                total_time_ms=total_time
            )
    
    def get_stats(self) -> dict:
        """
        Retorna estadísticas de uso por capa.
        
        Útil para monitorear qué porcentaje de queries requiere cada capa
        y detectar si la capa 3 se activa más de lo esperado.
        """
        if self.stats["total_queries"] == 0:
            return self.stats
        
        total = self.stats["total_queries"]
        
        return {
            **self.stats,
            "rule_based_percentage": (self.stats["rule_based_used"] / total) * 100,
            "ml_percentage": (self.stats["ml_used"] / total) * 100,
            "miniml_percentage": (self.stats["miniml_used"] / total) * 100,
            "ml_failure_rate": (self.stats["ml_failed"] / total) * 100 if self.stats["ml_failed"] > 0 else 0.0,
            "miniml_skip_rate": (self.stats["miniml_skipped"] / max(1, self.stats["miniml_used"] + self.stats["miniml_skipped"])) * 100,
        }
    
    def reset_stats(self):
        """Resetea estadísticas de todas las capas."""
        self.stats = {
            "total_queries": 0,
            "rule_based_used": 0,
            "ml_used": 0,
            "ml_failed": 0,
            "miniml_used": 0,
            "miniml_skipped": 0,
            "miniml_failed": 0,
        }


# Singleton global
_global_hybrid_detector: Optional[HybridIntentDetector] = None


def get_hybrid_intent_detector() -> HybridIntentDetector:
    """
    Retorna instancia global del hybrid detector (singleton)
    """
    global _global_hybrid_detector
    
    if _global_hybrid_detector is None:
        _global_hybrid_detector = HybridIntentDetector()
    
    return _global_hybrid_detector