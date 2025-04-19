"""
Configuración centralizada para el sistema de recomendaciones.

Este módulo proporciona una configuración centralizada basada en Pydantic
que lee variables de entorno y proporciona valores por defecto cuando es necesario.
"""

import os
from pydantic import BaseSettings, Field
from typing import Dict, Any, Optional, List
from functools import lru_cache

class RecommenderSettings(BaseSettings):
    # Configuración general
    app_name: str = "Retail Recommender API"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, env="DEBUG")
    
    # Configuración de Google Cloud
    google_project_number: str = Field(..., env="GOOGLE_PROJECT_NUMBER")
    google_location: str = Field(default="global", env="GOOGLE_LOCATION")
    google_catalog: str = Field(default="default_catalog", env="GOOGLE_CATALOG")
    google_serving_config: str = Field(
        default="default_recommendation_config", 
        env="GOOGLE_SERVING_CONFIG"
    )
    use_gcs_import: bool = Field(default=True, env="USE_GCS_IMPORT")
    gcs_bucket_name: Optional[str] = Field(default=None, env="GCS_BUCKET_NAME")
    
    # Configuración de Shopify
    shopify_shop_url: Optional[str] = Field(default=None, env="SHOPIFY_SHOP_URL")
    shopify_access_token: Optional[str] = Field(default=None, env="SHOPIFY_ACCESS_TOKEN")
    
    # Configuración de seguridad
    api_key: str = Field(..., env="API_KEY")
    
    # Configuración de recomendadores
    content_weight: float = Field(default=0.5, env="CONTENT_WEIGHT")
    
    # Características activables
    use_metrics: bool = Field(default=True, env="METRICS_ENABLED")
    exclude_seen_products: bool = Field(default=True, env="EXCLUDE_SEEN_PRODUCTS")
    validate_products: bool = Field(default=True, env="VALIDATE_PRODUCTS")
    use_fallback: bool = Field(default=True, env="USE_FALLBACK")
    
    # Configuración de moneda
    default_currency: str = Field(default="COP", env="DEFAULT_CURRENCY")
    
    # Configuración de inicialización
    startup_timeout: float = Field(default=300.0, env="STARTUP_TIMEOUT")
    
    # Configuración de cachés
    use_redis_cache: bool = Field(default=False, env="USE_REDIS_CACHE")
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")
    cache_ttl: int = Field(default=3600, env="CACHE_TTL")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> RecommenderSettings:
    """Obtiene la configuración con caché para evitar lecturas repetidas."""
    return RecommenderSettings()
