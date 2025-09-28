#!/usr/bin/env python3
"""
Redis Configuration Fix
=======================

Fix urgente para resolver el problema de configuración Redis que está
desactivando el cache incluso cuando USE_REDIS_CACHE=True.

Author: Senior Architecture Team
"""

import sys
import os
sys.path.append('src')

def debug_redis_configuration():
    """Debuggea la configuración Redis paso a paso"""
    
    print("🔍 DEBUG CONFIGURACIÓN REDIS PASO A PASO")
    print("=" * 50)
    
    # Debug variables de entorno
    print("\n📋 VARIABLES DE ENTORNO:")
    redis_vars = [
        'USE_REDIS_CACHE',
        'REDIS_HOST', 
        'REDIS_PORT',
        'REDIS_SSL',
        'REDIS_PASSWORD',
        'REDIS_USERNAME',
        'REDIS_DB'
    ]
    
    for var in redis_vars:
        value = os.getenv(var, 'NOT_SET')
        print(f"  {var}: '{value}'")
    
    # Debug lógica de validación
    print("\n🔧 LÓGICA DE VALIDACIÓN:")
    
    use_cache_raw = os.getenv('USE_REDIS_CACHE', 'false')
    print(f"  use_cache_raw: '{use_cache_raw}'")
    
    use_cache_lower = use_cache_raw.lower()
    print(f"  use_cache_lower: '{use_cache_lower}'")
    
    valid_values = ['true', '1', 'yes', 'on']
    print(f"  valid_values: {valid_values}")
    
    use_cache_result = use_cache_lower in valid_values
    print(f"  use_cache_result: {use_cache_result}")
    
    # Test del validador actual
    print("\n🧪 TEST DEL VALIDADOR ACTUAL:")
    try:
        from src.api.core.redis_config_fix import RedisConfigValidator
        
        config = RedisConfigValidator.validate_and_fix_config()
        print(f"  config['use_redis_cache']: {config.get('use_redis_cache', 'NOT_FOUND')}")
        
        if config.get('use_redis_cache'):
            print("  ✅ Validador debería activar Redis")
        else:
            print("  ❌ Validador está desactivando Redis - PROBLEMA AQUÍ")
            
    except Exception as e:
        print(f"  ❌ Error en validador: {e}")
    
    return use_cache_result

