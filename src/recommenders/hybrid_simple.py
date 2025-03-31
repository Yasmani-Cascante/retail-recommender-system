"""
Implementación del recomendador híbrido con nuestro SimpleContentRecommender
y RetailAPIRecommender.
"""
from typing import List, Dict, Optional
import logging
from .simple_content_based import SimpleContentRecommender
from .retail_api import RetailAPIRecommender

class HybridRecommender:
    """
    Recomendador híbrido que combina recomendaciones basadas en contenido
    con recomendaciones basadas en comportamiento de Google Cloud Retail API.
    """
    
    def __init__(
        self,
        content_recommender: SimpleContentRecommender,
        retail_recommender: RetailAPIRecommender,
        content_weight: float = 0.5
    ):
        """
        Inicializa el recomendador híbrido.
        
        Args:
            content_recommender: Instancia del recomendador basado en contenido
            retail_recommender: Instancia del recomendador basado en Retail API
            content_weight: Peso para las recomendaciones basadas en contenido (0-1)
                            donde 0 = solo Google Retail API y 1 = solo basado en contenido
        """
        self.content_recommender = content_recommender
        self.retail_recommender = retail_recommender
        self.content_weight = content_weight
        
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        n_recommendations: int = 5,
        content_weight: Optional[float] = None
    ) -> List[Dict]:
        """
        Obtiene recomendaciones híbridas combinando ambos enfoques.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            n_recommendations: Número de recomendaciones a devolver
            content_weight: Peso para las recomendaciones basadas en contenido (anula el valor por defecto)
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        # Usar el peso proporcionado o el valor por defecto
        weight = content_weight if content_weight is not None else self.content_weight
        
        # Obtener recomendaciones de ambos sistemas
        content_recs = []
        retail_recs = []
        
        # Si hay un product_id, obtener recomendaciones basadas en contenido
        if product_id:
            try:
                content_recs = self.content_recommender.recommend(product_id, n_recommendations)
                logging.info(f"Obtenidas {len(content_recs)} recomendaciones basadas en contenido para producto {product_id}")
            except Exception as e:
                logging.error(f"Error al obtener recomendaciones basadas en contenido: {str(e)}")
        
        # Intentar obtener recomendaciones de Retail API
        try:
            retail_recs = await self.retail_recommender.get_recommendations(
                user_id=user_id,
                product_id=product_id,
                n_recommendations=n_recommendations
            )
            logging.info(f"Obtenidas {len(retail_recs)} recomendaciones de Retail API para usuario {user_id}")
        except Exception as e:
            logging.error(f"Error al obtener recomendaciones de Retail API: {str(e)}")
        
        # Si no hay product_id y tampoco recomendaciones de Retail API,
        # usar recomendaciones basadas en productos populares o aleatorios
        if not product_id and not retail_recs and not content_recs:
            logging.info("Usando recomendaciones de fallback")
            return self._get_fallback_recommendations(n_recommendations)
            
        # Si hay product_id, combinar ambas recomendaciones
        if product_id:
            recommendations = self._combine_recommendations(
                content_recs,
                retail_recs,
                n_recommendations,
                weight
            )
            return recommendations
        
        # Si no hay product_id, usar solo recomendaciones de Retail API
        return retail_recs
        
    def _combine_recommendations(
        self,
        content_recs: List[Dict],
        retail_recs: List[Dict],
        n_recommendations: int,
        content_weight: float
    ) -> List[Dict]:
        """
        Combina las recomendaciones de ambos sistemas usando los pesos definidos.
        
        Args:
            content_recs: Recomendaciones basadas en contenido
            retail_recs: Recomendaciones de Retail API
            n_recommendations: Número de recomendaciones a devolver
            content_weight: Peso para el recomendador basado en contenido
            
        Returns:
            List[Dict]: Lista combinada de recomendaciones
        """
        # Crear un diccionario para trackear scores combinados
        combined_scores = {}
        
        # Procesar recomendaciones basadas en contenido
        for rec in content_recs:
            product_id = rec["id"]
            combined_scores[product_id] = {
                **rec,
                "final_score": rec.get("similarity_score", 0) * content_weight,
                "sources": ["content"]
            }
            
        # Procesar recomendaciones de Retail API
        for rec in retail_recs:
            product_id = rec["id"]
            if product_id in combined_scores:
                combined_scores[product_id]["final_score"] += (
                    rec.get("score", 0) * (1 - content_weight)
                )
                combined_scores[product_id]["sources"].append("retail_api")
            else:
                combined_scores[product_id] = {
                    **rec,
                    "final_score": rec.get("score", 0) * (1 - content_weight),
                    "sources": ["retail_api"]
                }
                
        # Ordenar por score final y devolver los top N
        sorted_recs = sorted(
            combined_scores.values(),
            key=lambda x: x["final_score"],
            reverse=True
        )
        
        return sorted_recs[:n_recommendations]
    
    def _get_fallback_recommendations(self, n_recommendations: int = 5) -> List[Dict]:
        """
        Proporciona recomendaciones de respaldo cuando no se pueden obtener
        recomendaciones de ninguna de las fuentes principales.
        
        Args:
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        # Verificar si el recomendador de contenido está disponible
        if not hasattr(self.content_recommender, 'products') or not self.content_recommender.products:
            # Si no hay datos, devolver lista vacía
            return []
        
        # Obtener todos los productos disponibles
        all_products = self.content_recommender.products
        
        # Seleccionar productos (podría ser por popularidad, fecha, etc.)
        # Por ahora, simplemente tomamos los primeros 'n'
        selected_products = all_products[:min(n_recommendations, len(all_products))]
        
        # Añadir información adicional
        return [
            {
                **product,
                "score": 0.5,  # Score arbitrario
                "recommendation_type": "fallback"  # Indicar que es una recomendación de respaldo
            }
            for product in selected_products
        ]
        
    async def record_user_event(
        self,
        user_id: str,
        event_type: str,
        product_id: Optional[str] = None
    ):
        """
        Registra eventos de usuario para mejorar las recomendaciones futuras.
        
        Args:
            user_id: ID del usuario
            event_type: Tipo de evento (view, add-to-cart, purchase)
            product_id: ID del producto (opcional)
        """
        return await self.retail_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id
        )
