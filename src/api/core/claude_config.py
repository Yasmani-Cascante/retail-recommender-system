# src/api/core/claude_config.py
"""
Configuracion centralizada para integracion Claude/Anthropic
==========================================================

Sistema de configuracion centralizada que:
- Elimina hardcoding de modelos
- Facilita A/B testing futuro
- Prepara para microservicios (Fase 3)
- Permite configuracion por entorno
- Soporta multiples estrategias de modelo

Author: CTO Technical Team
Version: 1.1.0 - Fix lru_cache + _resolved_config + duplicate properties (21/03/2026)
Last Updated: 2025-07-25
"""

import os
import logging
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
# NOTE: lru_cache removido intencionalmente (fix 21/03/2026).
# lru_cache congela el resultado del PRIMER import: si CLAUDE_MODEL_TIER
# no esta disponible en ese momento (race condition en Cloud Run startup),
# el singleton queda con SONNET para toda la vida del contenedor,
# incluso si el secret llega correctamente 50ms despues.
# Se usa un singleton manual con reset_claude_config_service() para tests
# y para poder recargar la config en caliente si fuera necesario.

logger = logging.getLogger(__name__)


class ClaudeModelTier(str, Enum):
    """Tiers de modelos Claude disponibles"""
    HAIKU  = "claude-3-haiku-20240307"    # Rapido, economico
    SONNET = "claude-sonnet-4-20250514"   # Balanceado (RECOMENDADO)
    OPUS   = "claude-3-opus-20240229"     # Maximo rendimiento

    @classmethod
    def get_valid_tier_names(cls) -> List[str]:
        """Obtiene lista de nombres de tier validos"""
        return [tier.name for tier in cls]

    @classmethod
    def from_string(cls, tier_string: str) -> "ClaudeModelTier":
        """Crea ClaudeModelTier desde string de manera segura"""
        tier_name = tier_string.upper()
        if hasattr(cls, tier_name):
            return getattr(cls, tier_name)
        raise ValueError(
            f"Invalid tier '{tier_string}'. "
            f"Valid options: {', '.join(cls.get_valid_tier_names())}"
        )

    @classmethod
    def get_available_models(cls) -> List[str]:
        """Retorna lista de modelos disponibles"""
        return [tier.value for tier in cls]


class ClaudeRegion(str, Enum):
    """Regiones disponibles para Claude API"""
    US     = "us"
    EU     = "eu"
    GLOBAL = "global"


@dataclass
class ClaudeModelConfig:
    """Configuracion especifica por modelo Claude"""
    model_name: str
    max_tokens: int
    temperature: float
    top_p: float
    cost_per_1k_tokens: float
    context_window: int
    recommended_use: str

    def to_anthropic_params(self) -> Dict[str, Any]:
        """Convierte a parametros para Anthropic API"""
        return {
            "model":       self.model_name,
            "max_tokens":  self.max_tokens,
            "temperature": self.temperature,
            "top_p":       self.top_p,
        }


