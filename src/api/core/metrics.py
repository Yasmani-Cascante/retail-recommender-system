"""
Sistema de métricas para evaluar la calidad de las recomendaciones.

Este módulo proporciona funcionalidades para recopilar y analizar métricas sobre
la calidad y el rendimiento del sistema de recomendaciones, incluyendo:
- Diversidad de recomendaciones
- Relevancia de recomendaciones
- Tasa de fallback
- Tiempo de respuesta
- Conversión de recomendaciones
"""

import time
import logging
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

class RecommendationMetrics:
    """
    Sistema para evaluar métricas de calidad de recomendaciones en tiempo real.
    
    Esta clase mantiene un seguimiento de diversas métricas de calidad de las
    recomendaciones, permitiendo analizar y mejorar el sistema con el tiempo.
    """
    
    def __init__(self, log_to_file: bool = True, metrics_file: Optional[str] = None):
        """
        Inicializa el sistema de métricas.
        
        Args:
            log_to_file: Si debe guardar las métricas en un archivo
            metrics_file: Ruta del archivo de métricas (si log_to_file=True)
        """
        self.log_to_file = log_to_file
        self.metrics_file = metrics_file or "recommendation_metrics.jsonl"
        
        # Métricas agregadas
        self.request_count = 0
        self.recommendation_counts = defaultdict(int)  # Por tipo de recomendación
        self.recommendation_times = []
        self.category_diversity = Counter()
        self.user_recommendation_cache = {}  # Para calcular novedad
        
        # Inicializar archivo de métricas si es necesario
        if self.log_to_file:
            # Crear directorio de métricas si no existe
            metrics_dir = os.path.dirname(self.metrics_file)
            if metrics_dir and not os.path.exists(metrics_dir):
                os.makedirs(metrics_dir)
    
    def record_recommendation_request(
        self,
        request_data: Dict,
        recommendations: List[Dict],
        response_time_ms: float,
        user_id: str,
        product_id: Optional[str] = None
    ):
        """
        Registra métricas para una solicitud de recomendación.
        
        Args:
            request_data: Datos de la solicitud (parámetros)
            recommendations: Lista de recomendaciones devueltas
            response_time_ms: Tiempo de respuesta en milisegundos
            user_id: ID del usuario
            product_id: ID del producto (si aplica)
        """
        self.request_count += 1
        self.recommendation_times.append(response_time_ms)
        
        # Fecha y hora
        timestamp = datetime.now().isoformat()
        
        # Métricas específicas para esta solicitud
        recommendation_types = Counter([r.get("recommendation_type", "unknown") for r in recommendations])
        categories = Counter([r.get("category", "unknown") for r in recommendations])
        
        # Actualizar métricas globales
        for rec_type, count in recommendation_types.items():
            self.recommendation_counts[rec_type] += count
        
        for category in categories:
            self.category_diversity[category] += 1
        
        # Calcular novedad (productos no recomendados previamente al usuario)
        novelty_score = 1.0
        if user_id in self.user_recommendation_cache:
            prev_recommendations = self.user_recommendation_cache[user_id]
            new_items = [r for r in recommendations if r.get("id") not in prev_recommendations]
            novelty_score = len(new_items) / len(recommendations) if recommendations else 0
        
        # Actualizar caché de recomendaciones previas
        if user_id not in self.user_recommendation_cache:
            self.user_recommendation_cache[user_id] = set()
        self.user_recommendation_cache[user_id].update([r.get("id") for r in recommendations])
        
        # Limitar tamaño del caché para cada usuario
        if len(self.user_recommendation_cache[user_id]) > 100:
            # Convertir a lista, recortar y volver a conjunto
            user_recs = list(self.user_recommendation_cache[user_id])
            self.user_recommendation_cache[user_id] = set(user_recs[-100:])
        
        # Calcular diversidad interna (categorías únicas / total)
        internal_diversity = len(categories) / len(recommendations) if recommendations else 0
        
        # Crear registro de métrica
        metric_entry = {
            "timestamp": timestamp,
            "user_id": user_id,
            "product_id": product_id,
            "request_parameters": request_data,
            "response_time_ms": response_time_ms,
            "recommendation_count": len(recommendations),
            "recommendation_types": dict(recommendation_types),
            "category_distribution": dict(categories),
            "internal_diversity": internal_diversity,
            "novelty_score": novelty_score
        }
        
        # Registrar métrica
        if self.log_to_file:
            self._log_to_file(metric_entry)
        
        # Log para depuración
        logger.debug(f"Métricas registradas: {len(recommendations)} recomendaciones, "
                    f"{response_time_ms:.2f}ms, diversidad={internal_diversity:.2f}, "
                    f"novedad={novelty_score:.2f}")
    
    def record_user_interaction(
        self,
        user_id: str,
        product_id: str,
        event_type: str,
        recommendation_id: Optional[str] = None
    ):
        """
        Registra métricas para una interacción de usuario con un producto.
        Esto permite evaluar la efectividad de las recomendaciones.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto
            event_type: Tipo de evento (view, add-to-cart, purchase)
            recommendation_id: ID de la recomendación (si el producto fue recomendado)
        """
        timestamp = datetime.now().isoformat()
        
        metric_entry = {
            "timestamp": timestamp,
            "user_id": user_id,
            "product_id": product_id,
            "event_type": event_type,
            "recommendation_id": recommendation_id,
            "conversion_type": "recommended" if recommendation_id else "organic"
        }
        
        # Registrar métrica
        if self.log_to_file:
            self._log_to_file(metric_entry)
    
    def get_aggregated_metrics(self) -> Dict[str, Any]:
        """
        Devuelve un resumen de las métricas agregadas.
        
        Returns:
            Dict: Métricas agregadas del sistema de recomendaciones
        """
        if not self.request_count:
            return {"status": "No hay suficientes datos para generar métricas"}
        
        # Calcular estadísticas de tiempo de respuesta
        avg_response_time = sum(self.recommendation_times) / len(self.recommendation_times) if self.recommendation_times else 0
        max_response_time = max(self.recommendation_times) if self.recommendation_times else 0
        
        # Calcular distribución de tipos de recomendación
        recommendation_dist = {k: v / sum(self.recommendation_counts.values()) 
                              for k, v in self.recommendation_counts.items()}
        
        # Calcular diversidad global de categorías (normalizada)
        total_recommendations = sum(self.category_diversity.values())
        category_dist = {k: v / total_recommendations 
                        for k, v in self.category_diversity.most_common(10)}
        
        # Resultado
        return {
            "total_requests": self.request_count,
            "average_response_time_ms": avg_response_time,
            "max_response_time_ms": max_response_time,
            "recommendation_type_distribution": recommendation_dist,
            "top_10_category_distribution": category_dist,
            "fallback_rate": recommendation_dist.get("fallback", 0) + 
                            recommendation_dist.get("popular_fallback", 0) + 
                            recommendation_dist.get("diverse_fallback", 0) +
                            recommendation_dist.get("personalized_fallback", 0)
        }
    
    def _log_to_file(self, metric_entry: Dict):
        """
        Guarda una entrada de métrica en el archivo de log.
        
        Args:
            metric_entry: Entrada de métrica a guardar
        """
        try:
            with open(self.metrics_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(metric_entry) + "\n")
        except Exception as e:
            logger.error(f"Error al guardar métrica en archivo: {str(e)}")


