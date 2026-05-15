"""
MiniLM Semantic Intent Classifier  — Capa 3 del HybridIntentDetector
======================================================================

Usa paraphrase-multilingual-MiniLM-L6-v2 para clasificacion semantica
de intents. Solo actua cuando rule-based (capa 1) Y sklearn TF-IDF
(capa 2) tienen baja confianza (< MINILM_TRIGGER_THRESHOLD).

POR QUE ESTE MODELO:
  - 22M parametros / ~88MB en disco (sin GPU)
  - 200+ idiomas: ES formal, ES-MX, ES-CL, ES-CH, EN, FR, DE, ...
  - Captura semantica real: sinonimos, slang, typos, cross-lingual
  - ~8-12ms de inferencia en CPU despues del warmup inicial
  - Zero fine-tuning: prototype-based classification (zero-shot)

PROTOTYPE-BASED CLASSIFICATION:
  Para cada sub-intent, se precomputan embeddings de 6-10 queries
  representativas (multilingues + variantes LATAM). El "centroide"
  de esos embeddings define el espacio semantico del sub-intent.
  En inferencia: embed query -> cosine similarity vs. centroides.

  Ventaja vs fine-tuning:
    - Extensible sin reentrenamiento: agregar sub-intent = agregar ejemplos
    - Funciona con pocos datos (fine-tuning sobreajusta con < 500 samples)
    - Actualizable en runtime cambiando PROTOTYPE_EXAMPLES
    - Explicable: puedes ver que ejemplos "ganaron" en similitud

INTEGRACION CON HYBRID_DETECTOR:
  Activado por feature flag: MINILM_INTENT_ENABLED=true
  Threshold de disparo: MINILM_TRIGGER_THRESHOLD (default 0.60)
  El hybrid_detector lo llama solo cuando ml_confidence < 0.60

AUTOR: Retail Recommender Engineering
FECHA: Mayo 2026
"""

import logging
import time
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ================================================================
# PROTOTYPE EXAMPLES
# ================================================================
# Reglas de diseno:
#   1. 6-10 queries por label — suficiente para un centroide robusto
#   2. Cubrir variantes: ES formal, ES-LATAM informal, EN
#   3. Incluir al menos 1 ejemplo con typo comun en policies principales
#   4. Incluir al menos 1 variante LATAM (MX, CL, AR) en policies
#   5. NO duplicar exactamente keywords del rule-based —
#      el valor esta en capturar lo que TF-IDF NO captura
# ================================================================

