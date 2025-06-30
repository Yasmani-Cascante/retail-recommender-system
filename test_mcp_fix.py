#!/usr/bin/env python3
"""
Script de prueba para verificar que el fix del MCP está funcionando
Versión corregida con soporte para asyncio
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
import asyncio
from src.api.factories import MCPFactory, RecommenderFactory

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def test_mcp_client_creation():
    """Prueba la creación del cliente MCP"""
    logger.info("🧪 Probando creación de cliente MCP...")
    
    mcp_client = await MCPFactory.create_mcp_client_async()
    
    if mcp_client is None:
        logger.error("❌ No se pudo crear cliente MCP")
        return False
    
    logger.info(f"✅ Cliente MCP creado: {type(mcp_client).__name__}")
    logger.info(f"✅ Tiene get_metrics: {hasattr(mcp_client, 'get_metrics')}")
    
    if hasattr(mcp_client, 'get_metrics'):
        try:
            metrics = await mcp_client.get_metrics()
            logger.info(f"✅ get_metrics() funciona: {type(metrics)}")
            logger.info(f"📊 Métricas: {metrics}")
            return True
        except Exception as e:
            logger.error(f"❌ Error llamando get_metrics(): {e}")
            return False
    else:
        logger.error("❌ Cliente MCP no tiene método get_metrics")
        return False

async def test_mcp_recommender_creation():
    """Prueba la creación del recomendador MCP"""
    logger.info("🧪 Probando creación de recomendador MCP...")
    
    try:
        # Crear componentes básicos
        tfidf_recommender = await RecommenderFactory.create_tfidf_recommender_async()
        retail_recommender = await RecommenderFactory.create_retail_recommender_async()
        hybrid_recommender = await RecommenderFactory.create_hybrid_recommender_async(
            tfidf_recommender, retail_recommender
        )
        
        # Crear cliente MCP
        mcp_client = await MCPFactory.create_mcp_client_async()
        
        # Crear Redis client para UserEventStore
        redis_client = await RecommenderFactory.create_redis_client_async()
        
        # Crear UserEventStore si Redis está disponible
        user_event_store = None
        if redis_client:
            user_event_store = await RecommenderFactory.create_user_event_store_async(redis_client)
        
        # Crear recomendador MCP
        mcp_recommender = await MCPFactory.create_mcp_recommender_async(
            base_recommender=hybrid_recommender,
            mcp_client=mcp_client,
            user_event_store=user_event_store
        )
        
        if mcp_recommender is None:
            logger.error("❌ No se pudo crear recomendador MCP")
            return False
        
        logger.info(f"✅ Recomendador MCP creado: {type(mcp_recommender).__name__}")
        logger.info(f"✅ Tiene get_metrics: {hasattr(mcp_recommender, 'get_metrics')}")
        
        if hasattr(mcp_recommender, 'get_metrics'):
            try:
                metrics = await mcp_recommender.get_metrics()
                logger.info(f"✅ get_metrics() funciona: {type(metrics)}")
                return True
            except Exception as e:
                logger.error(f"❌ Error llamando get_metrics(): {e}")
                return False
        else:
            logger.error("❌ Recomendador MCP no tiene método get_metrics")
            return False
            
        # Cerrar recursos
        if redis_client:
            await redis_client.close()
            
    except Exception as e:
        logger.error(f"❌ Error creando recomendador MCP: {e}")
        return False

async def async_main():
    """Función principal de pruebas asíncronas"""
    logger.info("🚀 Iniciando pruebas del fix MCP (versión asíncrona)...")
    
    test1_passed = await test_mcp_client_creation()
    test2_passed = await test_mcp_recommender_creation()
    
    if test1_passed and test2_passed:
        logger.info("🎉 ¡Todas las pruebas pasaron! El fix del MCP está funcionando.")
        return True
    else:
        logger.error("💥 Algunas pruebas fallaron. Revisar logs arriba.")
        return False

def main():
    """Punto de entrada para ejecutar pruebas asíncronas"""
    return asyncio.run(async_main())

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
