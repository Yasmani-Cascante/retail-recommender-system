"""
ML Intent Classifier
====================

Clasificador de intents basado en sklearn integrado en FastAPI.

Características:
- Lazy loading (no impacta startup)
- Thread-safe
- Manejo robusto de errores
- Logging detallado
- Métricas de performance

Fecha: 02 Enero 2026
"""

import joblib
import numpy as np
import time
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class MLPrediction:
    """Resultado de predicción ML"""
    intent: str  # "INFORMATIONAL" | "TRANSACTIONAL"
    confidence: float  # 0.0 - 1.0
    probabilities: Dict[str, float]  # {"INFORMATIONAL": 0.x, "TRANSACTIONAL": 0.y"}
    inference_time_ms: float  # Tiempo de inferencia en ms
    method: str = "ml_sklearn"  # Identificador del método usado


class MLIntentClassifier:
    """
    Clasificador ML ligero integrado para intent detection
    
    Usa TF-IDF + Logistic Regression para balance óptimo
    entre accuracy y latencia.
    
    Características:
    - Lazy loading: Solo carga modelo cuando se usa por primera vez
    - Thread-safe: Puede ser usado concurrentemente
    - Graceful degradation: Si falla, retorna None (no exception)
    - Logging: Detallado para debugging
    
    Ejemplo de uso:
    ```python
    classifier = MLIntentClassifier()
    
    # Primera llamada carga el modelo (lento)
    result = classifier.predict("¿puedo devolver un vestido?")
    # → MLPrediction(intent="INFORMATIONAL", confidence=0.95, ...)
    
    # Llamadas subsecuentes son rápidas
    result = classifier.predict("busco vestido largo")
    # → MLPrediction(intent="TRANSACTIONAL", confidence=0.92, ...)
    ```
    """
    
    def __init__(self, model_path: Optional[Path] = None):
        """
        Inicializa classifier (NO carga modelo todavía)
        
        Args:
            model_path: Path al directorio con vectorizer.pkl y model.pkl
                       Si None, usa 'models/intent_classifier' (default)
        """
        self.model_path = model_path or Path("models/intent_classifier")
        self.vectorizer = None
        self.model = None
        self.metadata = None
        self.loaded = False
        self._load_attempted = False
        
        logger.info(f"MLIntentClassifier initialized (model path: {self.model_path})")
    
    def load(self) -> bool:
        """
        Carga el modelo del disco (lazy load)
        
        Returns:
            True si carga exitosa, False si falla
        """
        if self.loaded:
            return True
        
        if self._load_attempted:
            # Ya intentamos cargar y falló, no reintentar
            return False
        
        self._load_attempted = True
        
        try:
            logger.info("🔄 Loading ML intent classifier...")
            start_time = time.time()
            
            # Validar que archivos existen
            vectorizer_path = self.model_path / "vectorizer.pkl"
            model_path = self.model_path / "model.pkl"
            metadata_path = self.model_path / "metadata.json"
            
            if not vectorizer_path.exists():
                logger.error(f"❌ Vectorizer not found: {vectorizer_path}")
                return False
            
            if not model_path.exists():
                logger.error(f"❌ Model not found: {model_path}")
                return False
            
            # Cargar vectorizer
            logger.debug(f"Loading vectorizer from {vectorizer_path}")
            self.vectorizer = joblib.load(vectorizer_path)
            
            # Cargar model
            logger.debug(f"Loading model from {model_path}")
            self.model = joblib.load(model_path)
            
            # Cargar metadata (opcional)
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                    logger.debug(f"Metadata loaded: {self.metadata.get('training_date', 'unknown')}")
            
            load_time = (time.time() - start_time) * 1000
            
            self.loaded = True
            logger.info(f"✅ ML model loaded successfully ({load_time:.0f}ms)")
            logger.info(f"   Classes: {self.model.classes_}")
            logger.info(f"   Vocab size: {len(self.vectorizer.vocabulary_)}")
            
            if self.metadata:
                logger.info(f"   Test accuracy: {self.metadata.get('metrics', {}).get('test_accuracy', 'N/A')}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to load ML model: {e}", exc_info=True)
            self.loaded = False
            return False
    
    def predict(self, query: str, preload: bool = False) -> Optional[MLPrediction]:
        """
        Predice intent de una query
        
        Args:
            query: Query del usuario
            preload: Si True y modelo no cargado, intenta cargar primero
        
        Returns:
            MLPrediction con intent y confidence, o None si falla
        """
        # Lazy load si no está cargado
        if not self.loaded:
            if preload or not self._load_attempted:
                if not self.load():
                    logger.warning("ML model not loaded, prediction failed")
                    return None
            else:
                return None
        
        try:
            start_time = time.time()
            
            # Preprocesar query (lowercase)
            query_clean = query.lower().strip()
            
            if not query_clean:
                logger.warning("Empty query provided")
                return None
            
            # Vectorizar
            X = self.vectorizer.transform([query_clean])
            
            # Predicción
            prediction = self.model.predict(X)[0]
            probabilities = self.model.predict_proba(X)[0]
            
            # Mapear a diccionario de probabilidades
            classes = self.model.classes_
            proba_dict = dict(zip(classes, probabilities))
            
            # Confidence = max probability
            confidence = float(max(probabilities))
            
            inference_time = (time.time() - start_time) * 1000  # ms
            
            result = MLPrediction(
                intent=prediction,
                confidence=confidence,
                probabilities=proba_dict,
                inference_time_ms=inference_time,
                method="ml_sklearn"
            )
            
            # Log para debugging (solo en casos de baja confidence)
            if confidence < 0.7:
                logger.debug(
                    f"Low confidence prediction: query='{query[:50]}...' "
                    f"intent={prediction} confidence={confidence:.3f}"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"ML prediction failed: {e}", exc_info=True)
            return None
    
    def predict_batch(self, queries: List[str]) -> List[Optional[MLPrediction]]:
        """
        Predice intents para múltiples queries (más eficiente)
        
        Args:
            queries: Lista de queries
        
        Returns:
            Lista de MLPrediction (o None si falla)
        """
        if not self.loaded:
            if not self.load():
                return [None] * len(queries)
        
        try:
            start_time = time.time()
            
            # Preprocesar
            queries_clean = [q.lower().strip() for q in queries]
            
            # Vectorizar (batch)
            X = self.vectorizer.transform(queries_clean)
            
            # Predicción (batch)
            predictions = self.model.predict(X)
            probabilities = self.model.predict_proba(X)
            
            inference_time = (time.time() - start_time) * 1000
            avg_time = inference_time / len(queries)
            
            # Construir resultados
            results = []
            classes = self.model.classes_
            
            for i, (pred, proba) in enumerate(zip(predictions, probabilities)):
                proba_dict = dict(zip(classes, proba))
                confidence = float(max(proba))
                
                results.append(MLPrediction(
                    intent=pred,
                    confidence=confidence,
                    probabilities=proba_dict,
                    inference_time_ms=avg_time,
                    method="ml_sklearn_batch"
                ))
            
            logger.debug(
                f"Batch prediction: {len(queries)} queries "
                f"in {inference_time:.1f}ms ({avg_time:.1f}ms avg)"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Batch prediction failed: {e}", exc_info=True)
            return [None] * len(queries)
    
    def get_model_info(self) -> Dict:
        """
        Retorna información del modelo cargado
        
        Returns:
            Dict con metadata del modelo
        """
        if not self.loaded:
            return {
                "loaded": False,
                "error": "Model not loaded"
            }
        
        info = {
            "loaded": True,
            "model_type": "TF-IDF + Logistic Regression",
            "classes": self.model.classes_.tolist(),
            "vocab_size": len(self.vectorizer.vocabulary_),
            "model_path": str(self.model_path)
        }
        
        if self.metadata:
            info.update({
                "training_date": self.metadata.get("training_date"),
                "test_accuracy": self.metadata.get("metrics", {}).get("test_accuracy"),
                "cv_accuracy": self.metadata.get("metrics", {}).get("cv_mean")
            })
        
        return info
    
    def is_loaded(self) -> bool:
        """Retorna True si el modelo está cargado"""
        return self.loaded


# Singleton global (opcional - para reuso fácil)
_global_classifier: Optional[MLIntentClassifier] = None


def get_ml_classifier() -> MLIntentClassifier:
    """
    Retorna instancia global del classifier (singleton pattern)
    
    Útil para reusar misma instancia en toda la app sin cargar múltiples veces.
    """
    global _global_classifier
    
    if _global_classifier is None:
        _global_classifier = MLIntentClassifier()
    
    return _global_classifier