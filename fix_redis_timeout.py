#!/usr/bin/env python3
"""
Redis Timeout Optimization Fix
=============================

Fix inmediato para resolver los timeouts Redis en ServiceFactory
aumentando timeouts y mejorando la lógica de retry.

Author: Senior Architecture Team
"""

import sys
sys.path.append('src')

def apply_redis_timeout_optimization():
    """Aplica optimizaciones de timeout Redis"""
    
    print("🔧 APLICANDO OPTIMIZACIÓN DE TIMEOUTS REDIS")
    print("=" * 50)
    
    # Leer el archivo actual de ServiceFactory
    service_factory_path = 'src/api/factories/service_factory.py'
    
    try:
        with open(service_factory_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Backup del archivo original
        import time
        timestamp = int(time.time())
        backup_path = f'{service_factory_path}.backup_timeout_fix_{timestamp}'
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Backup creado: {backup_path}")
        
        # Optimizaciones a aplicar
        optimizations = [
            # Aumentar timeout principal
            ('timeout=5.0', 'timeout=15.0  # Increased timeout for cloud Redis'),
            
            # Mejorar timeout de health check
            ('timeout=2.0', 'timeout=5.0  # Increased health check timeout'),
            
            # Añadir retry logic mejorado
            ('except asyncio.TimeoutError:', '''except asyncio.TimeoutError:
                logger.warning("⚠️ Redis connection timeout - attempting retry...")
                # Retry una vez más con timeout extendido
                try:
                    redis_service = await asyncio.wait_for(
                        get_redis_service(),
                        timeout=20.0  # Extended timeout for retry
                    )
                    logger.info("✅ Redis connection successful on retry")
                    cls._redis_service = redis_service
                    return cls._redis_service
                except Exception as retry_error:
                    logger.error(f"❌ Redis retry failed: {retry_error}")'''),
        ]
        
        # Aplicar optimizaciones
        modified_content = content
        changes_applied = 0
        
        for old_text, new_text in optimizations:
            if old_text in modified_content:
                modified_content = modified_content.replace(old_text, new_text)
                changes_applied += 1
                print(f"✅ Optimización aplicada: {old_text[:30]}...")
        
        # Guardar archivo modificado
        if changes_applied > 0:
            with open(service_factory_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            print(f"✅ {changes_applied} optimizaciones aplicadas a ServiceFactory")
            print(f"📁 Archivo actualizado: {service_factory_path}")
        else:
            print("⚠️ No se encontraron patrones para optimizar")
        
        # Crear configuración Redis optimizada
        redis_config_optimization = '''
# Redis Configuration Optimization
# ================================
# Añadir al .env para optimizar conexiones Redis:

# Connection timeouts
REDIS_SOCKET_CONNECT_TIMEOUT=10.0
REDIS_SOCKET_TIMEOUT=10.0

# Connection pooling
REDIS_MAX_CONNECTIONS=20
REDIS_RETRY_ON_TIMEOUT=true

# Keepalive settings
REDIS_SOCKET_KEEPALIVE=true

# Health check intervals
REDIS_HEALTH_CHECK_INTERVAL=30

# Development overrides (local Redis)
# REDIS_HOST=localhost
# REDIS_PORT=6379
# REDIS_PASSWORD=
'''
        
        with open('redis_optimization_config.txt', 'w') as f:
            f.write(redis_config_optimization)
        
        print("📋 Configuración Redis optimizada creada: redis_optimization_config.txt")
        
    except Exception as e:
        print(f"❌ Error aplicando optimización: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = apply_redis_timeout_optimization()
    
    if success:
        print("\n🎯 PRÓXIMOS PASOS:")
        print("1. Ejecutar diagnóstico: python diagnostic_scripts/diagnose_redis_timeout.py")
        print("2. Revisar configuración en redis_optimization_config.txt")  
        print("3. Reiniciar aplicación para aplicar cambios")
        print("4. Ejecutar tests nuevamente para validar")
    else:
        print("\n❌ OPTIMIZACIÓN FALLÓ - Revisar errores arriba")
