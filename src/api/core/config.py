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
    debug: bool = Field(default=False)
    
    # Configuración de Google Cloud
    google_project_number: str
    google_location: str = Field(default="global")
    google_catalog: str = Field(default="default_catalog")
    google_serving_config: str = Field(
        default="default_recommendation_config"
    )
    use_gcs_import: bool = Field(default=True)
    gcs_bucket_name: Optional[str] = Field(default=None)
    
    # Configuración de Shopify
    shopify_shop_url: Optional[str] = Field(default=None)
    shopify_access_token: Optional[str] = Field(default=None)
    
    # Configuración de seguridad
    api_key: str
    
    # Configuración de recomendadores
    content_weight: float = Field(default=0.5)
    
    # Características activables
    use_metrics: bool = Field(default=True)
    exclude_seen_products: bool = Field(default=True)
    validate_products: bool = Field(default=True)
    use_fallback: bool = Field(default=True)
    
    # Configuración de moneda
    default_currency: str = Field(default="COP")
    
    # Configuración de inicialización
    startup_timeout: float = Field(default=300.0)
    
    # Configuración de cachés
    use_redis_cache: bool = Field(default=False)
    redis_url: Optional[str] = Field(default=None)
    cache_ttl: int = Field(default=3600)
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_prefix="",
        extra="ignore",
        env_nested_delimiter="_"
    )

@lru_cache()
def get_settings() -> RecommenderSettings:
    """Obtiene la configuración con caché para evitar lecturas repetidas."""
    return RecommenderSettings()

# Función para pruebas que evita el cache
def get_test_settings() -> RecommenderSettings:
    """Obtiene la configuración sin cache para pruebas."""
    return RecommenderSettings()
