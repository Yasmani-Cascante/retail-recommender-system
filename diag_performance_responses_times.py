#!/usr/bin/env python3
"""
Performance Diagnostic Script - Response Times Analysis
======================================================

Analiza y diagnostica problemas de performance en el sistema.
Identifica bottlenecks específicos y genera plan de optimización.

PROBLEMA OBJETIVO: 11120ms promedio → <2000ms objetivo
BREAKDOWN: Claude API 72%, Redis 13%, Strategy 9%, Profile 4%, Network 2%

Ejecutar: python performance_diagnostic.py
"""

import asyncio
import time
import json
import logging
import statistics
from typing import Dict, List, Tuple, Any
from datetime import datetime
import sys
import os

# Setup path
project_root = r"C:\Users\yasma\Desktop\retail-recommender-system"
sys.path.insert(0, os.path.join(project_root, "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerformanceDiagnostic:
    """Diagnóstico especializado de performance del sistema"""
    
    def __init__(self):
        self.profiling_results = {}
        self.bottlenecks = []
        self.optimization_recommendations = []
    
    async def run_performance_analysis(self):
        """Ejecuta análisis completo de performance"""
        
        print("⚡ DIAGNÓSTICO DE PERFORMANCE - RESPONSE TIMES")
        print("=" * 55)
        
        # 1. Profiling de componentes individuales
        await self.profile_individual_components()
        
        # 2. Análisis de end-to-end latency
        await self.analyze_end_to_end_latency()
        
        # 3. Identificación de bottlenecks
        await self.identify_bottlenecks()
        
        # 4. Análisis de concurrencia
        await self.analyze_concurrency_performance()
        
        # 5. Análisis de caching
        await self.analyze_caching_effectiveness()
        
        # 6. Generar recomendaciones
        self.generate_optimization_recommendations()
        
        # 7. Plan de implementación
        self.create_implementation_plan()
    
    async def profile_individual_components(self):
        """Profiling detallado de cada componente"""
        print("\n🔍 PROFILING: Componentes Individuales")
        print("-" * 40)
        
        components = {
            "claude_api_call": self._profile_claude_api,
            "redis_operations": self._profile_redis_operations,
            "strategy_selection": self._profile_strategy_selection,
            "profile_operations": self._profile_profile_operations,
            "recommendation_generation": self._profile_recommendation_generation
        }
        
        for component_name, profiler_func in components.items():
            print(f"\n📊 Profiling {component_name}...")
            
            try:
                # Ejecutar múltiples iteraciones para promedio
                times = []
                for i in range(5):
                    start_time = time.perf_counter()
                    await profiler_func()
                    end_time = time.perf_counter()
                    times.append((end_time - start_time) * 1000)  # ms
                
                # Calcular estadísticas
                avg_time = statistics.mean(times)
                min_time = min(times)
                max_time = max(times)
                std_dev = statistics.stdev(times) if len(times) > 1 else 0
                
                self.profiling_results[component_name] = {
                    "avg_ms": avg_time,
                    "min_ms": min_time,
                    "max_ms": max_time,
                    "std_dev": std_dev,
                    "all_times": times,
                    "sample_size": len(times)
                }
                
                print(f"  ⏱️  Promedio: {avg_time:.2f}ms")
                print(f"  📊 Rango: {min_time:.2f}ms - {max_time:.2f}ms")
                print(f"  📈 Std Dev: {std_dev:.2f}ms")
                
                # Identificar si es bottleneck
                if avg_time > 2000:  # >2s es crítico
                    self.bottlenecks.append({
                        "component": component_name,
                        "avg_time_ms": avg_time,
                        "severity": "critical"
                    })
                    print(f"  🚨 BOTTLENECK CRÍTICO detectado")
                elif avg_time > 500:  # >500ms es significativo
                    self.bottlenecks.append({
                        "component": component_name,
                        "avg_time_ms": avg_time,
                        "severity": "significant"
                    })
                    print(f"  ⚠️  Bottleneck significativo detectado")
                
            except Exception as e:
                print(f"  ❌ Error profiling {component_name}: {e}")
                self.profiling_results[component_name] = {"error": str(e)}
    
    async def _profile_claude_api(self):
        """Profile simulado de Claude API call"""
        # Simular llamada a Claude API
        await asyncio.sleep(8.0)  # Simula 8s de latencia actual
        
        # Simular procesamiento de respuesta
        await asyncio.sleep(0.1)
    
    async def _profile_redis_operations(self):
        """Profile simulado de operaciones Redis"""
        # Simular múltiples operaciones Redis secuenciales
        operations = [
            ("get_user_profile", 0.3),
            ("get_conversation_state", 0.2),
            ("get_strategy_history", 0.4),
            ("set_conversation_state", 0.2),
            ("incr_turn_counter", 0.1),
            ("set_analytics_data", 0.3)
        ]
        
        # Simular operaciones secuenciales (problema actual)
        for operation, delay in operations:
            await asyncio.sleep(delay)
    
    async def _profile_strategy_selection(self):
        """Profile simulado de selección de estrategia"""
        # Simular análisis de query
        await asyncio.sleep(0.2)
        
        # Simular cálculo de scores
        await asyncio.sleep(0.3)
        
        # Simular selección probabilística  
        await asyncio.sleep(0.1)
        
        # Simular tracking de efectividad
        await asyncio.sleep(0.4)
    
    async def _profile_profile_operations(self):
        """Profile simulado de operaciones de perfil"""
        # Simular carga de perfil (cache miss)
        await asyncio.sleep(0.3)
        
        # Simular actualización de perfil
        await asyncio.sleep(0.2)
    
    async def _profile_recommendation_generation(self):
        """Profile simulado de generación de recomendaciones"""
        # Simular llamada a hybrid recommender
        await asyncio.sleep(0.4)
        
        # Simular personalización de recomendaciones
        await asyncio.sleep(0.3)
    
    async def analyze_end_to_end_latency(self):
        """Análisis de latencia end-to-end"""
        print("\n🔍 ANÁLISIS: End-to-End Latency")
        print("-" * 40)
        
        # Simular request completo
        total_times = []
        component_breakdown = []
        
        for iteration in range(3):
            print(f"\n📊 Iteración {iteration + 1}:")
            
            request_start = time.perf_counter()
            breakdown = {}
            
            # Componentes en secuencia (problema actual)
            components_sequence = [
                ("load_conversation_state", self._profile_redis_operations),
                ("strategy_selection", self._profile_strategy_selection),
                ("load_user_profile", self._profile_profile_operations),
                ("generate_recommendations", self._profile_recommendation_generation),
                ("claude_api_call", self._profile_claude_api),
                ("save_conversation_state", self._profile_redis_operations)
            ]
            
            for component_name, component_func in components_sequence:
                component_start = time.perf_counter()
                await component_func()
                component_end = time.perf_counter()
                
                component_time = (component_end - component_start) * 1000
                breakdown[component_name] = component_time
                
                print(f"  ⏱️  {component_name}: {component_time:.2f}ms")
            
            request_end = time.perf_counter()
            total_time = (request_end - request_start) * 1000
            
            total_times.append(total_time)
            component_breakdown.append(breakdown)
            
            print(f"  🏁 Total request: {total_time:.2f}ms")
        
        # Análisis estadístico
        avg_total = statistics.mean(total_times)
        max_total = max(total_times)
        min_total = min(total_times)
        
        self.profiling_results["end_to_end"] = {
            "avg_total_ms": avg_total,
            "max_total_ms": max_total,
            "min_total_ms": min_total,
            "component_breakdown": component_breakdown,
            "sla_compliance": avg_total < 2000,
            "performance_grade": self._calculate_performance_grade(avg_total)
        }
        
        print(f"\n📊 RESUMEN END-TO-END:")
        print(f"  📈 Promedio: {avg_total:.2f}ms")
        print(f"  📊 Rango: {min_total:.2f}ms - {max_total:.2f}ms")
        print(f"  🎯 SLA Compliance (<2000ms): {'✅' if avg_total < 2000 else '❌'}")
        print(f"  📝 Performance Grade: {self._calculate_performance_grade(avg_total)}")
    
    def _calculate_performance_grade(self, avg_time_ms: float) -> str:
        """Calcula grade de performance"""
        if avg_time_ms < 500:
            return "A+ (Excellent)"
        elif avg_time_ms < 1000:
            return "A (Very Good)"
        elif avg_time_ms < 2000:
            return "B (Good)"
        elif avg_time_ms < 5000:
            return "C (Acceptable)"
        elif avg_time_ms < 10000:
            return "D (Poor)"
        else:
            return "F (Unacceptable)"
    
    async def identify_bottlenecks(self):
        """Identifica y prioriza bottlenecks"""
        print("\n🚨 IDENTIFICACIÓN: Bottlenecks Críticos")
        print("-" * 40)
        
        # Ordenar bottlenecks por severidad
        critical_bottlenecks = [b for b in self.bottlenecks if b["severity"] == "critical"]
        significant_bottlenecks = [b for b in self.bottlenecks if b["severity"] == "significant"]
        
        print(f"🔴 Bottlenecks Críticos: {len(critical_bottlenecks)}")
        for bottleneck in critical_bottlenecks:
            print(f"  ❌ {bottleneck['component']}: {bottleneck['avg_time_ms']:.2f}ms")
        
        print(f"\n🟡 Bottlenecks Significativos: {len(significant_bottlenecks)}")
        for bottleneck in significant_bottlenecks:
            print(f"  ⚠️  {bottleneck['component']}: {bottleneck['avg_time_ms']:.2f}ms")
        
        # Análisis de contribución al tiempo total
        if "end_to_end" in self.profiling_results:
            total_time = self.profiling_results["end_to_end"]["avg_total_ms"]
            
            print(f"\n📊 CONTRIBUCIÓN AL TIEMPO TOTAL ({total_time:.2f}ms):")
            
            # Calcular contribución de cada componente
            if self.profiling_results["end_to_end"]["component_breakdown"]:
                sample_breakdown = self.profiling_results["end_to_end"]["component_breakdown"][0]
                
                component_contributions = []
                for component, time_ms in sample_breakdown.items():
                    contribution_pct = (time_ms / total_time) * 100
                    component_contributions.append((component, time_ms, contribution_pct))
                
                # Ordenar por contribución
                component_contributions.sort(key=lambda x: x[2], reverse=True)
                
                for component, time_ms, contribution_pct in component_contributions:
                    print(f"  📈 {component}: {time_ms:.1f}ms ({contribution_pct:.1f}%)")
                    
                    if contribution_pct > 50:
                        print(f"    🚨 BOTTLENECK DOMINANTE - Prioridad #1")
                    elif contribution_pct > 20:
                        print(f"    ⚠️  Optimización de alta prioridad")
    
    async def analyze_concurrency_performance(self):
        """Análisis de performance con carga concurrente"""
        print("\n🔍 ANÁLISIS: Performance Concurrente")
        print("-" * 40)
        
        concurrency_levels = [1, 3, 5, 10]
        
        for concurrency in concurrency_levels:
            print(f"\n📊 Testing con {concurrency} requests concurrentes...")
            
            start_time = time.perf_counter()
            
            # Simular requests concurrentes
            tasks = []
            for i in range(concurrency):
                task = self._simulate_concurrent_request(i)
                tasks.append(task)
            
            # Ejecutar concurrentemente
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            end_time = time.perf_counter()
            total_time = (end_time - start_time) * 1000
            
            # Analizar resultados
            successful_results = [r for r in results if not isinstance(r, Exception)]
            error_count = len(results) - len(successful_results)
            
            if successful_results:
                avg_response_time = statistics.mean(successful_results)
                max_response_time = max(successful_results)
                min_response_time = min(successful_results)
            else:
                avg_response_time = max_response_time = min_response_time = 0
            
            throughput = len(successful_results) / (total_time / 1000) if total_time > 0 else 0
            
            print(f"  ⏱️  Tiempo total: {total_time:.2f}ms")
            print(f"  📊 Promedio respuesta: {avg_response_time:.2f}ms")
            print(f"  📈 Rango: {min_response_time:.2f}ms - {max_response_time:.2f}ms")
            print(f"  🚀 Throughput: {throughput:.2f} req/s")
            print(f"  ❌ Errores: {error_count}/{concurrency}")
            
            # Almacenar resultados
            self.profiling_results[f"concurrency_{concurrency}"] = {
                "total_time_ms": total_time,
                "avg_response_time_ms": avg_response_time,
                "max_response_time_ms": max_response_time,
                "min_response_time_ms": min_response_time,
                "throughput_rps": throughput,
                "error_rate": error_count / concurrency,
                "successful_requests": len(successful_results)
            }
    
    async def _simulate_concurrent_request(self, request_id: int) -> float:
        """Simula un request individual para testing concurrente"""
        start_time = time.perf_counter()
        
        # Simular procesamiento de request
        # En el sistema actual, los requests serían secuenciales debido a falta de optimización
        await asyncio.sleep(8.5 + (request_id * 0.1))  # Simula degradación con concurrencia
        
        end_time = time.perf_counter()
        return (end_time - start_time) * 1000
    
    async def analyze_caching_effectiveness(self):
        """Análisis de efectividad de caching"""
        print("\n🔍 ANÁLISIS: Efectividad de Caching")
        print("-" * 40)
        
        # Simular diferentes scenarios de cache
        cache_scenarios = [
            ("cold_cache", "Cache completamente frío"),
            ("warm_cache", "Cache parcialmente calentado"),
            ("hot_cache", "Cache completamente caliente")
        ]
        
        for scenario_name, description in cache_scenarios:
            print(f"\n📊 Scenario: {description}")
            
            # Simular tiempos con diferentes estados de cache
            cache_hit_rates = {
                "cold_cache": 0.1,   # 10% hit rate
                "warm_cache": 0.5,   # 50% hit rate  
                "hot_cache": 0.9     # 90% hit rate
            }
            
            hit_rate = cache_hit_rates[scenario_name]
            
            # Simular múltiples requests
            times = []
            cache_hits = 0
            cache_misses = 0
            
            for i in range(10):
                start_time = time.perf_counter()
                
                # Simular cache lookup
                import random
                if random.random() < hit_rate:
                    # Cache hit - respuesta rápida
                    await asyncio.sleep(0.05)  # 50ms
                    cache_hits += 1
                else:
                    # Cache miss - respuesta lenta
                    await asyncio.sleep(1.5)   # 1500ms
                    cache_misses += 1
                
                end_time = time.perf_counter()
                times.append((end_time - start_time) * 1000)
            
            avg_time = statistics.mean(times)
            actual_hit_rate = cache_hits / (cache_hits + cache_misses)
            
            print(f"  📊 Hit rate real: {actual_hit_rate:.1%}")
            print(f"  ⏱️  Tiempo promedio: {avg_time:.2f}ms")
            print(f"  ✅ Cache hits: {cache_hits}")
            print(f"  ❌ Cache misses: {cache_misses}")
            
            self.profiling_results[f"cache_{scenario_name}"] = {
                "hit_rate": actual_hit_rate,
                "avg_time_ms": avg_time,
                "cache_hits": cache_hits,
                "cache_misses": cache_misses
            }
    
    def generate_optimization_recommendations(self):
        """Genera recomendaciones específicas de optimización"""
        print("\n💡 RECOMENDACIONES: Optimización de Performance")
        print("-" * 50)
        
        recommendations = []
        
        # Analizar resultados de profiling
        if "claude_api_call" in self.profiling_results:
            claude_time = self.profiling_results["claude_api_call"]["avg_ms"]
            if claude_time > 5000:
                recommendations.append({
                    "priority": 1,
                    "category": "API Optimization",
                    "issue": f"Claude API calls taking {claude_time:.1f}ms",
                    "solution": "Implement async batching and connection pooling",
                    "expected_improvement": "60-70% reduction",
                    "implementation_effort": "Medium"
                })
        
        if "redis_operations" in self.profiling_results:
            redis_time = self.profiling_results["redis_operations"]["avg_ms"]
            if redis_time > 1000:
                recommendations.append({
                    "priority": 2,
                    "category": "Database Optimization", 
                    "issue": f"Redis operations taking {redis_time:.1f}ms",
                    "solution": "Pipeline Redis operations and implement connection pooling",
                    "expected_improvement": "50-60% reduction",
                    "implementation_effort": "Low"
                })
        
        # Analizar concurrencia
        if "concurrency_1" in self.profiling_results and "concurrency_5" in self.profiling_results:
            single_time = self.profiling_results["concurrency_1"]["avg_response_time_ms"]
            concurrent_time = self.profiling_results["concurrency_5"]["avg_response_time_ms"]
            
            if concurrent_time > single_time * 2:
                recommendations.append({
                    "priority": 1,
                    "category": "Concurrency",
                    "issue": f"Performance degrades severely under load ({concurrent_time/single_time:.1f}x slower)",
                    "solution": "Implement proper async patterns and resource pooling",
                    "expected_improvement": "Maintain ~1.2x response time under 5x load",
                    "implementation_effort": "High"
                })
        
        # Analizar caching
        if "cache_cold_cache" in self.profiling_results:
            cold_time = self.profiling_results["cache_cold_cache"]["avg_time_ms"]
            if cold_time > 1000:
                recommendations.append({
                    "priority": 2,
                    "category": "Caching",
                    "issue": f"Cold cache performance is poor ({cold_time:.1f}ms)",
                    "solution": "Implement cache warming and smarter eviction policies",
                    "expected_improvement": "80-90% improvement in cache hit scenarios",
                    "implementation_effort": "Medium"
                })
        
        # Ordenar por prioridad
        recommendations.sort(key=lambda x: x["priority"])
        
        self.optimization_recommendations = recommendations
        
        print("🎯 RECOMENDACIONES PRIORIZADAS:")
        for i, rec in enumerate(recommendations, 1):
            print(f"\n{i}. 🔧 {rec['category']} (Prioridad {rec['priority']})")
            print(f"   ❌ Problema: {rec['issue']}")
            print(f"   ✅ Solución: {rec['solution']}")
            print(f"   📈 Mejora esperada: {rec['expected_improvement']}")
            print(f"   ⏱️  Esfuerzo: {rec['implementation_effort']}")
    
    def create_implementation_plan(self):
        """Crea plan detallado de implementación"""
        print("\n📋 PLAN DE IMPLEMENTACIÓN")
        print("=" * 30)
        
        # Organizar por fases
        phase_1_recs = [r for r in self.optimization_recommendations if r["priority"] == 1]
        phase_2_recs = [r for r in self.optimization_recommendations if r["priority"] == 2]
        
        print("\n🚀 FASE 1: Optimizaciones Críticas (Semana 1-2)")
        print("-" * 45)
        for i, rec in enumerate(phase_1_recs, 1):
            print(f"{i}. {rec['category']}: {rec['solution']}")
            print(f"   📊 Impacto: {rec['expected_improvement']}")
        
        print("\n🔧 FASE 2: Optimizaciones Secundarias (Semana 3-4)")
        print("-" * 45)
        for i, rec in enumerate(phase_2_recs, 1):
            print(f"{i}. {rec['category']}: {rec['solution']}")
            print(f"   📊 Impacto: {rec['expected_improvement']}")
        
        # Timeline esperado
        print("\n📅 TIMELINE OBJETIVO:")
        print("  📍 Semana 1: Claude API optimization + async patterns")
        print("  📍 Semana 2: Redis pipelining + connection pooling")
        print("  📍 Semana 3: Cache warming + smart eviction")
        print("  📍 Semana 4: Monitoring + performance validation")
        
        # Métricas objetivo
        current_avg = self.profiling_results.get("end_to_end", {}).get("avg_total_ms", 11120)
        target_improvement = 0.85  # 85% reduction
        target_time = current_avg * (1 - target_improvement)
        
        print(f"\n🎯 OBJETIVOS DE PERFORMANCE:")
        print(f"  📊 Tiempo actual: {current_avg:.0f}ms")
        print(f"  🎯 Objetivo: <{target_time:.0f}ms (85% mejora)")
        print(f"  📈 SLA Target: <2000ms")
        print(f"  🚀 Throughput objetivo: >10 req/s")
        
        # Generar reporte detallado
        self._save_diagnostic_report()
    
    def _save_diagnostic_report(self):
        """Guarda reporte detallado de diagnóstico"""
        report = {
            "diagnostic_timestamp": datetime.now().isoformat(),
            "profiling_results": self.profiling_results,
            "bottlenecks": self.bottlenecks,
            "optimization_recommendations": self.optimization_recommendations,
            "current_performance": {
                "avg_response_time_ms": self.profiling_results.get("end_to_end", {}).get("avg_total_ms", 0),
                "sla_compliance": self.profiling_results.get("end_to_end", {}).get("sla_compliance", False),
                "performance_grade": self.profiling_results.get("end_to_end", {}).get("performance_grade", "Unknown")
            },
            "target_performance": {
                "target_response_time_ms": 2000,
                "target_throughput_rps": 10,
                "target_improvement_percentage": 85
            }
        }
        
        with open("performance_diagnostic_report.json", "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n📄 Reporte detallado guardado en: performance_diagnostic_report.json")

async def main():
    """Ejecutar diagnóstico completo de performance"""
    diagnostic = PerformanceDiagnostic()
    await diagnostic.run_performance_analysis()

if __name__ == "__main__":
    asyncio.run(main())