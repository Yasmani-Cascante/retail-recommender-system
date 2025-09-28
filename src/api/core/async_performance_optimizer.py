#!/usr/bin/env python3
"""
Async Performance Optimizer - Solución Crítica para Performance
==============================================================

Implementa operaciones async-first para resolver el problema de response times
de 12,234ms → <2,000ms objetivo.

NUEVA IMPLEMENTACIÓN: Paralelización de operaciones independientes
CRÍTICO: Reduce blocking operations en event loop
"""

import asyncio
import time
import logging
import json
from typing import Dict, Any, Optional, Callable, List, Union
from dataclasses import dataclass
from enum import Enum
import traceback

logger = logging.getLogger(__name__)

class OperationType(Enum):
    """Tipos de operaciones para optimización específica"""
    INTENT_RECOGNITION = "intent_recognition"
    MARKET_CONTEXT = "market_context"
    USER_PROFILE = "user_profile"
    PERSONALIZATION = "personalization"
    CLAUDE_API = "claude_api"
    REDIS_OPERATION = "redis_operation"
    RECOMMENDATION_GENERATION = "recommendation_generation"

@dataclass
class AsyncOperationResult:
    """Resultado de operación asíncrona"""
    operation_type: OperationType
    success: bool
    result: Any
    execution_time_ms: float
    error: Optional[str] = None

