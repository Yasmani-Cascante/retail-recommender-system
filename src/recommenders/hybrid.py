from typing import List, Dict, Optional
from .content_based import ContentBasedRecommender
from .retail_api import RetailAPIRecommender

class HybridRecommender:
    def __init__(
        self,
        content_recommender: ContentBasedRecommender,
        retail_recommender: RetailAPIRecommender,
        content_weight: float = 0.5
    ):
        """
        Inicializa el recomendador híbrido.
        
        Args:
            content_recommender: Instancia de ContentBasedRecommender
            retail_recommender: Instancia de RetailAPIRecommender
            content_weight: Peso para las recomendaciones basadas en contenido (0-1)
        """
        self.content_recommender = content_recommender
        self.retail_recommender = retail_recommender
        self.content_weight = content_weight
        
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        n_recommendations: int = 5
    ) -> List[Dict]:
        """
        Obtiene recomendaciones híbridas combinando ambos enfoques.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        # Obtener recomendaciones de ambos sistemas
        content_recs = (
            self.content_recommender.recommend(product_id, n_recommendations)
            if product_id else []
        )
        
        retail_recs = await self.retail_recommender.get_recommendations(
            user_id=user_id,
            product_id=product_id,
            n_recommendations=n_recommendations
        )
        
        # Si no hay producto_id, usar solo recomendaciones de Retail API
        if not product_id:
            return retail_recs
            
        # Si hay producto_id, combinar ambas recomendaciones
        recommendations = self._combine_recommendations(
            content_recs,
            retail_recs,
            n_recommendations
        )
        
        return recommendations
        
    def _combine_recommendations(
        self,
        content_recs: List[Dict],
        retail_recs: List[Dict],
        n_recommendations: int
    ) -> List[Dict]:
        """
        Combina las recomendaciones de ambos sistemas usando los pesos definidos.
        
        Args:
            content_recs: Recomendaciones basadas en contenido
            retail_recs: Recomendaciones de Retail API
            n_recommendations: Número de recomendaciones a devolver
            
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
                "final_score": rec.get("similarity_score", 0) * self.content_weight
            }
            
        # Procesar recomendaciones de Retail API
        for rec in retail_recs:
            product_id = rec["id"]
            if product_id in combined_scores:
                combined_scores[product_id]["final_score"] += (
                    rec.get("score", 0) * (1 - self.content_weight)
                )
            else:
                combined_scores[product_id] = {
                    **rec,
                    "final_score": rec.get("score", 0) * (1 - self.content_weight)
                }
                
        # Ordenar por score final y devolver los top N
        sorted_recs = sorted(
            combined_scores.values(),
            key=lambda x: x["final_score"],
            reverse=True
        )
        
        return sorted_recs[:n_recommendations]
        
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
            event_type: Tipo de evento
            product_id: ID del producto (opcional)
        """
        return await self.retail_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id
        )