# src/api/monitoring/claude_monitoring.py
"""
Advanced Monitoring System para Claude Integration
=================================================

Sistema de monitoreo avanzado que proporciona métricas detalladas,
alertas automáticas y análisis de tendencias para la integración Claude.

Author: Arquitecto Senior
Version: 1.0.0
"""

import time
import json
import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum
import statistics
from collections import deque, defaultdict

# Claude integration imports
from src.api.core.claude_config import get_claude_config_service

logger = logging.getLogger(__name__)

class MetricType(str, Enum):
    """Tipos de métricas"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"

class AlertSeverity(str, Enum):
    """Severidad de alertas"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class MetricDataPoint:
    """Punto de datos de métrica"""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AlertRule:
    """Regla de alerta"""
    name: str
    metric_name: str
    condition: str  # e.g., "> 1000", "< 0.95"
    threshold: float
    severity: AlertSeverity
    description: str
    cooldown_seconds: int = 300  # 5 minutos
    enabled: bool = True

@dataclass
class Alert:
    """Alerta generada"""
    rule_name: str
    severity: AlertSeverity
    message: str
    timestamp: float
    metric_value: float
    threshold: float
    resolved: bool = False
    resolved_timestamp: Optional[float] = None

class ClaudeMetricsCollector:
    """
    Colector de métricas específicas para Claude
    """
    
    def __init__(self, max_data_points: int = 1000):
        self.max_data_points = max_data_points
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_data_points))
        self.alert_rules: List[AlertRule] = []
        self.active_alerts: List[Alert] = []
        self.resolved_alerts: List[Alert] = []
        self.claude_config = get_claude_config_service()
        
        # Métricas de Claude específicas
        self.claude_metrics = {
            "requests_total": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "total_tokens_used": 0,
            "total_cost_usd": 0.0,
            "average_response_time_ms": 0.0,
            "model_tier_usage": defaultdict(int),
            "error_types": defaultdict(int),
            "conversation_lengths": deque(maxlen=100),
            "cost_by_hour": defaultdict(float),
            "performance_trends": deque(maxlen=24)  # 24 horas
        }
        
        # Configurar reglas de alerta por defecto
        self._setup_default_alert_rules()
        
        logger.info("🔍 Claude Metrics Collector initialized")
    
    def record_claude_request(
        self,
        success: bool,
        response_time_ms: float,
        tokens_used: int = 0,
        model_tier: str = None,
        error_type: str = None,
        cost_usd: float = 0.0,
        conversation_length: int = 0,
        user_id: str = None,
        market_id: str = None
    ) -> None:
        """
        Registra métricas de una request a Claude
        """
        timestamp = time.time()
        
        # Métricas básicas
        self.claude_metrics["requests_total"] += 1
        if success:
            self.claude_metrics["requests_successful"] += 1
        else:
            self.claude_metrics["requests_failed"] += 1
            if error_type:
                self.claude_metrics["error_types"][error_type] += 1
        
        # Métricas de performance
        self._record_metric("claude_response_time_ms", response_time_ms, {
            "model_tier": model_tier or "unknown",
            "success": str(success)
        })
        
        # Actualizar promedio de tiempo de respuesta
        self._update_average_response_time(response_time_ms)
        
        # Métricas de uso de tokens y costo
        if tokens_used > 0:
            self.claude_metrics["total_tokens_used"] += tokens_used
            self._record_metric("claude_tokens_used", tokens_used, {
                "model_tier": model_tier or "unknown"
            })
        
        if cost_usd > 0:
            self.claude_metrics["total_cost_usd"] += cost_usd
            hour_key = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d-%H")
            self.claude_metrics["cost_by_hour"][hour_key] += cost_usd
            self._record_metric("claude_cost_usd", cost_usd, {
                "model_tier": model_tier or "unknown"
            })
        
        # Métricas por modelo
        if model_tier:
            self.claude_metrics["model_tier_usage"][model_tier] += 1
        
        # Métricas de conversación
        if conversation_length > 0:
            self.claude_metrics["conversation_lengths"].append(conversation_length)
        
        # Métricas por usuario/mercado
        if user_id:
            self._record_metric("claude_requests_by_user", 1, {"user_id": user_id})
        if market_id:
            self._record_metric("claude_requests_by_market", 1, {"market_id": market_id})
        
        # Verificar alertas
        self._check_alerts()
    
    def _record_metric(self, name: str, value: float, labels: Dict[str, str] = None) -> None:
        """Registra un punto de métrica"""
        data_point = MetricDataPoint(
            timestamp=time.time(),
            value=value,
            labels=labels or {},
            metadata={}
        )
        self.metrics[name].append(data_point)
    
    def _update_average_response_time(self, new_time: float) -> None:
        """Actualiza promedio móvil de tiempo de respuesta"""
        current_avg = self.claude_metrics["average_response_time_ms"]
        total_requests = self.claude_metrics["requests_total"]
        
        if total_requests == 1:
            self.claude_metrics["average_response_time_ms"] = new_time
        else:
            # Promedio móvil ponderado
            weight = min(0.1, 1.0 / total_requests)
            self.claude_metrics["average_response_time_ms"] = (
                current_avg * (1 - weight) + new_time * weight
            )
    
    def get_realtime_metrics(self) -> Dict[str, Any]:
        """
        Obtiene métricas en tiempo real del sistema Claude
        """
        current_time = time.time()
        
        # Calcular métricas derivadas
        error_rate = 0.0
        if self.claude_metrics["requests_total"] > 0:
            error_rate = self.claude_metrics["requests_failed"] / self.claude_metrics["requests_total"]
        
        # Métricas de performance recientes (última hora)
        recent_response_times = self._get_recent_metric_values("claude_response_time_ms", 3600)
        p95_response_time = self._calculate_percentile(recent_response_times, 95) if recent_response_times else 0
        
        # Costo por hora actual
        current_hour = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d-%H")
        current_hour_cost = self.claude_metrics["cost_by_hour"].get(current_hour, 0.0)
        
        # Tendencias de performance
        performance_trend = self._calculate_performance_trend()
        
        return {
            "timestamp": current_time,
            "claude_integration": {
                "status": "operational",
                "model_tier": self.claude_config.claude_model_tier.value,
                "configuration_source": "centralized"
            },
            "request_metrics": {
                "total_requests": self.claude_metrics["requests_total"],
                "successful_requests": self.claude_metrics["requests_successful"],
                "failed_requests": self.claude_metrics["requests_failed"],
                "error_rate": round(error_rate, 4),
                "requests_per_minute": self._calculate_requests_per_minute()
            },
            "performance_metrics": {
                "average_response_time_ms": round(self.claude_metrics["average_response_time_ms"], 2),
                "p95_response_time_ms": round(p95_response_time, 2),
                "performance_trend": performance_trend,
                "sla_compliance": p95_response_time < 2000  # 2s SLA
            },
            "usage_metrics": {
                "total_tokens_used": self.claude_metrics["total_tokens_used"],
                "total_cost_usd": round(self.claude_metrics["total_cost_usd"], 4),
                "current_hour_cost_usd": round(current_hour_cost, 4),
                "average_tokens_per_request": self._calculate_avg_tokens_per_request(),
                "model_tier_distribution": dict(self.claude_metrics["model_tier_usage"])
            },
            "conversation_metrics": {
                "average_conversation_length": self._calculate_avg_conversation_length(),
                "total_conversations": len(self.claude_metrics["conversation_lengths"]),
                "conversation_length_distribution": self._get_conversation_length_distribution()
            },
            "error_analysis": {
                "error_types": dict(self.claude_metrics["error_types"]),
                "most_common_error": self._get_most_common_error(),
                "error_trend": self._calculate_error_trend()
            },
            "alerts": {
                "active_alerts": len(self.active_alerts),
                "critical_alerts": len([a for a in self.active_alerts if a.severity == AlertSeverity.CRITICAL]),
                "recent_alerts": [asdict(a) for a in self.active_alerts[-5:]]
            }
        }
    
    def get_historical_metrics(self, hours_back: int = 24) -> Dict[str, Any]:
        """
        Obtiene métricas históricas
        """
        cutoff_time = time.time() - (hours_back * 3600)
        
        # Filtrar métricas por tiempo
        historical_data = {}
        for metric_name, data_points in self.metrics.items():
            recent_points = [dp for dp in data_points if dp.timestamp >= cutoff_time]
            if recent_points:
                historical_data[metric_name] = {
                    "data_points": [asdict(dp) for dp in recent_points],
                    "summary": {
                        "count": len(recent_points),
                        "min": min(dp.value for dp in recent_points),
                        "max": max(dp.value for dp in recent_points),
                        "avg": statistics.mean(dp.value for dp in recent_points),
                        "median": statistics.median(dp.value for dp in recent_points)
                    }
                }
        
        return {
            "time_range_hours": hours_back,
            "metrics": historical_data,
            "cost_by_hour": self._get_cost_trend(hours_back),
            "performance_trend": self._get_performance_trend(hours_back),
            "alert_history": [asdict(a) for a in self.resolved_alerts[-50:]]
        }
    
    def _get_recent_metric_values(self, metric_name: str, seconds_back: int) -> List[float]:
        """Obtiene valores recientes de una métrica"""
        cutoff_time = time.time() - seconds_back
        if metric_name in self.metrics:
            return [dp.value for dp in self.metrics[metric_name] if dp.timestamp >= cutoff_time]
        return []
    
    def _calculate_percentile(self, values: List[float], percentile: int) -> float:
        """Calcula percentil de una lista de valores"""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * percentile / 100
        f = int(k)
        c = k - f
        if f == len(sorted_values) - 1:
            return sorted_values[f]
        return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c
    
    def _calculate_requests_per_minute(self) -> float:
        """Calcula requests por minuto en la última hora"""
        recent_requests = self._get_recent_metric_values("claude_response_time_ms", 3600)
        if recent_requests:
            return len(recent_requests) / 60  # Convertir a por minuto
        return 0.0
    
    def _calculate_avg_tokens_per_request(self) -> float:
        """Calcula promedio de tokens por request"""
        if self.claude_metrics["requests_successful"] > 0:
            return self.claude_metrics["total_tokens_used"] / self.claude_metrics["requests_successful"]
        return 0.0
    
    def _calculate_avg_conversation_length(self) -> float:
        """Calcula longitud promedio de conversaciones"""
        lengths = list(self.claude_metrics["conversation_lengths"])
        return statistics.mean(lengths) if lengths else 0.0
    
    def _get_conversation_length_distribution(self) -> Dict[str, int]:
        """Obtiene distribución de longitudes de conversación"""
        lengths = list(self.claude_metrics["conversation_lengths"])
        if not lengths:
            return {}
        
        distribution = {
            "short (1-3)": len([l for l in lengths if 1 <= l <= 3]),
            "medium (4-10)": len([l for l in lengths if 4 <= l <= 10]),
            "long (11-20)": len([l for l in lengths if 11 <= l <= 20]),
            "very_long (21+)": len([l for l in lengths if l > 20])
        }
        return distribution
    
    def _get_most_common_error(self) -> str:
        """Obtiene el tipo de error más común"""
        if not self.claude_metrics["error_types"]:
            return "none"
        return max(self.claude_metrics["error_types"].items(), key=lambda x: x[1])[0]
    
    def _calculate_performance_trend(self) -> str:
        """Calcula tendencia de performance"""
        recent_times = self._get_recent_metric_values("claude_response_time_ms", 1800)  # 30 min
        if len(recent_times) < 10:
            return "insufficient_data"
        
        # Dividir en dos mitades y comparar
        mid_point = len(recent_times) // 2
        first_half_avg = statistics.mean(recent_times[:mid_point])
        second_half_avg = statistics.mean(recent_times[mid_point:])
        
        if second_half_avg < first_half_avg * 0.9:
            return "improving"
        elif second_half_avg > first_half_avg * 1.1:
            return "degrading"
        else:
            return "stable"
    
    def _calculate_error_trend(self) -> str:
        """Calcula tendencia de errores"""
        recent_requests = self._get_recent_metric_values("claude_response_time_ms", 1800)
        if len(recent_requests) < 10:
            return "insufficient_data"
        
        recent_errors = len([dp for dp in self.metrics.get("claude_response_time_ms", []) 
                           if dp.timestamp >= time.time() - 1800 and dp.labels.get("success") == "False"])
        
        error_rate = recent_errors / len(recent_requests) if recent_requests else 0
        
        if error_rate < 0.01:
            return "low"
        elif error_rate < 0.05:
            return "moderate" 
        else:
            return "high"
    
    def _get_cost_trend(self, hours_back: int) -> Dict[str, float]:
        """Obtiene tendencia de costos"""
        cost_trend = {}
        current_time = datetime.now()
        
        for i in range(hours_back):
            hour_time = current_time - timedelta(hours=i)
            hour_key = hour_time.strftime("%Y-%m-%d-%H")
            cost_trend[hour_key] = self.claude_metrics["cost_by_hour"].get(hour_key, 0.0)
        
        return cost_trend
    
    def _get_performance_trend(self, hours_back: int) -> List[Dict[str, Any]]:
        """Obtiene tendencia de performance"""
        performance_data = []
        cutoff_time = time.time() - (hours_back * 3600)
        
        # Agrupar por horas
        hourly_data = defaultdict(list)
        for dp in self.metrics.get("claude_response_time_ms", []):
            if dp.timestamp >= cutoff_time:
                hour_key = datetime.fromtimestamp(dp.timestamp).strftime("%Y-%m-%d-%H")
                hourly_data[hour_key].append(dp.value)
        
        for hour, values in hourly_data.items():
            if values:
                performance_data.append({
                    "hour": hour,
                    "avg_response_time": statistics.mean(values),
                    "p95_response_time": self._calculate_percentile(values, 95),
                    "request_count": len(values)
                })
        
        return sorted(performance_data, key=lambda x: x["hour"])
    
    def _setup_default_alert_rules(self) -> None:
        """Configura reglas de alerta por defecto"""
        default_rules = [
            AlertRule(
                name="claude_high_response_time",
                metric_name="claude_response_time_ms",
                condition="> 3000",
                threshold=3000.0,
                severity=AlertSeverity.WARNING,
                description="Claude response time exceeded 3 seconds",
                cooldown_seconds=300
            ),
            AlertRule(
                name="claude_very_high_response_time",
                metric_name="claude_response_time_ms",
                condition="> 5000",
                threshold=5000.0,
                severity=AlertSeverity.ERROR,
                description="Claude response time exceeded 5 seconds",
                cooldown_seconds=180
            ),
            AlertRule(
                name="claude_high_error_rate",
                metric_name="error_rate",
                condition="> 0.05",
                threshold=0.05,
                severity=AlertSeverity.ERROR,
                description="Claude error rate exceeded 5%",
                cooldown_seconds=300
            ),
            AlertRule(
                name="claude_high_cost",
                metric_name="hourly_cost",
                condition="> 50",
                threshold=50.0,
                severity=AlertSeverity.WARNING,
                description="Claude hourly cost exceeded $50",
                cooldown_seconds=600
            ),
            AlertRule(
                name="claude_api_unavailable",
                metric_name="requests_total",
                condition="= 0",
                threshold=0.0,
                severity=AlertSeverity.CRITICAL,
                description="No Claude requests in last 10 minutes",
                cooldown_seconds=600
            )
        ]
        
        self.alert_rules.extend(default_rules)
    
    def _check_alerts(self) -> None:
        """Verifica condiciones de alerta"""
        current_time = time.time()
        
        for rule in self.alert_rules:
            if not rule.enabled:
                continue
            
            # Verificar cooldown
            recent_alert = next(
                (a for a in self.active_alerts 
                 if a.rule_name == rule.name and not a.resolved 
                 and current_time - a.timestamp < rule.cooldown_seconds),
                None
            )
            if recent_alert:
                continue
            
            # Evaluar condición
            should_alert = self._evaluate_alert_condition(rule)
            if should_alert:
                self._create_alert(rule)
    
    def _evaluate_alert_condition(self, rule: AlertRule) -> bool:
        """Evalúa si se debe generar una alerta"""
        try:
            if rule.metric_name == "error_rate":
                # Calcular error rate actual
                if self.claude_metrics["requests_total"] > 0:
                    current_error_rate = self.claude_metrics["requests_failed"] / self.claude_metrics["requests_total"]
                    return current_error_rate > rule.threshold
                return False
            
            elif rule.metric_name == "hourly_cost":
                # Verificar costo de la hora actual
                current_hour = datetime.now().strftime("%Y-%m-%d-%H")
                current_cost = self.claude_metrics["cost_by_hour"].get(current_hour, 0.0)
                return current_cost > rule.threshold
            
            elif rule.metric_name == "requests_total":
                # Verificar si hay requests recientes
                recent_requests = self._get_recent_metric_values("claude_response_time_ms", 600)  # 10 min
                return len(recent_requests) == 0
            
            elif rule.metric_name in self.metrics:
                # Verificar métricas normales
                recent_values = self._get_recent_metric_values(rule.metric_name, 300)  # 5 min
                if recent_values:
                    current_value = recent_values[-1]
                    if rule.condition.startswith(">"):
                        return current_value > rule.threshold
                    elif rule.condition.startswith("<"):
                        return current_value < rule.threshold
                    elif rule.condition.startswith("="):
                        return abs(current_value - rule.threshold) < 0.001
            
            return False
            
        except Exception as e:
            logger.error(f"Error evaluating alert condition for {rule.name}: {e}")
            return False
    
    def _create_alert(self, rule: AlertRule) -> None:
        """Crea una nueva alerta"""
        # Obtener valor actual de la métrica
        current_value = 0.0
        if rule.metric_name == "error_rate":
            if self.claude_metrics["requests_total"] > 0:
                current_value = self.claude_metrics["requests_failed"] / self.claude_metrics["requests_total"]
        elif rule.metric_name in self.metrics:
            recent_values = self._get_recent_metric_values(rule.metric_name, 300)
            current_value = recent_values[-1] if recent_values else 0.0
        
        alert = Alert(
            rule_name=rule.name,
            severity=rule.severity,
            message=f"{rule.description} (current: {current_value:.2f}, threshold: {rule.threshold})",
            timestamp=time.time(),
            metric_value=current_value,
            threshold=rule.threshold
        )
        
        self.active_alerts.append(alert)
        logger.warning(f"🚨 Alert generated: {alert.message}")
    
    def resolve_alert(self, rule_name: str) -> bool:
        """Resuelve una alerta activa"""
        for alert in self.active_alerts:
            if alert.rule_name == rule_name and not alert.resolved:
                alert.resolved = True
                alert.resolved_timestamp = time.time()
                self.resolved_alerts.append(alert)
                self.active_alerts.remove(alert)
                logger.info(f"✅ Alert resolved: {rule_name}")
                return True
        return False
    
    def add_custom_alert_rule(self, rule: AlertRule) -> None:
        """Añade una regla de alerta personalizada"""
        self.alert_rules.append(rule)
        logger.info(f"📋 Custom alert rule added: {rule.name}")
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Obtiene resumen de alertas"""
        return {
            "active_alerts": [asdict(a) for a in self.active_alerts],
            "resolved_alerts_last_24h": [
                asdict(a) for a in self.resolved_alerts 
                if a.resolved_timestamp and time.time() - a.resolved_timestamp < 86400
            ],
            "alert_rules": [asdict(r) for r in self.alert_rules],
            "alert_statistics": {
                "total_active": len(self.active_alerts),
                "critical_active": len([a for a in self.active_alerts if a.severity == AlertSeverity.CRITICAL]),
                "total_resolved_24h": len([
                    a for a in self.resolved_alerts 
                    if a.resolved_timestamp and time.time() - a.resolved_timestamp < 86400
                ])
            }
        }

# Instancia global del collector
claude_metrics_collector = ClaudeMetricsCollector()

# Funciones de conveniencia
async def record_claude_request(**kwargs):
    """Registra métricas de request Claude"""
    claude_metrics_collector.record_claude_request(**kwargs)

async def get_claude_metrics() -> Dict[str, Any]:
    """Obtiene métricas de Claude en tiempo real"""
    return claude_metrics_collector.get_realtime_metrics()

async def get_claude_historical_metrics(hours_back: int = 24) -> Dict[str, Any]:
    """Obtiene métricas históricas de Claude"""
    return claude_metrics_collector.get_historical_metrics(hours_back)

async def get_claude_alerts() -> Dict[str, Any]:
    """Obtiene resumen de alertas de Claude"""
    return claude_metrics_collector.get_alert_summary()