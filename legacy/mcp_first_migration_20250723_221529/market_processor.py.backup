"""
Market Recommendation Processor - Procesador de Recomendaciones con Adaptación de Mercado
=======================================================================================

Módulo que procesa las recomendaciones del sistema para aplicar conversión de moneda
y traducción básica según el mercado objetivo.
"""

import logging
import time
from typing import Dict, List, Any, Optional
from src.api.utils.market_utils import adapt_product_for_market

logger = logging.getLogger(__name__)

class MarketRecommendationProcessor:
    """
    Procesador que adapta recomendaciones para mercados específicos.
    Aplica conversión de moneda y traducción básica.
    """
    
    def __init__(self):
        """Inicializar el procesador"""
        self.processed_count = 0
        self.adaptation_stats = {
            "total_processed": 0,
            "currency_conversions": 0,
            "translations_applied": 0,
            "adaptations_by_market": {}
        }
    
    def process_recommendations(
        self,
        recommendations: List[Dict[str, Any]],
        market_id: str = "US",
        source: str = "unknown"
    ) -> List[Dict[str, Any]]:
        """
        Procesa una lista de recomendaciones para adaptarlas al mercado.
        
        Args:
            recommendations: Lista de recomendaciones originales
            market_id: ID del mercado objetivo
            source: Fuente de las recomendaciones
            
        Returns:
            Lista de recomendaciones adaptadas
        """
        start_time = time.time()
        
        try:
            adapted_recommendations = []
            
            for i, rec in enumerate(recommendations):
                try:
                    # Adaptar producto individual
                    adapted_rec = self._adapt_single_recommendation(rec, market_id, source)
                    adapted_recommendations.append(adapted_rec)
                    
                except Exception as e:
                    logger.error(f"Error adaptando recomendación {i}: {e}")
                    # En caso de error, usar recomendación original
                    adapted_recommendations.append(rec)
            
            # Actualizar estadísticas
            self._update_stats(adapted_recommendations, market_id)
            
            processing_time = (time.time() - start_time) * 1000
            logger.info(f"Processed {len(adapted_recommendations)} recommendations for market {market_id} in {processing_time:.2f}ms")
            
            return adapted_recommendations
            
        except Exception as e:
            logger.error(f"Error general en procesamiento de recomendaciones: {e}")
            return recommendations  # Retornar originales en caso de error
    
    def _adapt_single_recommendation(
        self,
        recommendation: Dict[str, Any],
        market_id: str,
        source: str
    ) -> Dict[str, Any]:
        """
        Adapta una recomendación individual para el mercado.
        
        Args:
            recommendation: Recomendación original
            market_id: ID del mercado
            source: Fuente de la recomendación
            
        Returns:
            Recomendación adaptada
        """
        try:
            # Crear copia para no modificar el original
            adapted = recommendation.copy()
            
            # Verificar si ya fue procesada
            if adapted.get("market_adapted") and adapted.get("market_id") == market_id:
                logger.debug(f"Recomendación {adapted.get('id', 'unknown')} ya adaptada para {market_id}")
                return adapted
            
            # 1. Detectar estructura de datos
            if "product" in adapted:
                # Estructura MCP con producto anidado
                product_data = adapted["product"]
                adapted_product = adapt_product_for_market(product_data, market_id)
                adapted["product"] = adapted_product
                
                # Propagar datos del producto al nivel superior para compatibilidad
                adapted.update({
                    "id": adapted_product.get("id", adapted.get("id", "unknown")),
                    "title": adapted_product.get("title", adapted.get("title", "Producto")),
                    "description": adapted_product.get("description", adapted.get("description", "")),
                    "price": adapted_product.get("price", adapted.get("price", 0.0)),
                    "currency": adapted_product.get("currency", "USD"),
                    "category": adapted_product.get("category", adapted.get("category", "")),
                })
                
            else:
                # Estructura plana - adaptar directamente
                adapted = adapt_product_for_market(adapted, market_id)
            
            # 2. Añadir metadatos de adaptación
            adapted.update({
                "market_id": market_id,
                "processing_source": source,
                "adapted_at": time.time(),
                "adaptation_version": "1.0"
            })
            
            # 3. Validar campos requeridos después de adaptación
            self._validate_adapted_recommendation(adapted)
            
            return adapted
            
        except Exception as e:
            logger.error(f"Error en adaptación individual: {e}")
            return recommendation
    
    def _validate_adapted_recommendation(self, recommendation: Dict[str, Any]) -> None:
        """
        Valida que una recomendación adaptada tenga todos los campos requeridos.
        
        Args:
            recommendation: Recomendación a validar
        """
        required_fields = ["id", "title", "price", "currency"]
        missing_fields = []
        
        for field in required_fields:
            if field not in recommendation or recommendation[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            logger.warning(f"Campos faltantes en recomendación: {missing_fields}")
            # Llenar con valores por defecto
            defaults = {
                "id": "unknown",
                "title": "Producto",
                "price": 0.0,
                "currency": "USD"
            }
            for field in missing_fields:
                recommendation[field] = defaults.get(field, "")
    
    def _update_stats(self, recommendations: List[Dict[str, Any]], market_id: str) -> None:
        """
        Actualiza estadísticas de procesamiento.
        
        Args:
            recommendations: Recomendaciones procesadas
            market_id: ID del mercado
        """
        try:
            self.adaptation_stats["total_processed"] += len(recommendations)
            
            # Contar adaptaciones por mercado
            if market_id not in self.adaptation_stats["adaptations_by_market"]:
                self.adaptation_stats["adaptations_by_market"][market_id] = 0
            self.adaptation_stats["adaptations_by_market"][market_id] += len(recommendations)
            
            # Contar conversiones de moneda
            currency_conversions = sum(1 for rec in recommendations if rec.get("exchange_rate"))
            self.adaptation_stats["currency_conversions"] += currency_conversions
            
            # Contar traducciones
            translations = sum(1 for rec in recommendations if rec.get("original_title") or rec.get("original_description"))
            self.adaptation_stats["translations_applied"] += translations
            
        except Exception as e:
            logger.error(f"Error actualizando estadísticas: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas de procesamiento.
        
        Returns:
            Diccionario con estadísticas
        """
        return self.adaptation_stats.copy()
    
    def reset_stats(self) -> None:
        """Reinicia las estadísticas"""
        self.adaptation_stats = {
            "total_processed": 0,
            "currency_conversions": 0,
            "translations_applied": 0,
            "adaptations_by_market": {}
        }

# Instancia global del procesador
market_processor = MarketRecommendationProcessor()

def process_recommendations_for_market(
    recommendations: List[Dict[str, Any]],
    market_id: str = "US",
    source: str = "unknown"
) -> List[Dict[str, Any]]:
    """
    Función de conveniencia para procesar recomendaciones.
    
    Args:
        recommendations: Lista de recomendaciones
        market_id: ID del mercado
        source: Fuente de las recomendaciones
        
    Returns:
        Lista de recomendaciones adaptadas
    """
    return market_processor.process_recommendations(recommendations, market_id, source)

def get_processing_stats() -> Dict[str, Any]:
    """
    Obtiene estadísticas globales de procesamiento.
    
    Returns:
        Estadísticas de procesamiento
    """
    return market_processor.get_stats()
