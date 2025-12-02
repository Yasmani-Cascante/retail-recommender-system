"""
Test Suite for RedisService - Enterprise Redis Layer
====================================================

Comprehensive tests para src/api/core/redis_service.py validando:
- Singleton pattern correctness
- Connection management
- CRUD operations (GET, SET, DELETE)
- JSON serialization/deserialization
- Error handling y graceful degradation
- Observability (stats, health checks)

Author: Senior Architecture Team
Date: 30 Noviembre 2025
Version: 1.0.0 - Fase 3A Day 1
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any
import json

# Module under test
from src.api.core.redis_service import (
    RedisService,
    RedisServiceError,
    get_redis_service,
    get_redis_health,
    get_redis_stats
)

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_redis_client():
    """
    Mock del cliente Redis con todas las operaciones async.
    
    Simula comportamiento de redis.asyncio client con:
    - Operaciones CRUD (get, set, setex, delete)
    - Connection management (ping)
    - Estado conectado
    """
    mock = AsyncMock()
    
    # Operaciones básicas
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.ping = AsyncMock(return_value=True)
    
    # Connection state
    mock.connected = True
    
    return mock


@pytest.fixture
def mock_optimized_client():
    """
    Mock de create_optimized_redis_client para tests de inicialización.
    
    Returns un mock del cliente Redis ya configurado.
    """
    with patch('src.api.core.redis_service.create_optimized_redis_client') as mock:
        client = AsyncMock()
        client.ping = AsyncMock(return_value=True)
        client.get = AsyncMock(return_value=None)
        client.set = AsyncMock(return_value=True)
        client.setex = AsyncMock(return_value=True)
        client.delete = AsyncMock(return_value=1)
        
        mock.return_value = client
        yield mock


@pytest.fixture
async def redis_service_instance(mock_optimized_client):
    """
    Fixture que proporciona una instancia de RedisService para tests.
    
    IMPORTANTE: Limpia el singleton después de cada test para evitar
    interferencia entre tests.
    """
    # Limpiar singleton antes del test
    RedisService._instance = None
    
    # Crear nueva instancia
    service = await RedisService.get_instance()
    
    yield service
    
    # Cleanup después del test
    RedisService._instance = None
    service._client = None
    service._connected = False


@pytest.fixture
def sample_data():
    """Datos de ejemplo para tests"""
    return {
        "string_value": "test_value_123",
        "json_data": {"id": "123", "name": "Test Product", "price": 99.99},
        "ttl": 3600,
        "key": "test:key:123"
    }


# ============================================================================
# TEST CLASS 1: SINGLETON PATTERN
# ============================================================================

class TestRedisServiceSingleton:
    """
    Tests del patrón Singleton de RedisService.
    
    Verifica que:
    - Solo existe una instancia
    - Thread-safe con acceso concurrente
    - Lazy initialization funciona correctamente
    """
    
    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self, mock_optimized_client):
        """
        Verifica que get_instance() siempre retorna la misma instancia.
        
        Given: Un RedisService no inicializado
        When: Se llama get_instance() múltiples veces
        Then: Todas las llamadas retornan la misma instancia
        """
        # Limpiar cualquier instancia previa
        RedisService._instance = None
        
        # Obtener instancias múltiples veces
        instance1 = await RedisService.get_instance()
        instance2 = await RedisService.get_instance()
        instance3 = await RedisService.get_instance()
        
        # Verificar que todas son la misma instancia
        assert instance1 is instance2, "Instance 1 and 2 should be identical"
        assert instance2 is instance3, "Instance 2 and 3 should be identical"
        assert instance1 is instance3, "Instance 1 and 3 should be identical"
        
        # Verificar que create_optimized_redis_client solo se llamó una vez
        assert mock_optimized_client.call_count == 1, \
            "Optimized client should only be created once"
        
        # Cleanup
        RedisService._instance = None
    
    @pytest.mark.asyncio
    async def test_singleton_thread_safe_with_concurrent_access(self, mock_optimized_client):
        """
        Verifica que el singleton es thread-safe con acceso concurrente.
        
        Given: Múltiples coroutines intentando obtener la instancia simultáneamente
        When: Se ejecutan concurrentemente
        Then: Todas obtienen la misma instancia y el cliente se crea solo una vez
        """
        # Limpiar cualquier instancia previa
        RedisService._instance = None
        
        # Simular 10 requests concurrentes
        async def get_instance_task():
            return await RedisService.get_instance()
        
        # Ejecutar 10 tasks concurrentes
        instances = await asyncio.gather(*[get_instance_task() for _ in range(10)])
        
        # Verificar que todas son la misma instancia
        first_instance = instances[0]
        for instance in instances[1:]:
            assert instance is first_instance, \
                "All concurrent accesses should return the same instance"
        
        # Verificar que create_optimized_redis_client solo se llamó una vez
        # (esto valida el async lock)
        assert mock_optimized_client.call_count == 1, \
            "Client should only be created once despite concurrent access"
        
        # Cleanup
        RedisService._instance = None
    
    @pytest.mark.asyncio
    async def test_get_instance_initializes_connection(self, mock_optimized_client):
        """
        Verifica que get_instance() inicializa la conexión correctamente.
        
        Given: Un RedisService no inicializado
        When: Se llama get_instance()
        Then: Se crea el cliente optimizado y se verifica la conexión con ping
        """
        # Limpiar cualquier instancia previa
        RedisService._instance = None
        
        # Obtener instancia
        instance = await RedisService.get_instance()
        
        # Verificar que se creó el cliente
        mock_optimized_client.assert_called_once()
        
        # Verificar que se llamó ping para verificar conexión
        mock_client = mock_optimized_client.return_value
        mock_client.ping.assert_called_once()
        
        # Verificar estado de la instancia
        assert instance._connected is True, "Service should be marked as connected"
        assert instance._client is not None, "Client should be initialized"
        assert instance._connection_attempts == 1, "Should have 1 connection attempt"
        
        # Cleanup
        RedisService._instance = None


# ============================================================================
# TEST CLASS 2: INITIALIZATION & CONNECTION
# ============================================================================

class TestRedisServiceInitialization:
    """
    Tests de inicialización y gestión de conexión.
    
    Verifica:
    - Inicialización exitosa
    - Graceful degradation en fallos
    - Connection verification
    """
    
    @pytest.mark.asyncio
    async def test_initialization_with_successful_connection(self, mock_optimized_client):
        """
        Verifica inicialización exitosa con conexión Redis disponible.
        
        Given: Redis está disponible y responde a ping
        When: Se inicializa RedisService
        Then: El servicio se marca como conectado y funcional
        """
        # Limpiar instancia previa
        RedisService._instance = None
        
        # Configurar mock para conexión exitosa
        mock_client = mock_optimized_client.return_value
        mock_client.ping = AsyncMock(return_value=True)
        
        # Inicializar servicio
        service = await RedisService.get_instance()
        
        # Verificar estado post-inicialización
        assert service._connected is True, "Should be marked as connected"
        assert service._client is not None, "Client should be initialized"
        assert service._connection_attempts == 1, "Should have 1 connection attempt"
        
        # Verificar que se ejecutó el flujo correcto
        mock_optimized_client.assert_called_once()
        mock_client.ping.assert_called_once()
        
        # Cleanup
        RedisService._instance = None
    
    @pytest.mark.asyncio
    async def test_initialization_with_failed_connection_graceful_degradation(
        self, 
        mock_optimized_client
    ):
        """
        Verifica graceful degradation cuando Redis no está disponible.
        
        Given: Redis no está disponible (ping falla)
        When: Se inicializa RedisService
        Then: El servicio se degrada gracefully sin crash
        """
        # Limpiar instancia previa
        RedisService._instance = None
        
        # Configurar mock para simular fallo de conexión
        mock_optimized_client.side_effect = Exception("Connection refused")
        
        # Inicializar servicio (no debe lanzar excepción)
        service = await RedisService.get_instance()
        
        # Verificar graceful degradation
        assert service._connected is False, "Should be marked as disconnected"
        assert service._client is None, "Client should be None after failure"
        
        # El servicio debe estar disponible pero en modo degradado
        assert service is not None, "Service should exist even with failed connection"
        
        # Cleanup
        RedisService._instance = None
    
    @pytest.mark.asyncio
    async def test_ensure_connection_verifies_client_availability(
        self,
        redis_service_instance,
        mock_optimized_client
    ):
        """
        Verifica que _ensure_connection() valida disponibilidad del cliente.
        
        Given: Un RedisService inicializado
        When: Se llama _ensure_connection()
        Then: Se verifica la conexión con ping
        """
        mock_client = mock_optimized_client.return_value
        mock_client.ping = AsyncMock(return_value=True)
        
        # Llamar ensure_connection
        result = await redis_service_instance._ensure_connection()
        
        # Verificar resultado
        assert result is True, "Should return True when client is available"
        mock_client.ping.assert_called()
        
        # Verificar estado interno
        assert redis_service_instance._connected is True


# ============================================================================
# TEST CLASS 3: CRUD OPERATIONS
# ============================================================================

class TestRedisServiceOperations:
    """
    Tests de operaciones CRUD básicas.
    
    Verifica:
    - GET operation
    - SET operation (con y sin TTL)
    - DELETE operation
    - Stats tracking (cache hits/misses)
    """
    
    @pytest.mark.asyncio
    async def test_get_operation_success(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica operación GET exitosa.
        
        Given: Un valor existe en Redis
        When: Se ejecuta get(key)
        Then: Se retorna el valor correcto
        """
        # Configurar mock para retornar valor
        mock_client = mock_optimized_client.return_value
        mock_client.get = AsyncMock(return_value=sample_data["string_value"])
        
        # Ejecutar GET
        result = await redis_service_instance.get(sample_data["key"])
        
        # Verificar resultado
        assert result == sample_data["string_value"], "Should return the stored value"
        
        # Verificar que se llamó al cliente con la key correcta
        mock_client.get.assert_called_once_with(sample_data["key"])
        
        # Verificar stats
        stats = redis_service_instance.get_stats()
        assert stats["operations_total"] >= 1, "Should increment operations counter"
        assert stats["operations_successful"] >= 1, "Should increment successful operations"
    
    @pytest.mark.asyncio
    async def test_get_operation_cache_hit_increments_stats(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica que cache hit incrementa stats correctamente.
        
        Given: Un valor existe en Redis (cache hit)
        When: Se ejecuta get(key)
        Then: Se incrementa cache_hits en stats
        """
        # Configurar mock para cache HIT
        mock_client = mock_optimized_client.return_value
        mock_client.get = AsyncMock(return_value=sample_data["string_value"])
        
        # Reset stats para medición limpia
        redis_service_instance.reset_stats()
        
        # Ejecutar GET
        await redis_service_instance.get(sample_data["key"])
        
        # Verificar stats de cache hit
        stats = redis_service_instance.get_stats()
        assert stats["cache_hits"] == 1, "Should have 1 cache hit"
        assert stats["cache_misses"] == 0, "Should have 0 cache misses"
    
    @pytest.mark.asyncio
    async def test_get_operation_cache_miss_increments_stats(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica que cache miss incrementa stats correctamente.
        
        Given: Un valor NO existe en Redis (cache miss)
        When: Se ejecuta get(key)
        Then: Se incrementa cache_misses en stats
        """
        # Configurar mock para cache MISS
        mock_client = mock_optimized_client.return_value
        mock_client.get = AsyncMock(return_value=None)
        
        # Reset stats para medición limpia
        redis_service_instance.reset_stats()
        
        # Ejecutar GET
        result = await redis_service_instance.get(sample_data["key"])
        
        # Verificar resultado
        assert result is None, "Should return None for cache miss"
        
        # Verificar stats de cache miss
        stats = redis_service_instance.get_stats()
        assert stats["cache_hits"] == 0, "Should have 0 cache hits"
        assert stats["cache_misses"] == 1, "Should have 1 cache miss"
    
    @pytest.mark.asyncio
    async def test_set_operation_success(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica operación SET exitosa sin TTL.
        
        Given: Un RedisService conectado
        When: Se ejecuta set(key, value)
        Then: El valor se guarda exitosamente
        """
        # Configurar mock
        mock_client = mock_optimized_client.return_value
        mock_client.set = AsyncMock(return_value=True)
        
        # Ejecutar SET
        result = await redis_service_instance.set(
            sample_data["key"],
            sample_data["string_value"]
        )
        
        # Verificar resultado
        assert result is True, "SET operation should succeed"
        
        # Verificar llamada al cliente
        mock_client.set.assert_called_once_with(
            sample_data["key"],
            sample_data["string_value"]
        )
        
        # Verificar stats
        stats = redis_service_instance.get_stats()
        assert stats["operations_successful"] >= 1, "Should increment successful operations"
    
    @pytest.mark.asyncio
    async def test_set_operation_with_ttl(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica operación SET con TTL.
        
        Given: Un RedisService conectado
        When: Se ejecuta set(key, value, ttl)
        Then: Se usa SETEX con el TTL especificado
        """
        # Configurar mock
        mock_client = mock_optimized_client.return_value
        mock_client.setex = AsyncMock(return_value=True)
        
        # Ejecutar SET con TTL
        result = await redis_service_instance.set(
            sample_data["key"],
            sample_data["string_value"],
            ttl=sample_data["ttl"]
        )
        
        # Verificar resultado
        assert result is True, "SET with TTL should succeed"
        
        # Verificar que se usó SETEX (no SET)
        mock_client.setex.assert_called_once_with(
            sample_data["key"],
            sample_data["ttl"],
            sample_data["string_value"]
        )
        
        # Verificar que SET normal NO se llamó
        mock_client.set.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_delete_operation_success(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica operación DELETE exitosa.
        
        Given: Una key existe en Redis
        When: Se ejecuta delete(key)
        Then: La key se elimina exitosamente
        """
        # Configurar mock
        mock_client = mock_optimized_client.return_value
        mock_client.delete = AsyncMock(return_value=1)  # 1 = key deleted
        
        # Ejecutar DELETE
        result = await redis_service_instance.delete(sample_data["key"])
        
        # Verificar resultado
        assert result is True, "DELETE operation should succeed"
        
        # Verificar llamada al cliente
        mock_client.delete.assert_called_once_with(sample_data["key"])


# ============================================================================
# TEST CLASS 4: JSON OPERATIONS
# ============================================================================

class TestRedisServiceJSONOperations:
    """
    Tests de operaciones JSON (serialization/deserialization).
    
    Verifica:
    - get_json() deserializa correctamente
    - set_json() serializa correctamente
    - Manejo de JSON inválido
    """
    
    @pytest.mark.asyncio
    async def test_get_json_deserializes_correctly(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica que get_json() deserializa JSON correctamente.
        
        Given: Un valor JSON válido en Redis
        When: Se ejecuta get_json(key)
        Then: Se retorna el dict deserializado
        """
        # Configurar mock para retornar JSON string
        mock_client = mock_optimized_client.return_value
        json_string = json.dumps(sample_data["json_data"])
        mock_client.get = AsyncMock(return_value=json_string)
        
        # Ejecutar get_json
        result = await redis_service_instance.get_json(sample_data["key"])
        
        # Verificar deserialización
        assert result == sample_data["json_data"], "Should deserialize JSON correctly"
        assert isinstance(result, dict), "Should return a dict"
        assert result["id"] == "123", "Should preserve data structure"
    
    @pytest.mark.asyncio
    async def test_set_json_serializes_correctly(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica que set_json() serializa dict a JSON.
        
        Given: Un dict Python
        When: Se ejecuta set_json(key, dict)
        Then: Se serializa a JSON string antes de guardar
        """
        # Configurar mock
        mock_client = mock_optimized_client.return_value
        mock_client.set = AsyncMock(return_value=True)
        
        # Ejecutar set_json
        result = await redis_service_instance.set_json(
            sample_data["key"],
            sample_data["json_data"]
        )
        
        # Verificar resultado
        assert result is True, "set_json should succeed"
        
        # Verificar que se serializó correctamente
        # El cliente debe recibir un JSON string, no un dict
        call_args = mock_client.set.call_args
        stored_value = call_args[0][1]  # Segundo argumento de set()
        
        # Verificar que es un string JSON válido
        assert isinstance(stored_value, str), "Should store as JSON string"
        parsed = json.loads(stored_value)
        assert parsed == sample_data["json_data"], "Should preserve data when serialized"
    
    @pytest.mark.asyncio
    async def test_get_json_handles_invalid_json(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica manejo de JSON inválido en get_json().
        
        Given: Redis contiene un string que NO es JSON válido
        When: Se ejecuta get_json(key)
        Then: Se retorna None sin lanzar excepción
        """
        # Configurar mock para retornar string inválido
        mock_client = mock_optimized_client.return_value
        mock_client.get = AsyncMock(return_value="invalid-json-{{{")
        
        # Ejecutar get_json (no debe lanzar excepción)
        result = await redis_service_instance.get_json(sample_data["key"])
        
        # Verificar graceful handling
        assert result is None, "Should return None for invalid JSON"


# ============================================================================
# TEST CLASS 5: ERROR HANDLING
# ============================================================================

class TestRedisServiceErrorHandling:
    """
    Tests de manejo de errores y graceful degradation.
    
    Verifica:
    - Operaciones con cliente desconectado
    - Reconexión después de fallos
    - Stats de errores
    """
    
    @pytest.mark.asyncio
    async def test_get_operation_with_disconnected_client(
        self,
        redis_service_instance,
        sample_data
    ):
        """
        Verifica GET con cliente desconectado retorna None sin crash.
        
        Given: Redis client está desconectado
        When: Se ejecuta get(key)
        Then: Se retorna None y se incrementan stats de errores
        """
        # Simular cliente desconectado
        redis_service_instance._client = None
        redis_service_instance._connected = False
        redis_service_instance.reset_stats()
        
        # Ejecutar GET
        result = await redis_service_instance.get(sample_data["key"])
        
        # Verificar graceful degradation
        assert result is None, "Should return None when disconnected"
        
        # Verificar stats
        stats = redis_service_instance.get_stats()
        assert stats["operations_failed"] == 1, "Should increment failed operations"
    
    @pytest.mark.asyncio
    async def test_set_operation_with_disconnected_client(
        self,
        redis_service_instance,
        sample_data
    ):
        """
        Verifica SET con cliente desconectado retorna False sin crash.
        
        Given: Redis client está desconectado
        When: Se ejecuta set(key, value)
        Then: Se retorna False y se incrementan stats de errores
        """
        # Simular cliente desconectado
        redis_service_instance._client = None
        redis_service_instance._connected = False
        redis_service_instance.reset_stats()
        
        # Ejecutar SET
        result = await redis_service_instance.set(
            sample_data["key"],
            sample_data["string_value"]
        )
        
        # Verificar graceful degradation
        assert result is False, "Should return False when disconnected"
        
        # Verificar stats
        stats = redis_service_instance.get_stats()
        assert stats["operations_failed"] == 1, "Should increment failed operations"
    
    @pytest.mark.asyncio
    async def test_operations_handle_redis_exceptions(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica que excepciones de Redis se manejan gracefully.
        
        Given: Redis client lanza excepción en operación
        When: Se ejecuta una operación
        Then: Se captura la excepción y se degrada gracefully
        """
        # Configurar mock para lanzar excepción
        mock_client = mock_optimized_client.return_value
        mock_client.get = AsyncMock(side_effect=Exception("Redis error"))
        
        redis_service_instance.reset_stats()
        
        # Ejecutar GET (no debe crashear)
        result = await redis_service_instance.get(sample_data["key"])
        
        # Verificar graceful handling
        assert result is None, "Should return None on exception"
        
        # Verificar stats
        stats = redis_service_instance.get_stats()
        assert stats["operations_failed"] >= 1, "Should track failed operations"
        
        # Verificar que se marcó como desconectado
        assert redis_service_instance._connected is False, \
            "Should mark as disconnected after error"


# ============================================================================
# TEST CLASS 6: OBSERVABILITY
# ============================================================================

class TestRedisServiceObservability:
    """
    Tests de observabilidad (stats, health checks, metrics).
    
    Verifica:
    - get_stats() estructura correcta
    - health_check() estados
    - reset_stats() limpia métricas
    - Hit ratio calculation
    """
    
    @pytest.mark.asyncio
    async def test_get_stats_returns_correct_structure(self, redis_service_instance):
        """
        Verifica que get_stats() retorna estructura completa de métricas.
        
        Given: Un RedisService con actividad
        When: Se llama get_stats()
        Then: Se retorna dict con todas las métricas esperadas
        """
        # Ejecutar algunas operaciones para generar stats
        # (esto usa los mocks del fixture)
        
        # Obtener stats
        stats = redis_service_instance.get_stats()
        
        # Verificar estructura completa
        required_fields = [
            "operations_total",
            "operations_successful",
            "operations_failed",
            "cache_hits",
            "cache_misses",
            "connection_errors",
            "connected",
            "hit_ratio",
            "client_available",
            "connection_attempts",
            "last_update"
        ]
        
        for field in required_fields:
            assert field in stats, f"Stats should include '{field}'"
        
        # Verificar tipos de datos
        assert isinstance(stats["operations_total"], int)
        assert isinstance(stats["hit_ratio"], float)
        assert isinstance(stats["connected"], bool)
        assert isinstance(stats["last_update"], str)
    
    @pytest.mark.asyncio
    async def test_health_check_with_connected_client(
        self,
        redis_service_instance,
        mock_optimized_client
    ):
        """
        Verifica health check con cliente conectado.
        
        Given: Redis está conectado y respondiendo
        When: Se ejecuta health_check()
        Then: Se retorna status "healthy"
        """
        # Configurar mock para ping exitoso
        mock_client = mock_optimized_client.return_value
        mock_client.ping = AsyncMock(return_value=True)
        
        # Ejecutar health check
        health = await redis_service_instance.health_check()
        
        # Verificar estructura
        assert "service" in health
        assert "timestamp" in health
        assert "connected" in health
        assert "status" in health
        
        # Verificar valores
        assert health["service"] == "redis"
        assert health["status"] == "healthy"
        assert health["connected"] is True
    
    @pytest.mark.asyncio
    async def test_health_check_with_disconnected_client(
        self,
        redis_service_instance
    ):
        """
        Verifica health check con cliente desconectado.
        
        Given: Redis NO está disponible
        When: Se ejecuta health_check()
        Then: Se retorna status apropiado sin crash
        """
        # Simular cliente desconectado
        redis_service_instance._client = None
        redis_service_instance._connected = False
        
        # Ejecutar health check
        health = await redis_service_instance.health_check()
        
        # Verificar status
        assert health["status"] == "disconnected"
        assert health["connected"] is False
        assert health["client_available"] is False
    
    def test_reset_stats_clears_metrics(self, redis_service_instance):
        """
        Verifica que reset_stats() limpia todas las métricas.
        
        Given: Un RedisService con stats acumulados
        When: Se llama reset_stats()
        Then: Todas las métricas numéricas se resetean a 0
        """
        # Simular stats con valores
        redis_service_instance._stats = {
            "operations_total": 100,
            "operations_successful": 80,
            "operations_failed": 20,
            "cache_hits": 60,
            "cache_misses": 40,
            "connection_errors": 5
        }
        
        # Reset stats
        redis_service_instance.reset_stats()
        
        # Verificar que todos los contadores están en 0
        stats = redis_service_instance._stats
        for key, value in stats.items():
            assert value == 0, f"{key} should be reset to 0"
    
    @pytest.mark.asyncio
    async def test_hit_ratio_calculation(
        self,
        redis_service_instance,
        mock_optimized_client,
        sample_data
    ):
        """
        Verifica cálculo correcto de hit_ratio.
        
        Given: Un mix de cache hits y misses
        When: Se calcula hit_ratio en get_stats()
        Then: El ratio es correcto (hits / (hits + misses))
        """
        mock_client = mock_optimized_client.return_value
        redis_service_instance.reset_stats()
        
        # Simular 3 cache hits
        mock_client.get = AsyncMock(return_value="value")
        await redis_service_instance.get("key1")
        await redis_service_instance.get("key2")
        await redis_service_instance.get("key3")
        
        # Simular 1 cache miss
        mock_client.get = AsyncMock(return_value=None)
        await redis_service_instance.get("key4")
        
        # Obtener stats
        stats = redis_service_instance.get_stats()
        
        # Verificar hit ratio: 3 hits / (3 hits + 1 miss) = 0.75
        expected_ratio = 3 / 4
        assert abs(stats["hit_ratio"] - expected_ratio) < 0.01, \
            f"Hit ratio should be {expected_ratio}, got {stats['hit_ratio']}"


# ============================================================================
# TEST CLASS 7: CONVENIENCE FUNCTIONS
# ============================================================================

class TestRedisServiceConvenienceFunctions:
    """
    Tests de funciones de conveniencia (backward compatibility).
    
    Verifica:
    - get_redis_service()
    - get_redis_health()
    - get_redis_stats()
    """
    
    @pytest.mark.asyncio
    async def test_get_redis_service_returns_singleton(self, mock_optimized_client):
        """
        Verifica que get_redis_service() retorna el singleton.
        
        Given: Una instancia de RedisService existe
        When: Se llama get_redis_service()
        Then: Se retorna la instancia singleton
        """
        # Limpiar singleton
        RedisService._instance = None
        
        # Llamar función de conveniencia
        service = await get_redis_service()
        
        # Verificar que retorna una instancia válida
        assert service is not None
        assert isinstance(service, RedisService)
        
        # Verificar que es singleton
        service2 = await get_redis_service()
        assert service is service2
        
        # Cleanup
        RedisService._instance = None
    
    @pytest.mark.asyncio
    async def test_get_redis_health_returns_health_check(self, mock_optimized_client):
        """
        Verifica que get_redis_health() retorna health check.
        
        Given: Un RedisService funcional
        When: Se llama get_redis_health()
        Then: Se retorna el resultado de health_check()
        """
        # Limpiar singleton
        RedisService._instance = None
        
        # Llamar función de conveniencia
        health = await get_redis_health()
        
        # Verificar estructura
        assert "service" in health
        assert "status" in health
        assert health["service"] == "redis"
        
        # Cleanup
        RedisService._instance = None
    
    @pytest.mark.asyncio
    async def test_get_redis_stats_returns_statistics(self, mock_optimized_client):
        """
        Verifica que get_redis_stats() retorna estadísticas.
        
        Given: Un RedisService funcional
        When: Se llama get_redis_stats()
        Then: Se retorna el resultado de get_stats()
        """
        # Limpiar singleton
        RedisService._instance = None
        
        # Llamar función de conveniencia
        stats = await get_redis_stats()
        
        # Verificar estructura
        assert "operations_total" in stats
        assert "hit_ratio" in stats
        assert "connected" in stats
        
        # Cleanup
        RedisService._instance = None


# ============================================================================
# RUNNER CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    """
    Ejecutar tests directamente:
    
    pytest tests/unit/test_redis_service.py -v
    pytest tests/unit/test_redis_service.py -v --cov=src.api.core.redis_service
    pytest tests/unit/test_redis_service.py -v -k "singleton"
    """
    pytest.main([__file__, "-v", "--tb=short"])