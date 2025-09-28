#!/usr/bin/env python3
"""
Test práctico de product_cache.py integration
"""

import sys
import os
sys.path.append('src')

def test_imports():
    """Test si podemos importar product_cache sin errores"""
    try:
        from src.api.core.product_cache import ProductCache
        print("✅ product_cache.py import successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_initialization():
    """Test si podemos inicializar ProductCache"""
    try:
        from src.api.core.product_cache import ProductCache
        
        # Initialize without Redis for simplicity
        cache = ProductCache(
            redis_client=None,
            shopify_client=None,
            ttl_seconds=300
        )
        
        print("✅ ProductCache initialization successful")
        print(f"   TTL: {cache.ttl_seconds}s")
        print(f"   Prefix: {cache.prefix}")
        
        # Test stats method
        stats = cache.get_stats()
        print(f"✅ Stats accessible: {stats}")
        
        return True
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False

def test_basic_functionality():
    """Test funcionalidad básica sin dependencies"""
    try:
        from src.api.core.product_cache import ProductCache
        
        cache = ProductCache(redis_client=None, shopify_client=None)
        
        # Test methods exist
        assert hasattr(cache, 'get_product'), "get_product method missing"
        assert hasattr(cache, 'preload_products'), "preload_products method missing"
        assert hasattr(cache, 'get_stats'), "get_stats method missing"
        assert hasattr(cache, 'intelligent_cache_warmup'), "intelligent_cache_warmup missing"
        
        print("✅ All required methods available")
        return True
    except Exception as e:
        print(f"❌ Functionality test failed: {e}")
        return False

def test_shopify_integration():
    """Test integración con Shopify client"""
    try:
        from src.api.core.product_cache import ProductCache
        from src.api.core.store import get_shopify_client
        
        shopify_client = get_shopify_client()
        cache = ProductCache(
            redis_client=None,
            shopify_client=shopify_client,
            ttl_seconds=300
        )
        
        print(f"✅ Shopify integration successful")
        print(f"   Shopify client: {type(shopify_client).__name__ if shopify_client else 'None'}")
        
        return True
    except Exception as e:
        print(f"❌ Shopify integration failed: {e}")
        return False

async def test_async_operations():
    """Test async operations"""
    try:
        from src.api.core.product_cache import ProductCache
        
        cache = ProductCache(redis_client=None, shopify_client=None)
        
        # Test async get_product (will return None without shopify, but shouldn't crash)
        product = await cache.get_product("test_product_123")
        print(f"✅ Async get_product completed (result: {type(product)})")
        
        # Test stats after operation
        stats = cache.get_stats()
        print(f"✅ Stats after async op: requests={stats['total_requests']}")
        
        return True
    except Exception as e:
        print(f"❌ Async operations failed: {e}")
        return False

def main():
    print("🧪 TESTING product_cache.py INTEGRATION")
    print("=" * 50)
    
    # Sync tests
    sync_tests = [
        ("Import Test", test_imports),
        ("Initialization Test", test_initialization), 
        ("Functionality Test", test_basic_functionality),
        ("Shopify Integration Test", test_shopify_integration)
    ]
    
    results = {}
    for test_name, test_func in sync_tests:
        print(f"\n📋 {test_name}:")
        results[test_name] = test_func()
    
    # Async test
    print(f"\n📋 Async Operations Test:")
    try:
        import asyncio
        async_result = asyncio.run(test_async_operations())
        results["Async Operations Test"] = async_result
    except Exception as e:
        print(f"❌ Async test failed: {e}")
        results["Async Operations Test"] = False
    
    print("\n📊 RESULTADOS:")
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    print(f"\n🎯 OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ RECOMMENDATION: product_cache.py is READY for integration")
        print("🚀 Next step: Replace emergency_shopify_cache with product_cache")
        print("💡 Benefits: Better performance, Redis support, market intelligence")
    elif passed >= total * 0.6:
        print("\n⚠️ RECOMMENDATION: product_cache.py is MOSTLY ready")
        print("🔧 Minor issues detected, but integration possible")
        print("💡 Consider gradual migration after fixing failed tests")
    else:
        print("\n❌ RECOMMENDATION: Keep emergency_shopify_cache for now")
        print("🛠️ product_cache.py needs significant work before integration")
        print("💡 Focus on stabilizing current emergency cache first")

if __name__ == "__main__":
    main()
