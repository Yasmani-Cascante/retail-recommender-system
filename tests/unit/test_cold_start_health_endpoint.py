"""Unit tests for /health endpoint shutdown_at field."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_returns_shutdown_at_none_when_flag_not_set():
    """When service:shutdown_at is not in Redis, _get_shutdown_at returns None."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch(
        "src.api.main_unified_redis.ServiceFactory.get_redis_service",
        new=AsyncMock(return_value=mock_rs),
    ):
        from src.api.main_unified_redis import _get_shutdown_at
        result = await _get_shutdown_at()

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_returns_shutdown_at_timestamp_when_flag_set():
    """When service:shutdown_at is in Redis, _get_shutdown_at returns its integer value."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=b"1714000000")
    mock_rs = MagicMock()
    mock_rs._client = mock_client

    with patch(
        "src.api.main_unified_redis.ServiceFactory.get_redis_service",
        new=AsyncMock(return_value=mock_rs),
    ):
        from src.api.main_unified_redis import _get_shutdown_at
        result = await _get_shutdown_at()

    assert result == 1714000000


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_returns_shutdown_at_none_when_redis_fails():
    """When Redis raises during shutdown_at lookup, _get_shutdown_at returns None (not crash)."""
    with patch(
        "src.api.main_unified_redis.ServiceFactory.get_redis_service",
        new=AsyncMock(side_effect=Exception("Redis down")),
    ):
        from src.api.main_unified_redis import _get_shutdown_at
        result = await _get_shutdown_at()

    assert result is None
