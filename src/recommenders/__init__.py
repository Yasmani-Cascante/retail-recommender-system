"""
Módulo de recomendadores para el sistema de recomendaciones de retail.

Este módulo expone las clases principales de recomendadores que pueden
ser utilizadas por otros componentes del sistema.
"""

# Importar recomendadores esenciales
from .tfidf_recommender import TFIDFRecommender
from .retail_api import RetailAPIRecommender

# Importaciones opcionales en bloques try/except separados
try:
    from .hybrid import HybridRecommender
    __all__ = ['TFIDFRecommender', 'RetailAPIRecommender', 'HybridRecommender']
except ImportError:
    __all__ = ['TFIDFRecommender', 'RetailAPIRecommender']

# Importar mejoras si están disponibles
try:
    from .improved_fallback_exclude_seen import ImprovedFallbackStrategies
    __all__.append('ImprovedFallbackStrategies')
except ImportError:
    pass

# Intentar importar ContentBasedRecommender solo si se requiere
try:
    from .content_based import ContentBasedRecommender
    __all__.append('ContentBasedRecommender')
except ImportError:
    pass

try:
    from .collaborative import CollaborativeRecommender
    __all__.append('CollaborativeRecommender')
except ImportError:
    pass
