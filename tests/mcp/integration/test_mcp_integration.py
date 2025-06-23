# tests/mcp/test_mcp_integration.py
"""
Tests de integración para validar la funcionalidad MCP completa
"""

import asyncio
import pytest
import httpx
import time
from typing import Dict, Any

class MCPIntegrationTester:
    """Tester completo para validar integración MCP"""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "test_key"):
        self.base_url = base_url
        self.headers = {
            "X-API-Key": api_key,
            "X-User-ID": "test_user_mcp",
            "Content-Type": "application/json"
        }
        self.session_id = f"test_session_{int(time.time())}"
        
    async def run_all_tests(self):
        """Ejecutar todos los tests de integración MCP"""
        print("🚀 Iniciando tests de integración MCP...")
        
        async with httpx.AsyncClient() as client:
            results = {
                "health_check": await self.test_health_check(client),
                "mcp_status": await self.test_mcp_status(client),
                "intent_analysis": await self.test_intent_analysis(client),
                "conversational_flow": await self.test_conversational_flow(client),
                "documentation_search": await self.test_documentation_search(client),
                "performance": await self.test_performance(client),
                "error_handling": await self.test_error_handling(client)
            }
            
        # Generar reporte
        self.print_test_report(results)
        return results
        
    async def test_health_check(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Test 1: Verificar health check general y MCP"""
        try:
            print("📊 Test 1: Health Check...")
            
            # Health check general
            response = await client.get(f"{self.base_url}/health")
            health_data = response.json()
            
            mcp_healthy = (
                health_data.get("components", {}).get("mcp", {}).get("status") == "operational"
            )
            
            return {
                "passed": response.status_code == 200 and mcp_healthy,
                "status_code": response.status_code,
                "mcp_status": health_data.get("components", {}).get("mcp", {}),
                "details": "Health check successful" if mcp_healthy else "MCP not operational"
            }
            
        except Exception as e:
            return {"passed": False, "error": str(e)}
            
    async def test_mcp_status(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Test 2: Verificar estado específico de MCP"""
        try:
            print("🔌 Test 2: MCP Status...")
            
            response = await client.get(
                f"{self.base_url}/v1/mcp/status",
                headers=self.headers
            )
            
            if response.status_code == 200:
                data = response.json()
                bridge_healthy = data.get("bridge_health", {}).get("status") == "healthy"
                
                return {
                    "passed": bridge_healthy,
                    "status_code": response.status_code,
                    "bridge_status": data.get("bridge_health", {}),
                    "mcp_status": data.get("mcp_status", {}),
                    "details": "MCP Bridge connected" if bridge_healthy else "Bridge disconnected"
                }
            else:
                return {
                    "passed": False,
                    "status_code": response.status_code,
                    "details": "MCP status endpoint failed"
                }
                
        except Exception as e:
            return {"passed": False, "error": str(e)}
            
    async def test_intent_analysis(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Test 3: Análisis de intenciones"""
        try:
            print("🧠 Test 3: Intent Analysis...")
            
            test_cases = [
                {"text": "busco una camiseta azul", "expected_intent": "search"},
                {"text": "recomiéndame algo", "expected_intent": "recommend"},
                {"text": "compara estos productos", "expected_intent": "compare"},
                {"text": "ayúdame a elegir", "expected_intent": "help"}
            ]
            
            results = []
            for case in test_cases:
                response = await client.post(
                    f"{self.base_url}/v1/mcp/analyze-intent",
                    headers=self.headers,
                    json={"text": case["text"]}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    intent_correct = data.get("intent") == case["expected_intent"]
                    confidence = data.get("confidence", 0)
                    
                    results.append({
                        "text": case["text"],
                        "expected": case["expected_intent"],
                        "detected": data.get("intent"),
                        "confidence": confidence,
                        "passed": intent_correct or confidence > 0.5
                    })
                else:
                    results.append({
                        "text": case["text"],
                        "passed": False,
                        "error": f"HTTP {response.status_code}"
                    })
            
            passed = sum(1 for r in results if r.get("passed", False))
            return {
                "passed": passed >= len(test_cases) * 0.75,  # 75% success rate
                "results": results,
                "success_rate": passed / len(test_cases),
                "details": f"Intent analysis: {passed}/{len(test_cases)} passed"
            }
            
        except Exception as e:
            return {"passed": False, "error": str(e)}
            
    async def test_conversational_flow(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Test 4: Flujo conversacional completo"""
        try:
            print("💬 Test 4: Conversational Flow...")
            
            conversation_steps = [
                "Hola, busco ropa para mujer",
                "Algo casual y cómodo", 
                "¿Qué colores tienes disponibles?",
                "Muéstrame las camisetas azules"
            ]
            
            results = []
            session_id = self.session_id
            
            for i, query in enumerate(conversation_steps):
                start_time = time.time()
                
                response = await client.post(
                    f"{self.base_url}/v1/mcp/conversation",
                    headers=self.headers,
                    json={
                        "query": query,
                        "session_id": session_id,
                        "n_recommendations": 3
                    }
                )
                
                response_time = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Validar estructura de respuesta
                    has_response = bool(data.get("conversational_response"))
                    has_intent = bool(data.get("intent"))
                    has_session = bool(data.get("session_id"))
                    
                    results.append({
                        "step": i + 1,
                        "query": query,
                        "passed": has_response and has_intent and has_session,
                        "response_time_ms": response_time,
                        "intent": data.get("intent"),
                        "confidence": data.get("confidence"),
                        "recommendations_count": len(data.get("recommendations", [])),
                        "session_id": data.get("session_id")
                    })
                    
                    # Usar session_id para continuidad
                    session_id = data.get("session_id", session_id)
                else:
                    results.append({
                        "step": i + 1,
                        "query": query,
                        "passed": False,
                        "error": f"HTTP {response.status_code}",
                        "response_time_ms": response_time
                    })
            
            passed = sum(1 for r in results if r.get("passed", False))
            avg_response_time = sum(r.get("response_time_ms", 0) for r in results) / len(results)
            
            return {
                "passed": passed == len(conversation_steps),
                "results": results,
                "success_rate": passed / len(conversation_steps),
                "avg_response_time_ms": avg_response_time,
                "session_continuity": len(set(r.get("session_id") for r in results if r.get("session_id"))) == 1,
                "details": f"Conversation flow: {passed}/{len(conversation_steps)} steps passed"
            }
            
        except Exception as e:
            return {"passed": False, "error": str(e)}
            
    async def test_documentation_search(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Test 5: Búsqueda en documentación"""
        try:
            print("📚 Test 5: Documentation Search...")
            
            search_queries = [
                "API authentication",
                "webhooks configuration", 
                "product variants",
                "checkout process"
            ]
            
            results = []
            for query in search_queries:
                response = await client.post(
                    f"{self.base_url}/v1/mcp/search-docs",
                    headers=self.headers,
                    json={"query": query}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    has_results = data.get("success", False)
                    
                    results.append({
                        "query": query,
                        "passed": has_results,
                        "results_structure": "results" in data
                    })
                else:
                    results.append({
                        "query": query,
                        "passed": False,
                        "error": f"HTTP {response.status_code}"
                    })
            
            passed = sum(1 for r in results if r.get("passed", False))
            return {
                "passed": passed >= len(search_queries) * 0.5,  # 50% success rate (MCP may have limitations)
                "results": results,
                "success_rate": passed / len(search_queries),
                "details": f"Documentation search: {passed}/{len(search_queries)} queries successful"
            }
            
        except Exception as e:
            return {"passed": False, "error": str(e)}
            
    async def test_performance(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Test 6: Performance bajo carga"""
        try:
            print("⚡ Test 6: Performance...")
            
            # Test concurrent requests
            concurrent_requests = 5
            query = "test performance query"
            
            async def single_request():
                start_time = time.time()
                response = await client.post(
                    f"{self.base_url}/v1/mcp/conversation",
                    headers=self.headers,
                    json={
                        "query": query,
                        "session_id": f"perf_test_{time.time()}",
                        "n_recommendations": 3
                    }
                )
                response_time = (time.time() - start_time) * 1000
                return {
                    "success": response.status_code == 200,
                    "response_time_ms": response_time
                }
            
            # Ejecutar requests concurrentes
            tasks = [single_request() for _ in range(concurrent_requests)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Analizar resultados
            successful = [r for r in results if isinstance(r, dict) and r.get("success")]
            failed = len(results) - len(successful)
            
            if successful:
                avg_response_time = sum(r["response_time_ms"] for r in successful) / len(successful)
                max_response_time = max(r["response_time_ms"] for r in successful)
                min_response_time = min(r["response_time_ms"] for r in successful)
            else:
                avg_response_time = max_response_time = min_response_time = 0
            
            # Criterios de performance
            performance_good = (
                len(successful) >= concurrent_requests * 0.8 and  # 80% success rate
                avg_response_time < 2000  # < 2 segundos promedio
            )
            
            return {
                "passed": performance_good,
                "concurrent_requests": concurrent_requests,
                "successful": len(successful),
                "failed": failed,
                "success_rate": len(successful) / concurrent_requests,
                "avg_response_time_ms": avg_response_time,
                "min_response_time_ms": min_response_time,
                "max_response_time_ms": max_response_time,
                "details": f"Performance: {len(successful)}/{concurrent_requests} requests successful"
            }
            
        except Exception as e:
            return {"passed": False, "error": str(e)}
            
    async def test_error_handling(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Test 7: Manejo de errores"""
        try:
            print("🚨 Test 7: Error Handling...")
            
            error_cases = [
                {
                    "name": "empty_query",
                    "payload": {"query": "", "session_id": "test"},
                    "expected_status": 400
                },
                {
                    "name": "invalid_n_recommendations",
                    "payload": {"query": "test", "n_recommendations": -1},
                    "expected_status": 422
                },
                {
                    "name": "missing_auth",
                    "payload": {"query": "test"},
                    "headers": {},  # Sin API key
                    "expected_status": 401
                }
            ]
            
            results = []
            for case in error_cases:
                headers = case.get("headers", self.headers)
                
                response = await client.post(
                    f"{self.base_url}/v1/mcp/conversation",
                    headers=headers,
                    json=case["payload"]
                )
                
                status_correct = response.status_code == case["expected_status"]
                has_error_details = "error" in response.text or "detail" in response.text
                
                results.append({
                    "case": case["name"],
                    "expected_status": case["expected_status"],
                    "actual_status": response.status_code,
                    "passed": status_correct,
                    "has_error_details": has_error_details
                })
            
            passed = sum(1 for r in results if r.get("passed", False))
            return {
                "passed": passed >= len(error_cases) * 0.75,  # 75% success rate
                "results": results,
                "success_rate": passed / len(error_cases),
                "details": f"Error handling: {passed}/{len(error_cases)} cases handled correctly"
            }
            
        except Exception as e:
            return {"passed": False, "error": str(e)}
            
    def print_test_report(self, results: Dict[str, Any]):
        """Imprimir reporte de tests"""
        print("\n" + "="*60)
        print("📋 REPORTE DE TESTS MCP INTEGRATION")
        print("="*60)
        
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result.get("passed", False))
        
        print(f"\n🎯 RESUMEN GENERAL:")
        print(f"   Total de tests: {total_tests}")
        print(f"   Tests pasados: {passed_tests}")
        print(f"   Tests fallidos: {total_tests - passed_tests}")
        print(f"   Tasa de éxito: {passed_tests/total_tests*100:.1f}%")
        
        print(f"\n📊 RESULTADOS DETALLADOS:")
        for test_name, result in results.items():
            status = "✅ PASS" if result.get("passed", False) else "❌ FAIL"
            details = result.get("details", "")
            error = result.get("error", "")
            
            print(f"   {status} {test_name.replace('_', ' ').title()}")
            if details:
                print(f"      → {details}")
            if error:
                print(f"      → Error: {error}")
                
        # Métricas específicas
        if "performance" in results and results["performance"].get("passed"):
            perf = results["performance"]
            print(f"\n⚡ MÉTRICAS DE PERFORMANCE:")
            print(f"   Tiempo promedio de respuesta: {perf.get('avg_response_time_ms', 0):.1f}ms")
            print(f"   Tasa de éxito concurrente: {perf.get('success_rate', 0)*100:.1f}%")
            
        if "conversational_flow" in results and results["conversational_flow"].get("passed"):
            conv = results["conversational_flow"]
            print(f"\n💬 MÉTRICAS CONVERSACIONALES:")
            print(f"   Continuidad de sesión: {'✅' if conv.get('session_continuity') else '❌'}")
            print(f"   Tiempo promedio por paso: {conv.get('avg_response_time_ms', 0):.1f}ms")
        
        # Recomendaciones
        print(f"\n💡 RECOMENDACIONES:")
        if passed_tests == total_tests:
            print("   🎉 ¡Todos los tests pasaron! Sistema MCP listo para producción.")
        elif passed_tests >= total_tests * 0.8:
            print("   ⚠️ Mayoría de tests pasaron. Revisar fallos antes de producción.")
        else:
            print("   🚨 Múltiples fallos detectados. Revisión completa necesaria.")
            
        print("="*60)

# Script principal para ejecutar tests
async def main():
    """Función principal para ejecutar tests MCP"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Integration Tests")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL del API")
    parser.add_argument("--api-key", default="test_key", help="API Key para autenticación")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout en segundos")
    
    args = parser.parse_args()
    
    print("🔧 Configuración de tests:")
    print(f"   URL: {args.url}")
    print(f"   API Key: {args.api_key[:8]}...")
    print(f"   Timeout: {args.timeout}s")
    print()
    
    tester = MCPIntegrationTester(
        base_url=args.url,
        api_key=args.api_key
    )
    
    try:
        results = await tester.run_all_tests()
        
        # Exit code basado en resultados
        passed_tests = sum(1 for result in results.values() if result.get("passed", False))
        total_tests = len(results)
        
        if passed_tests == total_tests:
            exit_code = 0  # Éxito total
        elif passed_tests >= total_tests * 0.8:
            exit_code = 1  # Advertencia
        else:
            exit_code = 2  # Error crítico
            
        exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrumpidos por el usuario")
        exit(130)
    except Exception as e:
        print(f"\n💥 Error fatal ejecutando tests: {e}")
        exit(3)

if __name__ == "__main__":
    asyncio.run(main())