"""
Redis Service Layer - Arquitectura Enterprise
==============================================

Capa de abstracción para operaciones Redis que proporciona:
- Connection pooling automático
- Error handling consistente  
- Observabilidad integrada
- Preparación para microservicios

Author: Senior Architecture Team
"""

import asyncio
import logging
import json
from typing import Optional, Any, Dict
from datetime import datetime
import time

from src.api.core.redis_config_fix import PatchedRedisClient

logger = logging.getLogger(__name__)

class RedisServiceError(Exception):
    """Base exception para errores de Redis Service"""
    pass

class RedisService:
    """
    🏗️ ENTERPRISE REDIS SERVICE
    
    Proporciona una interfaz limpia y robusta para operaciones Redis
    con connection management automático y error handling consistente.
    """
    
    _instance: Optional['RedisService'] = None
    _connection_lock = asyncio.Lock()
    
    def __init__(self):
        self._client: Optional[PatchedRedisClient] = None
        self._connected = False
        self._connection_attempts = 0
        self._last_connection_attempt = 0
        self._stats = {
            "operations_total": 0,
            "operations_successful": 0,
            "operations_failed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "connection_errors": 0
        }
    
    @classmethod
    async def get_instance(cls) -> 'RedisService':
        """
        Singleton pattern con lazy initialization.
        Thread-safe y async-safe.
        """
        logger.info(f"✅ get_instance(): Getting RedisService instance: {cls._instance}")
        if cls._instance is None:
            async with cls._connection_lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance._initialize()
        logger.info(f"✅ get_instance(): RedisService instance retrieved: {cls._instance}")
        return cls._instance
    
    async def _initialize(self):
        """Inicialización segura del servicio Redis"""
        try:
            self._client = PatchedRedisClient(use_validated_config=True)
            # ✅ FASE 1 KEY FIX: Conectar durante inicialización
            await self._ensure_connection()
            logger.info("✅ RedisService initialized successfully")
        except Exception as e:
            logger.warning(f"⚠️ RedisService initialization failed: {e}")
            # Service degrada gracefully sin Redis
            self._client = None
    
    async def _ensure_connection(self) -> bool:
        """
        Asegura que tenemos una conexión válida a Redis.
        
        Returns:
            bool: True si la conexión está disponible
        """
        if not self._client:
            return False
        
        # Rate limiting para evitar spam de conexiones
        current_time = time.time()
        if (current_time - self._last_connection_attempt) < 5:  # 5 segundo cooldown
            return self._connected
        
        self._last_connection_attempt = current_time
        
        try:
            if not self._connected:
                async with self._connection_lock:
                    if not self._connected:  # Double-check
                        logger.info("🔄 Intentando conectar a Redis (PatchedRedisClient.connect)...")
                        try:
                            # Timeout de 5 segundos para la conexión
                            success = await asyncio.wait_for(self._client.connect(), timeout=5)
                        except asyncio.TimeoutError:
                            logger.error("❌ Timeout: La conexión a Redis superó los 5 segundos.")
                            self._connection_attempts += 1
                            return False
                        if success:
                            self._connected = True
                            self._connection_attempts = 0
                            logger.info("✅ Redis connection established")
                        else:
                            self._connection_attempts += 1
                            logger.warning(f"Redis connection failed (attempt {self._connection_attempts})")
            return self._connected
        except Exception as e:
            self._stats["connection_errors"] += 1
            self._connected = False
            logger.error(f"Redis connection error: {e}")
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """
        🔍 GET operation con error handling robusto
        
        Args:
            key: Redis key
            
        Returns:
            Valor o None si no existe/error
        """
        self._stats["operations_total"] += 1
        
        if not await self._ensure_connection():
            self._stats["operations_failed"] += 1
            logger.debug(f"Redis not available for GET: {key}")
            return None
        
        try:
            result = await self._client.get(key)
            self._stats["operations_successful"] += 1
            
            if result is not None:
                self._stats["cache_hits"] += 1
                logger.debug(f"Cache HIT: {key}")
            else:
                self._stats["cache_misses"] += 1
                logger.debug(f"Cache MISS: {key}")
            
            return result
            
        except Exception as e:
            self._stats["operations_failed"] += 1
            self._connected = False  # Force reconnection next time
            logger.debug(f"Redis GET error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """
        🔄 SET operation con TTL opcional
        
        Args:
            key: Redis key
            value: Value to store
            ttl: TTL in seconds (optional)
            
        Returns:
            bool: True if successful
        """
        self._stats["operations_total"] += 1
        
        if not await self._ensure_connection():
            self._stats["operations_failed"] += 1
            logger.debug(f"Redis not available for SET: {key}")
            return False
        
        try:
            if ttl:
                success = await self._client.setex(key, ttl, value)
            else:
                success = await self._client.set(key, value)
            
            if success:
                self._stats["operations_successful"] += 1
                logger.debug(f"Cache SET: {key} (TTL: {ttl})")
            else:
                self._stats["operations_failed"] += 1
            
            return bool(success)
            
        except Exception as e:
            self._stats["operations_failed"] += 1
            self._connected = False
            logger.debug(f"Redis SET error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        🗑️ DELETE operation
        
        Args:
            key: Redis key to delete
            
        Returns:
            bool: True if successful
        """
        self._stats["operations_total"] += 1
        
        if not await self._ensure_connection():
            self._stats["operations_failed"] += 1
            return False
        
        try:
            result = await self._client.delete(key)
            self._stats["operations_successful"] += 1
            logger.debug(f"Cache DELETE: {key}")
            return bool(result)
            
        except Exception as e:
            self._stats["operations_failed"] += 1
            self._connected = False
            logger.debug(f"Redis DELETE error for key {key}: {e}")
            return False
    
    async def get_json(self, key: str) -> Optional[Dict]:
        """
        📄 GET con deserialización JSON automática
        
        Args:
            key: Redis key
            
        Returns:
            Dict deserialized or None
        """
        raw_value = await self.get(key)
        if raw_value is None:
            return None
        
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for key {key}: {e}")
            return None
    
    async def set_json(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        """
        📝 SET con serialización JSON automática
        
        Args:
            key: Redis key
            value: Dict to serialize
            ttl: TTL in seconds (optional)
            
        Returns:
            bool: True if successful
        """
        try:
            json_value = json.dumps(value)
            return await self.set(key, json_value, ttl)
        except (TypeError, ValueError) as e:
            logger.warning(f"JSON encode error for key {key}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        📊 Estadísticas del servicio para observabilidad
        """
        hit_ratio = 0.0
        if self._stats["cache_hits"] + self._stats["cache_misses"] > 0:
            hit_ratio = self._stats["cache_hits"] / (self._stats["cache_hits"] + self._stats["cache_misses"])
        
        return {
            **self._stats,
            "connected": self._connected,
            "hit_ratio": hit_ratio,
            "client_available": self._client is not None,
            "connection_attempts": self._connection_attempts,
            "last_update": datetime.now().isoformat()
        }
    
    def reset_stats(self):
        """Reset statistics (útil para testing)"""
        self._stats = {key: 0 for key in self._stats.keys()}
    
    async def health_check(self) -> Dict[str, Any]:
        """
        🏥 Health check completo del servicio
        """
        health = {
            "service": "RedisService",
            "status": "unknown",
            "connected": False,
            "ping_successful": False,
            "error": None
        }
        
        try:
            if await self._ensure_connection():
                # Test ping
                ping_result = await self._client.ping()
                health.update({
                    "status": "healthy",
                    "connected": True,
                    "ping_successful": bool(ping_result),
                    "stats": self.get_stats()
                })
            else:
                health.update({
                    "status": "degraded",
                    "connected": False,
                    "ping_successful": False,
                    "stats": self.get_stats()
                })
                
        except Exception as e:
            health.update({
                "status": "unhealthy",
                "connected": False,
                "ping_successful": False,
                "error": str(e),
                "stats": self.get_stats()
            })
        
        return health


# ============================================================================
# 🔧 CONVENIENCE FUNCTIONS - Backward Compatibility
# ============================================================================

async def get_redis_service() -> RedisService:
    """
    Factory function para obtener la instancia del servicio Redis.
    Mantiene compatibilidad con el código existente.
    """
    instance = await RedisService.get_instance()
    if not instance:
        logger.error("❌ No se pudo obtener la instancia de RedisService")
    logger.info(f"✅ get_redis_service(): RedisService instance retrieved: {instance}")
    # return await RedisService.get_instance()
    return instance


# ============================================================================
# 📊 OBSERVABILITY HELPERS
# ============================================================================

async def get_redis_health() -> Dict[str, Any]:
    """Health check rápido para endpoints de salud"""
    service = await get_redis_service()
    return await service.health_check()

async def get_redis_stats() -> Dict[str, Any]:
    """Estadísticas para métricas"""
    service = await get_redis_service()
    return service.get_stats()
