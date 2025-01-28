from google.cloud import retail_v2
# from google.cloud.retail_v2 import ProductService, ServingConfig
from google.cloud.retail_v2 import ProductServiceClient, ServingConfig
from google.cloud.retail_v2.types import Product, PredictRequest, PredictResponse
from typing import List, Dict, Optional
from datetime import datetime
import asyncio
import os

class RetailAPIRecommender:
    def __init__(
        self,
        project_number: str,
        location: str,
        catalog: str = "default_catalog",
        serving_config_id: str = "default_config"
    ):
        """
        Inicializa el recomendador usando Google Cloud Retail API.
        
        Args:
            project_number: Número del proyecto de Google Cloud
            location: Ubicación del catálogo (ej: 'global')
            catalog: ID del catálogo (default: 'default_catalog')
            serving_config_id: ID de la configuración de servicio
        """
        self.project_number = project_number
        self.location = location
        self.catalog = catalog
        self.serving_config_id = serving_config_id
        
        # Inicializar clientes
        self.predict_client = retail_v2.PredictionServiceClient()
        self.product_client = retail_v2.ProductServiceClient()
        
        # Construir la ruta del placement
        self.placement = (
            f"projects/{project_number}/locations/{location}"
            f"/catalogs/{catalog}/servingConfigs/{serving_config_id}"
        )
        
    def _convert_product_to_retail(self, product: Dict) -> Product:
        """
        Convierte un producto de nuestro formato al formato de Retail API.
        """
        return Product(
            id=product["id"],
            title=product["name"],
            description=product["description"],
            price_info={
                "price": product["price"],
                "currency_code": "EUR"
            },
            categories=[product["category"]],
            attributes={
                "material": {"text": [product["attributes"]["material"]]},
                "style": {"text": [product["attributes"]["style"]]},
                "occasions": {"text": product["attributes"]["occasion"]}
            }
        )
        
    async def import_catalog(self, products: List[Dict]):
        """
        Importa productos al catálogo de Retail API.
        """
        try:
            # Convertir productos al formato de Retail API
            retail_products = [
                self._convert_product_to_retail(product)
                for product in products
            ]
            
            # Crear la solicitud de importación
            parent = (
                f"projects/{self.project_number}/locations/{self.location}"
                f"/catalogs/{self.catalog}"
            )
            
            import_request = retail_v2.ImportProductsRequest(
                parent=parent,
                input_config=retail_v2.ImportProductsRequest.InputConfig(
                    product_inline_source=retail_v2.ProductInlineSource(
                        products=retail_products
                    )
                )
            )
            
            # Realizar la importación
            operation = self.product_client.import_products(request=import_request)
            result = operation.result()  # Esperar a que termine
            
            return {
                "status": "success",
                "products_imported": len(retail_products),
                "operation_details": str(result)
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
            
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        n_recommendations: int = 5
    ) -> List[Dict]:
        """
        Obtiene recomendaciones personalizadas usando Retail API.
        """
        try:
            # Construir el contexto de usuario
            user_event = {
                "user_info": {"visitor_id": user_id},
                "event_type": "detail-page-view" if product_id else "home-page-view",
                "product_details": [{"product": {"id": product_id}}] if product_id else []
            }
            
            # Crear la solicitud de predicción
            request = PredictRequest(
                placement=self.placement,
                user_event=user_event,
                page_size=n_recommendations,
                params={"return_product": True}
            )
            
            # Obtener predicciones
            response = self.predict_client.predict(request)
            
            # Procesar y formatear las recomendaciones
            recommendations = []
            for result in response.results:
                product = result.product
                recommendations.append({
                    "id": product.id,
                    "name": product.title,
                    "description": product.description,
                    "price": product.price_info.price,
                    "category": product.categories[0] if product.categories else "",
                    "attributes": {
                        "material": product.attributes.get("material", {}).get("text", []),
                        "style": product.attributes.get("style", {}).get("text", []),
                        "occasion": product.attributes.get("occasions", {}).get("text", [])
                    },
                    "score": result.metadata.get("score", 0.0)
                })
                
            return recommendations
            
        except Exception as e:
            print(f"Error getting recommendations: {str(e)}")
            return []
            
    async def record_user_event(
        self,
        user_id: str,
        event_type: str,
        product_id: Optional[str] = None
    ):
        """
        Registra eventos de usuario para mejorar las recomendaciones.
        """
        try:
            # Construir el evento
            event = {
                "event_type": event_type,
                "visitor_id": user_id,
                "event_time": datetime.utcnow().isoformat() + "Z"
            }
            
            if product_id:
                event["product_details"] = [{
                    "product": {"id": product_id},
                    "quantity": 1
                }]
                
            # Crear la solicitud
            parent = (
                f"projects/{self.project_number}/locations/{self.location}"
                f"/catalogs/{self.catalog}"
            )
            
            request = retail_v2.UserEvent(
                parent=parent,
                **event
            )
            
            # Registrar el evento
            self.predict_client.write_user_event(user_event=request)
            
            return {"status": "success", "message": "Event recorded"}
            
        except Exception as e:
            print(f"Error recording user event: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }