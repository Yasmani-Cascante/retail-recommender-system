#!/usr/bin/env python3
"""
🧪 Validación de la Nueva Arquitectura Redis
============================================

Valida que la refactorización arquitectónica funciona correctamente.
"""

import sys
import asyncio
sys.path.append('src')

async def test_redis_service():
    """Test del nuevo RedisService"""
    print("🧪 Testing RedisService...")
    
    try:
        from src.api.core.redis_service import get_redis_service
        
        # Obtener servicio
        service = await get_redis_service()
        print("✅ RedisService instance obtenida")
        
        # Health check
        health = await service.health_check()
        print(f"✅ Health check: {health['status']}")
        
        # Test operaciones básicas
        test_key = "test:architecture:validation"
        test_value = {"message": "Nueva arquitectura funcionando", "timestamp": "2025-08-07"}
        
        # Test SET
        set_result = await service.set_json(test_key, test_value, ttl=60)
        print(f"✅ SET operation: {set_result}")
        
        # Test GET
        get_result = await service.get_json(test_key)
        print(f"✅ GET operation: {get_result}")
        
        # Test DELETE
        del_result = await service.delete(test_key)
        print(f"✅ DELETE operation: {del_result}")
        
        # Stats
        stats = service.get_stats()
        print(f"✅ Service stats: hit_ratio={stats['hit_ratio']:.2f}, operations={stats['operations_total']}")
        
        return True
        
    except Exception as e:
        print(f"❌ RedisService test failed: {e}")
        return False

async def test_inventory_service():
    """Test del InventoryService refactorizado"""
    print("\n🧪 Testing InventoryService...")
    
    try:
        from src.api.inventory.inventory_service import create_inventory_service
        
        # Crear servicio (RedisService se inicializa automáticamente)
        service = create_inventory_service()
        print("✅ InventoryService creado")
        
        # Test availability check
        inventory_info = await service.check_product_availability("test_product", "US")
        print(f"✅ Availability check: {inventory_info.status.value}")
        
        # Test múltiples productos
        multi_result = await service.check_multiple_products_availability(
            ["prod_001", "prod_002"], "US"
        )
        print(f"✅ Multiple products check: {len(multi_result)} productos procesados")
        
        return True
        
    except Exception as e:
        print(f"❌ InventoryService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_products_router():
    """Test de products_router factories"""
    print("\n🧪 Testing ProductsRouter factories...")
    
    try:
        from src.api.routers.products_router import get_inventory_service, get_product_cache
        
        # Test inventory service factory
        inventory_service = get_inventory_service()
        print("✅ get_inventory_service() funcionando")
        
        # Test product cache factory
        product_cache = get_product_cache()
        print(f"✅ get_product_cache() funcionando: {type(product_cache)}")
        
        return True
        
    except Exception as e:
        print(f"❌ ProductsRouter test failed: {e}")
        return False

async def main():
    """Ejecutar todas las validaciones"""
    print("🚀 === VALIDACIÓN ARQUITECTURA REDIS FASE 1 ===\n")
    
    results = []
    
    # Test RedisService
    results.append(await test_redis_service())
    
    # Test InventoryService  
    results.append(await test_inventory_service())
    
    # Test ProductsRouter
    results.append(await test_products_router())
    
    # Resultado final
    print("\n📊 === RESULTADOS ===")
    total_tests = len(results)
    passed_tests = sum(results)
    
    print(f"Tests ejecutados: {total_tests}")
    print(f"Tests exitosos: {passed_tests}")
    print(f"Tests fallidos: {total_tests - passed_tests}")
    
    if passed_tests == total_tests:
        print("\n🎉 ¡TODAS LAS VALIDACIONES EXITOSAS!")
        print("✅ La nueva arquitectura Redis está funcionando correctamente")
        print("✅ Sistema listo para Fase 2 (Repository Pattern)")
    else:
        print(f"\n⚠️ {total_tests - passed_tests} validaciones fallaron")
        print("❌ Revisar implementación antes de continuar")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    asyncio.run(main())
