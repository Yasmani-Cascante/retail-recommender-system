"""Unit tests for cold-start shutdown flag helpers."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
@pytest.mark.asyncio
async def test_write_shutdown_flag_sets_redis_key():
    """_write_shutdown_flag writes service:shutdown_at with 1h TTL."""
    mock_client = AsyncMock()
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch("src.api.main_unified_redis.ServiceFactory.get_redis_service", new=AsyncMock(return_value=mock_rs)):
        from src.api.main_unified_redis import _write_shutdown_flag
        await _write_shutdown_flag()

    mock_client.set.assert_called_once()
    call_args = mock_client.set.call_args
    assert call_args[0][0] == "service:shutdown_at"
    assert call_args[1].get("ex") == 3600


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clear_shutdown_flag_deletes_redis_key():
    """_clear_shutdown_flag deletes service:shutdown_at from Redis."""
    mock_client = AsyncMock()
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch("src.api.main_unified_redis.ServiceFactory.get_redis_service", new=AsyncMock(return_value=mock_rs)):
        from src.api.main_unified_redis import _clear_shutdown_flag
        await _clear_shutdown_flag()

    mock_client.delete.assert_called_once_with("service:shutdown_at")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_write_shutdown_flag_handles_redis_error_gracefully():
    """_write_shutdown_flag does not raise when Redis is unavailable."""
    with patch(
        "src.api.main_unified_redis.ServiceFactory.get_redis_service",
        new=AsyncMock(side_effect=Exception("Redis connection refused")),
    ):
        from src.api.main_unified_redis import _write_shutdown_flag
        # Should not raise
        await _write_shutdown_flag()
