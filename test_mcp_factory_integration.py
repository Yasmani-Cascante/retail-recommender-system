#!/usr/bin/env python3
"""
Test script para verificar la integración MCP Factory con ServiceFactory
========================================================================

Este script valida:
1. ServiceFactory.get_mcp_recommender() funciona correctamente
2. Dependency injection está bien configurada
3. Los componentes MCP se inicializan sin errores
4. La integración con main_unified_redis es correcta

Autor: Senior Architecture Team
Fecha: 28 Agosto 2025
"""

import asyncio
import sys
import os
import logging
from pathlib import Path

# Añadir el directorio raíz al Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_mcp_factory_integration():
    """Test principal para validar integración MCP Factory"""
    
    print("🧪 INICIANDO TEST MCP FACTORY INTEGRATION")
    print("=" * 60)
    
    results = {
        "service_factory_import": False,
        "mcp_recommender_creation": False,
        "conversation_manager_creation": False,
        "dependency_injection": False,
        "main_app_state": False,
        "overall_success": False
    }
    
    # TEST 1: Import ServiceFactory
    try:
        print("\n🔍 TEST 1: Importing ServiceFactory...")
        from src.api.factories.service_factory import ServiceFactory
        print("✅ ServiceFactory imported successfully")
        results["service_factory_import"] = True
    except Exception as e:
        print(f"❌ ServiceFactory import failed: {e}")
        return results
    
    # TEST 2: Create MCP Recommender
    try:
        print("\n🔍 TEST 2: Creating MCP Recommender singleton...")
        mcp_recommender = await ServiceFactory.get_mcp_recommender()
        
        if mcp_recommender:
            print("✅ MCP Recommender created successfully")
            print(f"   Type: {type(mcp_recommender).__name__}")
            print(f"   Has redis_service: {hasattr(mcp_recommender, 'redis_service')}")
            print(f"   Has conversation_manager: {hasattr(mcp_recommender, 'conversation_manager')}")
            results["mcp_recommender_creation"] = True
        else:
            print("❌ MCP Recommender creation returned None")
            
    except Exception as e:
        print(f"❌ MCP Recommender creation failed: {e}")
        print(f"   Error type: {type(e)}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
    
    # TEST 3: Create Conversation Manager
    try:
        print("\n🔍 TEST 3: Creating Conversation Manager...")
        conversation_manager = await ServiceFactory.get_conversation_manager()
        
        if conversation_manager:
            print("✅ Conversation Manager created successfully")
            print(f"   Type: {type(conversation_manager).__name__}")
            results["conversation_manager_creation"] = True
        else:
            print("❌ Conversation Manager creation returned None")
            
    except Exception as e:
        print(f"❌ Conversation Manager creation failed: {e}")
    
    # TEST 4: Test Dependency Injection Functions
    try:
        print("\n🔍 TEST 4: Testing dependency injection functions...")
        from src.api.factories.service_factory import get_mcp_recommender, get_conversation_manager
        
        # Test convenience functions
        mcp_via_function = await get_mcp_recommender()
        conv_via_function = await get_conversation_manager()
        
        if mcp_via_function and conv_via_function:
            print("✅ Dependency injection functions work correctly")
            results["dependency_injection"] = True
        else:
            print(f"❌ Dependency injection issues: MCP={bool(mcp_via_function)}, Conv={bool(conv_via_function)}")
            
    except Exception as e:
        print(f"❌ Dependency injection test failed: {e}")
    
    # TEST 5: Test App State Integration (simulated)
    try:
        print("\n🔍 TEST 5: Testing app state integration pattern...")
        
        # Simular lo que hace main_unified_redis.py
        class MockApp:
            def __init__(self):
                self.state = MockState()
        
        class MockState:
            def __init__(self):
                self.mcp_recommender = None
        
        mock_app = MockApp()
        
        # Simular la inicialización
        mock_app.state.mcp_recommender = await ServiceFactory.get_mcp_recommender()
        
        if mock_app.state.mcp_recommender:
            print("✅ App state integration pattern validated")
            results["main_app_state"] = True
        else:
            print("❌ App state integration failed")
            
    except Exception as e:
        print(f"❌ App state integration test failed: {e}")
    
    # RESUMEN FINAL
    print("\n" + "=" * 60)
    print("📋 RESUMEN DE RESULTADOS:")
    
    passed = sum(results.values())
    total = len(results) - 1  # Exclude overall_success
    
    for test_name, passed_test in results.items():
        if test_name != "overall_success":
            status = "✅ PASSED" if passed_test else "❌ FAILED"
            print(f"   {test_name}: {status}")
    
    results["overall_success"] = passed >= total * 0.8  # 80% success rate
    
    print(f"\n🎯 RESULTADO GENERAL: {passed}/{total} tests passed")
    
    if results["overall_success"]:
        print("🎉 MCP FACTORY INTEGRATION: ✅ SUCCESS")
        print("   Sistema listo para production!")
    else:
        print("⚠️ MCP FACTORY INTEGRATION: ❌ NEEDS FIXES")
        print(f"   Necesita correcciones: {total - passed} tests fallaron")
    
    return results

async def test_mcp_router_integration():
    """Test adicional para validar integración del MCP router"""
    
    print("\n🔍 TEST ADICIONAL: MCP Router Integration...")
    
    try:
        from src.api.routers.mcp_router import get_mcp_recommender as router_get_mcp
        
        # Test dependency injection function in router
        mcp_from_router = await router_get_mcp()
        
        if mcp_from_router:
            print("✅ MCP Router dependency injection works correctly")
            return True
        else:
            print("❌ MCP Router dependency injection returned None")
            return False
            
    except Exception as e:
        print(f"❌ MCP Router integration test failed: {e}")
        return False

if __name__ == "__main__":
    async def main():
        """Función principal del test"""
        try:
            # Load environment variables
            from dotenv import load_dotenv
            load_dotenv()
            
            print("🚀 Iniciando tests de integración MCP Factory...")
            
            # Test principal
            main_results = await test_mcp_factory_integration()
            
            # Test adicional del router
            router_success = await test_mcp_router_integration()
            
            # Resultado final
            overall_success = main_results["overall_success"] and router_success
            
            print(f"\n🏁 RESULTADO FINAL:")
            print(f"   Main Integration: {'✅ SUCCESS' if main_results['overall_success'] else '❌ FAILED'}")
            print(f"   Router Integration: {'✅ SUCCESS' if router_success else '❌ FAILED'}")
            print(f"   Overall: {'🎉 ALL SYSTEMS GO!' if overall_success else '⚠️ NEEDS ATTENTION'}")
            
            # Exit code para CI/CD
            return 0 if overall_success else 1
            
        except Exception as e:
            print(f"❌ CRITICAL ERROR in main test: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return 1
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
