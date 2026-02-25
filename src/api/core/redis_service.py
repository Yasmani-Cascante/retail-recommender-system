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
from contextlib import asynccontextmanager  # ✅ M3: Para distributed_lock
from datetime import datetime
import time

from src.api.core.redis_config_optimized import create_optimized_redis_client

# ✅ H1 Structured Logging: usar structlog (mismo patron que shopify_kb_sync.py).
# REQUERIDO por M3: distributed_lock() usa kwargs estructurados en los logs
# (lock_name=, action=, note=). El logger estandar de Python no los acepta.
# structlog.BoundLogger si acepta kwargs arbitrarios como campos de contexto.
#
# PREREQUISITO: structlog debe estar configurado antes de usar este logger.
# En produccion: configure_structlog() en main.py
# En tests:      structlog.configure() en tests/conftest.py (top-level)
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    # Fallback para entornos sin structlog instalado.
    # ADVERTENCIA: logger.warning(msg, lock_name=...) lanzara TypeError
    # porque logging.Logger no acepta kwargs arbitrarios.
    # Solucion: instalar structlog (esta en requirements.txt del proyecto).
    logger = logging.getLogger(__name__)


# ============================================================================
# ✅ M3: CUSTOM EXCEPTIONS
# ============================================================================

class DistributedLockError(Exception):
    """
    ✅ M3 — Distributed Locking

    Lanzada cuando no se puede obtener un distributed lock en Redis
    dentro del tiempo limite definido por blocking_timeout.

    Permite al caller decidir si hacer retry, skip o fallar la operacion.

    Ejemplo:
        try:
            async with redis_service.distributed_lock("kb_sync:lock:returns:es"):
                await conn.execute(upsert_query)
        except DistributedLockError as e:
            logger.warning("lock_timeout", lock_name=str(e))
    """
    pass


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
        """Reset statistics (util para testing)"""
        self._stats = {key: 0 for key in self._stats.keys()}

    # ========================================================================
    # ✅ M3: DISTRIBUTED LOCKING
    # ========================================================================

    @asynccontextmanager
    async def distributed_lock(
        self,
        lock_name: str,
        timeout: float = 30.0,
        blocking_timeout: float = 5.0,
        sleep: float = 0.1
    ):
        """
        ✅ M3 — Distributed Lock via Redis.

        Context manager que adquiere un lock en Redis antes de ceder control
        al bloque `async with`, y lo libera al salir (incluso si hay excepcion).

        GARANTIA CROSS-INSTANCE:
            Cualquier numero de instancias de Cloud Run comparten el mismo Redis.
            Solo UNA instancia a la vez puede tener el lock para un lock_name dado.
            Esto previene race conditions en operaciones criticas como upserts en DB.

        DEGRADED MODE (Redis no disponible):
            Si self._client es None o la conexion falla, el metodo cede control
            SIN lock. La operacion se ejecuta igual, pero sin garantia cross-instance.
            Esto preserva el comportamiento pre-M3 y evita que Redis caido tumbe el sync.

        LOCK KEY FORMAT RECOMENDADO:
            "kb_sync:lock:{sub_intent}:{language}:{category}"
            Ejemplo: "kb_sync:lock:policy_return:es:general"

        PARAMETROS:
            lock_name        Nombre unico del lock (Redis key). Debe identificar
                             exactamente el recurso a proteger.
            timeout          TTL en segundos del lock en Redis (30.0 default).
                             Tras este tiempo, Redis lo libera automaticamente,
                             previniendo deadlocks si una instancia muere con el lock.
            blocking_timeout Segundos maximos esperando para obtener el lock (5.0 default).
                             Si transcurre este tiempo sin obtenerlo, lanza DistributedLockError.
            sleep            Intervalo de polling en segundos mientras espera (0.1 default).

        RAISES:
            DistributedLockError  Si no se obtiene el lock en blocking_timeout segundos.

        EJEMPLO:
            lock_key = f"kb_sync:lock:{sub_intent}:{language}:{category}"
            try:
                async with redis_service.distributed_lock(lock_key, timeout=30, blocking_timeout=5):
                    async with db_pool.acquire() as conn:
                        await conn.execute(upsert_query, ...)
            except DistributedLockError:
                logger.warning("lock_not_acquired", lock_key=lock_key)
                # Hacer retry o re-raise segun politica del caller
        """
        # ── DEGRADED MODE: Si no hay cliente Redis, ceder sin lock ────────────
        # Esto garantiza que el sync siga funcionando aunque Redis este caido.
        # La proteccion cross-instance no aplica en este caso, pero es mejor
        # ejecutar sin lock que bloquear todo el proceso de sync.
        if not self._client or not self._connected:
            logger.warning(
                "distributed_lock_redis_unavailable",
                lock_name=lock_name,
                action="yielding_without_lock",
                note="degraded_mode_active_no_cross_instance_protection"
            )
            # ✅ M3: Registrar modo degradado en Prometheus
            try:
                from src.api.core.prometheus_metrics import kb_distributed_lock_acquisitions_total
                kb_distributed_lock_acquisitions_total.labels(result="degraded").inc()
            except ImportError:
                pass
            # Ceder sin lock (comportamiento identico al pre-M3)
            yield None
            return

        # ── ADQUIRIR EL LOCK ─────────────────────────────────────────────────
        # redis.asyncio.Lock implementa el algoritmo de locking de Redis:
        # 1. SET lock_name {random_token} NX PX {timeout_ms}
        # 2. Si NX tiene exito, somos los duenos del lock
        # 3. Si no, hacer polling cada `sleep` segundos hasta blocking_timeout
        lock = self._client.lock(
            lock_name,
            timeout=timeout,             # TTL del lock en Redis (auto-expire)
            blocking_timeout=blocking_timeout,  # Tiempo maximo esperando
            sleep=sleep                  # Intervalo entre reintentos
        )

        acquired = False
        lock_wait_start = time.time()  # ✅ M3: Medir tiempo de espera para Prometheus
        try:
            # acquire() hace polling hasta blocking_timeout y retorna True/False
            acquired = await lock.acquire()
            lock_wait_elapsed = time.time() - lock_wait_start

            if not acquired:
                # No se pudo obtener el lock en el tiempo limite.
                # Registrar timeout en Prometheus antes de lanzar la excepcion.
                try:
                    from src.api.core.prometheus_metrics import (
                        kb_distributed_lock_acquisitions_total,
                        kb_distributed_lock_timeouts_total
                    )
                    kb_distributed_lock_acquisitions_total.labels(result="timeout").inc()
                    kb_distributed_lock_timeouts_total.inc()
                except ImportError:
                    pass

                raise DistributedLockError(
                    f"Could not acquire distributed lock '{lock_name}' "
                    f"within {blocking_timeout}s. Another instance may be processing "
                    f"this resource. Consider increasing blocking_timeout or checking "
                    f"for stuck processes."
                )

            # ✅ M3: Registrar adquisicion exitosa y tiempo de espera en Prometheus
            try:
                from src.api.core.prometheus_metrics import (
                    kb_distributed_lock_acquisitions_total,
                    kb_distributed_lock_wait_seconds
                )
                kb_distributed_lock_acquisitions_total.labels(result="acquired").inc()
                kb_distributed_lock_wait_seconds.observe(lock_wait_elapsed)
            except ImportError:
                pass

            logger.debug(
                "distributed_lock_acquired",
                lock_name=lock_name,
                timeout_seconds=timeout,
                blocking_timeout_seconds=blocking_timeout,
                wait_elapsed_ms=round(lock_wait_elapsed * 1000, 2)
            )

            # ── CEDER CONTROL AL BLOQUE `async with` ─────────────────────────
            yield lock

        finally:
            # ── LIBERAR EL LOCK siempre que lo hayamos adquirido ─────────────
            # Se ejecuta incluso si hay una excepcion dentro del bloque `with`.
            # Si el lock ya expiro (TTL alcanzado), release() falla silenciosamente.
            if acquired:
                try:
                    await lock.release()
                    logger.debug(
                        "distributed_lock_released",
                        lock_name=lock_name
                    )
                except Exception as release_error:
                    # El lock puede haber expirado por TTL antes de que lo liberemos.
                    # Esto es correcto por diseno: el TTL es el safety net.
                    logger.debug(
                        "distributed_lock_release_skipped",
                        lock_name=lock_name,
                        reason=str(release_error),
                        note="lock_may_have_expired_by_ttl_this_is_ok"
                    )

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
