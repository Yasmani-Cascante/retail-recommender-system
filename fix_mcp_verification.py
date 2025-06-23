# fix_mcp_verification.py
"""
Script para verificar que todas las correcciones MCP están funcionando correctamente.
Ejecutar después de aplicar las correcciones para validar el sistema.
"""

import asyncio
import os
import sys
import logging
from pathlib import Path

# Añadir el directorio raíz al PATH
root_dir = Path(__file__).resolve().parent
sys.path.append(str(root_dir))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_redis_connection():
    """Verificar conexión a Redis"""
    logger.info("🔍 Verificando conexión a Redis...")
    
    try:
        from src.api.core.cache import get_redis_client
        
        redis_client = get_redis_client()
        if not redis_client or not redis_client.client:
            logger.error("❌ Redis no configurado o no disponible")
            return False
        
        # Test básico de conectividad
        test_key = "mcp_test_connection"
        await redis_client.set(test_key, {"test": "success"}, expiration=60)
        result = await redis_client.get(test_key)
        await redis_client.delete(test_key)
        
        if result and result.get("test") == "success":
            logger.info("✅ Redis conectado y funcionando correctamente")
            return True
        else:
            logger.error("❌ Redis conectado pero falló el test de escritura/lectura")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error verificando Redis: {e}")
        return False

async def verify_market_manager():
    """Verificar MarketContextManager"""
    logger.info("🔍 Verificando MarketContextManager...")
    
    try:
        from src.api.mcp.adapters.market_manager import MarketContextManager
        
        manager = MarketContextManager()
        await manager.initialize()
        
        # Test obtener mercados soportados
        markets = await manager.get_supported_markets()
        
        if markets and "default" in markets:
            logger.info(f"✅ MarketContextManager funcionando - {len(markets)} mercados disponibles")
            return True
        else:
            logger.error("❌ MarketContextManager: no se pudieron obtener mercados")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error verificando MarketContextManager: {e}")
        return False

async def verify_market_cache():
    """Verificar MarketAwareProductCache"""
    logger.info("🔍 Verificando MarketAwareProductCache...")
    
    try:
        from src.cache.market_aware.market_cache import MarketAwareProductCache
        
        cache = MarketAwareProductCache()
        
        # Test básico de cache
        test_product = {
            "id": "test_123",
            "title": "Test Product",
            "price": 99.99
        }
        
        # Guardar en cache
        saved = await cache.set_product("test_123", test_product, "US")
        
        if saved:
            # Recuperar de cache
            retrieved = await cache.get_product("test_123", "US")
            
            if retrieved and retrieved.get("id") == "test_123":
                logger.info("✅ MarketAwareProductCache funcionando correctamente")
                # Limpiar test
                await cache.invalidate_product("test_123", "US")
                return True
            else:
                logger.error("❌ MarketAwareProductCache: error recuperando datos")
                return False
        else:
            logger.error("❌ MarketAwareProductCache: error guardando datos")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error verificando MarketAwareProductCache: {e}")
        return False

async def verify_mcp_recommender():
    """Verificar MCPAwareHybridRecommender"""
    logger.info("🔍 Verificando MCPAwareHybridRecommender...")
    
    try:
        from src.recommenders.mcp_aware_hybrid import MCPAwareHybridRecommender
        
        # Crear mock base recommender
        class MockBaseRecommender:
            async def get_recommendations(self, user_id, product_id=None, n_recommendations=5):
                return [
                    {"id": "prod_1", "title": "Test Product 1", "score": 0.9, "price": 29.99},
                    {"id": "prod_2", "title": "Test Product 2", "score": 0.8, "price": 39.99}
                ]
            
            async def record_user_event(self, user_id, event_type, product_id=None, **kwargs):
                return {"status": "success"}
        
        base_recommender = MockBaseRecommender()
        mcp_recommender = MCPAwareHybridRecommender(base_recommender)
        
        # Test request básico
        test_request = {
            "user_id": "test_user",
            "market_id": "US",
            "n_recommendations": 3,
            "include_conversation_response": False
        }
        
        response = await mcp_recommender.get_recommendations(test_request)
        
        if response and "recommendations" in response and len(response["recommendations"]) > 0:
            logger.info("✅ MCPAwareHybridRecommender funcionando correctamente")
            return True
        else:
            logger.error("❌ MCPAwareHybridRecommender: respuesta inválida")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error verificando MCPAwareHybridRecommender: {e}")
        return False