class ClaudeConfigurationService:
    """
    Servicio centralizado para configuracion Claude.

    Responsabilidades:
    - Gestionar configuracion de modelos
    - Resolver configuracion por entorno
    - Facilitar A/B testing futuro
    - Preparar para microservicios
    """

    # ------------------------------------------------------------------
    # max_tokens CALIBRACION (20/03/2026)
    # ------------------------------------------------------------------
    # PROBLEMA original: Con max_tokens=2000 (Sonnet) / 1000 (Haiku),
    # Claude generaba cientos de tokens por respuesta.
    # A ~30-50 tokens/s en Sonnet, max_tokens=2000 => 40-65s de generacion.
    # Ningun timeout puede ganar contra eso.
    #
    # CONTEXTO DE USO: generate_personalized_response produce una
    # respuesta conversacional de recomendacion de moda. Una respuesta
    # util y natural necesita ~150-300 tokens (2-4 oraciones).
    # No es un documento ni un analisis: es una respuesta de chat.
    #
    # VALORES ACTUALES:
    #   HAIKU:  300 tokens -- suficiente para respuesta conversacional breve
    #   SONNET: 500 tokens -- permite respuesta mas rica pero acotada
    #   OPUS:   800 tokens -- para analisis (no usado en produccion actualmente)
    # ------------------------------------------------------------------
    MODEL_CONFIGS: Dict["ClaudeModelTier", ClaudeModelConfig] = {
        ClaudeModelTier.HAIKU: ClaudeModelConfig(
            model_name="claude-3-haiku-20240307",
            max_tokens=300,          # reducido de 1000: respuesta conversacional breve
            temperature=0.7,
            top_p=0.9,
            cost_per_1k_tokens=0.50,
            context_window=200_000,
            recommended_use="Respuestas rapidas, alta frecuencia",
        ),
        ClaudeModelTier.SONNET: ClaudeModelConfig(
            model_name="claude-sonnet-4-20250514",
            max_tokens=500,          # reducido de 2000: respuesta conversacional, no documento
            temperature=0.7,
            top_p=0.9,
            cost_per_1k_tokens=3.00,
            context_window=200_000,
            recommended_use="Uso general, recomendaciones personalizadas",
        ),
        ClaudeModelTier.OPUS: ClaudeModelConfig(
            model_name="claude-3-opus-20240229",
            max_tokens=800,          # reducido de 4000: mantiene capacidad de analisis
            temperature=0.7,
            top_p=0.9,
            cost_per_1k_tokens=15.00,
            context_window=200_000,
            recommended_use="Analisis complejos, razonamiento avanzado",
        ),
    }

    def __init__(self) -> None:
        """Inicializa el servicio leyendo el entorno en este momento.

        El tier queda fijo en la instancia para ser la fuente de verdad,
        pero get_model_config() re-lee CLAUDE_MAX_TOKENS en cada llamada
        (sin cache) para que los cambios de secret sean efectivos sin
        necesidad de redeploy.
        """
        # Leer tier/region desde entorno -- se fijan en la instancia
        self.claude_model_tier: ClaudeModelTier = self._resolve_model_tier()
        self.claude_region: ClaudeRegion = self._resolve_region()
        self.enable_ab_testing: bool = self._get_bool_env("CLAUDE_ENABLE_AB_TESTING", False)
        self.ab_testing_group: str = self._get_env("CLAUDE_AB_GROUP", "default")

        # Flag "once" para suprimir logs repetitivos de overrides.
        # get_model_config() se llama por cada request; sin este flag
        # _apply_environment_overrides inundaria los logs con el mismo warning
        # en cada request. El log de 'claude_config_effective' solo se emite
        # una vez por instancia (durante startup).
        self._overrides_logged: bool = False

        # Log de arranque -- confirma que tier se leyo del entorno
        logger.info(
            "🔧 Claude configuration initialized: "
            "model_tier=%s (%s), region=%s",
            self.claude_model_tier.name,
            self.claude_model_tier.value,
            self.claude_region,
        )

    # ------------------------------------------------------------------
    # Resolucion de tier y region
    # ------------------------------------------------------------------

    def _resolve_model_tier(self) -> ClaudeModelTier:
        """Resuelve el tier de modelo desde configuracion."""
        # 1. Desde variable de entorno especifica (secret CLAUDE_MODEL_TIER)
        model_tier = self._get_env("CLAUDE_MODEL_TIER")
        if model_tier:
            try:
                resolved = ClaudeModelTier.from_string(model_tier)
                logger.info(
                    "✅ Resolved CLAUDE_MODEL_TIER '%s' to %s",
                    model_tier,
                    resolved.value,
                )
                return resolved
            except ValueError as exc:
                logger.warning("Error resolving CLAUDE_MODEL_TIER: %s", exc)

        # 2. Desde CLAUDE_MODEL (backward compatibility)
        model_name = self._get_env("CLAUDE_MODEL")
        if model_name:
            for tier, cfg in self.MODEL_CONFIGS.items():
                if cfg.model_name == model_name:
                    logger.info(
                        "✅ Resolved CLAUDE_MODEL %s to tier %s",
                        model_name,
                        tier.name,
                    )
                    return tier
            logger.warning("Unknown CLAUDE_MODEL: %s", model_name)

        # 3. Desde configuracion por entorno (fallback)
        env = self._get_env("ENVIRONMENT", "development").lower()
        if env in ("production", "prod"):
            logger.info("🏭 Production environment detected: using SONNET tier")
            return ClaudeModelTier.SONNET
        if env in ("staging", "test"):
            logger.info("🧪 Test environment detected: using HAIKU tier")
            return ClaudeModelTier.HAIKU

        logger.info("🔧 Development environment: using SONNET tier (default)")
        return ClaudeModelTier.SONNET

    def _resolve_region(self) -> ClaudeRegion:
        """Resuelve la region desde configuracion."""
        region = self._get_env("CLAUDE_REGION", "global").lower()
        try:
            return ClaudeRegion(region)
        except ValueError:
            logger.warning("Invalid CLAUDE_REGION: %s, using global", region)
            return ClaudeRegion.GLOBAL

    # ------------------------------------------------------------------
    # Helpers de entorno
    # ------------------------------------------------------------------

    def _get_env(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Helper para obtener variables de entorno."""
        return os.getenv(key, default)

    def _get_bool_env(self, key: str, default: bool = False) -> bool:
        """Helper para obtener variables booleanas."""
        return os.getenv(key, str(default)).lower() in ("true", "1", "yes", "on")

    # ------------------------------------------------------------------
    # Obtencion de configuracion de modelo
    # ------------------------------------------------------------------

    def get_model_config(self, context: Optional[Dict[str, Any]] = None) -> ClaudeModelConfig:
        """Obtiene configuracion de modelo resolviendo contexto.

        NOTA (fix 21/03/2026): El cache interno _resolved_config fue eliminado.
        Antes: la primera llamada congelaba max_tokens para siempre. Si el
        secret CLAUDE_MAX_TOKENS llegaba DESPUES del primer import (startup
        race condition en Cloud Run), max_tokens quedaba en el valor del
        codigo, no del secret.
        Ahora: re-lee el entorno en cada llamada. El overhead es despreciable
        (~0.01 ms) porque MODEL_CONFIGS es un dict en memoria y os.getenv
        es O(1).

        Args:
            context: Contexto opcional para resolucion dinamica
                     (A/B testing futuro).

        Returns:
            ClaudeModelConfig con overrides de entorno aplicados.
        """
        tier = self._resolve_model_tier_with_context(context)
        base_config = self.MODEL_CONFIGS[tier]
        # Aplica CLAUDE_MAX_TOKENS / CLAUDE_TEMPERATURE si existen en el entorno
        return self._apply_environment_overrides(base_config)

    def _resolve_model_tier_with_context(
        self,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClaudeModelTier:
        """Resuelve tier considerando contexto (A/B testing futuro)."""
        if not self.enable_ab_testing or not context:
            return self.claude_model_tier

        user_id  = context.get("user_id")
        market_id = context.get("market_id", "default")

        if self.ab_testing_group == "premium" and market_id in ("US", "ES"):
            logger.info(
                "🎯 A/B Testing: Using OPUS for premium user %s in %s",
                user_id,
                market_id,
            )
            return ClaudeModelTier.OPUS

        if self.ab_testing_group == "economy":
            logger.info("💰 A/B Testing: Using HAIKU for economy group")
            return ClaudeModelTier.HAIKU

        return self.claude_model_tier

    def _apply_environment_overrides(self, config: ClaudeModelConfig) -> ClaudeModelConfig:
        """Aplica overrides desde variables de entorno y emite el log de configuracion efectiva.

        ADVERTENCIA: El secret CLAUDE_MAX_TOKENS en Cloud Run sobreescribe
        el max_tokens definido en MODEL_CONFIGS. Si ese secret tiene un valor
        alto (ej. 1000 o 2000), los cambios en el codigo son invisibles en
        produccion. Para usar el valor del codigo hay que actualizar o eliminar
        el secret en Secret Manager.

        Los logs de este metodo se emiten SOLO en el primer call por instancia
        (_overrides_logged=True despues), para no inundar los logs en produccion.
        """
        # Crear copia para no mutar el CONFIG original (que es un singleton de clase)
        new_config = ClaudeModelConfig(
            model_name=config.model_name,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            cost_per_1k_tokens=config.cost_per_1k_tokens,
            context_window=config.context_window,
            recommended_use=config.recommended_use,
        )

        # -- OVERRIDE max_tokens -------------------------------------------
        max_tokens_env = self._get_env("CLAUDE_MAX_TOKENS")
        if max_tokens_env:
            try:
                override_value = int(max_tokens_env)
                if not self._overrides_logged:
                    logger.warning(
                        "⚠️ CLAUDE_MAX_TOKENS secret SOBREESCRIBE el valor del codigo: "
                        "%d → %d. Para usar el valor del codigo (%d), "
                        "elimina o actualiza el secret en Cloud Run Secret Manager.",
                        config.max_tokens,
                        override_value,
                        config.max_tokens,
                    )
                new_config.max_tokens = override_value
            except ValueError:
                if not self._overrides_logged:
                    logger.warning(
                        "Invalid CLAUDE_MAX_TOKENS env value: '%s' "
                        "-- using code default: %d",
                        max_tokens_env,
                        config.max_tokens,
                    )
        else:
            if not self._overrides_logged:
                logger.info(
                    "✅ CLAUDE_MAX_TOKENS secret no encontrado "
                    "-- usando valor del codigo: max_tokens=%d",
                    config.max_tokens,
                )

        # -- OVERRIDE temperature ------------------------------------------
        temperature_env = self._get_env("CLAUDE_TEMPERATURE")
        if temperature_env:
            try:
                new_config.temperature = float(temperature_env)
                if not self._overrides_logged:
                    logger.info("⚙️ Override CLAUDE_TEMPERATURE: %s", temperature_env)
            except ValueError:
                if not self._overrides_logged:
                    logger.warning("Invalid CLAUDE_TEMPERATURE: %s", temperature_env)

        # -- LOG FINAL EFECTIVO (solo 1 vez por instancia) -----------------
        # Este log es el unico punto de verdad sobre que modelo y max_tokens
        # usa Claude en produccion. Busca 'claude_config_effective' en GCP.
        if not self._overrides_logged:
            logger.info(
                "📊 claude_config_effective: model=%s, max_tokens=%d, temperature=%.2f",
                new_config.model_name,
                new_config.max_tokens,
                new_config.temperature,
            )
            self._overrides_logged = True  # No repetir en llamadas subsiguientes

        return new_config

    # ------------------------------------------------------------------
    # Parametros para el cliente Anthropic
    # ------------------------------------------------------------------

    def get_anthropic_client_params(
        self,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Obtiene parametros listos para AsyncAnthropic client.

        Args:
            context: Contexto para resolucion dinamica.

        Returns:
            Dict con api_key, model_params, region, timeout y max_retries.
        """
        config = self.get_model_config(context)
        return {
            "api_key":      self._get_env("ANTHROPIC_API_KEY"),
            "model_params": config.to_anthropic_params(),
            "region":       self.claude_region.value,
            "timeout":      float(self._get_env("CLAUDE_TIMEOUT", "30")),
            "max_retries":  int(self._get_env("CLAUDE_MAX_RETRIES", "3")),
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene metricas de configuracion para monitoring."""
        config = self.get_model_config()
        return {
            "model_tier":                  self.claude_model_tier.value,
            "model_name":                  config.model_name,
            "region":                      self.claude_region.value,
            "ab_testing_enabled":          self.enable_ab_testing,
            "ab_testing_group":            self.ab_testing_group,
            "estimated_cost_per_1k_tokens": config.cost_per_1k_tokens,
            "max_context_window":          config.context_window,
            "configuration_source":        "centralized",
        }

    # ------------------------------------------------------------------
    # Propiedades de configuracion de cliente
    # Definidas UNA SOLA VEZ. El bug original tenia estas properties
    # duplicadas -- Python sobreescribe silenciosamente la primera
    # definicion con la segunda, creando confusion en debugging.
    # ------------------------------------------------------------------

    @property
    def timeout(self) -> float:
        """Timeout para llamadas Claude API (segundos)."""
        return float(self._get_env("CLAUDE_TIMEOUT", "30"))

    @property
    def max_retries(self) -> int:
        """Numero maximo de reintentos para Claude API."""
        return int(self._get_env("CLAUDE_MAX_RETRIES", "3"))

    @property
    def region(self) -> str:
        """Region Claude API como string simple."""
        return self.claude_region.value

    def get_timeout_config(self) -> Dict[str, Any]:
        """Obtiene configuracion de timeouts para componentes legacy."""
        return {
            "timeout":            self.timeout,
            "max_retries":        self.max_retries,
            "connection_timeout": self.timeout * 0.8,  # 80% del timeout total
            "read_timeout":       self.timeout * 0.9,  # 90% del timeout total
        }

    # ------------------------------------------------------------------
    # Validacion
    # ------------------------------------------------------------------

    def validate_configuration(self) -> Dict[str, Any]:
        """Valida la configuracion actual."""
        issues: List[str]   = []
        warnings: List[str] = []

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
        except Exception as exc:
            issues.append(f"Model configuration error: {exc}")

        # Validar timeout
        try:
            timeout_val = self.timeout
            if timeout_val <= 0:
                issues.append("Invalid timeout value: must be > 0")
            elif timeout_val > 120:
                warnings.append(f"High timeout value: {timeout_val}s may impact UX")
        except Exception as exc:
            issues.append(f"Timeout configuration error: {exc}")

        # Validar max_retries
        try:
            retries = self.max_retries
            if retries < 0:
                issues.append("Invalid max_retries: must be >= 0")
            elif retries > 10:
                warnings.append(f"High retry count: {retries} may cause delays")
        except Exception as exc:
            issues.append(f"Retry configuration error: {exc}")

        # Advertir sobre uso de OPUS en produccion (caro)
        env = self._get_env("ENVIRONMENT", "development")
        if env == "production" and self.claude_model_tier == ClaudeModelTier.OPUS:
            warnings.append("Using expensive OPUS model in production")

        return {
            "valid":          len(issues) == 0,
            "issues":         issues,
            "warnings":       warnings,
            "config_summary": self.get_metrics(),
        }


# ======================================================================
# SINGLETON MANUAL (reemplaza @lru_cache)
# ======================================================================
# Por que no @lru_cache:
#   lru_cache congela el resultado del PRIMER import. En Cloud Run, si el
#   secret CLAUDE_MODEL_TIER no esta disponible exactamente en ese momento
#   (race condition de startup), la instancia queda con SONNET para toda la
#   vida del contenedor, incluso si el secret llega 50ms despues.
#
# El singleton manual tiene el mismo comportamiento (una unica instancia por
# proceso) pero ademas permite:
#   1. reset_claude_config_service() en tests para evitar estado compartido
#   2. Recargar configuracion en caliente sin reiniciar el contenedor
#   3. Debugging claro: la linea que crea la instancia es legible
# ======================================================================

_claude_config_instance: Optional[ClaudeConfigurationService] = None


def get_claude_config_service() -> ClaudeConfigurationService:
    """Retorna el singleton de ClaudeConfigurationService.

    Crea la instancia en el PRIMER call (lazy init), luego la reutiliza.
    El singleton vive mientras viva el proceso Python (igual que lru_cache).
    """
    global _claude_config_instance
    if _claude_config_instance is None:
        _claude_config_instance = ClaudeConfigurationService()
    return _claude_config_instance


def reset_claude_config_service() -> None:
    """Resetea el singleton -- uso valido EXCLUSIVO: tests unitarios.

    Permite que cada test empiece con un ClaudeConfigurationService fresco,
    sin estado compartido de la ejecucion anterior.

    Ejemplo en pytest:
        def test_haiku_from_env(monkeypatch):
            monkeypatch.setenv("CLAUDE_MODEL_TIER", "HAIKU")
            reset_claude_config_service()       # <-- indispensable
            svc = get_claude_config_service()
            assert svc.claude_model_tier == ClaudeModelTier.HAIKU
    """
    global _claude_config_instance
    _claude_config_instance = None
    logger.info("🔄 claude_config_service singleton reset (intended for tests only)")


# ======================================================================
# Convenience functions para backward compatibility
# ======================================================================

def get_claude_model() -> str:
    """Obtiene el nombre del modelo Claude actual."""
    return get_claude_config_service().get_model_config().model_name


def get_claude_params(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Obtiene parametros para llamadas a Claude API."""
    return get_claude_config_service().get_anthropic_client_params(context)
