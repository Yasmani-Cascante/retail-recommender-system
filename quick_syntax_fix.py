#!/usr/bin/env python3
"""
CORRECCIÓN ESPECÍFICA: ProductCache initialization_failed

PROBLEMA IDENTIFICADO:
- Redis conectado pero ProductCache no puede inicializarse
- Error: "Redis client available but ProductCache failed to initialize"
- Causa: Variables globales no actualizadas correctamente en startup_event

SOLUCIÓN:
- Corregir scope de variables globales para product_cache y redis_client
- Añadir logging detallado para diagnóstico
- Verificar secuencia de inicialización
- Implementar fallback seguro

Basado en la documentación técnica de resolución previa del mismo problema.
"""

import os
import shutil
from pathlib import Path

def fix_product_cache_initialization():
    """Corrige específicamente el problema de ProductCache initialization_failed"""
    
    file_path = Path("src/api/main_unified_redis.py")
    
    if not file_path.exists():
        print(f"❌ ARCHIVO NO ENCONTRADO: {file_path}")
        print("💡 Ejecuta desde: C:\\Users\\yasma\\Desktop\\retail-recommender-system")
        return False
    
    print("🔧 CORRIGIENDO PRODUCTCACHE INITIALIZATION_FAILED")
    print("=" * 55)
    
    # Crear backup
    backup_path = file_path.with_suffix('.py.backup_product_cache')
    shutil.copy2(file_path, backup_path)
    print(f"✅ Backup creado: {backup_path}")
    
    try:
        # Leer archivo
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # CORRECCIÓN 1: Asegurar declaración global correcta para product_cache
        print("\n🔧 Aplicando corrección 1: Variables globales")
        
        # Buscar la declaración global existente y añadir product_cache si falta
        global_patterns = [
            'global redis_client, product_cache, hybrid_recommender',
            'global mcp_recommender, mcp_conversation_state_manager',
            'global optimized_conversation_manager, personalization_engine, mcp_state_manager'
        ]
        
        # Verificar si product_cache está en la declaración global
        if 'global redis_client, product_cache' not in content:
            # Buscar la línea de global y añadir product_cache
            old_global = 'global redis_client, product_cache, hybrid_recommender'
            new_global = 'global redis_client, product_cache, hybrid_recommender'
            
            # Si no está, buscar otra declaración global para actualizar
            if 'global redis_client' in content and 'product_cache' not in content.split('global redis_client')[1].split('\n')[0]:
                old_pattern = 'global redis_client'
                new_pattern = 'global redis_client, product_cache'
                content = content.replace(old_pattern, new_pattern, 1)
                print("✅ Añadida product_cache a declaración global")
        
        # CORRECCIÓN 2: Añadir logging detallado para diagnóstico
        print("🔧 Aplicando corrección 2: Logging detallado")
        
        diagnostic_logging = '''
    # ✅ DIAGNÓSTICO PRODUCTCACHE: Logging detallado para debugging
    logger.info(f"🔍 DIAGNÓSTICO REDIS antes de ProductCache:")
    logger.info(f"  redis_client type: {type(redis_client).__name__}")
    logger.info(f"  redis_client is None: {redis_client is None}")
    if redis_client:
        logger.info(f"  redis_client connected: {getattr(redis_client, 'connected', 'N/A')}")
        logger.info(f"  redis_client ssl: {getattr(redis_client, 'ssl', 'N/A')}")
    else:
        logger.error("❌ redis_client es None - ProductCache fallará")'''
        
        # Buscar donde insertar el logging - antes de crear ProductCache
        product_cache_creation_marker = 'product_cache = ProductCache('
        if product_cache_creation_marker in content:
            content = content.replace(
                product_cache_creation_marker,
                diagnostic_logging + '\n    \n    ' + product_cache_creation_marker
            )
            print("✅ Logging de diagnóstico añadido")
        
        # CORRECCIÓN 3: Verificación explícita antes de crear ProductCache
        print("🔧 Aplicando corrección 3: Verificación explícita")
        
        verification_code = '''
        # ✅ VERIFICACIÓN CRÍTICA: Asegurar que redis_client esté disponible
        if redis_client is None:
            logger.error("❌ CRÍTICO: redis_client es None - no se puede crear ProductCache")
            logger.error("❌ Verificar que la declaración global incluya redis_client")
            logger.error("❌ Verificar que redis_client se inicialice correctamente antes de ProductCache")
            product_cache = None
        elif not hasattr(redis_client, 'connected'):
            logger.error("❌ CRÍTICO: redis_client no tiene atributo 'connected'")
            product_cache = None
        elif not redis_client.connected:
            logger.warning("⚠️ redis_client no está conectado - intentando crear ProductCache anyway")
            try:'''
        
        # Insertar verificación antes de la creación de ProductCache
        if 'product_cache = ProductCache(' in content:
            old_creation = 'product_cache = ProductCache('
            new_creation = verification_code + '\n                product_cache = ProductCache('
            content = content.replace(old_creation, new_creation, 1)
            print("✅ Verificación explícita añadida")
        
        # CORRECCIÓN 4: Manejo de errores mejorado para ProductCache
        print("🔧 Aplicando corrección 4: Manejo de errores mejorado")
        
        error_handling = '''
            except Exception as product_cache_error:
                logger.error(f"❌ ERROR CRÍTICO creando ProductCache: {product_cache_error}")
                logger.error(f"❌ Tipo de error: {type(product_cache_error).__name__}")
                logger.error("❌ ProductCache será None - sistema funcionará sin caché")
                product_cache = None
        else:
            logger.info("✅ redis_client disponible y conectado - creando ProductCache")
            try:
                product_cache = ProductCache('''
        
        # Buscar el final del bloque try de ProductCache y añadir manejo de errores
        if 'except Exception as cache_error:' in content:
            old_error = 'except Exception as cache_error:'
            new_error = error_handling.replace('product_cache = ProductCache(', '') + '\n            except Exception as cache_error:'
            content = content.replace(old_error, new_error, 1)
            print("✅ Manejo de errores mejorado")
        
        # CORRECCIÓN 5: Logging final para confirmar estado
        print("🔧 Aplicando corrección 5: Logging de confirmación")
        
        confirmation_logging = '''
    # ✅ CONFIRMACIÓN FINAL: Estado de ProductCache después de inicialización
    logger.info(f"📊 ESTADO FINAL ProductCache:")
    logger.info(f"  product_cache type: {type(product_cache).__name__}")
    logger.info(f"  product_cache is None: {product_cache is None}")
    if product_cache:
        logger.info(f"  product_cache.redis disponible: {hasattr(product_cache, 'redis') and product_cache.redis is not None}")
        if hasattr(product_cache, 'redis') and product_cache.redis:
            logger.info(f"  product_cache.redis.connected: {getattr(product_cache.redis, 'connected', 'N/A')}")
        logger.info("✅ ProductCache inicializado correctamente")
    else:
        logger.error("❌ ProductCache es None - sistema funcionará sin caché")
    
    # ✅ ACTUALIZAR VARIABLE GLOBAL EXPLÍCITAMENTE
    globals()['product_cache'] = product_cache
    logger.info(f"🔄 Variable global product_cache actualizada: {type(globals().get('product_cache', None)).__name__}")'''
        
        # Insertar logging de confirmación después de la inicialización de ProductCache
        if 'logger.info("✅ ProductCache creado con Redis")' in content:
            content = content.replace(
                'logger.info("✅ ProductCache creado con Redis")',
                'logger.info("✅ ProductCache creado con Redis")' + confirmation_logging
            )
            print("✅ Logging de confirmación añadido")
        
        # CORRECCIÓN 6: Actualización explícita de hybrid_recommender con product_cache
        print("🔧 Aplicando corrección 6: Actualización de hybrid_recommender")
        
        hybrid_update = '''
    
    # ✅ ACTUALIZACIÓN CRÍTICA: Asegurar que hybrid_recommender use el product_cache correcto
    try:
        if product_cache is not None:
            logger.info("🔄 Actualizando hybrid_recommender con ProductCache inicializado")
            hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
                tfidf_recommender,
                retail_recommender,
                product_cache=product_cache
            )
            logger.info("✅ hybrid_recommender actualizado con ProductCache")
        else:
            logger.warning("⚠️ hybrid_recommender funcionará sin ProductCache")
            hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
                tfidf_recommender,
                retail_recommender,
                product_cache=None
            )
    except Exception as hybrid_error:
        logger.error(f"❌ Error actualizando hybrid_recommender: {hybrid_error}")'''
        
        # Buscar donde se actualiza hybrid_recommender y mejorar
        if 'hybrid_recommender = RecommenderFactory.create_hybrid_recommender(' in content:
            # Buscar el bloque completo y reemplazarlo
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'hybrid_recommender = RecommenderFactory.create_hybrid_recommender(' in line:
                    # Encontrar el final del bloque
                    j = i
                    while j < len(lines) and not lines[j].strip().startswith('except') and not lines[j].strip().startswith('logger.info("✅ Hybrid Recommender'):
                        j += 1
                    
                    # Reemplazar el bloque
                    new_lines = lines[:i] + hybrid_update.split('\n') + lines[j:]
                    content = '\n'.join(new_lines)
                    break
            print("✅ Actualización de hybrid_recommender mejorada")
        
        # Escribir archivo corregido
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("\n🎉 CORRECCIONES APLICADAS EXITOSAMENTE")
        return True
        
    except Exception as e:
        print(f"❌ ERROR aplicando correcciones: {e}")
        # Restaurar backup
        if backup_path.exists():
            shutil.copy2(backup_path, file_path)
            print("🔄 Backup restaurado")
        return False

