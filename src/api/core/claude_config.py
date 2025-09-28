# src/api/core/claude_config.py
"""
Configuración centralizada para integración Claude/Anthropic
==========================================================

Sistema de configuración centralizada que:
- Elimina hardcoding de modelos
- Facilita A/B testing futuro
- Prepara para microservicios (Fase 3)
- Permite configuración por entorno
- Soporta múltiples estrategias de modelo

Author: CTO Technical Team
Version: 1.0.0
Last Updated: 2025-07-25
"""

import os
import logging
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)


class ClaudeModelTier(str, Enum):
    """Tiers de modelos Claude disponibles"""
    HAIKU = "claude-3-haiku-20240307"          # Rápido, económico
    SONNET = "claude-sonnet-4-20250514"       # Balanceado (RECOMENDADO)
    OPUS = "claude-3-opus-20240229"           # Máximo rendimiento
    
    @classmethod
    def get_valid_tier_names(cls) -> List[str]:
        """Obtiene lista de nombres de tier válidos"""
        return [tier.name for tier in cls]
    
    @classmethod
    def from_string(cls, tier_string: str) -> 'ClaudeModelTier':
        """Crea ClaudeModelTier desde string de manera segura"""
        tier_name = tier_string.upper()
        if hasattr(cls, tier_name):
            return getattr(cls, tier_name)
        raise ValueError(f"Invalid tier '{tier_string}'. Valid options: {', '.join(cls.get_valid_tier_names())}")
    
    @classmethod
    def get_available_models(cls) -> List[str]:
        """Retorna lista de modelos disponibles en el tier actual
        
        Nota: Esta implementación básica retorna todos los modelos
        del enum. Para verificación en tiempo real con Anthropic API,
        usar get_available_models_from_api()
        """
        return [tier.value for tier in cls]


class ClaudeRegion(str, Enum):
    """Regiones disponibles para Claude API"""
    US = "us"
    EU = "eu"
    GLOBAL = "global"


@dataclass
class ClaudeModelConfig:
    """Configuración específica por modelo Claude"""
    model_name: str
    max_tokens: int
    temperature: float
    top_p: float
    cost_per_1k_tokens: float
    context_window: int
    recommended_use: str
    
    def to_anthropic_params(self) -> Dict[str, Any]:
        """Convierte a parámetros para Anthropic API"""
        return {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p
        }


