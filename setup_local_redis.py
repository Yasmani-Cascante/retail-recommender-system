#!/usr/bin/env python3
"""
Redis Local Development Setup
============================

Configuración para usar Redis local en desarrollo y eliminar timeouts de red.

Author: Senior Architecture Team
"""

def create_local_redis_config():
    """Crea configuración para Redis local"""
    
    print("🏠 CONFIGURACIÓN REDIS LOCAL PARA DESARROLLO")
    print("=" * 50)
    
    # Configuración .env para Redis local
    local_env_config = '''
# ===== REDIS LOCAL DEVELOPMENT CONFIGURATION =====
# Para usar Redis local en lugar de Redis Cloud

# Enable Redis caching
USE_REDIS_CACHE=true

# Local Redis configuration (elimina timeouts de red)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_SSL=false
REDIS_USERNAME=

# Cache configuration
CACHE_TTL=3600
CACHE_PREFIX=dev_product:
CACHE_ENABLE_BACKGROUND_TASKS=true

# Development timeouts (más permisivos)
REDIS_SOCKET_CONNECT_TIMEOUT=30.0
REDIS_SOCKET_TIMEOUT=30.0
REDIS_MAX_CONNECTIONS=10

# ===== REDIS CLOUD PRODUCTION CONFIGURATION =====
# Para usar Redis Cloud en production (comentar para dev local)

# USE_REDIS_CACHE=true
# REDIS_HOST=redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com
# REDIS_PORT=14272
# REDIS_SSL=false
# REDIS_USERNAME=default
# REDIS_PASSWORD=your_password_here
'''
    
    # Guardar configuración
    with open('.env.local_redis', 'w') as f:
        f.write(local_env_config)
    
    print("✅ Configuración local creada: .env.local_redis")
    
    # Instrucciones de instalación Redis local
    redis_install_instructions = '''
# INSTALACIÓN REDIS LOCAL
# =======================

## Windows (usando Chocolatey):
choco install redis-64

## Windows (usando WSL2):
# En WSL2 terminal:
sudo apt update
sudo apt install redis-server
sudo service redis-server start

## Windows (Docker):
docker run -d -p 6379:6379 --name redis-dev redis:alpine

## macOS:
brew install redis
brew services start redis

## Linux (Ubuntu/Debian):
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server

# VERIFICAR INSTALACIÓN:
redis-cli ping
# Expected output: PONG

# CONFIGURAR PARA DESARROLLO:
# 1. Copiar .env.local_redis a .env
# 2. Reiniciar aplicación
# 3. Ejecutar tests
'''
    
    with open('REDIS_LOCAL_INSTALL.md', 'w') as f:
        f.write(redis_install_instructions)
    
    print("📋 Instrucciones de instalación creadas: REDIS_LOCAL_INSTALL.md")
    
    # Script de test para Redis local
    redis_test_script = '''#!/usr/bin/env python3
"""Test Redis Local Connection"""

import asyncio
import sys
sys.path.append('src')

async def test_local_redis():
    """Test conexión Redis local"""
    
    print("🧪 TESTING REDIS LOCAL CONNECTION")
    print("=" * 40)
    
    try:
        from src.api.core.redis_config_fix import PatchedRedisClient
        
        # Configuración local
        redis_client = PatchedRedisClient(
            host='localhost',
            port=6379,
            password=None,
            ssl=False
        )
        
        print("🔌 Connecting to localhost:6379...")
        await redis_client.connect()
        
        if redis_client.connected:
            print("✅ Connection successful!")
            
            # Test básico
            await redis_client.set("test_local", "hello_world", ex=60)
            value = await redis_client.get("test_local")
            print(f"📝 Test value: {value}")
            
            # Ping test
            ping = await redis_client.ping()
            print(f"🏓 Ping result: {ping}")
            
            # Cleanup
            await redis_client.delete("test_local")
            print("🧹 Cleanup completed")
            
        else:
            print("❌ Connection failed")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure Redis is running locally:")
        print("   - Windows: redis-server.exe")
        print("   - Linux/Mac: redis-server")
        print("   - Docker: docker run -p 6379:6379 redis:alpine")

if __name__ == "__main__":
    asyncio.run(test_local_redis())
'''
    
    with open('test_local_redis.py', 'w') as f:
        f.write(redis_test_script)
    
    print("🧪 Script de test creado: test_local_redis.py")
    
    print("\n🎯 PRÓXIMOS PASOS PARA REDIS LOCAL:")
    print("1. Instalar Redis local (ver REDIS_LOCAL_INSTALL.md)")
    print("2. Copiar .env.local_redis a .env (o actualizar .env existente)")
    print("3. Ejecutar: python test_local_redis.py")
    print("4. Si test pasa, ejecutar tests principales de nuevo")

if __name__ == "__main__":
    create_local_redis_config()
