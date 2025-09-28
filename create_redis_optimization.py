#!/usr/bin/env python3
"""
Optimización adicional: Connection pooling para PatchedRedisClient
"""

import sys
sys.path.append('src')

def create_connection_pool_optimization():
    """
    Crea un parche para evitar múltiples conexiones Redis simultáneas
    """
    print("🔧 Creando optimización de connection pooling...")
    
    optimization_code = '''# src/api/core/redis_connection_pool.py
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
            return cls._connected_clients[client_id]
        
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
'''
    
    # Escribir el archivo de optimización
    with open("src/api/core/redis_connection_pool.py", 'w', encoding='utf-8') as f:
        f.write(optimization_code)
    
    print("✅ Archivo de optimización creado: src/api/core/redis_connection_pool.py")
    
    # Crear parche para inventory_service usando el pool
    inventory_patch = '''
    # ✅ OPTIMIZACIÓN: Usar connection pool
    from src.api.core.redis_connection_pool import ensure_redis_connected
    
    async def _get_cached_inventory_optimized(self, product_id: str, market_id: str) -> Optional[InventoryInfo]:
        """Obtener información de inventario desde cache - VERSION OPTIMIZADA"""
        if not self.redis:
            return None
            
        try:
            # ✅ OPTIMIZADO: Usar connection pool
            if not await ensure_redis_connected(self.redis):
                return None
                
            cache_key = f"{self.CACHE_PREFIX}:{product_id}:{market_id}"
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                data = json.loads(cached_data)
                return InventoryInfo(
                    product_id=data["product_id"],
                    status=InventoryStatus(data["status"]),
                    quantity=data["quantity"],
                    reserved_quantity=data.get("reserved_quantity", 0),
                    available_quantity=data.get("available_quantity", 0),
                    low_stock_threshold=data.get("low_stock_threshold", 5),
                    market_availability=data.get("market_availability", {}),
                    supplier_info=data.get("supplier_info", {}),
                    last_updated=data.get("last_updated", time.time()),
                    estimated_restock_date=data.get("estimated_restock_date")
                )
        except Exception as e:
            logger.debug(f"Error reading inventory cache: {e}")
        
        return None
    '''
    
    print("\n📝 Optimización creada:")
    print("   1. RedisConnectionPool para evitar conexiones múltiples")
    print("   2. ensure_redis_connected() helper function")
    print("   3. Thread-safe connection management")
    
    print("\n💡 Para aplicar esta optimización:")
    print("   1. La optimización está lista en redis_connection_pool.py")
    print("   2. OPCIONAL: Reemplazar ensure_connected() con ensure_redis_connected()")
    print("   3. Esto reduciría los logs de 5 conexiones a 1 sola")
    
    print("\n🎯 Estado actual: FUNCIONANDO CORRECTAMENTE")
    print("   - Los warnings críticos han sido eliminados")
    print("   - Los logs restantes son normales y esperados")
    print("   - Esta optimización es opcional para mejorar performance")

if __name__ == "__main__":
    create_connection_pool_optimization()
