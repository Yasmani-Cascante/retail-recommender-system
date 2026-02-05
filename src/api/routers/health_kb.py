"""
Health Check Endpoint - Knowledge Base v2
==========================================

Endpoint para validar estado del sistema KB Multi-Language:
- Conectividad PostgreSQL
- Contenido sincronizado disponible
- Cobertura de idiomas (ES/EN)
- Cache Redis operativo
- Métricas de sincronización

Fecha: 31 Enero 2026
Objetivo: Mitigar R1 (Sync Silently Failing) con monitoring continuo
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import asyncpg
from enum import Enum

# Dependencies
from src.api.dependencies import (
    get_knowledge_base,
    get_redis_service,
    get_db_pool
)
from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
from src.api.core.redis_service import RedisService


# ============================================================================
# MODELS - Health Check Response
# ============================================================================

class HealthStatus(str, Enum):
    """Estados posibles del health check"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Estado de un componente individual"""
    status: HealthStatus
    message: str
    details: Optional[Dict] = None
    last_check: datetime = Field(default_factory=datetime.utcnow)


class LanguageCoverage(BaseModel):
    """Cobertura de idiomas en Knowledge Base"""
    language: str
    total_records: int
    sub_intents_covered: List[str]
    last_synced: Optional[datetime] = None


class SyncMetrics(BaseModel):
    """Métricas de sincronización"""
    total_records: int
    languages: List[LanguageCoverage]
    oldest_sync: Optional[datetime] = None
    newest_sync: Optional[datetime] = None
    stale_records_24h: int = 0
    stale_records_7d: int = 0


class KBHealthResponse(BaseModel):
    """Response completa del health check"""
    overall_status: HealthStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    components: Dict[str, ComponentHealth]
    sync_metrics: Optional[SyncMetrics] = None
    warnings: List[str] = []
    recommendations: List[str] = []


# ============================================================================
# ROUTER CONFIGURATION
# ============================================================================

router = APIRouter(
    prefix="/health",
    tags=["health-db"]
)


# ============================================================================
# HEALTH CHECK FUNCTIONS
# ============================================================================

