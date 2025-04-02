
import redis
import json
import logging
import os
from typing import Any, Optional
import time

class RedisCache:
    """
    Cliente Redis para la caché distribuida de recomendaciones.
    Implementa el patrón Singleton para asegurar una única instancia en toda la aplicación.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisCache, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            # Obtener configuración de variables de entorno
            redis_host = os.getenv("REDIS_HOST")
            redis_port = os.getenv("REDIS_PORT", "6379")
            
            if not redis_host:
                logging.warning("REDIS_HOST no configurado. La caché está deshabilitada.")
                self.client = None
            else:
                try:
                    self.client = redis.Redis(
                        host=redis_host,
                        port=int(redis_port),
                        db=0,
                        socket_timeout=5,
                        retry_on_timeout=True
                    )
                    # Verificar conexión
                    self.client.ping()
                    logging.info(f"✅ Conectado a Redis en {redis_host}:{redis_port}")
                except Exception as e:
                    logging.error(f"❌ Error conectando a Redis: {str(e)}")
                    self.client = None
                    
            self.initialized = True
            self.stats = {
                "hits": 0,
                "misses": 0,
                "errors": 0
            }
                
    async def get(self, key: str) -> Optional[Any]:
        """
        Obtiene un valor de la caché con manejo de errores.
        
        Args:
            key: Clave a buscar
            
        Returns:
            Any: Valor almacenado, o None si no existe o hay error
        """
        if not self.client:
            return None
            
        try:
            value = self.client.get(key)
            
            if value:
                self.stats["hits"] += 1
                return json.loads(value)
                
            self.stats["misses"] += 1
            return None
            
        except Exception as e:
            self.stats["errors"] += 1
            logging.error(f"Error obteniendo valor de Redis para clave '{key}': {str(e)}")
            return None
            
    async def set(self, key: str, value: Any, expiration: int = 3600) -> bool:
        """
        Guarda un valor en la caché con expiración en segundos.
        
        Args:
            key: Clave para almacenar el valor
            value: Valor a almacenar (será serializado a JSON)
            expiration: Tiempo de expiración en segundos (por defecto 1 hora)
            
        Returns:
            bool: True si se guardó correctamente, False en caso contrario
        """
        if not self.client:
            return False
            
        try:
            serialized = json.dumps(value)
            return self.client.setex(
                key,
                expiration,
                serialized
            )
        except Exception as e:
            self.stats["errors"] += 1
            logging.error(f"Error guardando en Redis para clave '{key}': {str(e)}")
            return False
            
    async def delete(self, key: str) -> bool:
        """
        Elimina un valor de la caché.
        
        Args:
            key: Clave a eliminar
            
        Returns:
            bool: True si se eliminó correctamente, False en caso contrario
        """
        if not self.client:
            return False
            
        try:
            return self.client.delete(key) > 0
        except Exception as e:
            self.stats["errors"] += 1
            logging.error(f"Error eliminando de Redis para clave '{key}': {str(e)}")
            return False
            
    async def get_stats(self) -> dict:
        """
        Obtiene estadísticas de uso de la caché.
        
        Returns:
            dict: Diccionario con estadísticas de uso
        """
        return {
            **self.stats,
            "hit_ratio": self.stats["hits"] / (self.stats["hits"] + self.stats["misses"]) * 100 if (self.stats["hits"] + self.stats["misses"]) > 0 else 0,
            "available": self.client is not None
        }
            
    async def flush(self) -> bool:
        """
        Limpia toda la caché.
        
        Returns:
            bool: True si se limpió correctamente, False en caso contrario
        """
        if not self.client:
            return False
            
        try:
            return self.client.flushdb()
        except Exception as e:
            self.stats["errors"] += 1
            logging.error(f"Error limpiando Redis: {str(e)}")
            return False