async def verify_environment_config():
    """Verificar configuración de entorno"""
    logger.info("🔍 Verificando configuración de entorno...")
    
    required_vars = [
        "REDIS_HOST",
        "REDIS_PORT", 
        "USE_REDIS_CACHE",
        "MCP_ENABLED"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"❌ Variables de entorno faltantes: {missing_vars}")
        return False
    else:
        logger.info("✅ Configuración de entorno correcta")
        return True

async def verify_imports():
    """Verificar que todos los imports funcionan"""
    logger.info("🔍 Verificando imports...")
    
    import_tests = [
        ("src.api.core.cache", "get_redis_client"),
        ("src.api.mcp.adapters.market_manager", "MarketContextManager"),
        ("src.cache.market_aware.market_cache", "MarketAwareProductCache"),
        ("src.recommenders.mcp_aware_hybrid", "MCPAwareHybridRecommender"),
        ("src.api.mcp.models.mcp_models", "ConversationContext")
    ]
    
    failed_imports = []
    
    for module_name, class_name in import_tests:
        try:
            module = __import__(module_name, fromlist=[class_name])
            getattr(module, class_name)
            logger.info(f"  ✅ {module_name}.{class_name}")
        except Exception as e:
            failed_imports.append((module_name, class_name, str(e)))
            logger.error(f"  ❌ {module_name}.{class_name}: {e}")
    
    if failed_imports:
        logger.error(f"❌ {len(failed_imports)} imports fallaron")
        return False
    else:
        logger.info("✅ Todos los imports funcionan correctamente")
        return True

async def main():
    """Ejecutar todas las verificaciones"""
    logger.info("🚀 Iniciando verificación de correcciones MCP...")
    
    tests = [
        ("Configuración de entorno", verify_environment_config),
        ("Imports de módulos", verify_imports),
        ("Conexión Redis", verify_redis_connection),
        ("MarketContextManager", verify_market_manager),
        ("MarketAwareProductCache", verify_market_cache),
        ("MCPAwareHybridRecommender", verify_mcp_recommender)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info(f"\n📋 Ejecutando: {test_name}")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"❌ Error en {test_name}: {e}")
            results.append((test_name, False))
    
    # Resumen de resultados
    logger.info("\n" + "="*50)
    logger.info("📊 RESUMEN DE VERIFICACIONES")
    logger.info("="*50)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status} {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info(f"\n📈 Total: {passed} pasaron, {failed} fallaron")
    
    if failed == 0:
        logger.info("🎉 ¡Todas las correcciones verificadas exitosamente!")
        logger.info("🚀 El sistema está listo para ejecutar MCP Fase 2")
        return True
    else:
        logger.error("⚠️ Algunas verificaciones fallaron - revisar errores arriba")
        return False

if __name__ == "__main__":
    # Cargar variables de entorno
    from dotenv import load_dotenv
    load_dotenv()
    
    success = asyncio.run(main())
    
    if success:
        print("\n🎯 PRÓXIMOS PASOS:")
        print("1. Ejecutar el sistema: python src/api/run.py")
        print("2. Verificar health check: http://localhost:8000/health")
        print("3. Probar endpoints MCP: http://localhost:8000/docs")
        sys.exit(0)
    else:
        print("\n⚠️ CORRECCIONES REQUERIDAS:")
        print("1. Revisar los errores mostrados arriba")
        print("2. Aplicar las correcciones necesarias")
        print("3. Re-ejecutar este script")
        sys.exit(1)
