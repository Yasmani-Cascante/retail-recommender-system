#!/usr/bin/env python3
"""
Redis Timeout Diagnostic Tool
============================

Herramienta para diagnosticar específicamente el problema de timeout Redis
y determinar las optimizaciones necesarias.

Author: Senior Architecture Team
"""

import sys
import asyncio
import time
import logging
sys.path.append('src')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def diagnose_redis_timeout():
    """Diagnóstico específico del timeout Redis"""
    
    print("🔍 DIAGNÓSTICO REDIS TIMEOUT - ANÁLISIS DETALLADO")
    print("=" * 60)
    
    # Test 1: Configuración y variables de entorno
    print("\n📋 TEST 1: Verificando configuración...")
    try:
        from src.api.core.config import get_settings
        settings = get_settings()
        
        print(f"✅ USE_REDIS_CACHE: {settings.use_redis_cache}")
        print(f"✅ REDIS_HOST: {settings.redis_host}")
        print(f"✅ REDIS_PORT: {settings.redis_port}")
        print(f"✅ REDIS_SSL: {settings.redis_ssl}")
        print(f"✅ Configuration loaded successfully")
        
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return
    
    # Test 2: Conexión directa con timing
    print("\n🔌 TEST 2: Conexión directa Redis...")
    try:
        from src.api.core.redis_config_fix import PatchedRedisClient
        
        connection_start = time.time()
        redis_client = PatchedRedisClient()
        
        print(f"⏱️ Client creation: {(time.time() - connection_start) * 1000:.1f}ms")
        
        # Test conexión
        connect_start = time.time()
        await redis_client.connect()
        connect_time = (time.time() - connect_start) * 1000
        print(f"⏱️ Connection time: {connect_time:.1f}ms")
        
        if connect_time > 5000:
            print(f"🔴 CONNECTION TIMEOUT DETECTED: {connect_time:.1f}ms > 5000ms")
        elif connect_time > 2000:
            print(f"🟡 CONNECTION SLOW: {connect_time:.1f}ms > 2000ms")
        else:
            print(f"🟢 CONNECTION GOOD: {connect_time:.1f}ms < 2000ms")
        
        # Test operaciones básicas
        if redis_client.connected:
            operation_start = time.time()
            ping_result = await redis_client.ping()
            operation_time = (time.time() - operation_start) * 1000
            
            print(f"⏱️ Ping operation: {operation_time:.1f}ms")
            print(f"✅ Ping result: {ping_result}")
            
            # Test set/get
            test_start = time.time()
            await redis_client.set("test_key", "test_value", ex=60)
            value = await redis_client.get("test_key")
            test_time = (time.time() - test_start) * 1000
            
            print(f"⏱️ Set/Get operation: {test_time:.1f}ms")
            print(f"✅ Test value: {value}")
            
            # Cleanup
            await redis_client.delete("test_key")
            
        else:
            print("❌ Redis not connected - cannot test operations")
            
    except asyncio.TimeoutError:
        print("❌ Connection timeout occurred")
    except Exception as e:
        print(f"❌ Redis connection error: {e}")
        return
    
    # Test 3: ServiceFactory con timing detallado
    print("\n🏭 TEST 3: ServiceFactory con timing detallado...")
    try:
        from src.api.factories import ServiceFactory
        
        factory_start = time.time()
        redis_service = await asyncio.wait_for(
            ServiceFactory.get_redis_service(),
            timeout=10.0  # Timeout extendido para diagnóstico
        )
        factory_time = (time.time() - factory_start) * 1000
        
        print(f"⏱️ ServiceFactory time: {factory_time:.1f}ms")
        
        if factory_time > 5000:
            print(f"🔴 SERVICEFACTORY TIMEOUT: {factory_time:.1f}ms > 5000ms")
        else:
            print(f"🟢 ServiceFactory good: {factory_time:.1f}ms < 5000ms")
        
        # Test health check
        health_start = time.time()
        health = await redis_service.health_check()
        health_time = (time.time() - health_start) * 1000
        
        print(f"⏱️ Health check time: {health_time:.1f}ms")
        print(f"📊 Health status: {health.get('status', 'unknown')}")
        
    except asyncio.TimeoutError:
        print("❌ ServiceFactory timeout occurred")
    except Exception as e:
        print(f"❌ ServiceFactory error: {e}")
    
    # Test 4: Network connectivity test
    print("\n🌐 TEST 4: Network connectivity test...")
    try:
        import socket
        
        # Test DNS resolution
        dns_start = time.time()
        host_ip = socket.gethostbyname(settings.redis_host)
        dns_time = (time.time() - dns_start) * 1000
        
        print(f"⏱️ DNS resolution: {dns_time:.1f}ms")
        print(f"📍 Host IP: {host_ip}")
        
        # Test TCP connection
        tcp_start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        result = sock.connect_ex((host_ip, settings.redis_port))
        tcp_time = (time.time() - tcp_start) * 1000
        sock.close()
        
        print(f"⏱️ TCP connection: {tcp_time:.1f}ms")
        
        if result == 0:
            print(f"✅ TCP connection successful")
        else:
            print(f"❌ TCP connection failed: {result}")
            
        if tcp_time > 2000:
            print(f"🔴 NETWORK LATENCY HIGH: {tcp_time:.1f}ms")
        else:
            print(f"🟢 Network latency good: {tcp_time:.1f}ms")
            
    except Exception as e:
        print(f"❌ Network test error: {e}")
    
    # Análisis y recomendaciones
    print("\n📊 ANÁLISIS Y RECOMENDACIONES")
    print("=" * 60)
    
    print("\n🎯 POSIBLES CAUSAS DEL TIMEOUT:")
    print("1. Network latency alta (>2s)")
    print("2. Redis server sobrecargado")
    print("3. Timeout muy restrictivo en ServiceFactory")
    print("4. DNS resolution lenta")
    print("5. Configuración SSL/TLS issues")
    
    print("\n🔧 RECOMENDACIONES INMEDIATAS:")
    print("1. Aumentar timeout en ServiceFactory de 5s a 15s")
    print("2. Implementar connection pooling optimizado")
    print("3. Configurar Redis connection keepalive")
    print("4. Añadir retry logic con backoff")
    print("5. Considerar Redis local para desarrollo")
    
    print("\n✅ DIAGNÓSTICO COMPLETADO")

if __name__ == "__main__":
    asyncio.run(diagnose_redis_timeout())
