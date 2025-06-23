# test_redis_connection.py
"""
Test específico para verificar conexión Redis con autenticación.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Añadir path del proyecto
root_dir = Path(__file__).resolve().parent
sys.path.append(str(root_dir))

def test_redis_direct():
    """Test directo con redis-py"""
    try:
        import redis
        
        # Configuración desde .env
        redis_host = os.getenv("REDIS_HOST")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_password = os.getenv("REDIS_PASSWORD")
        redis_username = os.getenv("REDIS_USERNAME", "default")
        redis_ssl = os.getenv("REDIS_SSL", "false").lower() == "true"
        redis_db = int(os.getenv("REDIS_DB", "0"))
        
        print(f"🔍 Conectando a Redis:")
        print(f"   Host: {redis_host}")
        print(f"   Port: {redis_port}")
        print(f"   Password: {'***' if redis_password else 'None'}")
        print(f"   Username: {redis_username}")
        print(f"   SSL: {redis_ssl}")
        print(f"   DB: {redis_db}")
        
        # Configurar parámetros
        connection_params = {
            "host": redis_host,
            "port": redis_port,
            "db": redis_db,
            "socket_timeout": 10,
            "retry_on_timeout": True,
            "socket_connect_timeout": 10
        }
        
        if redis_password:
            connection_params["password"] = redis_password
            
        if redis_username and redis_username != "default":
            connection_params["username"] = redis_username
        
        if redis_ssl:
            connection_params["ssl"] = True
            connection_params["ssl_cert_reqs"] = None
        
        # Crear cliente
        client = redis.Redis(**connection_params)
        
        # Test ping
        result = client.ping()
        print(f"✅ Ping exitoso: {result}")
        
        # Test set/get
        test_key = "mcp_test_key"
        test_value = "mcp_test_value"
        
        client.set(test_key, test_value, ex=60)
        retrieved = client.get(test_key)
        
        if retrieved and retrieved.decode('utf-8') == test_value:
            print("✅ Set/Get exitoso")
            client.delete(test_key)
            print("✅ Delete exitoso")
            return True
        else:
            print("❌ Set/Get falló")
            return False
            
    except Exception as e:
        print(f"❌ Error en test directo: {e}")
        return False

async def test_redis_cache_class():
    """Test con la clase RedisCache actualizada"""
    try:
        from src.api.core.cache import RedisCache
        
        print("\n🔍 Testing clase RedisCache actualizada...")
        
        cache = RedisCache()
        
        if not cache.client:
            print("❌ RedisCache: cliente no inicializado")
            return False
        
        # Test básico
        test_key = "mcp_cache_test"
        test_data = {"test": "success", "timestamp": "2025-01-01"}
        
        # Set
        success = await cache.set(test_key, test_data, expiration=60)
        if not success:
            print("❌ RedisCache: set falló")
            return False
        
        # Get
        result = await cache.get(test_key)
        if not result or result.get("test") != "success":
            print("❌ RedisCache: get falló")
            return False
        
        # Delete
        deleted = await cache.delete(test_key)
        if not deleted:
            print("❌ RedisCache: delete falló")
            return False
        
        print("✅ RedisCache funcionando correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en RedisCache: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Iniciando tests de conexión Redis...")
    
    # Test 1: Conexión directa
    print("\n" + "="*50)
    print("TEST 1: Conexión directa con redis-py")
    print("="*50)
    direct_success = test_redis_direct()
    
    # Test 2: Clase RedisCache
    print("\n" + "="*50)
    print("TEST 2: Clase RedisCache")
    print("="*50)
    
    import asyncio
    cache_success = asyncio.run(test_redis_cache_class())
    
    # Resumen
    print("\n" + "="*50)
    print("RESUMEN DE TESTS")
    print("="*50)
    print(f"Redis directo: {'✅ PASS' if direct_success else '❌ FAIL'}")
    print(f"RedisCache: {'✅ PASS' if cache_success else '❌ FAIL'}")
    
    if direct_success and cache_success:
        print("\n🎉 ¡Todos los tests de Redis pasaron!")
        print("🚀 El sistema está listo para ejecutar con Redis")
    else:
        print("\n⚠️ Algunos tests fallaron - revisar configuración")
        
        if not direct_success:
            print("❌ Problema con autenticación/conexión básica")
        if not cache_success:
            print("❌ Problema con clase RedisCache")
