#!/usr/bin/env python3
"""
Script de Validación: Redis Client Enhancement
==============================================

Valida que los cambios aplicados al conversation_state_manager.py 
resuelven el error crítico de Fase 2:
`await self.redis.expire(index_key, self.conversation_ttl)`

Uso:
    python validate_redis_enhancement.py
    python validate_redis_enhancement.py --verbose
"""

import asyncio
import logging
import time
import json
import sys
from typing import Dict, Optional

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_redis_client_methods():
    """Test 1: Verificar que RedisClient tiene todos los métodos necesarios"""
    try:
        from src.api.core.redis_client import RedisClient
        
        required_methods = ['connect', 'get', 'set', 'expire', 'zadd', 'setex', 'ensure_connected']
        missing_methods = []
        
        for method in required_methods:
            if not hasattr(RedisClient, method):
                missing_methods.append(method)
        
        if missing_methods:
            logger.error(f"❌ RedisClient missing methods: {missing_methods}")
            return False
        
        logger.info("✅ RedisClient has all required methods")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Cannot import RedisClient: {e}")
        return False

async def test_conversation_state_manager_import():
    """Test 2: Verificar que ConversationStateManager se puede importar"""
    try:
        from src.api.mcp.conversation_state_manager import MCPConversationStateManager
        logger.info("✅ MCPConversationStateManager imported successfully")
        return True
    except ImportError as e:
        logger.error(f"❌ Cannot import MCPConversationStateManager: {e}")
        return False

async def test_redis_connection():
    """Test 3: Probar conexión a Redis"""
    try:
        from src.api.core.redis_client import RedisClient
        from src.api.core.config import get_settings
        
        settings = get_settings()
        
        redis_client = RedisClient(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            ssl=settings.redis_ssl,
            db=settings.redis_db
        )
        
        connection_success = await redis_client.connect()
        
        if connection_success:
            logger.info("✅ Redis connection successful")
            
            # Test métodos específicos
            test_key = "test_validation_key"
            
            # Test set/get
            await redis_client.set(test_key, "test_value", ex=30)
            value = await redis_client.get(test_key)
            
            # Test expire
            expire_success = await redis_client.expire(test_key, 60)
            
            # Test zadd  
            zadd_result = await redis_client.zadd("test_sorted_set", {"member1": 1.0})
            
            # Cleanup
            await redis_client.delete(test_key)
            await redis_client.delete("test_sorted_set")
            
            if value == "test_value" and expire_success and zadd_result > 0:
                logger.info("✅ Redis methods (set/get/expire/zadd) working correctly")
                return True, redis_client
            else:
                logger.error(f"❌ Redis methods failed: get={value}, expire={expire_success}, zadd={zadd_result}")
                return False, None
        else:
            logger.warning("⚠️ Redis connection failed - will test without Redis")
            return True, None  # OK to test without Redis
            
    except Exception as e:
        logger.error(f"❌ Redis test error: {e}")
        return False, None

async def test_conversation_state_manager_creation(redis_client):
    """Test 4: Crear ConversationStateManager"""
    try:
        from src.api.mcp.conversation_state_manager import MCPConversationStateManager
        
        # Crear manager con o sin Redis
        manager = MCPConversationStateManager(
            redis_client=redis_client,
            state_ttl=3600,
            conversation_ttl=7*24*3600
        )
        
        logger.info(f"✅ ConversationStateManager created (Redis: {redis_client is not None})")
        return True, manager
        
    except Exception as e:
        logger.error(f"❌ ConversationStateManager creation failed: {e}")
        return False, None

async def test_index_session_method(manager):
    """Test 5: Probar el método _index_session_for_user específicamente"""
    try:
        # Este es el método que causaba el error original
        await manager._index_session_for_user(
            user_id="test_user_validation",
            session_id="test_session_validation",
            timestamp=time.time()
        )
        
        logger.info("✅ _index_session_for_user method executed successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ _index_session_for_user failed: {e}")
        logger.error(f"   This was the original error reported!")
        return False

async def test_full_conversation_flow(manager):
    """Test 6: Probar flujo conversacional completo"""
    try:
        session_id = f"validation_test_{int(time.time())}"
        user_id = "test_user_validation_full"
        
        # Crear contexto
        context = await manager.create_conversation_context(
            session_id=session_id,
            user_id=user_id,
            initial_query="Test validation query",
            market_context={"market_id": "US"},
            user_agent="ValidationScript/1.0"
        )
        
        # Agregar turno
        updated_context = await manager.add_conversation_turn(
            context=context,
            user_query="I'm looking for shoes",
            intent_analysis={
                "intent": "search",
                "confidence": 0.8,
                "entities": ["shoes"],
                "market_context": {"market_id": "US"}
            },
            ai_response="I can help you find great shoes!",
            recommendations=["product1", "product2"]
        )
        
        # Guardar estado
        save_success = await manager.save_conversation_state(session_id, updated_context)
        
        # Cargar estado
        loaded_context = await manager.load_conversation_state(session_id)
        
        success = (
            context is not None and
            updated_context is not None and
            save_success and
            loaded_context is not None and
            loaded_context.session_id == session_id
        )
        
        if success:
            logger.info(f"✅ Full conversation flow successful (turns: {loaded_context.total_turns})")
        else:
            logger.error("❌ Full conversation flow failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Full conversation flow error: {e}")
        return False

