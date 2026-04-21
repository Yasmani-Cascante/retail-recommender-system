"""
Verificar tamaño del connection pool de PostgreSQL
"""
import asyncio
from src.api.dependencies import get_db_pool

async def check_pool_config():
    """Obtener configuración del pool."""
    pool = await get_db_pool()
    
    print("=" * 70)
    print("POSTGRESQL POOL CONFIGURATION")
    print("=" * 70)
    print(f"Pool size (max connections): {pool.get_size()}")
    print(f"Idle connections: {pool.get_idle_size()}")
    print(f"Min size: {pool.get_min_size()}")
    print(f"Max size: {pool.get_max_size()}")
    print(f"Max queries: {pool.get_max_queries()}")
    print(f"Timeout: {pool.get_timeout()}")
    print("=" * 70)
    
    return {
        "current_size": pool.get_size(),
        "idle": pool.get_idle_size(),
        "min_size": pool.get_min_size(),
        "max_size": pool.get_max_size()
    }

if __name__ == "__main__":
    result = asyncio.run(check_pool_config())
    print(f"\n✅ Max concurrent connections: {result['max_size']}")
    print(f"🎯 Recommended semaphore <= {result['max_size']}")