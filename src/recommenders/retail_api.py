from google.cloud import retail_v2
from google.cloud.retail_v2 import ProductServiceClient
from google.cloud.retail_v2.types import Product, PredictRequest, PredictResponse
from google.cloud.retail_v2.types.import_config import ProductInputConfig, ProductInlineSource
from google.cloud.retail_v2.types import ImportProductsRequest
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
        """
        Convierte un producto de Shopify al formato de Google Retail API.
        
        Args:
            product: Diccionario con datos del producto de Shopify
            
        Returns:
            Product: Objeto Product de Google Retail API
        """
        try:
            # Extracción segura de datos con valores predeterminados
            product_id = str(product.get("id", ""))
            title = product.get("title", "")
            
            # Limpiar HTML de la descripción
            description = product.get("body_html", "")
            if description:
                # Eliminar etiquetas HTML comunes
                for tag in ["<p>", "</p>", "<br>", "<ul>", "</ul>", "<li>", "</li>", "<span>", "</span>", "<strong>", "</strong>"]:
                    description = description.replace(tag, " ")
                # Eliminar atributos HTML
                import re
                description = re.sub(r'\s+', ' ', description).strip()
            
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
            
            # Asegurar que el ID sea válido
            if not product_id:
                logging.warning(f"Producto sin ID válido: {title}")
                return None
            
            # Construcción del objeto Product con valores mínimos requeridos
            retail_product = Product(
                id=product_id,
                title=title,
                availability="IN_STOCK"
            )
            
            # Agregar campos opcionales solo si tienen valores
            if description:
                retail_product.description = description
                
            if price > 0:
                retail_product.price_info = retail_v2.PriceInfo(
                    price=price,
                    original_price=price,
                    currency_code="COP"
                )
                
            if category:
                retail_product.categories = [category]
                
            # Agregar imágenes si están disponibles
            if product.get("images") and len(product["images"]) > 0:
                retail_product.images = [
                    retail_v2.Image(uri=img.get("src"))
                    for img in product["images"]
                    if img.get("src")
                ][:10]  # Limitar a 10 imágenes
                
            # Agregar etiquetas como atributos
            if product.get("tags"):
                tags = product["tags"]
                if isinstance(tags, str):
                    tags = [tag.strip() for tag in tags.split(",")]
                
                if tags:
                    retail_product.attributes = {
                        "tags": retail_v2.CustomAttribute(text=tags)
                    }
                    
            # Agregar información de variantes si está disponible
            if product.get("variants") and len(product["variants"]) > 0:
                variant = product["variants"][0]
                if variant.get("sku"):
                    retail_product.attributes = retail_product.attributes or {}
                    retail_product.attributes["sku"] = retail_v2.CustomAttribute(
                        text=[variant.get("sku")]
                    )
                    
            return retail_product
            
        except Exception as e:
            logging.error(f"Error al convertir producto {product.get('id', 'unknown')}: {str(e)}")
            return None
        
    async def import_catalog(self, products: List[Dict]):
        """
        Importa productos al catálogo de Google Retail API
        
        Args:
            products: Lista de productos en formato Shopify
            
        Returns:
            Dict: Resultado de la importación
        """
        try:
            # Agregamos log para depuración
            logging.info(f"Importando {len(products)} productos al catálogo de Google Retail API")
            if products and len(products) > 0:
                logging.debug(f"Estructura del primer producto: {list(products[0].keys())}")
            else:
                logging.error("No hay productos para importar")
                return {"status": "error", "error": "No hay productos para importar"}
            
            # Convertir productos al formato de Google Retail API
            retail_products = []
            skipped_products = 0
            
            for product in products:
                try:
                    retail_product = self._convert_product_to_retail(product)
                    if retail_product:
                        retail_products.append(retail_product)
                    else:
                        skipped_products += 1
                except Exception as e:
                    logging.error(f"Error al convertir producto {product.get('id', 'unknown')}: {str(e)}")
                    skipped_products += 1
                    continue
            
            if not retail_products:
                logging.error("No se pudo convertir ningún producto al formato de Google Retail API")
                return {
                    "status": "error", 
                    "error": "No se pudo convertir ningún producto",
                    "total_products": len(products),
                    "skipped_products": skipped_products
                }
            
            logging.info(f"Se convirtieron {len(retail_products)} productos correctamente (ignorados: {skipped_products})")
            
            # Construir la ruta del catálogo
            parent = (
                f"projects/{self.project_number}/locations/{self.location}"
                f"/catalogs/{self.catalog}/branches/default_branch"
            )
            
            logging.info(f"Importando productos a: {parent}")
            
            # Importar en lotes si hay muchos productos
            batch_size = 100  # Google recomienda no más de 100 productos por lote
            success_count = 0
            batches = [retail_products[i:i+batch_size] for i in range(0, len(retail_products), batch_size)]
            
            for i, batch in enumerate(batches):
                try:
                    logging.info(f"Importando lote {i+1}/{len(batches)} ({len(batch)} productos)...")
                    
                    # Crear objeto ProductInlineSource
                    product_inline_source = ProductInlineSource(products=batch)
                    
                    # Crear InputConfig usando la estructura anidada correcta
                    input_config = ProductInputConfig(
                        product_inline_source=product_inline_source
                    )
                    
                    # Crear solicitud con el modo de reconciliación correcto
                    import_request = ImportProductsRequest(
                        parent=parent,
                        input_config=input_config,
                        reconciliation_mode=retail_v2.types.ImportProductsRequest.ReconciliationMode.INCREMENTAL
                    )
                    
                    operation = self.product_client.import_products(request=import_request)
                    result = operation.result()
                    
                    success_count += len(batch)
                    logging.info(f"Lote {i+1} importado correctamente")
                    
                except Exception as e:
                    logging.error(f"Error al importar lote {i+1}: {str(e)}")
            
            return {
                "status": "success" if success_count > 0 else "partial_error",
                "products_imported": success_count,
                "products_converted": len(retail_products),
                "total_products": len(products),
                "skipped_products": skipped_products,
                "error_batches": len(batches) - (success_count // batch_size) - (1 if success_count % batch_size > 0 else 0)
            }
            
        except Exception as e:
            logging.error(f"Error general en import_catalog: {str(e)}")
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