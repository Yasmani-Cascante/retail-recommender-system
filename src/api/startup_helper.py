"""
Helper para controlar la inicialización en segundo plano de componentes pesados.

Este módulo proporciona funciones para gestionar la carga asíncrona de componentes
que pueden requerir mucho tiempo, permitiendo que la API responda rápidamente
a health checks mientras se completa la inicialización.
"""

import time
import asyncio
import logging
from typing import Dict, Any, Optional, Callable, Awaitable, List, Tuple

logger = logging.getLogger(__name__)

class StartupManager:
    """
    Gestor de inicialización para cargar componentes en segundo plano.
    
    Permite que la aplicación responda inmediatamente a health checks mientras
    carga componentes pesados en segundo plano, solucionando problemas comunes
    en entornos serverless como Cloud Run.
    """
    
    def __init__(self, startup_timeout: float = 300.0):
        """
        Inicializa el gestor de arranque.
        
        Args:
            startup_timeout: Tiempo máximo de espera para inicialización (segundos)
        """
        self.components = {}
        self.loading_status = {}
        self.startup_time = time.time()
        self.startup_timeout = startup_timeout
        self._tasks = []
    
    def register_component(self, 
                          name: str, 
                          loader: Callable[[], Awaitable[bool]], 
                          required: bool = False,
                          dependencies: List[str] = None):
        """
        Registra un componente para carga en segundo plano.
        
        Args:
            name: Nombre único del componente
            loader: Función asíncrona que carga el componente
            required: Si es True, la aplicación se considera no saludable si falla
            dependencies: Lista de nombres de componentes que deben cargarse antes
        """
        self.components[name] = {
            "loader": loader,
            "required": required,
            "dependencies": dependencies or [],
            "task": None,
            "retry_count": 0
        }
        self.loading_status[name] = {
            "loaded": False,
            "loading": False,
            "error": None,
            "start_time": None,
            "end_time": None,
            "duration": None
        }
    
    async def _load_component(self, name: str, max_retries: int = 3) -> bool:
        """
        Carga un componente y actualiza su estado.
        
        Args:
            name: Nombre del componente
            max_retries: Número máximo de reintentos si falla
            
        Returns:
            True si la carga fue exitosa, False en caso contrario
        """
        component = self.components[name]
        status = self.loading_status[name]
        
        # Si ya está cargado o cargando, no hacer nada
        if status["loaded"] or status["loading"]:
            return status["loaded"]
        
        # Verificar dependencias
        for dep in component["dependencies"]:
            if dep not in self.loading_status:
                logger.error(f"Dependencia {dep} no registrada para componente {name}")
                return False
            
            if not self.loading_status[dep]["loaded"]:
                logger.info(f"Esperando que se cargue dependencia {dep} para componente {name}")
                return False
        
        # Marcar como cargando e inicializar tiempo
        status["loading"] = True
        status["start_time"] = time.time()
        
        try:
            logger.info(f"🔄 Iniciando carga de componente: {name}")
            success = await component["loader"]()
            
            # Actualizar estado
            status["loaded"] = success
            status["loading"] = False
            status["end_time"] = time.time()
            status["duration"] = status["end_time"] - status["start_time"]
            
            if success:
                logger.info(f"✓ Componente {name} cargado exitosamente en {status['duration']:.2f} segundos")
            else:
                logger.error(f"✗ Error cargando componente {name} ({status['duration']:.2f} segundos)")
                
                # Reintentar si es necesario
                if component["retry_count"] < max_retries:
                    component["retry_count"] += 1
                    retry_delay = 2 ** component["retry_count"]  # Backoff exponencial
                    logger.info(f"⏱️ Reintentando cargar {name} en {retry_delay} segundos (intento {component['retry_count']})")
                    
                    # Programar reintento
                    asyncio.create_task(self._delayed_retry(name, retry_delay))
            
            return success
            
        except Exception as e:
            status["error"] = str(e)
            status["loading"] = False
            status["end_time"] = time.time()
            status["duration"] = status["end_time"] - status["start_time"]
            
            logger.error(f"❌ Excepción cargando componente {name}: {e}")
            
            # Reintentar si es necesario
            if component["retry_count"] < max_retries:
                component["retry_count"] += 1
                retry_delay = 2 ** component["retry_count"]  # Backoff exponencial
                logger.info(f"⏱️ Reintentando cargar {name} en {retry_delay} segundos (intento {component['retry_count']})")
                
                # Programar reintento
                asyncio.create_task(self._delayed_retry(name, retry_delay))
            
            return False
    
    async def _delayed_retry(self, name: str, delay: float):
        """Reintenta cargar un componente después de un retraso."""
        await asyncio.sleep(delay)
        self.loading_status[name]["loading"] = False  # Resetear estado de carga
        asyncio.create_task(self._load_component(name))
    
    async def start_loading(self):
        """Inicia la carga de todos los componentes registrados en segundo plano."""
        logger.info("🚀 Iniciando carga de componentes en segundo plano")
        
        # Primero, ordenar componentes según dependencias
        components_order = self._sort_components_by_dependencies()
        
        # Iniciar carga para cada componente
        for name in components_order:
            task = asyncio.create_task(self._load_component(name))
            self.components[name]["task"] = task
            self._tasks.append(task)
    
    def _sort_components_by_dependencies(self) -> List[str]:
        """
        Ordena los componentes según sus dependencias.
        
        Returns:
            Lista de nombres de componentes ordenados para cargar
        """
        # Construir grafo de dependencias
        graph = {name: set(self.components[name]["dependencies"]) for name in self.components}
        
        # Ordenamiento topológico
        result = []
        temp_marks = set()
        perm_marks = set()
        
        def visit(node):
            if node in perm_marks:
                return
            if node in temp_marks:
                raise ValueError(f"Dependencia circular detectada con componente {node}")
            
            temp_marks.add(node)
            
            for dep in graph[node]:
                visit(dep)
            
            temp_marks.remove(node)
            perm_marks.add(node)
            result.append(node)
        
        # Visitar cada nodo
        for node in graph:
            if node not in perm_marks:
                visit(node)
        
        # Invertir para obtener el orden correcto
        return list(reversed(result))
    
    def get_status(self) -> Dict[str, Any]:
        """
        Obtiene el estado de carga de todos los componentes.
        
        Returns:
            Diccionario con estado detallado
        """
        total_components = len(self.components)
        loaded_components = sum(1 for status in self.loading_status.values() if status["loaded"])
        loading_components = sum(1 for status in self.loading_status.values() if status["loading"])
        
        # Determinar estado general
        failed_required = any(
            not status["loaded"] and self.components[name]["required"] and status["end_time"] is not None
            for name, status in self.loading_status.items()
        )
        
        if failed_required:
            overall_status = "error"
        elif loaded_components == total_components:
            overall_status = "ready"
        else:
            overall_status = "initializing"
        
        uptime = time.time() - self.startup_time
        
        return {
            "status": overall_status,
            "uptime_seconds": uptime,
            "total_components": total_components,
            "loaded_components": loaded_components,
            "loading_components": loading_components,
            "components": {
                name: {
                    "loaded": status["loaded"],
                    "loading": status["loading"],
                    "duration": status["duration"],
                    "error": status["error"],
                    "required": self.components[name]["required"]
                }
                for name, status in self.loading_status.items()
            }
        }
    
    def is_healthy(self) -> Tuple[bool, str]:
        """
        Determina si la aplicación está en un estado saludable.
        
        Returns:
            Tupla (is_healthy, reason) donde is_healthy es un booleano 
            y reason es una explicación
        """
        # Verificar componentes requeridos que han fallado
        for name, component in self.components.items():
            status = self.loading_status[name]
            
            if component["required"] and not status["loaded"] and status["end_time"] is not None:
                return False, f"Componente requerido {name} falló al cargar: {status['error']}"
        
        # La aplicación se considera saludable si:
        # 1. Todos los componentes se han cargado, o
        # 2. Algunos componentes aún se están cargando pero no ha pasado el timeout
        all_loaded = all(status["loaded"] for status in self.loading_status.values())
        
        if all_loaded:
            return True, "Todos los componentes cargados"
        
        if time.time() - self.startup_time > self.startup_timeout:
            return False, f"Timeout de inicialización ({self.startup_timeout}s) alcanzado"
        
        return True, "Inicialización en progreso"
