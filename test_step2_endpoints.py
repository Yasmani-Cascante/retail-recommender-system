#!/usr/bin/env python3
"""
STEP 2 TESTING - Endpoints Performance Testing
==============================================

Script para probar los endpoints originales y optimizados después de Step 2.
"""

import requests
import time
import json
import sys
from datetime import datetime

# Configuración
BASE_URL = "http://localhost:8000"
API_KEY = "2fed9999056fab6dac5654238f0cae1c"  # Usar la misma que en los tests

class Step2EndpointTester:
    def __init__(self):
        self.headers = {
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        }
        self.results = {}
    
    def test_server_health(self):
        """Test 1: Verificar que el servidor está funcionando"""
        print("🔍 Test 1: Verificando health del servidor...")
        
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                print(f"   ✅ Servidor healthy: {health_data.get('status')}")
                
                # Verificar componentes
                components = health_data.get('components', {})
                for component, status in components.items():
                    comp_status = status.get('status', 'unknown') if isinstance(status, dict) else status
                    print(f"   📊 {component}: {comp_status}")
                
                self.results['health'] = {'status': 'SUCCESS', 'data': health_data}
                return True
            else:
                print(f"   ❌ Health check failed: {response.status_code}")
                self.results['health'] = {'status': 'FAIL', 'code': response.status_code}
                return False
                
        except Exception as e:
            print(f"   ❌ Error en health check: {e}")
            self.results['health'] = {'status': 'ERROR', 'error': str(e)}
            return False
    
    def test_original_endpoint(self):
        """Test 2: Probar endpoint original MCP"""
        print("\n🔍 Test 2: Probando endpoint original (/v1/mcp/conversation)...")
        
        payload = {
            "query": "Test query for original endpoint",
            "user_id": "test_user_step2",
            "market_id": "US",
            "n_recommendations": 3
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{BASE_URL}/v1/mcp/conversation",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            end_time = time.time()
            
            response_time_ms = (end_time - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Endpoint original funciona")
                print(f"   ⏱️ Response time: {response_time_ms:.1f}ms")
                print(f"   📊 Answer length: {len(data.get('answer', ''))}")
                print(f"   🎯 Recommendations: {len(data.get('recommendations', []))}")
                
                self.results['original_endpoint'] = {
                    'status': 'SUCCESS',
                    'response_time_ms': response_time_ms,
                    'data': data
                }
                return True
            else:
                print(f"   ❌ Endpoint original falló: {response.status_code}")
                print(f"   📝 Response: {response.text[:200]}")
                self.results['original_endpoint'] = {
                    'status': 'FAIL',
                    'code': response.status_code,
                    'response': response.text
                }
                return False
                
        except Exception as e:
            print(f"   ❌ Error en endpoint original: {e}")
            self.results['original_endpoint'] = {'status': 'ERROR', 'error': str(e)}
            return False
    
    def test_optimized_endpoint(self):
        """Test 3: Probar endpoint optimizado MCP"""
        print("\n🔍 Test 3: Probando endpoint optimizado (/v1/mcp/conversation/optimized)...")
        
        payload = {
            "query": "Test query for optimized endpoint",
            "user_id": "test_user_step2_opt",
            "market_id": "US",
            "n_recommendations": 3,
            "enable_optimization": True
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{BASE_URL}/v1/mcp/conversation/optimized",
                headers=self.headers,
                json=payload,
                timeout=10  # Timeout más corto para endpoint optimizado
            )
            end_time = time.time()
            
            response_time_ms = (end_time - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Endpoint optimizado funciona")
                print(f"   ⚡ Response time: {response_time_ms:.1f}ms")
                print(f"   📊 Answer length: {len(data.get('answer', ''))}")
                print(f"   🎯 Recommendations: {len(data.get('recommendations', []))}")
                print(f"   🚀 Optimization applied: {data.get('optimization_applied', False)}")
                
                if 'performance_improvement' in data:
                    print(f"   📈 Performance improvement: {data['performance_improvement']}")
                
                self.results['optimized_endpoint'] = {
                    'status': 'SUCCESS',
                    'response_time_ms': response_time_ms,
                    'data': data
                }
                return True
            else:
                print(f"   ❌ Endpoint optimizado falló: {response.status_code}")
                print(f"   📝 Response: {response.text[:200]}")
                self.results['optimized_endpoint'] = {
                    'status': 'FAIL',
                    'code': response.status_code,
                    'response': response.text
                }
                return False
                
        except Exception as e:
            print(f"   ❌ Error en endpoint optimizado: {e}")
            self.results['optimized_endpoint'] = {'status': 'ERROR', 'error': str(e)}
            return False
    
    def test_performance_comparison_endpoint(self):
        """Test 4: Probar endpoint de comparación de performance"""
        print("\n🔍 Test 4: Probando endpoint de comparación (/v1/mcp/conversation/performance-comparison)...")
        
        try:
            response = requests.get(
                f"{BASE_URL}/v1/mcp/conversation/performance-comparison",
                headers=self.headers,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Endpoint de comparación funciona")
                
                endpoints = data.get('endpoints', {})
                for endpoint_name, endpoint_data in endpoints.items():
                    print(f"   📊 {endpoint_name}: {endpoint_data.get('expected_time_ms', 'N/A')}")
                
                self.results['comparison_endpoint'] = {
                    'status': 'SUCCESS',
                    'data': data
                }
                return True
            else:
                print(f"   ❌ Endpoint de comparación falló: {response.status_code}")
                self.results['comparison_endpoint'] = {
                    'status': 'FAIL',
                    'code': response.status_code
                }
                return False
                
        except Exception as e:
            print(f"   ❌ Error en endpoint de comparación: {e}")
            self.results['comparison_endpoint'] = {'status': 'ERROR', 'error': str(e)}
            return False
    
    def compare_performance(self):
        """Test 5: Comparar performance entre endpoints"""
        print("\n🔍 Test 5: Comparando performance entre endpoints...")
        
        original_time = self.results.get('original_endpoint', {}).get('response_time_ms')
        optimized_time = self.results.get('optimized_endpoint', {}).get('response_time_ms')
        
        if original_time and optimized_time:
            improvement_factor = original_time / optimized_time if optimized_time > 0 else 0
            improvement_percentage = ((original_time - optimized_time) / original_time) * 100
            
            print(f"   📊 Endpoint original: {original_time:.1f}ms")
            print(f"   ⚡ Endpoint optimizado: {optimized_time:.1f}ms")
            print(f"   📈 Mejora: {improvement_factor:.1f}x más rápido")
            print(f"   📉 Reducción: {improvement_percentage:.1f}%")
            
            # Evaluar si cumple objetivos
            target_time = 2000  # 2 segundos
            if optimized_time <= target_time:
                print(f"   🎯 ✅ Objetivo cumplido: {optimized_time:.1f}ms <= {target_time}ms")
                performance_success = True
            else:
                print(f"   🎯 ❌ Objetivo no cumplido: {optimized_time:.1f}ms > {target_time}ms")
                performance_success = False
            
            self.results['performance_comparison'] = {
                'status': 'SUCCESS',
                'original_time_ms': original_time,
                'optimized_time_ms': optimized_time,
                'improvement_factor': improvement_factor,
                'improvement_percentage': improvement_percentage,
                'target_achieved': performance_success
            }
            
            return performance_success
        else:
            print("   ❌ No se pueden comparar tiempos - faltan datos")
            self.results['performance_comparison'] = {
                'status': 'FAIL',
                'issue': 'Missing timing data'
            }
            return False
    
    def generate_test_report(self):
        """Generar reporte de testing"""
        print("\n📋 Generando reporte de testing...")
        
        report = {
            "test_date": datetime.now().isoformat(),
            "test_type": "Step 2 Endpoint Testing",
            "base_url": BASE_URL,
            "results": self.results,
            "summary": {
                "tests_passed": sum(1 for r in self.results.values() if r.get('status') == 'SUCCESS'),
                "tests_total": len(self.results),
                "overall_success": all(r.get('status') == 'SUCCESS' for r in self.results.values())
            }
        }
        
        try:
            with open('step2_endpoint_test_report.json', 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            print("   ✅ Reporte guardado: step2_endpoint_test_report.json")
            return True
        except Exception as e:
            print(f"   ❌ Error guardando reporte: {e}")
            return False
    
    def run_all_tests(self):
        """Ejecutar todos los tests"""
        print("🚀 INICIANDO TESTING DE ENDPOINTS STEP 2")
        print(f"Base URL: {BASE_URL}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("=" * 60)
        
        tests = [
            ("Server Health", self.test_server_health),
            ("Original Endpoint", self.test_original_endpoint),
            ("Optimized Endpoint", self.test_optimized_endpoint),
            ("Comparison Endpoint", self.test_performance_comparison_endpoint),
            ("Performance Comparison", self.compare_performance)
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append(result)
            except Exception as e:
                print(f"\n❌ CRITICAL ERROR in {test_name}: {e}")
                results.append(False)
        
        # Generar reporte
        self.generate_test_report()
        
        # Resumen final
        print("\n" + "=" * 60)
        print("📊 RESUMEN FINAL DE TESTING")
        print("=" * 60)
        
        success_count = sum(results)
        total_count = len(results)
        
        for i, (test_name, result) in enumerate(zip([t[0] for t in tests], results)):
            emoji = "✅" if result else "❌"
            print(f"{emoji} {test_name}: {'PASS' if result else 'FAIL'}")
        
        print(f"\n🎯 OVERALL: {success_count}/{total_count} tests passed")
        
        if success_count == total_count:
            print("🎉 STEP 2 ENDPOINT TESTING COMPLETAMENTE EXITOSO!")
            print("✅ Todos los endpoints funcionan correctamente")
            print("✅ Optimización de performance activa")
            return True
        elif success_count >= total_count * 0.8:
            print("✅ STEP 2 ENDPOINT TESTING MAYORMENTE EXITOSO")
            print("⚠️ Algunos tests fallaron pero la funcionalidad básica está operativa")
            return True
        else:
            print("❌ STEP 2 ENDPOINT TESTING FALLÓ")
            print("❌ Múltiples issues detectados - revisar servidor y configuración")
            return False

def main():
    """Función principal"""
    print("Asegúrate de que el servidor esté ejecutándose en http://localhost:8000")
    print("Comando: python src/api/main_unified_redis.py")
    
    input("Presiona Enter cuando el servidor esté listo...")
    
    tester = Step2EndpointTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n🚀 PRÓXIMOS PASOS:")
        print("1. Revisar step2_endpoint_test_report.json para detalles")
        print("2. Ejecutar: python tests/phase2_consolidation/validate_phase2_complete.py")
        print("3. Comparar resultados con phase2_results.json anterior")
        print("4. Si hay mejoras, proceder con deployment")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
