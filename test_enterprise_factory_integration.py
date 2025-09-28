#!/usr/bin/env python3
"""
Test de Validación - Integración Enterprise Factory
=====================================================

Script para validar que las modificaciones realizadas a la arquitectura
de factories funcionan correctamente.

Author: Senior Architecture Team
Version: 2.1.0 - Enterprise Integration Test
"""

import sys
import os
import asyncio
import logging

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_factory_imports():
    """Test that all factory imports work correctly"""
    print("🧪 Testing Factory Imports...")
    
    try:
        # Test __init__.py imports
        from src.api.factories import (
            ServiceFactory, 
            RecommenderFactory, 
            MCPFactory,
            BusinessCompositionRoot,
            InfrastructureCompositionRoot,
            HealthCompositionRoot
        )
        print("✅ All factory imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

async def test_enterprise_integration():
    """Test enterprise integration functionality"""
    print("🧪 Testing Enterprise Integration...")
    
    try:
        from src.api.factories.factories import ENTERPRISE_INTEGRATION_AVAILABLE
        print(f"📊 Enterprise integration available: {ENTERPRISE_INTEGRATION_AVAILABLE}")
        
        if ENTERPRISE_INTEGRATION_AVAILABLE:
            from src.api.factories.factories import RecommenderFactory
            
            # Test that enterprise methods exist
            enterprise_methods = [
                'create_redis_client_enterprise',
                'create_product_cache_enterprise', 
                'create_user_event_store_enterprise'
            ]
            
            for method_name in enterprise_methods:
                if hasattr(RecommenderFactory, method_name):
                    print(f"✅ {method_name} method available")
                else:
                    print(f"❌ {method_name} method missing")
                    return False
        
        return True
    except Exception as e:
        print(f"❌ Enterprise integration test failed: {e}")
        return False

async def test_composition_roots():
    """Test composition root functionality"""
    print("🧪 Testing Composition Roots...")
    
    try:
        from src.api.factories import (
            BusinessCompositionRoot,
            InfrastructureCompositionRoot,
            HealthCompositionRoot
        )
        
        # Test that key methods exist
        business_methods = ['create_recommendation_service', 'create_conversation_service']
        infrastructure_methods = ['create_cache_service', 'create_inventory_service', 'create_redis_infrastructure']
        health_methods = ['comprehensive_health_check']
        
        for method_name in business_methods:
            if hasattr(BusinessCompositionRoot, method_name):
                print(f"✅ BusinessCompositionRoot.{method_name} available")
            else:
                print(f"❌ BusinessCompositionRoot.{method_name} missing")
                return False
        
        for method_name in infrastructure_methods:
            if hasattr(InfrastructureCompositionRoot, method_name):
                print(f"✅ InfrastructureCompositionRoot.{method_name} available")
            else:
                print(f"❌ InfrastructureCompositionRoot.{method_name} missing")
                return False
        
        for method_name in health_methods:
            if hasattr(HealthCompositionRoot, method_name):
                print(f"✅ HealthCompositionRoot.{method_name} available")
            else:
                print(f"❌ HealthCompositionRoot.{method_name} missing")
                return False
        
        return True
    except Exception as e:
        print(f"❌ Composition roots test failed: {e}")
        return False

async def test_legacy_compatibility():
    """Test that legacy methods still work"""
    print("🧪 Testing Legacy Compatibility...")
    
    try:
        from src.api.factories import RecommenderFactory, MCPFactory
        
        # Test that original methods still exist
        legacy_recommender_methods = [
            'create_tfidf_recommender',
            'create_retail_recommender', 
            'create_hybrid_recommender',
            'create_redis_client',
            'create_product_cache'
        ]
        
        legacy_mcp_methods = [
            'create_mcp_client',
            'create_market_manager',
            'create_market_cache',
            'create_mcp_recommender'
        ]
        
        for method_name in legacy_recommender_methods:
            if hasattr(RecommenderFactory, method_name):
                print(f"✅ RecommenderFactory.{method_name} (legacy) available")
            else:
                print(f"❌ RecommenderFactory.{method_name} (legacy) missing")
                return False
        
        for method_name in legacy_mcp_methods:
            if hasattr(MCPFactory, method_name):
                print(f"✅ MCPFactory.{method_name} (legacy) available")
            else:
                print(f"❌ MCPFactory.{method_name} (legacy) missing")
                return False
        
        return True
    except Exception as e:
        print(f"❌ Legacy compatibility test failed: {e}")
        return False

async def test_architecture_validation():
    """Test architecture validation function"""
    print("🧪 Testing Architecture Validation...")
    
    try:
        from src.api.factories import validate_factory_architecture
        
        result = validate_factory_architecture()
        print(f"📊 Architecture validation result: {result}")
        
        return True
    except Exception as e:
        print(f"❌ Architecture validation test failed: {e}")
        return False

async def main():
    """Run all validation tests"""
    print("🚀 Starting Enterprise Factory Validation Tests")
    print("=" * 60)
    
    tests = [
        ("Factory Imports", test_factory_imports),
        ("Enterprise Integration", test_enterprise_integration),
        ("Composition Roots", test_composition_roots),
        ("Legacy Compatibility", test_legacy_compatibility),
        ("Architecture Validation", test_architecture_validation)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        print("-" * 40)
        try:
            result = await test_func()
            results[test_name] = result
            print(f"📊 {test_name}: {'✅ PASSED' if result else '❌ FAILED'}")
        except Exception as e:
            print(f"📊 {test_name}: ❌ ERROR - {e}")
            results[test_name] = False
    
    print("\n" + "=" * 60)
    print("📊 FINAL RESULTS:")
    print("=" * 60)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"   {test_name:<25} {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED - Enterprise Factory Integration Successful!")
        return 0
    else:
        print("⚠️ SOME TESTS FAILED - Review and fix issues before proceeding")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
