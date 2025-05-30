"""
Cliente Redis para el sistema de caché híbrido.

Proporciona una interfaz asíncrona para interactuar con Redis,
incluyendo manejo de errores y métricas de uso.
"""

import redis.asyncio as redis
import logging
from typing import Optional, Any, Dict
import json
import traceback
import ssl as ssl_lib

logger = logging.getLogger(__name__)

class RedisClient:
    """Cliente Redis con manejo de errores y métricas."""
    
    def __init__(
        self, 
        host='localhost', 
        port=6379, 
        db=0, 
        password=None, 
        ssl=False,
        username=None
    ):
        """
        Inicializa el cliente Redis.
        
        Args:
            host: Hostname o IP del servidor Redis
            port: Puerto del servidor Redis
            db: Número de base de datos Redis
            password: Contraseña para autenticación (opcional)
            ssl: Si debe usar conexión SSL/TLS
            username: Nombre de usuario para Redis ACL (opcional)
        """
        # Construir la URL de conexión
        if username and password:
            auth_part = f"{username}:{password}@"
        elif password:
            auth_part = f"{password}@"
        else:
            auth_part = ""
            
        self.redis_url = f"redis{'s' if ssl else ''}://{auth_part}{host}:{port}/{db}"
        self.client = None
        self.connected = False
        self.stats = {"connections": 0, "errors": 0, "operations": 0}
        self.ssl = ssl
        
    async def connect(self) -> bool:
        """
        Establece conexión con Redis.
        
        Returns:
            bool: True si la conexión fue exitosa, False en caso contrario
        """
        try:
            logger.info(f"Conectando a Redis: {self.redis_url.replace('/0', '/***')}")
            
            # Configuración específica para SSL (necesaria para Redis Labs)
            ssl_options = None
            if self.ssl:
                ssl_context = ssl_lib.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl_lib.CERT_NONE
                ssl_options = ssl_context
            
            # Crear las opciones de conexión
            connection_options = {
                "decode_responses": True,
                "health_check_interval": 30
            }
            
            # Agregar SSL solo si está habilitado
            if self.ssl and ssl_options:
                connection_options["ssl"] = True
                # No usar ssl_context directamente, puede causar error
                # en algunas versiones de redis-py
                
            self.client = await redis.from_url(
                self.redis_url,
                **connection_options
            )
            
            await self.client.ping()
            self.connected = True
            self.stats["connections"] += 1
            logger.info(f"Conexión exitosa a Redis")
            return True
        except Exception as e:
            self.connected = False
            self.stats["errors"] += 1
            logger.error(f"Error conectando a Redis: {str(e)}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """
        Obtiene un valor de Redis con manejo de errores.
        
        Args:
            key: Clave a obtener
            
        Returns:
            str: Valor almacenado o None si ocurre un error
        """
        if not self.connected or not self.client:
            logger.warning("Intento de obtener clave sin conexión a Redis")
            return None
           
        try:
            self.stats["operations"] += 1
            result = await self.client.get(key)
            if result:
                logger.debug(f"Obtenida clave {key} de Redis")
            return result
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error obteniendo clave {key} de Redis: {str(e)}")
            return None
    
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """
        Guarda un valor en Redis con manejo de errores.
        
        Args:
            key: Clave a guardar
            value: Valor a guardar
            ex: Tiempo de expiración en segundos (opcional)
            
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        if not self.connected or not self.client:
            logger.warning("Intento de guardar clave sin conexión a Redis")
            return False
            
        try:
            self.stats["operations"] += 1
            await self.client.set(key, value, ex=ex)
            logger.debug(f"Guardada clave {key} en Redis" + (f" (TTL: {ex}s)" if ex else ""))
            return True
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error guardando clave {key} en Redis: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Elimina una clave de Redis.
        
        Args:
            key: Clave a eliminar
            
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        if not self.connected or not self.client:
            return False
            
        try:
            self.stats["operations"] += 1
            await self.client.delete(key)
            logger.debug(f"Eliminada clave {key} de Redis")
            return True
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error eliminando clave {key} de Redis: {str(e)}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado de la conexión a Redis.
        
        Returns:
            dict: Estado de la conexión y estadísticas del servidor
        """
        status = {
            "connected": self.connected,
            "stats": self.stats
        }
        
        if self.connected and self.client:
            try:
                # Verificar conexión con ping
                ping_result = await self.client.ping()
                status["ping"] = ping_result
                
                # Obtener estadísticas del servidor
                info = await self.client.info()
                status["server_info"] = {
                    "version": info.get("redis_version"),
                    "used_memory_human": info.get("used_memory_human"),
                    "uptime_in_days": info.get("uptime_in_days"),
                    "connected_clients": info.get("connected_clients")
                }
            except Exception as e:
                status["error"] = str(e)
                self.connected = False
        
        return status