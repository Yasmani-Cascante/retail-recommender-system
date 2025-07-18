#!/usr/bin/env python3
"""
Script de Validación Rápida para diagnóstico específico de Fase 2
Identifica exactamente qué componente está fallando
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

class QuickValidator:
    """Validador específico para diagnosticar problemas exactos"""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.api_key = "2fed9999056fab6dac5654238f0cae1c"
        self.results = {}
    
    async def run_quick_diagnostics(self):
        """Ejecutar diagnósticos específicos"""
        print("🔍 DIAGNÓSTICO ESPECÍFICO DE FASE 2")
        print("=" * 50)
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Verificar estructura de respuesta
            print("\n1. 🧪 Testing response structure...")
            await self._test_response_structure(session)
            
            # Test 2: Verificar PersonalizationEngine
            print("\n2. 🎯 Testing PersonalizationEngine...")
            await self._test_personalization_engine(session)
            
            # Test 3: Verificar timeouts
            print("\n3. ⏱️ Testing response times...")
            await self._test_response_times(session)
            
            # Test 4: Verificar componentes MCP
            print("\n4. 🌉 Testing MCP components...")
            await self._test_mcp_components(session)
        
        # Generar diagnóstico final
        print("\n" + "=" * 50)
        print("📋 DIAGNÓSTICO FINAL")
        print("=" * 50)
        await self._generate_diagnosis()
    
    async def _test_response_structure(self, session):
        """Test específico de estructura de respuesta"""
        try:
            payload = {
                "query": "Test structure response",
                "user_id": "test_structure",
                "market_id": "US",
                "n_recommendations": 2
            }
            
            headers = {
                "X-API-Key": self.api_key,
                "Content-Type": "application/json"
            }
            
            async with session.post(
                f"{self.base_url}/v1/mcp/conversation",
                headers=headers,
                json=payload,
                timeout=15
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Verificar campos esperados
                    expected_fields = [
                        'answer', 'recommendations', 'session_metadata',
                        'intent_analysis', 'market_context', 'personalization_metadata'
                    ]
                    
                    present_fields = []
                    missing_fields = []
                    
                    for field in expected_fields:
                        if field in data:
                            present_fields.append(field)
                        else:
                            missing_fields.append(field)
                    
                    self.results['structure_test'] = {
                        'status': 'PASS' if len(missing_fields) == 0 else 'PARTIAL',
                        'present_fields': present_fields,
                        'missing_fields': missing_fields,
                        'response_size': len(str(data))
                    }
                    
                    print(f"   ✅ Response: HTTP {response.status}")
                    print(f"   📊 Present fields: {len(present_fields)}/{len(expected_fields)}")
                    print(f"   ✅ Fields: {', '.join(present_fields)}")
                    if missing_fields:
                        print(f"   ❌ Missing: {', '.join(missing_fields)}")
                    
                    # Verificar contenido de personalization_metadata
                    if 'personalization_metadata' in data:
                        p_meta = data['personalization_metadata']
                        if p_meta and len(p_meta) > 0:
                            print(f"   ✅ Personalization metadata: Present with {len(p_meta)} fields")
                        else:
                            print(f"   ⚠️ Personalization metadata: Empty object")
                    
                else:
                    self.results['structure_test'] = {
                        'status': 'FAIL',
                        'error': f"HTTP {response.status}",
                        'response': await response.text()
                    }
                    print(f"   ❌ HTTP {response.status}: {await response.text()}")
                    
        except Exception as e:
            self.results['structure_test'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"   ❌ Exception: {e}")
    
    async def _test_personalization_engine(self, session):
        """Test específico del PersonalizationEngine"""
        try:
            # Verificar endpoint de health específico de MCP
            async with session.get(
                f"{self.base_url}/v1/mcp/health",
                headers={"X-API-Key": self.api_key}
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Extraer información del PersonalizationEngine
                    pe_available = data.get('components', {}).get('personalization_engine', {})
                    pe_metrics = data.get('metrics', {}).get('engine_metrics', {})
                    
                    self.results['personalization_test'] = {
                        'status': 'PASS' if pe_available.get('available') else 'FAIL',
                        'engine_available': pe_available.get('available', False),
                        'engine_status': pe_available.get('status', 'unknown'),
                        'personalizations_generated': pe_metrics.get('personalizations_generated', 0),
                        'strategies_available': len(data.get('metrics', {}).get('strategies_available', []))
                    }
                    
                    print(f"   ✅ Engine available: {pe_available.get('available', False)}")
                    print(f"   📊 Status: {pe_available.get('status', 'unknown')}")
                    print(f"   🎯 Personalizations generated: {pe_metrics.get('personalizations_generated', 0)}")
                    print(f"   🧠 Strategies: {len(data.get('metrics', {}).get('strategies_available', []))}")
                    
                else:
                    self.results['personalization_test'] = {
                        'status': 'FAIL',
                        'error': f"HTTP {response.status}"
                    }
                    print(f"   ❌ MCP Health failed: HTTP {response.status}")
                    
        except Exception as e:
            self.results['personalization_test'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"   ❌ Exception: {e}")
    
    async def _test_response_times(self, session):
        """Test de tiempos de respuesta"""
        try:
            times = []
            
            for i in range(3):
                start_time = time.time()
                
                payload = {
                    "query": f"Speed test {i+1}",
                    "user_id": f"speed_test_{i}",
                    "market_id": "US",
                    "n_recommendations": 3
                }
                
                try:
                    async with session.post(
                        f"{self.base_url}/v1/mcp/conversation",
                        headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
                        json=payload,
                        timeout=20
                    ) as response:
                        
                        response_time = (time.time() - start_time) * 1000
                        times.append({
                            'time_ms': response_time,
                            'status': response.status,
                            'success': response.status == 200
                        })
                        
                except Exception as e:
                    times.append({
                        'time_ms': (time.time() - start_time) * 1000,
                        'status': 'ERROR',
                        'success': False,
                        'error': str(e)
                    })
            
            successful_times = [t['time_ms'] for t in times if t['success']]
            
            self.results['timing_test'] = {
                'status': 'PASS' if len(successful_times) > 0 else 'FAIL',
                'total_tests': len(times),
                'successful_tests': len(successful_times),
                'avg_time_ms': sum(successful_times) / len(successful_times) if successful_times else 0,
                'max_time_ms': max(successful_times) if successful_times else 0,
                'all_times': times
            }
            
            print(f"   ✅ Successful responses: {len(successful_times)}/3")
            if successful_times:
                print(f"   ⏱️ Average time: {self.results['timing_test']['avg_time_ms']:.0f}ms")
                print(f"   ⏱️ Max time: {self.results['timing_test']['max_time_ms']:.0f}ms")
            
        except Exception as e:
            self.results['timing_test'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"   ❌ Exception: {e}")
    
    async def _test_mcp_components(self, session):
        """Test de componentes MCP específicos"""
        try:
            # Test MCP Bridge connectivity
            bridge_result = await self._test_bridge_connectivity(session)
            
            # Test main system health
            system_result = await self._test_system_health(session)
            
            self.results['mcp_test'] = {
                'status': 'PASS' if bridge_result and system_result else 'PARTIAL',
                'bridge_healthy': bridge_result,
                'system_healthy': system_result
            }
            
            print(f"   ✅ MCP Bridge: {'Healthy' if bridge_result else 'Issues'}")
            print(f"   ✅ System Health: {'Healthy' if system_result else 'Issues'}")
            
        except Exception as e:
            self.results['mcp_test'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"   ❌ Exception: {e}")
    
    async def _test_bridge_connectivity(self, session):
        """Test conectividad del bridge"""
        try:
            async with session.get("http://localhost:3001/health") as response:
                return response.status == 200
        except:
            return False
    
    async def _test_system_health(self, session):
        """Test health del sistema principal"""
        try:
            async with session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('status') == 'ready'
                return False
        except:
            return False
    
    async def _generate_diagnosis(self):
        """Generar diagnóstico final"""
        
        print("\n🎯 RESULTADOS POR COMPONENTE:")
        for test_name, result in self.results.items():
            status = result.get('status', 'UNKNOWN')
            emoji = "✅" if status == "PASS" else "⚠️" if status == "PARTIAL" else "❌"
            print(f"   {emoji} {test_name}: {status}")
        
        # Análisis específico
        print("\n🔍 ANÁLISIS ESPECÍFICO:")
        
        # Estructura
        if 'structure_test' in self.results:
            struct = self.results['structure_test']
            if struct['status'] == 'PASS':
                print("   ✅ Response structure: PERFECT")
            else:
                print(f"   ⚠️ Response structure: Missing {struct.get('missing_fields', [])}")
        
        # Personalización
        if 'personalization_test' in self.results:
            pers = self.results['personalization_test']
            if pers.get('personalizations_generated', 0) == 0:
                print("   ⚠️ PersonalizationEngine: Available but not generating personalizations")
            else:
                print("   ✅ PersonalizationEngine: Actively generating personalizations")
        
        # Tiempos
        if 'timing_test' in self.results:
            timing = self.results['timing_test']
            avg_time = timing.get('avg_time_ms', 0)
            if avg_time > 5000:
                print(f"   ⚠️ Response times: SLOW ({avg_time:.0f}ms average)")
            elif avg_time > 2000:
                print(f"   ⚠️ Response times: ACCEPTABLE ({avg_time:.0f}ms average)")
            else:
                print(f"   ✅ Response times: GOOD ({avg_time:.0f}ms average)")
        
        # Recomendación final
        print("\n🚀 RECOMENDACIÓN:")
        
        # Contar problemas
        fails = sum(1 for r in self.results.values() if r.get('status') == 'FAIL')
        partials = sum(1 for r in self.results.values() if r.get('status') == 'PARTIAL')
        
        if fails == 0 and partials == 0:
            print("   🎉 SISTEMA PERFECTO - Ejecutar tests completos de Fase 2")
        elif fails == 0:
            print("   ✅ SISTEMA FUNCIONAL - Issues menores, proceder con optimizaciones")
        else:
            print("   🔧 SISTEMA NECESITA CORRECCIONES - Resolver problemas críticos primero")
        
        print(f"\n📊 Summary: {len(self.results)} tests, {fails} failures, {partials} warnings")

async def main():
    """Ejecutar validación rápida"""
    validator = QuickValidator()
    await validator.run_quick_diagnostics()

if __name__ == "__main__":
    asyncio.run(main())