# tests/unit/test_kb_health_fix.py

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_health_endpoint_with_timeout():
    """Validate health endpoint respects 500ms timeout."""
    
    # Mock Redis ping que tarda 1 segundo
    async def slow_ping():
        await asyncio.sleep(1.0)
        return True
    
    with patch.object(kb.redis, 'ping', side_effect=slow_ping):
        start = asyncio.get_event_loop().time()
        result = await kb_health_check()
        elapsed = (asyncio.get_event_loop().time() - start) * 1000
        
        # ✅ VALIDAR: Timeout respetado
        assert elapsed < 600, f"Health check tardó {elapsed}ms (debe ser <600ms)"
        assert result["details"]["redis_connected"] == False
        assert result["details"]["redis_status"] == "timeout"

@pytest.mark.asyncio
async def test_health_endpoint_fast_redis():
    """Validate health endpoint with fast Redis."""
    
    # Mock Redis ping que responde rápido
    async def fast_ping():
        await asyncio.sleep(0.01)  # 10ms
        return True
    
    with patch.object(kb.redis, 'ping', side_effect=fast_ping):
        result = await kb_health_check()
        
        # ✅ VALIDAR: Redis detectado como conectado
        assert result["details"]["redis_connected"] == True
        assert "redis_status" not in result["details"] or result["details"]["redis_status"] != "timeout"