async def check_postgres_connectivity(
    db_pool: asyncpg.Pool
) -> ComponentHealth:
    """
    Verifica conectividad con PostgreSQL.
    
    Checks:
    - Pool tiene conexiones disponibles
    - Query simple ejecuta correctamente
    - Tabla kb_content existe
    
    Returns:
        ComponentHealth con estado del componente
    """
    try:
        # Intentar adquirir conexión del pool
        async with db_pool.acquire() as conn:
            # Query simple para verificar conectividad
            result = await conn.fetchval("SELECT 1")
            
            if result != 1:
                return ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    message="PostgreSQL query returned unexpected result"
                )
            
            # Verificar que tabla kb_content existe
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'kb_content'
                )
            """)
            
            if not table_exists:
                return ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    message="Table kb_content does not exist",
                    details={"error": "Database schema incomplete"}
                )
            
            # Pool size info
            pool_size = db_pool.get_size()
            pool_free = db_pool.get_idle_size()
            
            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                message="PostgreSQL connectivity OK",
                details={
                    "pool_size": pool_size,
                    "pool_free": pool_free,
                    "pool_usage_pct": round((pool_size - pool_free) / pool_size * 100, 2)
                }
            )
            
    except asyncpg.PostgresError as e:
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"PostgreSQL error: {str(e)}",
            details={"error_type": type(e).__name__}
        )
    except Exception as e:
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Unexpected error checking PostgreSQL: {str(e)}",
            details={"error_type": type(e).__name__}
        )


async def check_kb_content_availability(
    db_pool: asyncpg.Pool
) -> ComponentHealth:
    """
    Verifica que hay contenido sincronizado en la base de datos.
    
    Checks:
    - Tabla kb_content tiene registros
    - Hay contenido en español (default)
    - Hay contenido en inglés (opcional pero deseable)
    
    Returns:
        ComponentHealth con estado del contenido
    """
    try:
        async with db_pool.acquire() as conn:
            # Contar total de registros
            total_records = await conn.fetchval(
                "SELECT COUNT(*) FROM kb_content"
            )
            
            if total_records == 0:
                return ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    message="Knowledge Base is EMPTY - no content synced",
                    details={
                        "total_records": 0,
                        "action_required": "Run sync_all_pages() to populate KB"
                    }
                )
            
            # Contar por idioma
            es_count = await conn.fetchval(
                "SELECT COUNT(*) FROM kb_content WHERE language = 'es'"
            )
            en_count = await conn.fetchval(
                "SELECT COUNT(*) FROM kb_content WHERE language = 'en'"
            )
            
            # Validar que hay contenido ES (requerido)
            if es_count == 0:
                return ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    message="No Spanish content available (required)",
                    details={
                        "total_records": total_records,
                        "es_records": 0,
                        "en_records": en_count
                    }
                )
            
            # Advertencia si no hay contenido EN (degradado pero funcional)
            status = HealthStatus.HEALTHY
            message = "Content available in multiple languages"
            
            if en_count == 0:
                status = HealthStatus.DEGRADED
                message = "Content available in Spanish only (EN missing)"
            
            return ComponentHealth(
                status=status,
                message=message,
                details={
                    "total_records": total_records,
                    "es_records": es_count,
                    "en_records": en_count,
                    "es_pct": round(es_count / total_records * 100, 2),
                    "en_pct": round(en_count / total_records * 100, 2)
                }
            )
            
    except Exception as e:
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Error checking KB content: {str(e)}",
            details={"error_type": type(e).__name__}
        )


async def check_redis_connectivity(redis: RedisService) -> ComponentHealth:
    """
    Verifica conectividad con Redis usando health_check() nativo.
    """
    try:
        # ✅ USAR: Método existente en lugar de ping()
        health_data = await redis.health_check(timeout=1.0)
        
        status = health_data.get("status")
        
        if status == "healthy":
            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                message="Redis connectivity OK",
                details={
                    "ping_time_ms": health_data.get("ping_time_ms"),
                    "connected": health_data.get("connected")
                }
            )
        elif status == "degraded":
            return ComponentHealth(
                status=HealthStatus.DEGRADED,
                message="Redis slow response",
                details=health_data
            )
        else:
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                message="Redis not connected",
                details=health_data
            )
        
    except Exception as e:
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Redis error: {str(e)}",
            details={"error_type": type(e).__name__}
        )


async def get_sync_metrics(
    db_pool: asyncpg.Pool
) -> SyncMetrics:
    """
    Obtiene métricas detalladas de sincronización.
    
    Metrics:
    - Total de registros por idioma
    - Sub-intents cubiertos por idioma
    - Timestamps de última sincronización
    - Registros desactualizados (>24h, >7d)
    
    Returns:
        SyncMetrics con datos de sincronización
    """
    try:
        async with db_pool.acquire() as conn:
            # Total de registros
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM kb_content"
            )
            
            # Cobertura por idioma
            lang_rows = await conn.fetch("""
                SELECT 
                    language,
                    COUNT(*) as total,
                    ARRAY_AGG(DISTINCT sub_intent) as sub_intents,
                    MAX(last_synced) as last_synced
                FROM kb_content
                GROUP BY language
                ORDER BY language
            """)
            
            languages = []
            for row in lang_rows:
                languages.append(LanguageCoverage(
                    language=row["language"],
                    total_records=row["total"],
                    sub_intents_covered=row["sub_intents"],
                    last_synced=row["last_synced"]
                ))
            
            # Timestamps de sincronización
            oldest_sync = await conn.fetchval(
                "SELECT MIN(last_synced) FROM kb_content"
            )
            newest_sync = await conn.fetchval(
                "SELECT MAX(last_synced) FROM kb_content"
            )
            
            # Registros desactualizados
            now = datetime.utcnow()
            stale_24h = await conn.fetchval("""
                SELECT COUNT(*) FROM kb_content
                WHERE last_synced < $1
            """, now - timedelta(hours=24))
            
            stale_7d = await conn.fetchval("""
                SELECT COUNT(*) FROM kb_content
                WHERE last_synced < $1
            """, now - timedelta(days=7))
            
            return SyncMetrics(
                total_records=total,
                languages=languages,
                oldest_sync=oldest_sync,
                newest_sync=newest_sync,
                stale_records_24h=stale_24h,
                stale_records_7d=stale_7d
            )
            
    except Exception as e:
        # En caso de error, retornar métricas básicas
        return SyncMetrics(
            total_records=0,
            languages=[]
        )


def generate_warnings_and_recommendations(
    components: Dict[str, ComponentHealth],
    sync_metrics: Optional[SyncMetrics]
) -> tuple[List[str], List[str]]:
    """
    Genera warnings y recomendaciones basadas en el estado del sistema.
    
    Args:
        components: Estado de cada componente
        sync_metrics: Métricas de sincronización
    
    Returns:
        Tuple de (warnings, recommendations)
    """
    warnings = []
    recommendations = []
    
    # WARNING: PostgreSQL issues
    if components["postgres"].status == HealthStatus.UNHEALTHY:
        warnings.append("PostgreSQL database is not accessible")
        recommendations.append("Check database connection settings and ensure PostgreSQL is running")
    
    # WARNING: Empty KB
    if components["kb_content"].status == HealthStatus.UNHEALTHY:
        warnings.append("Knowledge Base contains no content")
        recommendations.append("Run sync_all_pages() to populate the Knowledge Base")
    
    # WARNING: Missing EN translations
    if components["kb_content"].status == HealthStatus.DEGRADED:
        warnings.append("English translations are missing or incomplete")
        recommendations.append("Add English translations to Shopify pages and re-sync")
    
    # WARNING: Redis issues
    if components["redis"].status != HealthStatus.HEALTHY:
        warnings.append("Redis cache is not fully operational")
        recommendations.append("Check Redis connection and ensure service is running")
    
    # WARNING: Stale content
    if sync_metrics and sync_metrics.stale_records_24h > 0:
        warnings.append(f"{sync_metrics.stale_records_24h} records not synced in last 24 hours")
        recommendations.append("Run sync_all_pages() to update content")
    
    # WARNING: Very old sync
    if sync_metrics and sync_metrics.oldest_sync:
        age_days = (datetime.utcnow() - sync_metrics.oldest_sync).days
        if age_days > 30:
            warnings.append(f"Oldest content is {age_days} days old")
            recommendations.append("Consider implementing automated daily sync")
    
    # WARNING: Low language coverage
    if sync_metrics:
        en_coverage = next((l for l in sync_metrics.languages if l.language == "en"), None)
        es_coverage = next((l for l in sync_metrics.languages if l.language == "es"), None)
        
        if es_coverage and en_coverage:
            coverage_ratio = en_coverage.total_records / es_coverage.total_records
            if coverage_ratio < 0.5:  # Menos del 50% de ES tiene EN
                warnings.append(f"English coverage is only {coverage_ratio*100:.1f}% of Spanish")
                recommendations.append("Prioritize translating high-traffic pages to English")
    
    return warnings, recommendations


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get(
    "/kb",
    response_model=KBHealthResponse,
    summary="Knowledge Base Health Check",
    description="""
    Comprehensive health check for KB v2 Multi-Language system.
    
    Validates:
    - PostgreSQL connectivity and content availability
    - Redis cache connectivity
    - Language coverage (ES/EN)
    - Sync freshness and metrics
    
    Returns detailed status with warnings and recommendations.
    
    Status Levels:
    - HEALTHY: All systems operational, content fresh
    - DEGRADED: Minor issues (e.g., missing EN translations)
    - UNHEALTHY: Critical issues (e.g., empty DB, no connectivity)
    """
)
async def health_check_kb(
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis: RedisService = Depends(get_redis_service)
) -> KBHealthResponse:
    """
    Ejecuta health check completo del Knowledge Base.
    
    Este endpoint valida que:
    1. ✅ PostgreSQL está accesible y tiene contenido
    2. ✅ Redis está operativo
    3. ✅ Contenido está sincronizado recientemente
    4. ✅ Cobertura de idiomas es adecuada
    
    Uso en monitoring:
    - Kubernetes liveness probe: /health/kb
    - Alerting: status != "healthy"
    - Metrics: sync_metrics para dashboards
    
    Returns:
        KBHealthResponse con estado completo del sistema
    """
    # Ejecutar checks en paralelo (más rápido)
    import asyncio
    
    postgres_check, content_check, redis_check = await asyncio.gather(
        check_postgres_connectivity(db_pool),
        check_kb_content_availability(db_pool),
        check_redis_connectivity(redis),
        return_exceptions=True
    )
    
    # Manejar exceptions en checks
    components = {}
    
    if isinstance(postgres_check, Exception):
        components["postgres"] = ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Exception during PostgreSQL check: {str(postgres_check)}"
        )
    else:
        components["postgres"] = postgres_check
    
    if isinstance(content_check, Exception):
        components["kb_content"] = ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Exception during content check: {str(content_check)}"
        )
    else:
        components["kb_content"] = content_check
    
    if isinstance(redis_check, Exception):
        components["redis"] = ComponentHealth(
            status=HealthStatus.DEGRADED,  # Redis no es crítico
            message=f"Exception during Redis check: {str(redis_check)}"
        )
    else:
        components["redis"] = redis_check
    
    # Obtener métricas de sincronización
    sync_metrics = await get_sync_metrics(db_pool)
    
    # Generar warnings y recommendations
    warnings, recommendations = generate_warnings_and_recommendations(
        components,
        sync_metrics
    )
    
    # Determinar overall status
    statuses = [c.status for c in components.values()]
    
    if HealthStatus.UNHEALTHY in statuses:
        overall_status = HealthStatus.UNHEALTHY
    elif HealthStatus.DEGRADED in statuses:
        overall_status = HealthStatus.DEGRADED
    else:
        overall_status = HealthStatus.HEALTHY
    
    return KBHealthResponse(
        overall_status=overall_status,
        components=components,
        sync_metrics=sync_metrics,
        warnings=warnings,
        recommendations=recommendations
    )


@router.get(
    "/kb/simple",
    summary="Simple KB Health Check",
    description="Quick health check returning only HTTP status code (for load balancers)"
)
async def simple_health_check(
    db_pool: asyncpg.Pool = Depends(get_db_pool)
) -> Dict[str, Any]:
    """
    Health check simplificado para load balancers.
    
    Verifica solo:
    - PostgreSQL accesible
    - KB tiene contenido (>0 records)
    
    Returns:
        200 OK si healthy
        503 Service Unavailable si unhealthy
    
    Uso:
    - Kubernetes readiness probe
    - Load balancer health checks
    - Uptime monitoring (Pingdom, etc.)
    """
    try:
        async with db_pool.acquire() as conn:
            # Check 1: DB accesible
            await conn.fetchval("SELECT 1")
            
            # Check 2: KB tiene contenido
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM kb_content"
            )
            
            if count == 0:
                raise HTTPException(
                    status_code=503,
                    detail="Knowledge Base is empty"
                )
            
            return {
                "status": "healthy",
                "records": count
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Health check failed: {str(e)}"
        )


# ============================================================================
# EXPORT ROUTER
# ============================================================================

__all__ = ["router"]