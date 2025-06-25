#!/usr/bin/env python3
# Script para verificar los cambios finales en el sistema MCP
# Ejecuta este script para asegurar que los cambios estén funcionando correctamente

import sys
import os
import json
import asyncio
from typing import Dict, Optional, Any

# Asegurarse de que el directorio actual esté en Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Configuración básica de logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("final_verification")

class MockBaseRecommender:
    """Mock del recomendador base que devuelve listas vacías"""
    
    def __init__(self, return_empty=True):
        self.return_empty = return_empty
        
        # Crear un content_recommender con product_data vacío (para probar fallback estático)
        self.content_recommender = MockContentRecommender(has_products=False)
    
    async def get_recommendations(self, **kwargs):
        """Simulación de get_recommendations que devuelve lista vacía"""
        logger.info(f"MockBaseRecommender.get_recommendations llamado con {kwargs}")
        
        if self.return_empty:
            return []
        else:
            return [
                {
                    "id": "product1",
                    "title": "Producto de Prueba 1",
                    "description": "Descripción del producto 1",
                    "price": 29.99,
                    "score": 0.85
                }
            ]
    
    async def record_user_event(self, **kwargs):
        return {"status": "ok"}

class MockContentRecommender:
    """Mock del recomendador de contenido con product_data vacío"""
    
    def __init__(self, has_products=False):
        # Si has_products es False, el product_data estará vacío para probar el fallback estático
        self.product_data = [] if not has_products else [
            {
                "id": "product1",
                "title": "Camisa Azul de Algodón",
                "body_html": "Camisa de algodón 100% en color azul. Ideal para ocasiones formales.",
                "variants": [{"price": "29.99"}],
                "product_type": "Camisas"
            }
        ]
        self.loaded = False
    
    async def load(self):
        """Simulación de carga del modelo"""
        logger.info("MockContentRecommender.load llamado")
        self.loaded = True
        return True
    
    async def search_products(self, query, n=5):
        """Simulación de búsqueda por texto que siempre devuelve lista vacía"""
        logger.info(f"MockContentRecommender.search_products llamado con query={query}, n={n}")
        return []  # Siempre devuelve lista vacía para forzar el fallback estático

class MockMCPClient:
    """Mock del cliente MCP"""
    
    async def process_conversation(self, query, session_id=None, context=None):
        """Simulación de proceso conversacional"""
        return {
            "response": f"Respuesta para: {query}",
            "sessionId": session_id or "mock-session"
        }

