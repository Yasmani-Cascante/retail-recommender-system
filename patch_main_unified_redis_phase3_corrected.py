# PATCH CORREGIDO PARA main_unified_redis.py - FASE 3
# ========================================================
"""
Este archivo contiene el código corregido para integrar la Fase 3
en main_unified_redis.py

APLICACIÓN MANUAL:
1. Añadir imports al inicio
2. Añadir endpoints antes del middleware
3. Modificar startup event
4. Actualizar .env
"""

# === IMPORTS A AÑADIR AL INICIO DEL ARCHIVO ===
# (Después de los imports existentes, antes de crear la app FastAPI)

import json

# === FASE 3: IMPORTS PARA COMPONENTES AVANZADOS ===
# Health checks extendidos
try:
    from src.api.health.claude_health import get_claude_health, claude_health_checker
    CLAUDE_HEALTH_AVAILABLE = True
    logger.info("✅ Claude Health module loaded")
except ImportError as e:
    CLAUDE_HEALTH_AVAILABLE = False
    logger.warning(f"⚠️ Claude Health module not available: {e}")

# Advanced monitoring
try:
    from src.api.monitoring.claude_monitoring import (
        get_claude_metrics, 
        get_claude_historical_metrics, 
        get_claude_alerts,
        record_claude_request,
        claude_metrics_collector
    )
    CLAUDE_MONITORING_AVAILABLE = True
    logger.info("✅ Claude Monitoring module loaded")
except ImportError as e:
    CLAUDE_MONITORING_AVAILABLE = False
    logger.warning(f"⚠️ Claude Monitoring module not available: {e}")

# Security audit
try:
    from src.api.security.claude_security_audit import run_claude_security_audit
    CLAUDE_SECURITY_AVAILABLE = True
    logger.info("✅ Claude Security module loaded")
except ImportError as e:
    CLAUDE_SECURITY_AVAILABLE = False
    logger.warning(f"⚠️ Claude Security module not available: {e}")

# === ENDPOINTS A AÑADIR ===
# (Añadir antes del middleware final, después de los endpoints existentes)

# ==========================================
# FASE 3: ENDPOINTS DE HEALTH, MONITORING Y SECURITY
# ==========================================

@app.get("/health/claude", 
         summary="Claude Health Check Extendido",
         description="Health check comprehensivo específico para la integración Claude",
         tags=["Health", "Claude"])
