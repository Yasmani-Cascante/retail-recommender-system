#!/usr/bin/env python3
"""
PATCH PARA test_step2_endpoints.py - REDUCIR OVERHEAD
====================================================

Mejora el script para obtener métricas más precisas eliminando overhead.
"""

import sys

def create_improved_endpoint_tester():
    """Crea versión mejorada de test_step2_endpoints.py"""
    
    improved_content = '''#!/usr/bin/env python3
"""
STEP 2 TESTING - Endpoints Performance Testing (IMPROVED VERSION)
================================================================

Versión mejorada que minimiza overhead y proporciona métricas precisas.
"""

import requests
import time
import json
import sys
import statistics
from datetime import datetime

# Configuración
BASE_URL = "http://localhost:8000"
API_KEY = "2fed9999056fab6dac5654238f0cae1c"

class ImprovedStep2EndpointTester:
    def __init__(self):
        self.headers = {
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        }
        self.results = {}
        
        # Pre-warm HTTP connection
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def warm_up_endpoints(self):
        """Warm up endpoints para eliminar cold start penalty"""
        print("🔥 Warming up endpoints...")
        
        warm_payload = {
            "query": "warm up test",
            "user_id": "warmup_user",
            "market_id": "US",
            "n_recommendations": 1
        }
        
        try:
            # Warm up original endpoint
            self.session.post(
                f"{BASE_URL}/v1/mcp/conversation",
                json=warm_payload,
                timeout=30
            )
            
            # Warm up optimized endpoint
            warm_payload["enable_optimization"] = True
            self.session.post(
                f"{BASE_URL}/v1/mcp/conversation/optimized", 
                json=warm_payload,
                timeout=15
            )
            
            print("   ✅ Endpoints warmed up")
            
        except Exception as e:
            print(f"   ⚠️ Warm up failed: {e}")
    
    def test_endpoint_multiple_times(self, endpoint_url, payload, iterations=3):
        """Test endpoint multiple times and return statistics"""
        
        times = []
        responses = []
        
        for i in range(iterations):
            try:
                start_time = time.perf_counter()
                response = self.session.post(endpoint_url, json=payload, timeout=30)
                end_time = time.perf_counter()
                
                response_time_ms = (end_time - start_time) * 1000
                times.append(response_time_ms)
                
                if response.status_code == 200:
                    responses.append(response.json())
                else:
                    print(f"   ⚠️ Iteration {i+1}: HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ Iteration {i+1} failed: {e}")
        
        if times:
            return {
                "avg_time_ms": statistics.mean(times),
                "min_time_ms": min(times),
                "max_time_ms": max(times),
                "median_time_ms": statistics.median(times),
                "std_dev_ms": statistics.stdev(times) if len(times) > 1 else 0,
                "successful_requests": len(responses),
                "total_requests": iterations,
                "success_rate": len(responses) / iterations,
                "sample_response": responses[0] if responses else None
            }
        return None
    
    def test_precise_performance_comparison(self):
        """Test de comparación de performance preciso con warm-up"""
        print("\\n🎯 Test de Comparación de Performance Preciso")
        print("=" * 60)
        
        # Warm up first
        self.warm_up_endpoints()
        
        base_payload = {
            "query": "Recomiéndame productos para running de alta calidad",
            "user_id": "test_user_precision",
            "market_id": "US",
            "n_recommendations": 5
        }
        
        print("\\n🔍 Testing Original Endpoint (3 iterations)...")
        original_stats = self.test_endpoint_multiple_times(
            f"{BASE_URL}/v1/mcp/conversation",
            base_payload.copy(),
            iterations=3
        )
        
        print("\\n🔍 Testing Optimized Endpoint (3 iterations)...")
        optimized_payload = base_payload.copy()
        optimized_payload["enable_optimization"] = True
        
        optimized_stats = self.test_endpoint_multiple_times(
            f"{BASE_URL}/v1/mcp/conversation/optimized",
            optimized_payload,
            iterations=3
        )
        
        # Análisis de resultados
        print("\\n📊 RESULTADOS PRECISOS:")
        print("=" * 40)
        
        if original_stats:
            print(f"📈 ENDPOINT ORIGINAL:")
            print(f"   • Promedio: {original_stats['avg_time_ms']:.1f}ms")
            print(f"   • Mediana: {original_stats['median_time_ms']:.1f}ms")
            print(f"   • Rango: {original_stats['min_time_ms']:.1f}-{original_stats['max_time_ms']:.1f}ms")
            print(f"   • Success Rate: {original_stats['success_rate']*100:.1f}%")
        
        if optimized_stats:
            print(f"\\n⚡ ENDPOINT OPTIMIZADO:")
            print(f"   • Promedio: {optimized_stats['avg_time_ms']:.1f}ms")
            print(f"   • Mediana: {optimized_stats['median_time_ms']:.1f}ms") 
            print(f"   • Rango: {optimized_stats['min_time_ms']:.1f}-{optimized_stats['max_time_ms']:.1f}ms")
            print(f"   • Success Rate: {optimized_stats['success_rate']*100:.1f}%")
        
        # Comparación
        if original_stats and optimized_stats:
            improvement_factor = original_stats['avg_time_ms'] / optimized_stats['avg_time_ms']
            reduction_percentage = ((original_stats['avg_time_ms'] - optimized_stats['avg_time_ms']) / original_stats['avg_time_ms']) * 100
            
            print(f"\\n🎯 ANÁLISIS DE MEJORA:")
            print(f"   📈 Mejora: {improvement_factor:.1f}x más rápido")
            print(f"   📉 Reducción: {reduction_percentage:.1f}%")
            
            # Verificar target
            target_achieved = optimized_stats['avg_time_ms'] < 2000
            target_status = "✅ OBJETIVO CUMPLIDO" if target_achieved else "❌ OBJETIVO NO CUMPLIDO"
            print(f"   🎯 Target <2000ms: {target_status}")
            print(f"   📊 Resultado: {optimized_stats['avg_time_ms']:.1f}ms")
            
            return target_achieved
        
        return False
    
    def run_comprehensive_test(self):
        """Ejecutar test comprehensivo mejorado"""
        print("🚀 INICIANDO TESTING COMPREHENSIVO MEJORADO")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("=" * 70)
        
        try:
            performance_success = self.test_precise_performance_comparison()
            
            print("\\n" + "=" * 70)
            print("📋 RESUMEN FINAL MEJORADO")
            print("=" * 70)
            
            if performance_success:
                print("🎉 PERFORMANCE TARGET ACHIEVED!")
                print("✅ Endpoint optimizado cumple objetivo <2000ms")
                print("✅ Mejora significativa confirmada")
                print("✅ Sistema listo para Phase 3")
            else:
                print("⚠️ PERFORMANCE TARGET NOT MET")
                print("❌ Revisar implementación de optimizaciones")
                print("❌ Verificar configuración de timeouts")
            
            return performance_success
            
        except Exception as e:
            print(f"❌ CRITICAL ERROR: {e}")
            return False

def main():
    """Función principal mejorada"""
    print("Asegúrate de que el servidor esté ejecutándose en http://localhost:8000")
    
    input("Presiona Enter cuando el servidor esté listo...")
    
    tester = ImprovedStep2EndpointTester()
    success = tester.run_comprehensive_test()
    
    if success:
        print("\\n🚀 PRÓXIMOS PASOS:")
        print("1. Ejecutar: python patch_validation_script.py")
        print("2. Ejecutar: python tests/phase2_consolidation/validate_phase2_complete.py")
        print("3. Verificar que success rate mejora significativamente")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
'''
    
    # Escribir archivo mejorado
    with open('test_step2_endpoints_improved.py', 'w', encoding='utf-8') as f:
        f.write(improved_content)
    
    print("✅ Created improved version: test_step2_endpoints_improved.py")
    return True

def main():
    print("🛠️ CREANDO VERSIÓN MEJORADA DE test_step2_endpoints.py")
    print("=" * 60)
    
    if create_improved_endpoint_tester():
        print("\n✅ VERSIÓN MEJORADA CREADA EXITOSAMENTE")
        print("📁 Archivo: test_step2_endpoints_improved.py")
        print("\n🎯 Mejoras implementadas:")
        print("• Connection warming para eliminar cold start")
        print("• Multiple iterations con estadísticas")
        print("• Session reuse para reducir overhead") 
        print("• Mediciones más precisas con perf_counter")
        print("• Análisis estadístico completo")
        
        print("\n📋 Próximos pasos:")
        print("1. python test_step2_endpoints_improved.py")
        print("2. Comparar resultados con versión anterior")
        print("3. Verificar que métricas son más consistentes")
        
        return True
    else:
        print("\n❌ Error creando versión mejorada")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
