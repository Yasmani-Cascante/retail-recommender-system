#!/usr/bin/env python3
"""
Tests Rápidos y Específicos para Fase 2
========================================

Scripts de validación rápida para funcionalidades específicas de Fase 2.
Útiles para debugging y validación durante desarrollo.

Uso:
    python phase2_quick_tests.py health
    python phase2_quick_tests.py personalization
    python phase2_quick_tests.py conversation
    python phase2_quick_tests.py performance
    python phase2_quick_tests.py all
"""

import asyncio
import aiohttp
import json
import time
import sys
import uuid
from datetime import datetime

# Configuración
BASE_URL = "http://localhost:8000"
API_KEY = "2fed9999056fab6dac5654238f0cae1c"
TEST_USER = f"quick_test_{uuid.uuid4().hex[:8]}"

async def make_request(session, method, endpoint, **kwargs):
    """Hacer request con headers estándar"""
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    if "headers" in kwargs:
        headers.update(kwargs["headers"])
        del kwargs["headers"]
    
    url = f"{BASE_URL}{endpoint}"
    return await session.request(method, url, headers=headers, **kwargs)

async def test_health():
    """Test rápido de health del sistema"""
    print("🔍 Testing System Health...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with await make_request(session, "GET", "/health") as response:
                data = await response.json()
                
                print(f"Status: {response.status}")
                print(f"Components: {len(data.get('components', {}))}")
                
                # Verificar componentes clave
                components = data.get('components', {})
                for name, info in components.items():
                    status = info.get('status', 'unknown')
                    print(f"  {name}: {status}")
                
                return response.status == 200
                
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False

async def test_personalization():
    """Test rápido de personalización"""
    print("🔍 Testing Personalization Engine...")
    
    async with aiohttp.ClientSession() as session:
        try:
            payload = {
                "query": "I need a comfortable dress for summer under $100",
                "user_id": TEST_USER,
                "market_id": "US",
                "n_recommendations": 3
            }
            
            start_time = time.time()
            async with await make_request(session, "POST", "/v1/mcp/conversation", json=payload) as response:
                response_time = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    print(f"✅ Response time: {response_time:.0f}ms")
                    print(f"✅ Recommendations: {len(data.get('recommendations', []))}")
                    
                    # Verificar personalización
                    personalization = data.get('personalization_metadata', {})
                    if personalization:
                        strategy = personalization.get('strategy_used', 'unknown')
                        score = personalization.get('personalization_score', 0)
                        print(f"✅ Strategy: {strategy}, Score: {score:.2f}")
                        return True
                    else:
                        print("⚠️ No personalization metadata found")
                        return False
                else:
                    print(f"❌ HTTP {response.status}: {await response.text()}")
                    return False
                    
        except Exception as e:
            print(f"❌ Personalization test failed: {e}")
            return False

async def test_conversation():
    """Test de flujo conversacional completo"""
    print("🔍 Testing Conversation Flow...")
    
    async with aiohttp.ClientSession() as session:
        session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        
        conversation_flow = [
            "I'm looking for something to wear",
            "I prefer dresses",
            "Something for a dinner date",
            "What's the price range?"
        ]
        
        try:
            for i, query in enumerate(conversation_flow):
                payload = {
                    "query": query,
                    "user_id": TEST_USER,
                    "session_id": session_id
                }
                
                async with await make_request(session, "POST", "/v1/mcp/conversation", json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Verificar progresión
                        session_metadata = data.get('session_metadata', {})
                        turn_number = session_metadata.get('turn_number', 0)
                        
                        print(f"  Turn {i+1}: ✅ (Turn number: {turn_number})")
                        
                        if i == len(conversation_flow) - 1:
                            # Última conversación - verificar context completo
                            intent = data.get('intent_analysis', {}).get('intent', 'unknown')
                            print(f"✅ Final intent: {intent}")
                            print(f"✅ Session tracking: {session_metadata.get('session_id') == session_id}")
                            return True
                    else:
                        print(f"  Turn {i+1}: ❌ HTTP {response.status}")
                        return False
                        
        except Exception as e:
            print(f"❌ Conversation test failed: {e}")
            return False

async def test_performance():
    """Test básico de performance"""
    print("🔍 Testing Performance...")
    
    async with aiohttp.ClientSession() as session:
        test_count = 5
        response_times = []
        
        try:
            for i in range(test_count):
                payload = {
                    "query": f"Performance test {i+1}",
                    "user_id": f"{TEST_USER}_perf_{i}",
                    "market_id": "US"
                }
                
                start_time = time.time()
                async with await make_request(session, "POST", "/v1/mcp/conversation", json=payload) as response:
                    response_time = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        response_times.append(response_time)
                        print(f"  Request {i+1}: {response_time:.0f}ms")
                    else:
                        print(f"  Request {i+1}: ❌ HTTP {response.status}")
            
            if response_times:
                avg_time = sum(response_times) / len(response_times)
                max_time = max(response_times)
                min_time = min(response_times)
                
                print(f"✅ Average: {avg_time:.0f}ms")
                print(f"✅ Range: {min_time:.0f}ms - {max_time:.0f}ms")
                print(f"✅ Success rate: {len(response_times)}/{test_count}")
                
                return avg_time < 2000  # Menos de 2 segundos promedio
            else:
                print("❌ No successful requests")
                return False
                
        except Exception as e:
            print(f"❌ Performance test failed: {e}")
            return False

async def test_metrics():
    """Test del endpoint de métricas"""
    print("🔍 Testing Metrics Endpoint...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with await make_request(session, "GET", "/v1/metrics") as response:
                if response.status == 200:
                    data = await response.json()
                    
                    print(f"✅ Metrics available: {len(data)} sections")
                    
                    # Verificar secciones importantes
                    key_sections = ["personalization_metrics", "system_metrics", "realtime_metrics"]
                    found_sections = [section for section in key_sections if section in data]
                    
                    print(f"✅ Key sections found: {found_sections}")
                    
                    # Verificar métricas específicas
                    if "personalization_metrics" in data:
                        p_metrics = data["personalization_metrics"]
                        print(f"✅ Personalization metrics: {len(p_metrics)} items")
                    
                    return len(found_sections) > 0
                else:
                    print(f"❌ HTTP {response.status}: {await response.text()}")
                    return False
                    
        except Exception as e:
            print(f"❌ Metrics test failed: {e}")
            return False

async def test_markets():
    """Test de múltiples mercados"""
    print("🔍 Testing Multi-Market Support...")
    
    async with aiohttp.ClientSession() as session:
        markets = ["US", "ES", "MX"]
        successful_markets = 0
        
        try:
            for market in markets:
                payload = {
                    "query": "I need a nice shirt",
                    "user_id": f"{TEST_USER}_{market}",
                    "market_id": market
                }
                
                async with await make_request(session, "POST", "/v1/mcp/conversation", json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Verificar adaptación de mercado
                        market_context = data.get('market_context', {})
                        detected_market = market_context.get('market_id', 'unknown')
                        
                        if detected_market == market:
                            successful_markets += 1
                            print(f"  {market}: ✅")
                        else:
                            print(f"  {market}: ⚠️ (detected: {detected_market})")
                    else:
                        print(f"  {market}: ❌ HTTP {response.status}")
            
            print(f"✅ Markets working: {successful_markets}/{len(markets)}")
            return successful_markets >= 2
            
        except Exception as e:
            print(f"❌ Multi-market test failed: {e}")
            return False

async def run_all_quick_tests():
    """Ejecutar todos los tests rápidos"""
    print("🚀 Running All Quick Tests for Phase 2")
    print("="*50)
    
    tests = [
        ("Health Check", test_health),
        ("Personalization", test_personalization),
        ("Conversation Flow", test_conversation),
        ("Performance", test_performance),
        ("Metrics", test_metrics),
        ("Multi-Market", test_markets)
    ]
    
    results = []
    start_time = time.time()
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)
        
        test_start = time.time()
        try:
            result = await test_func()
            test_time = time.time() - test_start
            
            results.append({
                "name": test_name,
                "passed": result,
                "time": test_time
            })
            
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"Result: {status} ({test_time:.1f}s)")
            
        except Exception as e:
            test_time = time.time() - test_start
            results.append({
                "name": test_name,
                "passed": False,
                "time": test_time,
                "error": str(e)
            })
            print(f"Result: ❌ ERROR - {e} ({test_time:.1f}s)")
    
    total_time = time.time() - start_time
    
    # Resumen final
    print("\n" + "="*50)
    print("📊 QUICK TESTS SUMMARY")
    print("="*50)
    
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    success_rate = (passed / total) * 100
    
    print(f"Tests passed: {passed}/{total} ({success_rate:.1f}%)")
    print(f"Total time: {total_time:.1f}s")
    
    # Mostrar fallos
    failures = [r for r in results if not r["passed"]]
    if failures:
        print(f"\n❌ Failed tests:")
        for failure in failures:
            print(f"  - {failure['name']}")
            if 'error' in failure:
                print(f"    Error: {failure['error']}")
    
    # Recomendación
    if success_rate >= 80:
        print(f"\n🎉 Quick validation PASSED! Phase 2 looking good.")
        return True
    else:
        print(f"\n⚠️ Quick validation ISSUES detected. Run full validation.")
        return False

def main():
    """Función principal"""
    if len(sys.argv) < 2:
        print("Usage: python phase2_quick_tests.py <test_type>")
        print("Test types: health, personalization, conversation, performance, metrics, markets, all")
        sys.exit(1)
    
    test_type = sys.argv[1].lower()
    
    test_functions = {
        "health": test_health,
        "personalization": test_personalization,
        "conversation": test_conversation,
        "performance": test_performance,
        "metrics": test_metrics,
        "markets": test_markets,
        "all": run_all_quick_tests
    }
    
    if test_type not in test_functions:
        print(f"❌ Unknown test type: {test_type}")
        print(f"Available: {', '.join(test_functions.keys())}")
        sys.exit(1)
    
    print(f"🚀 Running Quick Test: {test_type.upper()}")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Test User: {TEST_USER}")
    print()
    
    try:
        result = asyncio.run(test_functions[test_type]())
        
        if result:
            print(f"\n✅ Test PASSED")
            sys.exit(0)
        else:
            print(f"\n❌ Test FAILED")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n⚠️ Test cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()