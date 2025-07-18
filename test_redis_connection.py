#!/usr/bin/env python3
"""
Test Redis Connection - Script específico para probar Redis
========================================================

Ejecutar: python test_redis_connection.py
"""

import asyncio
import sys
import os

# Add path
sys.path.insert(0, os.getcwd())

async def test_redis_connection():
    """Test específico de conexión Redis"""
    
    print("🔍 TESTING REDIS CONNECTION")
    print("=" * 40)
    
    try:
        from src.api.core.redis_config_fix import PatchedRedisClient
        
        # Crear cliente
        print("1. Creating PatchedRedisClient...")
        redis_client = PatchedRedisClient(use_validated_config=True)
        
        # Conectar
        print("2. Connecting to Redis...")
        connected = await redis_client.connect()
        
        if not connected:
            print("❌ Connection failed")
            return False
        
        print("✅ Connected successfully")
        
        # Test ping
        print("3. Testing ping...")
        try:
            ping_result = await redis_client.ping()
            print(f"✅ Ping successful: {ping_result}")
        except Exception as e:
            print(f"❌ Ping failed: {e}")
            return False
        
        # Test set/get
        print("4. Testing set/get operations...")
        test_key = "test_connection_key"
        test_value = "test_value_123"
        
        try:
            # Set
            await redis_client.set(test_key, test_value, ex=30)
            print(f"✅ Set successful: {test_key} = {test_value}")
            
            # Get
            retrieved = await redis_client.get(test_key)
            print(f"✅ Get successful: {test_key} = {retrieved}")
            
            if retrieved == test_value:
                print("✅ Value integrity confirmed")
            else:
                print(f"❌ Value mismatch: expected '{test_value}', got '{retrieved}'")
                return False
            
            # Delete
            await redis_client.delete(test_key)
            print("✅ Delete successful")
            
        except Exception as e:
            print(f"❌ Set/Get/Delete failed: {e}")
            return False
        
        # Close connection
        await redis_client.close()
        print("✅ Connection closed")
        
        print("\n🎉 ALL REDIS TESTS PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Redis test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_redis_connection())
    
    if success:
        print("\n✅ Redis is working correctly!")
        print("You can now run: python step1_validate_environment.py")
    else:
        print("\n❌ Redis issues remain. Check configuration.")
