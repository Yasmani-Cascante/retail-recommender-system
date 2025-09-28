# src/api/core/redis_connection_pool.py
"""
Connection Pool para Redis - Evita conexiones múltiples simultáneas
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class RedisConnectionPool:
    """
    Pool de conexiones Redis para evitar múltiples conexiones simultáneas
    """
    _instance = None
    _connection_lock = asyncio.Lock()
    _connected_clients = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    async def get_or_create_connection(cls, redis_client):
        """
        Obtiene una conexión existente o crea una nueva de forma thread-safe
        """
        client_id = id(redis_client)
        
        # Si ya está conectado, retornar inmediatamente
        if hasattr(redis_client, 'connected') and redis_client.connected:
            return True
        
        # Si ya hay un proceso de conexión en curso para este cliente, esperar
        if client_id in cls._connected_clients:
            try:
                return await cls._connected_clients[client_id]
            except Exception:
                # Si el future falló, continuar con nueva conexión
                cls._connected_clients.pop(client_id, None)
        
        # Usar lock para evitar conexiones simultáneas
        async with cls._connection_lock:
            # Double-check después del lock
            if hasattr(redis_client, 'connected') and redis_client.connected:
                return True
            
            # Crear future para este cliente
            future = asyncio.Future()
            cls._connected_clients[client_id] = future
            
            try:
                # Intentar conectar
                connection_result = await redis_client.connect()
                future.set_result(connection_result)
                return connection_result
                
            except Exception as e:
                future.set_exception(e)
                raise
            finally:
                # Limpiar el future
                cls._connected_clients.pop(client_id, None)

# Función helper para usar en inventory_service
async def ensure_redis_connected(redis_client) -> bool:
    """
    Función helper para asegurar conexión Redis con pooling
    """
    if not redis_client:
        return False
    
    try:
        pool = RedisConnectionPool()
        return await pool.get_or_create_connection(redis_client)
    except Exception as e:
        logger.debug(f"Redis connection failed: {e}")
        return False
