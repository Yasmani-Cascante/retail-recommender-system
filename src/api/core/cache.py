
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
            redis_password = os.getenv("REDIS_PASSWORD")
            redis_username = os.getenv("REDIS_USERNAME", "default")
            redis_ssl = os.getenv("REDIS_SSL", "false").lower() == "true"
            redis_db = int(os.getenv("REDIS_DB", "0"))
            
            if not redis_host:
                logging.warning("REDIS_HOST no configurado. La caché está deshabilitada.")
                self.client = None
            else:
                try:
                    # Configurar parámetros de conexión
                    connection_params = {
                        "host": redis_host,
                        "port": int(redis_port),
                        "db": redis_db,
                        "socket_timeout": 10,
                        "retry_on_timeout": True,
                        "socket_connect_timeout": 10
                    }
                    
                    # Agregar autenticación si está configurada
                    if redis_password:
                        connection_params["password"] = redis_password
                        
                    # Agregar username si está configurado (Redis 6+)
                    if redis_username and redis_username != "default":
                        connection_params["username"] = redis_username
                    
                    # Configurar SSL si está habilitado
                    if redis_ssl:
                        connection_params["ssl"] = True
                        connection_params["ssl_cert_reqs"] = None
                    
                    self.client = redis.Redis(**connection_params)
                    
                    # Verificar conexión
                    self.client.ping()
                    logging.info(f"✅ Conectado a Redis en {redis_host}:{redis_port} (auth: {bool(redis_password)}, ssl: {redis_ssl})")
                except Exception as e:
                    logging.error(f"❌ Error conectando a Redis: {str(e)}")
                    logging.error(f"   Host: {redis_host}, Port: {redis_port}, Auth: {bool(redis_password)}, SSL: {redis_ssl}")
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
        

# Instancia global del cache Redis (patrón singleton)
_redis_cache_instance = None

def get_redis_client():
    """
    Función factory para obtener el cliente Redis configurado.
    Compatible con el código MCP que espera esta función.
    
    Returns:
        RedisCache: Instancia del cliente Redis
    """
    global _redis_cache_instance
    
    if _redis_cache_instance is None:
        _redis_cache_instance = RedisCache()
        
    return _redis_cache_instance

# Función de compatibilidad para código asíncrono
async def get_async_redis_client():
    """
    Versión asíncrona de get_redis_client para compatibilidad.
    
    Returns:
        RedisCache: Instancia del cliente Redis
    """
    return get_redis_client()

# Clase wrapper para compatibilidad con aioredis
class AsyncRedisWrapper:
    """
    Wrapper para hacer que RedisCache sea compatible con aioredis
    Provee una interfaz asíncrona para las operaciones de Redis.
    """
    
    def __init__(self, redis_cache: RedisCache):
        self.redis_cache = redis_cache
        self.client = redis_cache.client
        self._connected = redis_cache.client is not None
    
    @property 
    def connected(self) -> bool:
        """Compatibilidad con verificación de conexión"""
        return self._connected
    
    async def get(self, key: str) -> Optional[Any]:
        """Get con interfaz aioredis-compatible"""
        result = await self.redis_cache.get(key)
        return result
    
    async def set(self, key: str, value: Any, expiration: int = 3600) -> bool:
        """Set con interfaz aioredis-compatible"""
        return await self.redis_cache.set(key, value, expiration)
    
    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        """Setex con interfaz aioredis-compatible"""
        try:
            parsed_value = json.loads(value) if isinstance(value, str) and value.startswith('{') else value
        except:
            parsed_value = value
        return await self.redis_cache.set(key, parsed_value, seconds)
    
    async def delete(self, *keys: str) -> int:
        """Delete con interfaz aioredis-compatible"""
        deleted_count = 0
        for key in keys:
            if await self.redis_cache.delete(key):
                deleted_count += 1
        return deleted_count
    
    async def keys(self, pattern: str) -> list:
        """Keys con interfaz aioredis-compatible"""
        if not self.redis_cache.client:
            return []
            
        try:
            # Usar el cliente Redis directo para operaciones de keys
            keys = self.redis_cache.client.keys(pattern)
            return [key.decode('utf-8') if isinstance(key, bytes) else key for key in keys]
        except Exception as e:
            logging.error(f"Error getting keys with pattern {pattern}: {e}")
            return []
    
    async def ttl(self, key: str) -> int:
        """TTL con interfaz aioredis-compatible"""
        if not self.redis_cache.client:
            return -1
            
        try:
            return self.redis_cache.client.ttl(key)
        except Exception as e:
            logging.error(f"Error getting TTL for key {key}: {e}")
            return -1
    
    async def ping(self) -> bool:
        """Ping con interfaz aioredis-compatible"""
        if not self.redis_cache.client:
            return False
            
        try:
            self.redis_cache.client.ping()
            return True
        except:
            return False
            
    async def exists(self, key: str) -> bool:
        """Check if a key exists"""
        if not self.redis_cache.client:
            return False
            
        try:
            return bool(self.redis_cache.client.exists(key))
        except Exception as e:
            logging.error(f"Error checking key existence for {key}: {e}")
            return False
            
    async def scan(self, cursor: int = 0, match: Optional[str] = None, count: Optional[int] = None) -> tuple:
        """Scan the keyspace - aioredis compatible"""
        if not self.redis_cache.client:
            return (0, [])
            
        try:
            scan_args = {}
            if match:
                scan_args['match'] = match
            if count:
                scan_args['count'] = count
                
            cursor, keys = self.redis_cache.client.scan(cursor, **scan_args)
            return (cursor, [key.decode('utf-8') if isinstance(key, bytes) else key for key in keys])
        except Exception as e:
            logging.error(f"Error scanning keys: {e}")
            return (0, [])
            
    async def hget(self, name: str, key: str) -> Optional[Any]:
        """Get hash field - aioredis compatible"""
        if not self.redis_cache.client:
            return None
            
        try:
            value = self.redis_cache.client.hget(name, key)
            if value:
                try:
                    return json.loads(value) if isinstance(value, bytes) else json.loads(value.decode('utf-8'))
                except:
                    return value.decode('utf-8') if isinstance(value, bytes) else value
            return None
        except Exception as e:
            logging.error(f"Error getting hash field {name}:{key}: {e}")
            return None
            
    async def hset(self, name: str, key: str, value: Any) -> bool:
        """Set hash field - aioredis compatible"""
        if not self.redis_cache.client:
            return False
            
        try:
            serialized = json.dumps(value) if not isinstance(value, (str, bytes, int, float, bool)) else value
            return bool(self.redis_cache.client.hset(name, key, serialized))
        except Exception as e:
            logging.error(f"Error setting hash field {name}:{key}: {e}")
            return False
            
    async def incr(self, name: str, amount: int = 1) -> int:
        """Increment counter - aioredis compatible"""
        if not self.redis_cache.client:
            return 0
            
        try:
            return self.redis_cache.client.incr(name, amount)
        except Exception as e:
            logging.error(f"Error incrementing counter {name}: {e}")
            return 0

def get_async_redis_wrapper():
    """
    Obtener wrapper asíncrono compatible con aioredis
    """
    redis_cache = get_redis_client()
    return AsyncRedisWrapper(redis_cache)