from google.cloud import retail_v2
from google.cloud.retail_v2 import ProductServiceClient, PredictionServiceClient, UserEventServiceClient
from google.cloud.retail_v2.types import Product, PredictRequest, PredictResponse, ImportProductsRequest
from google.cloud.retail_v2.types.import_config import GcsSource, ProductInputConfig, ProductInlineSource, ImportErrorsConfig
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import time
import asyncio
import os
import logging
from google.cloud import storage
import json
import tempfile
import traceback

# Importar el gestor de catálogos (si existe)
try:
    from src.api.core.catalog_manager import CatalogManager
    CATALOG_MANAGER_AVAILABLE = True
except ImportError:
    CATALOG_MANAGER_AVAILABLE = False
    logging.warning("CatalogManager no disponible. Las funciones de gestión de ramas pueden no funcionar correctamente.")

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
        
        # Inicializar los diferentes clientes para Retail API
        self.predict_client = PredictionServiceClient()
        self.product_client = ProductServiceClient()
        self.user_event_client = UserEventServiceClient()
        
        self.placement = (
            f"projects/{project_number}/locations/{location}"
            f"/catalogs/{catalog}/servingConfigs/{serving_config_id}"
        )
        
        # Inicializar gestor de catálogos si está disponible
        self.catalog_manager = None
        if CATALOG_MANAGER_AVAILABLE:
            self.catalog_manager = CatalogManager(
                project_number=project_number,
                location=location,
                catalog=catalog
            )
    
    def _process_predictions(self, response) -> List[Dict]:
        """
        Procesa la respuesta de la API de Google Cloud Retail y extrae las recomendaciones.
        Maneja múltiples formatos de respuesta para diferentes tipos de consultas.
        
        Args:
            response: Respuesta de la API de Google Cloud Retail
            
        Returns:
            List[Dict]: Lista de productos recomendados con toda la información disponible
        """
        recommendations = []
        try:
            # Log detallado de la estructura de respuesta para diagnóstico
            logging.info(f"Tipo de respuesta: {type(response)}")
            logging.debug(f"Estructura completa de respuesta: {response}")
            
            # Función auxiliar para extraer información de producto de diferentes estructuras
            def extract_product_info(item, source_type):
                product_info = {
                    "id": "",
                    "title": "Producto",  # Valor por defecto
                    "description": "",
                    "price": 0.0,
                    "category": "",
                    "score": 0.0,
                    "source": "retail_api"
                }
                
                # Registrar tipo de estructura para diagnóstico
                logging.debug(f"Extrayendo información de producto desde {source_type}: {type(item)}")
                
                # Extraer ID (obligatorio)
                if hasattr(item, 'id'):
                    product_info["id"] = item.id
                elif hasattr(item, 'product') and hasattr(item.product, 'id'):
                    product_info["id"] = item.product.id
                
                # Si no hay ID, no podemos procesar este item
                if not product_info["id"]:
                    logging.warning(f"No se pudo extraer ID de producto desde {source_type}")
                    return None
                    
                # Extraer título
                if hasattr(item, 'title') and item.title:
                    product_info["title"] = item.title
                elif hasattr(item, 'product') and hasattr(item.product, 'title') and item.product.title:
                    product_info["title"] = item.product.title
                elif hasattr(item, 'name') and item.name:
                    name_parts = item.name.split('/')
                    if name_parts:
                        product_info["title"] = name_parts[-1]
                elif hasattr(item, 'product') and hasattr(item.product, 'name') and item.product.name:
                    name_parts = item.product.name.split('/')
                    if name_parts:
                        product_info["title"] = name_parts[-1]
                    
                # Extraer descripción
                if hasattr(item, 'description') and item.description:
                    product_info["description"] = item.description
                elif hasattr(item, 'product') and hasattr(item.product, 'description') and item.product.description:
                    product_info["description"] = item.product.description
                    
                # Extraer precio
                price = 0.0
                if hasattr(item, 'price') and item.price:
                    try:
                        price = float(item.price)
                    except (ValueError, TypeError):
                        pass
                elif hasattr(item, 'product') and hasattr(item.product, 'price_info') and item.product.price_info:
                    try:
                        price = float(item.product.price_info.price)
                    except (ValueError, TypeError):
                        pass
                product_info["price"] = price
                    
                # Extraer categoría
                if hasattr(item, 'category') and item.category:
                    product_info["category"] = item.category
                elif hasattr(item, 'product') and hasattr(item.product, 'categories') and item.product.categories:
                    product_info["category"] = item.product.categories[0] if len(item.product.categories) > 0 else ""
                    
                # Extraer score
                if hasattr(item, 'score') and item.score:
                    product_info["score"] = float(item.score)
                elif hasattr(item, 'metadata') and hasattr(item.metadata, 'get'):
                    product_info["score"] = float(item.metadata.get("predictScore", 0.0))
                    
                # Intentar extraer información adicional si está disponible
                if hasattr(item, 'product'):
                    # Extraer URLs de imágenes si están disponibles
                    if hasattr(item.product, 'images') and item.product.images:
                        image_uris = [img.uri for img in item.product.images if hasattr(img, 'uri')]
                        if image_uris:
                            product_info["images"] = image_uris
                    
                    # Extraer atributos adicionales si están disponibles
                    if hasattr(item.product, 'attributes') and item.product.attributes:
                        attributes = {}
                        for key, value in item.product.attributes.items():
                            if hasattr(value, 'text') and value.text:
                                attributes[key] = value.text[0] if value.text else None
                        if attributes:
                            product_info["attributes"] = attributes
                
                return product_info
                
            # Verificar si tiene el campo 'results'
            if hasattr(response, 'results') and response.results:
                logging.info(f"Procesando respuesta con {len(response.results)} resultados en campo 'results'")
                for result in response.results:
                    product_info = extract_product_info(result, "results")
                    if product_info:
                        recommendations.append(product_info)
                        
            # Verificar estructura alternativa (recomendaciones basadas en usuario)
            elif hasattr(response, 'recommendations'):
                logging.info(f"Procesando respuesta con {len(response.recommendations)} elementos en campo 'recommendations'")
                
                for rec in response.recommendations:
                    product_info = extract_product_info(rec, "recommendations")
                    if product_info:
                        recommendations.append(product_info)
            
            # Verificar estructura con campo 'prediction_results' (nuevo formato posible)
            elif hasattr(response, 'prediction_results'):
                logging.info(f"Procesando respuesta con {len(response.prediction_results)} elementos en campo 'prediction_results'")
                
                for result in response.prediction_results:
                    product_info = extract_product_info(result, "prediction_results")
                    if product_info:
                        recommendations.append(product_info)
                        
            else:
                # Intentar procesar respuesta como diccionario
                if hasattr(response, '__dict__') or isinstance(response, dict):
                    response_dict = response.__dict__ if hasattr(response, '__dict__') else response
                    logging.info(f"Intentando procesar respuesta como diccionario: {list(response_dict.keys())}")
                    
                    # Buscar campos que puedan contener recomendaciones
                    possible_fields = ['results', 'recommendations', 'prediction_results', 'items']
                    for field in possible_fields:
                        if field in response_dict and response_dict[field]:
                            logging.info(f"Encontrado campo '{field}' con {len(response_dict[field])} elementos")
                            for item in response_dict[field]:
                                product_info = extract_product_info(item, field)
                                if product_info:
                                    recommendations.append(product_info)
                            break
                
                if not recommendations:
                    logging.warning("La respuesta no contiene resultados en un formato reconocido")
                    logging.debug(f"Contenido de respuesta: {response}")
                    return []
                        
            # Log de resultados
            logging.info(f"Procesadas {len(recommendations)} recomendaciones")
            return recommendations
        except Exception as e:
            logging.error(f"Error processing predictions: {str(e)}")
            logging.error(f"Traceback: {traceback.format_exc()}")
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
                    # Extraer el precio si está disponible
                    price = 0.0
                    try:
                        price = float(item.get('price', 0.0))
                    except (ValueError, TypeError):
                        # Si no podemos convertir el precio, usar valor por defecto
                        price = 1.0
                        
                    # Multiplicar por la cantidad si está disponible
                    quantity = 1
                    try:
                        quantity = int(item.get('quantity', 1))
                    except (ValueError, TypeError):
                        quantity = 1
                        
                    total_price = price * quantity
                    
                    # Registrar evento de compra
                    # Intentar obtener el código de moneda de la orden si está disponible
                    order_currency = order.get('currency', 'COP')
                    
                    await self.record_user_event(
                        user_id=user_id,
                        event_type='purchase-complete',  # Actualizado al tipo correcto
                        product_id=str(item.get('product_id')),
                        purchase_amount=total_price,
                        currency_code=order_currency  # Pasar el código de moneda de la orden
                    )
                    events_recorded += 1
                    
                    # Registrar evento de vista
                    await self.record_user_event(
                        user_id=user_id,
                        event_type='detail-page-view',  # Actualizado al tipo correcto
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
                
            # Limitar la descripción a 5000 caracteres Unicode (requisito de Google Retail API)
            # Esta parte ahora debería ser manejada por el validador de productos, pero mantenemos
            # este código como respaldo para garantizar el cumplimiento de los requisitos
            if description and len(description) > 5000:
                try:
                    # Intentar usar el método de resumen inteligente
                    from src.api.core.product_validator import ProductValidator
                    validator = ProductValidator()
                    
                    original_length = len(description)
                    description = validator._summarize_description(description)
                    
                    logging.info(f"Descripción del producto {product_id} resumida inteligentemente de {original_length} a {len(description)} caracteres")
                except ImportError:
                    # Si no está disponible el validador, usar el método simple
                    logging.warning(f"Truncando descripción del producto {product_id} de {len(description)} a 5000 caracteres")
                    description = description[:4997] + "..."
                except Exception as e:
                    # En caso de error, usar el método simple
                    logging.error(f"Error al resumir descripción: {str(e)}. Usando truncamiento simple.")
                    description = description[:4997] + "..."
            
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
                            # "availability": str(retail_product.availability),
                            "availability": "IN_STOCK",  # Campo obligatorio
                            # Convertir Repeated a lista estándar para JSON
                            "categories": list(retail_product.categories) if hasattr(retail_product, 'categories') else ["General"],
                        }
                        
                        # Campos opcionales adicionales - convertidos a formatos JSON serializables
                        if hasattr(retail_product, 'description') and retail_product.description:
                            description = retail_product.description
                            # Asegurar nuevamente que la descripción no exceda 5000 caracteres
                            if len(description) > 5000:
                                try:
                                    # Intentar usar el método de resumen inteligente
                                    from src.api.core.product_validator import ProductValidator
                                    validator = ProductValidator()
                                    
                                    original_length = len(description)
                                    description = validator._summarize_description(description)
                                    
                                    logging.info(f"Descripción del producto {retail_product.id} resumida inteligentemente en serialización JSON de {original_length} a {len(description)} caracteres")
                                except ImportError:
                                    # Si no está disponible el validador, usar el método simple
                                    logging.warning(f"Truncando descripción del producto {retail_product.id} en la serialización JSON de {len(description)} a 5000 caracteres")
                                    description = description[:4997] + "..."
                                except Exception as e:
                                    # En caso de error, usar el método simple
                                    logging.error(f"Error al resumir descripción: {str(e)}. Usando truncamiento simple.")
                                    description = description[:4997] + "..."
                            retail_product_dict["description"] = description
                            
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
            
    async def get_user_events(self, user_id: str, limit: int = 50) -> List[Dict]:
        """
        Obtiene los eventos de un usuario específico.
        
        Args:
            user_id: ID del usuario
            limit: Número máximo de eventos a obtener
            
        Returns:
            List[Dict]: Lista de eventos del usuario
        """
        try:
            logging.info(f"Obteniendo eventos para usuario {user_id}")
            
            parent = f"projects/{self.project_number}/locations/{self.location}/catalogs/{self.catalog}"
            
            # CORRECCIÓN: Importación flexible de ListUserEventsRequest
            # Intentar múltiples patrones de importación para mayor compatibilidad
            ListUserEventsRequest = None
            import_successful = False
            
            # Patrón 1: Importación directa desde retail_v2 (más reciente)
            try:
                from google.cloud.retail_v2 import ListUserEventsRequest
                import_successful = True
                logging.debug("Importación exitosa: google.cloud.retail_v2.ListUserEventsRequest")
            except ImportError:
                pass
            
            # Patrón 2: Importación desde types (patrón anterior)
            if not import_successful:
                try:
                    from google.cloud.retail_v2.types import ListUserEventsRequest
                    import_successful = True
                    logging.debug("Importación exitosa: google.cloud.retail_v2.types.ListUserEventsRequest")
                except ImportError:
                    pass
            
            # Patrón 3: Importación desde user_event_service (patrón más antiguo)
            if not import_successful:
                try:
                    from google.cloud.retail_v2.types.user_event_service import ListUserEventsRequest
                    import_successful = True
                    logging.debug("Importación exitosa: google.cloud.retail_v2.types.user_event_service.ListUserEventsRequest")
                except ImportError:
                    pass
            
            # Si ningún patrón de importación funciona, usar implementación alternativa
            if not import_successful or ListUserEventsRequest is None:
                logging.warning("No se pudo importar ListUserEventsRequest. Usando implementación alternativa.")
                logging.info(f"Implementación alternativa: simulando consulta de eventos para usuario {user_id}")
                
                # Implementación alternativa: devolver estructura vacía pero válida
                # En una implementación real, esto podría consultar una base de datos local
                # o usar otro método para obtener eventos de usuario
                return []
            
            # Crear el request para list_user_events
            request = ListUserEventsRequest(
                parent=parent,
                filter=f'visitorId="{user_id}"',
                page_size=limit
            )
            
            # Obtener eventos
            events = []
            try:
                # Intentar obtener los eventos
                response = self.user_event_client.list_user_events(request=request)
                
                # Procesar eventos
                for event in response.user_events:
                    event_dict = {
                        "event_type": event.event_type,
                        "visitor_id": event.visitor_id,
                        "event_time": event.event_time.isoformat() if event.event_time else None,
                    }
                    
                    # Agregar detalles del producto si están disponibles
                    if event.product_details and len(event.product_details) > 0:
                        product_detail = event.product_details[0]
                        event_dict["product_id"] = product_detail.product.id if product_detail.product else None
                        event_dict["quantity"] = product_detail.quantity
                    
                    # Agregar atributos personalizados si están disponibles
                    if event.attributes:
                        for key, value in event.attributes.items():
                            if hasattr(value, 'text') and value.text:
                                event_dict[key] = value.text[0] if value.text else None
                    
                    events.append(event_dict)
                    
                logging.info(f"Se obtuvieron {len(events)} eventos para el usuario {user_id}")
                return events
                
            except Exception as api_error:
                logging.warning(f"Error al obtener eventos desde Google Retail API: {str(api_error)}")
                # Si hay un error específico de la API, devolver lista vacía
                return []
                
        except Exception as e:
            logging.error(f"Error general al obtener eventos de usuario: {str(e)}")
            logging.warning("Usando implementación alternativa para obtener eventos de usuario")
            return []
        
    async def ensure_catalog_branches(self) -> bool:
        """
        Asegura que las ramas del catálogo existen y están correctamente configuradas.
        
        Returns:
            bool: True si las ramas están correctamente configuradas, False en caso contrario
        """
        try:
            # Verificar si el gestor de catálogos está disponible
            if not self.catalog_manager:
                logging.warning("CatalogManager no disponible. No se pueden verificar/crear ramas.")
                return False
                
            # Verificar ramas del catálogo
            branches_ok = await self.catalog_manager.ensure_default_branches()
            return branches_ok
        except Exception as e:
            logging.error(f"Error al asegurar ramas del catálogo: {str(e)}")
            return False
    
    async def import_catalog(self, products: List[Dict]):
        """
        Importa productos al catálogo de Google Retail API
        
        Args:
            products: Lista de productos en formato Shopify
            
        Returns:
            Dict: Resultado de la importación
        """
        try:
            # NUEVO: Asegurar que las ramas del catálogo están correctamente configuradas
            if self.catalog_manager:
                await self.ensure_catalog_branches()
            else:
                logging.warning("CatalogManager no disponible. Continuando sin verificar ramas.")
                
            # NUEVO: Validar productos antes de la importación
            try:
                from src.api.core.product_validator import ProductValidator
                validator = ProductValidator()
                logging.info(f"Validando {len(products)} productos antes de la importación")
                
                validated_products, validation_stats = validator.validate_products(products)
                validation_report = validator.get_validation_report()
                
                logging.info(f"Validación completada: {validation_stats['valid_products']} válidos, "
                           f"{validation_stats['modified_products']} modificados, "
                           f"{validation_stats['invalid_products']} inválidos")
                
                if validation_stats['modified_products'] > 0:
                    logging.warning(f"Se han modificado {validation_stats['modified_products']} productos. "
                                f"Ver detalles en: {validator.modified_products_log}")
                
                # Usar productos validados para la importación
                products = validated_products
                
            except ImportError:
                logging.warning("ProductValidator no disponible. Continuando sin validación de productos.")
            except Exception as validation_error:
                logging.error(f"Error durante la validación de productos: {str(validation_error)}")
                logging.warning("Continuando con productos sin validar")
                
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
        """
        Obtiene recomendaciones personalizadas de Google Cloud Retail API.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional, para recomendaciones basadas en producto)
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        try:
            # Verificar parámetros de configuración
            if not self.project_number or not self.location or not self.catalog or not self.serving_config_id:
                logging.error("Faltan parámetros de configuración para Google Retail API")
                logging.error(f"Project: {self.project_number}, Location: {self.location}, Catalog: {self.catalog}, Serving Config: {self.serving_config_id}")
                return []
                
            # Verificar que el serving_config_id no sea una ruta de archivo
            if self.serving_config_id.endswith('.json') or '/' in self.serving_config_id or '\\' in self.serving_config_id:
                logging.error(f"El valor de serving_config_id parece ser una ruta de archivo: {self.serving_config_id}")
                return []

            # CORREGIDO: Crear evento de usuario contextual basado en parámetros
            if product_id:
                # Si hay product_id, usar evento de vista de producto
                event_type = "detail-page-view"
                logging.info(f"[DEBUG] 👁️ Creando evento de vista de producto para product_id={product_id}")
                
                user_event = retail_v2.UserEvent(
                    event_type=event_type,
                    visitor_id=str(user_id),
                    event_time=datetime.utcnow()
                )
                
                # Añadir detalles del producto
                product_detail = retail_v2.ProductDetail()
                product_detail.product.id = product_id
                product_detail.quantity = 1
                user_event.product_details = [product_detail]
                
                logging.info(f"[DEBUG] 📦 Añadido product_detail para {product_id}")
                
            else:
                # Sin product_id, usar evento genérico pero personalizado para el usuario
                event_type = "home-page-view"
                logging.info(f"[DEBUG] 🏠 Creando evento de página de inicio para user_id={user_id}")
                
                user_event = retail_v2.UserEvent(
                    event_type=event_type,
                    visitor_id=str(user_id),
                    event_time=datetime.utcnow()
                )

            logging.info(f"[DEBUG] 📨 User event creado: tipo={event_type}, visitor_id={user_id}")
            logging.info(f"[DEBUG] 🎯 Placement: {self.placement}")

            # CORREGIDO: Crear request sin validación previa que puede fallar
            request = retail_v2.PredictRequest(
                placement=self.placement,
                user_event=user_event,
                page_size=n_recommendations,
                validate_only=False  # CAMBIADO: No validar, ejecutar directamente
            )

            logging.info(f"[DEBUG] 📤 Request creado - page_size: {n_recommendations}")

            try:
                # CORREGIDO: Ejecutar la solicitud directamente
                logging.info(f"[DEBUG] 🚀 Enviando petición a Google Cloud Retail API...")
                response = self.predict_client.predict(request)
                
                logging.info(f"[DEBUG] ✅ Respuesta recibida de Google Cloud Retail API")
                logging.info(f"[DEBUG] 📊 Tipo de respuesta: {type(response)}")
                
                # Procesar y devolver resultados
                results = self._process_predictions(response)
                
                if results:
                    logging.info(f"[DEBUG] 🎉 ÉXITO: {len(results)} recomendaciones procesadas para user_id={user_id}, product_id={product_id}")
                    
                    # Log de las primeras recomendaciones para diagnóstico
                    for i, rec in enumerate(results[:3]):
                        logging.info(f"[DEBUG] Retail API Rec {i+1}: ID={rec.get('id')}, Título={rec.get('title', '')[:30]}..., Score={rec.get('score', 0)}")
                else:
                    logging.warning(f"[DEBUG] ⚠️ Google Retail API devolvió respuesta vacía para user_id={user_id}, product_id={product_id}")
                
                return results
                
            except Exception as api_error:
                logging.error(f"[DEBUG] ❌ ERROR en API de Google Retail: {str(api_error)}")
                logging.error(f"[DEBUG] Tipo de error: {type(api_error).__name__}")
                
                if hasattr(api_error, 'details'):
                    logging.error(f"[DEBUG] Detalles del error: {api_error.details}")
                    
                # Verificar si es un error de configuración
                error_msg = str(api_error).lower()
                if 'permission' in error_msg or 'auth' in error_msg:
                    logging.error(f"[DEBUG] 🔒 ERROR DE AUTENTICACIÓN: Verificar credenciales de Google Cloud")
                elif 'not found' in error_msg or '404' in error_msg:
                    logging.error(f"[DEBUG] 📍 ERROR DE CONFIGURACIÓN: Verificar project_number, location, catalog, serving_config")
                elif 'quota' in error_msg or 'limit' in error_msg:
                    logging.error(f"[DEBUG] 🚧 ERROR DE QUOTA: Verificar límites de la API de Google Cloud")
                    
                return []

        except Exception as e:
            logging.error(f"[DEBUG] 💥 ERROR GENERAL en get_recommendations: {str(e)}")
            logging.error(f"[DEBUG] Traceback: {traceback.format_exc()}")
            return []
            
    async def record_user_event(
        self,
        user_id: str,
        event_type: str,
        product_id: Optional[str] = None,
        recommendation_id: Optional[str] = None,
        purchase_amount: Optional[float] = None,
        currency_code: Optional[str] = None
    ):
        try:
            # Validar el tipo de evento
            valid_event_types = [
                "add-to-cart", 
                "category-page-view", 
                "detail-page-view", 
                "home-page-view", 
                "purchase-complete",
                "search"
            ]
            
            # Convertir tipos alternativos a los aceptados por la API
            event_type_map = {
                "view": "detail-page-view",
                "detail-page": "detail-page-view",
                "add": "add-to-cart",
                "cart": "add-to-cart",
                "buy": "purchase-complete",
                "purchase": "purchase-complete",
                "checkout": "purchase-complete",
                "home": "home-page-view",
                "category": "category-page-view",
                "promo": "category-page-view"
            }
            
            # Mapear el tipo de evento si es necesario
            if event_type in event_type_map:
                actual_event_type = event_type_map[event_type]
                logging.info(f"Tipo de evento '{event_type}' mapeado a '{actual_event_type}'")
                event_type = actual_event_type
            
            # Verificar tipo de evento
            if event_type not in valid_event_types:
                logging.warning(f"Tipo de evento '{event_type}' no reconocido. Cambiando a 'detail-page-view'")
                event_type = "detail-page-view"
            
            # Construir el objeto UserEvent correctamente
            parent = f"projects/{self.project_number}/locations/{self.location}/catalogs/{self.catalog}"
            
            # Crear el objeto UserEvent
            user_event = retail_v2.UserEvent(
                event_type=event_type,
                visitor_id=user_id,
                event_time=datetime.utcnow()
            )
            
            # Agregar detalles del producto si está disponible
            if product_id:
                product_detail = retail_v2.ProductDetail()
                product_detail.product.id = product_id
                product_detail.quantity = 1
                user_event.product_details = [product_detail]
                
                # Si el evento viene de una recomendación, agregar atributos personalizados
                if recommendation_id:
                    # Agregar atributos para tracking de recomendaciones
                    user_event.attributes = {
                        "recommendation_id": retail_v2.CustomAttribute(
                            text=[recommendation_id]
                        ),
                        "recommendation_source": retail_v2.CustomAttribute(
                            text=["api"]
                        )
                    }
                    logging.info(f"Evento asociado a recomendación: {recommendation_id}")
            
            # CORRECCIÓN: Agregar campo obligatorio purchaseTransaction para eventos de compra
            # Este es el cambio clave que corrige el error
            if event_type == "purchase-complete":
                transaction_id = f"transaction_{int(time.time())}_{user_id[-5:] if len(user_id) >= 5 else user_id}"
                
                # Utilizar el valor proporcionado o un valor predeterminado
                revenue = purchase_amount if purchase_amount is not None else 1.0
                
                # Obtener el código de moneda de parámetros, configuración o valor por defecto
                # 1. Usar el valor proporcionado en el parámetro
                # 2. Intentar obtener de variables de entorno
                # 3. Usar "COP" como valor predeterminado
                used_currency_code = currency_code or os.getenv("DEFAULT_CURRENCY", "COP")
                
                # Validar que el código de moneda sea válido (ISO 4217)
                valid_currency_codes = [
                    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
                    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
                    "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHF", "CLP", "CNY",
                    "COP", "CRC", "CUC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD",
                    "EGP", "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP",
                    "GMD", "GNF", "GTQ", "GYD", "HKD", "HNL", "HRK", "HTG", "HUF", "IDR",
                    "ILS", "INR", "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS",
                    "KHR", "KMF", "KPW", "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR",
                    "LRD", "LSL", "LYD", "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP",
                    "MRU", "MUR", "MVR", "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO",
                    "NOK", "NPR", "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN",
                    "PYG", "QAR", "RON", "RSD", "RUB", "RWF", "SAR", "SBD", "SCR", "SDG",
                    "SEK", "SGD", "SHP", "SLL", "SOS", "SRD", "SSP", "STN", "SVC", "SYP",
                    "SZL", "THB", "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS",
                    "UAH", "UGX", "USD", "UYU", "UZS", "VES", "VND", "VUV", "WST", "XAF",
                    "XCD", "XDR", "XOF", "XPF", "YER", "ZAR", "ZMW", "ZWL"
                ]
                
                if used_currency_code not in valid_currency_codes:
                    logging.warning(f"Código de moneda proporcionado '{used_currency_code}' no es válido. Usando 'COP' por defecto.")
                    used_currency_code = "COP"
                
                # Crear el objeto PurchaseTransaction requerido
                user_event.purchase_transaction = retail_v2.PurchaseTransaction(
                    id=transaction_id,
                    revenue=revenue,
                    currency_code=used_currency_code  # Usar el código de moneda validado
                )
                
                logging.info(f"Evento de compra con transaction_id={transaction_id}, revenue={revenue}, currency_code={used_currency_code}")
            
            # Registrar el evento
            logging.info(f"Registrando evento: usuario={user_id}, tipo={event_type}, producto={product_id or 'N/A'}")
            
            # Crear el request para write_user_event
            request = retail_v2.WriteUserEventRequest(
                parent=parent,
                user_event=user_event
            )
            
            # Usar el cliente correcto (UserEventServiceClient) para registrar eventos
            response = self.user_event_client.write_user_event(request=request)
            
            response = {
                "status": "success", 
                "message": "Event recorded", 
                "event_type": event_type,
                "recommendation_tracked": recommendation_id is not None
            }
            
            # Añadir información de moneda si es un evento de compra
            if event_type == "purchase-complete":
                response["currency_used"] = used_currency_code
                response["transaction_id"] = transaction_id
                response["revenue"] = revenue
                
            return response
            
        except Exception as e:
            logging.error(f"Error recording user event: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }