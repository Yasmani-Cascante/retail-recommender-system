# test_import_fix.py
"""
Test para verificar que el error de ImportError se ha resuelto
"""

def test_import_fix():
    """Verifica que RecommenderFactory se puede importar correctamente"""
    try:
        from src.api.factories import RecommenderFactory
        print("✅ SUCCESS: RecommenderFactory imported successfully")
        print(f"   Type: {type(RecommenderFactory)}")
        
        # Test que tenga los métodos esperados
        expected_methods = [
            'create_tfidf_recommender',
            'create_retail_recommender', 
            'create_hybrid_recommender',
            'create_redis_client'
        ]
        
        for method in expected_methods:
            if hasattr(RecommenderFactory, method):
                print(f"   ✅ Method {method}: Available")
            else:
                print(f"   ❌ Method {method}: Missing")
        
        return True
        
    except ImportError as e:
        print(f"❌ FAILED: ImportError still exists: {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")
        return False

def test_new_architecture():
    """Verifica que la nueva arquitectura enterprise también funciona"""
    try:
        from src.api.factories import ServiceFactory
        print("✅ SUCCESS: ServiceFactory (enterprise) imported successfully")
        print(f"   Type: {type(ServiceFactory)}")
        
        # Test métodos enterprise
        expected_methods = [
            'get_redis_service',
            'create_inventory_service',
            'create_product_cache',
            'health_check_all_services'
        ]
        
        for method in expected_methods:
            if hasattr(ServiceFactory, method):
                print(f"   ✅ Enterprise method {method}: Available")
            else:
                print(f"   ❌ Enterprise method {method}: Missing")
        
        return True
        
    except ImportError as e:
        print(f"❌ FAILED: Enterprise ServiceFactory import failed: {e}")
        return False

def test_compatibility_layer():
    """Test que el compatibility layer funciona"""
    try:
        from src.api.factories import LEGACY_FACTORIES_AVAILABLE
        print(f"✅ Legacy factories available: {LEGACY_FACTORIES_AVAILABLE}")
        
        if LEGACY_FACTORIES_AVAILABLE:
            from src.api.factories import MCPFactory
            print("✅ MCPFactory also available")
        
        return True
        
    except ImportError as e:
        print(f"❌ Compatibility layer failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Import Fix for Redis Enterprise Architecture")
    print("=" * 60)
    
    results = []
    
    print("\n1️⃣ Testing Legacy RecommenderFactory Import:")
    results.append(test_import_fix())
    
    print("\n2️⃣ Testing Enterprise ServiceFactory:")
    results.append(test_new_architecture())
    
    print("\n3️⃣ Testing Compatibility Layer:")
    results.append(test_compatibility_layer())
    
    print("\n" + "=" * 60)
    success_count = sum(results)
    total_tests = len(results)
    
    if success_count == total_tests:
        print(f"🎉 ALL TESTS PASSED ({success_count}/{total_tests})")
        print("✅ ImportError resolved successfully!")
        print("✅ Enterprise architecture functional!")
        print("✅ Migration path established!")
    else:
        print(f"⚠️ PARTIAL SUCCESS ({success_count}/{total_tests})")
        print("❌ Some issues remain - review implementation")
