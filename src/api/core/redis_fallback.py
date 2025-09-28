#!/usr/bin/env python3
"""
Redis Fallback Module - Mock Implementation
==========================================

Proporciona implementaciones mock de Redis cuando el módulo redis no está disponible.
Esto permite que el sistema funcione sin Redis instalado, manteniendo la funcionalidad
básica pero sin caché distribuida.

ARQUITECTURA: Fallback elegante para robustez empresarial
OBJETIVO: Permitir desarrollo sin infraestructura compleja
"""

import logging
import asyncio
import json
from typing import Dict, Any, Optional, Union, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MockRedisClient:
    """Mock implementation de Redis client para fallback"""
    
    def __init__(self, **kwargs):
        self.connected = True  # Simular conexión exitosa
        self.ssl = kwargs.get('ssl', False)
        self.host = kwargs.get('host', 'localhost')
        self.port = kwargs.get('port', 6379)
        self.db = kwargs.get('db', 0)
        
        # Storage en memoria (se pierde al reiniciar)
        self._storage: Dict[str, Any] = {}
        self._expiry: Dict[str, datetime] = {}
        
        logger.info(f"🔄 MockRedisClient initialized (fallback mode)")
        logger.info(f"   Host: {self.host}:{self.port}")
        logger.info(f"   SSL: {self.ssl}")
        logger.info(f"   Database: {self.db}")
    
    async def connect(self) -> bool:
        """Simular conexión exitosa"""
        logger.info("✅ MockRedisClient connected (in-memory storage)")
        return True
    
    async def ping(self) -> bool:
        """Simular ping exitoso"""
        return True
    
    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set value con TTL opcional"""
        self._storage[key] = value
        
        if ex:
            self._expiry[key] = datetime.now() + timedelta(seconds=ex)
        
        logger.debug(f"MockRedis SET: {key} (TTL: {ex}s)")
        return True
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value con verificación de TTL"""
        # Verificar si la key ha expirado
        if key in self._expiry:
            if datetime.now() > self._expiry[key]:
                # Key expirada, eliminar
                self._storage.pop(key, None)
                self._expiry.pop(key, None)
                logger.debug(f"MockRedis GET: {key} EXPIRED")
                return None
        
        value = self._storage.get(key)
        logger.debug(f"MockRedis GET: {key} -> {'found' if value else 'not found'}")
        return value
    
    async def delete(self, key: str) -> int:
        """Delete key"""
        existed = key in self._storage
        self._storage.pop(key, None)
        self._expiry.pop(key, None)
        
        logger.debug(f"MockRedis DELETE: {key} -> {'existed' if existed else 'not found'}")
        return 1 if existed else 0
    
    async def exists(self, key: str) -> int:
        """Check if key exists (verificando TTL)"""
        # Verificar TTL primero
        if key in self._expiry:
            if datetime.now() > self._expiry[key]:
                self._storage.pop(key, None)
                self._expiry.pop(key, None)
                return 0
        
        exists = key in self._storage
        logger.debug(f"MockRedis EXISTS: {key} -> {exists}")
        return 1 if exists else 0
    
    async def hset(self, name: str, key: str, value: Any) -> int:
        """Hash set"""
        if name not in self._storage:
            self._storage[name] = {}
        
        if not isinstance(self._storage[name], dict):
            self._storage[name] = {}
        
        existed = key in self._storage[name]
        self._storage[name][key] = value
        
        logger.debug(f"MockRedis HSET: {name}.{key}")
        return 0 if existed else 1
    
    async def hget(self, name: str, key: str) -> Optional[Any]:
        """Hash get"""
        hash_obj = self._storage.get(name, {})
        if isinstance(hash_obj, dict):
            value = hash_obj.get(key)
            logger.debug(f"MockRedis HGET: {name}.{key} -> {'found' if value else 'not found'}")
            return value
        return None
    
    async def hgetall(self, name: str) -> Dict[str, Any]:
        """Hash get all"""
        hash_obj = self._storage.get(name, {})
        if isinstance(hash_obj, dict):
            logger.debug(f"MockRedis HGETALL: {name} -> {len(hash_obj)} keys")
            return hash_obj
        return {}
    
    async def hdel(self, name: str, *keys: str) -> int:
        """Hash delete"""
        hash_obj = self._storage.get(name, {})
        if not isinstance(hash_obj, dict):
            return 0
        
        deleted = 0
        for key in keys:
            if key in hash_obj:
                del hash_obj[key]
                deleted += 1
        
        logger.debug(f"MockRedis HDEL: {name} -> {deleted} keys deleted")
        return deleted
    
    async def keys(self, pattern: str = "*") -> List[str]:
        """List keys (simple pattern matching)"""
        all_keys = list(self._storage.keys())
        
        if pattern == "*":
            return all_keys
        
        # Simple pattern matching (solo * al final)
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            matched = [k for k in all_keys if k.startswith(prefix)]
        else:
            matched = [k for k in all_keys if k == pattern]
        
        logger.debug(f"MockRedis KEYS: {pattern} -> {len(matched)} keys")
        return matched
    
    async def flushdb(self) -> bool:
        """Flush database"""
        count = len(self._storage)
        self._storage.clear()
        self._expiry.clear()
        
        logger.info(f"MockRedis FLUSHDB: {count} keys cleared")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get stats del mock redis"""
        active_keys = 0
        expired_keys = 0
        
        now = datetime.now()
        for key in list(self._storage.keys()):
            if key in self._expiry and now > self._expiry[key]:
                expired_keys += 1
                # Cleanup de keys expiradas
                self._storage.pop(key, None)
                self._expiry.pop(key, None)
            else:
                active_keys += 1
        
        return {
            "type": "MockRedisClient",
            "active_keys": active_keys,
            "expired_keys_cleaned": expired_keys,
            "total_operations": active_keys,  # Approximation
            "memory_usage": "in_process",
            "connected": self.connected,
            "fallback_mode": True
        }

class MockRedisConnectionPool:
    """Mock connection pool para compatibilidad"""
    
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        logger.info("🔄 MockRedisConnectionPool initialized")
    
    async def get_connection(self) -> MockRedisClient:
        """Get connection del pool (crea nueva instancia)"""
        return MockRedisClient(**self.kwargs)

# Factory functions para compatibilidad
def create_mock_redis_client(**kwargs) -> MockRedisClient:
    """Factory para crear MockRedisClient"""
    return MockRedisClient(**kwargs)

def create_mock_redis_pool(**kwargs) -> MockRedisConnectionPool:
    """Factory para crear MockRedisConnectionPool"""
    return MockRedisConnectionPool(**kwargs)

# Función principal para testing
async def test_mock_redis():
    """Test basic functionality del MockRedisClient"""
    print("🧪 Testing MockRedisClient...")
    
    client = MockRedisClient()
    await client.connect()
    
    # Test basic operations
    await client.set("test_key", "test_value", ex=5)
    value = await client.get("test_key")
    print(f"SET/GET test: {value}")
    
    # Test hash operations
    await client.hset("test_hash", "field1", "value1")
    hash_value = await client.hget("test_hash", "field1")
    print(f"HSET/HGET test: {hash_value}")
    
    # Test stats
    stats = client.get_stats()
    print(f"Stats: {stats}")
    
    print("✅ MockRedisClient test completed")

if __name__ == "__main__":
    asyncio.run(test_mock_redis())
