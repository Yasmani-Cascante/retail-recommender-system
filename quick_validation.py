#!/usr/bin/env python3
"""
Quick Fix Validation
===================

Valida rápidamente los fixes críticos aplicados.
"""

import asyncio
import time
import sys
sys.path.append('src')

async def quick_validation():
    print("🔍 QUICK VALIDATION - CACHE PRIORITY FIXES")
    print("=" * 50)
    
    try:
        # Test 1: Singleton pattern
        print("1. Testing singleton pattern...")
        from src.api.routers.products_router import get_product_cache_dependency
        
        cache1 = await get_product_cache_dependency()
        cache2 = await get_product_cache_dependency()
        
        if cache1 is cache2:
            print("   ✅ Singleton working")
        else:
            print("   ❌ Singleton broken")
        
        # Test 2: Cache method existence
        print("2. Testing cache methods...")
        
        if hasattr(cache1, 'get_cached_product_ids'):
            print("   ✅ get_cached_product_ids exists")
        else:
            print("   ❌ get_cached_product_ids missing")
        
        if hasattr(cache1, '_save_to_redis'):
            print("   ✅ _save_to_redis exists")
        else:
            print("   ❌ _save_to_redis missing")
        
        # Test 3: Basic functionality
        print("3. Testing basic cache functionality...")
        
        test_data = {"id": "test_123", "title": "Test Product"}
        saved = await cache1._save_to_redis("test_123", test_data)
        
        if saved:
            print("   ✅ Basic save working")
        else:
            print("   ❌ Basic save failed")
        
        # Test 4: Popular products
        print("4. Testing popular products...")
        
        popular = await cache1.get_popular_products("US", 5)
        print(f"   Popular products returned: {len(popular)} items")
        
        if len(popular) > 0:
            print("   ✅ Popular products returning data")
        else:
            print("   ⚠️ Popular products empty (may be normal for new cache)")
        
        print("\n✅ Quick validation completed")
        print("Ready to test with real endpoint calls")
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(quick_validation())
