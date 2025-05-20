
#!/usr/bin/env python
"""
Script de verificación para el Sistema de Caché Híbrido con Redis.

Este script realiza una serie de verificaciones para comprobar 
que todos los componentes del sistema de caché están correctamente
implementados y configurados.
"""

import os
import sys
import asyncio
import logging
import json
from typing import Dict, Any, List
import time

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def check_redis_connection():
    """Verifica la conexión a Redis."""
    logger.info("⏳ Verificando conexión a Redis...")
    
    try:
        from src.api.core.redis_client import RedisClient
        
        # Obtener configuración
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD", "")
        db = int(os.getenv("REDIS_DB", "0"))
        ssl = os.getenv("REDIS_SSL", "False").lower() == "true"
        
        logger.info(f"📝 Configuración Redis: {host}:{port}, DB={db}, SSL={ssl}")
        
        # Crear cliente
        client = RedisClient(
            host=host,
            port=port,
            db=db,
            password=password,
            ssl=ssl
        )
        
        # Intentar conectar
        connected = await client.connect()
        
        if connected:
            logger.info("✅ Conexión a Redis establecida correctamente")
            
            # Realizar prueba simple
            test_key = "test:verification"
            test_value = f"cache_verification_{int(time.time())}"
            
            # Guardar en caché
            await client.set(test_key, test_value, ex=60)
            
            # Leer de caché
            retrieved = await client.get(test_key)
            
            if retrieved == test_value:
                logger.info("✅ Operaciones básicas (set/get) funcionan correctamente")
            else:
                logger.error(f"❌ Error en operaciones básicas. Esperado: '{test_value}', Obtenido: '{retrieved}'")
                return False
                
            # Limpiar
            await client.delete(test_key)
            
            # Obtener información de salud
            health = await client.health_check()
            logger.info(f"📊 Información de salud: {json.dumps(health, indent=2)}")
            
            return True
        else:
            logger.error("❌ No se pudo conectar a Redis")
            return False
            
    except ImportError:
        logger.error("❌ No se pudo importar RedisClient. Verifica que redis-py esté instalado")
        return False
    except Exception as e:
        logger.error(f"❌ Error verificando conexión a Redis: {str(e)}")
        logger.exception(e)
        return False

async def check_product_cache():
    """Verifica la implementación de ProductCache."""
    logger.info("⏳ Verificando implementación de ProductCache...")
    
    try:
        from src.api.core.product_cache import ProductCache
        from src.api.core.redis_client import RedisClient
        
        # Crear redis_client mínimo para pruebas
        redis_client = RedisClient(host="localhost")
        
        # Crear ProductCache mínimo
        cache = ProductCache(
            redis_client=redis_client,
            ttl_seconds=3600,
            prefix="test:"
        )
        
        # Verificar métodos requeridos
        required_methods = [
            "get_product", 
            "preload_products", 
            "invalidate", 
            "get_stats",
            "_calculate_hit_ratio",
            "_save_to_redis",
            "start_background_tasks"
        ]
        
        for method in required_methods:
            if not hasattr(cache, method):
                logger.error(f"❌ ProductCache no tiene el método requerido: {method}")
                return False
        
        logger.info("✅ ProductCache tiene todos los métodos requeridos")
        
        # Verificar estadísticas iniciales
        stats = cache.get_stats()
        if not isinstance(stats, dict) or "hit_ratio" not in stats:
            logger.error(f"❌ get_stats() no devuelve un diccionario con 'hit_ratio'")
            return False
            
        logger.info("✅ Método get_stats() funciona correctamente")
        logger.info(f"📊 Estadísticas iniciales: {json.dumps(stats, indent=2)}")
        
        return True
        
    except ImportError:
        logger.error("❌ No se pudo importar ProductCache")
        return False
    except Exception as e:
        logger.error(f"❌ Error verificando ProductCache: {str(e)}")
        logger.exception(e)
        return False

async def check_hybrid_recommender():
    """Verifica la integración con HybridRecommender."""
    logger.info("⏳ Verificando integración con HybridRecommender...")
    
    try:
        # Importar y verificar si acepta product_cache
        from src.recommenders.hybrid import HybridRecommender
        
        # Verificar si el constructor acepta product_cache
        import inspect
        params = inspect.signature(HybridRecommender.__init__).parameters
        
        if "product_cache" not in params:
            logger.error("❌ HybridRecommender.__init__ no acepta el parámetro product_cache")
            logger.error(f"📝 Parámetros actuales: {list(params.keys())}")
            return False
            
        logger.info("✅ HybridRecommender acepta el parámetro product_cache")
        
        # Verificar si tiene método de enriquecimiento
        if not hasattr(HybridRecommender, "_enrich_recommendations"):
            logger.error("❌ HybridRecommender no tiene el método _enrich_recommendations")
            return False
            
        logger.info("✅ HybridRecommender tiene el método _enrich_recommendations")
        
        return True
        
    except ImportError:
        logger.error("❌ No se pudo importar HybridRecommender")
        return False
    except Exception as e:
        logger.error(f"❌ Error verificando HybridRecommender: {str(e)}")
        logger.exception(e)
        return False

