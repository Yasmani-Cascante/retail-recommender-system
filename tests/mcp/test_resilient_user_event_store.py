# tests/test_resilient_user_event_store.py
import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock
from src.api.mcp.user_events.resilient_user_event_store import UserEventStore, StorageError
from src.api.mcp.client.circuit_breaker import CircuitState

@pytest.fixture
async def event_store():
    """Fixture para proporcionar un UserEventStore con mocks"""
    # Usar una URL de Redis falsa para pruebas
    store = UserEventStore(
        redis_url="redis://localhost:6379/0",
        cache_ttl=1,  # 1 segundo para pruebas
        enable_circuit_breaker=True,
        cache_size=10,
        local_buffer_size=5,
        flush_interval_seconds=1,
        local_fallback_dir="./test_fallback"
    )
    
    # Mock de Redis
    store.redis = AsyncMock()
    store.connected = True
    
    # Reiniciar métricas
    store.metrics = {
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
    
    yield store
    
    # Limpieza
    if store._flush_task and not store._flush_task.done():
        store._flush_task.cancel()
    if store._recovery_task and not store._recovery_task.done():
        store._recovery_task.cancel()

@pytest.mark.asyncio
async def test_record_event(event_store):
    """Test para registrar un evento básico"""
    # Configurar mock
    event_store._flush_events_buffer = AsyncMock(return_value=True)
    
    # Ejecutar
    result = await event_store.record_event(
        user_id="test_user",
        event_type="detail-page-view",
        data={"product_id": "123", "product_category": "Ropa"}
    )
    
    # Verificar
    assert result is True
    assert len(event_store.events_buffer) == 1
    assert event_store.events_buffer[0]["user_id"] == "test_user"
    assert event_store.events_buffer[0]["event_type"] == "detail-page-view"
    assert event_store.metrics["events_buffered"] == 1

@pytest.mark.asyncio
async def test_get_user_profile_cache_hit(event_store):
    """Test para obtener perfil con caché hit"""
    # Configurar mock para caché hit
    test_profile = {"user_id": "test_user", "total_events": 5}
    event_store.profile_cache[f"profile:test_user"] = test_profile
    
    # Ejecutar
    profile = await event_store.get_user_profile("test_user")
    
    # Verificar
    assert profile == test_profile
    assert event_store.metrics["cache_hits"] == 1
    assert event_store.metrics["cache_misses"] == 0

@pytest.mark.asyncio
async def test_get_user_profile_generate_new(event_store):
    """Test para generar nuevo perfil cuando no existe en caché ni Redis"""
    # Configurar mocks
    event_store.redis.exists = AsyncMock(return_value=0)
    event_store.redis.lrange = AsyncMock(return_value=[])
    event_store.redis.set = AsyncMock()
    
    # Ejecutar
    profile = await event_store.get_user_profile("new_user")
    
    # Verificar
    assert profile["user_id"] == "new_user"
    assert profile["total_events"] == 0
    assert profile["activity_level"] == "new"
    assert event_store.metrics["cache_misses"] == 1
    assert event_store.metrics["profiles_generated"] == 1

@pytest.mark.asyncio
async def test_circuit_breaker_open(event_store):
    """Test para verificar comportamiento cuando circuit breaker está abierto"""
    # Configurar circuit breaker en estado abierto
    event_store.read_circuit_breaker.state = CircuitState.OPEN
    event_store._read_fallback = AsyncMock(return_value={"user_id": "fallback_user", "fallback": True})
    
    # Ejecutar
    profile = await event_store.get_user_profile("test_user")
    
    # Verificar
    assert profile["fallback"] is True
    assert event_store.metrics["fallbacks_used"] == 1
    assert event_store.metrics["circuit_breaker_triggers"] == 1

@pytest.mark.asyncio
async def test_bulk_operations(event_store):
    """Test para verificar operaciones bulk"""
    # Configurar mocks
    event_store._persist_events_batch = AsyncMock(return_value=True)
    
    # Llenar buffer con eventos
    for i in range(event_store.local_buffer_size):
        await event_store.record_event(
            user_id=f"user_{i}",
            event_type="detail-page-view",
            data={"product_id": f"product_{i}"}
        )
    
    # Verificar que se haya llamado a _persist_events_batch
    event_store._persist_events_batch.assert_called_once()
    assert event_store.metrics["events_buffered"] == event_store.local_buffer_size