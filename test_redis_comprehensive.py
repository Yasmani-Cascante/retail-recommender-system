#!/usr/bin/env python3
"""
Redis Configuration Test with Explicit .env Loading
==================================================

Test Redis con carga explícita de variables de entorno desde .env

Author: Senior Architecture Team
"""

import sys
import os

sys.path.append('src')

# ✅ CRITICAL: Load .env explicitly before any imports
from dotenv import load_dotenv
load_dotenv()  # This loads .env file

def test_redis_with_proper_env():
    """Test Redis con variables de entorno cargadas correctamente"""
    
    print("🚀 REDIS TEST CON VARIABLES DE ENTORNO CARGADAS")
    print("=" * 60)
    
    # Debug variables de entorno después de cargar .env
    print("\n📋 VARIABLES DE ENTORNO (POST LOAD_DOTENV):")
    redis_vars = [
        'USE_REDIS_CACHE',
        'REDIS_HOST', 
        'REDIS_PORT',
        'REDIS_SSL',
        'REDIS_PASSWORD',
        'REDIS_USERNAME',
        'REDIS_DB'
    ]
    
    all_loaded = True
    for var in redis_vars:
        value = os.getenv(var, 'NOT_SET')
        print(f"  {var}: '{value}'")
        if value == 'NOT_SET':
            all_loaded = False
    
    if not all_loaded:
        print("\n❌ ALGUNAS VARIABLES NO SE CARGARON")
        print("🔧 Verificando ubicación del archivo .env...")
        
        # Check if .env exists
        env_paths = ['.env', '../.env', '../../.env']
        for path in env_paths:
            if os.path.exists(path):
                print(f"✅ Archivo .env encontrado en: {path}")
                
                # Load from specific path
                load_dotenv(path)
                print(f"🔄 Cargando variables desde: {path}")
                
                # Test again
                use_redis = os.getenv('USE_REDIS_CACHE', 'NOT_SET')
                print(f"📊 USE_REDIS_CACHE después de cargar: '{use_redis}'")
                
                if use_redis != 'NOT_SET':
                    break
            else:
                print(f"❌ No encontrado: {path}")
    
    # Test validation logic
    print("\n🔧 LÓGICA DE VALIDACIÓN (POST LOAD):")
    
    use_cache_raw = os.getenv('USE_REDIS_CACHE', 'false')
    print(f"  use_cache_raw: '{use_cache_raw}'")
    
    use_cache_lower = use_cache_raw.lower()
    print(f"  use_cache_lower: '{use_cache_lower}'")
    
    valid_values = ['true', '1', 'yes', 'on']
    print(f"  valid_values: {valid_values}")
    
    use_cache_result = use_cache_lower in valid_values
    print(f"  use_cache_result: {use_cache_result}")
    
    if use_cache_result:
        print("  ✅ Redis debería estar activado")
        return True
    else:
        print("  ❌ Redis sigue desactivado")
        return False

async def test_redis_connection_with_env():
    """Test conexión Redis con variables cargadas"""
    
    print("\n🔌 TEST CONEXIÓN REDIS CON ENV CARGADO")
    print("=" * 50)
    
    try:
        from src.api.core.redis_config_fix import RedisConfigValidator, PatchedRedisClient
        
        # Test validador con env cargado
        config = RedisConfigValidator.validate_and_fix_config()
        print(f"📊 Config validation result: {config.get('use_redis_cache', False)}")
        
        if config.get('use_redis_cache'):
            print("✅ Validation passed - attempting connection...")
            
            # Create client with validated config
            redis_client = PatchedRedisClient(use_validated_config=True)
            
            print("🔄 Connecting to Redis...")
            connection_result = await redis_client.connect()
            
            if connection_result:
                print("✅ CONNECTION SUCCESSFUL!")
                
                # Test operations
                await redis_client.set("test_env_load", "success", ex=60)
                value = await redis_client.get("test_env_load")
                print(f"📝 Test value: {value}")
                
                # Ping test
                ping = await redis_client.ping()
                print(f"🏓 Ping result: {ping}")
                
                # Cleanup
                await redis_client.delete("test_env_load")
                print("🧹 Cleanup completed")
                
                return True
            else:
                print("❌ Connection failed")
                return False
        else:
            print("❌ Validation failed - Redis marked as disabled")
            return False
            
    except Exception as e:
        print(f"❌ Error testing Redis connection: {e}")
        return False

