"""
Hybrid Intent Detector
=======================

Combina rule-based intent detection con ML fallback para
máxima accuracy con mínima latencia.

Estrategia:
1. Siempre ejecutar rule-based primero (rápido, 1-5ms)
2. Si confidence >= threshold → usar resultado
3. Si confidence < threshold → fallback a ML
4. Si ML falla → usar rule-based de todos modos

Autor: AI Assistant  
Fecha: 09 Enero 2026 - FIXED: ML intent lowercase conversion
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
    method_used: str  # "rule_based" | "ml_fallback"
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
        
        # ML classifier (lazy load)
        self.ml_classifier = None
        
        # Configuración
        self.ml_enabled = os.getenv("ML_INTENT_ENABLED", "false").lower() == "true"
        self.confidence_threshold = float(os.getenv("ML_CONFIDENCE_THRESHOLD", "0.8"))
        
        # Estadísticas (para análisis)
        self.stats = {
            "total_queries": 0,
            "rule_based_used": 0,
            "ml_used": 0,
            "ml_failed": 0
        }
        
        logger.info(
            f"HybridIntentDetector initialized "
            f"(ML enabled: {self.ml_enabled}, threshold: {self.confidence_threshold})"
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
            
            # Usar intent ML con sub_intent compatible
            return HybridIntentResult(
                primary_intent=ml_intent_lowercase,  # ✅ FIXED: lowercase
                sub_intent=ml_sub_intent,  # ✅ FIXED: compatible con primary_intent
                confidence=ml_prediction.confidence,
                reasoning=f"ML classification (rule-based: {rule_confidence:.2f})",
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
        Retorna estadísticas de uso
        
        Útil para analizar qué método se usa más
        """
        if self.stats["total_queries"] == 0:
            return self.stats
        
        total = self.stats["total_queries"]
        
        return {
            **self.stats,
            "rule_based_percentage": (self.stats["rule_based_used"] / total) * 100,
            "ml_percentage": (self.stats["ml_used"] / total) * 100,
            "ml_failure_rate": (self.stats["ml_failed"] / total) * 100 if self.stats["ml_failed"] > 0 else 0.0
        }
    
    def reset_stats(self):
        """Resetea estadísticas"""
        self.stats = {
            "total_queries": 0,
            "rule_based_used": 0,
            "ml_used": 0,
            "ml_failed": 0
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