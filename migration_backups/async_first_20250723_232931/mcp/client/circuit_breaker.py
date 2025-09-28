# src/api/mcp/client/circuit_breaker.py
"""
Circuit Breaker implementation para operaciones MCP

Implementa el patrón Circuit Breaker para proteger el sistema contra fallos
de servicios externos y proporcionar degradación elegante.
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Any, Callable, Optional, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    """Estados del Circuit Breaker"""
    CLOSED = "CLOSED"        # Normal operation
    OPEN = "OPEN"           # Circuit is open, calls are failing
    HALF_OPEN = "HALF_OPEN" # Testing if service recovered

@dataclass
class CircuitBreakerConfig:
    """Configuración del Circuit Breaker"""
    failure_threshold: int = 5          # Número de fallos para abrir el circuito
    timeout_seconds: int = 60           # Tiempo en estado OPEN antes de intentar HALF_OPEN
    success_threshold: int = 3          # Éxitos necesarios en HALF_OPEN para cerrar
    reset_timeout: int = 300           # Tiempo para reset completo de estadísticas
    max_timeout: int = 300             # Timeout máximo para operaciones

class CircuitBreakerError(Exception):
    """Excepción cuando el circuit breaker está abierto"""
    pass

class CircuitBreaker:
    """
    Circuit Breaker para operaciones MCP con soporte para:
    - Estados automáticos (CLOSED/OPEN/HALF_OPEN)
    - Fallback functions
    - Métricas de rendimiento
    - Reset automático
    """
    
    def __init__(self, 
                 name: str,
                 config: Optional[CircuitBreakerConfig] = None,
                 fallback_function: Optional[Callable] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.fallback_function = fallback_function
        
        # Estado interno
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.last_success_time = None
        self.total_calls = 0
        self.total_failures = 0
        
        # Lock para thread safety
        self._lock = asyncio.Lock()
        
        logger.info(f"Circuit breaker '{name}' initialized with config: {self.config}")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Ejecuta una función protegida por el circuit breaker
        
        Args:
            func: Función a ejecutar
            *args, **kwargs: Argumentos para la función
            
        Returns:
            Resultado de la función o del fallback
            
        Raises:
            CircuitBreakerError: Si el circuito está abierto y no hay fallback
        """
        async with self._lock:
            self.total_calls += 1
            
            # Verificar estado del circuito
            await self._update_state()
            
            if self.state == CircuitState.OPEN:
                logger.warning(f"Circuit breaker '{self.name}' is OPEN, rejecting call")
                if self.fallback_function:
                    logger.info(f"Using fallback function for '{self.name}'")
                    return await self._execute_fallback(*args, **kwargs)
                else:
                    raise CircuitBreakerError(f"Circuit breaker '{self.name}' is open")
            
            # Intentar ejecutar la función
            try:
                # Aplicar timeout
                result = await asyncio.wait_for(
                    func(*args, **kwargs), 
                    timeout=self.config.max_timeout
                )
                
                await self._record_success()
                return result
                
            except asyncio.TimeoutError:
                logger.error(f"Timeout in circuit breaker '{self.name}'")
                await self._record_failure()
                
                if self.fallback_function:
                    return await self._execute_fallback(*args, **kwargs)
                raise
                
            except Exception as e:
                logger.error(f"Failure in circuit breaker '{self.name}': {e}")
                await self._record_failure()
                
                if self.fallback_function:
                    return await self._execute_fallback(*args, **kwargs)
                raise
    
    async def _execute_fallback(self, *args, **kwargs) -> Any:
        """Ejecuta la función de fallback"""
        try:
            if asyncio.iscoroutinefunction(self.fallback_function):
                return await self.fallback_function(*args, **kwargs)
            else:
                return self.fallback_function(*args, **kwargs)
        except Exception as e:
            logger.error(f"Fallback function failed for '{self.name}': {e}")
            raise
    
    async def _update_state(self):
        """Actualiza el estado del circuit breaker"""
        now = time.time()
        
        if self.state == CircuitState.OPEN:
            # Verificar si es hora de intentar HALF_OPEN
            if (self.last_failure_time and 
                now - self.last_failure_time > self.config.timeout_seconds):
                logger.info(f"Circuit breaker '{self.name}' transitioning to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                
        elif self.state == CircuitState.HALF_OPEN:
            # En HALF_OPEN, esperamos éxitos para cerrar
            if self.success_count >= self.config.success_threshold:
                logger.info(f"Circuit breaker '{self.name}' transitioning to CLOSED")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
    
    async def _record_success(self):
        """Registra un éxito"""
        self.last_success_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success in CLOSED state
            self.failure_count = 0
        
        logger.debug(f"Circuit breaker '{self.name}': Success recorded, state={self.state.value}")
    
    async def _record_failure(self):
        """Registra un fallo"""
        self.last_failure_time = time.time()
        self.failure_count += 1
        self.total_failures += 1
        
        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                logger.warning(f"Circuit breaker '{self.name}' threshold reached, transitioning to OPEN")
                self.state = CircuitState.OPEN
                
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit breaker '{self.name}' failed in HALF_OPEN, back to OPEN")
            self.state = CircuitState.OPEN
            self.success_count = 0
        
        logger.debug(f"Circuit breaker '{self.name}': Failure recorded, state={self.state.value}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del circuit breaker"""
        success_rate = 0.0
        if self.total_calls > 0:
            success_rate = (self.total_calls - self.total_failures) / self.total_calls
        
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "success_rate": success_rate,
            "current_failures": self.failure_count,
            "current_successes": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "timeout_seconds": self.config.timeout_seconds,
                "success_threshold": self.config.success_threshold
            }
        }
    
    async def reset(self):
        """Reset manual del circuit breaker"""
        async with self._lock:
            logger.info(f"Manually resetting circuit breaker '{self.name}'")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.total_calls = 0
            self.total_failures = 0
            self.last_failure_time = None
            self.last_success_time = None
    
    @property
    def is_open(self) -> bool:
        """Verifica si el circuit breaker está abierto"""
        return self.state == CircuitState.OPEN
    
    @property
    def is_closed(self) -> bool:
        """Verifica si el circuit breaker está cerrado"""
        return self.state == CircuitState.CLOSED
    
    @property
    def is_half_open(self) -> bool:
        """Verifica si el circuit breaker está en half-open"""
        return self.state == CircuitState.HALF_OPEN

# Decorador para facilitar uso del circuit breaker
def circuit_breaker(name: str, 
                   config: Optional[CircuitBreakerConfig] = None,
                   fallback: Optional[Callable] = None):
    """
    Decorador para aplicar circuit breaker a una función
    
    Args:
        name: Nombre del circuit breaker
        config: Configuración del circuit breaker
        fallback: Función de fallback
    """
    def decorator(func):
        cb = CircuitBreaker(name, config, fallback)
        
        async def wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)
        
        # Agregar referencia al circuit breaker para acceso a stats
        wrapper.circuit_breaker = cb
        return wrapper
    
    return decorator
