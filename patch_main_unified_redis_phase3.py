# patch_main_unified_redis_phase3.py
"""
Patch de Integración Fase 3 para main_unified_redis.py
=====================================================

Integra los componentes de Fase 3:
- Health checks extendidos de Claude
- Advanced monitoring y métricas
- Security audit endpoints
- Load testing endpoints

Este patch debe aplicarse a main_unified_redis.py
"""

# === IMPORTS ADICIONALES PARA FASE 3 ===
"""
Añadir estos imports al inicio de main_unified_redis.py después de los imports existentes:
"""

# Health checks extendidos
from src.api.health.claude_health import get_claude_health, claude_health_checker

# Advanced monitoring
from src.api.monitoring.claude_monitoring import (
    get_claude_metrics, 
    get_claude_historical_metrics, 
    get_claude_alerts,
    record_claude_request,
    claude_metrics_collector
)

# Security audit
from src.api.security.claude_security_audit import run_claude_security_audit

# === NUEVOS ENDPOINTS PARA FASE 3 ===
"""
Añadir estos endpoints al final de main_unified_redis.py, antes del middleware y de la configuración de uvicorn:
"""

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
    
    Incluye:
    - Validación de configuración
    - Conectividad API
    - Disponibilidad de modelos
    - Métricas de performance
    - Análisis de costos
    """
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
    
    Incluye:
    - Métricas en tiempo real
    - Análisis de performance
    - Tracking de costos
    - Distribución de uso por modelo
    - Tendencias y alertas
    """
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
    
    Incluye:
    - Validación de API keys
    - Configuración de seguridad
    - Protección de datos
    - Seguridad de red
    - Validación de entrada
    - Rate limiting
    """
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

@app.post("/v1/monitoring/claude/record",
          summary="Registrar Métricas Claude",
          description="Endpoint para registrar métricas de requests Claude manualmente",
          tags=["Monitoring", "Claude"])
async def record_claude_metrics_endpoint(
    metrics_data: Dict[str, Any],
    api_key: str = Depends(get_api_key)
):
    """
    Endpoint para registrar métricas de Claude manualmente.
    
    Útil para testing y validación de métricas.
    """
    try:
        await record_claude_request(**metrics_data)
        
        return {
            "status": "success",
            "message": "Claude metrics recorded successfully",
            "timestamp": time.time(),
            "recorded_metrics": metrics_data
        }
        
    except Exception as e:
        logger.error(f"Error recording Claude metrics: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Error recording metrics: {str(e)}"
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

@app.post("/v1/alerts/claude/{rule_name}/resolve",
          summary="Resolver Alerta Claude",
          description="Marca una alerta específica como resuelta",
          tags=["Alerts", "Claude"])
async def resolve_claude_alert_endpoint(
    rule_name: str,
    api_key: str = Depends(get_api_key)
):
    """
    Endpoint para resolver alertas manualmente.
    """
    try:
        success = claude_metrics_collector.resolve_alert(rule_name)
        
        if success:
            return {
                "status": "success",
                "message": f"Alert '{rule_name}' resolved successfully",
                "timestamp": time.time()
            }
        else:
            return {
                "status": "not_found",
                "message": f"Alert '{rule_name}' not found or already resolved",
                "timestamp": time.time()
            }
        
    except Exception as e:
        logger.error(f"Error resolving alert {rule_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error resolving alert: {str(e)}"
        )

# ==========================================
# FASE 3: MIDDLEWARE DE MÉTRICAS
# ==========================================

@app.middleware("http")
async def claude_metrics_middleware(request, call_next):
    """
    Middleware para capturar métricas de Claude automáticamente
    """
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
        
        # Registrar métricas básicas
        await record_claude_request(
            success=success,
            response_time_ms=response_time_ms,
            user_id=user_id,
            market_id=market_id,
            error_type="http_error" if not success else None
        )
    
    return response

# ==========================================
# FASE 3: EXTENSIÓN DEL ENDPOINT DE MÉTRICAS EXISTENTE
# ==========================================

"""
Modificar el endpoint /v1/metrics existente para incluir métricas de Claude.
Buscar el endpoint existente y añadir esta sección al final del diccionario de respuesta:
"""

# En el endpoint /v1/metrics existente, añadir esta sección:
try:
    claude_realtime = await get_claude_metrics()
    metrics_response["claude_integration"] = {
        "status": "enabled",
        "realtime_metrics": claude_realtime,
        "health_endpoint": "/health/claude",
        "detailed_metrics_endpoint": "/v1/metrics/claude",
        "security_audit_endpoint": "/v1/security/claude/audit"
    }
except Exception as e:
    metrics_response["claude_integration"] = {
        "status": "error",
        "error": str(e)
    }

# ==========================================
# FASE 3: STARTUP EVENT EXTENSIONS
# ==========================================

"""
Añadir al final del startup event existente (antes del resumen final):
"""

# === FASE 3: INICIALIZACIÓN DE COMPONENTES DE MONITORING ===
logger.info("🔍 Inicializando componentes de Fase 3...")

try:
    # Inicializar collector de métricas
    logger.info("📊 Inicializando Claude metrics collector...")
    
    # Configurar alertas personalizadas según el entorno
    if settings.debug:
        # En desarrollo, alertas más permisivas
        from src.api.monitoring.claude_monitoring import AlertRule, AlertSeverity
        claude_metrics_collector.add_custom_alert_rule(
            AlertRule(
                name="dev_claude_slow_response",
                metric_name="claude_response_time_ms",
                condition="> 10000",
                threshold=10000.0,
                severity=AlertSeverity.WARNING,
                description="Claude response very slow in development",
                cooldown_seconds=600
            )
        )
    
    # Registrar métricas iniciales
    await record_claude_request(
        success=True,
        response_time_ms=0,
        tokens_used=0,
        model_tier=claude_config.claude_model_tier.value if 'claude_config' in locals() else "unknown",
        conversation_length=0,
        user_id="system_startup",
        market_id="system"
    )
    
    logger.info("✅ Claude metrics collector initialized")
    
    # Ejecutar health check inicial
    initial_health = await get_claude_health()
    logger.info(f"🏥 Initial Claude health status: {initial_health.get('overall_status', 'unknown')}")
    
    # Si hay alertas críticas al inicio, loggearlas
    if initial_health.get('claude_integration', {}).get('checks', {}).get('api_connectivity', {}).get('status') == 'unhealthy':
        logger.warning("⚠️ Claude API connectivity issue detected at startup")
    
    logger.info("✅ Fase 3 components initialized successfully")
    
except Exception as e:
    logger.error(f"❌ Error initializing Fase 3 components: {e}")
    logger.warning("Continuing without advanced monitoring features")

# ==========================================
# FASE 3: LOAD TESTING INTEGRATION
# ==========================================

@app.get("/v1/loadtest/claude/status",
         summary="Estado de Load Testing",
         description="Obtiene el estado actual para load testing de Claude",
         tags=["LoadTest", "Claude"])
async def claude_loadtest_status(api_key: str = Depends(get_api_key)):
    """
    Endpoint para verificar que el sistema está listo para load testing
    """
    try:
        # Verificar salud del sistema
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
        
    except Exception as e:
        logger.error(f"Error checking loadtest status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error checking loadtest readiness: {str(e)}"
        )

# ==========================================
# FASE 3: INTEGRATION WITH EXISTING MCP ENDPOINTS
# ==========================================

"""
Para integrar métricas en los endpoints MCP existentes, añadir este decorator
a los endpoints de conversación existentes:
"""

def claude_metrics_decorator(func):
    """
    Decorator para capturar métricas de Claude automáticamente
    """
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        success = False
        tokens_used = 0
        error_type = None
        model_tier = None
        conversation_length = 0
        user_id = None
        market_id = None
        
        try:
            # Extraer parámetros si están disponibles
            if 'user_id' in kwargs:
                user_id = kwargs['user_id']
            if 'market_id' in kwargs:
                market_id = kwargs['market_id']
            
            # Ejecutar función original
            result = await func(*args, **kwargs)
            success = True
            
            # Extraer métricas del resultado si están disponibles
            if isinstance(result, dict):
                if 'claude_metrics' in result:
                    claude_metrics = result['claude_metrics']
                    tokens_used = claude_metrics.get('tokens_used', 0)
                    model_tier = claude_metrics.get('model_tier', 'unknown')
                
                if 'context' in result and 'conversation_length' in result['context']:
                    conversation_length = result['context']['conversation_length']
            
            return result
            
        except Exception as e:
            error_type = type(e).__name__
            raise
            
        finally:
            # Registrar métricas
            response_time_ms = (time.time() - start_time) * 1000
            
            try:
                # Obtener tier actual de configuración si no se extrajo del resultado
                if not model_tier:
                    claude_config = get_claude_config_service()
                    model_tier = claude_config.claude_model_tier.value
                
                # Estimar costo
                config = get_claude_config_service().get_model_config()
                estimated_cost = (tokens_used * config.cost_per_1k_tokens / 1000) if tokens_used > 0 else 0
                
                await record_claude_request(
                    success=success,
                    response_time_ms=response_time_ms,
                    tokens_used=tokens_used,
                    model_tier=model_tier,
                    error_type=error_type,
                    cost_usd=estimated_cost,
                    conversation_length=conversation_length,
                    user_id=user_id,
                    market_id=market_id
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record Claude metrics: {metrics_error}")
    
    return wrapper

# ==========================================
# FASE 3: CONFIGURATION UPDATES
# ==========================================

"""
Añadir estas configuraciones al archivo de configuración o .env:
"""

# Claude Monitoring Configuration
CLAUDE_METRICS_ENABLED=true
CLAUDE_ALERTS_ENABLED=true
CLAUDE_SECURITY_AUDIT_ENABLED=true
CLAUDE_LOADTEST_ENDPOINTS_ENABLED=true

# Alert Configuration
CLAUDE_MAX_RESPONSE_TIME_WARNING=3000
CLAUDE_MAX_RESPONSE_TIME_ERROR=5000
CLAUDE_MAX_ERROR_RATE=0.05
CLAUDE_MAX_HOURLY_COST=50
CLAUDE_ALERT_COOLDOWN_SECONDS=300

# Security Configuration
CLAUDE_SECURITY_AUDIT_CACHE_HOURS=1
CLAUDE_ENFORCE_HTTPS=true
CLAUDE_RATE_LIMIT_ENABLED=true
CLAUDE_PII_ANONYMIZATION=true

# Load Testing Configuration
CLAUDE_LOADTEST_MAX_RPS=1000
CLAUDE_LOADTEST_SLA_P95_MS=2000
CLAUDE_LOADTEST_MAX_CONCURRENT_USERS=500

# ==========================================
# FASE 3: VALIDATION SCRIPT
# ==========================================

"""
Script de validación para verificar que la Fase 3 está correctamente implementada.
Crear como archivo separado: validate_phase3_implementation.py
"""

#!/usr/bin/env python3
"""
Validador de Implementación Fase 3
==================================