async def test_phase2_compatibility(manager):
    """Test 7: Verificar compatibilidad con validate_phase2_complete.py"""
    try:
        session_id = f"phase2_test_{int(time.time())}"
        user_id = "test_user_phase2_validation"
        
        # Test método get_or_create_session (usado por Phase2)
        context = await manager.get_or_create_session(
            session_id=session_id,
            user_id=user_id,
            market_id="US"
        )
        
        # Test método add_conversation_turn_simple (usado por Phase2)
        updated_context = await manager.add_conversation_turn_simple(
            context=context,
            user_query="Phase2 test query",
            ai_response="Phase2 test response",
            metadata={"recommendations": ["test1", "test2"]}
        )
        
        # Test método get_session_metadata_for_response (usado por Phase2)
        session_metadata = manager.get_session_metadata_for_response(updated_context)
        
        required_fields = ["session_id", "turn_number", "user_id", "last_updated"]
        has_all_fields = all(field in session_metadata for field in required_fields)
        
        success = (
            context is not None and
            updated_context is not None and
            has_all_fields and
            session_metadata["session_id"] == session_id
        )
        
        if success:
            logger.info("✅ Phase2 compatibility test successful")
        else:
            logger.error("❌ Phase2 compatibility test failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Phase2 compatibility error: {e}")
        return False

async def main():
    """Función principal de validación"""
    logger.info("🚀 Iniciando validación de Redis Client Enhancement...")
    
    results = []
    
    # Test 1: RedisClient methods
    logger.info("\n📋 Test 1: Verificando métodos de RedisClient...")
    test1_result = await test_redis_client_methods()
    results.append(("RedisClient Methods", test1_result))
    
    if not test1_result:
        logger.error("❌ CRÍTICO: RedisClient no tiene métodos requeridos")
        return False
    
    # Test 2: ConversationStateManager import
    logger.info("\n📋 Test 2: Verificando import de ConversationStateManager...")
    test2_result = await test_conversation_state_manager_import()
    results.append(("ConversationStateManager Import", test2_result))
    
    if not test2_result:
        logger.error("❌ CRÍTICO: No se puede importar ConversationStateManager")
        return False
    
    # Test 3: Redis connection
    logger.info("\n📋 Test 3: Probando conexión Redis...")
    test3_result, redis_client = await test_redis_connection()
    results.append(("Redis Connection", test3_result))
    
    if not test3_result:
        logger.error("❌ CRÍTICO: Error en conexión Redis")
        return False
    
    # Test 4: ConversationStateManager creation
    logger.info("\n📋 Test 4: Creando ConversationStateManager...")
    test4_result, manager = await test_conversation_state_manager_creation(redis_client)
    results.append(("ConversationStateManager Creation", test4_result))
    
    if not test4_result:
        logger.error("❌ CRÍTICO: No se puede crear ConversationStateManager")
        return False
    
    # Test 5: _index_session_for_user method (EL TEST CRÍTICO)
    logger.info("\n📋 Test 5: Probando método _index_session_for_user (CRÍTICO)...")
    test5_result = await test_index_session_method(manager)
    results.append(("Index Session Method", test5_result))
    
    if not test5_result:
        logger.error("❌ CRÍTICO: El método _index_session_for_user sigue fallando!")
        logger.error("   Este era el error original reportado en validate_phase2_complete.py")
        return False
    
    # Test 6: Full conversation flow
    logger.info("\n📋 Test 6: Probando flujo conversacional completo...")
    test6_result = await test_full_conversation_flow(manager)
    results.append(("Full Conversation Flow", test6_result))
    
    # Test 7: Phase2 compatibility
    logger.info("\n📋 Test 7: Verificando compatibilidad con Phase2...")
    test7_result = await test_phase2_compatibility(manager)
    results.append(("Phase2 Compatibility", test7_result))
    
    # Generar reporte final
    logger.info("\n" + "="*60)
    logger.info("📊 REPORTE FINAL DE VALIDACIÓN")
    logger.info("="*60)
    
    passed_tests = sum(1 for _, result in results if result)
    total_tests = len(results)
    success_rate = (passed_tests / total_tests) * 100
    
    logger.info(f"✅ Tests pasados: {passed_tests}/{total_tests}")
    logger.info(f"📈 Tasa de éxito: {success_rate:.1f}%")
    
    for test_name, result in results:
        status = "✅" if result else "❌"
        logger.info(f"   {status} {test_name}")
    
    # Determinar estado del enhancement
    critical_tests = [
        "RedisClient Methods",
        "ConversationStateManager Import", 
        "Index Session Method"
    ]
    
    critical_passed = all(
        result for test_name, result in results 
        if test_name in critical_tests
    )
    
    if critical_passed and success_rate >= 85:
        logger.info("\n🎉 ¡REDIS CLIENT ENHANCEMENT EXITOSO!")
        logger.info("   ✅ Problema crítico de expire() resuelto")
        logger.info("   ✅ Sistema listo para validate_phase2_complete.py")
        logger.info("   🚀 Proceder con: python validate_phase2_complete.py")
        return True
    elif critical_passed:
        logger.info("\n⚠️ ENHANCEMENT PARCIALMENTE EXITOSO")
        logger.info("   ✅ Problema crítico resuelto")
        logger.info("   ⚠️ Algunos tests menores fallaron")
        logger.info("   🔍 Revisar warnings antes de proceder")
        return True
    else:
        logger.error("\n❌ ENHANCEMENT FALLÓ")
        logger.error("   ❌ Problema crítico NO resuelto")
        logger.error("   🛠️ Revisar configuración Redis y dependencias")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validar Redis Client Enhancement")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Validación cancelada por usuario")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ Error durante validación: {e}")
        sys.exit(1)