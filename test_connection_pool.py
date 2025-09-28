#!/usr/bin/env python3
"""
Test para verificar que el Connection Pool funciona
"""
import asyncio
import sys
sys.path.append('src')

async def test_connection_pool():
    print("🧪 === TEST CONNECTION POOL ===\n")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    from src.api.core.redis_config_fix import PatchedRedisClient
    from src.api.core.redis_connection_pool import ensure_redis_connected
    
    # Crear múltiples clientes (simulando operaciones paralelas)
    clients = []
    for i in range(5):
        client = PatchedRedisClient(use_validated_config=True)
        clients.append(client)
    
    print("🔗 Probando conexiones paralelas con Connection Pool...")
    
    # Ejecutar conexiones en paralelo
    start_time = asyncio.get_event_loop().time()
    
    tasks = [ensure_redis_connected(client) for client in clients]
    results = await asyncio.gather(*tasks)
    
    end_time = asyncio.get_event_loop().time()
    
    print(f"\n📊 Resultados:")
    print(f"   ⏱️ Tiempo total: {(end_time - start_time)*1000:.1f}ms")
    print(f"   ✅ Conexiones exitosas: {sum(results)}")
    print(f"   📝 Deberías ver MENOS logs de 'Intentando conexión'")
    
    # Cerrar conexiones
    for client in clients:
        try:
            await client.close()
        except:
            pass
    
    print("\n✅ Test completado")

if __name__ == "__main__":
    asyncio.run(test_connection_pool())