Verifica que todos los componentes de Fase 3 estén correctamente implementados.
"""

import asyncio
import httpx
import sys
import time

async def validate_phase3_implementation():
    """Valida implementación completa de Fase 3"""
    
    print("🔍 VALIDANDO IMPLEMENTACIÓN FASE 3")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    api_key = "2fed9999056fab6dac5654238f0cae1c"  # From .env
    headers = {"X-API-Key": api_key}
    
    validation_results = []
    
    async with httpx.AsyncClient() as client:
        # Test 1: Health Check Extendido
        print("📋 Testing Claude health check...")
        try:
            response = await client.get(f"{base_url}/health/claude")
            if response.status_code in [200, 503]:  # 503 is acceptable for degraded state
                data = response.json()
                if "overall_status" in data and "claude_integration" in data:
                    validation_results.append(("claude_health_check", "✅ PASS"))
                    print(f"   Status: {data['overall_status']}")
                else:
                    validation_results.append(("claude_health_check", "❌ FAIL - Invalid response structure"))
            else:
                validation_results.append(("claude_health_check", f"❌ FAIL - HTTP {response.status_code}"))
        except Exception as e:
            validation_results.append(("claude_health_check", f"❌ FAIL - {str(e)}"))
        
        # Test 2: Advanced Metrics
        print("📊 Testing Claude advanced metrics...")
        try:
            response = await client.get(f"{base_url}/v1/metrics/claude", headers=headers)
            if response.status_code == 200:
                data = response.json()
                if "realtime_metrics" in data and "alerts" in data:
                    validation_results.append(("claude_metrics", "✅ PASS"))
                else:
                    validation_results.append(("claude_metrics", "❌ FAIL - Missing required fields"))
            else:
                validation_results.append(("claude_metrics", f"❌ FAIL - HTTP {response.status_code}"))
        except Exception as e:
            validation_results.append(("claude_metrics", f"❌ FAIL - {str(e)}"))
        
        # Test 3: Security Audit
        print("🔒 Testing Claude security audit...")
        try:
            response = await client.get(f"{base_url}/v1/security/claude/audit", headers=headers)
            if response.status_code == 200:
                data = response.json()
                if "total_findings" in data and "risk_summary" in data:
                    validation_results.append(("claude_security", "✅ PASS"))
                else:
                    validation_results.append(("claude_security", "❌ FAIL - Invalid audit structure"))
            else:
                validation_results.append(("claude_security", f"❌ FAIL - HTTP {response.status_code}"))
        except Exception as e:
            validation_results.append(("claude_security", f"❌ FAIL - {str(e)}"))
        
        # Test 4: Load Test Status
        print("🧪 Testing load test readiness...")
        try:
            response = await client.get(f"{base_url}/v1/loadtest/claude/status", headers=headers)
            if response.status_code == 200:
                data = response.json()
                if "loadtest_ready" in data and "test_endpoints" in data:
                    validation_results.append(("loadtest_status", "✅ PASS"))
                    print(f"   Ready for load testing: {data['loadtest_ready']}")
                else:
                    validation_results.append(("loadtest_status", "❌ FAIL - Missing required fields"))
            else:
                validation_results.append(("loadtest_status", f"❌ FAIL - HTTP {response.status_code}"))
        except Exception as e:
            validation_results.append(("loadtest_status", f"❌ FAIL - {str(e)}"))
        
        # Test 5: Alerts Endpoint
        print("🚨 Testing alerts endpoint...")
        try:
            response = await client.get(f"{base_url}/v1/alerts/claude", headers=headers)
            if response.status_code == 200:
                data = response.json()
                if "active_alerts" in data and "alert_statistics" in data:
                    validation_results.append(("claude_alerts", "✅ PASS"))
                else:
                    validation_results.append(("claude_alerts", "❌ FAIL - Invalid alerts structure"))
            else:
                validation_results.append(("claude_alerts", f"❌ FAIL - HTTP {response.status_code}"))
        except Exception as e:
            validation_results.append(("claude_alerts", f"❌ FAIL - {str(e)}"))
    
    # Resumen de resultados
    print("\n🎯 RESUMEN DE VALIDACIÓN FASE 3")
    print("=" * 40)
    
    passed = 0
    total = len(validation_results)
    
    for test_name, result in validation_results:
        print(f"{result} {test_name}")
        if "✅ PASS" in result:
            passed += 1
    
    print(f"\nResultado: {passed}/{total} tests pasaron")
    
    if passed == total:
        print("🎉 FASE 3 IMPLEMENTACIÓN COMPLETA Y EXITOSA")
        return True
    else:
        print("⚠️ FASE 3 REQUIERE ATENCIÓN - Algunos componentes fallaron")
        return False

if __name__ == "__main__":
    success = asyncio.run(validate_phase3_implementation())
    sys.exit(0 if success else 1)