# Instancia global de métricas
recommendation_metrics = RecommendationMetrics(
    log_to_file=True,
    metrics_file="logs/recommendation_metrics.jsonl"
)


def time_function(func):
    """
    Decorador para medir el tiempo de ejecución de una función.
    
    Args:
        func: Función a medir
        
    Returns:
        Función decorada
    """
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000  # Convertir a ms
        return result, execution_time
    return wrapper


def analyze_metrics_file(metrics_file: str = "logs/recommendation_metrics.jsonl") -> Dict:
    """
    Analiza un archivo de métricas para generar un informe detallado.
    
    Args:
        metrics_file: Ruta al archivo de métricas
        
    Returns:
        Dict: Informe de análisis de métricas
    """
    if not os.path.exists(metrics_file):
        return {"status": "error", "message": f"Archivo de métricas no encontrado: {metrics_file}"}
    
    try:
        metrics = []
        with open(metrics_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    metrics.append(json.loads(line))
        
        if not metrics:
            return {"status": "error", "message": "No hay métricas registradas en el archivo"}
        
        # Separar por tipo de métrica
        recommendation_metrics = [m for m in metrics if "recommendation_count" in m]
        interaction_metrics = [m for m in metrics if "event_type" in m]
        
        # Análisis de recomendaciones
        rec_analysis = analyze_recommendation_metrics(recommendation_metrics) if recommendation_metrics else {}
        
        # Análisis de interacciones
        int_analysis = analyze_interaction_metrics(interaction_metrics, recommendation_metrics) if interaction_metrics else {}
        
        return {
            "status": "success",
            "total_records": len(metrics),
            "recommendation_metrics": len(recommendation_metrics),
            "interaction_metrics": len(interaction_metrics),
            "recommendation_analysis": rec_analysis,
            "interaction_analysis": int_analysis,
            "timeframe": {
                "start": metrics[0].get("timestamp", "unknown"),
                "end": metrics[-1].get("timestamp", "unknown")
            }
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Error al analizar métricas: {str(e)}"}


def analyze_recommendation_metrics(metrics: List[Dict]) -> Dict:
    """
    Analiza métricas específicas de recomendaciones.
    
    Args:
        metrics: Lista de métricas de recomendaciones
        
    Returns:
        Dict: Análisis de métricas de recomendaciones
    """
    if not metrics:
        return {}
    
    # Tiempos de respuesta
    response_times = [m.get("response_time_ms", 0) for m in metrics]
    avg_response_time = sum(response_times) / len(response_times)
    
    # Tipos de recomendación
    recommendation_types = Counter()
    for m in metrics:
        for rec_type, count in m.get("recommendation_types", {}).items():
            recommendation_types[rec_type] += count
    
    total_recommendations = sum(recommendation_types.values())
    type_distribution = {k: (v / total_recommendations if total_recommendations else 0) 
                        for k, v in recommendation_types.items()}
    
    # Diversidad
    avg_diversity = sum(m.get("internal_diversity", 0) for m in metrics) / len(metrics)
    
    # Novedad
    avg_novelty = sum(m.get("novelty_score", 0) for m in metrics) / len(metrics)
    
    # Categorías
    categories = Counter()
    for m in metrics:
        for category, count in m.get("category_distribution", {}).items():
            categories[category] += count
    
    top_categories = categories.most_common(5)
    
    return {
        "count": len(metrics),
        "response_time": {
            "avg_ms": avg_response_time,
            "min_ms": min(response_times),
            "max_ms": max(response_times)
        },
        "recommendation_types": dict(recommendation_types),
        "type_distribution": type_distribution,
        "avg_diversity": avg_diversity,
        "avg_novelty": avg_novelty,
        "top_categories": dict(top_categories)
    }


def analyze_interaction_metrics(interaction_metrics: List[Dict], 
                              recommendation_metrics: List[Dict]) -> Dict:
    """
    Analiza métricas de interacción y su relación con las recomendaciones.
    
    Args:
        interaction_metrics: Lista de métricas de interacción
        recommendation_metrics: Lista de métricas de recomendaciones
        
    Returns:
        Dict: Análisis de métricas de interacción
    """
    if not interaction_metrics:
        return {}
    
    # Tipos de eventos
    event_types = Counter([m.get("event_type", "unknown") for m in interaction_metrics])
    
    # Tasa de conversión por tipo
    conversion_types = Counter([m.get("conversion_type", "unknown") for m in interaction_metrics])
    
    # Análisis por tipo de evento
    event_analysis = {}
    for event_type in event_types:
        events = [m for m in interaction_metrics if m.get("event_type") == event_type]
        recommended = [m for m in events if m.get("conversion_type") == "recommended"]
        organic = [m for m in events if m.get("conversion_type") == "organic"]
        
        event_analysis[event_type] = {
            "count": len(events),
            "recommended_count": len(recommended),
            "organic_count": len(organic),
            "recommended_rate": len(recommended) / len(events) if events else 0
        }
    
    # Crear mapa de recomendaciones por usuario
    user_recommendations = {}
    for m in recommendation_metrics:
        user_id = m.get("user_id")
        if user_id not in user_recommendations:
            user_recommendations[user_id] = set()
        
        # Añadir productos recomendados
        for rec in m.get("recommendations", []):
            rec_id = rec.get("id")
            if rec_id:
                user_recommendations[user_id].add(rec_id)
    
    # Analizar conversiones de recomendaciones
    converted_recommendations = 0
    total_applicable_interactions = 0
    
    for m in interaction_metrics:
        user_id = m.get("user_id")
        product_id = m.get("product_id")
        
        if user_id in user_recommendations and product_id:
            total_applicable_interactions += 1
            if product_id in user_recommendations[user_id]:
                converted_recommendations += 1
    
    conversion_rate = (converted_recommendations / total_applicable_interactions 
                      if total_applicable_interactions else 0)
    
    return {
        "count": len(interaction_metrics),
        "event_types": dict(event_types),
        "conversion_types": dict(conversion_types),
        "event_analysis": event_analysis,
        "overall_conversion_rate": conversion_rate
    }
