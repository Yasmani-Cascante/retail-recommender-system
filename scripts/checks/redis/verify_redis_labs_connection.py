#!/usr/bin/env python3
"""
Script para verificar la conexión a Redis Labs.

Este script verifica la conectividad directa con Redis Labs utilizando
las mismas credenciales que usa el sistema de recomendaciones.
"""

import os
import asyncio
import json
import time
import ssl as ssl_lib
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv('.env.secrets')

async def test_redis_connection():
    """Prueba la conexión a Redis Labs."""
    
    print("🔍 Verificando conexión a Redis Labs...")
    print("=" * 60)
    
    # Obtener credenciales de Redis desde variables de entorno
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_password = os.getenv("REDIS_PASSWORD", "")
    redis_username = os.getenv("REDIS_USERNAME", "")
    redis_ssl = os.getenv("REDIS_SSL", "false").lower() == "true"
    
    print(f"📡 Configuración de Redis:")
    print(f"   Host: {redis_host}")
    print(f"   Port: {redis_port}")
    print(f"   Username: {redis_username}")
    print(f"   Password: {'*' * len(redis_password) if redis_password else 'No configurada'}")
    print(f"   SSL: {redis_ssl}")
    print()
    
    # Intentar importar redis
    try:
        import redis.asyncio as redis
        print("✅ Librería redis importada correctamente")
    except ImportError as e:
        print(f"❌ Error importando redis: {e}")
        print("💡 Instala redis con: pip install redis>=4.6.0")
        return False
    
    # Construir la URL de conexión
    if redis_username and redis_password:
        auth_part = f"{redis_username}:{redis_password}@"
    elif redis_password:
        auth_part = f":{redis_password}@"
    else:
        auth_part = ""
        
    redis_url = f"redis{'s' if redis_ssl else ''}://{auth_part}{redis_host}:{redis_port}/0"
    print(f"🔗 URL de conexión: {redis_url.replace(redis_password, '*' * len(redis_password) if redis_password else '')}")
    print()
    
    # Intentar conexión
    client = None
    try:
        print("🔄 Intentando conectar...")
        
        # Configuración específica para SSL (necesaria para Redis Labs)
        connection_options = {
            "decode_responses": True,
            "health_check_interval": 30,
            "socket_connect_timeout": 10,
            "socket_timeout": 10
        }
        
        # Agregar SSL solo si está habilitado
        if redis_ssl:
            connection_options["ssl"] = True
            connection_options["ssl_check_hostname"] = False
            connection_options["ssl_cert_reqs"] = ssl_lib.CERT_NONE
        
        client = await redis.from_url(redis_url, **connection_options)
        
        # Probar ping
        print("📡 Enviando PING...")
        ping_result = await client.ping()
        print(f"✅ PING exitoso: {ping_result}")
        
        # Probar operaciones básicas
        print("\n🧪 Probando operaciones básicas...")
        
        # Test SET
        test_key = "test:connection:redis_labs"
        test_value = f"test_value_{int(time.time())}"
        
        print(f"   SET {test_key} = {test_value}")
        await client.set(test_key, test_value, ex=60)  # TTL de 60 segundos
        
        # Test GET
        print(f"   GET {test_key}")
        retrieved_value = await client.get(test_key)
        print(f"   Valor recuperado: {retrieved_value}")
        
        if retrieved_value == test_value:
            print("   ✅ Operación SET/GET exitosa")
        else:
            print(f"   ❌ Error: Valor esperado '{test_value}', obtenido '{retrieved_value}'")
        
        # Test TTL
        print(f"   TTL {test_key}")
        ttl = await client.ttl(test_key)
        print(f"   TTL restante: {ttl} segundos")
        
        # Test DELETE
        print(f"   DEL {test_key}")
        deleted_count = await client.delete(test_key)
        print(f"   Claves eliminadas: {deleted_count}")
        
        # Obtener información del servidor
        print("\n📊 Información del servidor Redis:")
        try:
            info = await client.info()
            print(f"   Versión Redis: {info.get('redis_version', 'N/A')}")
            print(f"   Memoria usada: {info.get('used_memory_human', 'N/A')}")
            print(f"   Uptime: {info.get('uptime_in_days', 'N/A')} días")
            print(f"   Clientes conectados: {info.get('connected_clients', 'N/A')}")
            print(f"   Total comandos procesados: {info.get('total_commands_processed', 'N/A')}")
            print(f"   Keyspace hits: {info.get('keyspace_hits', 'N/A')}")
            print(f"   Keyspace misses: {info.get('keyspace_misses', 'N/A')}")
        except Exception as e:
            print(f"   ⚠️ No se pudo obtener información del servidor: {e}")
        
        print("\n✅ Todas las pruebas de Redis Labs exitosas!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error conectando a Redis Labs: {e}")
        print(f"🔍 Tipo de error: {type(e).__name__}")
        
        # Diagnósticos adicionales
        print("\n🔧 Diagnósticos:")
        
        # Verificar si es un error de SSL
        if "ssl" in str(e).lower() or "tls" in str(e).lower():
            print("   📝 Posible problema de SSL/TLS:")
            print("      - Verifica que REDIS_SSL=true esté configurado")
            print("      - Redis Labs requiere conexión SSL")
            print("      - Verifica que el puerto sea el correcto para SSL")
        
        # Verificar si es un error de autenticación
        if "auth" in str(e).lower() or "password" in str(e).lower() or "username" in str(e).lower():
            print("   🔐 Posible problema de autenticación:")
            print("      - Verifica REDIS_USERNAME y REDIS_PASSWORD")
            print("      - Asegúrate de que las credenciales sean correctas")
        
        # Verificar si es un error de conectividad
        if "connection" in str(e).lower() or "timeout" in str(e).lower() or "refused" in str(e).lower():
            print("   🌐 Posible problema de conectividad:")
            print("      - Verifica REDIS_HOST y REDIS_PORT")
            print("      - Verifica que el firewall permita conexiones salientes")
            print("      - Verifica que Redis Labs esté funcionando")
        
        return False
        
    finally:
        # Cerrar conexión
        if client:
            try:
                await client.close()
                print("\n🔌 Conexión cerrada correctamente")
            except:
                pass