class ClaudeConfigurationService:
    """
    Servicio centralizado para configuración Claude
    
    Responsabilidades:
    - Gestionar configuración de modelos
    - Resolver configuración por entorno
    - Facilitar A/B testing futuro
    - Preparar para microservicios
    """
    
    # Configuraciones predefinidas por modelo
    MODEL_CONFIGS = {
        ClaudeModelTier.HAIKU: ClaudeModelConfig(
            model_name="claude-3-haiku-20240307",
            max_tokens=1000,
            temperature=0.7,
            top_p=0.9,
            cost_per_1k_tokens=0.50,
            context_window=200000,
            recommended_use="Respuestas rápidas, alta frecuencia"
        ),
        ClaudeModelTier.SONNET: ClaudeModelConfig(
            model_name="claude-sonnet-4-20250514",
            max_tokens=2000,
            temperature=0.7,
            top_p=0.9,
            cost_per_1k_tokens=3.00,
            context_window=200000,
            recommended_use="Uso general, recomendaciones personalizadas"
        ),
        ClaudeModelTier.OPUS: ClaudeModelConfig(
            model_name="claude-3-opus-20240229",  # ✅ CORREGIDO
            max_tokens=4000,
            temperature=0.7,
            top_p=0.9,
            cost_per_1k_tokens=15.00,
            context_window=200000,
            recommended_use="Análisis complejos, razonamiento avanzado"
        )
    }
    
    def __init__(self):
        """Inicializa el servicio con configuración del sistema"""
        self._resolved_config: Optional[ClaudeModelConfig] = None
        
        # Cargar configuración específica de Claude desde env
        self.claude_model_tier = self._resolve_model_tier()
        self.claude_region = self._resolve_region()
        self.enable_ab_testing = self._get_bool_env("CLAUDE_ENABLE_AB_TESTING", False)
        self.ab_testing_group = self._get_env("CLAUDE_AB_GROUP", "default")
        
        logger.info(f"🔧 Claude configuration initialized: model={self.claude_model_tier.value}, region={self.claude_region}")
    
    def _resolve_model_tier(self) -> ClaudeModelTier:
        """Resuelve el tier de modelo desde configuración"""
        # 1. Desde variable de entorno específica
        model_tier = self._get_env("CLAUDE_MODEL_TIER")
        if model_tier:
            try:
                # 🚀 CORRECCIÓN: Usar método helper seguro
                resolved_tier = ClaudeModelTier.from_string(model_tier)
                logger.info(f"✅ Resolved CLAUDE_MODEL_TIER '{model_tier}' to {resolved_tier.value}")
                return resolved_tier
            except ValueError as e:
                logger.warning(f"Error resolving CLAUDE_MODEL_TIER: {e}")
        
        # 2. Desde CLAUDE_MODEL (backward compatibility)
        model_name = self._get_env("CLAUDE_MODEL")
        if model_name:
            for tier, config in self.MODEL_CONFIGS.items():
                if config.model_name == model_name:
                    logger.info(f"✅ Resolved CLAUDE_MODEL {model_name} to tier {tier.name}")
                    return tier
            logger.warning(f"Unknown CLAUDE_MODEL: {model_name}")
        
        # 3. Desde configuración por entorno
        env = self._get_env("ENVIRONMENT", "development").lower()
        if env in ["production", "prod"]:
            logger.info("🏭 Production environment detected: using SONNET tier")
            return ClaudeModelTier.SONNET  # Balanceado para producción
        elif env in ["staging", "test"]:
            logger.info("🧪 Test environment detected: using HAIKU tier")
            return ClaudeModelTier.HAIKU   # Económico para testing
        else:
            logger.info("🔧 Development environment: using SONNET tier")
            return ClaudeModelTier.SONNET  # Default
    
    def _resolve_region(self) -> ClaudeRegion:
        """Resuelve la región desde configuración"""
        region = self._get_env("CLAUDE_REGION", "global").lower()
        try:
            return ClaudeRegion(region)
        except ValueError:
            logger.warning(f"Invalid CLAUDE_REGION: {region}, using global")
            return ClaudeRegion.GLOBAL
    
    def _get_env(self, key: str, default: str = None) -> Optional[str]:
        """Helper para obtener variables de entorno"""
        return os.getenv(key, default)
    
    def _get_bool_env(self, key: str, default: bool = False) -> bool:
        """Helper para obtener variables booleanas"""
        value = os.getenv(key, str(default)).lower()
        return value in ["true", "1", "yes", "on"]
    
    def get_model_config(self, context: Optional[Dict[str, Any]] = None) -> ClaudeModelConfig:
        """
        Obtiene configuración de modelo resolviendo contexto
        
        Args:
            context: Contexto opcional para resolución dinámica
                   (usado para A/B testing futuro)
        
        Returns:
            Configuración de modelo Claude
        """
        if self._resolved_config:
            return self._resolved_config
        
        # Resolver tier de modelo
        tier = self._resolve_model_tier_with_context(context)
        base_config = self.MODEL_CONFIGS[tier]
        
        # Aplicar overrides desde entorno si existen
        base_config = self._apply_environment_overrides(base_config)
        
        # Cache para performance
        self._resolved_config = base_config
        return base_config
    
    def _resolve_model_tier_with_context(self, context: Optional[Dict[str, Any]] = None) -> ClaudeModelTier:
        """Resuelve tier considerando contexto (A/B testing futuro)"""
        if not self.enable_ab_testing or not context:
            return self.claude_model_tier
        
        # A/B Testing logic (para implementación futura)
        user_id = context.get("user_id")
        market_id = context.get("market_id", "default")
        
        # Ejemplo de lógica A/B (simplificada)
        if self.ab_testing_group == "premium" and market_id in ["US", "ES"]:
            logger.info(f"🎯 A/B Testing: Using OPUS for premium user {user_id} in {market_id}")
            return ClaudeModelTier.OPUS
        elif self.ab_testing_group == "economy":
            logger.info(f"💰 A/B Testing: Using HAIKU for economy group")
            return ClaudeModelTier.HAIKU
        
        return self.claude_model_tier
    
    def _apply_environment_overrides(self, config: ClaudeModelConfig) -> ClaudeModelConfig:
        """Aplica overrides específicos desde variables de entorno"""
        # Crear copia para no mutar el original
        new_config = ClaudeModelConfig(
            model_name=config.model_name,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            cost_per_1k_tokens=config.cost_per_1k_tokens,
            context_window=config.context_window,
            recommended_use=config.recommended_use
        )
        
        # Override max_tokens
        max_tokens = self._get_env("CLAUDE_MAX_TOKENS")
        if max_tokens:
            try:
                new_config.max_tokens = int(max_tokens)
                logger.info(f"⚙️ Override CLAUDE_MAX_TOKENS: {max_tokens}")
            except ValueError:
                logger.warning(f"Invalid CLAUDE_MAX_TOKENS: {max_tokens}")
        
        # Override temperature
        temperature = self._get_env("CLAUDE_TEMPERATURE")
        if temperature:
            try:
                new_config.temperature = float(temperature)
                logger.info(f"⚙️ Override CLAUDE_TEMPERATURE: {temperature}")
            except ValueError:
                logger.warning(f"Invalid CLAUDE_TEMPERATURE: {temperature}")
        
        return new_config
    
    def get_anthropic_client_params(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Obtiene parámetros listos para AsyncAnthropic client
        
        Args:
            context: Contexto para resolución dinámica
            
        Returns:
            Parámetros para crear/llamar AsyncAnthropic
        """
        config = self.get_model_config(context)
        
        return {
            "api_key": self._get_env("ANTHROPIC_API_KEY"),
            "model_params": config.to_anthropic_params(),
            "region": self.claude_region.value,
            "timeout": float(self._get_env("CLAUDE_TIMEOUT", "30")),
            "max_retries": int(self._get_env("CLAUDE_MAX_RETRIES", "3"))
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas de configuración para monitoring"""
        config = self.get_model_config()
        
        return {
            "model_tier": self.claude_model_tier.value,
            "model_name": config.model_name,
            "region": self.claude_region.value,
            "ab_testing_enabled": self.enable_ab_testing,
            "ab_testing_group": self.ab_testing_group,
            "estimated_cost_per_1k_tokens": config.cost_per_1k_tokens,
            "max_context_window": config.context_window,
            "configuration_source": "centralized"
        }
    
    # 🔧 PROPIEDADES FALTANTES - REPARACIÓN CRÍTICA
    @property
    def timeout(self) -> float:
        """Timeout para llamadas Claude API"""
        return float(self._get_env("CLAUDE_TIMEOUT", "30"))
    
    @property
    def max_retries(self) -> int:
        """Número máximo de reintentos para Claude API"""
        return int(self._get_env("CLAUDE_MAX_RETRIES", "3"))
    
    @property
    def region(self) -> str:
        """Región Claude API como string simple"""
        return self.claude_region.value
    
    # 🔧 MÉTODO FALTANTE PARA COMPATIBILIDAD
    def get_timeout_config(self) -> Dict[str, Any]:
        """Obtiene configuración de timeouts para componentes legacy"""
        return {
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "connection_timeout": self.timeout * 0.8,  # 80% del timeout total
            "read_timeout": self.timeout * 0.9  # 90% del timeout total
        }
    
    # 🔧 PROPIEDADES FALTANTES - REPARACIÓN CRÍTICA
    @property
    def timeout(self) -> float:
        """Timeout para llamadas Claude API"""
        return float(self._get_env("CLAUDE_TIMEOUT", "30"))
    
    @property
    def max_retries(self) -> int:
        """Número máximo de reintentos para Claude API"""
        return int(self._get_env("CLAUDE_MAX_RETRIES", "3"))
    
    @property
    def region(self) -> str:
        """Región Claude API como string simple"""
        return self.claude_region.value
    
    def validate_configuration(self) -> Dict[str, Any]:
        """Valida la configuración actual con validaciones extendidas"""
        issues = []
        warnings = []
        
        # Validar API key
        api_key = self._get_env("ANTHROPIC_API_KEY")
        if not api_key:
            issues.append("ANTHROPIC_API_KEY not configured")
        elif not api_key.startswith("sk-ant-"):
            warnings.append("ANTHROPIC_API_KEY format unusual")
        
        # Validar modelo
        try:
            config = self.get_model_config()
            if not config.model_name:
                issues.append("Claude model not properly resolved")
        except Exception as e:
            issues.append(f"Model configuration error: {str(e)}")
        
        # Validar timeout configuration
        try:
            timeout_val = self.timeout
            if timeout_val <= 0:
                issues.append("Invalid timeout value: must be > 0")
            elif timeout_val > 120:
                warnings.append(f"High timeout value: {timeout_val}s may impact user experience")
        except Exception as e:
            issues.append(f"Timeout configuration error: {str(e)}")
        
        # Validar max_retries
        try:
            retries = self.max_retries
            if retries < 0:
                issues.append("Invalid max_retries: must be >= 0")
            elif retries > 10:
                warnings.append(f"High retry count: {retries} may cause delays")
        except Exception as e:
            issues.append(f"Retry configuration error: {str(e)}")
        
        # Validar configuración por entorno
        env = self._get_env("ENVIRONMENT", "development")
        if env == "production" and self.claude_model_tier == ClaudeModelTier.OPUS:
            warnings.append("Using expensive OPUS model in production")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "config_summary": self.get_metrics()
        }


# Factory para crear el servicio
@lru_cache()
def get_claude_config_service() -> ClaudeConfigurationService:
    """Factory función para obtener instancia singleton del servicio"""
    return ClaudeConfigurationService()


# Convenience functions para backward compatibility
def get_claude_model() -> str:
    """Obtiene el nombre del modelo Claude actual"""
    service = get_claude_config_service()
    config = service.get_model_config()
    return config.model_name

def get_claude_params(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Obtiene parámetros para llamadas a Claude API"""
    service = get_claude_config_service()
    return service.get_anthropic_client_params(context)
