"""
Script de diagnóstico para verificar la conexión Redis
"""
import asyncio
import os
import logging
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_redis_connection():
    """Prueba detallada de conexión Redis"""
    load_dotenv()
    
    # Obtener configuración
    host = os.getenv("REDIS_HOST")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD")
    username = os.getenv("REDIS_USERNAME", "default")
    ssl = os.getenv("REDIS_SSL", "false").lower() == "true"
    
    print(f"🔍 Configuración Redis:")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Username: {username}")
    print(f"  Password: {'***' if password else 'None'}")
    print(f"  SSL: {ssl}")
    
    try:
        from src.api.core.redis_client import RedisClient
        
        client = RedisClient(
            host=host,
            port=port,
            password=password,
            username=username,
            ssl=ssl
        )
        
        print(f"\n🔗 Intentando conexión...")
        connected = await client.connect()
        
        if connected:
            print("✅ Conexión exitosa!")
            
            # Probar operaciones básicas
            test_key = "test:health_check"
            test_value = "redis_working"
            
            # Set
            set_ok = await client.set(test_key, test_value, ex=60)
            print(f"📝 Set operation: {'✅' if set_ok else '❌'}")
            
            # Get
            get_result = await client.get(test_key)
            print(f"📖 Get operation: {'✅' if get_result == test_value else '❌'}")
            print(f"   Retrieved: {get_result}")
            
            # Health check
            health = await client.health_check()
            print(f"❤️ Health check: {health}")
            
            # Cleanup
            await client.delete(test_key)
            print("🧹 Cleanup completed")
            
            return True
            
        else:
            print("❌ Conexión fallida")
            return False
            
    except Exception as e:
        print(f"💥 Error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_factory_method():
    """Prueba el método de fábrica"""
    print(f"\n🏭 Probando método de fábrica...")
    
    try:
        from src.api.factories import RecommenderFactory
        
        redis_client = RecommenderFactory.create_redis_client()
        
        if redis_client:
            print("✅ Cliente Redis creado con factory method")
            
            # Intentar conexión
            connected = await redis_client.connect()
            
            if connected:
                print("✅ Conexión via factory method exitosa!")
                
                # Test básico
                test_result = await redis_client.set("test:factory", "working", ex=30)
                print(f"📝 Test set via factory: {'✅' if test_result else '❌'}")
                
                # Cleanup
                await redis_client.delete("test:factory")
                
                return True
            else:
                print("❌ No se pudo conectar via factory method")
                return False
        else:
            print("❌ No se pudo crear cliente Redis con factory method")
            return False
            
    except Exception as e:
        print(f"💥 Error en factory method: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Función principal de diagnóstico"""
    print("🚀 Iniciando diagnóstico Redis...")
    
    # Test 1: Conexión directa
    result1 = await test_redis_connection()
    
    # Test 2: Método de fábrica
    result2 = await test_factory_method()
    
    print(f"\n📋 Resumen:")
    print(f"  Conexión directa: {'✅' if result1 else '❌'}")
    print(f"  Factory method: {'✅' if result2 else '❌'}")
    
    if result1 and result2:
        print("\n🎉 ¡Todos los tests pasaron! Redis está funcionando correctamente.")
    else:
        print("\n⚠️ Algunos tests fallaron. Revisar configuración de Redis.")

if __name__ == "__main__":
    asyncio.run(main())
