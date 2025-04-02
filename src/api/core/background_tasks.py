
import asyncio
import logging
import time
from src.recommenders.precomputed_recommender import PrecomputedEmbeddingRecommender
from src.api.core.cache import RedisCache

class BackgroundTaskManager:
    """
    Administrador de tareas en segundo plano para pre-calcular recomendaciones
    y realizar otras tareas asíncronas.
    """
    
    def __init__(self, recommender: PrecomputedEmbeddingRecommender, cache: RedisCache):
        self.recommender = recommender
        self.cache = cache
        self.is_running = False
        self.stats = {
            "last_run": None,
            "precalculated_items": 0,
            "errors": 0,
            "total_runs": 0
        }
        self.start_time = time.time()
        
    async def start(self):
        """
        Inicia la ejecución de tareas en segundo plano.
        """
        if self.is_running:
            logging.info("Las tareas en segundo plano ya están en ejecución")
            return
            
        self.is_running = True
        asyncio.create_task(self.run_background_tasks())
        logging.info("✅ Tareas en segundo plano iniciadas")
        
    async def run_background_tasks(self):
        """
        Ejecuta tareas periódicas en segundo plano.
        """
        while self.is_running:
            try:
                self.stats["total_runs"] += 1
                self.stats["last_run"] = time.time()
                
                # Pre-calcular recomendaciones populares
                await self.precalculate_popular_recommendations()
                
                # Esperar 1 hora antes de la próxima ejecución
                await asyncio.sleep(3600)  # 1 hora
            except Exception as e:
                self.stats["errors"] += 1
                logging.error(f"Error en tareas en segundo plano: {str(e)}")
                await asyncio.sleep(300)  # Reintentar en 5 minutos si hay error
                
    async def precalculate_popular_recommendations(self):
        """
        Pre-calcula recomendaciones para productos populares.
        En un sistema real, obtendríamos los productos más populares de analytics.
        Por ahora, usamos los primeros 20 productos como ejemplo.
        """
        if not self.recommender.product_metadata:
            logging.warning("No hay productos disponibles para pre-calcular recomendaciones")
            return
            
        # En un sistema real, obtendríamos los productos más populares de analytics
        # Por ahora, usamos los primeros 20 productos como ejemplo
        popular_products = self.recommender.product_metadata[:20]
        
        logging.info(f"Pre-calculando recomendaciones para {len(popular_products)} productos populares")
        
        precalculated_count = 0
        
        for product in popular_products:
            product_id = product.get('id')
            if not product_id:
                continue
                
            # Calcular recomendaciones para diferentes tamaños comunes
            for n in [5, 10, 20]:
                cache_key = f"recommendations:content:{product_id}:{n}"
                
                # Verificar si ya existe en caché
                existing = await self.cache.get(cache_key)
                if existing:
                    continue
                    
                # Calcular y guardar en caché
                try:
                    recommendations = self.recommender.recommend(product_id, n)
                    await self.cache.set(
                        cache_key,
                        {
                            "product_id": product_id,
                            "recommendations": recommendations,
                            "count": len(recommendations),
                            "cached_at": time.time()
                        },
                        expiration=86400  # 24 horas
                    )
                    precalculated_count += 1
                    logging.info(f"Pre-calculadas recomendaciones para producto {product_id} (n={n})")
                except Exception as e:
                    self.stats["errors"] += 1
                    logging.error(f"Error pre-calculando recomendaciones para {product_id}: {str(e)}")
                    
                # Pequeña pausa para no saturar el sistema
                await asyncio.sleep(0.1)
        
        self.stats["precalculated_items"] += precalculated_count
        logging.info(f"Pre-cálculo de recomendaciones completado. Total: {precalculated_count}")
        
    async def get_stats(self):
        """
        Obtiene estadísticas de las tareas en segundo plano.
        """
        return {
            **self.stats,
            "is_running": self.is_running,
            "uptime": time.time() - self.start_time,
            "uptime_formatted": self._format_uptime(time.time() - self.start_time)
        }
        
    def _format_uptime(self, seconds):
        """
        Formatea el tiempo en segundos a un formato legible.
        """
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{int(days)} días")
        if hours > 0:
            parts.append(f"{int(hours)} horas")
        if minutes > 0:
            parts.append(f"{int(minutes)} minutos")
        if seconds > 0 or not parts:
            parts.append(f"{int(seconds)} segundos")
            
        return ", ".join(parts)
