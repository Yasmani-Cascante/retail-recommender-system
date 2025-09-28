# src/api/health/claude_health.py
"""
Health Checks Extendidos para Claude Integration
==============================================

Sistema comprehensivo de health checks para validar el estado
de la integración Claude centralizada en tiempo real.

Author: Arquitecto Senior
Version: 1.0.0
"""

import time
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

# Claude integration imports
from src.api.core.claude_config import get_claude_config_service, ClaudeModelTier
from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager

logger = logging.getLogger(__name__)

class HealthStatus(str, Enum):
    """Estados de salud del sistema"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

@dataclass
class HealthCheckResult:
    """Resultado de un health check individual"""
    component: str
    status: HealthStatus
    response_time_ms: float
    details: Dict[str, Any]
    timestamp: float
    error_message: Optional[str] = None

@dataclass
class ClaudeHealthMetrics:
    """Métricas de salud específicas de Claude"""
    configuration_valid: bool
    model_tier: str
    api_connectivity: bool
    last_successful_call: Optional[float]
    average_response_time_ms: float
    error_rate_24h: float
    cost_estimate_24h: float
    rate_limit_status: str

class ClaudeHealthChecker:
    """
    Servicio de health checks para la integración Claude
    """
    
    def __init__(self):
        self.claude_config = get_claude_config_service()
        self.conversation_manager = None
        self.last_health_check = 0
        self.health_cache_ttl = 30  # Cache por 30 segundos
        self.cached_result = None
        
        # Métricas históricas para trending
        self.metrics_history = []
        self.max_history_size = 100
    
    async def get_comprehensive_health(self) -> Dict[str, Any]:
        """
        Realiza health check comprehensivo de todo el sistema Claude
        """
        start_time = time.time()
        
        # Verificar cache
        if (time.time() - self.last_health_check) < self.health_cache_ttl and self.cached_result:
            return self.cached_result
        
        logger.info("🔍 Executing comprehensive Claude health check...")
        
        # Ejecutar todos los health checks en paralelo
        health_checks = await asyncio.gather(
            self._check_configuration_health(),
            self._check_api_connectivity(),
            self._check_model_availability(),
            self._check_performance_metrics(),
            self._check_cost_and_usage(),
            return_exceptions=True
        )
        
        # Procesar resultados
        results = {}
        overall_status = HealthStatus.HEALTHY
        
        check_names = [
            "configuration", "api_connectivity", "model_availability", 
            "performance", "cost_usage"
        ]
        
        for i, check_result in enumerate(health_checks):
            check_name = check_names[i]
            
            if isinstance(check_result, Exception):
                results[check_name] = HealthCheckResult(
                    component=check_name,
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=0,
                    details={},
                    timestamp=time.time(),
                    error_message=str(check_result)
                )
                overall_status = HealthStatus.UNHEALTHY
            else:
                results[check_name] = check_result
                # Determinar estado general
                if check_result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif check_result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
        
        # Compilar respuesta final
        total_time = (time.time() - start_time) * 1000
        
        comprehensive_result = {
            "overall_status": overall_status.value,
            "check_duration_ms": round(total_time, 2),
            "timestamp": time.time(),
            "claude_integration": {
                "status": overall_status.value,
                "model_tier": self.claude_config.claude_model_tier.value,
                "configuration_source": "centralized",
                "checks": {name: asdict(result) for name, result in results.items()}
            },
            "metrics_summary": await self._get_metrics_summary(),
            "recommendations": self._get_health_recommendations(results)
        }
        
        # Actualizar cache y métricas históricas
        self.cached_result = comprehensive_result
        self.last_health_check = time.time()
        self._update_metrics_history(comprehensive_result)
        
        return comprehensive_result
    
    async def _check_configuration_health(self) -> HealthCheckResult:
        """Verifica la salud de la configuración Claude"""
        start_time = time.time()
        
        try:
            # Validar configuración
            validation_result = self.claude_config.validate_configuration()
            response_time = (time.time() - start_time) * 1000
            
            if validation_result["valid"]:
                status = HealthStatus.HEALTHY
                details = {
                    "model_tier": self.claude_config.claude_model_tier.value,
                    "region": self.claude_config.claude_region.value,
                    "timeout": self.claude_config.timeout,
                    "max_retries": self.claude_config.max_retries,
                    "config_summary": validation_result.get("config_summary", {})
                }
                error_msg = None
            else:
                status = HealthStatus.DEGRADED if validation_result.get("warnings") else HealthStatus.UNHEALTHY
                details = {
                    "issues": validation_result.get("issues", []),
                    "warnings": validation_result.get("warnings", [])
                }
                error_msg = f"Configuration issues: {len(validation_result.get('issues', []))}"
            
            return HealthCheckResult(
                component="configuration",
                status=status,
                response_time_ms=response_time,
                details=details,
                timestamp=time.time(),
                error_message=error_msg
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="configuration",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=(time.time() - start_time) * 1000,
                details={},
                timestamp=time.time(),
                error_message=f"Configuration check failed: {str(e)}"
            )
    
    async def _check_api_connectivity(self) -> HealthCheckResult:
        """Verifica conectividad con la API de Claude"""
        start_time = time.time()
        
        try:
            # Crear client temporal para test
            from anthropic import AsyncAnthropic
            import os
            
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            
            claude = AsyncAnthropic(api_key=api_key)
            
            # Test simple de conectividad
            test_message = "Health check test - respond with 'OK'"
            
            response = await claude.messages.create(
                model=self.claude_config.claude_model_tier.value,
                max_tokens=10,
                messages=[{"role": "user", "content": test_message}]
            )
            
            response_time = (time.time() - start_time) * 1000
            
            if response and response.content:
                status = HealthStatus.HEALTHY
                details = {
                    "model_used": self.claude_config.claude_model_tier.value,
                    "response_received": True,
                    "token_usage": {
                        "input_tokens": getattr(response.usage, 'input_tokens', 0),
                        "output_tokens": getattr(response.usage, 'output_tokens', 0)
                    } if hasattr(response, 'usage') else {}
                }
                error_msg = None
            else:
                status = HealthStatus.DEGRADED
                details = {"response_received": False}
                error_msg = "Empty response from Claude API"
            
            return HealthCheckResult(
                component="api_connectivity",
                status=status,
                response_time_ms=response_time,
                details=details,
                timestamp=time.time(),
                error_message=error_msg
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="api_connectivity",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=(time.time() - start_time) * 1000,
                details={},
                timestamp=time.time(),
                error_message=f"API connectivity failed: {str(e)}"
            )
    
    async def _check_model_availability(self) -> HealthCheckResult:
        """Verifica disponibilidad de modelos Claude"""
        start_time = time.time()
        
        try:
            # Verificar todos los tiers de modelo
            model_statuses = {}
            # Solo probar modelos que sabemos que existen
            available_models = ClaudeModelTier.get_available_models()  
                      
            for tier in ClaudeModelTier:
                model_name = tier.value
            
                # Pre-verificación: ¿está en la lista de modelos conocidos?
                if model_name not in available_models:
                    model_statuses[tier.name] = {
                        "available": False,
                        "error": "model_not_in_api",
                        "model_name": model_name,
                        "note": "Model name not found in Anthropic API"
                    }
                    continue
                try:
                    # Test rápido de cada modelo
                    from anthropic import AsyncAnthropic
                    import os
                    
                    claude = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                    
                    # Test muy básico por timeout
                    test_start = time.time()
                    response = await asyncio.wait_for(
                        claude.messages.create(
                            model=model_name,
                            max_tokens=5,
                            messages=[{"role": "user", "content": "test"}]
                        ),
                        timeout=10.0  # Timeout más largo para OPUS
                    )
                    test_time = (time.time() - test_start) * 1000
                    
                    model_statuses[tier.name] = {
                        "available": True,
                        "response_time_ms": test_time,
                        "model_name": model_name,
                        "tokens_used": getattr(response.usage, 'output_tokens', 0) if hasattr(response, 'usage') else 0
                    }
                    
                except asyncio.TimeoutError:
                    model_statuses[tier.name] = {
                        "available": False,
                        "error": "timeout", 
                        "model_name": model_name,
                        "note": "Model request timed out"
                    }
                except Exception as e:
                    error_str = str(e)
                    # Detectar errores específicos de modelo no encontrado
                    if "not_found_error" in error_str or "model:" in error_str:
                        model_statuses[tier.name] = {
                            "available": False,
                            "error": "model_not_found",
                            "model_name": model_name,
                            "note": f"Model not found in API: {error_str}"
                        }
                    else:
                        model_statuses[tier.name] = {
                            "available": False,
                            "error": "api_error",
                            "model_name": model_name,
                            "note": str(e)
                        }
            
            response_time = (time.time() - start_time) * 1000
            
            # Determinar estado general
            available_models = sum(1 for status in model_statuses.values() if status.get("available"))
            total_models = len(model_statuses)
            
            if available_models == total_models:
                status = HealthStatus.HEALTHY
                error_msg = None
            elif available_models > 0:
                status = HealthStatus.DEGRADED
                error_msg = f"Only {available_models}/{total_models} models available"
            else:
                status = HealthStatus.UNHEALTHY
                error_msg = "No models available"
            
            return HealthCheckResult(
                component="model_availability",
                status=status,
                response_time_ms=response_time,
                details={
                    "models": model_statuses,
                    "available_count": available_models,
                    "total_count": total_models,
                    "current_tier": self.claude_config.claude_model_tier.name
                },
                timestamp=time.time(),
                error_message=error_msg
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="model_availability",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=(time.time() - start_time) * 1000,
                details={},
                timestamp=time.time(),
                error_message=f"Model availability check failed: {str(e)}"
            )
    
    async def _check_performance_metrics(self) -> HealthCheckResult:
        """Verifica métricas de performance de Claude"""
        start_time = time.time()
        
        try:
            # Obtener métricas del servicio
            metrics = self.claude_config.get_metrics()
            response_time = (time.time() - start_time) * 1000
            
            # Evaluar performance
            avg_response_time = metrics.get("average_response_time_ms", 0)
            error_rate = metrics.get("error_rate", 0)
            
            if avg_response_time < 1500 and error_rate < 0.01:
                status = HealthStatus.HEALTHY
                error_msg = None
            elif avg_response_time < 3000 and error_rate < 0.05:
                status = HealthStatus.DEGRADED
                error_msg = f"Performance degraded: {avg_response_time:.0f}ms avg, {error_rate:.2%} errors"
            else:
                status = HealthStatus.UNHEALTHY
                error_msg = f"Performance poor: {avg_response_time:.0f}ms avg, {error_rate:.2%} errors"
            
            return HealthCheckResult(
                component="performance",
                status=status,
                response_time_ms=response_time,
                details={
                    "average_response_time_ms": avg_response_time,
                    "error_rate": error_rate,
                    "total_requests": metrics.get("total_requests", 0),
                    "successful_requests": metrics.get("successful_requests", 0)
                },
                timestamp=time.time(),
                error_message=error_msg
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="performance",
                status=HealthStatus.UNKNOWN,
                response_time_ms=(time.time() - start_time) * 1000,
                details={},
                timestamp=time.time(),
                error_message=f"Performance metrics unavailable: {str(e)}"
            )
    
    async def _check_cost_and_usage(self) -> HealthCheckResult:
        """Verifica uso y costos de Claude"""
        start_time = time.time()
        
        try:
            # Estimar costos basado en métricas
            config = self.claude_config.get_model_config()
            metrics = self.claude_config.get_metrics()
            
            # Calcular estimaciones
            total_requests = metrics.get("total_requests", 0)
            avg_tokens_per_request = 1000  # Estimación
            estimated_cost = total_requests * avg_tokens_per_request * config.cost_per_1k_tokens / 1000
            
            response_time = (time.time() - start_time) * 1000
            
            # Evaluar nivel de uso
            if estimated_cost < 100:  # $100/día
                status = HealthStatus.HEALTHY
                error_msg = None
            elif estimated_cost < 500:  # $500/día
                status = HealthStatus.DEGRADED
                error_msg = f"High usage: ${estimated_cost:.2f} estimated daily cost"
            else:
                status = HealthStatus.UNHEALTHY
                error_msg = f"Very high usage: ${estimated_cost:.2f} estimated daily cost"
            
            return HealthCheckResult(
                component="cost_usage",
                status=status,
                response_time_ms=response_time,
                details={
                    "model_tier": config.model_name,
                    "cost_per_1k_tokens": config.cost_per_1k_tokens,
                    "estimated_daily_cost": estimated_cost,
                    "total_requests": total_requests,
                    "cost_optimization_tier": "optimal" if config.cost_per_1k_tokens < 5 else "expensive"
                },
                timestamp=time.time(),
                error_message=error_msg
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="cost_usage",
                status=HealthStatus.UNKNOWN,
                response_time_ms=(time.time() - start_time) * 1000,
                details={},
                timestamp=time.time(),
                error_message=f"Cost analysis failed: {str(e)}"
            )
    
    async def _get_metrics_summary(self) -> Dict[str, Any]:
        """Genera resumen de métricas"""
        try:
            metrics = self.claude_config.get_metrics()
            return {
                "claude_tier": self.claude_config.claude_model_tier.value,
                "configuration_source": "centralized",
                "total_health_checks": len(self.metrics_history),
                "last_check_time": self.last_health_check,
                "system_metrics": metrics
            }
        except Exception:
            return {"status": "metrics_unavailable"}
    
    def _get_health_recommendations(self, results: Dict[str, HealthCheckResult]) -> List[str]:
        """Genera recomendaciones basadas en health checks"""
        recommendations = []
        
        for name, result in results.items():
            if result.status == HealthStatus.UNHEALTHY:
                if name == "api_connectivity":
                    recommendations.append("Check ANTHROPIC_API_KEY and network connectivity")
                elif name == "model_availability":
                    recommendations.append("Consider switching to HAIKU tier for better availability")
                elif name == "performance":
                    recommendations.append("Review Claude timeout settings and optimize prompts")
                elif name == "cost_usage":
                    recommendations.append("Consider optimizing model tier usage for cost efficiency")
            elif result.status == HealthStatus.DEGRADED:
                if name == "performance":
                    recommendations.append("Monitor Claude response times, consider tier optimization")
                elif name == "cost_usage":
                    recommendations.append("Monitor usage patterns for cost optimization opportunities")
        
        if not recommendations:
            recommendations.append("All Claude systems healthy - no action required")
        
        return recommendations
    
    def _update_metrics_history(self, result: Dict[str, Any]) -> None:
        """Actualiza historial de métricas"""
        self.metrics_history.append({
            "timestamp": result["timestamp"],
            "overall_status": result["overall_status"],
            "check_duration_ms": result["check_duration_ms"]
        })
        
        # Mantener tamaño máximo
        if len(self.metrics_history) > self.max_history_size:
            self.metrics_history = self.metrics_history[-self.max_history_size:]

# Instancia global del health checker
claude_health_checker = ClaudeHealthChecker()

async def get_claude_health() -> Dict[str, Any]:
    """
    Función de conveniencia para obtener health check de Claude
    """
    return await claude_health_checker.get_comprehensive_health()