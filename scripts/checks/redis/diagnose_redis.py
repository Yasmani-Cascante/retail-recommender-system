# diagnose_redis.py
import asyncio
import logging
import os
import ssl
import time
import redis.asyncio as redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_redis_connection(host, port, password, username="default", use_ssl=True):
    logger.info(f"Probando conexión a Redis: {host}:{port}, SSL={use_ssl}")
    
    # Construir URL
    if username and password:
        auth_part = f"{username}:{password}@"
    elif password:
        auth_part = f"{password}@"
    else:
        auth_part = ""
        
    redis_url = f"redis{'s' if use_ssl else ''}://{auth_part}{host}:{port}/0"
    logger.info(f"URL: {redis_url.replace(password, '***')}")
    
    # Configuración con SSL
    if use_ssl:
        try:
            # Con verificación SSL
            logger.info("Intentando con verificación SSL estándar...")
            client = await redis.from_url(
                redis_url,
                decode_responses=True,
                health_check_interval=30
            )
            await client.ping()
            logger.info("✅ Conexión exitosa con SSL estándar")
            return True
        except Exception as e:
            logger.warning(f"❌ Falló con SSL estándar: {str(e)}")
            
            # Con SSL pero sin verificación
            try:
                logger.info("Intentando con SSL sin verificación...")
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                client = await redis.from_url(
                    redis_url,
                    decode_responses=True,
                    health_check_interval=30,
                    ssl_context=ssl_context
                )
                await client.ping()
                logger.info("✅ Conexión exitosa con SSL sin verificación")
                return True
            except Exception as e:
                logger.warning(f"❌ Falló con SSL sin verificación: {str(e)}")
    
    # Sin SSL
    try:
        logger.info("Intentando sin SSL...")
        redis_url = f"redis://{auth_part}{host}:{port}/0"
        client = await redis.from_url(
            redis_url,
            decode_responses=True,
            health_check_interval=30
        )
        await client.ping()
        logger.info("✅ Conexión exitosa sin SSL")
        return True
    except Exception as e:
        logger.error(f"❌ Falló sin SSL: {str(e)}")
    
    logger.error("❌ Todas las conexiones fallaron")
    return False

async def main():
    # Cargar configuración desde variables de entorno
    host = os.getenv("REDIS_HOST", "redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com")
    port = int(os.getenv("REDIS_PORT", "14272"))
    password = os.getenv("REDIS_PASSWORD", "34rleeRxTmFYqBZpSA5UoDP71bHEq6zO")
    username = os.getenv("REDIS_USERNAME", "default")
    
    # Probar con SSL
    logger.info("=== Prueba con SSL ===")
    await test_redis_connection(host, port, password, username, use_ssl=True)
    
    # Probar sin SSL
    logger.info("\n=== Prueba sin SSL ===")
    await test_redis_connection(host, port, password, username, use_ssl=False)

if __name__ == "__main__":
    asyncio.run(main())