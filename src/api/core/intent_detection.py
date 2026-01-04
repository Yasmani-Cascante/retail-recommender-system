"""
Intent Detection - Rule-Based Implementation
Simple, fast, and effective rule-based intent detector.

Design Principles:
- Rules over ML (for now) - simple, maintainable, fast
- High precision over high recall - better to default to products than give wrong info
- Easy to extend - adding new patterns is trivial
- Ready for extraction - designed as standalone module
"""

import re
import logging
from typing import List, Dict, Optional, Set
from functools import lru_cache

from src.api.core.intent_types import (
    IntentType,
    InformationalSubIntent,
    TransactionalSubIntent,
    IntentDetectionResult
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# PATTERN DEFINITIONS
# ═══════════════════════════════════════════════════════════════

class IntentPatterns:
    """
    Pattern definitions for intent detection.
    Organized by intent type and sub-intent.
    """
    
    # ───────────────────────────────────────────────────────────
    # INFORMATIONAL PATTERNS
    # ───────────────────────────────────────────────────────────
    
    INFORMATIONAL_PATTERNS = {
        # Policy - Returns/Refunds
        InformationalSubIntent.POLICY_RETURN: {
            "keywords": [
                r"\b(política|policy|políticas|policies)\b",
                r"\b(devolución|devolucion|devolver|devoluciones|return|returns)\b",
                r"\b(reembolso|refund|reintegro)\b",
                r"\b(cambio|cambiar|exchange)\b",
                r"\b(garantía|warranty|garantia)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(cuál|cual|cuáles|cuales|what|which)\b",
                r"\b(puedo|puede|can|may)\b",
            ],
            "negative_context": [
                r"\b(no (me )?(queda|gusta|sirve))\b",
                r"\b(mal(o)?|defectuoso|roto|damaged)\b",
            ]
        },
        
        # Policy - Shipping/Delivery
        InformationalSubIntent.POLICY_SHIPPING: {
            "keywords": [
                r"\b(envío|envio|shipping|delivery|entrega)\b",
                r"\b(enviar|mandar|send|ship)\b",
                r"\b(paquete|package|pedido|order)\b",
                r"\b(rastreo|tracking|seguimiento)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(cuándo|cuando|cuanto.*tarda|when)\b",
                r"\b(dónde|donde|where)\b",
            ]
        },
        
        # Policy - Payment
        InformationalSubIntent.POLICY_PAYMENT: {
            "keywords": [
                r"\b(pago|payment|pagos|payments)\b",
                r"\b(pagar|pay|paid)\b",
                r"\b(tarjeta|card|crédito|credito|débito|debito)\b",
                r"\b(efectivo|cash|transferencia|transfer)\b",
                r"\b(paypal|mercadopago|mercado.*pago)\b",
                r"\b(cuotas|meses.*sin.*intereses|installments)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(acepta|accept|aceptan)\b",
                r"\b(puedo|puede|can)\b",
            ]
        },
        
        # Product Info - Material
        InformationalSubIntent.PRODUCT_MATERIAL: {
            "keywords": [
                r"\b(material|tela|fabric|hecho.*de)\b",
                r"\b(algodón|cotton|polyester|poliéster|seda|silk)\b",
                r"\b(cuero|leather|sintético|synthetic)\b",
            ],
            "question_words": [
                r"\b(de qué|what.*made|qué tipo)\b",
                r"\b(cuál|cual|what)\b",
            ]
        },
        
        # Product Info - Size/Fit
        InformationalSubIntent.PRODUCT_SIZE: {
            "keywords": [
                r"\b(talla|size|sizing|medida|número)\b",
                r"\b(chico|mediano|grande|small|medium|large)\b",
                r"\b(guía.*de.*tallas|size.*guide|sizing.*chart)\b",
                r"\b(corre|queda|fit|fits)\b",
            ],
            "question_words": [
                r"\b(qué.*talla|what.*size)\b",
                r"\b(cómo.*saber|how.*know)\b",
                r"\b(cuál.*es.*mi|what.*my)\b",
            ]
        },
        
        # Product Info - Care
        InformationalSubIntent.PRODUCT_CARE: {
            "keywords": [
                r"\b(lavar|wash|washing|limpieza|clean)\b",
                r"\b(cuidado|care|mantenimiento|maintenance)\b",
                r"\b(planchar|iron|secar|dry)\b",
            ],
            "question_words": [
                r"\b(cómo|como|how)\b",
                r"\b(puedo|puede|can)\b",
            ]
        },
        
        # Product Info - Availability
        InformationalSubIntent.PRODUCT_AVAILABILITY: {
            "keywords": [
                r"\b(disponible|available|availability|stock)\b",
                r"\b(hay|have|tiene|there.*is)\b",
                r"\b(cuándo.*llega|when.*arrive|when.*available)\b",
            ],
            "question_words": [
                r"\b(hay|have|tiene)\b",
                r"\b(cuándo|cuando|when)\b",
            ]
        }
    }
    
    # ───────────────────────────────────────────────────────────
    # TRANSACTIONAL PATTERNS
    # ───────────────────────────────────────────────────────────
    
    TRANSACTIONAL_PATTERNS = {
        TransactionalSubIntent.PRODUCT_SEARCH: {
            "keywords": [
                r"\b(busco|buscando|estoy.*buscando|looking.*for)\b",
                r"\b(necesito|quiero|me.*interesa|need|want)\b",
                r"\b(mostrar|ver|enseñar|dame|show|display)\b",
                r"\b(recomienda|sugerir|suggest|recommend)\b",
                r"\b(opciones.*de|options|alternativas)\b",
            ]
        },
        
        TransactionalSubIntent.PRODUCT_VIEW: {
            "keywords": [
                r"\b(ver.*este|ver.*ese|see.*this|see.*that)\b",
                r"\b(detalles|details|información.*del.*producto)\b",
                r"\b(características|features|especificaciones)\b",
            ]
        },
        
        TransactionalSubIntent.PURCHASE_INTENT: {
            "keywords": [
                r"\b(comprar|buy|purchase|adquirir)\b",
                r"\b(llevar|me.*llevo|take|get)\b",
                r"\b(agregar.*carrito|add.*cart|añadir)\b",
                r"\b(checkout|finalizar.*compra|pay)\b",
            ]
        }
    }
    
    # ───────────────────────────────────────────────────────────
    # QUESTION INDICATORS
    # ───────────────────────────────────────────────────────────
    
    QUESTION_INDICATORS = [
        r"^\s*¿",  # Spanish question start
        r"\?\s*$",  # Question mark at end
        r"\b(cómo|como|cuál|cual|cuáles|cuales|qué|que|cuándo|cuando|cuánto|cuanto|dónde|donde|por qué|porque)\b",
        r"\b(how|what|which|when|where|why|who)\b",
        r"\b(puedo|puede|pueden|can|may|could)\b",
        r"\b(acepta|aceptan|accept|accepts)\b",
    ]


# ═══════════════════════════════════════════════════════════════
# INTENT DETECTOR
# ═══════════════════════════════════════════════════════════════

class RuleBasedIntentDetector:
    """
    Rule-based intent detector.
    
    Strategy:
    1. Detect if query is a question
    2. Check for informational patterns
    3. Check for transactional patterns
    4. Default to TRANSACTIONAL (safe fallback)
    """
    
    def __init__(self):
        """Initialize detector."""
        self.patterns = IntentPatterns()
        
        # Compile regex patterns for performance
        self._compiled_patterns = self._compile_patterns()
        
        # Metrics
        self.metrics = {
            "total_detections": 0,
            "informational_detected": 0,
            "transactional_detected": 0,
            "avg_confidence": 0.0
        }
        
        logger.info("✅ RuleBasedIntentDetector initialized")
    
    def _compile_patterns(self) -> Dict:
        """
        Compile regex patterns for better performance.
        Called once during initialization.
        """
        compiled = {
            "question_indicators": [
                re.compile(pattern, re.IGNORECASE)
                for pattern in self.patterns.QUESTION_INDICATORS
            ],
            "informational": {},
            "transactional": {}
        }
        
        # Compile informational patterns
        for sub_intent, patterns_dict in self.patterns.INFORMATIONAL_PATTERNS.items():
            compiled["informational"][sub_intent] = {
                "keywords": [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in patterns_dict.get("keywords", [])
                ],
                "question_words": [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in patterns_dict.get("question_words", [])
                ] if "question_words" in patterns_dict else [],
                "negative_context": [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in patterns_dict.get("negative_context", [])
                ] if "negative_context" in patterns_dict else []
            }
        
        # Compile transactional patterns
        for sub_intent, patterns_dict in self.patterns.TRANSACTIONAL_PATTERNS.items():
            compiled["transactional"][sub_intent] = {
                "keywords": [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in patterns_dict.get("keywords", [])
                ]
            }
        
        return compiled
    
    def detect(self, query: str, context: Optional[Dict] = None) -> IntentDetectionResult:
        """
        Detect intent from user query.
        
        Args:
            query: User query string
            context: Optional context (not used yet, for future expansion)
        
        Returns:
            IntentDetectionResult with detected intent
        """
        self.metrics["total_detections"] += 1
        
        logger.debug(f"Detecting intent for query: '{query[:50]}...'")
        
        # ═══════════════════════════════════════════════════════
        # STEP 1: Check if it's a question
        # ═══════════════════════════════════════════════════════
        
        is_question = self._is_question(query)
        
        # ═══════════════════════════════════════════════════════
        # STEP 2: Try informational detection
        # ═══════════════════════════════════════════════════════
        
        if is_question:
            info_result = self._detect_informational(query)
            
            if info_result and info_result.confidence >= 0.7:
                self.metrics["informational_detected"] += 1
                self._update_avg_confidence(info_result.confidence)
                logger.info(f"✅ Detected INFORMATIONAL: {info_result.sub_intent} "
                           f"(confidence: {info_result.confidence:.2f})")
                return info_result
        
        # ═══════════════════════════════════════════════════════
        # STEP 3: Try transactional detection
        # ═══════════════════════════════════════════════════════
        
        trans_result = self._detect_transactional(query)
        
        # ✅ FIX: Lower threshold for transactional (0.5) since single keyword is strong signal
        if trans_result and trans_result.confidence >= 0.5:
            self.metrics["transactional_detected"] += 1
            self._update_avg_confidence(trans_result.confidence)
            logger.info(f"✅ Detected TRANSACTIONAL: {trans_result.sub_intent} "
                       f"(confidence: {trans_result.confidence:.2f})")
            return trans_result
        
        # ═══════════════════════════════════════════════════════
        # STEP 4: Default fallback (TRANSACTIONAL)
        # ═══════════════════════════════════════════════════════
        
        logger.warning(f"⚠️ No clear pattern match, defaulting to TRANSACTIONAL")
        
        default_result = IntentDetectionResult(
            primary_intent=IntentType.TRANSACTIONAL,
            sub_intent=TransactionalSubIntent.PRODUCT_SEARCH,
            confidence=0.5,
            reasoning="Default fallback - no clear pattern matched",
            matched_patterns=[]
        )
        
        self.metrics["transactional_detected"] += 1
        self._update_avg_confidence(0.5)
        
        return default_result
    
    def _is_question(self, query: str) -> bool:
        """Check if query is a question."""
        for pattern in self._compiled_patterns["question_indicators"]:
            if pattern.search(query):
                return True
        return False
    
    def _detect_informational(self, query: str) -> Optional[IntentDetectionResult]:
        """
        Detect informational intent and sub-intent.
        
        Returns best match based on:
        1. Keywords match
        2. Question words match (bonus)
        3. Negative context (bonus for returns)
        """
        best_match = None
        best_score = 0.0
        best_sub_intent = None
        matched_patterns_list = []
        
        for sub_intent, patterns in self._compiled_patterns["informational"].items():
            score = 0.0
            local_matches = []
            
            # Check keywords (required)
            keyword_matches = 0
            for pattern in patterns["keywords"]:
                if pattern.search(query):
                    keyword_matches += 1
                    local_matches.append(pattern.pattern)
            
            if keyword_matches == 0:
                continue  # No keyword match, skip this sub-intent
            
            score += keyword_matches * 0.4  # Base score from keywords
            
            # Check question words (bonus)
            if patterns["question_words"]:
                for pattern in patterns["question_words"]:
                    if pattern.search(query):
                        score += 0.3  # Bonus for question word match
                        local_matches.append(pattern.pattern)
                        break
            
            # Check negative context (bonus for returns)
            if patterns["negative_context"]:
                for pattern in patterns["negative_context"]:
                    if pattern.search(query):
                        score += 0.2  # Bonus for negative context
                        local_matches.append(pattern.pattern)
                        break
            
            # Update best match
            if score > best_score:
                best_score = score
                best_sub_intent = sub_intent
                matched_patterns_list = local_matches
        
        if best_score >= 0.4:  # Minimum threshold
            confidence = min(best_score, 1.0)  # Cap at 1.0
            
            return IntentDetectionResult(
                primary_intent=IntentType.INFORMATIONAL,
                sub_intent=best_sub_intent.value,
                confidence=confidence,
                reasoning=f"Question + {best_sub_intent.value} keywords",
                matched_patterns=matched_patterns_list[:3]  # Limit to 3 for readability
            )
        
        return None
    
    def _detect_transactional(self, query: str) -> Optional[IntentDetectionResult]:
        """Detect transactional intent and sub-intent."""
        best_match = None
        best_score = 0.0
        best_sub_intent = None
        matched_patterns_list = []
        
        for sub_intent, patterns in self._compiled_patterns["transactional"].items():
            score = 0.0
            local_matches = []
            
            # Check keywords
            for pattern in patterns["keywords"]:
                if pattern.search(query):
                    score += 0.5  # Each keyword match
                    local_matches.append(pattern.pattern)
            
            if score > best_score:
                best_score = score
                best_sub_intent = sub_intent
                matched_patterns_list = local_matches
        
        if best_score >= 0.5:  # Minimum threshold
            confidence = min(best_score, 0.95)  # Cap at 0.95 (not 1.0, less certain than informational)
            
            return IntentDetectionResult(
                primary_intent=IntentType.TRANSACTIONAL,
                sub_intent=best_sub_intent.value,
                confidence=confidence,
                reasoning=f"Transactional keywords: {best_sub_intent.value}",
                matched_patterns=matched_patterns_list[:3]
            )
        
        return None
    
    def _update_avg_confidence(self, confidence: float):
        """Update rolling average confidence."""
        n = self.metrics["total_detections"]
        current_avg = self.metrics["avg_confidence"]
        self.metrics["avg_confidence"] = (current_avg * (n - 1) + confidence) / n
    
    def get_metrics(self) -> Dict:
        """Get detector metrics."""
        total = self.metrics["total_detections"]
        return {
            **self.metrics,
            "informational_rate": (
                self.metrics["informational_detected"] / total
                if total > 0 else 0.0
            ),
            "transactional_rate": (
                self.metrics["transactional_detected"] / total
                if total > 0 else 0.0
            )
        }


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

# Singleton instance
_detector_instance: Optional[RuleBasedIntentDetector] = None


def get_intent_detector() -> RuleBasedIntentDetector:
    """
    Get singleton instance of intent detector.
    Lazy initialization.
    """
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = RuleBasedIntentDetector()
    return _detector_instance


def detect_intent(query: str, context: Optional[Dict] = None) -> IntentDetectionResult:
    """
    Public API for intent detection.
    
    Args:
        query: User query string
        context: Optional context dictionary
    
    Returns:
        IntentDetectionResult
    
    Example:
        >>> result = detect_intent("¿cuál es la política de devolución?")
        >>> print(result.primary_intent)
        IntentType.INFORMATIONAL
        >>> print(result.sub_intent)
        'policy_return'
    """
    detector = get_intent_detector()
    return detector.detect(query, context)