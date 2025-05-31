"""
Configuración centralizada para el sistema de recomendaciones.

Este módulo proporciona una configuración centralizada utilizando Pydantic
para validar y cargar variables de entorno.
"""

import os
from typing import Optional
from pydantic import Field
from functools import lru_cache

# CORRECCIÓN: Importar BaseSettings desde el paquete correcto para Pydantic v2
try:
    from pydantic_settings import BaseSettings
    PYDANTIC_SETTINGS_AVAILABLE = True
except ImportError:
    try:
        # Fallback para versiones antiguas de Pydantic
        from pydantic import BaseSettings
        PYDANTIC_SETTINGS_AVAILABLE = False
        print("⚠️ Usando pydantic.BaseSettings (versión antigua). Considera actualizar: pip install pydantic-settings")
    except ImportError:
        raise ImportError(
            "No se pudo importar BaseSettings. "
            "Para Pydantic v2, instala: pip install pydantic-settings"
        )

class RecommenderSettings(BaseSettings):
    """Configuración centralizada para el sistema de recomendaciones."""
    
    # Configuración general
    app_name: str = "Retail Recommender API"
    app_version: str = "0.5.0"
    debug: bool = Field(default=False, env="DEBUG")
    
    # Configuración de Google Cloud
    google_project_number: str = Field(default="178362262166", env="GOOGLE_PROJECT_NUMBER")
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
    api_key: Optional[str] = Field(default=None, env="API_KEY")
    
    # Configuración de recomendadores
    content_weight: float = Field(default=0.5, env="CONTENT_WEIGHT")
    
    # Características activables
    metrics_enabled: bool = Field(default=True, env="METRICS_ENABLED")
    exclude_seen_products: bool = Field(default=True, env="EXCLUDE_SEEN_PRODUCTS")
    validate_products: bool = Field(default=True, env="VALIDATE_PRODUCTS")
    use_fallback: bool = Field(default=True, env="USE_FALLBACK")
    
    # Configuración de moneda
    default_currency: str = Field(default="COP", env="DEFAULT_CURRENCY")
    
    # Configuración de inicialización
    startup_timeout: float = Field(default=300.0, env="STARTUP_TIMEOUT")
    
    # Configuración de Redis Cache
    use_redis_cache: bool = Field(default=False, env="USE_REDIS_CACHE")
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db: int = Field(default=0, env="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_username: Optional[str] = Field(default=None, env="REDIS_USERNAME")
    redis_ssl: bool = Field(default=False, env="REDIS_SSL")
    cache_ttl: int = Field(default=3600, env="CACHE_TTL")  # 1 hora por defecto
    cache_prefix: str = Field(default="product:", env="CACHE_PREFIX")
    cache_enable_background_tasks: bool = Field(default=True, env="CACHE_ENABLE_BACKGROUND_TASKS")
    
    # Configuración para diferentes versiones de Pydantic
    if PYDANTIC_SETTINGS_AVAILABLE:
        # Pydantic v2 con pydantic-settings
        model_config = {
            "env_file": ".env",
            "case_sensitive": False,
            "extra": "ignore"
        }
    else:
        # Pydantic v1 o versiones anteriores
        class Config:
            env_file = ".env"
            case_sensitive = False

@lru_cache()
def get_settings() -> RecommenderSettings:
    """Obtiene la configuración con caché para evitar lecturas repetidas."""
    return RecommenderSettings()

# Función para pruebas que evita el cache y archivos .env
def get_test_settings() -> RecommenderSettings:
    """Obtiene la configuración sin cache para pruebas."""
    # Para pruebas, utilizamos una configuración limpia sin leer de .env
    if PYDANTIC_SETTINGS_AVAILABLE:
        # Pydantic v2 con pydantic-settings
        class TestRecommenderSettings(RecommenderSettings):
            model_config = {
                "env_file": None,  # No usar archivo .env
                "case_sensitive": False,
                "extra": "ignore"
            }
    else:
        # Pydantic v1 o versiones anteriores
        class TestRecommenderSettings(RecommenderSettings):
            class Config:
                env_file = None  # No usar archivo .env
                case_sensitive = False
    
    return TestRecommenderSettings()
