
"""
Prueba de conexión a Redis para verificar la configuración.

Este script verifica la conexión a Redis usando la configuración actual
y realiza operaciones básicas para validar su funcionamiento.
"""

import asyncio
import logging
import os
from src.api.core.redis_client import RedisClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_redis_connection():
    """
    Prueba la conexión a Redis con la configuración actual.
    """
    # Obtener configuración de variables de entorno
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD", "")
    db = int(os.getenv("REDIS_DB", "0"))
    ssl = os.getenv("REDIS_SSL", "False").lower() == "true"
    
    logger.info(f"Configuración Redis: {host}:{port}, DB={db}, SSL={ssl}")
    
    # Crear cliente Redis
    client = RedisClient(
        host=host,
        port=port,
        db=db,
        password=password,
        # ssl=ssl
    )
    
    # Intentar conectar
    connected = await client.connect()
    logger.info(f"Conexión establecida: {connected}")
    
    if connected:
        # Realizar operaciones de prueba
        test_key = "test:connection"
        test_value = f"redis_connection_test_{os.getpid()}"
        
        # Guardar valor
        set_result = await client.set(test_key, test_value, ex=60)
        logger.info(f"Set result: {set_result}")
        
        # Leer valor
        get_result = await client.get(test_key)
        logger.info(f"Get result: {get_result}")
        
        # Verificar si coincide
        if get_result == test_value:
            logger.info("✅ Prueba de lectura/escritura exitosa")
        else:
            logger.error(f"❌ Error en prueba de lectura/escritura. Esperado: {test_value}, Obtenido: {get_result}")
        
        # Verificar health check
        health = await client.health_check()
        logger.info(f"Health check: {health}")
        
        # Limpiar
        await client.delete(test_key)
        logger.info(f"Clave de prueba eliminada: {test_key}")
    
    return connected

if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(level=logging.INFO)
    
    # Ejecutar prueba
    asyncio.run(test_redis_connection())
