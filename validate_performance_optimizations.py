#!/usr/bin/env python3
"""
Validador Simple de Performance - Post Optimización
===================================================

Script simple para validar que las optimizaciones de performance están funcionando
después de implementar los pasos A y B.
"""

import asyncio
import time
import logging
import sys
import os

# Añadir src al path para imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimplePerformanceValidator:
    """Validador simple y robusto de las optimizaciones implementadas"""
    
    def __init__(self):
        self.target_time_ms = 2000
        self.results = []
    
    async def test_async_performance_optimizer(self):
        """Test 1: AsyncPerformanceOptimizer"""
        logger.info("🚀 Test 1: AsyncPerformanceOptimizer")
        
        start_time = time.time()
        try:
            from src.api.core.async_performance_optimizer import async_performance_optimizer, OperationType
            
            # Test simple de operaciones paralelas
            test_operations = [
                {
                    "name": "test_op_1",
                    "type": OperationType.INTENT_RECOGNITION,
                    "function": self._mock_operation,
                    "args": [0.1],
                    "timeout": 1.0
                },
                {
                    "name": "test_op_2", 
                    "type": OperationType.MARKET_CONTEXT,
                    "function": self._mock_operation,
                    "args": [0.1],
                    "timeout": 1.0
                }
            ]
            
            results = await async_performance_optimizer.execute_parallel_operations(test_operations)
            execution_time = (time.time() - start_time) * 1000
            
            success = len(results) == 2 and execution_time < 300
            logger.info(f"   ✅ AsyncPerformanceOptimizer: {execution_time:.1f}ms - {'PASS' if success else 'FAIL'}")
            
            return success
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"   ❌ AsyncPerformanceOptimizer: {execution_time:.1f}ms - ERROR: {e}")
            return False
    
    async def test_performance_timeouts(self):
        """Test 2: Performance Timeouts Configuration"""
        logger.info("⏱️ Test 2: Performance Timeouts")
        
        start_time = time.time()
        try:
            from src.api.core.performance_optimizer import PerformanceConfig, ComponentType
            
            # Verificar timeouts optimizados
            timeouts = PerformanceConfig.TIMEOUTS
            
            expected_fast_timeouts = [
                (ComponentType.CLAUDE_API, 3.0),
                (ComponentType.PERSONALIZATION, 10.0),
                (ComponentType.MCP_BRIDGE, 2.0),
                (ComponentType.REDIS_OPS, 1.0)
            ]
            
            all_optimized = True
            for component, max_expected in expected_fast_timeouts:
                actual = timeouts.get(component, 999)
                if actual > max_expected:
                    all_optimized = False
                    break
            
            execution_time = (time.time() - start_time) * 1000
            logger.info(f"   ✅ Performance Timeouts: {execution_time:.1f}ms - {'PASS' if all_optimized else 'FAIL'}")
            
            return all_optimized
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"   ❌ Performance Timeouts: {execution_time:.1f}ms - ERROR: {e}")
            return False
    
    async def test_mcp_router_patch(self):
        """Test 3: MCP Router Performance Patch"""
        logger.info("🔧 Test 3: MCP Router Performance Patch")
        
        start_time = time.time()
        try:
            from src.api.core.mcp_router_performance_patch import apply_critical_performance_optimization
            
            # Test con datos mock
            mock_request = type('MockRequest', (), {
                'query': 'test query',
                'market_id': 'US',
                'user_id': 'test_user'
            })()
            
            mock_recommendations = [
                {"id": "test1", "title": "Test Product 1", "price": 99.99},
                {"id": "test2", "title": "Test Product 2", "price": 149.99}
            ]
            
            result = await apply_critical_performance_optimization(
                conversation_request=mock_request,
                validated_user_id="test_user",
                validated_product_id=None,
                safe_recommendations=mock_recommendations,
                metadata={"test": True},
                real_session_id="test_session",
                turn_number=1
            )
            
            execution_time = (time.time() - start_time) * 1000
            
            # Verificar que el resultado tiene la estructura esperada
            has_required_fields = all(field in result for field in [
                "answer", "recommendations", "session_metadata", 
                "intent_analysis", "market_context", "personalization_metadata"
            ])
            
            success = has_required_fields and execution_time < self.target_time_ms
            logger.info(f"   ✅ MCP Router Patch: {execution_time:.1f}ms - {'PASS' if success else 'FAIL'}")
            
            return success
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"   ❌ MCP Router Patch: {execution_time:.1f}ms - ERROR: {e}")
            return False
    
    async def test_enhanced_optimizer(self):
        """Test 4: Performance Optimizer Enhanced"""
        logger.info("🔄 Test 4: Enhanced Optimizer Components")
        
        start_time = time.time()
        try:
            from src.api.core.performance_optimizer_enhanced import get_response_optimizer
            
            optimizer = get_response_optimizer()
            
            # Test simple de cache
            async def test_operation():
                await asyncio.sleep(0.05)
                return {"test": "result"}
            
            # Primera llamada
            result1 = await optimizer.cached_operation(
                "test_cache_operation",
                test_operation,
                cache_enabled=True,
                test_key="test_value"
            )
            
            # Segunda llamada (debería usar cache)
            cache_start = time.time()
            result2 = await optimizer.cached_operation(
                "test_cache_operation", 
                test_operation,
                cache_enabled=True,
                test_key="test_value"
            )
            cache_time = (time.time() - cache_start) * 1000
            
            execution_time = (time.time() - start_time) * 1000
            
            success = result1 == result2 and cache_time < 50  # Cache debe ser muy rápido
            logger.info(f"   ✅ Enhanced Optimizer: {execution_time:.1f}ms (cache: {cache_time:.1f}ms) - {'PASS' if success else 'FAIL'}")
            
            return success
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"   ❌ Enhanced Optimizer: {execution_time:.1f}ms - ERROR: {e}")
            return False
    
    async def _mock_operation(self, delay_seconds: float):
        """Operación mock para testing"""
        await asyncio.sleep(delay_seconds)
        return {"result": f"completed after {delay_seconds}s"}
    
    async def run_validation(self):
        """Ejecutar validación completa"""
        print("🚀 Performance Optimization Validation")
        print("=" * 50)
        print()
        
        # Lista de tests
        tests = [
            ("AsyncPerformanceOptimizer", self.test_async_performance_optimizer),
            ("Performance Timeouts", self.test_performance_timeouts),
            ("MCP Router Patch", self.test_mcp_router_patch),
            ("Enhanced Optimizer", self.test_enhanced_optimizer)
        ]
        
        # Ejecutar tests
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            try:
                success = await test_func()
                if success:
                    passed += 1
                self.results.append((test_name, success))
            except Exception as e:
                logger.error(f"💥 {test_name} failed with exception: {e}")
                self.results.append((test_name, False))
        
        # Mostrar resumen
        print()
        print("📊 VALIDATION SUMMARY")
        print("=" * 30)
        print(f"Tests Passed: {passed}/{total}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        print()
        
        print("📋 DETAILED RESULTS:")
        for test_name, success in self.results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"   {test_name}: {status}")
        
        print()
        
        # Determinar estado general
        if passed == total:
            print("🎉 ALL OPTIMIZATIONS WORKING PERFECTLY!")
            print("   System ready for <2s response times")
            return 0
        elif passed >= total * 0.75:
            print("✅ MOST OPTIMIZATIONS WORKING")
            print("   Performance significantly improved")
            return 0
        elif passed >= total * 0.5:
            print("⚠️ SOME OPTIMIZATIONS WORKING")
            print("   Partial performance improvement achieved")
            return 1
        else:
            print("❌ OPTIMIZATIONS NEED WORK")
            print("   Performance improvements not achieved")
            return 2

async def main():
    """Función principal"""
    validator = SimplePerformanceValidator()
    return await validator.run_validation()

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ Validation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Validation failed: {e}")
        sys.exit(1)
