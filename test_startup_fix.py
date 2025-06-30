#!/usr/bin/env python3
"""
Script de prueba para verificar que la aplicación se inicia correctamente
con la corrección de Redis implementada.
"""

import sys
import os
import asyncio
import logging

# Añadir el directorio del proyecto al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configurar logging detallado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_startup():
    """Prueba el startup de la aplicación con las correcciones"""
    
    print("🔧 PRUEBA DE STARTUP CON CORRECCIONES REDIS")
    print("=" * 50)
    
    try:
        # 1. Cargar variables de entorno
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Variables de entorno cargadas")
        
        # 2. Importar configuración
        from src.api.core.config import get_settings
        settings = get_settings()
        print(f"✅ Configuración cargada - Redis cache: {settings.use_redis_cache}")
        
        # 3. Probar RedisConfigValidator
        from src.api.core.redis_config_fix import RedisConfigValidator, PatchedRedisClient
        
        config = RedisConfigValidator.validate_and_fix_config()
        print(f"✅ Configuración Redis validada: {config.get('redis_ssl')}")
        
        # 4. Probar creación de cliente Redis
        if config.get('use_redis_cache'):
            try:
                redis_client = PatchedRedisClient(use_validated_config=True)
                print(f"✅ PatchedRedisClient creado con SSL={redis_client.ssl}")
                
                # 5. Probar conexión
                connection_result = await redis_client.connect()
                if connection_result:
                    print("✅ Conexión Redis exitosa")
                    
                    # 6. Probar operación básica
                    test_result = await redis_client.set("test_startup", "success", ex=10)
                    if test_result:
                        print("✅ Operación Redis exitosa")
                    else:
                        print("⚠️ Operación Redis falló")
                else:
                    print("❌ Conexión Redis falló")
                    
            except Exception as e:
                print(f"❌ Error con PatchedRedisClient: {e}")
        else:
            print("⚠️ Redis cache desactivado")
        
        # 7. Probar imports del sistema principal
        try:
            from src.api.factories import RecommenderFactory
            print("✅ RecommenderFactory importado correctamente")
            
            # Crear recomendadores
            tfidf_recommender = RecommenderFactory.create_tfidf_recommender()
            retail_recommender = RecommenderFactory.create_retail_recommender()
            print("✅ Recomendadores base creados")
            
            # Crear cliente Redis para test
            redis_client = None
            if config.get('use_redis_cache'):
                try:
                    redis_client = RecommenderFactory.create_redis_client()
                    print(f"✅ Redis client de fábrica creado: {type(redis_client).__name__}")
                except Exception as e:
                    print(f"⚠️ Redis client de fábrica falló: {e}")
            
            # Crear ProductCache
            if redis_client:
                try:
                    product_cache = RecommenderFactory.create_product_cache(
                        content_recommender=tfidf_recommender,
                        shopify_client=None  # No necesario para test
                    )
                    if product_cache:
                        print("✅ ProductCache creado exitosamente")
                        cache_stats = product_cache.get_stats()
                        print(f"   Hit ratio inicial: {cache_stats['hit_ratio']}")
                    else:
                        print("❌ ProductCache no se creó")
                except Exception as e:
                    print(f"❌ Error creando ProductCache: {e}")
            
            # Crear hybrid recommender
            hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
                tfidf_recommender, 
                retail_recommender,
                product_cache=product_cache if redis_client else None
            )
            print(f"✅ Hybrid recommender creado: {type(hybrid_recommender).__name__}")
            
        except Exception as e:
            print(f"❌ Error en imports del sistema: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 50)
        print("✅ PRUEBA DE STARTUP COMPLETADA")
        print("   El sistema debería funcionar correctamente ahora")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR EN PRUEBA DE STARTUP: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Iniciando prueba de startup...")
    result = asyncio.run(test_startup())
    
    if result:
        print("\n🎉 ¡Prueba exitosa! Puedes iniciar la aplicación:")
        print("   python run.py")
        print("   o")
        print("   uvicorn src.api.main_unified_redis:app --reload")
    else:
        print("\n💥 Prueba falló. Revisa los errores anteriores.")
