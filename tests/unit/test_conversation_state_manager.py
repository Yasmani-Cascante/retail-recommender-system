"""
Test Suite for MCPConversationStateManager - Conversational State Management
=============================================================================

Tests basados en la implementación REAL de conversation_state_manager.py validando:
- Creación de contextos conversacionales
- Gestión de turnos (add_conversation_turn)
- Persistencia en Redis
- Carga de estado
- Compatibilidad con interfaces legacy
- Session metadata generation

Author: Senior Architecture Team
Date: 30 Noviembre 2025
Version: 1.0.0 - Fase 3A Day 4
"""

import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

# Module under test
from src.api.mcp.conversation_state_manager import (
    MCPConversationStateManager,
    MCPConversationContext,
    ConversationTurn,
    ConversationStage,
    IntentEvolution,
    UserMarketPreferences,
    get_conversation_state_manager
)

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_redis_client():
    """
    Mock del Redis client para tests.
    
    Simula operaciones async de Redis.
    """
    mock = AsyncMock()
    
    # Operaciones básicas
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock(return_value=True)
    mock.zadd = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    
    return mock


@pytest.fixture
def mock_redis_service():
    """Mock de RedisService para ServiceFactory."""
    mock = AsyncMock()
    mock._client = AsyncMock()
    mock._client.get = AsyncMock(return_value=None)
    mock._client.setex = AsyncMock(return_value=True)
    mock._client.zadd = AsyncMock(return_value=1)
    mock._client.expire = AsyncMock(return_value=True)
    return mock


@pytest.fixture
async def state_manager(mock_redis_client):
    """
    Fixture que proporciona instancia de MCPConversationStateManager.
    """
    manager = MCPConversationStateManager(
        redis_client=mock_redis_client,
        state_ttl=3600,
        conversation_ttl=86400,
        max_turns_per_session=50
    )
    
    yield manager
    
    # Cleanup
    manager.sessions_cache.clear()


@pytest.fixture
def sample_market_context():
    """Contexto de mercado de ejemplo."""
    return {
        "market_id": "US",
        "currency": "USD",
        "language": "en"
    }


# ============================================================================
# TEST CLASS 1: INITIALIZATION
# ============================================================================

class TestMCPConversationStateManagerInitialization:
    """
    Tests de inicialización del MCPConversationStateManager.
    """
    
    @pytest.mark.asyncio
    async def test_initialization_with_redis_client(self, mock_redis_client):
        """
        Verifica inicialización con Redis client.
        
        Given: Un Redis client mock
        When: Se crea MCPConversationStateManager
        Then: Se inicializa correctamente
        """
        manager = MCPConversationStateManager(
            redis_client=mock_redis_client,
            state_ttl=3600
        )
        
        assert manager._redis_client is not None
        assert manager.state_ttl == 3600
        assert manager.conversation_ttl == 7 * 24 * 3600  # Default
        assert manager.max_turns_per_session == 50  # Default
    
    @pytest.mark.asyncio
    async def test_initialization_with_custom_ttls(self, mock_redis_client):
        """
        Verifica inicialización con TTLs personalizados.
        """
        manager = MCPConversationStateManager(
            redis_client=mock_redis_client,
            state_ttl=7200,
            conversation_ttl=172800,
            max_turns_per_session=100
        )
        
        assert manager.state_ttl == 7200
        assert manager.conversation_ttl == 172800
        assert manager.max_turns_per_session == 100
    
    @pytest.mark.asyncio
    async def test_initialization_sets_prefixes(self, mock_redis_client):
        """
        Verifica que se establecen los prefixes de Redis.
        """
        manager = MCPConversationStateManager(redis_client=mock_redis_client)
        
        assert manager.CONVERSATION_PREFIX == "mcp:conversation"
        assert manager.USER_PROFILE_PREFIX == "mcp:user_profile"
        assert manager.MARKET_PREFS_PREFIX == "mcp:market_prefs"
        assert manager.SESSION_INDEX_PREFIX == "mcp:session_index"
    
    @pytest.mark.asyncio
    async def test_initialization_sets_metrics_to_zero(self, mock_redis_client):
        """
        Verifica que métricas empiezan en cero.
        """
        manager = MCPConversationStateManager(redis_client=mock_redis_client)
        
        assert manager.metrics["conversations_created"] == 0
        assert manager.metrics["conversations_loaded"] == 0
        assert manager.metrics["state_saves"] == 0
        assert manager.metrics["cache_hits"] == 0
        assert manager.metrics["cache_misses"] == 0


