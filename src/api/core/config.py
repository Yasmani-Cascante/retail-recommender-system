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
    tfidf_model_path: str = Field(default="data/tfidf_model.pkl", env="TFIDF_MODEL_PATH")
    
    # Características activables
    metrics_enabled: bool = Field(default=True, env="METRICS_ENABLED")
    exclude_seen_products: bool = Field(default=True, env="EXCLUDE_SEEN_PRODUCTS")
    validate_products: bool = Field(default=True, env="VALIDATE_PRODUCTS")
    use_fallback: bool = Field(default=True, env="USE_FALLBACK")
    use_unified_architecture: bool = Field(default=True, env="USE_UNIFIED_ARCHITECTURE")
    use_transformers: bool = Field(default=False, env="USE_TRANSFORMERS")
    
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
    
    # === CLAUDE/ANTHROPIC CONFIGURATION ===
    # Configuración centralizada para Claude AI
    claude_model_tier: str = Field(default="SONNET", env="CLAUDE_MODEL_TIER")
    claude_region: str = Field(default="global", env="CLAUDE_REGION")
    claude_enable_ab_testing: bool = Field(default=False, env="CLAUDE_ENABLE_AB_TESTING")
    claude_ab_group: str = Field(default="default", env="CLAUDE_AB_GROUP")
    claude_timeout: float = Field(default=30.0, env="CLAUDE_TIMEOUT")
    claude_max_retries: int = Field(default=3, env="CLAUDE_MAX_RETRIES")
    
    # Claude API credentials
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    
    # Claude model overrides (optional)
    claude_max_tokens: Optional[int] = Field(default=None, env="CLAUDE_MAX_TOKENS")
    claude_temperature: Optional[float] = Field(default=None, env="CLAUDE_TEMPERATURE")
    claude_top_p: Optional[float] = Field(default=None, env="CLAUDE_TOP_P")
    
    # MCP Bridge Settings
    mcp_bridge_host: str = "localhost"
    mcp_bridge_port: int = 3001
    
    # MCP Circuit Breaker
    mcp_circuit_breaker_threshold: int = 3
    mcp_circuit_breaker_timeout: int = 30
    
    # MCP Caching
    mcp_local_cache_enabled: bool = True
    mcp_cache_ttl: int = 300
    
    # ═══════════════════════════════════════════════════════════════
    # INTENT DETECTION CONFIGURATION
    # ═══════════════════════════════════════════════════════════════
    
    # Enable/disable intent detection system
    enable_intent_detection: bool = Field(default=False, env="ENABLE_INTENT_DETECTION")
    
    # Minimum confidence threshold for intent classification
    # Queries below this threshold fall back to transactional (products)
    intent_confidence_threshold: float = Field(default=0.7, env="INTENT_CONFIDENCE_THRESHOLD")
    
    # Enable logging of intent detection for debugging/monitoring
    intent_detection_logging: bool = Field(default=True, env="INTENT_DETECTION_LOGGING")
    
    # Enable metrics collection for intent detection
    intent_detection_metrics: bool = Field(default=True, env="INTENT_DETECTION_METRICS")


    # ============================================================================
    # ML INTENT DETECTION CONFIGURATION
    # ============================================================================
    
    # Enable/disable ML-based intent detection (hybrid with rule-based)
    ml_intent_enabled: bool = Field(
        default=False, 
        env="ML_INTENT_ENABLED",
        description="Enable ML-based intent detection (sklearn integrated)"
    )
    
    # Confidence threshold for rule-based to trigger ML fallback
    # If rule-based confidence < threshold → use ML
    # Higher = more queries go to ML (slower but more accurate)
    # Lower = more queries stay in rule-based (faster but less accurate for edge cases)
    ml_confidence_threshold: float = Field(
        default=0.8,
        env="ML_CONFIDENCE_THRESHOLD",
        ge=0.0,
        le=1.0,
        description="Threshold for ML fallback (0.0-1.0)"
    )
    
    # Path to ML model directory (relative to project root)
    ml_model_path: str = Field(
        default="models/intent_classifier",
        env="ML_MODEL_PATH",
        description="Path to ML model directory"
    )

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
