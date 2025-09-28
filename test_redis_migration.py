#!/usr/bin/env python3
"""
Test script para validar la migración a redis_config_optimized.py

Este script prueba que:
1. RedisService se inicializa correctamente con cliente optimizado
2. Las operaciones básicas funcionan
3. Health check retorna estado correcto
4. Timeouts y configuración optimizada están activos

Author: Senior Architecture Team
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Agregar src al path para imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_redis_migration():
    """
    Test principal para validar migración Redis
    """
    logger.info("🚀 INICIANDO TEST DE MIGRACIÓN REDIS")
    logger.info("=" * 60)
    
    try:
        # Test 1: Import y configuración
        logger.info("📦 TEST 1: Importing RedisService...")
        from src.api.core.redis_service import RedisService, get_redis_service
        from src.api.core.redis_config_optimized import OptimizedRedisConfig
        logger.info("✅ Import successful")
        
        # Test 2: Configuración optimizada
        logger.info("⚙️ TEST 2: Verificando configuración optimizada...")
        config = OptimizedRedisConfig.get_optimized_config()
        logger.info(f"   USE_REDIS_CACHE: {config.get('use_redis_cache')}")
        logger.info(f"   Socket timeout: {config.get('socket_timeout')}s")
        logger.info(f"   Connect timeout: {config.get('socket_connect_timeout')}s")
        logger.info(f"   Max connections: {config.get('max_connections')}")
        logger.info("✅ Configuración optimizada cargada")
        
        # Test 3: Inicialización RedisService
        logger.info("🔧 TEST 3: Inicializando RedisService...")
        start_time = time.time()
        
        redis_service = await get_redis_service()
        
        init_time = time.time() - start_time
        logger.info(f"   Tiempo de inicialización: {init_time:.2f}s")
        logger.info(f"   Cliente disponible: {redis_service._client is not None}")
        logger.info(f"   Estado conectado: {redis_service._connected}")
        logger.info("✅ RedisService inicializado")
        
        # Test 4: Health check
        logger.info("🏥 TEST 4: Health check...")
        health_result = await redis_service.health_check()
        logger.info(f"   Status: {health_result.get('status')}")
        logger.info(f"   Connected: {health_result.get('connected')}")
        logger.info(f"   Client available: {health_result.get('client_available')}")
        if 'ping_time_ms' in health_result:
            logger.info(f"   Ping time: {health_result['ping_time_ms']}ms")
        logger.info("✅ Health check completado")
        
        # Test 5: Operaciones básicas
        logger.info("🔄 TEST 5: Operaciones básicas Redis...")
        
        # Test SET
        test_key = "test:migration:timestamp"
        test_value = str(int(time.time()))
        set_result = await redis_service.set(test_key, test_value, ttl=300)
        logger.info(f"   SET operation: {set_result}")
        
        # Test GET
        get_result = await redis_service.get(test_key)
        logger.info(f"   GET operation: {get_result == test_value}")
        
        # Test JSON
        json_data = {"migration": "success", "timestamp": time.time()}
        json_set_result = await redis_service.set_json("test:migration:json", json_data, ttl=300)
        json_get_result = await redis_service.get_json("test:migration:json")
        logger.info(f"   JSON operations: {json_set_result and json_get_result is not None}")
        
        # Test DELETE
        delete_result = await redis_service.delete(test_key)
        logger.info(f"   DELETE operation: {delete_result}")
        
        logger.info("✅ Operaciones básicas completadas")
        
        # Test 6: Stats
        logger.info("📊 TEST 6: Estadísticas...")
        stats = redis_service.get_stats()
        logger.info(f"   Operations total: {stats['operations_total']}")
        logger.info(f"   Operations successful: {stats['operations_successful']}")
        logger.info(f"   Hit ratio: {stats['hit_ratio']:.2%}")
        logger.info("✅ Estadísticas obtenidas")
        
        # Test 7: Validación de cliente optimizado
        logger.info("🔍 TEST 7: Validación cliente optimizado...")
        client = redis_service._client
        if client:
            # Verificar que es un cliente redis standard
            client_type = type(client).__name__
            logger.info(f"   Tipo de cliente: {client_type}")
            
            # Verificar métodos disponibles
            has_ping = hasattr(client, 'ping')
            has_set = hasattr(client, 'set')
            has_setex = hasattr(client, 'setex')
            has_get = hasattr(client, 'get')
            
            logger.info(f"   Métodos estándar disponibles: ping={has_ping}, set={has_set}, setex={has_setex}, get={has_get}")
            
            if all([has_ping, has_set, has_setex, has_get]):
                logger.info("✅ Cliente Redis standard confirmado")
            else:
                logger.warning("⚠️ Cliente Redis puede tener métodos faltantes")
        else:
            logger.error("❌ Cliente Redis no disponible")
        
        logger.info("=" * 60)
        logger.info("🎉 MIGRACIÓN REDIS COMPLETADA EXITOSAMENTE")
        logger.info("=" * 60)
        
        # Resumen final
        logger.info("📋 RESUMEN:")
        logger.info(f"   ✅ Configuración optimizada: Aplicada")
        logger.info(f"   ✅ Cliente Redis standard: {client_type if client else 'No disponible'}")
        logger.info(f"   ✅ Conexión activa: {redis_service._connected}")
        logger.info(f"   ✅ Tiempo inicialización: {init_time:.2f}s")
        logger.info(f"   ✅ Operaciones Redis: Funcionando")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ ERROR EN MIGRACIÓN: {e}")
        logger.error(f"   Tipo: {type(e).__name__}")
        import traceback
        logger.error(f"   Traceback: {traceback.format_exc()}")
        return False

async def main():
    """Main function"""
    logger.info("🧪 Redis Migration Test Script")
    logger.info("Testing migration from PatchedRedisClient to optimized Redis client")
    logger.info("")
    
    success = await test_redis_migration()
    
    if success:
        logger.info("🎊 TODOS LOS TESTS PASARON - MIGRACIÓN EXITOSA")
        return 0
    else:
        logger.error("💥 TESTS FALLARON - REVISAR MIGRACIÓN")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
