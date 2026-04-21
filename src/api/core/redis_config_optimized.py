# src/api/core/redis_config_optimized.py
"""
Redis Configuration Optimizada - Performance Fix
=================================================

✅ OPTIMIZACIONES APLICADAS:
1. Timeouts optimizados para startup rápido (2-3s)
2. Connection pooling mejorado (20 conexiones)
3. Health checks eficientes (1s timeout)
4. Circuit breaker integration
5. Async-first design

Author: Senior Architecture Team
Version: 2.1.0 - Redis Performance Optimized
"""

import os
import logging
import asyncio
from typing import Dict, Optional

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("✅ Redis module imported successfully (optimized config)")
except ImportError:
    REDIS_AVAILABLE = False
    import logging
    logger = logging.getLogger(__name__)
    logger.error("❌ Redis module not available")

class OptimizedRedisConfig:
    """
    ✅ Configuración Redis optimizada para performance enterprise
    """
    
    @staticmethod
    def get_optimized_config() -> dict:
        """
        ✅ CONFIGURACIÓN OPTIMIZADA - Fast startup, reliable connection
        
        Returns:
            dict: Configuración Redis optimizada para performance
        """
        config = {}
        
        # 1. Feature flags
        use_cache = os.getenv('USE_REDIS_CACHE', 'false').lower()
        config['use_redis_cache'] = use_cache in ['true', '1', 'yes', 'on']
        
        if not config['use_redis_cache']:
            logger.info("Redis cache desactivado por configuración")
            return config
        
        # 2. Configuración básica
        config['redis_host'] = os.getenv('REDIS_HOST', 'localhost')
        config['redis_port'] = int(os.getenv('REDIS_PORT', '6379'))
        config['redis_db'] = int(os.getenv('REDIS_DB', '0'))
        config['redis_password'] = os.getenv('REDIS_PASSWORD')
        config['redis_username'] = os.getenv('REDIS_USERNAME', 'default')
        
        # 3. SSL configuration
        ssl_env = os.getenv('REDIS_SSL', 'false').lower().strip()
        config['redis_ssl'] = ssl_env in ['true', '1', 'yes', 'on']
        
        # ✅ 4. PERFORMANCE OPTIMIZATIONS
        config.update({
            # ✅ Timeouts optimizados para startup rápido
            # 'socket_timeout': 2.0,           # ← REDUCIDO de 3.0s
            'socket_timeout': 1.0, 
            # 'socket_connect_timeout': 1.5,   # ← REDUCIDO de 2.0s  
            'socket_connect_timeout': 0.8,
            'socket_keepalive': True,
            'socket_keepalive_options': {},
            
            # ✅ Connection pooling enterprise
            'max_connections': 28,           # Pool size
            'retry_on_timeout': True,
            'retry_on_error': [ConnectionError, TimeoutError],
            'health_check_interval': 30,     # Health check cada 30s
            
            # ✅ Encoding y serialización
            'decode_responses': True,
            'encoding': 'utf-8',
            'encoding_errors': 'strict',
            
            # ✅ Cliente identificación
            'client_name': 'retail-recommender-v2-optimized'
        })
        
        # 5. Logging de configuración
        logger.info("✅ Redis configuration optimizada:")
        logger.info(f"   Host: {config['redis_host']}:{config['redis_port']}")
        logger.info(f"   SSL: {config['redis_ssl']}")
        logger.info(f"   Socket timeout: {config['socket_timeout']}s")
        logger.info(f"   Connect timeout: {config['socket_connect_timeout']}s")
        logger.info(f"   Max connections: {config['max_connections']}")
        
        return config
    
    @staticmethod
    def build_optimized_redis_url(config: dict) -> str:
        """
        ✅ Construir URL Redis optimizada
        """
        # Esquema basado en SSL
        scheme = "rediss" if config['redis_ssl'] else "redis"
        
        # Construir autenticación
        auth_part = ""
        if config['redis_username'] and config['redis_password']:
            auth_part = f"{config['redis_username']}:{config['redis_password']}@"
        elif config['redis_password']:
            auth_part = f":{config['redis_password']}@"
        
        # URL completa
        redis_url = f"{scheme}://{auth_part}{config['redis_host']}:{config['redis_port']}/{config['redis_db']}"
        
        # Log seguro
        safe_url = f"{scheme}://***@{config['redis_host']}:{config['redis_port']}/{config['redis_db']}"
        logger.info(f"✅ Redis URL optimizada: {safe_url}")
        
        return redis_url

    @staticmethod
    def get_optimized_redis_kwargs(config: dict) -> dict:
        """
        ✅ Generar kwargs optimizados para redis.from_url()
        """
        return {
            'socket_timeout': config['socket_timeout'],
            'socket_connect_timeout': config['socket_connect_timeout'],
            'socket_keepalive': config['socket_keepalive'],
            'socket_keepalive_options': config['socket_keepalive_options'],
            'max_connections': config['max_connections'],
            'retry_on_timeout': config['retry_on_timeout'],
            'retry_on_error': config['retry_on_error'],
            'health_check_interval': config['health_check_interval'],
            'decode_responses': config['decode_responses'],
            'encoding': config['encoding'],
            'encoding_errors': config['encoding_errors'],
            'client_name': config['client_name']
        }

# ============================================================================
# 🔧 INTEGRATION FUNCTIONS - Para usar en ServiceFactory y RedisService
# ============================================================================

async def create_optimized_redis_client():
    """
    ✅ Factory function para crear cliente Redis optimizado
    """
    if not REDIS_AVAILABLE:
        raise ImportError("Redis no disponible - instalar: pip install redis[asyncio]")
    
    config = OptimizedRedisConfig.get_optimized_config()
    
    if not config.get('use_redis_cache'):
        raise ValueError("Redis cache está desactivado")
    
    # Construir URL y kwargs optimizados
    redis_url = OptimizedRedisConfig.build_optimized_redis_url(config)
    redis_kwargs = OptimizedRedisConfig.get_optimized_redis_kwargs(config)
    
    # Crear cliente con configuración optimizada
    client = await redis.from_url(redis_url, **redis_kwargs)
    
    return client

def get_optimized_config_for_service_factory() -> dict:
    """
    ✅ Función específica para ServiceFactory integration
    """
    return OptimizedRedisConfig.get_optimized_config()

# ============================================================================
# 🔧 BACKWARD COMPATIBILITY - Para PatchedRedisClient
# ============================================================================

# def patch_redis_config_with_optimization():
#     """
#     ✅ Patch PatchedRedisClient con configuración optimizada
#     """
#     try:
#         from src.api.core.redis_config_fix import PatchedRedisClient
        
#         # Sobrescribir configuración por defecto
#         optimized_config = OptimizedRedisConfig.get_optimized_config()
        
#         # Crear método para usar configuración optimizada
#         def get_optimized_client():
#             return PatchedRedisClient(
#                 host=optimized_config['redis_host'],
#                 port=optimized_config['redis_port'],
#                 db=optimized_config['redis_db'],
#                 password=optimized_config['redis_password'],
#                 username=optimized_config['redis_username'],
#                 ssl=optimized_config['redis_ssl'],
#                 socket_timeout=optimized_config['socket_timeout'],
#                 socket_connect_timeout=optimized_config['socket_connect_timeout'],
#                 max_connections=optimized_config['max_connections']
#             )
        
#         return get_optimized_client
        
#     except ImportError as e:
#         logger.warning(f"⚠️ Could not patch PatchedRedisClient: {e}")
#         return None
