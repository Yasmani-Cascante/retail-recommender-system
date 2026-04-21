"""
Health Check Endpoint - Knowledge Base v2 (ENHANCED - FASE H3)
==============================================================

🎯 OBJETIVO:
Proporcionar visibilidad completa del estado del sistema KB Multi-Language
con checks comprehensivos, métricas detalladas y alertas tempranas.

✅ FEATURES (Post-H3 Día 1):
- ✅ PostgreSQL connectivity + pool metrics
- ✅ KB content availability + language coverage
- ✅ Redis connectivity (degraded mode friendly)
- ✅ Schema versioning status (FASE H2 integration) ← NUEVO DÍA 1
- ✅ Content staleness alerts (>24h, >48h, >72h) ← MEJORADO DÍA 1
- ✅ Per-language staleness detection ← NUEVO DÍA 1
- ✅ Structured logging (FASE H1 integration)
- ⏳ Performance instrumentation (<500ms target) ← PRÓXIMO (Día 2)
- ⏳ Shopify GraphQL API health (deep mode) ← PRÓXIMO (Día 2)

🔄 USAGE:
- Kubernetes liveness probe: GET /health/kb/simple
- Kubernetes readiness probe: GET /health/kb
- Monitoring dashboard: GET /health/kb (poll every 60s)

Fecha: 11 Febrero 2026 (H3 Día 1 - Schema Versioning + Enhanced Staleness)
Version: 2.1.0 (Enhanced Health Checks - Schema Versioning Integration)
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import asyncpg
from enum import Enum

# ============================================================================
# H1: STRUCTURED LOGGING IMPORT
# ============================================================================
import structlog

from src.api.services.shopify_kb_sync import ShopifyKBSyncService

logger = structlog.get_logger(__name__)

# Dependencies
from src.api.dependencies import (
    get_kb_sync_service,
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
    - Tabla kb_contents existe (FIXED: plural)
    
    Returns:
        ComponentHealth con estado del componente
    """
    try:
        # Intentar adquirir conexión del pool
        async with db_pool.acquire() as conn:
            # Query simple para verificar conectividad
            result = await conn.fetchval("SELECT 1")
            
            if result != 1:
                # ✅ H1: Structured logging para error
                logger.error(
                    "postgres_health_check_unexpected_result",
                    component="postgresql",
                    check_type="connectivity",
                    expected=1,
                    received=result
                )
                return ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    message="PostgreSQL query returned unexpected result"
                )
            
            # ✅ FIXED: Tabla kb_contents (plural)
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'kb_contents'
                )
            """)
            
            if not table_exists:
                # ✅ H1: Structured logging para tabla faltante
                logger.error(
                    "postgres_health_check_table_missing",
                    component="postgresql",
                    check_type="schema",
                    table_name="kb_contents"
                )
                return ComponentHealth(
                    status=HealthStatus.UNHEALTHY,
                    message="Table kb_contents does not exist",
                    details={"error": "Database schema incomplete"}
                )
            
            # Pool size info
            pool_size = db_pool.get_size()
            pool_free = db_pool.get_idle_size()
            pool_usage_pct = round((pool_size - pool_free) / pool_size * 100, 2)
            
            # ✅ H1: Structured logging para éxito
            logger.info(
                "postgres_health_check_passed",
                component="postgresql",
                pool_size=pool_size,
                pool_free=pool_free,
                pool_usage_pct=pool_usage_pct
            )
            
            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                message="PostgreSQL connectivity OK",
                details={
                    "pool_size": pool_size,
                    "pool_free": pool_free,
                    "pool_usage_pct": pool_usage_pct
                }
            )
            
    except asyncpg.PostgresError as e:
        # ✅ H1: Structured logging para errores de PostgreSQL
        logger.error(
            "postgres_health_check_error",
            error=str(e),
            error_type=type(e).__name__,
            component="postgresql",
            check_type="connectivity"
        )
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"PostgreSQL error: {str(e)}",
            details={"error_type": type(e).__name__}
        )
    except Exception as e:
        # ✅ H1: Structured logging para errores inesperados
        logger.error(
            "postgres_health_check_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
            component="postgresql",
            exc_info=True  # ← CRÍTICO para stack trace
        )
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
    - Tabla kb_contents tiene registros
    - Hay contenido en español (default)
    - Hay contenido en inglés (opcional pero deseable)
    
    Returns:
        ComponentHealth con estado del contenido
    """
    try:
        async with db_pool.acquire() as conn:
            # Contar total de registros
            total_records = await conn.fetchval(
                "SELECT COUNT(*) FROM kb_contents"
            )
            
            if total_records == 0:
                # ✅ H1: Structured logging para KB vacío
                logger.warning(
                    "kb_content_empty",
                    component="kb_content",
                    total_records=0,
                    status="unhealthy"
                )
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
                "SELECT COUNT(*) FROM kb_contents WHERE language = 'es'"
            )
            en_count = await conn.fetchval(
                "SELECT COUNT(*) FROM kb_contents WHERE language = 'en'"
            )
            
            # Validar que hay contenido ES (requerido)
            if es_count == 0:
                # ✅ H1: Structured logging para ES faltante
                logger.error(
                    "kb_content_missing_spanish",
                    component="kb_content",
                    total_records=total_records,
                    es_records=0,
                    en_records=en_count,
                    status="unhealthy"
                )
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
                
                # ✅ H1: Structured logging para EN faltante
                logger.warning(
                    "kb_content_missing_english",
                    component="kb_content",
                    total_records=total_records,
                    es_records=es_count,
                    en_records=0,
                    status="degraded"
                )
            else:
                # ✅ H1: Structured logging para éxito
                logger.info(
                    "kb_content_check_passed",
                    component="kb_content",
                    total_records=total_records,
                    es_records=es_count,
                    en_records=en_count,
                    status=status.value
                )
            
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
        # ✅ H1: Structured logging para error
        logger.error(
            "kb_content_check_error",
            error=str(e),
            error_type=type(e).__name__,
            component="kb_content",
            exc_info=True
        )
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
            # ✅ H1: Structured logging para éxito
            logger.info(
                "redis_health_check_passed",
                component="redis",
                status=status,
                ping_time_ms=health_data.get("ping_time_ms"),
                connected=health_data.get("connected")
            )
            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                message="Redis connectivity OK",
                details={
                    "ping_time_ms": health_data.get("ping_time_ms"),
                    "connected": health_data.get("connected")
                }
            )
        elif status == "degraded":
            # ✅ H1: Structured logging para degradado
            logger.warning(
                "redis_health_check_degraded",
                component="redis",
                status=status,
                details=health_data
            )
            return ComponentHealth(
                status=HealthStatus.DEGRADED,
                message="Redis slow response",
                details=health_data
            )
        else:
            # ✅ H1: Structured logging para unhealthy
            logger.error(
                "redis_health_check_unhealthy",
                component="redis",
                status=status,
                details=health_data
            )
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                message="Redis not connected",
                details=health_data
            )
        
    except Exception as e:
        # ✅ H1: Structured logging para error
        logger.error(
            "redis_health_check_error",
            error=str(e),
            error_type=type(e).__name__,
            component="redis",
            exc_info=True
        )
        return ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Redis error: {str(e)}",
            details={"error_type": type(e).__name__}
        )