async def test_fallback_estatico():
    """Prueba el mecanismo de fallback estático cuando no hay productos en el catálogo"""
    try:
        # Importar la clase del recomendador MCP
        logger.info("Importando MCPAwareHybridRecommender...")
        from src.recommenders.mcp_aware_hybrid import MCPAwareHybridRecommender
        
        # Crear instancias mock
        base_recommender = MockBaseRecommender(return_empty=True)
        mcp_client = MockMCPClient()
        
        # Crear el recomendador MCP
        logger.info("Creando MCPAwareHybridRecommender con mocks...")
        mcp_recommender = MCPAwareHybridRecommender(
            base_recommender=base_recommender,
            mcp_client=mcp_client,
            market_manager=None,
            market_cache=None
        )
        
        # Prueba con un request que incluye una consulta
        logger.info("Probando request con consulta...")
        request = {
            "user_id": "test_user",
            "market_id": "ES",
            "n_recommendations": 3,
            "query": "busco una camisa azul"  # Consulta que debería activar el fallback
        }
        
        response = await mcp_recommender.get_recommendations(request)
        
        # Verificar que tenemos recomendaciones a pesar de no tener productos en el catálogo
        has_recs = "recommendations" in response and len(response["recommendations"]) > 0
        logger.info(f"¿Tiene recomendaciones? {has_recs}")
        logger.info(f"Cantidad de recomendaciones: {len(response['recommendations']) if has_recs else 0}")
        
        if has_recs:
            # Mostrar las recomendaciones
            for i, rec in enumerate(response["recommendations"]):
                product = rec["product"]
                logger.info(f"Recomendación {i+1}: {product['title']}")
                logger.info(f"  Fuente: {rec.get('metadata', {}).get('source', 'desconocida')}")
        
        # Verificar respuesta conversacional
        ai_response = response.get("ai_response")
        logger.info(f"Respuesta conversacional: {ai_response}")
        
        # Resultado final de la prueba
        success = has_recs and len(response["recommendations"]) > 0
        return success
    
    except Exception as e:
        logger.error(f"Error durante la prueba: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def test_query_extraction():
    """Prueba la extracción de la consulta desde el contexto de conversación"""
    try:
        # Importar la clase del recomendador MCP
        from src.recommenders.mcp_aware_hybrid import MCPAwareHybridRecommender
        
        # Crear instancias mock
        base_recommender = MockBaseRecommender(return_empty=True)
        mcp_client = MockMCPClient()
        
        # Crear el recomendador MCP
        mcp_recommender = MCPAwareHybridRecommender(
            base_recommender=base_recommender,
            mcp_client=mcp_client,
            market_manager=None,
            market_cache=None
        )
        
        # Crear un request con contexto de conversación que contiene la consulta
        context = {
            "session_id": "test_session",
            "user_id": "test_user",
            "query": "busco zapatos marrones",
            "market_id": "ES",
            "language": "es"
        }
        
        request = {
            "user_id": "test_user",
            "market_id": "ES",
            "n_recommendations": 3,
            "conversation_context": context  # La consulta está aquí, no directamente en el request
        }
        
        logger.info("Probando extracción de consulta desde contexto...")
        response = await mcp_recommender.get_recommendations(request)
        
        # Verificar que tenemos recomendaciones
        has_recs = "recommendations" in response and len(response["recommendations"]) > 0
        logger.info(f"¿Tiene recomendaciones? {has_recs}")
        logger.info(f"Cantidad de recomendaciones: {len(response['recommendations']) if has_recs else 0}")
        
        # Resultado de la prueba
        return has_recs
        
    except Exception as e:
        logger.error(f"Error durante la prueba de extracción de consulta: {e}")
        return False

async def test_model_loading_attempt():
    """Prueba el intento de carga del modelo cuando no está cargado"""
    try:
        # Importar la clase del recomendador MCP
        from src.recommenders.mcp_aware_hybrid import MCPAwareHybridRecommender
        
        # Crear instancias mock
        base_recommender = MockBaseRecommender(return_empty=True)
        base_recommender.content_recommender.loaded = False  # Asegurar que el modelo no está cargado
        mcp_client = MockMCPClient()
        
        # Crear el recomendador MCP
        mcp_recommender = MCPAwareHybridRecommender(
            base_recommender=base_recommender,
            mcp_client=mcp_client,
            market_manager=None,
            market_cache=None
        )
        
        # Crear request con consulta
        request = {
            "user_id": "test_user",
            "market_id": "ES",
            "n_recommendations": 3,
            "query": "busco una camisa azul"
        }
        
        logger.info("Probando intento de carga del modelo...")
        response = await mcp_recommender.get_recommendations(request)
        
        # Verificar que tenemos recomendaciones
        has_recs = "recommendations" in response and len(response["recommendations"]) > 0
        logger.info(f"¿Tiene recomendaciones? {has_recs}")
        
        # Verificar si se intentó cargar el modelo
        model_loaded = base_recommender.content_recommender.loaded
        logger.info(f"¿Se intentó cargar el modelo? {model_loaded}")
        
        # Resultado de la prueba
        return has_recs and model_loaded
        
    except Exception as e:
        logger.error(f"Error durante la prueba de carga del modelo: {e}")
        return False

async def run_all_tests():
    """Ejecuta todas las pruebas y devuelve los resultados"""
    results = {
        "fallback_estatico": await test_fallback_estatico(),
        "extraccion_consulta": await test_query_extraction(),
        "carga_modelo": await test_model_loading_attempt()
    }
    
    return results

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🔍 VERIFICACIÓN FINAL DE LOS CAMBIOS EN MCP")
    print("="*50 + "\n")
    
    # Ejecutar todas las pruebas
    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(run_all_tests())
    
    # Mostrar resultados
    print("\n" + "="*50)
    print("📊 RESULTADOS DE LAS PRUEBAS")
    print("="*50)
    
    all_passed = True
    for test_name, result in results.items():
        status = "✅" if result else "❌"
        all_passed = all_passed and result
        print(f"{status} {test_name.replace('_', ' ').title()}")
    
    print("="*50)
    
    # Conclusión final
    print("\n" + "="*50)
    if all_passed:
        print("✅ TODAS LAS PRUEBAS PASARON EXITOSAMENTE")
        print("👉 Los cambios implementados deberían garantizar que siempre se devuelvan recomendaciones")
        print("👉 Ya puedes ejecutar 'python tests/mcp/test_mcp_bridge.py' para verificar la integración completa")
    else:
        print("❌ ALGUNAS PRUEBAS FALLARON")
        print("👉 Revisa los logs para más detalles sobre los errores")
    print("="*50 + "\n")
    
    sys.exit(0 if all_passed else 1)
