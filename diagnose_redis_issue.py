#!/usr/bin/env python3
"""
Script de diagnóstico para identificar problemas de conexión Redis
Ejecutar desde el directorio raíz del proyecto: python diagnose_redis_issue.py
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Configurar logging detallado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def diagnose_redis_connection():
    """Diagnostica paso a paso la conexión Redis"""
    
    print("🔍 DIAGNÓSTICO DE CONEXIÓN REDIS")
    print("=" * 50)
    
    # Paso 1: Verificar carga de variables de entorno
    print("\n1️⃣ VERIFICANDO VARIABLES DE ENTORNO")
    try:
        load_dotenv()
        print("✅ load_dotenv() ejecutado correctamente")
    except Exception as e:
        print(f"❌ Error en load_dotenv(): {e}")
        return False
    
    # Paso 2: Verificar variables específicas de Redis
    redis_vars = {
        'USE_REDIS_CACHE': os.getenv('USE_REDIS_CACHE', 'No encontrado'),
        'REDIS_HOST': os.getenv('REDIS_HOST', 'No encontrado'),
        'REDIS_PORT': os.getenv('REDIS_PORT', 'No encontrado'),
        'REDIS_SSL': os.getenv('REDIS_SSL', 'No encontrado'),
        'REDIS_PASSWORD': '***' if os.getenv('REDIS_PASSWORD') else 'No encontrado',
        'REDIS_USERNAME': os.getenv('REDIS_USERNAME', 'No encontrado'),
        'REDIS_DB': os.getenv('REDIS_DB', 'No encontrado')
    }
    
    print("\n2️⃣ VARIABLES DE REDIS EN .ENV")
    for key, value in redis_vars.items():
        print(f"   {key}: {value}")
    
    # Paso 3: Verificar configuración de Pydantic
    print("\n3️⃣ VERIFICANDO CONFIGURACIÓN PYDANTIC")
    try:
        # Importar path del proyecto
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from src.api.core.config import get_settings
        
        settings = get_settings()
        print(f"✅ get_settings() ejecutado correctamente")
        print(f"   use_redis_cache: {settings.use_redis_cache}")
        print(f"   redis_host: {settings.redis_host}")
        print(f"   redis_port: {settings.redis_port}")
        print(f"   redis_ssl: {settings.redis_ssl} (TIPO: {type(settings.redis_ssl)})")
        print(f"   redis_db: {settings.redis_db}")
        print(f"   redis_username: {settings.redis_username}")
        print(f"   redis_password: {'***' if settings.redis_password else 'None'}")
        
    except Exception as e:
        print(f"❌ Error importando configuración: {e}")
        return False
    
    # Paso 4: Verificar construcción de URL
    print("\n4️⃣ VERIFICANDO CONSTRUCCIÓN DE URL REDIS")
    try:
        from src.api.core.redis_client import RedisClient
        
        # Crear cliente manualmente con parámetros de configuración
        redis_client = RedisClient(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            ssl=settings.redis_ssl,
            username=settings.redis_username or "default"
        )
        
        print(f"✅ RedisClient creado correctamente")
        print(f"   URL construida: {redis_client.redis_url}")
        print(f"   SSL habilitado: {redis_client.ssl}")
        
    except Exception as e:
        print(f"❌ Error creando RedisClient: {e}")
        return False
    
    # Paso 5: Intentar conexión real
    print("\n5️⃣ INTENTANDO CONEXIÓN REAL")
    try:
        connection_result = await redis_client.connect()
        
        if connection_result:
            print("✅ Conexión exitosa!")
            
            # Verificar operaciones básicas
            print("\n6️⃣ VERIFICANDO OPERACIONES BÁSICAS")
            test_key = "test_diagnosis"
            test_value = "diagnosis_successful"
            
            # Test set
            set_result = await redis_client.set(test_key, test_value, ex=60)
            print(f"   SET {test_key}: {set_result}")
            
            # Test get
            get_result = await redis_client.get(test_key)
            print(f"   GET {test_key}: {get_result}")
            
            # Test delete
            delete_result = await redis_client.delete(test_key)
            print(f"   DELETE {test_key}: {delete_result}")
            
            # Health check
            health = await redis_client.health_check()
            print(f"   HEALTH CHECK: {health.get('connected', False)}")
            
            return True
        else:
            print("❌ Conexión falló")
            return False
            
    except Exception as e:
        print(f"❌ Error en conexión: {e}")
        print(f"   Tipo de error: {type(e).__name__}")
        
        # Diagnóstico específico para errores SSL
        if "SSL" in str(e) or "wrong version number" in str(e):
            print("\n🚨 ERROR SSL DETECTADO!")
            print("   Probablemente el servidor no acepta conexiones SSL")
            print("   Solución: Verificar REDIS_SSL=false en .env")
            
            # Intentar sin SSL forzadamente
            print("\n🔄 INTENTANDO SIN SSL (OVERRIDE)")
            try:
                redis_client_no_ssl = RedisClient(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    password=settings.redis_password,
                    ssl=False,  # Forzar sin SSL
                    username=settings.redis_username or "default"
                )
                
                print(f"   URL sin SSL: {redis_client_no_ssl.redis_url}")
                connection_no_ssl = await redis_client_no_ssl.connect()
                
                if connection_no_ssl:
                    print("✅ ¡CONEXIÓN EXITOSA SIN SSL!")
                    print("   SOLUCIÓN: El problema es la configuración SSL")
                    return "ssl_config_issue"
                else:
                    print("❌ Aún falla sin SSL - problema diferente")
                    
            except Exception as e2:
                print(f"❌ Error incluso sin SSL: {e2}")
        
        return False

async def main():
    """Función principal del diagnóstico"""
    result = await diagnose_redis_connection()
    
    print("\n" + "=" * 50)
    print("📋 RESUMEN DEL DIAGNÓSTICO")
    print("=" * 50)
    
    if result is True:
        print("✅ SISTEMA FUNCIONANDO CORRECTAMENTE")
        print("   Redis está conectado y operativo")
    elif result == "ssl_config_issue":
        print("🔧 PROBLEMA DE CONFIGURACIÓN SSL IDENTIFICADO")
        print("   Acción requerida: Verificar configuración SSL en .env o código")
    else:
        print("❌ PROBLEMA DETECTADO")
        print("   Revisar los errores anteriores para más detalles")
    
    print("\n🚀 PRÓXIMOS PASOS:")
    if result != True:
        print("   1. Corregir configuración identificada")
        print("   2. Verificar credenciales Redis Labs")
        print("   3. Ejecutar nuevamente este diagnóstico")
        print("   4. Probar aplicación principal")
    else:
        print("   1. Reiniciar aplicación principal")
        print("   2. Verificar endpoint /health")
        print("   3. Monitorear logs de aplicación")

if __name__ == "__main__":
    asyncio.run(main())