class AsyncPerformanceOptimizer:
    """
    Optimizador de performance que implementa async-first operations
    para resolver el cuello de botella de response times
    """
    
    def __init__(self):
        self.metrics = {
            "parallel_operations_executed": 0,
            "total_time_saved_ms": 0,
            "avg_parallelization_factor": 0.0,
            "timeout_fallbacks_triggered": 0
        }
        logger.info("🚀 AsyncPerformanceOptimizer initialized - Critical performance mode")
    
    async def execute_parallel_operations(
        self, 
        operations: List[Dict[str, Any]]
    ) -> Dict[str, AsyncOperationResult]:
        """
        Ejecutar múltiples operaciones en paralelo para reducir latencia total.
        
        SOLUCIÓN CRÍTICA: Elimina operaciones secuenciales que causan 12s+ response times
        
        Args:
            operations: Lista de operaciones con formato:
                [
                    {
                        "name": "intent_recognition",
                        "type": OperationType.INTENT_RECOGNITION,
                        "function": callable,
                        "args": [],
                        "kwargs": {},
                        "timeout": 2.0
                    }
                ]
        
        Returns:
            Dict con resultados de todas las operaciones
        """
        start_time = time.time()
        
        logger.info(f"🔄 Executing {len(operations)} operations in parallel")
        
        # Crear tasks para todas las operaciones
        tasks = {}
        for op in operations:
            task_name = op["name"]
            operation_func = op["function"]
            operation_args = op.get("args", [])
            operation_kwargs = op.get("kwargs", {})
            operation_timeout = op.get("timeout", 5.0)
            operation_type = op.get("type", OperationType.INTENT_RECOGNITION)
            
            # Wrap operation with timeout and error handling
            async def execute_single_operation(
                func=operation_func, 
                args=operation_args, 
                kwargs=operation_kwargs,
                timeout=operation_timeout,
                op_type=operation_type,
                name=task_name
            ):
                op_start = time.time()
                try:
                    # Execute with timeout
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=timeout
                    )
                    
                    execution_time = (time.time() - op_start) * 1000
                    logger.debug(f"✅ {name} completed in {execution_time:.1f}ms")
                    
                    return AsyncOperationResult(
                        operation_type=op_type,
                        success=True,
                        result=result,
                        execution_time_ms=execution_time
                    )
                    
                except asyncio.TimeoutError:
                    execution_time = (time.time() - op_start) * 1000
                    logger.warning(f"⏱️ {name} timeout after {execution_time:.1f}ms")
                    self.metrics["timeout_fallbacks_triggered"] += 1
                    
                    return AsyncOperationResult(
                        operation_type=op_type,
                        success=False,
                        result=None,
                        execution_time_ms=execution_time,
                        error=f"Timeout after {timeout}s"
                    )
                    
                except Exception as e:
                    execution_time = (time.time() - op_start) * 1000
                    logger.error(f"❌ {name} failed after {execution_time:.1f}ms: {e}")
                    
                    return AsyncOperationResult(
                        operation_type=op_type,
                        success=False,
                        result=None,
                        execution_time_ms=execution_time,
                        error=str(e)
                    )
            
            tasks[task_name] = asyncio.create_task(execute_single_operation())
        
        # Wait for all tasks to complete
        try:
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            
            # Process results
            operation_results = {}
            for (task_name, task), result in zip(tasks.items(), results):
                if isinstance(result, Exception):
                    operation_results[task_name] = AsyncOperationResult(
                        operation_type=OperationType.INTENT_RECOGNITION,
                        success=False,
                        result=None,
                        execution_time_ms=0,
                        error=str(result)
                    )
                else:
                    operation_results[task_name] = result
            
            total_time = (time.time() - start_time) * 1000
            
            # Calculate metrics
            successful_ops = sum(1 for r in operation_results.values() if r.success)
            sequential_time_estimate = sum(r.execution_time_ms for r in operation_results.values())
            time_saved = sequential_time_estimate - total_time
            
            # Update metrics
            self.metrics["parallel_operations_executed"] += 1
            self.metrics["total_time_saved_ms"] += time_saved
            self.metrics["avg_parallelization_factor"] = (
                sequential_time_estimate / total_time if total_time > 0 else 1.0
            )
            
            logger.info(
                f"✅ Parallel execution completed: {successful_ops}/{len(operations)} successful, "
                f"total: {total_time:.1f}ms, estimated sequential: {sequential_time_estimate:.1f}ms, "
                f"time saved: {time_saved:.1f}ms"
            )
            
            return operation_results
            
        except Exception as e:
            logger.error(f"❌ Parallel execution failed: {e}")
            traceback.print_exc()
            return {}
    
    async def execute_with_timeout_and_fallback(
        self, 
        operation: Callable,
        timeout: float,
        fallback: Optional[Callable] = None,
        operation_type: OperationType = OperationType.INTENT_RECOGNITION,
        *args,
        **kwargs
    ) -> AsyncOperationResult:
        """
        Ejecutar operación con timeout agresivo y fallback opcional.
        
        SOLUCIÓN CRÍTICA: Previene que operaciones lentas bloqueen el sistema
        
        Args:
            operation: Función a ejecutar
            timeout: Timeout en segundos
            fallback: Función fallback opcional
            operation_type: Tipo de operación para métricas
            *args, **kwargs: Argumentos para la operación
            
        Returns:
            AsyncOperationResult con resultado o fallback
        """
        start_time = time.time()
        
        try:
            # Execute main operation with timeout
            result = await asyncio.wait_for(
                operation(*args, **kwargs),
                timeout=timeout
            )
            
            execution_time = (time.time() - start_time) * 1000
            logger.debug(f"✅ {operation_type.value} completed in {execution_time:.1f}ms")
            
            return AsyncOperationResult(
                operation_type=operation_type,
                success=True,
                result=result,
                execution_time_ms=execution_time
            )
            
        except asyncio.TimeoutError:
            execution_time = (time.time() - start_time) * 1000
            logger.warning(f"⏱️ {operation_type.value} timeout after {execution_time:.1f}ms")
            
            # Execute fallback if available
            if fallback:
                try:
                    fallback_start = time.time()
                    fallback_result = await fallback(*args, **kwargs)
                    fallback_time = (time.time() - fallback_start) * 1000
                    
                    logger.info(f"🔄 Fallback executed in {fallback_time:.1f}ms")
                    self.metrics["timeout_fallbacks_triggered"] += 1
                    
                    return AsyncOperationResult(
                        operation_type=operation_type,
                        success=True,
                        result=fallback_result,
                        execution_time_ms=execution_time + fallback_time,
                        error=f"Main operation timeout, fallback used"
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Fallback failed: {e}")
            
            return AsyncOperationResult(
                operation_type=operation_type,
                success=False,
                result=None,
                execution_time_ms=execution_time,
                error=f"Timeout after {timeout}s"
            )
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"❌ {operation_type.value} failed after {execution_time:.1f}ms: {e}")
            
            return AsyncOperationResult(
                operation_type=operation_type,
                success=False,
                result=None,
                execution_time_ms=execution_time,
                error=str(e)
            )
    
    async def execute_redis_pipeline_operations(
        self,
        redis_client,
        operations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Ejecutar operaciones Redis en pipeline para optimizar latencia.
        
        SOLUCIÓN CRÍTICA: Redis operations no optimizadas causan 25,854ms en state persistence
        
        Args:
            redis_client: Cliente Redis
            operations: Lista de operaciones Redis
        
        Returns:
            Dict con resultados de pipeline
        """
        start_time = time.time()
        
        try:
            # Create Redis pipeline
            pipe = redis_client.pipeline()
            
            # Add operations to pipeline
            operation_keys = []
            for op in operations:
                op_type = op["type"]  # get, set, hget, hset, etc.
                op_key = op["key"]
                op_value = op.get("value")
                
                operation_keys.append(op_key)
                
                if op_type == "get":
                    pipe.get(op_key)
                elif op_type == "set":
                    pipe.set(op_key, op_value, ex=op.get("ttl"))
                elif op_type == "hget":
                    pipe.hget(op_key, op.get("field"))
                elif op_type == "hset":
                    pipe.hset(op_key, op.get("field"), op_value)
                elif op_type == "exists":
                    pipe.exists(op_key)
                elif op_type == "delete":
                    pipe.delete(op_key)
            
            # Execute pipeline
            results = await pipe.execute()
            
            execution_time = (time.time() - start_time) * 1000
            
            # Map results to operation keys
            pipeline_results = {}
            for key, result in zip(operation_keys, results):
                pipeline_results[key] = result
            
            logger.info(f"✅ Redis pipeline executed {len(operations)} operations in {execution_time:.1f}ms")
            
            return {
                "success": True,
                "results": pipeline_results,
                "execution_time_ms": execution_time,
                "operations_count": len(operations)
            }
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"❌ Redis pipeline failed after {execution_time:.1f}ms: {e}")
            
            return {
                "success": False,
                "results": {},
                "execution_time_ms": execution_time,
                "error": str(e)
            }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Obtener métricas de performance del optimizador"""
        return {
            "async_performance_optimizer": {
                **self.metrics,
                "status": "active",
                "optimization_level": "critical"
            }
        }

# Global instance
async_performance_optimizer = AsyncPerformanceOptimizer()
