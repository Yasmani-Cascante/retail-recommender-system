from google.cloud import recommendations_ai_v1beta1
from google.cloud.recommendations_ai_v1beta1.services.prediction_service import PredictionServiceClient
from typing import List, Dict, Optional
import os
import json
from datetime import datetime

class GoogleRecommender:
    def __init__(self, project_id: str, location: str, catalog_id: str, placement_id: str):
        """
        Inicializa el recomendador de Google Recommendations AI.
        
        Args:
            project_id (str): ID del proyecto de Google Cloud
            location (str): Ubicación del catálogo (ej: 'global')
            catalog_id (str): ID del catálogo de productos
            placement_id (str): ID del placement configurado en Google Recommendations AI
        """
        self.client = PredictionServiceClient()
        self.placement = f"projects/{project_id}/locations/{location}/catalogs/{catalog_id}/placements/{placement_id}"
        
    async def get_recommendations(self, 
                                user_id: str, 
                                product_id: Optional[str] = None,
                                n_recommendations: int = 5) -> List[Dict]:
        """
        Obtiene recomendaciones personalizadas usando Google Recommendations AI.
        
        Args:
            user_id (str): ID del usuario
            product_id (Optional[str]): ID del producto para recomendaciones similares
            n_recommendations (int): Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        try:
            user_event = {
                "eventType": "detail-page-view" if product_id else "home-page-view",
                "userInfo": {
                    "visitorId": user_id,
                },
                "eventDetail": {
                    "recommendationToken": "",  # Token from previous recommendations if available
                },
                "productEventDetail": {
                    "productDetails": [{
                        "id": product_id,
                        "eventTime": datetime.utcnow().isoformat() + "Z"
                    }] if product_id else []
                }
            }

            request = recommendations_ai_v1beta1.PredictRequest(
                placement=self.placement,
                user_event=user_event
            )
            
            response = await self.client.predict(request)
            
            # Procesar y formatear las recomendaciones
            recommendations = []
            for result in response.results[:n_recommendations]:
                recommendations.append({
                    "id": result.id,
                    "name": result.metadata.get("name", ""),
                    "description": result.metadata.get("description", ""),
                    "price": float(result.metadata.get("price", 0)),
                    "category": result.metadata.get("category", ""),
                    "confidence_score": result.metadata.get("score", 0)
                })
                
            return recommendations
            
        except Exception as e:
            print(f"Error getting recommendations from Google AI: {str(e)}")
            return []
            
    async def record_user_event(self, user_id: str, event_type: str, product_id: Optional[str] = None):
        """
        Registra eventos de usuario para mejorar las recomendaciones futuras.
        
        Args:
            user_id (str): ID del usuario
            event_type (str): Tipo de evento ('detail-page-view', 'add-to-cart', 'purchase', etc.)
            product_id (Optional[str]): ID del producto involucrado en el evento
        """
        try:
            user_event = {
                "eventType": event_type,
                "userInfo": {
                    "visitorId": user_id,
                },
                "productEventDetail": {
                    "productDetails": [{
                        "id": product_id,
                        "eventTime": datetime.utcnow().isoformat() + "Z"
                    }] if product_id else []
                }
            }
            
            # Aquí iría el código para registrar el evento en Google Recommendations AI
            # Usando el método write_user_event del cliente
            pass
            
        except Exception as e:
            print(f"Error recording user event: {str(e)}")
