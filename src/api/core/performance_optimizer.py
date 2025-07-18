#!/usr/bin/env python3
"""
Performance Optimization Manager
Gestiona timeouts y circuit breakers optimizados para components MCP
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ComponentType(Enum):
    """Tipos de componentes con timeouts específicos"""
    CLAUDE_API = "claude_api"
    MCP_BRIDGE = "mcp_bridge"
    PERSONALIZATION = "personalization"
    RETAIL_API = "retail_api"
    REDIS_OPS = "redis_ops"

@dataclass
class PerformanceConfig:
    """Configuración optimizada de performance por componente"""
    
    # Timeouts optimizados (en segundos)
    TIMEOUTS = {
        ComponentType.CLAUDE_API: 3.0,        # Reducido de 10s → 3s
        ComponentType.MCP_BRIDGE: 2.0,        # Reducido de 5s → 2s  
        ComponentType.PERSONALIZATION: 10.0,   # 🔧 FINAL OPTIMIZATION: 8s → 10s para eliminar timeouts
        ComponentType.RETAIL_API: 3.0,        # Nuevo timeout específico
        ComponentType.REDIS_OPS: 1.0,         # Operaciones Redis rápidas
    }
    
    # Circuit breaker thresholds optimizados
    CIRCUIT_BREAKER_CONFIG = {
        ComponentType.CLAUDE_API: {"failure_threshold": 3, "recovery_time": 30},
        ComponentType.MCP_BRIDGE: {"failure_threshold": 2, "recovery_time": 20},
        ComponentType.PERSONALIZATION: {"failure_threshold": 6, "recovery_time": 30},  # 🔧 RELAXED: 4→6 failures, 45s→30s
        ComponentType.RETAIL_API: {"failure_threshold": 5, "recovery_time": 60},
    }
    
    # Retry policies optimizadas
    RETRY_CONFIG = {
        ComponentType.CLAUDE_API: {"max_retries": 1, "backoff": 0.5},
        ComponentType.MCP_BRIDGE: {"max_retries": 2, "backoff": 0.3},
        ComponentType.PERSONALIZATION: {"max_retries": 1, "backoff": 1.0},
        ComponentType.RETAIL_API: {"max_retries": 1, "backoff": 0.5},
    }

class OptimizedCircuitBreaker:
    """Circuit breaker optimizado para performance"""
    
    def __init__(self, component_type: ComponentType):
        self.component_type = component_type
        config = PerformanceConfig.CIRCUIT_BREAKER_CONFIG.get(component_type, {})
        
        self.failure_threshold = config.get("failure_threshold", 3)
        self.recovery_time = config.get("recovery_time", 30)
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with optimized circuit breaker"""
        
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
                logger.info(f"Circuit breaker {self.component_type.value} → HALF_OPEN")
            else:
                raise CircuitBreakerOpenError(f"Circuit breaker OPEN for {self.component_type.value}")
        
        start_time = time.time()
        try:
            # Apply component-specific timeout
            timeout = PerformanceConfig.TIMEOUTS.get(self.component_type, 5.0)
            
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            
            # Success - reset failure count
            self._on_success()
            
            execution_time = (time.time() - start_time) * 1000
            logger.debug(f"✅ {self.component_type.value} executed in {execution_time:.1f}ms")
            
            return result
            
        except asyncio.TimeoutError:
            execution_time = (time.time() - start_time) * 1000
            logger.warning(f"⏱️ {self.component_type.value} timeout after {execution_time:.1f}ms")
            self._on_failure()
            raise TimeoutError(f"{self.component_type.value} timeout")
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"❌ {self.component_type.value} failed after {execution_time:.1f}ms: {e}")
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset"""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.recovery_time
    
    def _on_success(self):
        """Handle successful operation"""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failure_count = 0
            logger.info(f"✅ Circuit breaker {self.component_type.value} → CLOSED")
        elif self.state == "CLOSED":
            self.failure_count = max(0, self.failure_count - 1)
    
    def _on_failure(self):
        """Handle failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold and self.state != "OPEN":
            self.state = "OPEN"
            logger.error(f"💥 Circuit breaker {self.component_type.value} → OPEN (failures: {self.failure_count})")
    
    def reset_circuit_breaker(self):
        """Manually reset circuit breaker - useful when stuck OPEN"""
        previous_state = self.state
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_failure_time = None
        logger.info(f"🔄 Circuit breaker {self.component_type.value} manually reset: {previous_state} → CLOSED")
    
    def get_status(self) -> dict:
        """Get current circuit breaker status"""
        return {
            "component": self.component_type.value,
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "recovery_time": self.recovery_time
        }

