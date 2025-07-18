#!/usr/bin/env python3
"""
Parallel Processing Optimizer
Implementa procesamiento paralelo para operaciones concurrentes en MCP
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import functools

logger = logging.getLogger(__name__)

@dataclass
class ParallelTask:
    """Representa una tarea para procesamiento paralelo"""
    name: str
    func: Callable
    args: tuple = ()
    kwargs: dict = None
    timeout: float = 5.0
    priority: int = 1  # 1=alta, 2=media, 3=baja
    required: bool = True  # Si es crítica para el resultado final

class ParallelProcessor:
    """Gestor de procesamiento paralelo optimizado"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.metrics = {
            "parallel_executions": 0,
            "successful_parallel": 0,
            "failed_parallel": 0,
            "avg_parallel_time": 0.0,
            "time_saved": 0.0
        }
    
    async def execute_parallel_tasks(
        self, 
        tasks: List[ParallelTask],
        fail_fast: bool = False
    ) -> Dict[str, Any]:
        """
        Ejecuta múltiples tareas en paralelo con gestión de errores
        
        Args:
            tasks: Lista de tareas a ejecutar
            fail_fast: Si debe fallar inmediatamente al primer error
            
        Returns:
            Dict con resultados de cada tarea
        """
        start_time = time.time()
        self.metrics["parallel_executions"] += 1
        
        # Agrupar tareas por prioridad
        priority_groups = self._group_by_priority(tasks)
        results = {}
        
        # Ejecutar por grupos de prioridad
        for priority in sorted(priority_groups.keys()):
            group_tasks = priority_groups[priority]
            logger.debug(f"Executing priority {priority} tasks: {[t.name for t in group_tasks]}")
            
            # Crear tareas asyncio para este grupo
            async_tasks = []
            for task in group_tasks:
                async_task = self._create_async_task(task)
                async_tasks.append((task.name, async_task, task.required))
            
            # Ejecutar grupo en paralelo
            group_results = await self._execute_task_group(async_tasks, fail_fast)
            results.update(group_results)
            
            # Si hay errores críticos y fail_fast está habilitado
            if fail_fast and any(
                result.get("error") and task[2]  # task[2] es required
                for task, result in zip(group_tasks, group_results.values())
            ):
                break
        
        # Actualizar métricas
        execution_time = (time.time() - start_time) * 1000
        self._update_metrics(execution_time, results)
        
        return {
            "results": results,
            "execution_time_ms": execution_time,
            "parallel_efficiency": self._calculate_efficiency(tasks, execution_time),
            "timestamp": time.time()
        }
    
    def _group_by_priority(self, tasks: List[ParallelTask]) -> Dict[int, List[ParallelTask]]:
        """Agrupa tareas por prioridad"""
        groups = {}
        for task in tasks:
            if task.priority not in groups:
                groups[task.priority] = []
            groups[task.priority].append(task)
        return groups
    
    async def _create_async_task(self, task: ParallelTask) -> Any:
        """Crea una tarea asyncio para una ParallelTask"""
        try:
            kwargs = task.kwargs or {}
            
            # Ejecutar con timeout
            result = await asyncio.wait_for(
                task.func(*task.args, **kwargs),
                timeout=task.timeout
            )
            
            return {
                "success": True,
                "result": result,
                "task_name": task.name
            }
            
        except asyncio.TimeoutError:
            logger.warning(f"Task {task.name} timed out after {task.timeout}s")
            return {
                "success": False,
                "error": f"timeout_after_{task.timeout}s",
                "task_name": task.name
            }
            
        except Exception as e:
            logger.error(f"Task {task.name} failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_name": task.name
            }
    
    async def _execute_task_group(
        self, 
        async_tasks: List[Tuple[str, Any, bool]], 
        fail_fast: bool
    ) -> Dict[str, Any]:
        """Ejecuta un grupo de tareas en paralelo"""
        
        task_futures = [task[1] for task in async_tasks]
        task_names = [task[0] for task in async_tasks]
        
        try:
            if fail_fast:
                # Ejecutar con fail-fast
                results = await asyncio.gather(*task_futures, return_exceptions=True)
            else:
                # Ejecutar todas, capturando excepciones
                results = await asyncio.gather(*task_futures, return_exceptions=True)
            
            # Procesar resultados
            processed_results = {}
            for i, (name, result) in enumerate(zip(task_names, results)):
                if isinstance(result, Exception):
                    processed_results[name] = {
                        "success": False,
                        "error": str(result),
                        "task_name": name
                    }
                else:
                    processed_results[name] = result
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Error in task group execution: {e}")
            return {name: {"success": False, "error": str(e)} for name in task_names}
    
    def _update_metrics(self, execution_time: float, results: Dict[str, Any]):
        """Actualiza métricas de performance"""
        successful = sum(
            1 for result in results.values() 
            if isinstance(result, dict) and result.get("success", False)
        )
        
        if successful > 0:
            self.metrics["successful_parallel"] += 1
        else:
            self.metrics["failed_parallel"] += 1
        
        # Actualizar tiempo promedio
        if self.metrics["avg_parallel_time"] == 0:
            self.metrics["avg_parallel_time"] = execution_time
        else:
            self.metrics["avg_parallel_time"] = (
                self.metrics["avg_parallel_time"] * 0.8 + execution_time * 0.2
            )
    
    def _calculate_efficiency(self, tasks: List[ParallelTask], actual_time: float) -> float:
        """Calcula la eficiencia del procesamiento paralelo"""
        sequential_time = sum(task.timeout for task in tasks) * 1000  # Convert to ms
        if sequential_time > 0:
            efficiency = (sequential_time - actual_time) / sequential_time
            self.metrics["time_saved"] += max(0, sequential_time - actual_time)
            return max(0, efficiency)
        return 0.0
    
    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas de procesamiento paralelo"""
        success_rate = 0
        if self.metrics["parallel_executions"] > 0:
            success_rate = (
                self.metrics["successful_parallel"] / 
                self.metrics["parallel_executions"]
            ) * 100
        
        return {
            "parallel_executions": self.metrics["parallel_executions"],
            "success_rate": f"{success_rate:.1f}%",
            "avg_execution_time": f"{self.metrics['avg_parallel_time']:.1f}ms",
            "total_time_saved": f"{self.metrics['time_saved']:.1f}ms",
            "max_workers": self.max_workers
        }
    
    async def cleanup(self):
        """Limpia recursos del executor"""
        self.executor.shutdown(wait=True)

# Global parallel processor instance
parallel_processor = ParallelProcessor(max_workers=4)

# Helper functions para use cases comunes

async def execute_mcp_operations_parallel(
    mcp_call: Callable = None,
    personalization_call: Callable = None,
    market_context_call: Callable = None,
    intent_analysis_call: Callable = None
) -> Dict[str, Any]:
    """
    Ejecuta operaciones MCP comunes en paralelo
    
    Args:
        mcp_call: Función para llamada MCP principal
        personalization_call: Función para personalización
        market_context_call: Función para contexto de mercado
        intent_analysis_call: Función para análisis de intención
        
    Returns:
        Resultados de todas las operaciones ejecutadas en paralelo
    """
    tasks = []
    
    if mcp_call:
        tasks.append(ParallelTask(
            name="mcp_recommendations",
            func=mcp_call,
            timeout=3.0,
            priority=1,  # Alta prioridad
            required=True
        ))
    
    if personalization_call:
        tasks.append(ParallelTask(
            name="personalization",
            func=personalization_call,
            timeout=4.0,
            priority=2,  # Media prioridad
            required=False  # No crítica
        ))
    
    if market_context_call:
        tasks.append(ParallelTask(
            name="market_context",
            func=market_context_call,
            timeout=2.0,
            priority=1,  # Alta prioridad
            required=True
        ))
    
    if intent_analysis_call:
        tasks.append(ParallelTask(
            name="intent_analysis",
            func=intent_analysis_call,
            timeout=1.5,
            priority=3,  # Baja prioridad
            required=False
        ))
    
    if not tasks:
        return {"results": {}, "execution_time_ms": 0}
    
    return await parallel_processor.execute_parallel_tasks(tasks)

async def execute_data_fetch_parallel(
    redis_calls: List[Callable] = None,
    api_calls: List[Callable] = None,
    cache_calls: List[Callable] = None
) -> Dict[str, Any]:
    """
    Ejecuta operaciones de fetch de datos en paralelo
    Útil para cargar múltiples fuentes de datos simultáneamente
    """
    tasks = []
    
    # Redis calls (rápidas, alta prioridad)
    if redis_calls:
        for i, call in enumerate(redis_calls):
            tasks.append(ParallelTask(
                name=f"redis_call_{i}",
                func=call,
                timeout=1.0,
                priority=1,
                required=True
            ))
    
    # API calls (más lentas, media prioridad)
    if api_calls:
        for i, call in enumerate(api_calls):
            tasks.append(ParallelTask(
                name=f"api_call_{i}",
                func=call,
                timeout=3.0,
                priority=2,
                required=False
            ))
    
    # Cache calls (rápidas, baja prioridad)
    if cache_calls:
        for i, call in enumerate(cache_calls):
            tasks.append(ParallelTask(
                name=f"cache_call_{i}",
                func=call,
                timeout=2.0,
                priority=3,
                required=False
            ))
    
    return await parallel_processor.execute_parallel_tasks(tasks)

def get_parallel_metrics() -> Dict[str, Any]:
    """Obtiene métricas de procesamiento paralelo"""
    return parallel_processor.get_metrics()

if __name__ == "__main__":
    # Test básico
    async def test_parallel():
        async def quick_task():
            await asyncio.sleep(0.1)
            return "quick_result"
        
        async def slow_task():
            await asyncio.sleep(0.5)
            return "slow_result"
        
        tasks = [
            ParallelTask("quick", quick_task, timeout=1.0, priority=1),
            ParallelTask("slow", slow_task, timeout=2.0, priority=2)
        ]
        
        result = await parallel_processor.execute_parallel_tasks(tasks)
        print("Parallel execution result:", result)
        print("Metrics:", parallel_processor.get_metrics())
    
    asyncio.run(test_parallel())
