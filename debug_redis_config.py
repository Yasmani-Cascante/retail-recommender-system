#!/usr/bin/env python3
"""
Debug Redis Configuration
=========================

Script para debuggear por qué Redis cache aparece como desactivado.
"""

import os
import sys
sys.path.append('src')

# Cargar variables de entorno
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv no disponible, continuar

def debug_redis_config():
    print("🔍 DEBUGGING REDIS CONFIGURATION...")
    print("=" * 50)
    
    # Test 1: Variables de entorno raw
    print("\n1️⃣ Raw Environment Variables:")
    redis_vars = [
        'USE_REDIS_CACHE',
        'REDIS_HOST', 
        'REDIS_PORT',
        'REDIS_PASSWORD',
        'REDIS_USERNAME',
        'REDIS_DB',
        'REDIS_SSL'
    ]
    
    for var in redis_vars:
        value = os.getenv(var, 'NOT_SET')
        print(f"   {var}: '{value}' (type: {type(value).__name__})")
    
    # Test 2: Parsing logic
    print("\n2️⃣ Testing Parsing Logic:")
    use_cache_raw = os.getenv('USE_REDIS_CACHE', 'false')
    use_cache_lower = use_cache_raw.lower()
    use_cache_parsed = use_cache_lower in ['true', '1', 'yes', 'on']
    
    print(f"   Raw value: '{use_cache_raw}'")
    print(f"   Lowercased: '{use_cache_lower}'")
    print(f"   Parsed result: {use_cache_parsed}")
    print(f"   Expected: True")
    
    # Test 3: Redis config optimized
    print("\n3️⃣ Testing Redis Config Optimized:")
    try:
        from src.api.core.redis_config_optimized import OptimizedRedisConfig
        config = OptimizedRedisConfig.get_optimized_config()
        
        print(f"   Config returned: {len(config)} keys")
        print(f"   use_redis_cache in config: {'use_redis_cache' in config}")
        if 'use_redis_cache' in config:
            print(f"   use_redis_cache value: {config['use_redis_cache']}")
        
        if config.get('use_redis_cache', False):
            print("   ✅ Redis should be enabled")
        else:
            print("   ❌ Redis is disabled - PROBLEM HERE")
            
    except Exception as e:
        print(f"   ❌ Error importing/executing config: {e}")
    
    # Test 4: Environment file
    print("\n4️⃣ Checking .env File:")
    try:
        with open('.env', 'r') as f:
            lines = f.readlines()
        
        redis_lines = [line.strip() for line in lines if 'REDIS' in line or 'USE_REDIS' in line]
        for line in redis_lines[:5]:  # Solo primeras 5 para no mostrar passwords
            if 'PASSWORD' not in line:
                print(f"   {line}")
    except Exception as e:
        print(f"   ⚠️ Could not read .env: {e}")
    
    # Test 5: Direct Redis connection test
    print("\n5️⃣ Direct Redis Connection Test:")
    try:
        import redis.asyncio as redis
        import asyncio
        
        async def test_direct_connection():
            try:
                client = redis.Redis(
                    host=os.getenv('REDIS_HOST', 'localhost'),
                    port=int(os.getenv('REDIS_PORT', '6379')),
                    password=os.getenv('REDIS_PASSWORD'),
                    username=os.getenv('REDIS_USERNAME', 'default'),
                    db=int(os.getenv('REDIS_DB', '0')),
                    socket_timeout=2.0,
                    socket_connect_timeout=1.5,
                    decode_responses=True
                )
                
                await client.ping()
                print("   ✅ Direct Redis connection successful")
                await client.close()
                return True
            except Exception as e:
                print(f"   ❌ Direct Redis connection failed: {e}")
                return False
        
        result = asyncio.run(test_direct_connection())
        
    except Exception as e:
        print(f"   ❌ Could not test direct connection: {e}")

if __name__ == "__main__":
    debug_redis_config()
