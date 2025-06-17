# verify_redis_labs.py
import asyncio
import os
import logging
import redis.asyncio as redis
from dotenv import load_dotenv
import ssl as ssl_lib

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_redis_labs_connection():
    """Prueba la conexión a Redis Labs."""
    try:
        # Cargar variables de entorno
        load_dotenv(".env.redis_labs")
        
        # Obtener configuración
        redis_host = os.getenv("REDIS_HOST")
        redis_port = int(os.getenv("REDIS_PORT"))
        redis_password = os.getenv("REDIS_PASSWORD")
        redis_username = os.getenv("REDIS_USERNAME", "default")
        
        # Construir URL
        if redis_username and redis_password:
            auth_part = f"{redis_username}:{redis_password}@"
        elif redis_password:
            auth_part = f"{redis_password}@"
        else:
            auth_part = ""
            
        redis_url = f"rediss://{auth_part}{redis_host}:{redis_port}/0"
        
        logger.info(f"Conectando a Redis Labs: {redis_host}:{redis_port}")
        
        # Quitar ssl_context (no soportado en redis<5.0.0)
        client = await redis.from_url(
            redis_url,
            decode_responses=True
        )
        
        # Probar operaciones
        pong = await client.ping()
        logger.info(f"Ping exitoso: {pong}")
        
        # Probar operaciones básicas
        test_key = "test:redis_labs"
        test_value = "funcionando correctamente"
        
        await client.set(test_key, test_value, ex=60)
        logger.info(f"SET exitoso")
        
        result = await client.get(test_key)
        logger.info(f"GET exitoso: {result}")
        
        await client.delete(test_key)
        logger.info(f"DELETE exitoso")
        
        # Obtener información
        info = await client.info()
        logger.info(f"Versión de Redis: {info.get('redis_version')}")
        logger.info(f"Memoria usada: {info.get('used_memory_human')}")
        
        logger.info("✅ Conexión a Redis Labs exitosa")
        return True
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    asyncio.run(test_redis_labs_connection())