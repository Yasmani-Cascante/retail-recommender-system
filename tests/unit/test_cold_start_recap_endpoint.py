"""Unit tests for GET /v1/mcp/session/{session_id}/recap endpoint."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recap_returns_last_two_turns():
    """Returns last 2 turns from conversation_history in Redis."""
    session_data = {
        "conversation_history": [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola, ¿en qué te ayudo?"},
            {"role": "user", "content": "Busco vestidos para una boda"},
            {"role": "assistant", "content": "Te recomiendo estos modelos…"},
        ]
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=json.dumps(session_data).encode())
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch("src.api.routers.mcp_router.ServiceFactory.get_redis_service", new=AsyncMock(return_value=mock_rs)):
        from src.api.routers.mcp_router import get_session_recap
        result = await get_session_recap("test_session_123")

    assert result["session_id"] == "test_session_123"
    assert len(result["turns"]) == 2
    assert result["turns"][0]["role"] == "user"
    assert result["turns"][0]["content"] == "Busco vestidos para una boda"
    assert result["turns"][1]["role"] == "assistant"
    assert result["turns"][1]["content"] == "Te recomiendo estos modelos…"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recap_returns_404_when_session_not_found():
    """Returns 404 when session key doesn't exist in Redis."""
    from fastapi import HTTPException

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch("src.api.routers.mcp_router.ServiceFactory.get_redis_service", new=AsyncMock(return_value=mock_rs)):
        from src.api.routers.mcp_router import get_session_recap
        with pytest.raises(HTTPException) as exc_info:
            await get_session_recap("nonexistent_session")

    assert exc_info.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recap_handles_short_history():
    """Returns fewer than 2 turns if history has less than 2 entries."""
    session_data = {
        "conversation_history": [
            {"role": "user", "content": "Solo un mensaje"},
        ]
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=json.dumps(session_data).encode())
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch("src.api.routers.mcp_router.ServiceFactory.get_redis_service", new=AsyncMock(return_value=mock_rs)):
        from src.api.routers.mcp_router import get_session_recap
        result = await get_session_recap("short_session")

    assert len(result["turns"]) == 1
    assert result["turns"][0]["content"] == "Solo un mensaje"