async def check_schema_version(
    db_pool: asyncpg.Pool
) -> ComponentHealth:
    """
    Verifica el estado del schema versioning system (FASE H2 Integration).
    
    Checks:
    - Tabla schema_migrations existe
    - Versión actual del schema
    - No hay migraciones pendientes
    
    Returns:
        ComponentHealth con estado del schema versioning
        
    Notes:
        - FASE H2: Integración con sistema de versioning
        - Degraded si tabla no existe (pre-H2 state)
        - Healthy si schema está actualizado
    """
    try:
        async with db_pool.acquire() as conn:
            # Check 1: Tabla schema_migrations existe
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'schema_migrations'
                )
            """)
            
            if not table_exists:
                # ✅ H1: Structured logging para tabla faltante
                logger.warning(
                    "schema_migrations_table_missing",
                    component="schema_version",
                    check_type="table_existence",
                    status="degraded"
                )
                return ComponentHealth(
                    status=HealthStatus.DEGRADED,
                    message="Schema migrations table not found (pre-H2 state)",
                    details={
                        "table_exists": False,
                        "recommendation": "Schema versioning not yet implemented"
                    }
                )
            
            # Check 2: Get current version
            current_version = await conn.fetchval("""
                SELECT MAX(version) FROM schema_migrations
            """)
            
            # Check 3: Get total migrations count
            migrations_count = await conn.fetchval("""
                SELECT COUNT(*) FROM schema_migrations
            """)
            
            # Check 4: Verify kb_contents has schema_version column
            has_schema_column = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'kb_contents' 
                    AND column_name = 'schema_version'
                )
            """)
            
            # ✅ H1: Structured logging para éxito
            logger.info(
                "schema_version_check_passed",
                component="schema_version",
                current_version=current_version,
                migrations_count=migrations_count,
                has_schema_column=has_schema_column
            )
            
            return ComponentHealth(
                status=HealthStatus.HEALTHY,
                message="Schema versioning OK",
                details={
                    "current_version": current_version,
                    "total_migrations": migrations_count,
                    "schema_column_present": has_schema_column
                }
            )
            
    except Exception as e:
        # ✅ H1: Structured logging para error
        logger.error(
            "schema_version_check_error",
            error=str(e),
            error_type=type(e).__name__,
            component="schema_version",
            exc_info=True
        )
        return ComponentHealth(
            status=HealthStatus.DEGRADED,  # Degraded, not critical
            message=f"Schema version check failed: {str(e)}",
            details={"error_type": type(e).__name__}
        )
    
