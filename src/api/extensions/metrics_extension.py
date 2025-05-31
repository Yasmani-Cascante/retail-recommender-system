"""
Extensión para añadir funcionalidad de métricas al sistema de recomendaciones.

Esta extensión añade endpoints y lógica para recopilar y visualizar métricas
sobre la calidad y el rendimiento de las recomendaciones.
"""

import logging
import time
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from src.api.security import get_current_user
from src.api.core.metrics import recommendation_metrics, analyze_metrics_file

logger = logging.getLogger(__name__)

class MetricsExtension:
    """
    Extensión para añadir funcionalidad de métricas.
    """
    
    def __init__(self, app, settings):
        """
        Inicializa la extensión de métricas.
        
        Args:
            app: Aplicación FastAPI
            settings: Configuración del sistema
        """
        self.app = app
        self.settings = settings
        self.router = APIRouter(
            prefix="/v1",
            tags=["metrics"],
            dependencies=[Depends(get_current_user)]
        )
        
    def setup(self):
        """
        Configura la extensión de métricas.
        """
        if not self.settings.metrics_enabled:
            logger.info("Extensión de métricas desactivada")
            return
        
        logger.info("Configurando extensión de métricas")
        
        # Configurar endpoints
        self._configure_endpoints()
        
        # Registrar router
        self.app.include_router(self.router)
        logger.info("Extensión de métricas configurada correctamente")
    
    def _configure_endpoints(self):
        """
        Configura los endpoints de métricas.
        """
        @self.router.get("/metrics")
        async def get_recommendation_metrics(
            current_user: str = Depends(get_current_user)
        ):
            """
            Obtiene métricas agregadas sobre la calidad y rendimiento del sistema de recomendaciones.
            Requiere autenticación mediante API key.
            """
            try:
                # Verificar si las métricas están habilitadas (doble verificación)
                if not self.settings.metrics_enabled:
                    return {
                        "status": "disabled",
                        "message": "El sistema de métricas está desactivado. Actívalo con METRICS_ENABLED=true."
                    }
                    
                # Obtener métricas agregadas
                metrics = recommendation_metrics.get_aggregated_metrics()
                
                # Analizar archivo de métricas si existe
                file_metrics = {}
                try:
                    file_analysis = analyze_metrics_file()
                    if file_analysis.get("status") == "success":
                        file_metrics = file_analysis
                except Exception as file_error:
                    logger.warning(f"No se pudo analizar el archivo de métricas: {str(file_error)}")
                
                return {
                    "status": "success",
                    "realtime_metrics": metrics,
                    "historical_metrics": file_metrics,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
                }
            except Exception as e:
                logger.error(f"Error al obtener métricas: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error al obtener métricas: {str(e)}"
                )
