from google.cloud import retail_v2
from google.cloud.retail_v2 import ProductServiceClient, ServingConfig
from google.cloud.retail_v2.types import Product, PredictRequest, PredictResponse
from typing import List, Dict, Optional
from datetime import datetime
import asyncio
import os
import logging

class RetailAPIRecommender:
    def __init__(
        self,
        project_number: str,
        location: str,
        catalog: str = "default_catalog",
        serving_config_id: str = "default_config"
    ):
        self.project_number = project_number
        self.location = location
        self.catalog = catalog
        self.serving_config_id = serving_config_id
        
        self.predict_client = retail_v2.PredictionServiceClient()
        self.product_client = retail_v2.ProductServiceClient()
        
        self.placement = f"projects/{project_number}/locations/{location}/catalogs/{catalog}/servingConfigs/{serving_config_id}"
    
    def _process_predictions(self, response) -> List[Dict]:
        recommendations = []
        try:
            for result in response.results:
                if result.product:
                    recommendations.append({
                        "id": result.product.id,
                        "title": result.product.title,
                        "description": result.product.description or "",
                        "price": result.product.price_info.price if result.product.price_info else 0.0,
                        "category": result.product.categories[0] if result.product.categories else "",
                        "score": float(result.metadata.get("predictScore", 0.0))
                    })
            return recommendations
        except Exception as e:
            logging.error(f"Error processing predictions: {str(e)}")
            return []
    def __init__(
        self,
        project_number: str,
        location: str,
        catalog: str = "default_catalog",
        serving_config_id: str = "default_config"
    ):
        self.project_number = project_number
        self.location = location
        self.catalog = catalog
        self.serving_config_id = serving_config_id
        
        self.predict_client = retail_v2.PredictionServiceClient()
        self.product_client = retail_v2.ProductServiceClient()
        
        self.placement = (
            f"projects/{project_number}/locations/{location}"
            f"/catalogs/{catalog}/servingConfigs/{serving_config_id}"
        )

    async def process_shopify_orders(self, orders: List[Dict], user_id: str):
        """
        Procesa órdenes de Shopify y las registra como eventos de usuario.
        """
        try:
            events_recorded = 0
            for order in orders:
                # Registrar evento de compra
                for item in order.get('products', []):
                    await self.record_user_event(
                        user_id=user_id,
                        event_type='purchase',
                        product_id=str(item.get('product_id'))
                    )
                    events_recorded += 1
                    
                    # Registrar evento de vista
                    await self.record_user_event(
                        user_id=user_id,
                        event_type='detail-page-view',
                        product_id=str(item.get('product_id'))
                    )
                    events_recorded += 1

            return {
                "status": "success", 
                "events_recorded": events_recorded,
                "orders_processed": len(orders)
            }
        except Exception as e:
            logging.error(f"Error processing Shopify orders: {str(e)}")
            return {"status": "error", "error": str(e)}
        
    def _convert_product_to_retail(self, product: Dict) -> Product:
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
        try:
            retail_products = [
                self._convert_product_to_retail(product)
                for product in products
            ]
            
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
            
            operation = self.product_client.import_products(request=import_request)
            result = operation.result()
            
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
        try:
            parent = f"projects/{self.project_number}/locations/{self.location}/catalogs/{self.catalog}"
            
            user_event = retail_v2.UserEvent(
                event_type="home-page-view",
                visitor_id=str(user_id),
                event_time=datetime.utcnow()
            )

            logging.info(f"User event: {str(user_event)}")
            logging.info(f"Placement: {self.placement}")

            request = retail_v2.PredictRequest(
                placement=self.placement,
                user_event=user_event,
                page_size=n_recommendations,
                validate_only=True
            )

            logging.info(f"Request: {str(request)}")

            try:
                response = self.predict_client.predict(request)
                logging.info(f"Validation successful")
                
                request.validate_only = False
                response = self.predict_client.predict(request)
                
                return self._process_predictions(response)
            except Exception as e:
                logging.error(f"API Error: {str(e)}")
                if hasattr(e, 'details'):
                    logging.error(f"Error details: {e.details}")
                return []

        except Exception as e:
            logging.error(f"Error in get_recommendations: {str(e)}")
            return []
            
        except Exception as e:
            logging.error(f"Error getting recommendations: {str(e)}")
            return []
            
    async def record_user_event(
        self,
        user_id: str,
        event_type: str,
        product_id: Optional[str] = None
    ):
        try:
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
                
            parent = (
                f"projects/{self.project_number}/locations/{self.location}"
                f"/catalogs/{self.catalog}"
            )
            
            request = retail_v2.UserEvent(
                parent=parent,
                **event
            )
            
            self.predict_client.write_user_event(user_event=request)
            
            return {"status": "success", "message": "Event recorded"}
            
        except Exception as e:
            logging.error(f"Error recording user event: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }