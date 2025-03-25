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
        
        self.placement = (
            f"projects/{project_number}/locations/{location}"
            f"/catalogs/{catalog}/servingConfigs/{serving_config_id}"
        )
    
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
        # Extracción segura de datos con valores predeterminados
        product_id = str(product.get("id", ""))
        title = product.get("title", "")
        description = product.get("body_html", "").replace("<p>", "").replace("</p>", "")
        
        # Extracción de precio del primer variante si existe
        price = 0.0
        if product.get("variants") and len(product["variants"]) > 0:
            price_str = product["variants"][0].get("price", "0")
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                price = 0.0
        
        # Categoría del producto
        category = product.get("product_type", "")
        
        # Construcción del objeto Product
        return Product(
            id=product_id,
            title=title,
            description=description,
            price_info={
                "price": price,
                "currency_code": "COP"
            },
            categories=[category] if category else [],
            # Atributos opcionales basados en etiquetas
            attributes={
                "tags": {"text": product.get("tags", "").split(", ") if isinstance(product.get("tags", ""), str) else []}
            } if product.get("tags") else None
        )
        
    async def import_catalog(self, products: List[Dict]):
        try:
            # Agregamos log para depuración
            logging.info(f"Importando {len(products)} productos al catálogo de Google Retail API")
            if products and len(products) > 0:
                logging.debug(f"Estructura del primer producto: {products[0].keys()}")
            
            retail_products = []
            for product in products:
                try:
                    retail_product = self._convert_product_to_retail(product)
                    retail_products.append(retail_product)
                except Exception as e:
                    logging.error(f"Error al convertir producto {product.get('id', 'unknown')}: {str(e)}")
                    # Continuamos con el siguiente producto
                    continue
            
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
            # Verificamos parámetros de configuración
            if not self.project_number or not self.location or not self.catalog or not self.serving_config_id:
                logging.error("Faltan parámetros de configuración para Google Retail API")
                logging.error(f"Project: {self.project_number}, Location: {self.location}, Catalog: {self.catalog}, Serving Config: {self.serving_config_id}")
                return []
                
            # Verificamos que el serving_config_id no sea una ruta de archivo
            if self.serving_config_id.endswith('.json') or '/' in self.serving_config_id or '\\' in self.serving_config_id:
                logging.error(f"El valor de serving_config_id parece ser una ruta de archivo: {self.serving_config_id}")
                return []

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
                # Intentar validar la solicitud
                response = self.predict_client.predict(request)
                logging.info(f"Validación exitosa")
                
                # Si la validación es exitosa, hacer la solicitud real
                request.validate_only = False
                response = self.predict_client.predict(request)
                
                # Procesar y devolver resultados
                results = self._process_predictions(response)
                logging.info(f"Se obtuvieron {len(results)} recomendaciones para el usuario {user_id}")
                return results
            except Exception as e:
                logging.error(f"Error en API de Google Retail: {str(e)}")
                if hasattr(e, 'details'):
                    logging.error(f"Detalles del error: {e.details}")
                # Si falla la API de Google, intentar usar recomendaciones basadas en contenido
                return []

        except Exception as e:
            logging.error(f"Error en get_recommendations: {str(e)}")
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