PROTOTYPE_EXAMPLES: Dict[str, List[str]] = {

    # -- Greeting --------------------------------------------------
    "greeting": [
        "hola",
        "hi",
        "hello",
        "buenas",
        "buenos dias",
        "hola que tal",
        "hey",
        "saludos",
    ],

    # -- Policy: Returns -------------------------------------------
    # Cubre: slang LATAM, implicit returns, typos, cross-lingual
    "informational/policy_return": [
        "cual es la politica de devoluciones?",        # sin acentos (typo comun)
        "como puedo devolver un articulo?",
        "quiero regresar algo que compre",             # MX: "regresar"
        "se puede devolver la plata si no me gusta",   # CL: "devolver la plata"
        "cuantos dias tengo para devolver?",
        "me llegaron mal los zapatos como los devuelvo",  # implicit + informal
        "can I return this item?",
        "what is your return policy?",
        "esto no me gusto quiero que me devuelvan el dinero",  # intent implicito
        "cambio o devolucion como funciona",           # informal sin signos
    ],

    # -- Policy: Shipping ------------------------------------------
    # Cubre: "mandar" vs "enviar", domicilio, CL informal
    "informational/policy_shipping": [
        "cuanto tarda el envio?",
        "hacen envios a domicilio?",
        "me pueden mandar hasta Santiago?",            # CL: "mandar"
        "cuando llega mi pedido",
        "tienen envio a mi direccion?",
        "how long does shipping take?",
        "do you ship to my country?",
        "cuanto cuesta el envio?",
        "me mandan la compra a casa?",                 # LATAM muy informal
        "el paquete cuando me llega",                  # implicit shipping query
    ],

    # -- Policy: Payment -------------------------------------------
    # Cubre: marcas de tarjetas, plazos, terminologia LATAM
    "informational/policy_payment": [
        "que metodos de pago aceptan?",
        "puedo pagar con Mastercard?",
        "aceptan Visa?",
        "se puede pagar a plazos?",
        "aceptan PayPal?",
        "how can I pay?",
        "do you accept credit cards?",
        "pagan con mercadopago?",                      # LATAM: mercadopago
        "puedo pagar en cuotas sin intereses",
        "que formas de pago tienen",
    ],

    # -- Policy: Warranty ------------------------------------------
    "informational/policy_warranty": [
        "tienen garantia los productos?",
        "me llego defectuoso que hago",                # implicit warranty
        "el producto esta roto como lo reparan",
        "cuanto dura la garantia?",
        "warranty information",
        "the product is broken",
        "como aplico la garantia?",
        "salio fallado que hago",                      # CL: "salio fallado"
    ],

    # -- Policy: Privacy -------------------------------------------
    "informational/policy_privacy": [
        "como usan mis datos personales?",
        "politica de privacidad",
        "guardan mi informacion?",
        "privacy policy",
        "what data do you collect?",
        "venden mis datos?",
        "con quien comparten mi informacion",
    ],

    # -- Product: Sizing -------------------------------------------
    # Cubre: "corre grande", medidas en cm, recomendacion personal
    "informational/product_sizing": [
        "que talla me queda?",
        "como se mi talla?",
        "guia de tallas",
        "mido 1.70 que talla uso?",
        "tienen talla XL?",
        "what size should I order?",
        "how do I find my size?",
        "las tallas son europeas o americanas?",
        "me recomiendas una talla",
        "corre grande o chico",                        # LATAM: "corre grande"
        "me queda bien si pido mi talla normal?",
        "tabla de medidas en centimetros",
    ],

    # -- Product: Material -----------------------------------------
    "informational/product_material": [
        "de que material esta hecho?",
        "es de algodon?",
        "what fabric is this?",
        "que composicion tiene la tela?",
        "is this made of leather?",
        "de que esta hecho el vestido?",
        "que tan gruesa es la tela?",
    ],

    # -- Product: Care ---------------------------------------------
    "informational/product_care": [
        "como lavo esto?",
        "se puede meter a la lavadora?",
        "instrucciones de lavado",
        "how do I wash this?",
        "como cuido la prenda?",
        "can I machine wash it?",
        "se puede planchar?",
    ],

    # -- Product: Availability -------------------------------------
    # Cubre: "agotado", "se acabo", preguntas de stock implicitas
    "informational/product_availability": [
        "esta disponible en stock?",
        "hay en talla S?",
        "cuando vuelve a estar disponible?",
        "is this in stock?",
        "do you have this in blue?",
        "todavia lo tienen?",
        "se agoto?",
        "ya no hay?",                                  # LATAM muy informal
        "me avisan cuando llegue?",                    # implicit availability
    ],

    # -- Account: Orders -------------------------------------------
    "informational/account_orders": [
        "donde esta mi pedido?",
        "quiero ver mis compras",
        "how do I track my order?",
        "cuando llega mi pedido?",
        "ver historial de pedidos",
        "my order status",
        "ya salio mi pedido?",
    ],

    # -- Account: Modifications ------------------------------------
    "informational/account_modifications": [
        "como cambio mi direccion de envio?",
        "quiero modificar mi pedido",
        "can I change my order?",
        "como cancelo un pedido?",
        "change my delivery address",
        "actualizar mis datos de cuenta",
    ],

    # -- General FAQ -----------------------------------------------
    "informational/general_faq": [
        "como funciona la tienda?",
        "necesito ayuda",
        "tengo una pregunta",
        "I need help",
        "contact support",
        "tienen atencion al cliente?",
        "con quien me comunico",
    ],

    # -- Transactional: Product search ----------------------------
    # Cubre: recomendaciones, similares, busquedas de categoria
    "transactional/product_search": [
        "busco un vestido azul",
        "muestrame camisas de hombre",
        "quiero ver zapatos",
        "show me dresses",
        "I'm looking for a jacket",
        "necesito un regalo",
        "recomiendame algo casual",
        "tienen algo para una boda?",
        "ver los productos nuevos",
        "opciones de ropa de verano",
        "algo parecido a esto",
        "muestrame mas opciones",
        "que mas tienen de vestidos?",
    ],
}


# ================================================================
# RESULTADO
# ================================================================

@dataclass
class MiniLMPrediction:
    """
    Resultado de clasificacion semantica MiniLM.

    full_label combina primary_intent y sub_intent en el formato
    usado en PROTOTYPE_EXAMPLES: "informational/policy_return"
    o simplemente "greeting" para el caso sin sub-intent.
    """
    primary_intent: str           # "informational" | "transactional" | "greeting"
    sub_intent: Optional[str]     # "policy_return" | "product_search" | None
    full_label: str               # "informational/policy_return" | "greeting"
    confidence: float             # cosine similarity al centroide ganador [0, 1]
    inference_time_ms: float
    method: str = "miniml_semantic"


# ================================================================
# CLASIFICADOR
# ================================================================

