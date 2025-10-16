"""
Quick Test Script - Fase 1 Validation
=====================================

Tests básicos para validar que las modificaciones funcionan correctamente.

Autor: Senior Architecture Team
Fecha: 2025-10-15
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

async def test_imports():
    """Test 1: Validar que los imports funcionan"""
    print("🧪 Test 1: Imports validation")
    try:
        from src.api.factories.service_factory import ServiceFactory
        print("   ✅ ServiceFactory imported successfully")
        
        # Verificar que los métodos existen
        assert hasattr(ServiceFactory, 'get_tfidf_recommender'), "get_tfidf_recommender missing"
        print("   ✅ get_tfidf_recommender() exists")
        
        assert hasattr(ServiceFactory, 'get_retail_recommender'), "get_retail_recommender missing"
        print("   ✅ get_retail_recommender() exists")
        
        assert hasattr(ServiceFactory, 'get_hybrid_recommender'), "get_hybrid_recommender missing"
        print("   ✅ get_hybrid_recommender() exists")
        
        # Verificar class variables
        assert hasattr(ServiceFactory, '_tfidf_recommender'), "_tfidf_recommender missing"
        print("   ✅ _tfidf_recommender class variable exists")
        
        assert hasattr(ServiceFactory, '_retail_recommender'), "_retail_recommender missing"
        print("   ✅ _retail_recommender class variable exists")
        
        assert hasattr(ServiceFactory, '_hybrid_recommender'), "_hybrid_recommender missing"
        print("   ✅ _hybrid_recommender class variable exists")
        
        print("✅ Test 1 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Test 1 FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False

async def test_tfidf_singleton():
    """Test 2: Validar singleton pattern de TF-IDF"""
    print("🧪 Test 2: TF-IDF Singleton Pattern")
    try:
        from src.api.factories.service_factory import ServiceFactory
        
        # Get two instances
        print("   Creating first instance...")
        r1 = await ServiceFactory.get_tfidf_recommender()
        print(f"   r1 ID: {id(r1)}")
        
        print("   Creating second instance...")
        r2 = await ServiceFactory.get_tfidf_recommender()
        print(f"   r2 ID: {id(r2)}")
        
        # Should be same instance
        assert r1 is r2, "Not a singleton! Different instances returned"
        print(f"   ✅ Singleton works: {id(r1)} == {id(r2)}")
        
        # Check type
        print(f"   Type: {type(r1).__name__}")
        
        print("✅ Test 2 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Test 2 FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False

async def test_retail_singleton():
    """Test 3: Validar singleton pattern de Retail API"""
    print("🧪 Test 3: Retail API Singleton Pattern")
    print("   ⚠️ Note: This may take 4+ seconds (Google Cloud init)")
    try:
        from src.api.factories.service_factory import ServiceFactory
        import time
        
        # Get first instance (may be slow)
        start = time.time()
        print("   Creating first instance...")
        r1 = await ServiceFactory.get_retail_recommender()
        elapsed1 = time.time() - start
        print(f"   r1 created in {elapsed1:.2f}s, ID: {id(r1)}")
        
        # Get second instance (should be fast - singleton)
        start = time.time()
        print("   Creating second instance...")
        r2 = await ServiceFactory.get_retail_recommender()
        elapsed2 = time.time() - start
        print(f"   r2 created in {elapsed2:.2f}s, ID: {id(r2)}")
        
        # Should be same instance
        assert r1 is r2, "Not a singleton! Different instances returned"
        print(f"   ✅ Singleton works: {id(r1)} == {id(r2)}")
        
        # Second call should be much faster
        if elapsed2 < 0.01:
            print(f"   ✅ Singleton performance: {elapsed2*1000:.1f}ms (cached)")
        
        print("✅ Test 3 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Test 3 FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False

async def test_hybrid_auto_wiring():
    """Test 4: Validar auto-wiring de Hybrid"""
    print("🧪 Test 4: Hybrid Auto-Wiring")
    try:
        from src.api.factories.service_factory import ServiceFactory
        
        print("   Creating hybrid with auto-wiring...")
        hybrid = await ServiceFactory.get_hybrid_recommender()
        
        # Verify dependencies were auto-wired
        assert hybrid is not None, "Hybrid is None"
        print(f"   ✅ Hybrid created: {type(hybrid).__name__}")
        
        assert hasattr(hybrid, 'content_recommender'), "Missing content_recommender"
        assert hybrid.content_recommender is not None, "content_recommender is None"
        print(f"   ✅ content_recommender auto-wired: {type(hybrid.content_recommender).__name__}")
        
        assert hasattr(hybrid, 'retail_recommender'), "Missing retail_recommender"
        assert hybrid.retail_recommender is not None, "retail_recommender is None"
        print(f"   ✅ retail_recommender auto-wired: {type(hybrid.retail_recommender).__name__}")
        
        assert hasattr(hybrid, 'product_cache'), "Missing product_cache"
        # product_cache can be None in some setups, that's OK
        print(f"   ✅ product_cache present: {hybrid.product_cache is not None}")
        
        # Verify it's a singleton
        hybrid2 = await ServiceFactory.get_hybrid_recommender()
        assert hybrid is hybrid2, "Not a singleton!"
        print(f"   ✅ Singleton confirmed: {id(hybrid)} == {id(hybrid2)}")
        
        print("✅ Test 4 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Test 4 FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False

async def test_concurrent_access():
    """Test 5: Validar thread-safety con acceso concurrent"""
    print("🧪 Test 5: Concurrent Access (Thread Safety)")
    try:
        from src.api.factories.service_factory import ServiceFactory
        
        print("   Creating 10 concurrent requests...")
        
        # Create 10 concurrent tasks
        tasks = [ServiceFactory.get_tfidf_recommender() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should be the same instance
        first = results[0]
        all_same = all(r is first for r in results)
        
        assert all_same, "Thread safety issue! Different instances returned"
        print(f"   ✅ All 10 requests returned same singleton")
        print(f"   ✅ Instance ID: {id(first)}")
        
        print("✅ Test 5 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Test 5 FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False

async def test_all_three_together():
    """Test 6: Validar que los 3 métodos funcionan juntos"""
    print("🧪 Test 6: All Three Methods Together")
    try:
        from src.api.factories.service_factory import ServiceFactory
        
        print("   Getting TF-IDF...")
        tfidf = await ServiceFactory.get_tfidf_recommender()
        print(f"   ✅ TF-IDF: {type(tfidf).__name__}")
        
        print("   Getting Retail API...")
        retail = await ServiceFactory.get_retail_recommender()
        print(f"   ✅ Retail: {type(retail).__name__}")
        
        print("   Getting Hybrid...")
        hybrid = await ServiceFactory.get_hybrid_recommender()
        print(f"   ✅ Hybrid: {type(hybrid).__name__}")
        
        # Verify hybrid uses the singletons
        assert hybrid.content_recommender is tfidf, "Hybrid not using TF-IDF singleton"
        print("   ✅ Hybrid uses TF-IDF singleton")
        
        assert hybrid.retail_recommender is retail, "Hybrid not using Retail singleton"
        print("   ✅ Hybrid uses Retail singleton")
        
        print("✅ Test 6 PASSED\n")
        return True
        
    except Exception as e:
        print(f"❌ Test 6 FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False

async def run_all_tests():
    """Run all tests"""
    print("="*60)
    print("🚀 FASE 1 VALIDATION TEST SUITE")
    print("="*60)
    print()
    
    results = []
    
    # Test 1: Imports
    results.append(await test_imports())
    
    # Test 2: TF-IDF Singleton
    results.append(await test_tfidf_singleton())
    
    # Test 3: Retail Singleton (slow)
    # Uncomment if you want to test (takes 4+ seconds)
    # results.append(await test_retail_singleton())
    print("⏭️  Test 3 SKIPPED (Retail API init is slow, uncomment to run)\n")
    
    # Test 4: Hybrid Auto-wiring
    results.append(await test_hybrid_auto_wiring())
    
    # Test 5: Concurrent Access
    results.append(await test_concurrent_access())
    
    # Test 6: All Three Together
    results.append(await test_all_three_together())
    
    # Summary
    print("="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED! 🎉")
        print("Status: READY FOR COMMIT")
        return True
    else:
        print("\n❌ SOME TESTS FAILED")
        print("Status: NEEDS FIXING")
        return False

if __name__ == "__main__":
    print("Starting tests...\n")
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