async def check_factory_methods():
    """Verifica los métodos de fábrica."""
    logger.info("⏳ Verificando métodos de fábrica...")
    
    try:
        from src.api.factories import RecommenderFactory
        
        # Verificar métodos requeridos
        required_methods = [
            "create_redis_client",
            "create_product_cache"
        ]
        
        for method in required_methods:
            if not hasattr(RecommenderFactory, method):
                logger.error(f"❌ RecommenderFactory no tiene el método requerido: {method}")
                return False
        
        logger.info("✅ RecommenderFactory tiene todos los métodos requeridos")
        
        return True
    
    except ImportError:
        logger.error("❌ No se pudo importar RecommenderFactory")
        return False
    except Exception as e:
        logger.error(f"❌ Error verificando métodos de fábrica: {str(e)}")
        logger.exception(e)
        return False

async def check_requirements():
    """Verifica que las dependencias necesarias estén instaladas."""
    logger.info("⏳ Verificando dependencias...")
    
    required_packages = ["redis", "aioredis"]
    
    for package in required_packages:
        try:
            __import__(package)
            logger.info(f"✅ Dependencia '{package}' está instalada")
        except ImportError:
            logger.error(f"❌ Dependencia '{package}' NO está instalada")
            return False
    
    return True

async def check_env_file():
    """Verifica que las variables de entorno de Redis estén en el archivo .env."""
    logger.info("⏳ Verificando archivo .env...")
    
    env_file = ".env"
    if not os.path.exists(env_file):
        logger.warning(f"⚠️ No se encontró el archivo {env_file}")
        return False
    
    required_vars = [
        "REDIS_HOST",
        "REDIS_PORT",
        "USE_REDIS_CACHE",
        "CACHE_TTL"
    ]
    
    with open(env_file, "r") as f:
        content = f.read()
    
    missing_vars = []
    for var in required_vars:
        if var not in content:
            missing_vars.append(var)
    
    if missing_vars:
        logger.warning(f"⚠️ Variables faltantes en {env_file}: {', '.join(missing_vars)}")
        return False
    
    logger.info(f"✅ Archivo {env_file} contiene las variables necesarias para Redis")
    return True

async def check_health_endpoint():
    """Verifica que el endpoint de health incluye información de caché."""
    logger.info("⏳ Verificando endpoint de health...")
    
    try:
        # Verificar si el archivo main incluye caché en el estado de salud
        with open("src/api/main_tfidf_shopify_with_metrics.py", "r") as f:
            content = f.read()
        
        if "cache_status" not in content or "cache" not in content:
            logger.warning("⚠️ El endpoint de health puede que no incluya información de caché")
            return False
        
        # Si encontramos alguna referencia a caché en el endpoint de health
        if '"cache"' in content and "components" in content:
            logger.info("✅ El endpoint de health parece incluir información de caché")
            return True
            
        logger.warning("⚠️ No se encontró confirmación clara de que el endpoint de health incluya información de caché")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error verificando endpoint de health: {str(e)}")
        return False

async def main():
    """Función principal."""
    logger.info("🚀 Iniciando verificación del Sistema de Caché Híbrido con Redis")
    
    results = {}
    
    # Verificar dependencias
    results["requirements"] = await check_requirements()
    
    # Verificar archivo .env
    results["env_file"] = await check_env_file()
    
    # Verificar RedisClient
    results["redis_connection"] = await check_redis_connection()
    
    # Verificar ProductCache
    results["product_cache"] = await check_product_cache()
    
    # Verificar integración con HybridRecommender
    results["hybrid_recommender"] = await check_hybrid_recommender()
    
    # Verificar métodos de fábrica
    results["factory_methods"] = await check_factory_methods()
    
    # Verificar endpoint de health
    results["health_endpoint"] = await check_health_endpoint()
    
    # Mostrar resumen
    logger.info("📋 Resumen de verificación:")
    
    all_ok = True
    for name, result in results.items():
        status = "✅ OK" if result else "❌ ERROR"
        logger.info(f"  {status} - {name}")
        if not result:
            all_ok = False
    
    if all_ok:
        logger.info("🎉 Verificación completa: El Sistema de Caché Híbrido con Redis está correctamente implementado")
        return 0
    else:
        logger.error("⚠️ Verificación completa: Se encontraron problemas en el Sistema de Caché Híbrido con Redis")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("❌ Verificación interrumpida")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Error durante la verificación: {str(e)}")
        logger.exception(e)
        sys.exit(1)
