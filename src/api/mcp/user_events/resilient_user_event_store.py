"""
UserEventStore mejorado con patrones de resiliencia:
- Circuit breaker para operaciones de almacenamiento
- Local cache para reducir carga en base de datos
- Bulk operations para eficiencia
- Estrategias de fallback y recovery
- Métricas detalladas de rendimiento

Este módulo implementa un almacén de eventos de usuario resiliente para
soportar personalización en tiempo real incluso durante fallos parciales.
"""

import asyncio
import logging
import time
import json
import hashlib
import os
from typing import Dict, List, Optional, Any, Union, Set
from datetime import datetime, timedelta
import random
import uuid
import redis.asyncio as aioredis

from cachetools import TTLCache, LRUCache

from ..client.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .event_schemas import (
    EventType, UserEvent, UserProfile, IntentData, ProductEventData,
    validate_event_data, create_event_id, calculate_user_activity_level
)

logger = logging.getLogger(__name__)

class StorageError(Exception):
    """Error en operaciones de almacenamiento"""
    pass

class UserEventStore:
    """
    Almacén de eventos de usuario con resiliencia para personalización.
    
    Características:
    - Almacenamiento de eventos en Redis
    - Caché local para perfiles de usuario frecuentes
    - Circuit breaker para proteger contra fallos de Redis
    - Operaciones bulk para rendimiento
    - Métricas de rendimiento detalladas
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        cache_ttl: int = 300,  # 5 min cache TTL
        enable_circuit_breaker: bool = True,
        cache_size: int = 1000,
        local_buffer_size: int = 200,
        flush_interval_seconds: int = 30,
        local_fallback_dir: Optional[str] = None
    ):
        """
        Inicializa el almacén de eventos de usuario.
        
        Args:
            redis_url: URL de conexión a Redis
            cache_ttl: Tiempo de vida de caché en segundos
            enable_circuit_breaker: Habilitar circuit breaker
            cache_size: Tamaño máximo de caché local
            local_buffer_size: Tamaño de buffer para operaciones bulk
            flush_interval_seconds: Intervalo para flush de buffer
            local_fallback_dir: Directorio para almacenamiento local de fallback
        """
        self.redis_url = redis_url
        self.redis = None  # Se inicializa en connect()
        self.connected = False
        
        # Configuración
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        self.local_buffer_size = local_buffer_size
        self.flush_interval_seconds = flush_interval_seconds
        self.local_fallback_dir = local_fallback_dir
        
        # Crear directorio de fallback si no existe
        if local_fallback_dir and not os.path.exists(local_fallback_dir):
            try:
                os.makedirs(local_fallback_dir)
                logger.info(f"Creado directorio fallback: {local_fallback_dir}")
            except Exception as e:
                logger.warning(f"No se pudo crear directorio fallback: {e}")
        
        # Caché local y buffers
        self.profile_cache = TTLCache(maxsize=cache_size, ttl=cache_ttl)
        self.events_buffer = []
        self.failed_events_buffer = []
        
        # Última operación de flush
        self.last_flush_time = time.time()
        
        # Lock para operaciones concurrentes
        self._buffer_lock = asyncio.Lock()
        
        # Circuit breakers para diferentes operaciones
        if enable_circuit_breaker:
            self.read_circuit_breaker = CircuitBreaker(
                name="event_store_read",
                config=CircuitBreakerConfig(
                    failure_threshold=3,
                    timeout_seconds=30,
                    success_threshold=2,
                    max_timeout=10
                ),
                fallback_function=self._read_fallback
            )
            
            self.write_circuit_breaker = CircuitBreaker(
                name="event_store_write",
                config=CircuitBreakerConfig(
                    failure_threshold=5,  # Más tolerante para escrituras
                    timeout_seconds=20,
                    success_threshold=3,
                    max_timeout=15
                ),
                fallback_function=self._write_fallback
            )
        else:
            self.read_circuit_breaker = None
            self.write_circuit_breaker = None
        
        # Métricas
        self.metrics = {
            "events_stored": 0,
            "events_buffered": 0,
            "events_failed": 0,
            "profiles_generated": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "read_errors": 0,
            "write_errors": 0,
            "redis_latency_ms": 0.0,
            "bulk_operations": 0,
            "fallbacks_used": 0,
            "circuit_breaker_triggers": 0,
            "recovery_operations": 0,
            "local_storage_operations": 0
        }
        
        # Iniciar tareas background
        self._flush_task = None
        self._recovery_task = None
        
        logger.info(f"UserEventStore inicializado con Redis en {redis_url}")
        logger.info(f"Circuit breaker habilitado: {enable_circuit_breaker}")
        logger.info(f"Caché local: tamaño={cache_size}, TTL={cache_ttl}s")
        logger.info(f"Buffer de eventos: tamaño={local_buffer_size}, flush cada {flush_interval_seconds}s")
    
    async def connect(self):
        """
        Conecta al almacén Redis y inicia tareas background.
        """
        try:
            self.redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            
            # Verificar conexión
            await self.redis.ping()
            self.connected = True
            
            # Iniciar tareas background
            self._start_background_tasks()
            
            # Intentar recuperar eventos fallidos almacenados localmente
            if self.local_fallback_dir:
                asyncio.create_task(self._recover_local_fallback_events())
            
            logger.info("Conectado a Redis exitosamente")
            return True
        except Exception as e:
            logger.error(f"Error al conectar a Redis: {e}")
            self.connected = False
            return False
    
    def _start_background_tasks(self):
        """Inicia tareas background para mantenimiento"""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._background_flush())
            
        if self._recovery_task is None or self._recovery_task.done():
            self._recovery_task = asyncio.create_task(self._background_recovery())
    
    async def close(self):
        """
        Cierra conexiones y realiza flush final de buffers.
        """
        # Cancelar tareas background
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        if self._recovery_task and not self._recovery_task.done():
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
        
        # Flush final de eventos pendientes
        if self.events_buffer:
            try:
                async with self._buffer_lock:
                    await self._flush_events_buffer()
            except Exception as e:
                logger.error(f"Error en flush final: {e}")
                
                # Si falla flush a Redis, intentar guardar localmente
                if self.local_fallback_dir:
                    try:
                        self._persist_events_to_local_disk(self.events_buffer)
                        logger.info(f"Eventos pendientes guardados localmente durante cierre: {len(self.events_buffer)}")
                    except Exception as disk_e:
                        logger.error(f"Error guardando eventos localmente durante cierre: {disk_e}")
        
        # Cerrar conexión Redis
        if self.redis:
            await self.redis.close()
            self.connected = False
            
        logger.info("UserEventStore cerrado correctamente")
    
    async def record_event(self, user_id: str, event_type: EventType, data: Dict[str, Any], **kwargs) -> bool:
        """
        Registra un evento de usuario con manejo de errores y buffering.
        
        Args:
            user_id: ID del usuario
            event_type: Tipo de evento
            data: Datos del evento
            **kwargs: Datos adicionales como session_id, market_id, etc.
            
        Returns:
            bool: True si el evento fue registrado o buffer, False en caso de error
        """
        try:
            # Validar datos
            validated_data = validate_event_data(event_type, data)
            
            # Crear objeto de evento
            event_id = create_event_id(user_id, event_type)
            timestamp = datetime.utcnow()
            
            # Extraer datos adicionales
            session_id = kwargs.get("session_id")
            market_id = kwargs.get("market_id")
            ip_address = kwargs.get("ip_address")
            user_agent = kwargs.get("user_agent")
            
            event = UserEvent(
                event_id=event_id,
                user_id=user_id,
                event_type=event_type,
                timestamp=timestamp,
                session_id=session_id,
                market_id=market_id,
                data=validated_data,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            # Agregar a buffer con lock para proteger operaciones concurrentes
            async with self._buffer_lock:
                self.events_buffer.append(event.dict())
                self.metrics["events_buffered"] += 1
                
                # Si el buffer alcanza el límite, hacer flush
                if len(self.events_buffer) >= self.local_buffer_size:
                    await self._flush_events_buffer()
                    
                # También flush si ha pasado demasiado tiempo desde el último
                elif time.time() - self.last_flush_time > self.flush_interval_seconds:
                    await self._flush_events_buffer()
            
            # Invalidar caché de perfil si existe
            cache_key = f"profile:{user_id}"
            if cache_key in self.profile_cache:
                # No eliminar, solo marcar como actualizado para regenerar en próxima consulta
                profile = self.profile_cache[cache_key]
                profile["needs_update"] = True
            
            return True
            
        except Exception as e:
            logger.error(f"Error al registrar evento: {e}")
            self.metrics["events_failed"] += 1
            
            # Intentar mantener el evento en buffer de fallidos
            try:
                event_dict = {
                    "user_id": user_id,
                    "event_type": event_type.value if isinstance(event_type, EventType) else event_type,
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat(),
                    **kwargs
                }
                
                async with self._buffer_lock:
                    self.failed_events_buffer.append(event_dict)
                    
                    # Limitar buffer de fallidos
                    if len(self.failed_events_buffer) > self.local_buffer_size * 2:
                        self.failed_events_buffer = self.failed_events_buffer[-self.local_buffer_size:]
            except Exception as buffer_e:
                logger.error(f"Error al guardar evento en buffer de fallidos: {buffer_e}")
            
            return False
    
    async def record_conversation_intent(self, user_id: str, intent_data: Dict[str, Any]) -> bool:
        """
        Registra intención conversacional del usuario.
        
        Args:
            user_id: ID del usuario
            intent_data: Datos de intención conversacional
            
        Returns:
            bool: True si se registró correctamente
        """
        try:
            # Crear objeto IntentData para validación
            validated_intent = IntentData(**intent_data)
            
            # Registrar como evento
            return await self.record_event(
                user_id=user_id,
                event_type=EventType.CONVERSATION_INTENT,
                data=validated_intent.dict(),
                market_id=intent_data.get("market_id")
            )
        except Exception as e:
            logger.error(f"Error al registrar intención: {e}")
            return False
    
    async def record_mcp_event(self, user_id: str, event_data: Dict[str, Any]) -> bool:
        """
        Registra evento MCP genérico.
        
        Args:
            user_id: ID del usuario
            event_data: Datos del evento
            
        Returns:
            bool: True si se registró correctamente
        """
        session_id = event_data.pop("session_id", None)
        market_id = event_data.pop("market_id", None)
        
        return await self.record_event(
            user_id=user_id,
            event_type=EventType.MCP_EVENT,
            data=event_data,
            session_id=session_id,
            market_id=market_id
        )
    
    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Obtiene perfil de usuario con caché local y circuit breaker.
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Perfil de usuario o perfil vacío en caso de error
        """
        # Verificar caché local primero
        cache_key = f"profile:{user_id}"
        
        if cache_key in self.profile_cache:
            profile = self.profile_cache[cache_key]
            
            # Verificar si necesita actualización
            if profile.get("needs_update", False):
                # Caché existe pero está marcado para actualización
                logger.debug(f"Perfil en caché para {user_id} marcado para actualización")
            else:
                # Caché válido
                self.metrics["cache_hits"] += 1
                return profile
        
        self.metrics["cache_misses"] += 1
        
        try:
            # Usar circuit breaker para proteger la operación
            if self.read_circuit_breaker:
                try:
                    profile = await self.read_circuit_breaker.call(
                        self._fetch_user_profile,
                        user_id
                    )
                except Exception as e:
                    logger.warning(f"Circuit breaker activado para lectura de perfil: {e}")
                    self.metrics["circuit_breaker_triggers"] += 1
                    return await self._read_fallback(user_id)
            else:
                # Sin circuit breaker
                profile = await self._fetch_user_profile(user_id)
            
            # Cachear resultado
            self.profile_cache[cache_key] = profile
            return profile
            
        except Exception as e:
            logger.error(f"Error al obtener perfil de usuario {user_id}: {e}")
            self.metrics["read_errors"] += 1
            
            # Perfil vacío como fallback
            return self._create_empty_profile(user_id)
    
    async def _fetch_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Obtiene perfil desde Redis y lo genera si no existe.
        Protegido por circuit breaker.
        """
        if not self.connected or not self.redis:
            raise StorageError("Redis no está conectado")
        
        start_time = time.time()
        profile_key = f"user:profile:{user_id}"
        
        try:
            # Verificar si existe perfil
            profile_exists = await self.redis.exists(profile_key)
            
            if profile_exists:
                # Obtener perfil existente
                profile_json = await self.redis.get(profile_key)
                profile = json.loads(profile_json)
                
                # Actualizar métrica de latencia
                latency_ms = (time.time() - start_time) * 1000
                self._update_latency_metric(latency_ms)
                
                return profile
            else:
                # Generar perfil desde eventos
                profile = await self._generate_user_profile(user_id)
                
                # Guardar perfil generado
                if profile:
                    await self.redis.set(
                        profile_key,
                        json.dumps(profile),
                        ex=86400  # 24 horas
                    )
                    
                    self.metrics["profiles_generated"] += 1
                    
                # Actualizar métrica de latencia
                latency_ms = (time.time() - start_time) * 1000
                self._update_latency_metric(latency_ms)
                
                return profile
        except Exception as e:
            # Actualizar métrica de latencia en caso de error
            latency_ms = (time.time() - start_time) * 1000
            self._update_latency_metric(latency_ms)
            
            logger.error(f"Error en operación Redis para perfil {user_id}: {e}")
            raise StorageError(f"Error al obtener perfil: {str(e)}")
    
    async def _generate_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Genera perfil de usuario a partir de sus eventos.
        """
        if not self.connected or not self.redis:
            raise StorageError("Redis no está conectado")
        
        # Obtener eventos del usuario
        events_key = f"user:events:{user_id}"
        event_ids = await self.redis.lrange(events_key, 0, -1)
        
        if not event_ids:
            # Sin eventos, crear perfil vacío
            return self._create_empty_profile(user_id)
        
        # Obtener datos de los eventos
        all_events = []
        pipe = self.redis.pipeline()
        
        for event_id in event_ids:
            pipe.get(f"event:{event_id}")
        
        event_jsons = await pipe.execute()
        
        for event_json in event_jsons:
            if event_json:
                try:
                    event = json.loads(event_json)
                    all_events.append(event)
                except (json.JSONDecodeError, TypeError):
                    continue
        
        # Analizar eventos y construir perfil
        intent_history = []
        category_affinity = {}
        search_patterns = []
        session_count = 0
        market_preferences = {}
        purchase_history = []
        session_ids = set()
        
        # Calcular días activos
        timestamps = [datetime.fromisoformat(e["timestamp"]) for e in all_events if "timestamp" in e]
        first_activity = min(timestamps) if timestamps else datetime.utcnow()
        last_activity = max(timestamps) if timestamps else datetime.utcnow()
        days_active = (last_activity - first_activity).days + 1
        
        # Procesar eventos
        for event in all_events:
            event_type = event.get("event_type")
            data = event.get("data", {})
            
            # Rastrear sesiones únicas
            if "session_id" in event and event["session_id"]:
                session_ids.add(event["session_id"])
            
            # Rastrear preferencias de mercado
            if "market_id" in event and event["market_id"]:
                market_id = event["market_id"]
                market_preferences[market_id] = market_preferences.get(market_id, 0) + 1
            
            # Procesar según tipo de evento
            if event_type == EventType.CONVERSATION_INTENT.value:
                # Guardar intenciones únicas
                intent_type = data.get("type")
                if intent_type and len(intent_history) < 10:  # Limitar a últimos 10
                    intent_history.append(data)
            
            elif event_type == EventType.PRODUCT_VIEW.value:
                # Actualizar afinidad de categoría
                category = data.get("product_category")
                if category:
                    category_affinity[category] = category_affinity.get(category, 0) + 1
            
            elif event_type == EventType.PRODUCT_SEARCH.value:
                # Guardar patrones de búsqueda
                query = data.get("query")
                if query and len(search_patterns) < 20:  # Limitar a últimos 20
                    search_patterns.append(query)
            
            elif event_type == EventType.PURCHASE.value:
                # Guardar historial de compras
                if len(purchase_history) < 10:  # Limitar a últimas 10
                    purchase_history.append(data)
        
        # Calcular afinidad normalizada (0-1)
        total_category_views = sum(category_affinity.values())
        if total_category_views > 0:
            for category in category_affinity:
                category_affinity[category] = round(category_affinity[category] / total_category_views, 3)
        
        # Crear perfil completo
        session_count = len(session_ids)
        activity_level = calculate_user_activity_level(len(all_events), session_count, days_active)
        
        profile = {
            "user_id": user_id,
            "total_events": len(all_events),
            "last_activity": last_activity.isoformat(),
            "first_activity": first_activity.isoformat(),
            "intent_history": intent_history,
            "category_affinity": category_affinity,
            "search_patterns": search_patterns,
            "session_count": session_count,
            "market_preferences": market_preferences,
            "purchase_history": purchase_history,
            "days_active": days_active,
            "activity_level": activity_level,
            "generation_timestamp": datetime.utcnow().isoformat(),
            "source": "generated"
        }
        
        return profile
    
    def _create_empty_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Crea perfil vacío para nuevo usuario o fallback.
        """
        now = datetime.utcnow()
        return {
            "user_id": user_id,
            "total_events": 0,
            "last_activity": now.isoformat(),
            "first_activity": now.isoformat(),
            "intent_history": [],
            "category_affinity": {},
            "search_patterns": [],
            "session_count": 0,
            "market_preferences": {},
            "purchase_history": [],
            "days_active": 0,
            "activity_level": "new",
            "generation_timestamp": now.isoformat(),
            "source": "fallback" if self.connected else "offline"
        }
    
    async def _flush_events_buffer(self) -> bool:
        """
        Persiste eventos en buffer a Redis usando operación bulk.
        """
        if not self.events_buffer:
            return True
        
        if not self.connected or not self.redis:
            logger.warning("Intentando flush de eventos sin conexión a Redis")
            if self.local_fallback_dir:
                try:
                    self._persist_events_to_local_disk(self.events_buffer)
                    logger.info(f"Eventos guardados localmente al no tener conexión: {len(self.events_buffer)}")
                    self.events_buffer = []  # Limpiar buffer
                    self.last_flush_time = time.time()
                    return True
                except Exception as e:
                    logger.error(f"Error al guardar eventos localmente: {e}")
            return False
        
        # Tomar snapshot de buffer actual
        events_to_flush = self.events_buffer.copy()
        self.events_buffer = []
        self.last_flush_time = time.time()
        
        try:
            # Usar circuit breaker para proteger escritura
            if self.write_circuit_breaker:
                try:
                    result = await self.write_circuit_breaker.call(
                        self._persist_events_batch,
                        events_to_flush
                    )
                    return result
                except Exception as e:
                    logger.warning(f"Circuit breaker activado para escritura: {e}")
                    self.metrics["circuit_breaker_triggers"] += 1
                    
                    # El fallback maneja los eventos
                    await self._write_fallback(events_to_flush)
                    return False
            else:
                # Sin circuit breaker
                return await self._persist_events_batch(events_to_flush)
                
        except Exception as e:
            logger.error(f"Error en flush de eventos: {e}")
            
            # Restaurar eventos no guardados al buffer
            self.failed_events_buffer.extend(events_to_flush)
            self.metrics["write_errors"] += 1
            
            return False
    
    async def _persist_events_batch(self, events: List[Dict]) -> bool:
        """
        Persiste batch de eventos en Redis con operación pipeline.
        """
        if not events:
            return True
        
        if not self.connected or not self.redis:
            raise StorageError("Redis no está conectado")
        
        start_time = time.time()
        pipe = self.redis.pipeline()
        
        try:
            # Agrupar eventos por usuario
            user_events = {}
            
            for event in events:
                user_id = event["user_id"]
                if user_id not in user_events:
                    user_events[user_id] = []
                user_events[user_id].append(event)
            
            # Procesar eventos agrupados por usuario
            for user_id, user_events_list in user_events.items():
                user_events_key = f"user:events:{user_id}"
                
                for event in user_events_list:
                    event_id = event["event_id"]
                    event_key = f"event:{event_id}"
                    
                    # Guardar evento
                    pipe.set(event_key, json.dumps(event), ex=2592000)  # 30 días TTL
                    
                    # Agregar a lista de eventos del usuario
                    pipe.lpush(user_events_key, event_id)
                    
                # Trimear lista de eventos para limitar tamaño
                pipe.ltrim(user_events_key, 0, 999)  # Mantener últimos 1000
                
                # Set TTL para la lista de eventos
                pipe.expire(user_events_key, 2592000)  # 30 días
                
                # Invalidar caché de perfil
                profile_key = f"user:profile:{user_id}"
                pipe.delete(profile_key)
            
            # Ejecutar pipeline
            await pipe.execute()
            
            # Actualizar métricas
            self.metrics["events_stored"] += len(events)
            self.metrics["bulk_operations"] += 1
            
            # Actualizar métrica de latencia
            latency_ms = (time.time() - start_time) * 1000
            self._update_latency_metric(latency_ms)
            
            return True
            
        except Exception as e:
            # Actualizar métrica de latencia en caso de error
            latency_ms = (time.time() - start_time) * 1000
            self._update_latency_metric(latency_ms)
            
            logger.error(f"Error en bulk persist: {e}")
            raise StorageError(f"Error al persistir batch de eventos: {str(e)}")
    
    async def _background_flush(self):
        """
        Tarea background para flush periódico de buffer de eventos.
        """
        while True:
            try:
                # Esperar para próximo flush
                await asyncio.sleep(self.flush_interval_seconds)
                
                # Verificar si hay eventos en buffer
                if self.events_buffer:
                    async with self._buffer_lock:
                        await self._flush_events_buffer()
                        
            except asyncio.CancelledError:
                # Cancelación limpia de tarea
                break
                
            except Exception as e:
                logger.error(f"Error en tarea background de flush: {e}")
                # Continuar tarea a pesar de error
                await asyncio.sleep(5)  # Esperar antes de reintentar
    
    async def _background_recovery(self):
        """
        Tarea background para recuperación de eventos fallidos.
        """
        while True:
            try:
                # Esperar para próximo intento de recovery
                await asyncio.sleep(60)  # 1 minuto entre intentos
                
                # Solo intentar recovery si estamos conectados
                if not self.connected or not self.redis:
                    continue
                    
                # Verificar si hay eventos fallidos para recuperar
                if self.failed_events_buffer:
                    async with self._buffer_lock:
                        # Tomar solo un batch limitado para recuperación
                        recovery_batch = self.failed_events_buffer[:50]
                        
                        if recovery_batch:
                            logger.info(f"Intentando recuperar {len(recovery_batch)} eventos fallidos")
                            
                            try:
                                # Intentar persistir batch
                                if await self._persist_events_batch(recovery_batch):
                                    # Éxito, remover eventos recuperados
                                    self.failed_events_buffer = self.failed_events_buffer[50:]
                                    self.metrics["recovery_operations"] += 1
                                    logger.info(f"Recuperados {len(recovery_batch)} eventos exitosamente")
                            except Exception as e:
                                logger.warning(f"Fallo en recuperación de eventos: {e}")
                                # No remover eventos, se intentará en próximo ciclo
                
                # También verificar eventos almacenados en disco
                if self.local_fallback_dir:
                    await self._recover_local_fallback_events()
                        
            except asyncio.CancelledError:
                # Cancelación limpia de tarea
                break
                
            except Exception as e:
                logger.error(f"Error en tarea background de recovery: {e}")
                # Continuar tarea a pesar de error
                await asyncio.sleep(30)  # Esperar antes de reintentar
    
    async def _read_fallback(self, user_id: str) -> Dict[str, Any]:
        """
        Función de fallback para lecturas cuando circuit breaker está abierto.
        """
        logger.info(f"Usando fallback para lectura de perfil de usuario {user_id}")
        self.metrics["fallbacks_used"] += 1
        
        # Primero verificar caché expirada
        cache_key = f"profile:{user_id}"
        
        # Buscar en caché expirada (si está disponible)
        for key, value in self.profile_cache.items():
            if key == cache_key:
                # Encontramos una entrada en caché, aunque podría estar expirada
                logger.info(f"Usando caché expirada como fallback para usuario {user_id}")
                value["cached"] = True
                value["fallback"] = "expired_cache"
                return value
        
        # Si no hay caché, generar perfil local básico
        # Este perfil tendrá information limitada pero permitirá
        # que el sistema siga funcionando
        local_profile = self._create_empty_profile(user_id)
        local_profile["fallback"] = "generated_empty"
        
        return local_profile
    
    async def _write_fallback(self, events: List[Dict]) -> bool:
        """
        Función de fallback para escrituras cuando circuit breaker está abierto.
        """
        logger.info(f"Usando fallback para escritura de {len(events)} eventos")
        self.metrics["fallbacks_used"] += 1
        
        # Agregar eventos al buffer de fallidos para retry futuro
        self.failed_events_buffer.extend(events)
        
        # Limitar tamaño del buffer
        max_buffer_size = self.local_buffer_size * 4  # Mayor buffer para fallidos
        if len(self.failed_events_buffer) > max_buffer_size:
            # Conservar eventos más recientes
            self.failed_events_buffer = self.failed_events_buffer[-max_buffer_size:]
            
        # Intentar guardar en disco local si es posible
        if self.local_fallback_dir:
            try:
                self._persist_events_to_local_disk(events)
                logger.info(f"Eventos persistidos a disco local como fallback: {len(events)}")
                return True
            except Exception as e:
                logger.warning(f"No se pudo persistir eventos a disco local: {e}")
        
        return False
    
    def _persist_events_to_local_disk(self, events: List[Dict]) -> bool:
        """
        Persistir eventos a disco local como medida de fallback.
        """
        if not self.local_fallback_dir:
            return False
            
        # Generar nombre de archivo con timestamp
        timestamp = int(time.time())
        filename = f"events_fallback_{timestamp}_{uuid.uuid4().hex[:8]}.json"
        filepath = os.path.join(self.local_fallback_dir, filename)
        
        # Guardar eventos en archivo JSON
        with open(filepath, 'w') as f:
            json.dump({"events": events, "timestamp": timestamp}, f)
        
        self.metrics["local_storage_operations"] += 1
        return True
    
    async def _recover_local_fallback_events(self) -> bool:
        """
        Recupera eventos almacenados localmente durante fallos previos.
        """
        if not self.local_fallback_dir or not os.path.exists(self.local_fallback_dir):
            return False
            
        if not self.connected or not self.redis:
            logger.debug("No se pueden recuperar eventos locales sin conexión a Redis")
            return False
            
        # Verificar si hay archivos de fallback
        try:
            fallback_files = [f for f in os.listdir(self.local_fallback_dir) 
                             if f.startswith("events_fallback_") and f.endswith(".json")]
            
            if not fallback_files:
                return False
                
            logger.info(f"Encontrados {len(fallback_files)} archivos de fallback para recuperación")
            
            # Procesar máximo 3 archivos por iteración para evitar sobrecarga
            files_to_process = sorted(fallback_files)[:3]
            
            for filename in files_to_process:
                filepath = os.path.join(self.local_fallback_dir, filename)
                
                try:
                    # Leer eventos desde archivo
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        events = data.get("events", [])
                    
                    if not events:
                        # Archivo vacío, eliminar
                        os.remove(filepath)
                        continue
                    
                    # Intentar persistir eventos en Redis
                    logger.info(f"Recuperando {len(events)} eventos desde {filename}")
                    
                    if await self._persist_events_batch(events):
                        # Éxito, eliminar archivo
                        os.remove(filepath)
                        self.metrics["recovery_operations"] += 1
                        logger.info(f"Recuperación exitosa desde {filename}")
                    else:
                        # Fallo, mantener archivo para próximo intento
                        logger.warning(f"Fallo en recuperación desde {filename}")
                
                except Exception as e:
                    logger.error(f"Error procesando archivo de fallback {filename}: {e}")
                    
                    # Si hay error en formato, mover o eliminar archivo para evitar 
                    # intentos continuos con archivo corrupto
                    try:
                        corrupted_dir = os.path.join(self.local_fallback_dir, "corrupted")
                        if not os.path.exists(corrupted_dir):
                            os.makedirs(corrupted_dir)
                            
                        os.rename(filepath, os.path.join(corrupted_dir, filename))
                        logger.info(f"Archivo corrupto movido a {corrupted_dir}")
                    except Exception:
                        # Si no se puede mover, intentar eliminar
                        try:
                            os.remove(filepath)
                            logger.info(f"Archivo corrupto eliminado: {filename}")
                        except Exception:
                            pass
            
            return True
            
        except Exception as e:
            logger.error(f"Error en recuperación de archivos locales: {e}")
            return False
    
    def _update_latency_metric(self, latency_ms: float):
        """
        Actualiza métrica de latencia promedio con decaimiento exponencial.
        """
        if self.metrics["redis_latency_ms"] == 0:
            self.metrics["redis_latency_ms"] = latency_ms
        else:
            # Actualizar promedio con factor de decaimiento 0.9
            self.metrics["redis_latency_ms"] = (
                self.metrics["redis_latency_ms"] * 0.9 + latency_ms * 0.1
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas detalladas del store.
        """
        # Estadísticas básicas
        stats = {
            **self.metrics,
            "connected": self.connected,
            "cache_size": len(self.profile_cache),
            "events_buffer_size": len(self.events_buffer),
            "failed_buffer_size": len(self.failed_events_buffer),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Estadísticas de circuit breaker
        if self.read_circuit_breaker:
            stats["read_circuit_breaker"] = self.read_circuit_breaker.get_stats()
            
        if self.write_circuit_breaker:
            stats["write_circuit_breaker"] = self.write_circuit_breaker.get_stats()
            
        # Estadísticas de Redis si está conectado
        if self.connected and self.redis:
            try:
                # Obtener info básica de Redis
                info = await self.redis.info()
                memory_info = info.get("memory", {})
                
                stats["redis_info"] = {
                    "used_memory_human": memory_info.get("used_memory_human", "unknown"),
                    "used_memory_peak_human": memory_info.get("used_memory_peak_human", "unknown"),
                    "maxmemory_human": memory_info.get("maxmemory_human", "unknown"),
                    "maxmemory_policy": memory_info.get("maxmemory_policy", "unknown"),
                    "connected_clients": info.get("clients", {}).get("connected_clients", 0),
                    "uptime_in_seconds": info.get("server", {}).get("uptime_in_seconds", 0)
                }
            except Exception as e:
                logger.warning(f"Error obteniendo estadísticas de Redis: {e}")
                stats["redis_info"] = {"error": str(e)}
        
        return stats
    
    async def health_check(self) -> Dict[str, str]:
        """
        Realiza un health check simple.
        """
        if not self.connected or not self.redis:
            return {
                "status": "unhealthy",
                "reason": "Redis disconnected",
                "can_read": "false",
                "can_write": "false"
            }
            
        try:
            # Verificar conexión a Redis
            await self.redis.ping()
            
            # Verificar circuit breakers
            read_healthy = True
            write_healthy = True
            
            if self.read_circuit_breaker and self.read_circuit_breaker.is_open:
                read_healthy = False
                
            if self.write_circuit_breaker and self.write_circuit_breaker.is_open:
                write_healthy = False
                
            if read_healthy and write_healthy:
                return {
                    "status": "healthy",
                    "can_read": "true",
                    "can_write": "true"
                }
            elif read_healthy:
                return {
                    "status": "degraded",
                    "reason": "Write circuit breaker open",
                    "can_read": "true",
                    "can_write": "false"
                }
            elif write_healthy:
                return {
                    "status": "degraded",
                    "reason": "Read circuit breaker open",
                    "can_read": "false",
                    "can_write": "true"
                }
            else:
                return {
                    "status": "unhealthy",
                    "reason": "All circuit breakers open",
                    "can_read": "false",
                    "can_write": "false"
                }
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "reason": str(e),
                "can_read": "false",
                "can_write": "false"
            }
    
    async def reset_circuit_breakers(self):
        """
        Reset manual de circuit breakers.
        """
        if self.read_circuit_breaker:
            await self.read_circuit_breaker.reset()
            logger.info("Read circuit breaker reset")
            
        if self.write_circuit_breaker:
            await self.write_circuit_breaker.reset()
            logger.info("Write circuit breaker reset")
    
    def clear_cache(self):
        """
        Limpia caché local.
        """
        self.profile_cache.clear()
        logger.info("Caché local limpiada")