async def claude_health_endpoint():
    """
    Endpoint de health check extendido específico para Claude.
    """
    if not CLAUDE_HEALTH_AVAILABLE:
        return Response(
            content=json.dumps({
                "status": "unavailable", 
                "message": "Claude health module not available",
                "timestamp": time.time()
            }),
            status_code=503,
            media_type="application/json"
        )
    
    try:
        health_result = await get_claude_health()
        
        # Determinar status code basado en el resultado
        overall_status = health_result.get("overall_status", "unknown")
        
        if overall_status == "healthy":
            status_code = 200
        elif overall_status == "degraded":
            status_code = 200  # Still operational but with warnings
        else:
            status_code = 503  # Service unavailable
        
        return Response(
            content=json.dumps(health_result, indent=2),
            status_code=status_code,
            media_type="application/json"
        )
        
    except Exception as e:
        logger.error(f"Error in Claude health check: {e}")
        return Response(
            content=json.dumps({
                "overall_status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            }, indent=2),
            status_code=503,
            media_type="application/json"
        )

@app.get("/v1/metrics/claude",
         summary="Métricas Avanzadas de Claude",
         description="Métricas detalladas en tiempo real de la integración Claude",
         tags=["Metrics", "Claude"])
async def claude_metrics_endpoint(
    api_key: str = Depends(get_api_key),
    historical_hours: int = Query(default=1, description="Horas de datos históricos", ge=1, le=168)
):
    """
    Endpoint de métricas avanzadas específicas de Claude.
    """
    if not CLAUDE_MONITORING_AVAILABLE:
        return {
            "status": "unavailable", 
            "message": "Claude monitoring module not available",
            "timestamp": time.time()
        }
    
    try:
        # Métricas en tiempo real
        realtime_metrics = await get_claude_metrics()
        
        # Métricas históricas si se solicitan
        historical_metrics = None
        if historical_hours > 1:
            historical_metrics = await get_claude_historical_metrics(historical_hours)
        
        # Alertas activas
        alerts = await get_claude_alerts()
        
        response_data = {
            "timestamp": time.time(),
            "realtime_metrics": realtime_metrics,
            "historical_metrics": historical_metrics,
            "alerts": alerts,
            "metadata": {
                "api_version": "1.0",
                "claude_integration_version": "2.0",
                "metrics_collection_enabled": True
            }
        }
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error retrieving Claude metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving Claude metrics: {str(e)}"
        )

@app.get("/v1/security/claude/audit",
         summary="Auditoría de Seguridad Claude",
         description="Ejecuta auditoría de seguridad comprehensiva para la integración Claude",
         tags=["Security", "Claude"])
async def claude_security_audit_endpoint(
    api_key: str = Depends(get_api_key),
    force_refresh: bool = Query(default=False, description="Forzar nueva auditoría")
):
    """
    Endpoint de auditoría de seguridad para Claude.
    """
    if not CLAUDE_SECURITY_AVAILABLE:
        return {
            "status": "unavailable", 
            "message": "Claude security audit module not available",
            "timestamp": time.time()
        }
    
    try:
        # Verificar cache de auditoría (auditorías son costosas)
        cache_key = "claude_security_audit"
        cached_result = None
        
        if not force_refresh and hasattr(app.state, 'audit_cache'):
            cached_result = app.state.audit_cache.get(cache_key)
            if cached_result and time.time() - cached_result.get('timestamp', 0) < 3600:  # 1 hora cache
                cached_result['from_cache'] = True
                return cached_result
        
        # Ejecutar nueva auditoría
        logger.info("🔒 Executing Claude security audit...")
        audit_result = await run_claude_security_audit()
        
        # Guardar en cache
        if not hasattr(app.state, 'audit_cache'):
            app.state.audit_cache = {}
        app.state.audit_cache[cache_key] = audit_result
        
        audit_result['from_cache'] = False
        return audit_result
        
    except Exception as e:
        logger.error(f"Error in Claude security audit: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error executing security audit: {str(e)}"
        )

@app.get("/v1/alerts/claude",
         summary="Alertas de Claude",
         description="Obtiene alertas activas y resueltas de la integración Claude",
         tags=["Alerts", "Claude"])
async def claude_alerts_endpoint(
    api_key: str = Depends(get_api_key),
    include_resolved: bool = Query(default=False, description="Incluir alertas resueltas")
):
    """
    Endpoint de alertas específicas de Claude.
    """
    if not CLAUDE_MONITORING_AVAILABLE:
        return {
            "status": "unavailable", 
            "message": "Claude monitoring module not available",
            "timestamp": time.time()
        }
    
    try:
        alerts_data = await get_claude_alerts()
        
        if not include_resolved:
            # Filtrar solo alertas activas
            alerts_data['resolved_alerts_last_24h'] = []
        
        return alerts_data
        
    except Exception as e:
        logger.error(f"Error retrieving Claude alerts: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving alerts: {str(e)}"
        )

@app.get("/v1/loadtest/claude/status",
         summary="Estado de Load Testing",
         description="Obtiene el estado actual para load testing de Claude",
         tags=["LoadTest", "Claude"])
async def claude_loadtest_status(api_key: str = Depends(get_api_key)):
    """
    Endpoint para verificar que el sistema está listo para load testing
    """
    try:
        # Verificar salud del sistema si está disponible
        if CLAUDE_HEALTH_AVAILABLE and CLAUDE_MONITORING_AVAILABLE:
            health = await get_claude_health()
            metrics = await get_claude_metrics()
            
            # Determinar readiness para load testing
            is_ready = (
                health.get("overall_status") == "healthy" and
                metrics.get("performance_metrics", {}).get("sla_compliance", False)
            )
            
            return {
                "loadtest_ready": is_ready,
                "current_status": health.get("overall_status"),
                "sla_compliance": metrics.get("performance_metrics", {}).get("sla_compliance"),
                "current_response_time_p95": metrics.get("performance_metrics", {}).get("p95_response_time_ms"),
                "active_alerts": len(metrics.get("alerts", {}).get("recent_alerts", [])),
                "recommendations": [
                    "System ready for load testing" if is_ready else "Resolve health issues before load testing",
                    "Monitor /v1/metrics/claude during testing",
                    "Use /health/claude for real-time status"
                ],
                "test_endpoints": [
                    "/v1/mcp/conversation",
                    "/v1/recommendations/user/{user_id}",
                    "/v1/products/search/"
                ]
            }
        else:
            return {
                "loadtest_ready": False,
                "current_status": "modules_unavailable",
                "message": "Claude health and monitoring modules required for load testing status",
                "test_endpoints": [
                    "/v1/mcp/conversation",
                    "/v1/recommendations/user/{user_id}",
                    "/v1/products/search/"
                ]
            }
        
    except Exception as e:
        logger.error(f"Error checking loadtest status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error checking loadtest readiness: {str(e)}"
        )

# === MIDDLEWARE ADICIONAL ===
# (Añadir antes del middleware existente)

@app.middleware("http")
async def claude_metrics_middleware(request, call_next):
    """
    Middleware para capturar métricas de Claude automáticamente
    """
    if not CLAUDE_MONITORING_AVAILABLE:
        return await call_next(request)
    
    start_time = time.time()
    
    # Detectar si es una request relacionada con Claude
    is_claude_request = (
        "/mcp/" in str(request.url) or 
        "/conversation" in str(request.url) or
        "claude" in str(request.url).lower()
    )
    
    response = await call_next(request)
    
    # Si es una request de Claude, registrar métricas
    if is_claude_request:
        response_time_ms = (time.time() - start_time) * 1000
        success = 200 <= response.status_code < 400
        
        # Extraer información adicional si está disponible
        user_id = request.headers.get("X-User-ID")
        market_id = request.headers.get("X-Market-ID")
        
        try:
            # Registrar métricas básicas
            await record_claude_request(
                success=success,
                response_time_ms=response_time_ms,
                user_id=user_id,
                market_id=market_id,
                error_type="http_error" if not success else None
            )
        except Exception as e:
            logger.warning(f"Failed to record Claude metrics: {e}")
    
    return response

# === CONFIGURACIÓN PARA .env ===
"""
Añadir al archivo .env:

# === FASE 3 CONFIGURATION ===
CLAUDE_METRICS_ENABLED=true
CLAUDE_ALERTS_ENABLED=true
CLAUDE_SECURITY_AUDIT_ENABLED=true
CLAUDE_LOADTEST_ENDPOINTS_ENABLED=true

# Alert Configuration
CLAUDE_MAX_RESPONSE_TIME_WARNING=3000
CLAUDE_MAX_RESPONSE_TIME_ERROR=5000
CLAUDE_MAX_ERROR_RATE=0.05
CLAUDE_MAX_HOURLY_COST=50

# Security Configuration
CLAUDE_SECURITY_AUDIT_CACHE_HOURS=1
CLAUDE_ENFORCE_HTTPS=false
CLAUDE_RATE_LIMIT_ENABLED=true

# Load Testing Configuration
CLAUDE_LOADTEST_MAX_RPS=1000
CLAUDE_LOADTEST_SLA_P95_MS=2000
"""
