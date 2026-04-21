"""
ML Module
=========

Machine Learning components for intent detection.

Components:
- intent_classifier: ML classifier standalone (sklearn)
- hybrid_detector: Hybrid detector (rule-based + ML)
"""

from .intent_classifier import MLIntentClassifier, get_ml_classifier
from .hybrid_detector import HybridIntentDetector, get_hybrid_intent_detector

__all__ = [
    'MLIntentClassifier',
    'get_ml_classifier',
    'HybridIntentDetector',
    'get_hybrid_intent_detector',
]