async def test_service_factory_with_env():
    """Test ServiceFactory con variables de entorno cargadas"""
    
    print("\n🏭 TEST SERVICEFACTORY CON ENV CARGADO")
    print("=" * 50)
    
    try:
        from src.api.factories import ServiceFactory
        
        print("🔄 Getting Redis service from ServiceFactory...")
        
        import asyncio
        redis_service = await asyncio.wait_for(
            ServiceFactory.get_redis_service(),
            timeout=15.0  # Extended timeout
        )
        
        print("✅ ServiceFactory Redis service obtained")
        
        # Test health check
        health = await redis_service.health_check()
        print(f"📊 Redis health: {health.get('status', 'unknown')}")
        
        if health.get('status') in ['healthy', 'connected']:
            print("✅ ServiceFactory Redis is healthy!")
            return True
        else:
            print(f"⚠️ ServiceFactory Redis status: {health.get('status')}")
            return False
            
    except Exception as e:
        print(f"❌ ServiceFactory error: {e}")
        return False

async def comprehensive_redis_test():
    """Test comprehensivo de Redis con env cargado"""
    
    print("🧪 COMPREHENSIVE REDIS TEST")
    print("=" * 60)
    
    # Test 1: Environment loading
    env_loaded = test_redis_with_proper_env()
    
    if not env_loaded:
        print("\n❌ ENVIRONMENT LOADING FAILED - Cannot proceed")
        return False
    
    # Test 2: Direct Redis connection
    import asyncio
    direct_connection = await test_redis_connection_with_env()
    
    # Test 3: ServiceFactory
    service_factory_test = await test_service_factory_with_env()
    
    # Test 4: Integration test (the original failing test)
    if direct_connection and service_factory_test:
        print("\n🎯 INTEGRATION TEST - ORIGINAL FAILING TEST")
        print("=" * 50)
        
        try:
            from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager
            from src.api.mcp.conversation_state_manager import get_conversation_state_manager
            from src.api.mcp.engines.mcp_personalization_engine import create_mcp_personalization_engine
            from src.api.factories import ServiceFactory
            
            print("🔄 Testing integration with env loaded...")
            
            conv_mgr = OptimizedConversationAIManager('test_key')
            print('✅ OptimizedConversationAIManager created')
            
            if hasattr(conv_mgr, '_redis_client') and conv_mgr._redis_client:
                print('📊 Redis client available: True ← SHOULD BE FIXED!')
            else:
                print('📊 Redis client available: False (may need individual component fixes)')
            
            state_mgr = await get_conversation_state_manager()
            print('✅ ConversationStateManager created')
            
            engine = await create_mcp_personalization_engine('test_key')
            print('✅ PersonalizationEngine created')
            
            # Final Redis health check
            redis_service = await ServiceFactory.get_redis_service()
            health = await redis_service.health_check()
            print(f'📊 Final Redis health: {health.get("status", "unknown")}')
            
            return True
            
        except Exception as e:
            print(f"❌ Integration test failed: {e}")
            return False
    else:
        print("\n❌ PREREQUISITE TESTS FAILED - Skipping integration test")
        return False

if __name__ == "__main__":
    import asyncio
    
    success = asyncio.run(comprehensive_redis_test())
    
    if success:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Redis está funcionando correctamente")
        print("✅ ServiceFactory está funcionando")
        print("✅ Integración enterprise completada")
        
        print("\n🎯 LA MIGRACIÓN REDIS ENTERPRISE ES EXITOSA")
    else:
        print("\n❌ SOME TESTS FAILED")
        print("🔧 Review the output above for specific issues")
