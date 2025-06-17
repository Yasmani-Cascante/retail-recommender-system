# verify_redis_connection.py
import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_redis_connection():
    """Prueba la conexión a Redis con la configuración actual."""
    try:
        # Cargar variables de entorno
        load_dotenv()
        
        # Importar módulo Redis
        try:
            import redis.asyncio as redis
            logger.info("✅ Módulo redis importado correctamente")
        except ImportError:
            logger.error("❌ Error importando módulo redis. Verifica la instalación con: pip install redis>=4.6.0")
            return False
        
        # Obtener configuración de Redis
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD", "")
        redis_ssl = os.getenv("REDIS_SSL", "False").lower() == "true"
        use_redis_cache = os.getenv("USE_REDIS_CACHE", "False").lower() == "true"
        
        # Verificar si Redis está habilitado
        if not use_redis_cache:
            logger.warning("⚠️ Redis está desactivado (USE_REDIS_CACHE=False). Actívalo para usar el sistema de caché.")
            return False
        
        # Construir URL de Redis
        redis_url = f"redis{'s' if redis_ssl else ''}://{redis_password + '@' if redis_password else ''}{redis_host}:{redis_port}/{redis_db}"
        logger.info(f"📝 Configuración Redis: {redis_host}:{redis_port}, SSL={redis_ssl}, DB={redis_db}")
        
        # Intentar conectar
        logger.info(f"🔄 Conectando a Redis...")
        client = await redis.from_url(
            redis_url,
            decode_responses=True,
            health_check_interval=30
        )
        
        # Verificar conexión con ping
        pong = await client.ping()
        if pong:
            logger.info(f"✅ Conexión exitosa a Redis. Respuesta: {pong}")
            
            # Probar operaciones básicas
            test_key = "test:connection"
            test_value = f"test_value_{int(asyncio.get_event_loop().time())}"
            
            # Guardar valor
            await client.set(test_key, test_value, ex=60)
            logger.info(f"✅ SET exitoso: {test_key}={test_value}")
            
            # Leer valor
            read_value = await client.get(test_key)
            logger.info(f"✅ GET exitoso: {test_key}={read_value}")
            
            if read_value == test_value:
                logger.info("✅ Verificación completa: Redis funciona correctamente")
            else:
                logger.error(f"❌ Verificación fallida: Valor leído ({read_value}) no coincide con valor guardado ({test_value})")
                return False
            
            # Limpiar clave de prueba
            await client.delete(test_key)
            logger.info(f"✅ DELETE exitoso: {test_key}")
            
            # Obtener información del servidor
            info = await client.info()
            logger.info(f"📊 Información del servidor Redis:")
            logger.info(f"   - Versión: {info.get('redis_version')}")
            logger.info(f"   - Memoria usada: {info.get('used_memory_human')}")
            logger.info(f"   - Clientes conectados: {info.get('connected_clients')}")
            logger.info(f"   - Tiempo activo: {info.get('uptime_in_days')} días")
            
            return True
        else:
            logger.error("❌ Error: Redis no respondió al ping")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error conectando a Redis: {str(e)}")
        import traceback
        logger.debug(traceback.format_exc())
        return False

async def diagnose_redis_config():
    """Diagnostica problemas comunes con la configuración de Redis."""
    # Cargar variables de entorno
    load_dotenv()
    
    # Verificar variables críticas
    required_vars = [
        "USE_REDIS_CACHE",
        "REDIS_HOST",
        "REDIS_PORT"
    ]
    
    missing_vars = []
    for var in required_vars:
        if var not in os.environ:
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"❌ Faltan variables de entorno requeridas: {', '.join(missing_vars)}")
        logger.info("📝 Asegúrate de definir todas las variables requeridas en tu archivo .env o variables de entorno")
        return
    
    # Verificar valores
    use_redis_cache = os.getenv("USE_REDIS_CACHE", "").lower()
    if use_redis_cache not in ["true", "false"]:
        logger.warning(f"⚠️ Valor incorrecto para USE_REDIS_CACHE: '{use_redis_cache}'. Debe ser 'true' o 'false'")
    
    try:
        redis_port = int(os.getenv("REDIS_PORT", "0"))
        if redis_port <= 0 or redis_port > 65535:
            logger.warning(f"⚠️ Puerto Redis inválido: {redis_port}. Debe estar entre 1 y 65535")
    except ValueError:
        logger.error(f"❌ REDIS_PORT no es un número válido: '{os.getenv('REDIS_PORT')}'")
    
    # Verificar cache_enable_background_tasks
    cache_bg_tasks = os.getenv("CACHE_ENABLE_BACKGROUND_TASKS", "").lower()
    if cache_bg_tasks not in ["true", "false"]:
        logger.warning(f"⚠️ Valor incorrecto para CACHE_ENABLE_BACKGROUND_TASKS: '{cache_bg_tasks}'. Debe ser 'true' o 'false'")
    
    # Verificar dependencias
    try:
        import redis
        logger.info(f"✅ Redis instalado: versión {redis.__version__}")
        if not hasattr(redis, 'asyncio'):
            logger.warning("⚠️ Esta versión de redis no tiene soporte asíncrono (redis.asyncio). Actualiza a redis>=4.6.0")
    except ImportError:
        logger.error("❌ Redis no está instalado. Instálalo con: pip install redis>=4.6.0")
    
    try:
        # import aioredis
        import redis.asyncio as redis
        logger.warning("⚠️ El paquete aioredis está obsoleto. Se recomienda usar redis>=4.6.0 que incluye soporte asíncrono")
    except ImportError:
        pass  # No es necesario tener aioredis instalado
    
    logger.info("🔍 Diagnóstico completo")

async def main():
    """Función principal del script."""
    logger.info("=== VERIFICACIÓN DE CONEXIÓN REDIS ===")
    
    # Diagnosticar configuración
    await diagnose_redis_config()
    
    # Probar conexión
    logger.info("\n=== PRUEBA DE CONEXIÓN REDIS ===")
    connection_ok = await test_redis_connection()
    
    # Resultado final
    if connection_ok:
        logger.info("\n✅ RESULTADO: Redis está configurado correctamente y funciona")
        sys.exit(0)
    else:
        logger.error("\n❌ RESULTADO: Hay problemas con la conexión a Redis")
        logger.info("\nRecomendaciones:")
        logger.info("1. Verifica que el servidor Redis esté en ejecución")
        logger.info("2. Comprueba las variables de entorno (REDIS_HOST, REDIS_PORT, etc.)")
        logger.info("3. Si estás usando Docker, asegúrate de mapear correctamente los puertos")
        logger.info("4. Si usas un servicio cloud (MemoryStore), verifica la configuración de red y permisos")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())