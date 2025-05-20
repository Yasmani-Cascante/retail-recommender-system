# src/api/core/product_gateway.py

import logging
import aiohttp
import asyncio
from typing import Dict, Optional, Any, List
import os
import json

logger = logging.getLogger(__name__)

class ProductGateway:
    """
    Gateway para obtener información de productos desde fuentes externas.
    
    Este servicio proporciona una capa unificada para consultar productos
    desde diferentes fuentes cuando no están disponibles localmente.
    """
    
    def __init__(self, max_concurrent_requests: int = 10):
        """
        Inicializa el gateway.
        
        Args:
            max_concurrent_requests: Número máximo de peticiones concurrentes
        """
        self.session = None
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.stats = {
            "retail_api_calls": 0,
            "external_api_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0
        }
        
    async def initialize(self):
        """Inicializa recursos como sesiones HTTP."""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        
    async def shutdown(self):
        """Libera recursos."""
        if self.session is not None:
            await self.session.close()
            self.session = None
    
    async def get_product_from_retail_api(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un producto directamente de Google Cloud Retail API.
        
        Args:
            product_id: ID del producto
            
        Returns:
            Dict con información del producto o None si no se encuentra
        """
        try:
            async with self.semaphore:
                # Asegurar que la sesión está inicializada
                await self.initialize()
                
                self.stats["retail_api_calls"] += 1
                
                # Construir URL para la API de Retail
                project_number = os.getenv("GOOGLE_PROJECT_NUMBER")
                location = os.getenv("GOOGLE_LOCATION", "global")
                catalog = os.getenv("GOOGLE_CATALOG", "default_catalog")
                
                # Endpoint para obtener un producto específico
                url = f"https://retail.googleapis.com/v2/projects/{project_number}/locations/{location}/catalogs/{catalog}/branches/0/products/{product_id}"
                
                # Obtener token de autenticación (usando la biblioteca de Google)
                # Este paso depende de cómo se esté autenticando en Google Cloud
                # Por ejemplo, usando google-auth o service account
                import google.auth
                import google.auth.transport.requests
                
                credentials, _ = google.auth.default()
                auth_req = google.auth.transport.requests.Request()
                credentials.refresh(auth_req)
                
                headers = {
                    "Authorization": f"Bearer {credentials.token}",
                    "Content-Type": "application/json"
                }
                
                async with self.session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.stats["successful_calls"] += 1
                        
                        # Convertir formato Google Retail API al formato del catálogo local
                        return self._convert_retail_api_format(data)
                    else:
                        logger.warning(f"No se pudo obtener producto {product_id} de Retail API: {response.status}")
                        self.stats["failed_calls"] += 1
                        
                        # Si el error es 404, el producto no existe
                        if response.status == 404:
                            return None
                            
                        # Para otros errores, intentar extraer mensaje
                        try:
                            error_data = await response.json()
                            logger.error(f"Error de Retail API: {error_data}")
                        except:
                            pass
                        
                        return None
        except Exception as e:
            logger.error(f"Error obteniendo producto {product_id} de Retail API: {str(e)}")
            self.stats["failed_calls"] += 1
            return None
    
    async def get_product_from_external_api(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un producto desde un API externo.
        
        Esto es configurable según las fuentes de datos externas disponibles.
        
        Args:
            product_id: ID del producto
            
        Returns:
            Dict con información del producto o None si no se encuentra
        """
        # Verificar si hay un API externo configurado
        external_api_url = os.getenv("EXTERNAL_PRODUCT_API_URL")
        if not external_api_url:
            return None
            
        try:
            async with self.semaphore:
                # Asegurar que la sesión está inicializada
                await self.initialize()
                
                self.stats["external_api_calls"] += 1
                
                # URL para obtener producto
                url = f"{external_api_url}/products/{product_id}"
                
                # Headers de autenticación si son necesarios
                headers = {}
                api_key = os.getenv("EXTERNAL_API_KEY")
                if api_key:
                    headers["X-API-Key"] = api_key
                
                async with self.session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.stats["successful_calls"] += 1
                        return data
                    else:
                        logger.warning(f"No se pudo obtener producto {product_id} del API externo: {response.status}")
                        self.stats["failed_calls"] += 1
                        return None
        except Exception as e:
            logger.error(f"Error obteniendo producto {product_id} del API externo: {str(e)}")
            self.stats["failed_calls"] += 1
            return None
    
    def _convert_retail_api_format(self, retail_product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convierte el formato de Google Retail API al formato del catálogo local.
        
        Args:
            retail_product: Producto en formato Google Retail API
            
        Returns:
            Producto en formato del catálogo local
        """
        try:
            # Extraer ID
            product_id = retail_product.get("id", "")
            if "name" in retail_product and not product_id:
                # Extraer ID desde name (formato: projects/1/locations/global/.../products/123)
                parts = retail_product["name"].split("/")
                if len(parts) > 0:
                    product_id = parts[-1]
            
            # Construir producto en formato del catálogo local
            converted = {
                "id": product_id,
                "title": retail_product.get("title", "Producto sin título"),
                "body_html": retail_product.get("description", ""),
                "product_type": retail_product.get("categories", [""])[0] if retail_product.get("categories") else "",
                "variants": []
            }
            
            # Extraer precio
            if "priceInfo" in retail_product:
                price = retail_product["priceInfo"].get("price", 0)
                original_price = retail_product["priceInfo"].get("originalPrice", price)
                
                # Crear variante con precio
                converted["variants"].append({
                    "price": str(price),
                    "original_price": str(original_price)
                })
            
            # Extraer imágenes
            if "images" in retail_product and retail_product["images"]:
                converted["images"] = []
                for img in retail_product["images"]:
                    converted["images"].append({
                        "src": img.get("uri", "")
                    })
            
            return converted
        except Exception as e:
            logger.error(f"Error convirtiendo formato de Retail API: {str(e)}")
            # Devolver producto mínimo
            return {
                "id": retail_product.get("id", "unknown"),
                "title": retail_product.get("title", "Producto desconocido"),
                "body_html": "",
                "product_type": "",
                "variants": [{"price": "0"}]
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del gateway.
        
        Returns:
            Dict con estadísticas
        """
        return self.stats