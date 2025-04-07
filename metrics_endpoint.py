"""
Endpoint para métricas del sistema de recomendaciones.
Este archivo contiene solo la definición del endpoint /v1/metrics.
Se debe incluir en el archivo principal de la aplicación.
"""

@app.get("/v1/metrics")
async def get_recommendation_metrics(
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene métricas agregadas sobre la calidad y rendimiento del sistema de recomendaciones.
    Requiere autenticación mediante API key.
    """
    try:
        # Obtener métricas agregadas
        metrics = recommendation_metrics.get_aggregated_metrics()
        
        # Analizar archivo de métricas si existe
        file_metrics = {}
        try:
            from src.api.core.metrics import analyze_metrics_file
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