def fix_redis_configuration():
    """Aplica fix inmediato a la configuración Redis"""
    
    print("\n🔧 APLICANDO FIX CONFIGURACIÓN REDIS")
    print("=" * 50)
    
    # Backup del archivo original
    import time
    timestamp = int(time.time())
    
    redis_config_path = 'src/api/core/redis_config_fix.py'
    backup_path = f'{redis_config_path}.backup_config_fix_{timestamp}'
    
    try:
        with open(redis_config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Backup creado: {backup_path}")
        
        # Fix específico: Hacer logging más verbose y verificar lógica
        fixes = [
            # Añadir debug más detallado
            ('logger.info("Redis cache desactivado por configuración")', 
             '''logger.info(f"Redis cache desactivado por configuración - use_cache_raw: '{os.getenv('USE_REDIS_CACHE')}', processed: '{use_cache}', result: {config['use_redis_cache']}")'''),
            
            # Fix: Hacer la validación más explícita
            ('use_cache = os.getenv(\'USE_REDIS_CACHE\', \'false\').lower()',
             '''use_cache = os.getenv('USE_REDIS_CACHE', 'false').lower().strip()
        logger.info(f"🔍 Redis config debug: USE_REDIS_CACHE='{os.getenv('USE_REDIS_CACHE')}' -> processed='{use_cache}'")')'''),
        ]
        
        modified_content = content
        changes_applied = 0
        
        for old_text, new_text in fixes:
            if old_text in modified_content:
                modified_content = modified_content.replace(old_text, new_text)
                changes_applied += 1
                print(f"✅ Fix aplicado: {old_text[:50]}...")
        
        # Aplicar cambios
        if changes_applied > 0:
            with open(redis_config_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            print(f"✅ {changes_applied} fixes aplicados")
        else:
            print("⚠️ No se encontraron patrones para fix")
        
        return True
        
    except Exception as e:
        print(f"❌ Error aplicando fix: {e}")
        return False

def create_alternative_config():
    """Crea configuración alternativa que bypassa el problema"""
    
    print("\n🔄 CREANDO CONFIGURACIÓN ALTERNATIVA")
    print("=" * 50)
    
    # Configuración directa que bypassa validation
    alternative_config = '''
# CONFIGURACIÓN REDIS ALTERNATIVA - BYPASS VALIDATION
# ==================================================

# En .env, usar valores explícitos:
USE_REDIS_CACHE=true
REDIS_HOST=redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com
REDIS_PORT=14272
REDIS_SSL=false
REDIS_USERNAME=default
REDIS_PASSWORD=your_password_here

# Variables adicionales para debug
REDIS_DEBUG=true
REDIS_FORCE_ENABLE=true
'''
    
    with open('.env.redis_alternative', 'w') as f:
        f.write(alternative_config)
    
    print("✅ Configuración alternativa creada: .env.redis_alternative")
    
    # Script de test bypass
    bypass_test = '''#!/usr/bin/env python3
"""Test Redis con bypass de validation"""

import asyncio
import sys
import os
sys.path.append('src')

# BYPASS: Force enable Redis
os.environ['USE_REDIS_CACHE'] = 'true'
os.environ['REDIS_FORCE_ENABLE'] = 'true'

async def test_redis_bypass():
    """Test Redis con bypass de validation logic"""
    
    print("🔄 TESTING REDIS CON BYPASS")
    print("=" * 40)
    
    try:
        # Import directo sin validation
        from src.api.core.redis_config_fix import PatchedRedisClient
        
        # Crear cliente directamente con parámetros
        redis_client = PatchedRedisClient(
            host='redis-14272.c259.us-central1-2.gce.redns.redis-cloud.com',
            port=14272,
            password=os.getenv('REDIS_PASSWORD', ''),
            username='default',
            ssl=False,
            use_validated_config=False  # BYPASS validation
        )
        
        print("🔌 Connecting directly...")
        await redis_client.connect()
        
        if redis_client.connected:
            print("✅ CONNECTION SUCCESSFUL!")
            
            # Test operaciones
            await redis_client.set("test_bypass", "success", ex=60)
            value = await redis_client.get("test_bypass")
            print(f"📝 Test value: {value}")
            
            # Ping
            ping = await redis_client.ping()
            print(f"🏓 Ping: {ping}")
            
            # Cleanup
            await redis_client.delete("test_bypass")
            print("🧹 Cleanup done")
            
            return True
        else:
            print("❌ Connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_redis_bypass())
    if success:
        print("\\n🎯 BYPASS SUCCESSFUL - Redis está funcionando")
        print("El problema está en la lógica de validation, no en Redis")
    else:
        print("\\n❌ BYPASS FAILED - Hay otro problema")
'''
    
    with open('test_redis_bypass.py', 'w') as f:
        f.write(bypass_test)
    
    print("🧪 Test bypass creado: test_redis_bypass.py")

if __name__ == "__main__":
    print("🚀 REDIS CONFIGURATION DEBUG & FIX")
    print("=" * 60)
    
    # Debug configuración actual
    should_be_enabled = debug_redis_configuration()
    
    if should_be_enabled:
        print("\n✅ USE_REDIS_CACHE está correctamente configurado")
        print("❌ Problema está en la lógica de validation")
        
        # Aplicar fix
        fix_success = fix_redis_configuration()
        
        # Crear alternativas
        create_alternative_config()
        
        print("\n🎯 PRÓXIMOS PASOS:")
        print("1. Ejecutar: python test_redis_bypass.py")
        print("2. Si bypass funciona, el problema está confirmado en validation")
        print("3. Actualizar .env con variables de .env.redis_alternative")
        print("4. Ejecutar tests principales nuevamente")
        
    else:
        print("\n❌ USE_REDIS_CACHE no está configurado correctamente")
        print("🔧 Actualizar .env con USE_REDIS_CACHE=true")
