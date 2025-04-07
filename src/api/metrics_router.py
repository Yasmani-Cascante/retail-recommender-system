"""
Endpoints para métricas del sistema de recomendaciones.
Este módulo se importa en el archivo principal de la API.
"""

import os
import time
import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from src.api.security import get_current_user
from src.api.core.metrics import recommendation_metrics, analyze_metrics_file

# Configurar logging
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(
    prefix="/v1",
    tags=["metrics"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/metrics")
async def get_recommendation_metrics(
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene métricas agregadas sobre la calidad y rendimiento del sistema de recomendaciones.
    Requiere autenticación mediante API key.
    """
    try:
        # Verificar si las métricas están habilitadas
        if os.getenv("METRICS_ENABLED", "true").lower() != "true":
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
