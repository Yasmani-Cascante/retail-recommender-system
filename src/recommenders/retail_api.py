from google.cloud import retail_v2
from google.cloud.retail_v2 import ProductServiceClient
from google.cloud.retail_v2.types import Product, PredictRequest, PredictResponse, ImportProductsRequest
from google.cloud.retail_v2.types.import_config import GcsSource, ProductInputConfig, ProductInlineSource, ImportErrorsConfig
from typing import List, Dict, Optional
from datetime import datetime
import asyncio
import os
import logging
from google.cloud import storage
import json
import tempfile
import traceback

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
            
            # Intentar obtener el título de diferentes campos posibles
            title = product.get("title", "")
            if not title:
                title = product.get("name", "")
            
            # Intentar obtener la descripción de diferentes campos posibles
            description = product.get("body_html", "")
            if not description:
                description = product.get("description", "")
            
            # Validar campos obligatorios
            if not product_id:
                logging.warning(f"Producto sin ID válido: {title}")
                return None
                
            if not title:
                logging.warning(f"Producto sin título válido (ID: {product_id})")
                title = f"Producto {product_id}"  # Título predeterminado
            
            # Extracción de precio - intentar diferentes campos
            price = 0.0
            if product.get("variants") and len(product["variants"]) > 0:
                price_str = product["variants"][0].get("price", "0")
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    price = 0.0
            # Si no hay variantes, buscar precio directo
            if price == 0.0 and product.get("price"):
                try:
                    price = float(product.get("price", 0.0))
                except (ValueError, TypeError):
                    price = 0.0
                    
            # Categoría del producto - intentar diferentes campos
            category = product.get("product_type", "")
            if not category:
                category = product.get("category", "General")
            
            # La categoría es muy importante para la API, forzar un valor por defecto
            if not category:
                category = "General"
                
            # Asegurar que siempre haya categoría
            if not category:
                category = "General"
            
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
                
            # Siempre añadir la categoría al producto
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

    async def import_catalog_via_gcs(self, products: List[Dict]):
        """
        Importa productos al catálogo de Google Retail API usando GCS como intermediario
        para manejar catálogos de gran tamaño de manera eficiente.
        
        Args:
            products: Lista de productos en formato Shopify
            
        Returns:
            Dict: Resultado de la importación
        """
        try:
            # Verificamos que existan productos
            if not products:
                logging.error("No hay productos para importar")
                return {"status": "error", "error": "No hay productos para importar"}
            
            logging.info(f"Iniciando importación vía GCS de {len(products)} productos")
            
            # Convertir productos al formato de Google Retail API
            retail_products = []
            skipped_products = 0
            
            for product in products:
                try:
                    retail_product = self._convert_product_to_retail(product)
                    if retail_product:
                        # Convertir el objeto Product a diccionario para JSON
                        # Asegurarnos de incluir TODOS los campos requeridos y que sean serializables
                        retail_product_dict = {
                            "id": retail_product.id,
                            "title": retail_product.title,  # Campo obligatorio
                            "availability": str(retail_product.availability),
                            # Convertir Repeated a lista estándar para JSON
                            "categories": list(retail_product.categories) if hasattr(retail_product, 'categories') else ["General"],
                        }
                        
                        # Campos opcionales adicionales - convertidos a formatos JSON serializables
                        if hasattr(retail_product, 'description') and retail_product.description:
                            retail_product_dict["description"] = retail_product.description
                            
                        # Las categorías ya se han añadido arriba
                            
                        if hasattr(retail_product, 'price_info') and retail_product.price_info:
                            retail_product_dict["price_info"] = {
                                "price": retail_product.price_info.price,
                                "original_price": retail_product.price_info.original_price,
                                "currency_code": retail_product.price_info.currency_code
                            }
                            
                        if hasattr(retail_product, 'images') and retail_product.images:
                            # Convertir objetos Image a diccionarios serializables
                            retail_product_dict["images"] = [
                                {"uri": img.uri} for img in retail_product.images
                            ]
                        
                        retail_products.append(retail_product_dict)
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
            
            # Determinar el directorio temporal apropiado (que funcione en todos los entornos)
            temp_dir = tempfile.gettempdir()
            import_filename = f"retail_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            local_path = os.path.join(temp_dir, import_filename)
            
            logging.info(f"Creando archivo JSONL en: {local_path}")
            
            # Verificar que el directorio existe y tiene permisos
            try:
                os.makedirs(temp_dir, exist_ok=True)
                
                # Función para manejar objetos que no son serializables directamente
                def json_serializer(obj):
                    # Intentar convertir a un tipo serializable
                    if hasattr(obj, "to_json"):
                        return obj.to_json()
                    elif hasattr(obj, "__dict__"):
                        return obj.__dict__
                    else:
                        return str(obj)  # Última opción: convertir a string
                
                with open(local_path, 'w') as f:
                    for product in retail_products:
                        # Los productos ya deberían ser diccionarios serializables ahora
                        f.write(json.dumps(product) + '\n')
                logging.info(f"Archivo JSONL creado correctamente: {local_path}")
            except (IOError, PermissionError) as e:
                logging.error(f"Error al crear archivo temporal: {str(e)}")
                # Intento alternativo en directorio actual
                local_path = import_filename
                logging.info(f"Intentando crear archivo en directorio actual: {local_path}")
                with open(local_path, 'w') as f:
                    for product in retail_products:
                        f.write(json.dumps(product) + '\n')
            
            # Verificar que el archivo existe
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"No se pudo crear el archivo temporal: {local_path}")
                
            # Subir archivo a GCS
            bucket_name = os.getenv("GCS_BUCKET_NAME")
            if not bucket_name:
                raise ValueError("GCS_BUCKET_NAME no está configurado en las variables de entorno")
                
            blob_name = f"imports/{import_filename}"
            
            logging.info(f"Iniciando conexión con Google Cloud Storage...")
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            logging.info(f"Subiendo archivo {local_path} a GCS: gs://{bucket_name}/{blob_name}")
            blob.upload_from_filename(local_path)
            gcs_uri = f"gs://{bucket_name}/{blob_name}"
            logging.info(f"Archivo subido a GCS: {gcs_uri}")
            
            # Iniciar importación desde GCS usando Google Retail API
            gcs_source = GcsSource(input_uris=[gcs_uri])
            
            # Crear InputConfig para GCS
            input_config = ProductInputConfig(gcs_source=gcs_source)
            
            # Ruta del catálogo correcta (branch 0)
            parent = f"projects/{self.project_number}/locations/{self.location}/catalogs/{self.catalog}/branches/0"
            
            logging.info(f"Usando ruta del catálogo: {parent}")
            
            # Crear la configuración de errores
            bucket_name = os.getenv("GCS_BUCKET_NAME")
            errors_config = ImportErrorsConfig(
                gcs_prefix=f"gs://{bucket_name}/errors/"
            )
            
            # Crear la solicitud de importación
            import_request = ImportProductsRequest(
                parent=parent,
                input_config=input_config,
                errors_config=errors_config,
                # El modo de reconciliación es un enum del mensaje ImportProductsRequest
                reconciliation_mode=ImportProductsRequest.ReconciliationMode.INCREMENTAL
            )
            
            logging.info(f"Iniciando importación desde GCS: {gcs_uri}")
            
            # Ejecutar la operación
            operation = self.product_client.import_products(request=import_request)
            
            # Crear un ID para la operación para poder consultarla después si es necesario
            operation_id = operation.operation.name
            logging.info(f"Operación de importación iniciada: {operation_id}")
            
            # Esperar a que termine la operación
            try:
                logging.info("Esperando a que la operación de importación finalice...")
                result = operation.result(timeout=300)  # Timeout de 5 minutos
                logging.info(f"Importación completada: {result}")
            except Exception as e:
                logging.warning(f"La operación de importación sigue en progreso, pero no esperaremos: {str(e)}")
                logging.info(f"Puedes verificar el estado más tarde con el ID: {operation_id}")
                
            # Eliminar archivo temporal
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
                    logging.info(f"Archivo temporal eliminado: {local_path}")
            except Exception as e:
                logging.warning(f"No se pudo eliminar el archivo temporal {local_path}: {str(e)}")
                
            return {
                "status": "success",
                "products_imported": len(retail_products),
                "total_products": len(products),
                "skipped_products": skipped_products,
                "gcs_uri": gcs_uri,
                "operation_id": operation_id
            }
            
        except Exception as e:
            logging.error(f"Error general en import_catalog_via_gcs: {str(e)}")
            logging.error(f"Traceback: {traceback.format_exc()}")
            return {
                "status": "error",
                "error": str(e)
            }
        
    async def import_catalog(self, products: List[Dict]):
        """
        Importa productos al catálogo de Google Retail API
        
        Args:
            products: Lista de productos en formato Shopify
            
        Returns:
            Dict: Resultado de la importación
        """
        try:
            # Verificar si debemos usar el método de importación vía GCS
            # basado en el tamaño del catálogo o configuración
            use_gcs = os.getenv("USE_GCS_IMPORT", "False").lower() == "true"
            products_count = len(products) if products else 0
            
            # Si hay muchos productos o se configura explícitamente, usar GCS
            # Reducimos el umbral a 50 productos para probar más fácilmente
            if products_count >= 50 or use_gcs:
                logging.info(f"Utilizando importación vía GCS para {products_count} productos")
                return await self.import_catalog_via_gcs(products)
                
            # Para catálogos pequeños, usar el método directo original
            logging.info(f"Utilizando importación directa para {products_count} productos")
            
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
            
            # Construir la ruta del catálogo (branch 0)
            parent = f"projects/{self.project_number}/locations/{self.location}/catalogs/{self.catalog}/branches/0"
            
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
                        reconciliation_mode=ImportProductsRequest.ReconciliationMode.INCREMENTAL
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