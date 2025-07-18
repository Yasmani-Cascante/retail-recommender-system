"""
Patch para corregir el problema de configuración SSL de Redis.

Este archivo corrige el problema donde la configuración SSL no se aplica
correctamente desde el archivo .env.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class RedisConfigValidator:
    """Validador y corrector de configuración Redis"""
    
    @staticmethod
    def validate_and_fix_config() -> dict:
        """
        Valida y corrige la configuración Redis,
        asegurando que SSL se maneje correctamente.
        
        Returns:
            dict: Configuración corregida y validada
        """
        config = {}
        
        # 1. Validar USE_REDIS_CACHE
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
        
        # 3. CORRECCIÓN CRÍTICA: Manejo explícito de SSL
        ssl_env = os.getenv('REDIS_SSL', 'false').lower().strip()
        config['redis_ssl'] = ssl_env in ['true', '1', 'yes', 'on']
        
        # Logging para debugging
        logger.info(f"Configuración Redis validada:")
        logger.info(f"  Host: {config['redis_host']}")
        logger.info(f"  Port: {config['redis_port']}")
        logger.info(f"  SSL: {config['redis_ssl']} (original: '{ssl_env}')")
        logger.info(f"  DB: {config['redis_db']}")
        logger.info(f"  Username: {config['redis_username']}")
        logger.info(f"  Password: {'***' if config['redis_password'] else 'None'}")
        
        return config
    
    @staticmethod
    def build_redis_url(config: dict) -> str:
        """
        Construye la URL de Redis de forma explícita y segura.
        
        Args:
            config: Configuración validada de Redis
            
        Returns:
            str: URL de Redis correctamente formateada
        """
        # Esquema basado en SSL
        scheme = "rediss" if config['redis_ssl'] else "redis"
        
        # Construir parte de autenticación
        auth_part = ""
        if config['redis_username'] and config['redis_password']:
            auth_part = f"{config['redis_username']}:{config['redis_password']}@"
        elif config['redis_password']:
            auth_part = f":{config['redis_password']}@"
        
        # Construir URL completa
        redis_url = f"{scheme}://{auth_part}{config['redis_host']}:{config['redis_port']}/{config['redis_db']}"
        
        # Log seguro (sin credenciales)
        safe_url = f"{scheme}://***@{config['redis_host']}:{config['redis_port']}/{config['redis_db']}"
        logger.info(f"URL Redis construida: {safe_url}")
        
        return redis_url

# Parche directo para RedisClient
class PatchedRedisClient:
    """Cliente Redis con configuración corregida"""
    
    def __init__(self, use_validated_config=True, **kwargs):
        """
        Inicializa cliente Redis con configuración validada.
        
        Args:
            use_validated_config: Si usar validación automática de configuración
            **kwargs: Parámetros específicos (override automático)
        """
        if use_validated_config:
            # Usar configuración validada
            config = RedisConfigValidator.validate_and_fix_config()
            
            if not config.get('use_redis_cache'):
                raise ValueError("Redis cache está desactivado")
            
            # Aplicar configuración validada
            self.host = config['redis_host']
            self.port = config['redis_port']
            self.db = config['redis_db']
            self.password = config['redis_password']
            self.username = config['redis_username']
            self.ssl = config['redis_ssl']
            
            # Construir URL con método validado
            self.redis_url = RedisConfigValidator.build_redis_url(config)
        else:
            # Usar parámetros específicos (modo original)
            self.host = kwargs.get('host', 'localhost')
            self.port = kwargs.get('port', 6379)
            self.db = kwargs.get('db', 0)
            self.password = kwargs.get('password')
            self.username = kwargs.get('username', 'default')
            self.ssl = kwargs.get('ssl', False)
            
            # Construir URL manual
            scheme = "rediss" if self.ssl else "redis"
            auth_part = ""
            if self.username and self.password:
                auth_part = f"{self.username}:{self.password}@"
            elif self.password:
                auth_part = f":{self.password}@"
            
            self.redis_url = f"{scheme}://{auth_part}{self.host}:{self.port}/{self.db}"
        
        # Inicializar estado de conexión
        self.client = None
        self.connected = False
        self.stats = {"connections": 0, "errors": 0, "operations": 0}
        
        logger.info(f"PatchedRedisClient inicializado:")
        logger.info(f"  SSL: {self.ssl}")
        logger.info(f"  URL: {self.redis_url.split('@')[-1] if '@' in self.redis_url else self.redis_url}")
    
    async def connect(self) -> bool:
        """
        Establece conexión con Redis con retry automático.
        
        Returns:
            bool: True si la conexión fue exitosa
        """
        import redis.asyncio as redis
        
        # Intentar conexión con configuración actual
        try:
            logger.info(f"Intentando conexión Redis: {self.redis_url.split('@')[-1] if '@' in self.redis_url else self.redis_url}")
            
            self.client = await redis.from_url(
                self.redis_url,
                decode_responses=True,
                health_check_interval=30
            )
            
            await self.client.ping()
            self.connected = True
            self.stats["connections"] += 1
            logger.info("✅ Conexión Redis exitosa")
            return True
            
        except Exception as e:
            self.connected = False
            self.stats["errors"] += 1
            logger.error(f"❌ Error conectando a Redis: {str(e)}")
            
            # Si es error SSL, intentar sin SSL automáticamente
            if "SSL" in str(e) or "wrong version number" in str(e):
                logger.warning("🔄 Detectado error SSL, intentando sin SSL...")
                return await self._retry_without_ssl()
            
            return False
    
    async def _retry_without_ssl(self) -> bool:
        """
        Reintenta conexión forzando SSL=False.
        
        Returns:
            bool: True si la conexión sin SSL fue exitosa
        """
        import redis.asyncio as redis
        
        try:
            # Construir URL sin SSL
            auth_part = ""
            if self.username and self.password:
                auth_part = f"{self.username}:{self.password}@"
            elif self.password:
                auth_part = f":{self.password}@"
            
            no_ssl_url = f"redis://{auth_part}{self.host}:{self.port}/{self.db}"
            
            logger.info(f"Intentando conexión sin SSL: redis://***@{self.host}:{self.port}/{self.db}")
            
            self.client = await redis.from_url(
                no_ssl_url,
                decode_responses=True,
                health_check_interval=30
            )
            
            await self.client.ping()
            self.connected = True
            self.ssl = False  # Actualizar configuración
            self.redis_url = no_ssl_url  # Actualizar URL
            self.stats["connections"] += 1
            
            logger.info("✅ Conexión Redis exitosa SIN SSL")
            logger.warning("⚠️ IMPORTANTE: SSL desactivado automáticamente")
            logger.warning("   Considera actualizar la configuración .env con REDIS_SSL=false")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error incluso sin SSL: {str(e)}")
            self.connected = False
            return False
    
    async def ensure_connected(self) -> bool:
        """Asegura que el cliente esté conectado."""
        if self.connected and self.client:
            try:
                await self.client.ping()
                return True
            except Exception:
                self.connected = False
        
        if not self.connected:
            return await self.connect()
        return True
    
    async def get(self, key: str):
        """Obtiene un valor de Redis."""
        if not await self.ensure_connected():
            return None
        
        try:
            self.stats["operations"] += 1
            return await self.client.get(key)
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error obteniendo clave {key}: {str(e)}")
            self.connected = False
            return None
    
    async def set(self, key: str, value: str, ex=None) -> bool:
        """Guarda un valor en Redis."""
        if not await self.ensure_connected():
            return False
        
        try:
            self.stats["operations"] += 1
            await self.client.set(key, value, ex=ex)
            return True
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error guardando clave {key}: {str(e)}")
            self.connected = False
            return False
    
    async def delete(self, key: str) -> bool:
        """Elimina una clave de Redis."""
        if not await self.ensure_connected():
            return False
        
        try:
            self.stats["operations"] += 1
            await self.client.delete(key)
            return True
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error eliminando clave {key}: {str(e)}")
            self.connected = False
            return False
    
    async def health_check(self) -> dict:
        """Verifica el estado de la conexión a Redis."""
        status = {
            "connected": self.connected,
            "stats": self.stats,
            "ssl_enabled": self.ssl
        }
        
        if self.connected and self.client:
            try:
                ping_result = await self.client.ping()
                status["ping"] = ping_result
                
                info = await self.client.info()
                status["server_info"] = {
                    "version": info.get("redis_version"),
                    "used_memory_human": info.get("used_memory_human"),
                    "uptime_in_days": info.get("uptime_in_days"),
                    "connected_clients": info.get("connected_clients")
                }
            except Exception as e:
                status["error"] = str(e)
                self.connected = False
        
        return status


# Función para aplicar el parche al sistema existente
def patch_redis_system():
    """
    Aplica el parche al sistema Redis existente.
    Usar con precaución - modifica el comportamiento global.
    """
    try:
        import src.api.core.redis_client as redis_module
        
        # Guardar clase original como backup
        redis_module.RedisClientOriginal = redis_module.RedisClient
        
        # Reemplazar con versión patcheada
        redis_module.RedisClient = PatchedRedisClient
        
        logger.info("✅ Parche Redis aplicado correctamente")
        logger.info("   RedisClient original disponible como RedisClientOriginal")
        
        return True
    except Exception as e:
        logger.error(f"❌ Error aplicando parche Redis: {e}")
        return False


# Función para validar configuración sin modificar el sistema
async def validate_current_redis_config():
    """
    Valida la configuración actual de Redis sin modificar el sistema.
    Útil para debugging.
    
    Returns:
        dict: Resultado de la validación
    """
    result = {
        "config_valid": False,
        "connection_successful": False,
        "ssl_issue_detected": False,
        "recommended_action": None
    }
    
    try:
        # Validar configuración
        config = RedisConfigValidator.validate_and_fix_config()
        
        if not config.get('use_redis_cache'):
            result["recommended_action"] = "Activar Redis cache con USE_REDIS_CACHE=true"
            return result
        
        result["config_valid"] = True
        
        # Probar conexión
        test_client = PatchedRedisClient(use_validated_config=True)
        connection_result = await test_client.connect()
        
        result["connection_successful"] = connection_result
        result["ssl_issue_detected"] = not test_client.ssl and config['redis_ssl']
        
        if result["ssl_issue_detected"]:
            result["recommended_action"] = "Actualizar .env con REDIS_SSL=false"
        elif not connection_result:
            result["recommended_action"] = "Verificar credenciales y conectividad Redis"
        else:
            result["recommended_action"] = "Configuración correcta"
        
        return result
        
    except Exception as e:
        result["error"] = str(e)
        result["recommended_action"] = f"Corregir error: {e}"
        return result