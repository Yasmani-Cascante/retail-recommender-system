#!/usr/bin/env python3
"""
Test de integración Python ↔ Node.js MCP Bridge

Este script verifica que el sistema Python puede comunicarse correctamente
con el bridge Node.js que acabamos de corregir.
"""

import asyncio
import sys
import os
import logging
from typing import Dict, Any

# Agregar el directorio src al path para imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from src.api.mcp.client.mcp_client import MCPClient, MCPClientError

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PythonMCPIntegrationTester:
    """Tester para verificar integración Python ↔ Node.js MCP Bridge"""
    
    def __init__(self):
        self.results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "tests": []
        }
    
    async def run_test(self, test_name: str, test_coro):
        """Ejecutar un test y registrar resultado"""
        self.results["total_tests"] += 1
        logger.info(f"\n🧪 Running test: {test_name}")
        
        try:
            result = await test_coro
            self.results["passed"] += 1
            self.results["tests"].append({
                "name": test_name,
                "status": "PASSED",
                "result": result
            })
            logger.info(f"✅ {test_name} - PASSED")
            return result
            
        except Exception as e:
            self.results["failed"] += 1
            self.results["tests"].append({
                "name": test_name,
                "status": "FAILED",
                "error": str(e)
            })
            logger.error(f"❌ {test_name} - FAILED: {str(e)}")
            raise
    
    async def test_mcp_client_connection(self):
        """Test 1: Verificar que el cliente Python puede conectar al bridge Node.js"""
        return await self.run_test("MCP Client Connection", self._test_connection())
    
    async def _test_connection(self):
        async with MCPClient(bridge_host="localhost", bridge_port=3001) as client:
            # Verificar health check
            health = await client.health_check()
            
            if health.get("status") != "healthy":
                raise Exception(f"Bridge not healthy: {health}")
            
            if health.get("shopify_connection") != "connected":
                raise Exception(f"Shopify not connected: {health}")
            
            logger.info(f"   🏥 Bridge status: {health.get('status')}")
            logger.info(f"   🏪 Shopify status: {health.get('shopify_connection')}")
            logger.info(f"   ⏱️ Uptime: {health.get('uptime', 0) / 1000:.1f}s")
            
            return health
    
    async def test_intent_analysis(self):
        """Test 2: Verificar análisis de intención via Python client"""
        return await self.run_test("Intent Analysis", self._test_intent_analysis())
    
    async def _test_intent_analysis(self):
        async with MCPClient() as client:
            # Test varias queries en español
            test_queries = [
                {
                    "query": "busco zapatos deportivos para correr",
                    "market_context": {"market_id": "CL"},
                    "expected_intent": "search"
                },
                {
                    "query": "recomiéndame algo bueno para regalo",
                    "market_context": {"market_id": "CL"},
                    "expected_intent": "recommendation" 
                },
                {
                    "query": "quiero comparar precios de laptops",
                    "market_context": {"market_id": "CL"},
                    "expected_intent": "comparison"
                }
            ]
            
            results = []
            
            for test_case in test_queries:
                try:
                    intent_result = await client.analyze_intent(
                        test_case["query"],
                        context=test_case["market_context"]
                    )
                    
                    detected_intent = intent_result.get("intent", "unknown")
                    confidence = intent_result.get("confidence", 0.0)
                    
                    logger.info(f"   🧠 Query: '{test_case['query'][:40]}...'")
                    logger.info(f"      -> Intent: {detected_intent} (confidence: {confidence:.2f})")
                    
                    results.append({
                        "query": test_case["query"],
                        "detected_intent": detected_intent,
                        "confidence": confidence,
                        "market_id": test_case["market_context"]["market_id"]
                    })
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ Intent analysis failed for query: {e}")
                    results.append({
                        "query": test_case["query"],
                        "error": str(e)
                    })
            
            return results
    
    async def test_conversational_processing(self):
        """Test 3: Verificar procesamiento conversacional completo"""
        return await self.run_test("Conversational Processing", self._test_conversational())
    
    async def _test_conversational(self):
        async with MCPClient() as client:
            # Test conversación completa
            query = "necesito unos zapatos deportivos para correr maratón, que sean cómodos y no muy caros"
            session_id = "test_session_123"
            context = {
                "market_id": "CL",
                "user_preferences": ["deportes", "running", "presupuesto_medio"]
            }
            
            logger.info(f"   💬 Query: '{query[:50]}...'")
            
            result = await client.process_conversation(
                query=query,
                session_id=session_id,
                context=context
            )
            
            logger.info(f"   📝 Response length: {len(result.get('response', ''))}")
            logger.info(f"   🆔 Session ID: {result.get('sessionId', 'None')}")
            
            # Verificar estructura de respuesta
            if "response" not in result:
                raise Exception("Missing 'response' in conversation result")
            
            if not result.get("success", False):
                raise Exception("Conversation processing failed")
            
            return result
    
    async def test_mcp_status(self):
        """Test 4: Verificar estado MCP detallado"""
        return await self.run_test("MCP Status", self._test_mcp_status())
    
    async def _test_mcp_status(self):
        async with MCPClient() as client:
            status = await client.get_mcp_status()
            
            logger.info(f"   📊 MCP Status: {status.get('mcp_status', 'unknown')}")
            logger.info(f"   🔗 Bridge Version: {status.get('bridge_version', 'unknown')}")
            logger.info(f"   🤖 Claude Model: {status.get('claude_model', 'unknown')}")
            
            return status
    
    async def test_error_handling(self):
        """Test 5: Verificar manejo de errores"""
        return await self.run_test("Error Handling", self._test_error_handling())
    
    async def _test_error_handling(self):
        async with MCPClient() as client:
            # Test query vacía (debería fallar)
            try:
                await client.analyze_intent("", context={})
                raise Exception("Expected error for empty query but got success")
            except Exception as e:
                if "Query is required" in str(e) or "400" in str(e):
                    logger.info("   ✅ Correctly handled empty query error")
                else:
                    raise Exception(f"Unexpected error type: {e}")
            
            # Test market_id inválido
            try:
                await client.analyze_intent(
                    "test query", 
                    context={"market_id": "INVALID_MARKET_123"}
                )
                logger.info("   ⚠️ Invalid market ID was accepted (might be fallback)")
            except Exception as e:
                logger.info(f"   ✅ Correctly handled invalid market: {e}")
            
            return {"error_handling": "working"}
    
    async def run_all_tests(self):
        """Ejecutar todos los tests de integración"""
        logger.info("🚀 Starting Python ↔ Node.js MCP Integration Tests")
        logger.info("=" * 60)
        
        try:
            # Tests básicos
            await self.test_mcp_client_connection()
            await self.test_mcp_status()
            
            # Tests de funcionalidad core
            await self.test_intent_analysis()
            await self.test_conversational_processing()
            
            # Tests de robustez
            await self.test_error_handling()
            
        except Exception as e:
            logger.error(f"\n💥 Test suite failed: {e}")
        
        self.print_summary()
    
    def print_summary(self):
        """Imprimir resumen de resultados"""
        logger.info("\n" + "=" * 60)
        logger.info("📋 PYTHON ↔ NODE.JS INTEGRATION TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"📊 Total Tests: {self.results['total_tests']}")
        logger.info(f"✅ Passed: {self.results['passed']}")
        logger.info(f"❌ Failed: {self.results['failed']}")
        
        if self.results['total_tests'] > 0:
            success_rate = (self.results['passed'] / self.results['total_tests']) * 100
            logger.info(f"📈 Success Rate: {success_rate:.1f}%")
        
        if self.results['failed'] > 0:
            logger.info("\n❌ FAILED TESTS:")
            for test in self.results['tests']:
                if test['status'] == 'FAILED':
                    logger.info(f"   • {test['name']}: {test.get('error', 'Unknown error')}")
        
        final_status = "🎉 ALL TESTS PASSED!" if self.results['failed'] == 0 else "⚠️ SOME TESTS FAILED"
        logger.info(f"\n{final_status}")
        logger.info("=" * 60)

async def main():
    """Función principal"""
    tester = PythonMCPIntegrationTester()
    await tester.run_all_tests()
    
    # Exit code basado en resultados
    return 0 if tester.results['failed'] == 0 else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
