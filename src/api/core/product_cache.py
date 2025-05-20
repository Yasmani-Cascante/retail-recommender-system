"""
Sistema de caché híbrido para productos con Redis y fallback a otras fuentes.

Proporciona acceso a información de productos desde múltiples fuentes:
- Redis (primario para rendimiento)
- Catálogo local (fallback)
- Shopify (fallback secundario)
- Gateway de productos externos (fallback terciario)
"""

import logging
import time
import json
import asyncio
from typing import Dict, List, Optional, Any, Set
import traceback
import os

logger = logging.getLogger(__name__)

class ProductCache:
    """
    Sistema de caché híbrido para productos con Redis y fallback a otras fuentes.
    """
    
    def __init__(
        self, 
        redis_client, 
        local_catalog=None, 
        shopify_client=None, 
        product_gateway=None,
        ttl_seconds=3600,
        prefix="product:"
    ):
        """
        Inicializa el sistema de caché de productos.
        
        Args:
            redis_client: Cliente Redis inicializado
            local_catalog: Catálogo local (TFIDFRecommender)
            shopify_client: Cliente de Shopify para fallback
            product_gateway: Gateway para productos externos (opcional)
            ttl_seconds: Tiempo de vida en caché (segundos)
            prefix: Prefijo para claves en Redis
        """
        self.redis = redis_client
        self.local_catalog = local_catalog
        self.shopify_client = shopify_client
        self.product_gateway = product_gateway
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        
        self.stats = {
            "redis_hits": 0,
            "redis_misses": 0,
            "local_catalog_hits": 0,
            "shopify_hits": 0,
            "gateway_hits": 0,  # Nueva estadística para gateway
            "total_failures": 0,
            "total_requests": 0
        }
        
        # Iniciar background task para health check periódico (opcional)
        self.health_task = None
        logger.info(f"Sistema de caché de productos inicializado. TTL: {ttl_seconds}s, Prefix: {prefix}")
        
    async def start_background_tasks(self):
        """Inicia tareas en segundo plano."""
        self.health_task = asyncio.create_task(self._periodic_health_check())
        logger.info("Tareas en segundo plano del sistema de caché iniciadas")
        
    async def _periodic_health_check(self, interval=300):
        """
        Realiza health checks periódicos.
        
        Args:
            interval: Intervalo entre checks en segundos
        """
        logger.info(f"Iniciando health checks periódicos cada {interval} segundos")
        while True:
            try:
                # Verificar conexión a Redis
                if self.redis:
                    health_info = await self.redis.health_check()
                    redis_status = "conectado" if health_info.get("connected", False) else "desconectado"
                    logger.info(f"Redis health check: {redis_status}")
                    
                # Registrar estadísticas de caché
                hit_ratio = self._calculate_hit_ratio()
                logger.info(f"Cache stats: {self.stats}, hit ratio: {hit_ratio:.2f}")
                
            except Exception as e:
                logger.error(f"Error en health check de caché: {str(e)}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                
            # Esperar intervalo
            await asyncio.sleep(interval)
        
    def _calculate_hit_ratio(self):
        """
        Calcula ratio de éxito de caché.
        
        Returns:
            float: Ratio de éxito (0-1)
        """
        if self.stats["total_requests"] == 0:
            return 0
            
        hits = (
            self.stats["redis_hits"] + 
            self.stats["local_catalog_hits"] + 
            self.stats["shopify_hits"] + 
            self.stats["gateway_hits"]  # Incluir hits del gateway
        )
        return hits / self.stats["total_requests"]
    
    async def get_product(self, product_id: str) -> Optional[Dict]:
        """
        Obtiene un producto de la caché o fuentes alternativas.
        
        Args:
            product_id: ID del producto
            
        Returns:
            Dict con datos del producto o None si no se encuentra
        """
        if not product_id:
            logger.warning("Se intentó obtener un producto con ID vacío")
            return None
            
        self.stats["total_requests"] += 1
        
        # 1. Intentar obtener de Redis
        if self.redis and self.redis.connected:
            redis_key = f"{self.prefix}{product_id}"
            cached_data = await self.redis.get(redis_key)
            
            if cached_data:
                try:
                    self.stats["redis_hits"] += 1
                    logger.debug(f"Cache hit: producto {product_id} obtenido de Redis")
                    return json.loads(cached_data)
                except json.JSONDecodeError:
                    logger.warning(f"Datos corruptos en Redis para producto {product_id}")
                    self.stats["redis_misses"] += 1
            else:
                self.stats["redis_misses"] += 1
        
        # 2. Intentar obtener del catálogo local
        if self.local_catalog:
            local_product = self._get_from_local_catalog(product_id)
            if local_product:
                self.stats["local_catalog_hits"] += 1
                logger.debug(f"Producto {product_id} obtenido del catálogo local")
                # Guardar en Redis para futuras consultas
                await self._save_to_redis(product_id, local_product)
                return local_product
        
        # 3. Intentar obtener de Shopify
        if self.shopify_client:
            try:
                shopify_product = await self._get_from_shopify(product_id)
                if shopify_product:
                    self.stats["shopify_hits"] += 1
                    logger.debug(f"Producto {product_id} obtenido de Shopify")
                    # Guardar en Redis para futuras consultas
                    await self._save_to_redis(product_id, shopify_product)
                    return shopify_product
            except Exception as e:
                logger.error(f"Error obteniendo producto {product_id} de Shopify: {str(e)}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
        
        # 4. Intentar obtener del gateway de productos externos
        if self.product_gateway:
            try:
                # Intentar obtener de Retail API directamente
                gateway_product = await self.product_gateway.get_product_from_retail_api(product_id)
                if gateway_product:
                    self.stats["gateway_hits"] += 1
                    logger.info(f"Producto {product_id} obtenido de Retail API mediante gateway")
                    # Guardar en Redis para futuras consultas
                    await self._save_to_redis(product_id, gateway_product)
                    return gateway_product
                    
                # Si no está en Retail API, probar con otras fuentes externas
                external_product = await self.product_gateway.get_product_from_external_api(product_id)
                if external_product:
                    self.stats["gateway_hits"] += 1
                    logger.info(f"Producto {product_id} obtenido de API externo mediante gateway")
                    # Guardar en Redis para futuras consultas
                    await self._save_to_redis(product_id, external_product)
                    return external_product
            except Exception as e:
                logger.error(f"Error obteniendo producto {product_id} del gateway: {str(e)}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
        
        # 5. Si llegamos aquí, intentar crear un producto mínimo para evitar error
        if os.getenv("ENABLE_MINIMAL_PRODUCTS", "False").lower() == "true":
            logger.warning(f"Creando producto mínimo para ID {product_id} (último recurso)")
            minimal_product = {
                "id": product_id,
                "title": f"Producto {product_id}",
                "body_html": f"Información no disponible para el producto {product_id}",
                "product_type": "Desconocido",
                "variants": [{"price": "0.0"}],
                "_is_minimal": True  # Marcar como producto mínimo
            }
            # Guardar en Redis con TTL más corto para forzar actualización pronto
            await self._save_to_redis(product_id, minimal_product, ttl_override=300)  # 5 minutos
            return minimal_product
        
        # Si llegamos aquí, no se encontró el producto
        self.stats["total_failures"] += 1
        logger.warning(f"No se pudo encontrar el producto {product_id} en ninguna fuente")
        return None
    
    def _get_from_local_catalog(self, product_id: str) -> Optional[Dict]:
        """
        Obtiene un producto del catálogo local.
        
        Args:
            product_id: ID del producto
            
        Returns:
            Dict con datos del producto o None si no se encuentra
        """
        if not self.local_catalog:
            return None
            
        try:
            # Verificar si tiene método get_product_by_id
            if hasattr(self.local_catalog, 'get_product_by_id'):
                return self.local_catalog.get_product_by_id(product_id)
                
            # Alternativa: buscar manualmente en product_data
            if hasattr(self.local_catalog, 'product_data'):
                for product in self.local_catalog.product_data:
                    if str(product.get('id', '')) == str(product_id):
                        return product
        except Exception as e:
            logger.error(f"Error al buscar en catálogo local: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            
        return None
    
    async def _get_from_shopify(self, product_id: str) -> Optional[Dict]:
        """
        Obtiene un producto de Shopify.
        
        Args:
            product_id: ID del producto
            
        Returns:
            Dict con datos del producto o None si no se encuentra
        """
        if not self.shopify_client:
            return None
            
        try:
            # Manejar cliente síncrono o asíncrono
            if hasattr(self.shopify_client, 'get_product_async'):
                return await self.shopify_client.get_product_async(product_id)
            elif hasattr(self.shopify_client, 'get_product'):
                # Llamar método síncrono en thread pool para no bloquear
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, self.shopify_client.get_product, product_id
                )
        except Exception as e:
            logger.error(f"Error consultando Shopify para producto {product_id}: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            
        return None
    
    async def _save_to_redis(self, product_id: str, product_data: Dict, ttl_override: Optional[int] = None) -> bool:
        """
        Guarda un producto en Redis.
        
        Args:
            product_id: ID del producto
            product_data: Datos del producto
            ttl_override: Tiempo de vida personalizado (opcional)
            
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        if not self.redis or not self.redis.connected:
            return False
            
        try:
            redis_key = f"{self.prefix}{product_id}"
            json_data = json.dumps(product_data)
            ttl = ttl_override if ttl_override is not None else self.ttl_seconds
            return await self.redis.set(redis_key, json_data, ex=ttl)
        except Exception as e:
            logger.error(f"Error guardando producto {product_id} en Redis: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def preload_products(self, product_ids: List[str], concurrency: int = 5):
        """
        Precarga múltiples productos en la caché.
        
        Args:
            product_ids: Lista de IDs de productos a precargar
            concurrency: Nivel de concurrencia máximo
        """
        if not product_ids:
            return
            
        # Usar semáforo para limitar concurrencia
        semaphore = asyncio.Semaphore(concurrency)
        
        async def load_with_semaphore(pid):
            async with semaphore:
                await self.get_product(pid)
        
        # Crear y ejecutar tareas en paralelo
        tasks = [load_with_semaphore(pid) for pid in product_ids]
        await asyncio.gather(*tasks)
        
        logger.info(f"Precargados {len(product_ids)} productos en caché")
    
    async def invalidate(self, product_id: str) -> bool:
        """
        Invalida un producto en la caché.
        
        Args:
            product_id: ID del producto a invalidar
            
        Returns:
            bool: True si se invalidó correctamente, False en caso contrario
        """
        if not self.redis or not self.redis.connected:
            return False
            
        try:
            redis_key = f"{self.prefix}{product_id}"
            await self.redis.delete(redis_key)
            logger.debug(f"Producto {product_id} invalidado en caché")
            return True
        except Exception as e:
            logger.error(f"Error invalidando producto {product_id} en Redis: {str(e)}")
            return False
    
    async def invalidate_multiple(self, product_ids: List[str]) -> int:
        """
        Invalida múltiples productos en la caché.
        
        Args:
            product_ids: Lista de IDs de productos a invalidar
            
        Returns:
            int: Número de productos invalidados correctamente
        """
        if not self.redis or not self.redis.connected:
            return 0
            
        success_count = 0
        for pid in product_ids:
            if await self.invalidate(pid):
                success_count += 1
                
        logger.info(f"Invalidados {success_count}/{len(product_ids)} productos en caché")
        return success_count
    
    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas de uso del sistema de caché.
        
        Returns:
            Dict con estadísticas
        """
        total_hits = (
            self.stats["redis_hits"] + 
            self.stats["local_catalog_hits"] + 
            self.stats["shopify_hits"] + 
            self.stats["gateway_hits"]  # Incluir hits del gateway
        )
        hit_ratio = total_hits / self.stats["total_requests"] if self.stats["total_requests"] > 0 else 0
        
        return {
            "hit_ratio": hit_ratio,
            "total_requests": self.stats["total_requests"],
            "redis_hits": self.stats["redis_hits"],
            "redis_misses": self.stats["redis_misses"], 
            "local_catalog_hits": self.stats["local_catalog_hits"],
            "shopify_hits": self.stats["shopify_hits"],
            "gateway_hits": self.stats["gateway_hits"],  # Incluir hits del gateway
            "total_failures": self.stats["total_failures"],
            "ttl_seconds": self.ttl_seconds
        }
