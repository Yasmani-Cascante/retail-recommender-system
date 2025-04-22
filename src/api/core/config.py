"""
Configuración centralizada para el sistema de recomendaciones.

Este módulo proporciona una configuración centralizada basada en Pydantic
que lee variables de entorno y proporciona valores por defecto cuando es necesario.
"""

import os
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings
from typing import Dict, Any, Optional, List
from functools import lru_cache

class RecommenderSettings(BaseSettings):
    # Configuración general
    app_name: str = "Retail Recommender API"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, json_schema_extra={"env": "DEBUG"})
    
    # Configuración de Google Cloud
    google_project_number: str = Field(json_schema_extra={"env": "GOOGLE_PROJECT_NUMBER"})
    google_location: str = Field(default="global", json_schema_extra={"env": "GOOGLE_LOCATION"})
    google_catalog: str = Field(default="default_catalog", json_schema_extra={"env": "GOOGLE_CATALOG"})
    google_serving_config: str = Field(
        default="default_recommendation_config",
        json_schema_extra={"env": "GOOGLE_SERVING_CONFIG"}
    )
    use_gcs_import: bool = Field(default=True, json_schema_extra={"env": "USE_GCS_IMPORT"})
    gcs_bucket_name: Optional[str] = Field(default=None, json_schema_extra={"env": "GCS_BUCKET_NAME"})
    
    # Configuración de Shopify
    shopify_shop_url: Optional[str] = Field(default=None, json_schema_extra={"env": "SHOPIFY_SHOP_URL"})
    shopify_access_token: Optional[str] = Field(default=None, json_schema_extra={"env": "SHOPIFY_ACCESS_TOKEN"})
    
    # Configuración de seguridad
    api_key: str = Field(json_schema_extra={"env": "API_KEY"})
    
    # Configuración de recomendadores
    content_weight: float = Field(default=0.5, json_schema_extra={"env": "CONTENT_WEIGHT"})
    
    # Características activables
    use_metrics: bool = Field(default=True, json_schema_extra={"env": "METRICS_ENABLED"})
    exclude_seen_products: bool = Field(default=True, json_schema_extra={"env": "EXCLUDE_SEEN_PRODUCTS"})
    validate_products: bool = Field(default=True, json_schema_extra={"env": "VALIDATE_PRODUCTS"})
    use_fallback: bool = Field(default=True, json_schema_extra={"env": "USE_FALLBACK"})
    
    # Configuración de moneda
    default_currency: str = Field(default="COP", json_schema_extra={"env": "DEFAULT_CURRENCY"})
    
    # Configuración de inicialización
    startup_timeout: float = Field(default=300.0, json_schema_extra={"env": "STARTUP_TIMEOUT"})
    
    # Configuración de cachés
    use_redis_cache: bool = Field(default=False, json_schema_extra={"env": "USE_REDIS_CACHE"})
    redis_url: Optional[str] = Field(default=None, json_schema_extra={"env": "REDIS_URL"})
    cache_ttl: int = Field(default=3600, json_schema_extra={"env": "CACHE_TTL"})
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False
    )

@lru_cache()
def get_settings() -> RecommenderSettings:
    """Obtiene la configuración con caché para evitar lecturas repetidas."""
    return RecommenderSettings()
