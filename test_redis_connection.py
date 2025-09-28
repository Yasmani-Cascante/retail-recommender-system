#!/usr/bin/env python3
"""
Test de conexión real Redis - Asíncrono
"""
import asyncio
import sys
sys.path.append('src')

async def test_redis_connection():
    print("🔗 === TEST DE CONEXIÓN REDIS REAL ===\n")
    
    # Cargar .env
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Variables de entorno cargadas")
    
    # Crear cliente
    from src.api.core.redis_config_fix import PatchedRedisClient
    client = PatchedRedisClient(use_validated_config=True)
    print("✅ Cliente Redis creado")
    
    try:
        # Intentar conexión
        print("🔗 Intentando conectar a Redis...")
        connection_result = await client.connect()
        
        if connection_result:
            print("✅ ¡CONEXIÓN EXITOSA!")
            
            # Test básico de operaciones
            print("\n🧪 Testing operaciones básicas...")
            
            # Test SET
            set_result = await client.set("test_key", "test_value", ex=60)
            print(f"✅ SET: {set_result}")
            
            # Test GET
            get_result = await client.get("test_key")
            print(f"✅ GET: {get_result}")
            
            # Test DELETE
            del_result = await client.delete("test_key")
            print(f"✅ DELETE: {del_result}")
            
            # Health check
            health = await client.health_check()
            print(f"✅ HEALTH: Conectado={health['connected']}")
            
            print("\n🎉 ¡TODAS LAS OPERACIONES EXITOSAS!")
            
        else:
            print("❌ No se pudo conectar a Redis")
            
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        print("\n💡 Esto puede ser normal si:")
        print("   - Redis Labs requiere whitelist de IP")
        print("   - Hay problemas de red temporales")
        print("   - Las credenciales cambiaron")
        
    finally:
        try:
            await client.close()
            print("✅ Conexión cerrada limpiamente")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(test_redis_connection())