async def test_environment_variables():
    """Verifica que todas las variables de entorno estén configuradas."""
    
    print("\n🔍 Verificando variables de entorno...")
    print("=" * 60)
    
    required_vars = [
        "REDIS_HOST",
        "REDIS_PORT", 
        "REDIS_PASSWORD",
        "REDIS_USERNAME",
        "REDIS_SSL"
    ]
    
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            if var in ["REDIS_PASSWORD"]:
                print(f"✅ {var}: {'*' * len(value)}")
            else:
                print(f"✅ {var}: {value}")
        else:
            print(f"❌ {var}: No configurada")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n⚠️ Variables faltantes: {', '.join(missing_vars)}")
        print("💡 Verifica el archivo .env.secrets")
        return False
    else:
        print("\n✅ Todas las variables de Redis están configuradas")
        return True

def print_recommendations():
    """Imprime recomendaciones para solucionar problemas."""
    
    print("\n💡 Recomendaciones para solucionar problemas:")
    print("=" * 60)
    
    print("1. 🔧 Verificar credenciales de Redis Labs:")
    print("   - Accede a tu panel de Redis Labs")
    print("   - Verifica que el host, puerto, usuario y contraseña sean correctos")
    print("   - Asegúrate de que la instancia esté activa")
    
    print("\n2. 🔐 Configuración de SSL:")
    print("   - Redis Labs requiere SSL/TLS")
    print("   - Asegúrate de que REDIS_SSL=true")
    print("   - Usa el puerto SSL proporcionado por Redis Labs")
    
    print("\n3. 🌐 Configuración de red:")
    print("   - Verifica que tu IP esté en la lista blanca de Redis Labs")
    print("   - Verifica que no haya firewalls bloqueando la conexión")
    print("   - Prueba la conectividad desde otra ubicación")
    
    print("\n4. 📁 Configuración de variables:")
    print("   - Verifica que el archivo .env.secrets esté en el directorio correcto")
    print("   - Asegúrate de que no haya espacios extra en las variables")
    print("   - Verifica que no haya caracteres especiales mal codificados")

async def main():
    """Función principal."""
    
    print("🚀 Script de verificación de Redis Labs")
    print("=" * 60)
    
    # Verificar variables de entorno
    env_ok = await test_environment_variables()
    
    if not env_ok:
        print_recommendations()
        return
    
    # Probar conexión
    connection_ok = await test_redis_connection()
    
    if not connection_ok:
        print_recommendations()
    else:
        print("\n🎉 ¡Conexión a Redis Labs exitosa!")
        print("El sistema de caché debería funcionar correctamente.")

if __name__ == "__main__":
    # Ejecutar el script
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Script interrumpido por el usuario")
    except Exception as e:
        print(f"\n\n❌ Error ejecutando el script: {e}")
        import traceback
        traceback.print_exc()
