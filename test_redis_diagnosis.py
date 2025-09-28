#!/usr/bin/env python3
"""
Test de diagnóstico Redis para debugging
"""
import os
import sys
sys.path.append('src')

print("🔍 === DIAGNÓSTICO REDIS COMPLETO ===\n")

# 1. Cargar .env explícitamente
print("1️⃣ Cargando archivo .env...")
try:
    from dotenv import load_dotenv
    result = load_dotenv()
    print(f"✅ load_dotenv() result: {result}")
    print(f"✅ Archivo .env {'encontrado y cargado' if result else 'no encontrado o ya cargado'}")
except Exception as e:
    print(f"❌ Error cargando .env: {e}")

# 2. Verificar variables críticas
print("\n2️⃣ Verificando variables de entorno...")
critical_vars = ['USE_REDIS_CACHE', 'REDIS_HOST', 'REDIS_PORT', 'REDIS_SSL', 'REDIS_PASSWORD', 'REDIS_USERNAME']
for var in critical_vars:
    value = os.getenv(var, 'NOT_SET')
    if 'PASSWORD' in var and value != 'NOT_SET':
        display_value = '*' * len(value)
    else:
        display_value = value
    status = '✅' if value != 'NOT_SET' else '❌'
    print(f"  {status} {var}: {display_value}")

# 3. Probar el validador directamente
print("\n3️⃣ Probando RedisConfigValidator...")
try:
    from src.api.core.redis_config_fix import RedisConfigValidator
    print("✅ Import RedisConfigValidator exitoso")
    
    config = RedisConfigValidator.validate_and_fix_config()
    print("✅ validate_and_fix_config() exitoso")
    
    print(f"📋 Configuración validada:")
    for key, value in config.items():
        if 'password' in key.lower() and value:
            display_value = '*' * len(str(value))
        else:
            display_value = value
        print(f"  {key}: {display_value}")
    
    if config.get('use_redis_cache'):
        print("\n4️⃣ Configuración Redis válida - creando cliente...")
        try:
            from src.api.core.redis_config_fix import PatchedRedisClient
            print("✅ Import PatchedRedisClient exitoso")
            
            client = PatchedRedisClient(use_validated_config=True)
            print("✅ Cliente Redis creado exitosamente")
            print(f"✅ Cliente tipo: {type(client).__name__}")
            print(f"✅ SSL habilitado: {getattr(client, 'ssl', 'Unknown')}")
            print(f"✅ Host: {getattr(client, 'host', 'Unknown')}")
            print(f"✅ Puerto: {getattr(client, 'port', 'Unknown')}")
            
        except Exception as e:
            print(f"❌ Error creando cliente: {e}")
    else:
        print("⚠️ Redis cache desactivado por configuración")
        
except Exception as e:
    print(f"❌ Error en validación: {e}")
    import traceback
    traceback.print_exc()

# 5. Test de conexión (si llegamos hasta aquí)
print("\n5️⃣ Test de conexión (si el cliente fue creado)...")
try:
    if 'client' in locals():
        print("🔗 Intentando conexión...")
        # No podemos hacer await aquí, solo reportamos que el cliente fue creado
        print("✅ Cliente listo para conexión asíncrona")
        print("📝 Para test de conexión completo, usar contexto async")
    else:
        print("⚠️ Cliente no creado, saltando test de conexión")
except Exception as e:
    print(f"❌ Error en test de conexión: {e}")

print("\n🏁 === DIAGNÓSTICO COMPLETADO ===")
