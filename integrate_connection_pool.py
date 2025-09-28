#!/usr/bin/env python3
"""
Script de integración para Redis Connection Pool
"""

import sys
sys.path.append('src')

def integrate_connection_pool():
    """
    Integra el Connection Pool en inventory_service.py
    """
    print("🔧 === INTEGRACIÓN REDIS CONNECTION POOL ===\n")
    
    file_path = "src/api/inventory/inventory_service.py"
    
    # Leer archivo actual
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Agregar import del connection pool
    import_line = "from src.api.core.redis_connection_pool import ensure_redis_connected"
    
    if import_line not in content:
        # Buscar la línea de imports existentes
        redis_import_line = "from src.api.core.redis_config_fix import PatchedRedisClient as RedisClient"
        
        if redis_import_line in content:
            content = content.replace(
                redis_import_line,
                redis_import_line + "\n" + import_line
            )
            print("✅ Import del connection pool agregado")
        else:
            print("❌ No se pudo encontrar la línea de import de Redis")
            return False
    else:
        print("✅ Import del connection pool ya existe")
    
    # 2. Reemplazar ensure_connected() con ensure_redis_connected()
    old_pattern = "if not await self.redis.ensure_connected():"
    new_pattern = "if not await ensure_redis_connected(self.redis):"
    
    replacements_made = content.count(old_pattern)
    content = content.replace(old_pattern, new_pattern)
    
    if replacements_made > 0:
        print(f"✅ Reemplazadas {replacements_made} llamadas a ensure_connected()")
    else:
        print("⚠️ No se encontraron llamadas a ensure_connected() para reemplazar")
    
    # 3. Crear backup
    import shutil
    backup_path = f"{file_path}.backup_pool_integration"
    shutil.copy2(file_path, backup_path)
    print(f"✅ Backup creado: {backup_path}")
    
    # 4. Escribir archivo modificado
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Integración completada")
    
    return True

def create_test_script():
    """
    Crea un script para probar la optimización
    """
    test_script = '''#!/usr/bin/env python3
"""
Test para verificar que el Connection Pool funciona
"""
import asyncio
import sys
sys.path.append('src')

async def test_connection_pool():
    print("🧪 === TEST CONNECTION POOL ===\\n")
    
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
    
    print(f"\\n📊 Resultados:")
    print(f"   ⏱️ Tiempo total: {(end_time - start_time)*1000:.1f}ms")
    print(f"   ✅ Conexiones exitosas: {sum(results)}")
    print(f"   📝 Deberías ver MENOS logs de 'Intentando conexión'")
    
    # Cerrar conexiones
    for client in clients:
        try:
            await client.close()
        except:
            pass
    
    print("\\n✅ Test completado")

if __name__ == "__main__":
    asyncio.run(test_connection_pool())
'''
    
    with open("test_connection_pool.py", 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print("✅ Script de test creado: test_connection_pool.py")

def main():
    print("🚀 REDIS CONNECTION POOL - INTEGRACIÓN AUTOMÁTICA\\n")
    
    if integrate_connection_pool():
        create_test_script()
        
        print("\\n🎯 INTEGRACIÓN COMPLETADA:")
        print("   1. ✅ Connection Pool integrado en inventory_service.py")
        print("   2. ✅ ensure_connected() reemplazado por ensure_redis_connected()")
        print("   3. ✅ Script de test creado")
        
        print("\\n📝 PARA PROBAR:")
        print("   1. Ejecuta: python test_connection_pool.py")
        print("   2. Luego prueba el endpoint /products/ nuevamente")
        print("   3. Deberías ver MENOS logs de 'Intentando conexión Redis'")
        
        print("\\n🎯 BENEFICIO ESPERADO:")
        print("   ANTES: 5 logs 'Intentando conexión Redis'")
        print("   DESPUÉS: 1 log 'Intentando conexión Redis'")
        
    else:
        print("❌ Integración falló - revisa los errores arriba")

if __name__ == "__main__":
    main()
