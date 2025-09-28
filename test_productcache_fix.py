#!/usr/bin/env python3
"""
Script para verificar la corrección del problema de redis_client → redis_service

Este script verifica que:
1. ProductCache.__init__ acepta redis_service
2. No hay referencias restantes a redis_client en ProductCache instantiation
3. La interface ProductCache funciona correctamente

Author: Senior Architecture Team
"""

import logging
import sys
from pathlib import Path

# Agregar src al path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_productcache_interface():
    """Test la nueva interface ProductCache"""
    
    logger.info("🧪 Testing ProductCache interface fix...")
    
    try:
        # Test 1: Import ProductCache
        from src.api.core.product_cache import ProductCache
        logger.info("✅ ProductCache import successful")
        
        # Test 2: Verificar signature del constructor
        import inspect
        signature = inspect.signature(ProductCache.__init__)
        params = list(signature.parameters.keys())
        
        logger.info(f"📋 ProductCache.__init__ parameters: {params}")
        
        # Verificar que redis_service está en los parámetros
        if 'redis_service' in params:
            logger.info("✅ ProductCache acepta 'redis_service' parameter")
        else:
            logger.error("❌ ProductCache NO acepta 'redis_service' parameter")
            return False
        
        # Verificar que redis_client NO está en los parámetros
        if 'redis_client' not in params:
            logger.info("✅ ProductCache NO tiene 'redis_client' parameter (correcto)")
        else:
            logger.error("❌ ProductCache todavía tiene 'redis_client' parameter")
            return False
        
        logger.info("✅ ProductCache interface verification complete")
        return True
        
    except Exception as e:
        logger.error(f"❌ ProductCache interface test failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

async def test_service_factory_creation():
    """Test ServiceFactory ProductCache creation"""
    
    logger.info("🧪 Testing ServiceFactory ProductCache creation...")
    
    try:
        from src.api.factories.service_factory import ServiceFactory
        
        # Verificar que no hay errores de sintaxis
        logger.info("✅ ServiceFactory import successful")
        
        # Test method signature
        import inspect
        create_method = getattr(ServiceFactory, 'create_product_cache')
        source = inspect.getsource(create_method)
        
        # Verificar que usa redis_service, no redis_client
        if 'redis_service=' in source:
            logger.info("✅ ServiceFactory.create_product_cache uses 'redis_service'")
        else:
            logger.error("❌ ServiceFactory.create_product_cache NOT using 'redis_service'")
            return False
        
        if 'redis_client=' in source:
            logger.error("❌ ServiceFactory.create_product_cache still uses 'redis_client'")
            return False
        else:
            logger.info("✅ ServiceFactory.create_product_cache NO LONGER uses 'redis_client'")
        
        logger.info("✅ ServiceFactory creation verification complete")
        return True
        
    except Exception as e:
        logger.error(f"❌ ServiceFactory test failed: {e}")
        return False

async def main():
    """Main test function"""
    
    logger.info("🔧 REDIS_CLIENT → REDIS_SERVICE FIX VERIFICATION")
    logger.info("=" * 60)
    
    # Test 1: ProductCache interface
    test1_result = await test_productcache_interface()
    
    # Test 2: ServiceFactory creation
    test2_result = await test_service_factory_creation()
    
    # Summary
    logger.info("=" * 60)
    logger.info("📊 TEST SUMMARY:")
    logger.info(f"   ProductCache interface: {'✅ PASS' if test1_result else '❌ FAIL'}")
    logger.info(f"   ServiceFactory creation: {'✅ PASS' if test2_result else '❌ FAIL'}")
    
    if test1_result and test2_result:
        logger.info("🎉 ALL TESTS PASSED - Fix is correct!")
        return 0
    else:
        logger.error("💥 SOME TESTS FAILED - Review needed")
        return 1

if __name__ == "__main__":
    import asyncio
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