class MiniLMIntentClassifier:
    """
    Clasificador semantico de intents basado en sentence embeddings.

    ESTRATEGIA: prototype-based classification (zero-shot)
      1. Precomputa centroides (embeddings promedio) por sub-intent
      2. En inferencia: embed query -> cosine similarity vs centroides
      3. Gana el label con mayor similitud

    PATRON DE CARGA: identico a intent_classifier.py (lazy load).
      - __init__: NO carga el modelo (preserva startup time)
      - load(): descarga y carga el modelo en la primera llamada real
      - is_loaded(): permite verificar estado antes de predecir

    GRACEFUL DEGRADATION:
      Si sentence-transformers no esta instalado, load() retorna False
      y el hybrid_detector continua con el resultado de sklearn.
      El sistema NUNCA falla por causa de esta capa.
    """

    # Modelo: 22M params, 384-dim embeddings, 200+ idiomas
    # Benchmark SBERT: mejor accuracy/speed para multilingual classification
    MODEL_NAME = "paraphrase-multilingual-MiniLM-L6-v2"

    def __init__(self, model_cache_dir: Optional[Path] = None):
        """
        Inicializa el clasificador SIN cargar el modelo.

        Args:
            model_cache_dir: Directorio de cache para el modelo.
                             None -> usa cache por defecto de HuggingFace.
                             En Docker: pasar Path dentro de la imagen para
                             evitar descargas en runtime (ver Dockerfile.cloudrun).
        """
        self._model_cache_dir = model_cache_dir
        self._model = None                               # SentenceTransformer (lazy)
        self._centroids: Dict[str, np.ndarray] = {}     # label -> centroid (384-dim)
        self._loaded = False
        self._load_attempted = False

    # -- Estado ----------------------------------------------------

    def is_loaded(self) -> bool:
        """True si el modelo esta cargado y listo para predecir."""
        return self._loaded

    # -- Carga del modelo ------------------------------------------

    def load(self) -> bool:
        """
        Carga el modelo SentenceTransformer y precomputa centroides.
        Llamado lazy por HybridIntentDetector en la primera query de capa 3.

        Returns:
            True si cargo correctamente, False si fallo (degradacion graceful).
        """
        # Evitar reintentos si ya se intento y fallo
        if self._load_attempted:
            return self._loaded

        self._load_attempted = True
        t0 = time.time()

        try:
            # Import lazy: no impacta el startup de FastAPI.
            # Si sentence-transformers no esta instalado -> ImportError aqui.
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            cache_dir = str(self._model_cache_dir) if self._model_cache_dir else None
            logger.info(
                "miniml_loading model=%s cache_dir=%s",
                self.MODEL_NAME, cache_dir or "HF_default",
            )

            self._model = SentenceTransformer(
                self.MODEL_NAME,
                cache_folder=cache_dir,
            )

            # Precomputar centroides — cuesta ~2-3s en CPU, una sola vez.
            # Si el modelo ya estaba en cache local, este paso es el mas costoso.
            self._build_centroids()

            load_ms = (time.time() - t0) * 1000
            logger.info(
                "miniml_ready model=%s load_ms=%.0f n_labels=%d",
                self.MODEL_NAME, load_ms, len(self._centroids),
            )
            self._loaded = True
            return True

        except ImportError:
            # sentence-transformers no esta en el entorno
            logger.warning(
                "miniml_unavailable: sentence-transformers not installed. "
                "Add 'sentence-transformers>=3.0.0' to requirements.cloudrun.txt "
                "to enable layer-3 semantic classification."
            )
            return False

        except Exception as exc:
            logger.error(
                "miniml_load_failed model=%s error=%s",
                self.MODEL_NAME, str(exc), exc_info=True,
            )
            return False

    # -- Construccion de centroides --------------------------------

    def _build_centroids(self) -> None:
        """
        Precomputa el centroide de embedding para cada label.

        Proceso por label:
          1. Encode todas las queries prototipicas (normalize=True)
          2. Calcular el vector promedio -> centroide raw
          3. Re-normalizar el centroide

        Por que re-normalizar el centroide:
          Con normalize_embeddings=True, cada query tiene norma=1.
          El promedio de vectores unitarios NO es unitario (norma <= 1).
          Re-normalizar garantiza que:
            dot(query_emb, centroid) == cosine_similarity exactamente.
          Sin re-normalizar habria un sesgo sistematico que subestimaria
          la similitud, especialmente para labels con alta varianza.
        """
        logger.info(
            "miniml_building_centroids n_labels=%d", len(PROTOTYPE_EXAMPLES)
        )

        for label, examples in PROTOTYPE_EXAMPLES.items():
            # encode() retorna ndarray shape (N, 384)
            embeddings = self._model.encode(
                examples,
                normalize_embeddings=True,   # cada vector tiene norma 1
                show_progress_bar=False,
                batch_size=32,
            )

            # Centroide: promedio de N embeddings normalizados
            centroid = embeddings.mean(axis=0)  # shape (384,)

            # Re-normalizar para mantener la metrica cosine
            norm = np.linalg.norm(centroid)
            if norm > 0.0:
                centroid = centroid / norm

            self._centroids[label] = centroid

        logger.info(
            "miniml_centroids_ready labels=%s",
            list(self._centroids.keys()),
        )

    # -- Prediccion ------------------------------------------------

    def predict(self, query: str) -> Optional[MiniLMPrediction]:
        """
        Clasifica el query semanticamente contra los centroides.

        Flujo:
          1. Embed el query (normalize=True)
          2. dot(query_emb, centroid) = cosine_similarity para cada label
          3. Retornar el label con mayor similitud

        Rango de cosine similarity para texto: tipicamente [0.2, 0.95].
        Un valor >= 0.50 indica match semantico razonable.
        Un valor >= 0.70 indica match semantico fuerte.

        Args:
            query: Texto del usuario, cualquier idioma, con o sin acentos.

        Returns:
            MiniLMPrediction o None si el modelo no esta cargado o falla.
        """
        if not self._loaded or self._model is None:
            return None

        t0 = time.time()

        try:
            # Embed el query — shape (1, 384) -> [0] para (384,)
            query_emb: np.ndarray = self._model.encode(
                [query],
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0]

            # Cosine similarity = dot product (ambos normalizados)
            best_label: Optional[str] = None
            best_sim: float = -1.0
            second_sim: float = -1.0  # para loguear el margen de separacion

            for label, centroid in self._centroids.items():
                sim = float(np.dot(query_emb, centroid))
                if sim > best_sim:
                    second_sim = best_sim
                    best_sim = sim
                    best_label = label
                elif sim > second_sim:
                    second_sim = sim

            inference_ms = (time.time() - t0) * 1000

            if best_label is None:
                return None

            # Parsear "informational/policy_return" -> primary + sub
            # "greeting" -> primary="greeting", sub=None
            parts = best_label.split("/", 1)
            primary = parts[0]
            sub: Optional[str] = parts[1] if len(parts) > 1 else None

            # Clamp a [0, 1] — cosine puede ser negativo pero en la practica
            # el label ganador siempre tiene similitud positiva para texto
            confidence = max(0.0, min(1.0, best_sim))

            # Log con margen de separacion: util para detectar queries ambiguas
            # donde el segundo candidato esta muy cerca del ganador
            logger.info(
                "miniml_predict query='%s' label=%s sim=%.3f "
                "second_sim=%.3f margin=%.3f time_ms=%.1f",
                query[:60], best_label, best_sim,
                second_sim, best_sim - second_sim, inference_ms,
            )

            return MiniLMPrediction(
                primary_intent=primary,
                sub_intent=sub,
                full_label=best_label,
                confidence=confidence,
                inference_time_ms=inference_ms,
            )

        except Exception as exc:
            logger.error(
                "miniml_predict_failed query='%s' error=%s",
                query[:60], str(exc), exc_info=True,
            )
            return None

    # -- Utilidades de debugging -----------------------------------

    def get_similarity_ranking(
        self, query: str, top_k: int = 5
    ) -> List[tuple]:
        """
        Retorna los top_k labels con mayor similitud para un query.
        Util para debugging: entender por que un query fue clasificado
        de cierta manera y si hay competencia entre labels.

        Returns:
            [(label, similarity), ...] ordenados por similitud desc.
        """
        if not self._loaded or self._model is None:
            return []

        try:
            query_emb = self._model.encode(
                [query], normalize_embeddings=True, show_progress_bar=False
            )[0]
            sims = [
                (label, float(np.dot(query_emb, centroid)))
                for label, centroid in self._centroids.items()
            ]
            sims.sort(key=lambda x: x[1], reverse=True)
            return sims[:top_k]
        except Exception:
            return []

    def get_prototype_count(self) -> Dict[str, int]:
        """Retorna el numero de ejemplos prototipicos por label."""
        return {
            label: len(examples)
            for label, examples in PROTOTYPE_EXAMPLES.items()
        }


# ================================================================
# SINGLETON
# ================================================================

_global_miniml_classifier: Optional[MiniLMIntentClassifier] = None


def get_miniml_classifier(
    model_cache_dir: Optional[Path] = None,
) -> MiniLMIntentClassifier:
    """
    Retorna la instancia global del clasificador MiniLM (singleton).

    Patron identico a get_intent_detector() y get_ml_classifier().
    La primera llamada crea la instancia SIN cargar el modelo.
    El modelo se carga la primera vez que HybridIntentDetector
    llama a _ensure_miniml_loaded() -> miniml_classifier.load().
    """
    global _global_miniml_classifier
    if _global_miniml_classifier is None:
        _global_miniml_classifier = MiniLMIntentClassifier(
            model_cache_dir=model_cache_dir
        )
    return _global_miniml_classifier