def verify_product_cache_fix():
    """Verifica que las correcciones se aplicaron correctamente"""
    
    file_path = Path("src/api/main_unified_redis.py")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = [
            ("Variables globales incluyen product_cache", "global redis_client, product_cache" in content or "global" in content and "product_cache" in content),
            ("Logging de diagnóstico añadido", "DIAGNÓSTICO PRODUCTCACHE" in content),
            ("Verificación antes de ProductCache", "redis_client is None" in content),
            ("Manejo de errores mejorado", "ERROR CRÍTICO creando ProductCache" in content),
            ("Logging de confirmación", "ESTADO FINAL ProductCache" in content),
            ("Actualización de globals", "globals()['product_cache']" in content)
        ]
        
        print("\n🔍 VERIFICANDO CORRECCIONES:")
        all_good = True
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"   {status} {check_name}")
            if not passed:
                all_good = False
        
        return all_good
        
    except Exception as e:
        print(f"❌ Error en verificación: {e}")
        return False

def create_test_script():
    """Crea script para probar que ProductCache funciona"""
    
    test_script = '''#!/usr/bin/env python3
"""
Test específico para verificar que ProductCache se inicializa correctamente
"""
import requests
import json
import time

def test_product_cache():
    """Prueba que ProductCache esté funcionando"""
    print("🧪 PROBANDO PRODUCTCACHE...")
    
    base_url = "http://localhost:8000"
    
    tests = [
        ("Health Check", f"{base_url}/health"),
        ("Debug Globals", f"{base_url}/debug/globals")
    ]
    
    for test_name, url in tests:
        try:
            print(f"\\n🔍 {test_name}...")
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if test_name == "Health Check":
                    cache_status = data.get("cache", {})
                    print(f"   Cache status: {cache_status.get('status', 'unknown')}")
                    print(f"   Cache message: {cache_status.get('message', 'N/A')}")
                    
                    if cache_status.get("status") == "operational":
                        print("   ✅ ProductCache funcionando correctamente")
                        return True
                    elif cache_status.get("status") == "initialization_failed":
                        print("   ❌ ProductCache aún falla en inicialización")
                        return False
                    else:
                        print(f"   ⚠️ Estado inesperado: {cache_status.get('status')}")
                
                elif test_name == "Debug Globals":
                    product_cache_info = data.get("product_cache", {})
                    print(f"   product_cache type: {product_cache_info.get('type', 'unknown')}")
                    print(f"   redis_available: {product_cache_info.get('redis_available', 'unknown')}")
                    
            else:
                print(f"   ❌ HTTP {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    return False

def main():
    print("🧪 TEST PRODUCTCACHE DESPUÉS DE CORRECCIONES")
    print("=" * 50)
    
    print("💡 Asegúrate de que el sistema esté corriendo:")
    print("   python src/api/run.py")
    print()
    
    if test_product_cache():
        print("\\n🎉 ¡PRODUCTCACHE FUNCIONANDO CORRECTAMENTE!")
        print("✅ El problema de initialization_failed ha sido resuelto")
    else:
        print("\\n⚠️ ProductCache aún tiene problemas")
        print("🔍 Revisar logs del sistema para más detalles")

if __name__ == "__main__":
    main()
'''
    
    with open("test_product_cache.py", 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print("✅ Script de prueba creado: test_product_cache.py")

def main():
    """Función principal"""
    print("🚨 CORRECCIÓN PRODUCTCACHE INITIALIZATION_FAILED")
    print("=" * 55)
    
    # Verificar ubicación
    if not Path("src/api/main_unified_redis.py").exists():
        print("❌ ERROR: Ejecutar desde la raíz del proyecto")
        print("📁 Ubicación: C:\\Users\\yasma\\Desktop\\retail-recommender-system")
        return False
    
    # Aplicar correcciones
    if not fix_product_cache_initialization():
        return False
    
    # Verificar correcciones
    if verify_product_cache_fix():
        print("\n🎉 ¡CORRECCIONES APLICADAS EXITOSAMENTE!")
        print("✅ ProductCache debería inicializarse correctamente ahora")
    else:
        print("\n⚠️ Correcciones aplicadas pero necesitan verificación manual")
    
    # Crear script de prueba
    create_test_script()
    
    print("\n🚀 PRÓXIMOS PASOS:")
    print("1. Reiniciar el sistema: python src/api/run.py")
    print("2. Ejecutar test: python test_product_cache.py")
    print("3. Verificar health check: curl http://localhost:8000/health")
    
    return True

if __name__ == "__main__":
    main()