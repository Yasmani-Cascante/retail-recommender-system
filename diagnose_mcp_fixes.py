#!/usr/bin/env python3
"""
🔍 SCRIPT DE DIAGNÓSTICO POST-CORRECCIÓN
Verifica que todas las correcciones se hayan aplicado correctamente.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Agregar ruta del proyecto
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mcp_conversation_fixes():
    """Prueba las correcciones del endpoint MCP conversation."""
    
    logger.info("🔍 Iniciando diagnóstico de correcciones MCP...")
    
    try:
        # 1. Verificar importación del validador
        from src.api.core.product_data_validator import ProductDataValidator
        logger.info("✅ ProductDataValidator importado correctamente")
        
        # 2. Probar validación de productos
        test_product = {
            "id": "test_123",
            "title": "Producto de Prueba",
            "body_html": None,  # Valor None que causaba problemas
            "product_type": None,
            "variants": [{"price": "29.99", "id": "var1"}]
        }
        
        normalized = ProductDataValidator.validate_and_normalize_product(test_product)
        assert normalized["body_html"] == ""  # None convertido a string vacío
        assert normalized["product_type"] == "General"  # None convertido a default
        assert normalized["price"] == 29.99  # String convertido a float
        logger.info("✅ Validación de productos funciona correctamente")
        
        # 3. Verificar MCPAwareHybridRecommender
        try:
            from src.recommenders.mcp_aware_hybrid import MCPAwareHybridRecommender
            
            # Verificar que el método acepta parámetros keyword
            import inspect
            sig = inspect.signature(MCPAwareHybridRecommender.get_recommendations)
            params = list(sig.parameters.keys())
            
            required_params = ['user_id', 'product_id', 'n_recommendations', 'market_id']
            missing_params = [p for p in required_params if p not in params]
            
            if missing_params:
                logger.error(f"❌ MCPAwareHybridRecommender.get_recommendations falta parámetros: {missing_params}")
            else:
                logger.info("✅ MCPAwareHybridRecommender tiene interfaz correcta")
                
        except ImportError as e:
            logger.error(f"❌ Error importando MCPAwareHybridRecommender: {e}")
        
        # 4. Verificar estructura de datos de recomendaciones
        test_recommendation = {
            "id": None,  # Valor None que causaba problemas
            "title": "",
            "description": None,
            "price": "invalid_price"
        }
        
        normalized_rec = ProductDataValidator.validate_recommendation_data(test_recommendation)
        assert normalized_rec["id"] == "unknown"  # None convertido a string
        assert normalized_rec["price"] == 0.0  # Precio inválido convertido a 0.0
        logger.info("✅ Validación de recomendaciones funciona correctamente")
        
        logger.info("🎉 Todas las correcciones verificadas exitosamente!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en diagnóstico: {e}")
        return False

async def test_redis_connection():
    """Prueba la conexión Redis y circuit breakers."""
    try:
        from src.api.core.redis_config_fix import RedisConfigValidator
        
        config = RedisConfigValidator.validate_and_fix_config()
        if config.get('use_redis_cache'):
            logger.info("✅ Configuración Redis validada")
        else:
            logger.warning("⚠️ Redis deshabilitado - funcionará sin caché")
            
    except Exception as e:
        logger.error(f"❌ Error verificando Redis: {e}")

if __name__ == "__main__":
    async def main():
        success = await test_mcp_conversation_fixes()
        await test_redis_connection()
        
        if success:
            print("\n🎉 DIAGNÓSTICO EXITOSO - Las correcciones están funcionando!")
            sys.exit(0)
        else:
            print("\n❌ DIAGNÓSTICO FALLÓ - Revisar logs para más detalles")
            sys.exit(1)
    
    asyncio.run(main())