class PerformanceOptimizer:
    """Performance optimizer with circuit breakers and timeout management"""
    
    def __init__(self):
        self.circuit_breakers = {}
        self.performance_metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "timeout_calls": 0,
            "circuit_breaker_blocks": 0
        }
    
    def get_circuit_breaker(self, component_type: ComponentType) -> OptimizedCircuitBreaker:
        """Get or create circuit breaker for component"""
        if component_type not in self.circuit_breakers:
            self.circuit_breakers[component_type] = OptimizedCircuitBreaker(component_type)
        return self.circuit_breakers[component_type]
    
    async def execute_with_optimization(self, component_type: ComponentType, func: Callable, *args, **kwargs):
        """Execute function with performance optimization"""
        circuit_breaker = self.get_circuit_breaker(component_type)
        self.performance_metrics["total_calls"] += 1
        
        try:
            result = await circuit_breaker.call(func, *args, **kwargs)
            self.performance_metrics["successful_calls"] += 1
            return result
            
        except CircuitBreakerOpenError:
            self.performance_metrics["circuit_breaker_blocks"] += 1
            logger.error(f"💥 All retries exhausted for {component_type.value}")
            raise
            
        except TimeoutError:
            self.performance_metrics["timeout_calls"] += 1
            raise
            
        except Exception as e:
            self.performance_metrics["failed_calls"] += 1
            raise
    
    def reset_circuit_breaker(self, component_type: ComponentType):
        """Reset circuit breaker for specific component"""
        if component_type in self.circuit_breakers:
            self.circuit_breakers[component_type].reset_circuit_breaker()
    
    def get_circuit_breaker_status(self, component_type: ComponentType) -> dict:
        """Get circuit breaker status"""
        if component_type in self.circuit_breakers:
            return self.circuit_breakers[component_type].get_status()
        return {"component": component_type.value, "state": "NOT_INITIALIZED"}
    
    def get_performance_report(self) -> dict:
        """Get comprehensive performance report"""
        return {
            "metrics": self.performance_metrics,
            "circuit_breakers": {
                comp_type.value: self.get_circuit_breaker_status(comp_type)
                for comp_type in self.circuit_breakers.keys()
            },
            "configuration": {
                "timeouts": {comp.value: timeout for comp, timeout in PerformanceConfig.TIMEOUTS.items()},
                "thresholds": {comp.value: config for comp, config in PerformanceConfig.CIRCUIT_BREAKER_CONFIG.items()}
            }
        }

# Global instance
performance_optimizer = PerformanceOptimizer()

class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open"""
    pass

class TimeoutError(Exception):
    """Custom timeout exception"""
    pass

# Convenience functions for easy integration
async def execute_claude_call(func, *args, **kwargs):
    """Execute Claude API call with optimization"""
    return await performance_optimizer.execute_with_optimization(
        ComponentType.CLAUDE_API, func, *args, **kwargs
    )

async def execute_mcp_call(func, *args, **kwargs):
    """Execute MCP Bridge call with optimization"""
    return await performance_optimizer.execute_with_optimization(
        ComponentType.MCP_BRIDGE, func, *args, **kwargs
    )

async def execute_personalization_call(func, *args, **kwargs):
    """Execute Personalization Engine call with optimization"""
    return await performance_optimizer.execute_with_optimization(
        ComponentType.PERSONALIZATION, func, *args, **kwargs
    )

async def execute_retail_api_call(func, *args, **kwargs):
    """Execute Google Retail API call with optimization"""
    return await performance_optimizer.execute_with_optimization(
        ComponentType.RETAIL_API, func, *args, **kwargs
    )

async def execute_redis_call(func, *args, **kwargs):
    """Execute Redis operation with optimization"""
    return await performance_optimizer.execute_with_optimization(
        ComponentType.REDIS_OPS, func, *args, **kwargs
    )

def get_performance_report():
    """Get current performance report"""
    return performance_optimizer.get_performance_report()

if __name__ == "__main__":
    # Test basic functionality
    print("Performance Optimizer initialized with optimized timeouts:")
    for comp_type, timeout in PerformanceConfig.TIMEOUTS.items():
        print(f"  {comp_type.value}: {timeout}s")
