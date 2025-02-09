from src.recommenders.content_based import ContentBasedRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from src.recommenders.hybrid import HybridRecommender
import os

# Configuración de Google Cloud Retail API
GOOGLE_PROJECT_NUMBER = os.getenv("GOOGLE_PROJECT_NUMBER")
GOOGLE_LOCATION = os.getenv("GOOGLE_LOCATION", "global")
GOOGLE_CATALOG = os.getenv("GOOGLE_CATALOG", "default_catalog")
GOOGLE_SERVING_CONFIG = os.getenv("GOOGLE_SERVING_CONFIG", "default_config")

# Instanciar recomendadores
content_recommender = ContentBasedRecommender()
retail_recommender = RetailAPIRecommender(
    project_number=GOOGLE_PROJECT_NUMBER,
    location=GOOGLE_LOCATION,
    catalog=GOOGLE_CATALOG,
    serving_config_id=GOOGLE_SERVING_CONFIG
)
hybrid_recommender = HybridRecommender(
    content_recommender=content_recommender,
    retail_recommender=retail_recommender,
    content_weight=0.5
)