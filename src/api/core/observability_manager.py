# src/api/core/observability_manager.py
"""
Observability Manager Unificado - Single Source of Truth
=======================================================

Consolida todos los sistemas de monitoreo, métricas y health checks
para eliminar inconsistencias entre endpoints.

SOLUCIÓN A PROBLEMAS DETECTADOS:
1. Múltiples fuentes de verdad inconsistentes
2. Sistemas de alerting duplicados  
3. Estado contradictorio entre endpoints
"""

import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import threading

# Import solo lo que sabemos que existe
from src.api.core.claude_config import get_claude_config_service

logger = logging.getLogger(__name__)

@dataclass
class MetricsData:
    """Datos de métricas para tracking"""
    timestamp: float
    success: bool
    response_time_ms: float
    user_id: Optional[str] = None
    market_id: Optional[str] = None
    error_type: Optional[str] = None
    endpoint: Optional[str] = None

class MetricsCollector:
    """
    Collector de métricas para observabilidad unificada
    """
    
    def __init__(self):
        self._metrics_buffer: List[MetricsData] = []
        self._buffer_lock = threading.Lock()
        self._max_buffer_size = 1000
        
        # Métricas agregadas
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_response_time = 0.0
        self.error_rate = 0.0
        self.average_response_time_ms = 0.0
        
        # Métricas por endpoint
        self.endpoint_metrics: Dict[str, Dict[str, Any]] = {}
        
        logger.debug("🎯 MetricsCollector initialized")
    
    async def record_request(self, 
                           success: bool,
                           response_time_ms: float,
                           user_id: Optional[str] = None,
                           market_id: Optional[str] = None,
                           error_type: Optional[str] = None,
                           endpoint: Optional[str] = None):
        """
        Registra una request para métricas
        """
        try:
            # Crear entrada de métricas
            metrics_entry = MetricsData(
                timestamp=time.time(),
                success=success,
                response_time_ms=response_time_ms,
                user_id=user_id,
                market_id=market_id,
                error_type=error_type,
                endpoint=endpoint
            )
            
            # Añadir al buffer de manera thread-safe
            with self._buffer_lock:
                self._metrics_buffer.append(metrics_entry)
                
                # Mantener tamaño del buffer
                if len(self._metrics_buffer) > self._max_buffer_size:
                    self._metrics_buffer = self._metrics_buffer[-self._max_buffer_size:]
            
            # Actualizar métricas agregadas
            self._update_aggregate_metrics(metrics_entry)
            
            # Actualizar métricas por endpoint
            if endpoint:
                self._update_endpoint_metrics(endpoint, metrics_entry)
            
            logger.debug(f"📊 Metrics recorded: success={success}, time={response_time_ms:.1f}ms, endpoint={endpoint}")
            
        except Exception as e:
            logger.warning(f"Error recording metrics: {e}")
    
    def _update_aggregate_metrics(self, entry: MetricsData):
        """Actualiza métricas agregadas"""
        self.total_requests += 1
        
        if entry.success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        # Actualizar tiempo de respuesta promedio (promedio móvil)
        self.total_response_time += entry.response_time_ms
        self.average_response_time_ms = self.total_response_time / self.total_requests
        
        # Actualizar error rate
        self.error_rate = self.failed_requests / self.total_requests if self.total_requests > 0 else 0.0
    
    def _update_endpoint_metrics(self, endpoint: str, entry: MetricsData):
        """Actualiza métricas específicas por endpoint"""
        if endpoint not in self.endpoint_metrics:
            self.endpoint_metrics[endpoint] = {
                "requests": 0,
                "successful": 0,
                "failed": 0,
                "total_response_time": 0.0,
                "avg_response_time": 0.0,
                "error_rate": 0.0
            }
        
        metrics = self.endpoint_metrics[endpoint]
        metrics["requests"] += 1
        
        if entry.success:
            metrics["successful"] += 1
        else:
            metrics["failed"] += 1
        
        metrics["total_response_time"] += entry.response_time_ms
        metrics["avg_response_time"] = metrics["total_response_time"] / metrics["requests"]
        metrics["error_rate"] = metrics["failed"] / metrics["requests"]
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas actuales"""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "error_rate": self.error_rate,
            "average_response_time_ms": self.average_response_time_ms,
            "endpoint_metrics": self.endpoint_metrics.copy(),
            "buffer_size": len(self._metrics_buffer),
            "last_updated": time.time()
        }

class SystemStatus(str, Enum):
    """Estado unificado del sistema"""
    HEALTHY = "healthy"
    DEGRADED = "degraded" 
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

@dataclass
class UnifiedSystemState:
    """Estado unificado del sistema Claude"""
    overall_status: SystemStatus
    configuration_status: SystemStatus
    api_connectivity_status: SystemStatus
    model_availability_status: SystemStatus
    performance_status: SystemStatus
    cost_status: SystemStatus
    
    # Métricas consolidadas
    error_rate: float
    average_response_time_ms: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    
    # Alertas consolidadas
    active_alerts: List[Dict[str, Any]]
    critical_alerts_count: int
    
    # Metadata
    timestamp: float
    sla_compliance: bool
    loadtest_ready: bool

class ObservabilityManager:
    """
    Gestor unificado de observabilidad para eliminar inconsistencias
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern para garantizar una sola fuente de verdad"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self.claude_config = get_claude_config_service()
        
        # ✅ AÑADIR: Instanciar MetricsCollector
        self.metrics_collector = MetricsCollector()
        
        # Estado unificado
        self._unified_state: Optional[UnifiedSystemState] = None
        self._last_update: float = 0
        self._update_interval: float = 30  # 30 segundos
        
        # Cache para evitar recálculos costosos
        self._cache_ttl = 15  # 15 segundos para cache rápido
        self._cached_results: Dict[str, Any] = {}
        
        self._initialized = True
        logger.info("🎯 ObservabilityManager initialized with MetricsCollector")
    
    async def get_unified_state(self, force_refresh: bool = False) -> UnifiedSystemState:
        """
        Obtiene el estado unificado del sistema - SINGLE SOURCE OF TRUTH
        """
        current_time = time.time()
        
        # Verificar si necesitamos actualizar
        if (force_refresh or 
            self._unified_state is None or 
            current_time - self._last_update > self._update_interval):
            
            await self._update_unified_state()
            self._last_update = current_time
        
        return self._unified_state
    
    async def _update_unified_state(self):
        """Actualiza el estado unificado agregando todas las fuentes"""
        logger.debug("🔄 Updating unified state...")
        
        try:
            # Intentar obtener health check
            health_result = await self._get_health_safely()
            
            # Obtener métricas básicas
            metrics_result = self._get_basic_metrics()
            
            # Determinar estados usando lógica simplificada
            overall_status = self._determine_overall_status_safe(health_result, metrics_result)
            
            # Estados individuales
            config_status = self._extract_safe_status(health_result, "configuration")
            api_status = self._extract_safe_status(health_result, "api_connectivity") 
            model_status = self._extract_safe_status(health_result, "model_availability")
            perf_status = SystemStatus.HEALTHY  # Default para performance
            cost_status = SystemStatus.HEALTHY  # Default para cost
            
            # Métricas básicas
            error_rate = metrics_result.get("error_rate", 0.0)
            avg_response_time = metrics_result.get("average_response_time_ms", 500.0)
            total_requests = metrics_result.get("total_requests", 0)
            successful_requests = metrics_result.get("successful_requests", 0)
            failed_requests = metrics_result.get("failed_requests", 0)
            
            # Alertas básicas
            active_alerts = []
            if error_rate > 0.05:
                active_alerts.append({
                    "severity": "error",
                    "message": f"High error rate: {error_rate:.2%}",
                    "timestamp": time.time()
                })
            
            critical_alerts = [a for a in active_alerts if a.get("severity") == "critical"]
            
            # SLA y loadtest readiness
            sla_compliance = self._determine_sla_compliance(error_rate, avg_response_time, overall_status)
            loadtest_ready = self._determine_loadtest_readiness(overall_status, len(critical_alerts), sla_compliance)
            
            # Crear estado unificado
            self._unified_state = UnifiedSystemState(
                overall_status=overall_status,
                configuration_status=config_status,
                api_connectivity_status=api_status,
                model_availability_status=model_status,
                performance_status=perf_status,
                cost_status=cost_status,
                
                error_rate=error_rate,
                average_response_time_ms=avg_response_time,
                total_requests=total_requests,
                successful_requests=successful_requests,
                failed_requests=failed_requests,
                
                active_alerts=active_alerts,
                critical_alerts_count=len(critical_alerts),
                
                timestamp=time.time(),
                sla_compliance=sla_compliance,
                loadtest_ready=loadtest_ready
            )
            
            logger.debug(f"✅ Unified state updated: {overall_status.value}")
            
        except Exception as e:
            logger.error(f"Error updating unified state: {e}")
            # Estado de fallback en caso de error
            self._unified_state = self._create_fallback_state()
    
    async def _get_health_safely(self) -> Dict[str, Any]:
        """Obtiene health check de manera segura"""
        try:
            # Intentar import dinámico para evitar errores
            from src.api.health.claude_health import ClaudeHealthChecker
            health_checker = ClaudeHealthChecker()
            return await health_checker.get_comprehensive_health()
        except Exception as e:
            logger.warning(f"Health checker not available: {e}")
            return {
                "overall_status": "unknown",
                "claude_integration": {
                    "checks": {
                        "configuration": {"status": "unknown"},
                        "api_connectivity": {"status": "unknown"},
                        "model_availability": {"status": "unknown"}
                    }
                }
            }
    
    def _get_basic_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas básicas del collector real"""
        return self.metrics_collector.get_current_metrics()
    
    def _determine_overall_status_safe(self, health_result: Dict, metrics_result: Dict) -> SystemStatus:
        """Determina estado general de manera segura"""
        try:
            health_status = health_result.get("overall_status", "unknown")
            error_rate = metrics_result.get("error_rate", 0.0)
            
            if health_status == "unhealthy" or error_rate > 0.5:
                return SystemStatus.UNHEALTHY
            elif health_status == "degraded" or error_rate > 0.1:
                return SystemStatus.DEGRADED
            elif health_status == "healthy":
                return SystemStatus.HEALTHY
            else:
                return SystemStatus.UNKNOWN
        except Exception as e:
            logger.warning(f"Error determining status: {e}")
            return SystemStatus.UNKNOWN
    
    def _extract_safe_status(self, health_result: Dict, component: str) -> SystemStatus:
        """Extrae estado de componente de manera segura"""
        try:
            checks = health_result.get("claude_integration", {}).get("checks", {})
            component_result = checks.get(component, {})
            status_str = component_result.get("status", "unknown")
            return SystemStatus(status_str)
        except (ValueError, KeyError):
            return SystemStatus.UNKNOWN
    
    def _determine_sla_compliance(self, error_rate: float, avg_response_time: float, overall_status: SystemStatus) -> bool:
        """Determina si el sistema cumple con SLA"""
        return (
            error_rate < 0.05 and  # Error rate < 5%
            avg_response_time < 2000 and  # Response time < 2s
            overall_status in [SystemStatus.HEALTHY, SystemStatus.DEGRADED]
        )
    
    def _determine_loadtest_readiness(self, overall_status: SystemStatus, critical_alerts: int, sla_compliance: bool) -> bool:
        """Determina si el sistema está listo para load testing"""
        return (
            overall_status == SystemStatus.HEALTHY and
            critical_alerts == 0 and
            sla_compliance
        )
    
    def _create_fallback_state(self) -> UnifiedSystemState:
        """Crea estado de fallback en caso de error"""
        return UnifiedSystemState(
            overall_status=SystemStatus.UNKNOWN,
            configuration_status=SystemStatus.UNKNOWN,
            api_connectivity_status=SystemStatus.UNKNOWN,
            model_availability_status=SystemStatus.UNKNOWN,
            performance_status=SystemStatus.UNKNOWN,
            cost_status=SystemStatus.UNKNOWN,
            
            error_rate=0.0,
            average_response_time_ms=0.0,
            total_requests=0,
            successful_requests=0,
            failed_requests=0,
            
            active_alerts=[],
            critical_alerts_count=0,
            
            timestamp=time.time(),
            sla_compliance=False,
            loadtest_ready=False
        )
    
    # MÉTODOS PARA ENDPOINTS ESPECÍFICOS
    
    async def get_health_response(self) -> Dict[str, Any]:
        """Respuesta estandarizada para /health/claude"""
        state = await self.get_unified_state()
        
        return {
            "overall_status": state.overall_status.value,
            "check_duration_ms": 0,  # Cached response
            "timestamp": state.timestamp,
            "claude_integration": {
                "status": state.overall_status.value,
                "model_tier": self.claude_config.claude_model_tier.value,
                "configuration_source": "centralized",
                "checks": {
                    "configuration": {"status": state.configuration_status.value},
                    "api_connectivity": {"status": state.api_connectivity_status.value},
                    "model_availability": {"status": state.model_availability_status.value},
                    "performance": {"status": state.performance_status.value},
                    "cost_usage": {"status": state.cost_status.value}
                }
            },
            "recommendations": self._get_recommendations(state)
        }
    
    async def get_metrics_response(self) -> Dict[str, Any]:
        """Respuesta estandarizada para /v1/metrics/claude"""
        state = await self.get_unified_state()
        
        return {
            "timestamp": state.timestamp,
            "realtime_metrics": {
                "timestamp": state.timestamp,
                "claude_integration": {
                    "status": "operational" if state.overall_status == SystemStatus.HEALTHY else "degraded",
                    "model_tier": self.claude_config.claude_model_tier.value,
                    "configuration_source": "centralized"
                },
                "request_metrics": {
                    "total_requests": state.total_requests,
                    "successful_requests": state.successful_requests,
                    "failed_requests": state.failed_requests,
                    "error_rate": state.error_rate
                },
                "performance_metrics": {
                    "average_response_time_ms": state.average_response_time_ms,
                    "sla_compliance": state.sla_compliance
                },
                "alerts": {
                    "active_alerts": len(state.active_alerts),
                    "recent_alerts": state.active_alerts
                }
            }
        }
    
    async def get_loadtest_response(self) -> Dict[str, Any]:
        """Respuesta estandarizada para /v1/loadtest/claude/status"""
        state = await self.get_unified_state()
        
        return {
            "loadtest_ready": state.loadtest_ready,
            "current_status": state.overall_status.value,
            "sla_compliance": state.sla_compliance,
            "current_response_time_p95": state.average_response_time_ms * 1.2,  # Estimate P95
            "active_alerts": len(state.active_alerts),
            "critical_alerts": state.critical_alerts_count,
            "error_rate": state.error_rate,
            "recommendations": self._get_loadtest_recommendations(state),
            "test_endpoints": [
                "/v1/mcp/conversation",
                "/v1/recommendations/user/{user_id}",
                "/v1/products/search/"
            ]
        }
    
    def _get_recommendations(self, state: UnifiedSystemState) -> List[str]:
        """Genera recomendaciones basadas en el estado unificado"""
        recommendations = []
        
        if state.overall_status == SystemStatus.UNHEALTHY:
            if state.configuration_status == SystemStatus.UNHEALTHY:
                recommendations.append("Fix Claude configuration issues - check ANTHROPIC_API_KEY and model settings")
            if state.api_connectivity_status == SystemStatus.UNHEALTHY:
                recommendations.append("Resolve Claude API connectivity issues - check network and authentication")
            if state.error_rate > 0.5:
                recommendations.append("Critical error rate detected - investigate failed requests immediately")
        
        elif state.overall_status == SystemStatus.DEGRADED:
            if state.average_response_time_ms > 3000:
                recommendations.append("High response times detected - consider optimizing prompts or switching to HAIKU tier")
            if state.error_rate > 0.1:
                recommendations.append("Elevated error rate - monitor Claude API limits and retry logic")
            if len(state.active_alerts) > 2:
                recommendations.append("Multiple alerts active - review system performance and resolve issues")
        
        else:
            recommendations.append("All Claude systems healthy - no action required")
        
        return recommendations
    
    def _get_loadtest_recommendations(self, state: UnifiedSystemState) -> List[str]:
        """Genera recomendaciones específicas para load testing"""
        recommendations = []
        
        if not state.loadtest_ready:
            if state.overall_status != SystemStatus.HEALTHY:
                recommendations.append(f"Resolve {state.overall_status.value} status before load testing")
            if state.critical_alerts_count > 0:
                recommendations.append("Resolve critical alerts before load testing")
            if not state.sla_compliance:
                recommendations.append("Achieve SLA compliance before load testing")
        else:
            recommendations.append("System ready for load testing")
            recommendations.append("Monitor /v1/metrics/claude during testing")
            recommendations.append("Use /health/claude for real-time status")
        
        return recommendations

# Singleton instance
_observability_manager = None

def get_observability_manager() -> ObservabilityManager:
    """Factory function para obtener la instancia singleton"""
    global _observability_manager
    if _observability_manager is None:
        _observability_manager = ObservabilityManager()
    return _observability_manager
