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
from datetime import datetime, timedelta
from collections import defaultdict
import random

logger = logging.getLogger(__name__)

class ProductCache:
    """
    Sistema de caché híbrido para productos con Redis y fallback a otras fuentes.
    """
    
    def __init__(
        self, 
        redis_service, 
        local_catalog=None, 
        shopify_client=None, 
        product_gateway=None,
        ttl_seconds=3600,
        prefix="product:"
    ):
        """
        Inicializa el sistema de caché de productos.
        
        Args:
            redis_service: Servicio Redis inicializado
            local_catalog: Catálogo local (TFIDFRecommender)
            shopify_client: Cliente de Shopify para fallback
            product_gateway: Gateway para productos externos (opcional)
            ttl_seconds: Tiempo de vida en caché (segundos)
            prefix: Prefijo para claves en Redis
        """
        self.redis = redis_service
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
        # Nuevos atributos para warm-up inteligente
        self.access_frequency = defaultdict(int)  # Frecuencia de acceso por producto
        self.last_access = {}  # Último acceso por producto
        self.market_popularity = defaultdict(lambda: defaultdict(int))  # Popularidad por mercado
        self.category_stats = defaultdict(int)  # Estadísticas por categoría
        
        # Iniciar background task para health check periódico (opcional)
        self.health_task = None
        logger.info(f"Sistema de caché de productos inicializado. TTL: {ttl_seconds}s, Prefix: {prefix}")
        
    
    async def get_cached_product_ids(self, pattern: str = None) -> List[str]:
        """
        Obtiene IDs de productos en cache.
        
        Args:
            pattern: Patrón para filtrar keys
            
        Returns:
            Lista de IDs de productos en cache
        """
        try:
            if not self.redis:
                return []
            
            # Usar pattern o default
            search_pattern = pattern or f"{self.prefix}*"
            
            # Get keys usando Redis
            if hasattr(self.redis, 'keys'):
                keys = await self.redis.keys(search_pattern)
            else:
                # Fallback si no hay método keys
                return []
            
            # Extraer IDs de productos
            product_ids = []
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                # Solo incluir keys de productos, no de metadata
                if key.startswith(self.prefix) and not any(
                    exclude in key for exclude in ['recent_products_', 'popular_', 'stats_']
                ):
                    product_id = key.replace(self.prefix, '')
                    if product_id:
                        product_ids.append(product_id)
            
            return product_ids
            
        except Exception as e:
            logger.error(f"Error obteniendo cached product IDs: {e}")
            return []

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
        
        # Actualizar estadísticas de acceso para warm-up inteligente
        self.access_frequency[product_id] += 1
        self.last_access[product_id] = datetime.now()
        
        # 1. Intentar obtener de Redis
        if self.redis and self.redis._connected:
            redis_key = f"{self.prefix}{product_id}"
            cached_data = await self.redis.get(redis_key)
            
            if cached_data:
                try:
                    self.stats["redis_hits"] += 1
                    logger.debug(f"Cache hit: producto {product_id} obtenido de Redis")
                    product_data = json.loads(cached_data)
                    
                    # Actualizar estadísticas de mercado si está disponible
                    market_id = getattr(asyncio.current_task(), 'market_context', {}).get('market_id', 'default')
                    self.market_popularity[market_id][product_id] += 1
                    
                    # Actualizar estadísticas de categoría
                    category = product_data.get('product_type') or product_data.get('category', 'unknown')
                    self.category_stats[category] += 1
                    
                    return product_data
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
        if not self.redis or not self.redis._connected:
            return False
            
        try:
            redis_key = f"{self.prefix}{product_id}"
            json_data = json.dumps(product_data)
            ttl = ttl_override if ttl_override is not None else self.ttl_seconds
            # return await self.redis.set(redis_key, json_data, ex=ttl)
            return await self.redis.set(redis_key, json_data, ttl=ttl)
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
        if not self.redis or not self.redis._connected:
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
        if not self.redis or not self.redis._connected:
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
            "ttl_seconds": self.ttl_seconds,
            "access_frequency_top10": dict(sorted(self.access_frequency.items(), key=lambda x: x[1], reverse=True)[:10]),
            "category_stats": dict(self.category_stats),
            "market_popularity_summary": {k: len(v) for k, v in self.market_popularity.items()}
        }
    
    # ===========================================
    # MÉTODOS DE WARM-UP INTELIGENTE OPTIMIZADOS
    # ===========================================
    
    async def intelligent_cache_warmup(
        self, 
        market_priorities: List[str] = None, 
        max_products_per_market: int = 100,
        include_trending: bool = True,
        include_popular_categories: bool = True
    ):
        """
        Precarga inteligente basada en popularidad por mercado y patrones de acceso.
        
        Args:
            market_priorities: Lista de mercados priorizados ['US', 'ES', 'MX', 'CL']
            max_products_per_market: Máximo productos a precargar por mercado
            include_trending: Incluir productos con tendencia de acceso
            include_popular_categories: Incluir productos de categorías populares
        """
        if not market_priorities:
            market_priorities = ['US', 'ES', 'MX', 'CL', 'default']
            
        logger.info(f"Iniciando warm-up inteligente para mercados: {market_priorities}")
        start_time = time.time()
        total_preloaded = 0
        
        for market in market_priorities:
            try:
                # 1. Obtener productos populares del mercado
                popular_products = await self.get_popular_products(market, max_products_per_market // 2)
                
                # 2. Obtener productos de acceso frecuente
                frequent_products = self._get_frequently_accessed_products(max_products_per_market // 4)
                
                # 3. Incluir productos trending si está habilitado
                trending_products = []
                if include_trending:
                    trending_products = self._get_trending_products(max_products_per_market // 4)
                
                # 4. Incluir productos de categorías populares
                category_products = []
                if include_popular_categories:
                    category_products = await self._get_popular_category_products(market, max_products_per_market // 4)
                
                # 5. Combinar y deduplicar
                all_products = list(set(
                    popular_products + frequent_products + trending_products + category_products
                ))
                
                # 6. Limitar a max_products_per_market
                products_to_preload = all_products[:max_products_per_market]
                
                if products_to_preload:
                    logger.info(f"Precargando {len(products_to_preload)} productos para mercado {market}")
                    await self.preload_products(products_to_preload, concurrency=8)
                    total_preloaded += len(products_to_preload)
                else:
                    logger.warning(f"No se encontraron productos para precargar en mercado {market}")
                    
            except Exception as e:
                logger.error(f"Error en warm-up para mercado {market}: {str(e)}")
                continue
        
        elapsed_time = time.time() - start_time
        logger.info(f"Warm-up inteligente completado: {total_preloaded} productos en {elapsed_time:.2f}s")
        
        return {
            "success": True,
            "total_preloaded": total_preloaded,
            "markets_processed": len(market_priorities),
            "elapsed_time": elapsed_time
        }
    
    async def get_popular_products(self, market_id: str, limit: int = 50) -> List[str]:
        """
        Obtiene productos populares para un mercado específico.
        
        Args:
            market_id: ID del mercado
            limit: Número máximo de productos
            
        Returns:
            Lista de IDs de productos populares
        """
        try:
            # Si tenemos datos de popularidad por mercado, usarlos
            if market_id in self.market_popularity:
                market_products = self.market_popularity[market_id]
                sorted_products = sorted(market_products.items(), key=lambda x: x[1], reverse=True)
                popular_ids = [pid for pid, _ in sorted_products[:limit]]
                
                if popular_ids:
                    logger.debug(f"Encontrados {len(popular_ids)} productos populares para mercado {market_id}")
                    return popular_ids
            
            # Fallback 1: Productos recientes en cache
            cached_ids = await self.get_cached_product_ids()
            if cached_ids:
                # Simular popularidad para productos en cache
                popular_cached = cached_ids[:limit]
                if popular_cached:
                    logger.debug(f"Usando {len(popular_cached)} productos del cache para {market_id}")
                    return popular_cached
            
            # Fallback 1: Productos recientes en cache (NUEVO)
            cached_ids = await self.get_cached_product_ids()
            if cached_ids:
                # Usar productos en cache como "populares"
                popular_cached = cached_ids[:limit]
                if popular_cached:
                    logger.debug(f"Using {len(popular_cached)} cached products as popular for {market_id}")
                    return popular_cached
            
            # Fallback 2: usar catálogo local con filtrado por mercado simulado
            if self.local_catalog and hasattr(self.local_catalog, 'product_data'):
                all_products = self.local_catalog.product_data
                
                # Simular popularidad basada en hash del ID para consistencia
                market_products = []
                for product in all_products:
                    product_id = str(product.get('id', ''))
                    # Usar hash para simular popularidad consistente por mercado
                    popularity_score = hash(f"{market_id}_{product_id}") % 1000
                    market_products.append((product_id, popularity_score))
                
                # Ordenar por popularidad simulada y tomar top N
                market_products.sort(key=lambda x: x[1], reverse=True)
                popular_ids = [pid for pid, _ in market_products[:limit]]
                
                logger.debug(f"Generados {len(popular_ids)} productos simulados para mercado {market_id}")
                return popular_ids
                
        except Exception as e:
            logger.error(f"Error obteniendo productos populares para mercado {market_id}: {str(e)}")
        
        return []
    
    def _get_frequently_accessed_products(self, limit: int = 25) -> List[str]:
        """
        Obtiene productos accedidos frecuentemente.
        
        Args:
            limit: Número máximo de productos
            
        Returns:
            Lista de IDs de productos frecuentemente accedidos
        """
        if not self.access_frequency:
            return []
        
        # Ordenar por frecuencia de acceso
        sorted_by_frequency = sorted(
            self.access_frequency.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        frequent_ids = [pid for pid, _ in sorted_by_frequency[:limit]]
        logger.debug(f"Identificados {len(frequent_ids)} productos de acceso frecuente")
        
        return frequent_ids
    
    def _get_trending_products(self, limit: int = 25) -> List[str]:
        """
        Obtiene productos con tendencia de acceso reciente.
        
        Args:
            limit: Número máximo de productos
            
        Returns:
            Lista de IDs de productos trending
        """
        if not self.last_access:
            return []
        
        # Calcular trending score basado en accesos recientes
        now = datetime.now()
        trending_scores = {}
        
        for product_id, last_access_time in self.last_access.items():
            # Calcular cuánto tiempo ha pasado desde el último acceso
            time_diff = (now - last_access_time).total_seconds()
            
            # Productos accedidos en las últimas 2 horas tienen mayor score
            if time_diff < 7200:  # 2 horas
                frequency = self.access_frequency.get(product_id, 1)
                # Score mayor para productos accedidos recientemente y frecuentemente
                trending_score = frequency / (time_diff / 3600 + 1)  # Dividir por horas + 1
                trending_scores[product_id] = trending_score
        
        # Ordenar por trending score
        sorted_trending = sorted(
            trending_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        trending_ids = [pid for pid, _ in sorted_trending[:limit]]
        logger.debug(f"Identificados {len(trending_ids)} productos trending")
        
        return trending_ids
    
    async def _get_popular_category_products(self, market_id: str, limit: int = 25) -> List[str]:
        """
        Obtiene productos de categorías populares para un mercado.
        
        Args:
            market_id: ID del mercado
            limit: Número máximo de productos
            
        Returns:
            Lista de IDs de productos de categorías populares
        """
        if not self.category_stats:
            return []
        
        try:
            # Obtener top 3 categorías más populares
            top_categories = sorted(
                self.category_stats.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:3]
            
            category_products = []
            
            if self.local_catalog and hasattr(self.local_catalog, 'product_data'):
                for category, _ in top_categories:
                    # Buscar productos de esta categoría
                    category_items = []
                    for product in self.local_catalog.product_data:
                        product_category = product.get('product_type') or product.get('category', 'unknown')
                        if product_category == category:
                            category_items.append(str(product.get('id', '')))
                    
                    # Añadir algunos productos de esta categoría
                    products_per_category = min(limit // len(top_categories), len(category_items))
                    if products_per_category > 0:
                        # Usar random.sample para variedad
                        selected = random.sample(category_items, products_per_category)
                        category_products.extend(selected)
            
            logger.debug(f"Seleccionados {len(category_products)} productos de categorías populares para {market_id}")
            return category_products[:limit]
            
        except Exception as e:
            logger.error(f"Error obteniendo productos de categorías populares: {str(e)}")
            return []
    
    async def adaptive_cache_management(self):
        """
        Gestión adaptiva de caché que ajusta TTL y limpia productos obsoletos.
        """
        logger.info("Iniciando gestión adaptiva de caché")
        
        try:
            # 1. Identificar productos obsoletos (no accedidos en 24 horas)
            obsolete_threshold = datetime.now() - timedelta(hours=24)
            obsolete_products = []
            
            for product_id, last_access_time in self.last_access.items():
                if last_access_time < obsolete_threshold:
                    obsolete_products.append(product_id)
            
            # 2. Limpiar productos obsoletos
            if obsolete_products:
                cleaned_count = await self.invalidate_multiple(obsolete_products)
                logger.info(f"Limpiados {cleaned_count} productos obsoletos del caché")
            
            # 3. Precargar productos trending para mantener el caché fresco
            trending_products = self._get_trending_products(50)
            if trending_products:
                await self.preload_products(trending_products, concurrency=5)
                logger.info(f"Precargados {len(trending_products)} productos trending")
            
            return {
                "obsolete_cleaned": len(obsolete_products),
                "trending_preloaded": len(trending_products)
            }
            
        except Exception as e:
            logger.error(f"Error en gestión adaptiva de caché: {str(e)}")
            return {"error": str(e)}
