from src.recommenders.content_based import ContentBasedRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from src.recommenders.hybrid import HybridRecommender
import os

# Configuración de Google Cloud Retail API
GOOGLE_PROJECT_NUMBER = os.getenv("GOOGLE_PROJECT_NUMBER")
GOOGLE_LOCATION = os.getenv("GOOGLE_LOCATION", "global")
GOOGLE_CATALOG = os.getenv("GOOGLE_CATALOG", "default_catalog")

# Limpiar y validar GOOGLE_SERVING_CONFIG
GOOGLE_SERVING_CONFIG = os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
# Si parece ser una ruta de archivo, ignorarlo y usar el valor predeterminado
if GOOGLE_SERVING_CONFIG and ('/' in GOOGLE_SERVING_CONFIG or '\\' in GOOGLE_SERVING_CONFIG or GOOGLE_SERVING_CONFIG.endswith('.json')):
    print(f"⚠️ Detectado valor incorrecto para GOOGLE_SERVING_CONFIG: {GOOGLE_SERVING_CONFIG}")
    print("⚠️ Usando valor predeterminado 'default_recommendation_config' en su lugar")
    GOOGLE_SERVING_CONFIG = "default_recommendation_config"

print(f"ℹ️ Usando configuración: Project={GOOGLE_PROJECT_NUMBER}, Location={GOOGLE_LOCATION}, Catalog={GOOGLE_CATALOG}, ServingConfig={GOOGLE_SERVING_CONFIG}")

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