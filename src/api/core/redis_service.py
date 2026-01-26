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

from src.api.core.redis_config_optimized import create_optimized_redis_client

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
        self._client: Optional[Any] = None  # Redis standard client
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
        """
        ✅ OPTIMIZED: Inicialización con cliente Redis optimizado
        
        Usa create_optimized_redis_client() que incluye connection pooling,
        timeouts optimizados y error handling robusto.
        """
        try:
            logger.info("🔄 Initializing RedisService with optimized client...")
            
            # ✅ MIGRACIÓN: Usar cliente optimizado en lugar de PatchedRedisClient
            self._client = await create_optimized_redis_client()
            
            # ✅ VALIDATION: Verificar conexión inmediatamente
            await self._client.ping()
            self._connected = True
            self._connection_attempts += 1
            
            logger.info("✅ RedisService initialized with optimized Redis client")
            logger.info("   ✅ Connection pooling: Active")
            logger.info("   ✅ Optimized timeouts: Applied")
            logger.info("   ✅ Enterprise features: Enabled")
                
        except Exception as e:
            logger.error(f"❌ Redis optimized connection failed: {e}")
            logger.info("🔄 RedisService degrading gracefully - fallback mode active")
            # Service degrada gracefully sin Redis
            self._client = None
            self._connected = False
    
    async def _ensure_connection(self) -> bool:
        """
        ✅ OPTIMIZED: Conexión simplificada para cliente optimizado
        
        El cliente optimizado maneja connection pooling y reconnections automáticamente.
        Solo verificamos si el cliente está disponible y responde.
        
        Returns:
            bool: True si la conexión está activa
        """
        if not self._client:
            logger.warning("⚠️ No Redis client available")
            return False
        
        try:
            # ✅ SIMPLE VALIDATION: El cliente optimizado maneja reconexiones
            await self._client.ping()
            
            if not self._connected:
                self._connected = True
                logger.debug("✅ Redis connection verified and updated")
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Redis connection lost: {e}")
            self._connected = False
            self._stats["connection_errors"] += 1
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
    
    async def health_check(self, timeout: float = None) -> Dict[str, Any]:
        """
        ✅ ENHANCED: Health check con validación real de conexión y timeout configurable
        
        Args:
            timeout: Custom timeout in seconds. 
                     Default: 1.0s (tolerant for startup and high-load scenarios)
                     Can override to 0.5s for strict runtime monitoring if needed
        
        Performance target: 
            - Startup/high-load: <1000ms (default)
            - Runtime strict: <500ms (with timeout=0.5 override)
        
        Returns:
            dict: Health check results with status, metrics, and diagnostics
            
        Status values:
            - "healthy": All checks passed, response < timeout
            - "degraded": Connected but slow (> timeout)
            - "unhealthy": Cannot connect or critical error
            - "disconnected": No client available
        """
        # ✅ Default timeout: 1.0s (more tolerant for startup/high-load)
        if timeout is None:
            timeout = 1.0
        
        timeout_ms = timeout * 1000
        
        health_data = {
            "service": "redis",
            "timestamp": datetime.now().isoformat(),
            "connected": self._connected,
            "client_available": self._client is not None,
            "connection_attempts": self._connection_attempts,
            "stats": self._stats.copy(),
            "timeout_ms": timeout_ms  # ✅ Include timeout info for debugging
        }
        
        # ✅ CRITICAL FIX: REAL CONNECTION TEST - Force verification
        if self._client:
            try:
                logger.info(f"🧪 Health check: Testing real Redis connection (timeout: {timeout_ms}ms)...")
                
                # Test real con ping y timeout configurable
                ping_start = time.time()
                await asyncio.wait_for(
                    self._client.ping(),
                    timeout=timeout  # ✅ Usar timeout parámetro
                )
                ping_time = (time.time() - ping_start) * 1000
                
                # ✅ UPDATE STATE: Si ping exitoso, actualizar estado interno
                if not self._connected:
                    logger.info("🔄 Health check: Updating internal state to connected")
                    self._connected = True
                    self._connection_attempts += 1
                
                # ✅ Status based on timeout threshold (dynamic)
                if ping_time < timeout_ms:
                    health_data["status"] = "healthy"
                    logger.info(f"✅ Health check: Redis confirmed connected (ping: {ping_time:.1f}ms)")
                else:
                    health_data["status"] = "degraded"
                    logger.warning(
                        f"⚠️ Health check: Redis slow response "
                        f"(ping: {ping_time:.1f}ms, threshold: {timeout_ms}ms)"
                    )
                
                health_data["connected"] = True  # ✅ Force update
                health_data["ping_time_ms"] = round(ping_time, 2)
                health_data["last_test"] = "successful"
                
            except asyncio.TimeoutError:
                # ✅ TIMEOUT: Timeout específico con mensaje dinámico
                logger.warning(f"⚠️ Redis health check: timeout (> {timeout_ms}ms)")
                health_data["status"] = "degraded"  # No unhealthy, solo lento
                health_data["last_test"] = f"timeout (> {timeout_ms}ms)"
                health_data["connected"] = False
                self._connected = False
                
            except Exception as ping_error:
                # ✅ ERROR: Connection error real
                logger.warning(f"⚠️ Redis health check: Redis ping failed: {ping_error}")
                health_data["status"] = "unhealthy"
                health_data["last_test"] = f"failed: {ping_error}"
                health_data["connected"] = False
                self._connected = False  # Update internal state
        else:
            health_data["status"] = "disconnected"
            health_data["last_test"] = "no_client"
        
        return health_data


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