# ============================================================================
# TEST CLASS 2: CREATE CONVERSATION CONTEXT
# ============================================================================

class TestCreateConversationContext:
    """
    Tests de create_conversation_context().
    """
    
    @pytest.mark.asyncio
    async def test_create_conversation_context_success(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica creación exitosa de contexto conversacional.
        
        Given: Session ID, user ID y market context
        When: Se crea un nuevo contexto
        Then: Retorna MCPConversationContext con valores correctos
        """
        context = await state_manager.create_conversation_context(
            session_id="session_123",
            user_id="user_456",
            initial_query="Hello",
            market_context=sample_market_context,
            user_agent="Mozilla/5.0"
        )
        
        # Verificar estructura básica
        assert isinstance(context, MCPConversationContext)
        assert context.session_id == "session_123"
        assert context.user_id == "user_456"
        assert context.total_turns == 0
        assert len(context.turns) == 0
        
        # Verificar estados iniciales
        assert context.conversation_stage == ConversationStage.INITIAL
        assert context.primary_intent == "unknown"
        assert context.intent_evolution_pattern == IntentEvolution.STABLE
    
    @pytest.mark.asyncio
    async def test_create_conversation_context_sets_market_id(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica que se establece el market_id correctamente.
        """
        context = await state_manager.create_conversation_context(
            session_id="session_789",
            user_id="user_101",
            initial_query="Test",
            market_context=sample_market_context
        )
        
        assert context.initial_market_id == "US"
        assert context.current_market_id == "US"
    
    @pytest.mark.asyncio
    async def test_create_conversation_context_increments_metrics(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica que se incrementan las métricas correctamente.
        """
        initial_count = state_manager.metrics["conversations_created"]
        
        await state_manager.create_conversation_context(
            session_id="session_999",
            user_id="user_999",
            initial_query="Test",
            market_context=sample_market_context
        )
        
        assert state_manager.metrics["conversations_created"] == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_create_conversation_context_detects_device_type(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica detección de device type desde user agent.
        """
        # Mobile
        context_mobile = await state_manager.create_conversation_context(
            session_id="session_m",
            user_id="user_m",
            initial_query="Test",
            market_context=sample_market_context,
            user_agent="Mozilla/5.0 (Android 10)"
        )
        assert context_mobile.device_type == "mobile"
        
        # Desktop
        context_desktop = await state_manager.create_conversation_context(
            session_id="session_d",
            user_id="user_d",
            initial_query="Test",
            market_context=sample_market_context,
            user_agent="Mozilla/5.0 (Windows NT 10.0)"
        )
        assert context_desktop.device_type == "desktop"


# ============================================================================
# TEST CLASS 3: ADD CONVERSATION TURN
# ============================================================================

class TestAddConversationTurn:
    """
    Tests de add_conversation_turn() y variantes.
    """
    
    @pytest.mark.asyncio
    async def test_add_turn_simple_interface(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica add_conversation_turn_simple.
        
        Given: Un contexto existente
        When: Se agrega un turn simple
        Then: Turn se agrega correctamente
        """
        # Crear contexto
        context = await state_manager.create_conversation_context(
            session_id="session_turn1",
            user_id="user_turn1",
            initial_query="Hello",
            market_context=sample_market_context
        )
        
        # Agregar turn
        updated_context = await state_manager.add_conversation_turn_simple(
            context=context,
            user_query="Show me shoes",
            ai_response="Here are some shoes",
            metadata={"recommendations": ["prod_1", "prod_2"]}
        )
        
        # Verificar
        assert updated_context.total_turns == 1
        assert len(updated_context.turns) == 1
        assert updated_context.turns[0].user_query == "Show me shoes"
        assert updated_context.turns[0].ai_response == "Here are some shoes"
    
    @pytest.mark.asyncio
    async def test_add_turn_increments_turn_count(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica que turn_count se incrementa.
        """
        context = await state_manager.create_conversation_context(
            session_id="session_inc",
            user_id="user_inc",
            initial_query="Hello",
            market_context=sample_market_context
        )
        
        assert context.total_turns == 0
        
        # Agregar 3 turns
        for i in range(3):
            context = await state_manager.add_conversation_turn_simple(
                context=context,
                user_query=f"Query {i}",
                ai_response=f"Response {i}"
            )
        
        assert context.total_turns == 3
        assert len(context.turns) == 3
    
    @pytest.mark.asyncio
    async def test_add_turn_with_recommendations(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica add_conversation_turn_with_recommendations.
        """
        context = await state_manager.create_conversation_context(
            session_id="session_rec",
            user_id="user_rec",
            initial_query="Hello",
            market_context=sample_market_context
        )
        
        recommendation_ids = ["prod_100", "prod_200", "prod_300"]
        
        updated_context = await state_manager.add_conversation_turn_with_recommendations(
            session=context,
            user_query="Looking for shoes",
            ai_response="Here are recommendations",
            recommendation_ids=recommendation_ids
        )
        
        # Verificar que se guardaron los IDs
        assert updated_context.total_turns == 1
        assert len(updated_context.turns[0].recommendations_provided) == 3
        assert updated_context.turns[0].recommendations_provided == recommendation_ids
    
    @pytest.mark.asyncio
    async def test_add_turn_updates_last_updated(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica que last_updated se actualiza.
        """
        context = await state_manager.create_conversation_context(
            session_id="session_time",
            user_id="user_time",
            initial_query="Hello",
            market_context=sample_market_context
        )
        
        initial_time = context.last_updated
        
        # Esperar un poco
        await asyncio.sleep(0.1)
        
        # Agregar turn
        updated_context = await state_manager.add_conversation_turn_simple(
            context=context,
            user_query="Test",
            ai_response="Response"
        )
        
        assert updated_context.last_updated > initial_time


# ============================================================================
# TEST CLASS 4: SAVE & LOAD STATE
# ============================================================================

class TestSaveAndLoadState:
    """
    Tests de save_conversation_state() y load_conversation_state().
    """
    
    @pytest.mark.asyncio
    async def test_save_conversation_state_to_redis(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica que save guarda en Redis.
        
        Given: Un contexto conversacional
        When: Se guarda el estado
        Then: Se llama a Redis setex
        """
        context = await state_manager.create_conversation_context(
            session_id="session_save1",
            user_id="user_save1",
            initial_query="Test",
            market_context=sample_market_context
        )
        
        # Guardar
        result = await state_manager.save_conversation_state(context)
        
        # Verificar
        assert result is True
        assert state_manager._redis_client.setex.called
    
    @pytest.mark.asyncio
    async def test_save_stores_in_memory_cache(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica que se guarda en memoria cache como fallback.
        """
        context = await state_manager.create_conversation_context(
            session_id="session_mem",
            user_id="user_mem",
            initial_query="Test",
            market_context=sample_market_context
        )
        
        await state_manager.save_conversation_state(context)
        
        # Verificar que está en memoria
        assert "session_mem" in state_manager.sessions_cache
    
    @pytest.mark.asyncio
    async def test_load_conversation_state_from_redis(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica load desde Redis.
        """
        # Crear y guardar contexto
        context = await state_manager.create_conversation_context(
            session_id="session_load1",
            user_id="user_load1",
            initial_query="Test",
            market_context=sample_market_context
        )
        
        # Simular datos en Redis
        serialized = state_manager._serialize_context(context)
        state_manager._redis_client.get = AsyncMock(
            return_value=json.dumps(serialized)
        )
        
        # Cargar
        loaded_context = await state_manager.load_conversation_state("session_load1")
        
        # Verificar
        assert loaded_context is not None
        assert loaded_context.session_id == "session_load1"
        assert loaded_context.user_id == "user_load1"
    
    @pytest.mark.asyncio
    async def test_load_returns_none_when_not_found(self, state_manager):
        """
        Verifica que load retorna None si no se encuentra.
        """
        # Redis retorna None
        state_manager._redis_client.get = AsyncMock(return_value=None)
        
        result = await state_manager.load_conversation_state("nonexistent")
        
        assert result is None
        assert state_manager.metrics["cache_misses"] > 0


# ============================================================================
# TEST CLASS 5: SESSION METADATA
# ============================================================================

class TestSessionMetadata:
    """
    Tests de get_session_metadata_for_response().
    """
    
    @pytest.mark.asyncio
    async def test_get_session_metadata_structure(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica estructura del session metadata.
        
        Given: Un contexto con turns
        When: Se genera session metadata
        Then: Contiene campos requeridos
        """
        context = await state_manager.create_conversation_context(
            session_id="session_meta",
            user_id="user_meta",
            initial_query="Test",
            market_context=sample_market_context
        )
        
        # Agregar un turn
        context = await state_manager.add_conversation_turn_simple(
            context=context,
            user_query="Query",
            ai_response="Response"
        )
        
        # Generar metadata
        metadata = state_manager.get_session_metadata_for_response(context)
        
        # Verificar estructura
        assert "session_id" in metadata
        assert "turn_number" in metadata
        assert "user_id" in metadata
        assert "last_updated" in metadata
        
        # Verificar valores
        assert metadata["session_id"] == "session_meta"
        assert metadata["turn_number"] == 1
        assert metadata["user_id"] == "user_meta"


# ============================================================================
# TEST CLASS 6: COMPATIBILITY PROPERTIES
# ============================================================================

class TestCompatibilityProperties:
    """
    Tests de compatibility properties en MCPConversationContext.
    """
    
    @pytest.mark.asyncio
    async def test_turn_count_property(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica property turn_count mapea a total_turns.
        """
        context = await state_manager.create_conversation_context(
            session_id="session_prop",
            user_id="user_prop",
            initial_query="Test",
            market_context=sample_market_context
        )
        
        # Verificar que turn_count mapea a total_turns
        assert context.turn_count == context.total_turns
        assert context.turn_count == 0
        
        # Agregar turn
        context = await state_manager.add_conversation_turn_simple(
            context=context,
            user_query="Query",
            ai_response="Response"
        )
        
        assert context.turn_count == 1
        assert context.turn_count == context.total_turns
    
    @pytest.mark.asyncio
    async def test_market_id_property(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica property market_id mapea a current_market_id.
        """
        context = await state_manager.create_conversation_context(
            session_id="session_mkt",
            user_id="user_mkt",
            initial_query="Test",
            market_context=sample_market_context
        )
        
        # Verificar mapeo
        assert context.market_id == context.current_market_id
        assert context.market_id == "US"


# ============================================================================
# TEST CLASS 7: METRICS
# ============================================================================

class TestMetrics:
    """
    Tests de get_metrics().
    """
    
    @pytest.mark.asyncio
    async def test_get_metrics_returns_dict(self, state_manager):
        """
        Verifica que get_metrics retorna diccionario.
        """
        metrics = state_manager.get_metrics()
        
        assert isinstance(metrics, dict)
        assert "manager_metrics" in metrics
        assert "cache_hit_ratio" in metrics
    
    @pytest.mark.asyncio
    async def test_cache_hit_ratio_calculation(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica cálculo de cache hit ratio.
        """
        # Simular hits y misses
        state_manager.metrics["cache_hits"] = 7
        state_manager.metrics["cache_misses"] = 3
        
        metrics = state_manager.get_metrics()
        
        # 7 hits / 10 total = 0.7
        assert metrics["cache_hit_ratio"] == 0.7


# ============================================================================
# TEST CLASS 8: GET OR CREATE SESSION
# ============================================================================

class TestGetOrCreateSession:
    """
    Tests de get_or_create_session() - método de compatibilidad.
    """
    
    @pytest.mark.asyncio
    async def test_get_or_create_creates_new_when_no_session_id(
        self,
        state_manager
    ):
        """
        Verifica que crea nueva sesión si no hay session_id.
        
        Given: Sin session_id
        When: Se llama get_or_create_session
        Then: Crea nueva sesión
        """
        context = await state_manager.get_or_create_session(
            session_id=None,
            user_id="user_new",
            market_id="ES"
        )
        
        assert context is not None
        assert context.user_id == "user_new"
        assert context.current_market_id == "ES"
        assert context.total_turns == 0
    
    @pytest.mark.asyncio
    async def test_get_or_create_loads_existing_session(
        self,
        state_manager,
        sample_market_context
    ):
        """
        Verifica que carga sesión existente si está en cache.
        """
        # Crear sesión primero
        original_context = await state_manager.create_conversation_context(
            session_id="session_existing",
            user_id="user_existing",
            initial_query="Test",
            market_context=sample_market_context
        )
        
        # Guardar en memoria cache
        state_manager.sessions_cache["session_existing"] = state_manager._serialize_context(original_context)
        
        # Intentar cargar
        loaded_context = await state_manager.get_or_create_session(
            session_id="session_existing",
            user_id="user_existing",
            market_id="US"
        )
        
        assert loaded_context.session_id == "session_existing"


# ============================================================================
# RUNNER CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    """
    Ejecutar tests directamente:
    
    pytest tests/unit/test_conversation_state_manager.py -v
    pytest tests/unit/test_conversation_state_manager.py -v --cov=src.api.mcp.conversation_state_manager
    """
    pytest.main([__file__, "-v", "--tb=short"])