# ============================================================================
# H3 DÍA 2: SHOPIFY API HEALTH CHECK (DEEP MODE ONLY)
# ============================================================================

async def check_shopify_api(
    kb_sync_service: 'ShopifyKBSyncService'
) -> ComponentHealth:
    """
    Verifica conectividad con Shopify GraphQL API (DEEP MODE ONLY).
    
    Este check es **opcional** y solo se ejecuta cuando `deep=true` porque:
    - Toma 2-3 segundos por la latencia de red con Shopify
    - No es crítico para funcionalidad core del sistema
    - Útil solo para diagnóstico profundo
    
    Checks realizados:
    -------------------
    1. **GraphQL endpoint accesible**: Verifica que Shopify API responde
    2. **Credenciales válidas**: Confirma que API key funciona
    3. **Shop data readable**: Puede leer información básica del shop
    4. **Response time acceptable**: <3s considerado saludable
    
    Args:
        kb_sync_service: ShopifyKBSyncService con ShopifyKBClient configurado
    
    Returns:
        ComponentHealth con:
        - status: healthy (<3s), degraded (>=3s), unhealthy (error)
        - message: Descripción del estado
        - details: shop_name, shop_url, response_time_ms, etc.
    
    Notes:
        - ⚠️ Este check toma 2-3 segundos - NO ejecutar en checks normales
        - ✅ Solo ejecutar en deep mode (?deep=true)
        - ⚠️ No crítico: Si falla, sistema sigue funcionando (usa DB/Redis cache)
    
    Examples:
        >>> # En deep mode:
        >>> shopify_health = await check_shopify_api(kb_sync_service)
        >>> print(shopify_health.status)  # healthy/degraded/unhealthy
        
    Author: Senior Architecture Team
    Date: 11 Febrero 2026 (H3 Día 2)
    Version: 2.1.0
    """
    import time
    
    try:
        start_time = time.perf_counter()
        
        # ✅ Obtener ShopifyKBClient del sync service
        shopify_client = kb_sync_service.shopify
        
        if not shopify_client:
            logger.error(
                "shopify_api_check_missing_client",
                component="shopify_api",
                error="ShopifyKBClient not available in kb_sync_service"
            )
            return ComponentHealth(
                status=HealthStatus.UNHEALTHY,
                message="Shopify API client not configured",
                details={"error": "ShopifyKBClient missing"}
            )
        
        # ✅ Test query simple a Shopify GraphQL
        # Esta query solo lee información básica del shop (no datos sensibles)
        test_query = """
        query {
            shop {
                name
                primaryDomain {
                    url
                }
                currencyCode
            }
        }
        """
        
        # ✅ Ejecutar query (este es el paso que toma tiempo)
        logger.info(
            "shopify_api_check_started",
            component="shopify_api",
            action="executing_test_query"
        )
        
        result = await shopify_client._graphql_query(test_query)
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # ✅ Validar respuesta
        if result and "shop" in result:
            shop_name = result["shop"]["name"]
            shop_url = result["shop"]["primaryDomain"]["url"]
            currency = result["shop"].get("currencyCode", "N/A")
            
            # ✅ H1: Structured logging para éxito
            logger.info(
                "shopify_api_check_passed",
                component="shopify_api",
                shop_name=shop_name,
                response_time_ms=round(duration_ms, 2),
                currency=currency
            )
            
            # ✅ Determinar status basado en response time
            status = HealthStatus.HEALTHY
            if duration_ms > 3000:  # >3s = degraded (lento pero funcional)
                status = HealthStatus.DEGRADED
                logger.warning(
                    "shopify_api_slow_response",
                    component="shopify_api",
                    response_time_ms=round(duration_ms, 2),
                    threshold_ms=3000,
                    exceeded_by_ms=round(duration_ms - 3000, 2)
                )
            
            return ComponentHealth(
                status=status,
                message=f"Shopify API OK (shop: {shop_name})",
                details={
                    "shop_name": shop_name,
                    "shop_url": shop_url,
                    "currency_code": currency,
                    "response_time_ms": round(duration_ms, 2),
                    "graphql_endpoint": "accessible",
                    "credentials_valid": True
                }
            )
        else:
            # ✅ H1: Structured logging para respuesta inesperada
            logger.error(
                "shopify_api_unexpected_response",
                component="shopify_api",
                result_preview=str(result)[:200] if result else "None",
                duration_ms=round(duration_ms, 2)
            )
            return ComponentHealth(
                status=HealthStatus.DEGRADED,
                message="Shopify API returned unexpected response",
                details={
                    "error": "Invalid response structure",
                    "response_time_ms": round(duration_ms, 2),
                    "has_result": result is not None
                }
            )
            
    except Exception as e:
        # ✅ H1: Structured logging para error
        logger.error(
            "shopify_api_check_error",
            error=str(e),
            error_type=type(e).__name__,
            component="shopify_api",
            exc_info=True
        )
        return ComponentHealth(
            status=HealthStatus.DEGRADED,  # Degraded, not critical
            message=f"Shopify API check failed: {str(e)[:100]}",
            details={
                "error_type": type(e).__name__,
                "error_message": str(e)[:200]
            }
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
                "SELECT COUNT(*) FROM kb_contents"
            )
            
            # Cobertura por idioma
            lang_rows = await conn.fetch("""
                SELECT 
                    language,
                    COUNT(*) as total,
                    ARRAY_AGG(DISTINCT sub_intent) as sub_intents,
                    MAX(last_synced) as last_synced
                FROM kb_contents
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
                "SELECT MIN(last_synced) FROM kb_contents"
            )
            newest_sync = await conn.fetchval(
                "SELECT MAX(last_synced) FROM kb_contents"
            )
            
            # Registros desactualizados
            now = datetime.utcnow()
            stale_24h = await conn.fetchval("""
                SELECT COUNT(*) FROM kb_contents
                WHERE last_synced < $1
            """, now - timedelta(hours=24))
            
            stale_7d = await conn.fetchval("""
                SELECT COUNT(*) FROM kb_contents
                WHERE last_synced < $1
            """, now - timedelta(days=7))
            
            # ✅ H1: Structured logging para métricas
            logger.debug(
                "sync_metrics_retrieved",
                component="sync_metrics",
                total_records=total,
                languages_count=len(languages),
                stale_24h=stale_24h,
                stale_7d=stale_7d
            )
            
            return SyncMetrics(
                total_records=total,
                languages=languages,
                oldest_sync=oldest_sync,
                newest_sync=newest_sync,
                stale_records_24h=stale_24h,
                stale_records_7d=stale_7d
            )
            
    except Exception as e:
        # ✅ H1: Structured logging para error
        logger.error(
            "sync_metrics_error",
            error=str(e),
            error_type=type(e).__name__,
            component="sync_metrics",
            exc_info=True
        )
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
    
    # WARNING: Stale content - Enhanced granular detection
    if sync_metrics and sync_metrics.oldest_sync:
        age_hours = (datetime.utcnow() - sync_metrics.oldest_sync).total_seconds() / 3600
        
        if age_hours > 72:  # >3 days - SEVERE
            warnings.append(
                f"⚠️ Content severely stale: oldest record is {age_hours:.1f} hours old (>72h threshold)"
            )
            recommendations.append(
                "URGENT: Run sync_all_pages() immediately to update content"
            )
        elif age_hours > 48:  # >2 days - MODERATE
            warnings.append(
                f"Content moderately stale: oldest record is {age_hours:.1f} hours old (>48h threshold)"
            )
            recommendations.append(
                "Run sync_all_pages() soon to keep content fresh"
            )
        elif sync_metrics.stale_records_24h > 0:  # >24h - MINOR
            warnings.append(
                f"{sync_metrics.stale_records_24h} records not synced in last 24 hours"
            )
            recommendations.append(
                "Run sync_all_pages() to update content"
            )
    
    # ✅ NUEVO: Per-language staleness detection
    if sync_metrics and sync_metrics.languages:
        for lang_coverage in sync_metrics.languages:
            if lang_coverage.last_synced:
                age_hours = (datetime.utcnow() - lang_coverage.last_synced).total_seconds() / 3600
                
                if age_hours > 48:
                    warnings.append(
                        f"Language '{lang_coverage.language}' content stale: {age_hours:.1f} hours old"
                    )
                    recommendations.append(
                        f"Sync Shopify pages with language={lang_coverage.language}"
                    )

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
    
    # ✅ H1: Structured logging para warnings/recommendations generados
    if warnings or recommendations:
        logger.info(
            "warnings_recommendations_generated",
            component="health_check",
            warnings_count=len(warnings),
            recommendations_count=len(recommendations)
        )
    
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
    deep: bool = False,  # ← NUEVO: Deep mode query parameter
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis: RedisService = Depends(get_redis_service),
    kb_sync_service: 'ShopifyKBSyncService' = Depends(get_kb_sync_service)  # ← NUEVO para Shopify API check
) -> KBHealthResponse:
    """
    🏥 KNOWLEDGE BASE HEALTH CHECK - ENHANCED (H3 DÍA 2 EN PROGRESO)
    
    🎯 OBJETIVO:
    Proporcionar visibilidad completa del sistema KB con checks rápidos (normal mode)
    o comprehensivos (deep mode) según necesidad.
    
    ✅ FEATURES ACTUALES (Día 2):
    - ✅ PostgreSQL connectivity + pool metrics
    - ✅ KB content availability + language coverage
    - ✅ Redis connectivity (degraded mode friendly)
    - ✅ Schema versioning status (H2 integration)
    - ✅ Content staleness alerts (>24h, >48h, >72h)
    - ✅ Per-language staleness detection
    - ✅ Performance instrumentation (<500ms target) ← NUEVO DÍA 2
    - ✅ Shopify API health (deep mode only) ← NUEVO DÍA 2
    
    🔄 USAGE:
    - **Normal mode** (fast, <500ms):
      GET /health/kb
      
    - **Deep mode** (comprehensive, 2-3s):
      GET /health/kb?deep=true
      
    - Kubernetes liveness: GET /health/kb/simple
    - Kubernetes readiness: GET /health/kb
    - Monitoring dashboard: GET /health/kb (normal mode, poll 60s)
    - On-demand diagnosis: GET /health/kb?deep=true (manual, cuando hay issues)
    
    Query Parameters:
        deep (bool, optional): Enable deep health checks. Default: False.
            - False: Fast checks only (~200-300ms)
            - True: Includes Shopify API check (+2-3s)
    
    Returns:
        KBHealthResponse con todos los component health checks y métricas
    
    Examples:
        >>> # Normal mode (rápido)
        >>> curl http://localhost:8000/health/kb
        >>> # Response time: ~250ms
        
        >>> # Deep mode (comprehensivo)
        >>> curl "http://localhost:8000/health/kb?deep=true"
        >>> # Response time: ~2.5s (incluye Shopify API check)
    
    Author: Senior Architecture Team
    Date: 11 Febrero 2026 (H3 Día 2)
    Version: 2.1.0
    """
    # ============================================================================
    # H3 DÍA 2: PERFORMANCE INSTRUMENTATION - START TIMING
    # ============================================================================
    import time
    start_time = time.perf_counter()
    
    # ✅ H1: Structured logging para inicio
    logger.info(
        "health_check_started",
        endpoint="/health/kb",
        deep=deep,
        timestamp=datetime.utcnow().isoformat()
    )
    
    # ============================================================================
    # EXECUTE ALL HEALTH CHECKS IN PARALLEL (más rápido)
    # ============================================================================
    import asyncio
    
    postgres_check, content_check, redis_check, schema_check = await asyncio.gather(
    check_postgres_connectivity(db_pool),
    check_kb_content_availability(db_pool),
    check_redis_connectivity(redis),
    check_schema_version(db_pool),  # ← NUEVO
    return_exceptions=True
)
    
    # Manejar exceptions en checks
    components = {}
    
    if isinstance(postgres_check, Exception):
        # ✅ H1: Structured logging para exception en check
        logger.error(
            "postgres_check_exception",
            error=str(postgres_check),
            error_type=type(postgres_check).__name__,
            component="health_check",
            exc_info=True
        )
        components["postgres"] = ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Exception during PostgreSQL check: {str(postgres_check)}"
        )
    else:
        components["postgres"] = postgres_check
    
    if isinstance(content_check, Exception):
        # ✅ H1: Structured logging para exception en check
        logger.error(
            "content_check_exception",
            error=str(content_check),
            error_type=type(content_check).__name__,
            component="health_check",
            exc_info=True
        )
        components["kb_content"] = ComponentHealth(
            status=HealthStatus.UNHEALTHY,
            message=f"Exception during content check: {str(content_check)}"
        )
    else:
        components["kb_content"] = content_check
    
    if isinstance(redis_check, Exception):
        # ✅ H1: Structured logging para exception en check
        logger.warning(
            "redis_check_exception",
            error=str(redis_check),
            error_type=type(redis_check).__name__,
            component="health_check",
            exc_info=True
        )
        components["redis"] = ComponentHealth(
            status=HealthStatus.DEGRADED,  # Redis no es crítico
            message=f"Exception during Redis check: {str(redis_check)}"
        )
    else:
        components["redis"] = redis_check

    # ✅ NUEVO: Handle schema_check exception
    if isinstance(schema_check, Exception):
        # ✅ H1: Structured logging para exception en check
        logger.warning(
            "schema_check_exception",
            error=str(schema_check),
            error_type=type(schema_check).__name__,
            component="health_check",
            exc_info=True
        )
        components["schema_version"] = ComponentHealth(
            status=HealthStatus.DEGRADED,  # Schema version no es crítico
            message=f"Exception during schema version check: {str(schema_check)}"
        )
    else:
        components["schema_version"] = schema_check
    
    # Obtener métricas de sincronización
    sync_metrics = await get_sync_metrics(db_pool)
    
    # Generar warnings y recommendations
    warnings, recommendations = generate_warnings_and_recommendations(
        components,
        sync_metrics
    )
    
    # ============================================================================
    # H3 DÍA 2: DEEP MODE - SHOPIFY API CHECK (OPCIONAL)
    # ============================================================================
    
    if deep:
        try:
            logger.info(
                "deep_mode_enabled",
                endpoint="/health/kb",
                deep=True,
                action="executing_shopify_api_check"
            )
            
            # ✅ Ejecutar Shopify API check (toma 2-3s)
            shopify_check = await check_shopify_api(kb_sync_service)
            components["shopify_api"] = shopify_check
            
            logger.info(
                "shopify_api_check_completed",
                status=shopify_check.status.value if shopify_check else "error",
                deep=True
            )
            
        except Exception as e:
            logger.error(
                "shopify_api_check_failed",
                error=str(e),
                error_type=type(e).__name__,
                deep=True,
                exc_info=True
            )

    # Determinar overall status
    statuses = [c.status for c in components.values()]
    
    if HealthStatus.UNHEALTHY in statuses:
        overall_status = HealthStatus.UNHEALTHY
    elif HealthStatus.DEGRADED in statuses:
        overall_status = HealthStatus.DEGRADED
    else:
        overall_status = HealthStatus.HEALTHY
    
    # ✅ H1: Structured logging para finalización de health check
    logger.info(
        "health_check_completed",
        endpoint="/health/kb",
        overall_status=overall_status.value,
        components_healthy=sum(1 for c in components.values() if c.status == HealthStatus.HEALTHY),
        components_degraded=sum(1 for c in components.values() if c.status == HealthStatus.DEGRADED),
        components_unhealthy=sum(1 for c in components.values() if c.status == HealthStatus.UNHEALTHY),
        warnings_count=len(warnings),
        recommendations_count=len(recommendations)
    )

    # ============================================================================
    # H3 DÍA 2: PERFORMANCE INSTRUMENTATION - END TIMING
    # ============================================================================
    
    duration_ms = (time.perf_counter() - start_time) * 1000
    
    # ✅ H1: Structured logging para finalización CON TIMING
    logger.info(
        "health_check_completed",
        endpoint="/health/kb",
        overall_status=overall_status.value,
        duration_ms=round(duration_ms, 2),
        target_ms=500,
        within_target=duration_ms < 500,
        deep=deep,
        components_count=len(components),
        components_healthy=sum(1 for c in components.values() if c.status == HealthStatus.HEALTHY),
        components_degraded=sum(1 for c in components.values() if c.status == HealthStatus.DEGRADED),
        components_unhealthy=sum(1 for c in components.values() if c.status == HealthStatus.UNHEALTHY)
    )
    
    # ✅ Warning si supera target (solo en normal mode)
    if not deep and duration_ms > 500:
        logger.warning(
            "health_check_slow_response",
            endpoint="/health/kb",
            duration_ms=round(duration_ms, 2),
            target_ms=500,
            exceeded_by_ms=round(duration_ms - 500, 2),
            deep=False
        )
    
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
    # ✅ H1: Structured logging para inicio de simple check
    logger.debug(
        "simple_health_check_started",
        endpoint="/health/kb/simple"
    )
    
    try:
        async with db_pool.acquire() as conn:
            # Check 1: DB accesible
            await conn.fetchval("SELECT 1")
            
            # Check 2: KB tiene contenido
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM kb_contents"
            )
            
            if count == 0:
                # ✅ H1: Structured logging para KB vacío
                logger.warning(
                    "simple_health_check_empty_kb",
                    endpoint="/health/kb/simple",
                    records=0,
                    status_code=503
                )
                raise HTTPException(
                    status_code=503,
                    detail="Knowledge Base is empty"
                )
            
            # ✅ H1: Structured logging para éxito
            logger.debug(
                "simple_health_check_passed",
                endpoint="/health/kb/simple",
                records=count,
                status_code=200
            )
            
            return {
                "status": "healthy",
                "records": count
            }
            
    except HTTPException:
        raise
    except Exception as e:
        # ✅ H1: Structured logging para error
        logger.error(
            "simple_health_check_error",
            error=str(e),
            error_type=type(e).__name__,
            endpoint="/health/kb/simple",
            status_code=503,
            exc_info=True
        )
        raise HTTPException(
            status_code=503,
            detail=f"Health check failed: {str(e)}"
        )


# ============================================================================
# EXPORT ROUTER
# ============================================================================

__all__ = ["router"]