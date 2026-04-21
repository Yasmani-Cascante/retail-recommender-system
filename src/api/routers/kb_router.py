"""
Knowledge Base Router
=====================

Exposes endpoints for querying the Knowledge Base system.

Endpoints:
- GET /kb/answer - Get answer from KB by sub_intent
- GET /kb/health - Health check for KB
- POST /kb/sync - Trigger manual synchronization (admin)

Author: Retail Recommender System Team
Date: 2026-01-17
Version: H1 - Structured Logging Migration
"""

import asyncio
import structlog  # ✅ H1: Structured Logging Migration
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from src.api.core.intent_types import InformationalSubIntent
from src.api.core.knowledge_base_v2 import ShopifyKnowledgeBase
from src.api.services.shopify_kb_sync import ShopifyKBSyncService

# ✅ NUEVO: Import language detection utilities
from src.api.utils.language_detection import (
    detect_language_from_request,
    validate_language
)

logger = structlog.get_logger(__name__)  # ✅ H1: Structured Logging Migration

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

# Cache para evitar saturar Redis con health checks durante load testing
# Solo se usa si múltiples requests llegan en <15 segundos
_health_cache = {
    "status": None,           # Último health status conocido
    "timestamp": None,        # Cuándo se obtuvo
    "ttl_seconds": 15         # Cache válido por 15 segundos
}


# ══════════════════════════════════════════════════════════════════════════
# DEPENDENCY INJECTION
# ══════════════════════════════════════════════════════════════════════════

def get_kb(request) -> ShopifyKnowledgeBase:
    """Get Knowledge Base instance from app state."""
    if not hasattr(request.app.state, "knowledge_base"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge Base not initialized"
        )
    return request.app.state.knowledge_base


def get_sync_service(request) -> ShopifyKBSyncService:
    """Get KB Sync Service instance from app state."""
    if not hasattr(request.app.state, "kb_sync_service"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KB Sync Service not initialized"
        )
    return request.app.state.kb_sync_service


# ══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/answer")
async def get_kb_answer(
    request: Request,
    sub_intent: str = Query(..., description="Sub-intent to query"),
    language: Optional[str] = Query(
        None,
        description="Language code (es, en). Auto-detected from Accept-Language header if not provided."
    ),
    category: Optional[str] = Query(None, description="Optional category filter")
):
    """
    Get answer from Knowledge Base.
    
    **Language Detection Priority:**
    1. Explicit `language` query parameter (highest priority)
    2. Accept-Language HTTP header (browser/client preference)
    3. Default: 'es'
    
    **Parameters:**
    - sub_intent: The informational sub-intent (policy_return, product_care, etc.)
    - language: Language code (optional, auto-detected if not provided)
    - category: Optional category for specific answers
    
    **Returns:**
    ```json
    {
        "sub_intent": "policy_return",
        "language": "es",
        "category": null,
        "answer": "Content here...",
        "sub_intent_value": "policy_return",
        "sources": [],
        "related_links": []
    }
    ```
    """
    try:
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ✅ Language Detection
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if language:
            # Explicit parameter → Validate
            detected_language = validate_language(language)
            detection_method = "explicit_parameter"
        else:
            # Auto-detect from Accept-Language header
            detected_language = detect_language_from_request(request)
            detection_method = "accept_language_header" if request.headers.get("Accept-Language") else "default"
        
        # ✅ H1: Structured logging
        logger.info(
            "kb_answer_request",
            sub_intent=sub_intent,
            language=detected_language,
            detection_method=detection_method,
            category=category
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Validate sub_intent
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        try:
            sub_intent_enum = InformationalSubIntent(sub_intent.lower())
        except ValueError:
            # ✅ H1: Structured error
            logger.warning(
                "kb_invalid_sub_intent",
                sub_intent=sub_intent,
                valid_values=[e.value for e in InformationalSubIntent]
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sub_intent: {sub_intent}. Must be one of: {[e.value for e in InformationalSubIntent]}"
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Get KB from dependency injection
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        kb = get_kb(request)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Query KB with detected language
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        answer = await kb.get_answer(
            sub_intent=sub_intent_enum,
            language=detected_language,
            category=category
        )
        
        if not answer:
            # ✅ H1: Structured warning
            logger.warning(
                "kb_answer_not_found",
                sub_intent=sub_intent,
                language=detected_language,
                category=category
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "No answer found",
                    "sub_intent": sub_intent,
                    "language": detected_language,
                    "category": category,
                    "suggestion": "Check if content exists in Shopify and has been synced"
                }
            )
        
        # ✅ H1: Structured logging para éxito
        logger.info(
            "kb_answer_found",
            sub_intent=sub_intent,
            language=detected_language,
            category=category,
            answer_length=len(answer.answer) if answer.answer else 0
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Return answer
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        return {
            "sub_intent": sub_intent,
            "language": detected_language,
            "category": category,
            "answer": answer.answer,
            "sub_intent_value": answer.sub_intent.value,
            "sources": answer.sources or [],
            "related_links": answer.related_links or []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # ✅ H1: Structured error con exc_info
        logger.error(
            "kb_answer_error",
            sub_intent=sub_intent,
            language=language,
            category=category,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/health")
async def kb_health_check(request: Request = None):
    """
    Health check for Knowledge Base.

    **Performance**: Response time <500ms target

    **Returns:**
    ```json
    {
        "status": "healthy",
        "kb_initialized": true,
        "sync_service_initialized": true,
        "details": {
            "redis_connected": true,
            "db_connected": true
        }
    }
    ```
    """

    # ✅ CACHE CHECK: Evitar ping excesivo a Redis durante load testing
    now = datetime.utcnow()
    
    if (_health_cache["status"] is not None and 
        _health_cache["timestamp"] is not None):
        
        cache_age_seconds = (now - _health_cache["timestamp"]).total_seconds()
        
        if cache_age_seconds < _health_cache["ttl_seconds"]:
            # ✅ H1: Structured debug logging
            logger.debug(
                "kb_health_cache_hit",
                cache_age_seconds=round(cache_age_seconds, 2),
                ttl_seconds=_health_cache["ttl_seconds"]
            )
            return _health_cache["status"]
    
    # ✅ H1: Structured debug logging
    logger.debug("kb_health_cache_miss")

    try:
        health_status = {
            "status": "unknown",
            "kb_initialized": False,
            "sync_service_initialized": False,
            "details": {}
        }
        
        # Check KB initialization
        try:
            kb = get_kb(request)
            health_status["kb_initialized"] = True
            
            # Test Redis connection
            try:
                redis_health = await kb.redis.health_check()
                redis_status = redis_health.get("status", "unknown")
                
                if redis_status == "healthy":
                    health_status["details"]["redis_connected"] = True
                    ping_time = redis_health.get("ping_time_ms", "N/A")
                    # ✅ H1: Structured debug
                    logger.debug(
                        "kb_redis_health_check",
                        status="healthy",
                        ping_time_ms=ping_time
                    )
                    
                elif redis_status == "degraded":
                    health_status["details"]["redis_connected"] = False
                    health_status["details"]["redis_status"] = "timeout"
                    # ✅ H1: Structured warning
                    logger.warning(
                        "kb_redis_health_check",
                        status="timeout",
                        threshold_ms=500
                    )
                    
                else:
                    health_status["details"]["redis_connected"] = False
                    health_status["details"]["redis_status"] = redis_status
                    last_test = redis_health.get("last_test", "failed")
                    # ✅ H1: Structured warning
                    logger.warning(
                        "kb_redis_health_check",
                        status=redis_status,
                        last_test=last_test
                    )
                    
            except Exception as e:
                health_status["details"]["redis_connected"] = False
                health_status["details"]["redis_status"] = "error"
                health_status["details"]["redis_error"] = str(e)
                # ✅ H1: Structured warning
                logger.warning(
                    "kb_redis_health_check_exception",
                    error=str(e),
                    error_type=type(e).__name__
                )
          
            # Test DB connection
            try:
                async with kb.db.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                health_status["details"]["db_connected"] = True
            except Exception as e:
                health_status["details"]["db_connected"] = False
                # ✅ H1: Structured warning
                logger.warning(
                    "kb_db_health_check_failed",
                    error=str(e),
                    error_type=type(e).__name__
                )
                
        except HTTPException:
            health_status["kb_initialized"] = False
        
        # Check Sync Service initialization
        try:
            sync_service = get_sync_service(request)
            health_status["sync_service_initialized"] = True
        except HTTPException:
            health_status["sync_service_initialized"] = False
        
        # Determine overall status
        if (health_status["kb_initialized"] and 
            health_status["sync_service_initialized"] and
            health_status["details"].get("redis_connected") and
            health_status["details"].get("db_connected")):
            health_status["status"] = "healthy"
        elif health_status["kb_initialized"]:
            health_status["status"] = "degraded"
        else:
            health_status["status"] = "unhealthy"
        
        # ✅ UPDATE CACHE
        _health_cache["status"] = health_status
        _health_cache["timestamp"] = now
        
        # ✅ H1: Structured logging
        logger.debug(
            "kb_health_cache_updated",
            status=health_status["status"]
        )
        
        # Return appropriate status code
        if health_status["status"] == "healthy":
            return health_status
        elif health_status["status"] == "degraded":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=health_status
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=health_status
            )
            
    except Exception as e:
        # ✅ H1: Structured error
        logger.error(
            "kb_health_check_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "error": str(e)
            }
        )


@router.post("/sync")
async def trigger_kb_sync(request: Request = None):
    """
    Trigger manual KB sync from Shopify.
    
    **Admin endpoint** - Manually triggers synchronization of all KB pages.
    
    **Returns:**
    ```json
    {
        "status": "success",
        "total_pages": 11,
        "successful": 11,
        "failed": 0,
        "skipped": 0,
        "duration_seconds": 4.73,
        "details": [...]
    }
    ```
    """
    try:
        # Get sync service
        sync_service = get_sync_service(request)
        
        # ✅ H1: Structured logging
        logger.info(
            "kb_manual_sync_triggered",
            trigger_source="api_endpoint"
        )
        
        # Trigger sync
        report = await sync_service.sync_all_pages()
        
        # ✅ H1: Structured logging con métricas
        logger.info(
            "kb_manual_sync_completed",
            total_pages=report.total_pages,
            successful=report.successful,
            failed=report.failed,
            skipped=report.skipped,
            duration_seconds=round(report.duration_seconds, 2),
            success_rate=round(
                (report.successful / report.total_pages * 100) 
                if report.total_pages > 0 else 0, 
                1
            )
        )
        
        # Return report
        return {
            "status": "success" if report.failed == 0 else "partial",
            "total_pages": report.total_pages,
            "successful": report.successful,
            "failed": report.failed,
            "skipped": report.skipped,
            "duration_seconds": report.duration_seconds,
            "sync_started_at": report.sync_started_at.isoformat(),
            "sync_completed_at": report.sync_completed_at.isoformat() if report.sync_completed_at else None,
            "errors": report.errors[:10] if report.errors else [],
            "details": [
                {
                    "sub_intent": d.sub_intent,
                    "language": d.language,
                    "status": d.status.value,
                    "last_error": d.last_error
                }
                for d in report.details[:20]
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # ✅ H1: Structured error
        logger.error(
            "kb_manual_sync_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger sync: {str(e)}"
        )


# ══════════════════════════════════════════════════════════════════════════
# CONVENIENCE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/sub-intents")
async def list_sub_intents():
    """
    List all available sub-intents.
    
    **Returns:**
    ```json
    {
        "sub_intents": [
            "policy_return",
            "policy_shipping",
            "product_care",
            ...
        ],
        "count": 15
    }
    ```
    """
    sub_intents = [e.value for e in InformationalSubIntent]
    
    # ✅ H1: Structured logging
    logger.debug(
        "kb_sub_intents_listed",
        count=len(sub_intents)
    )
    
    return {
        "sub_intents": sub_intents,
        "count": len(sub_intents)
    }


@router.get("/stats")
async def kb_stats(request: Request = None):
    """
    Get Knowledge Base statistics.
    
    **Returns:**
    ```json
    {
        "total_pages": 11,
        "by_sub_intent": {
            "policy_return": 1,
            "product_care": 1,
            ...
        },
        "by_language": {
            "es": 11,
            "en": 0
        }
    }
    ```
    """
    try:
        kb = get_kb(request)
        
        # Query database for stats
        async with kb.db.acquire() as conn:
            # Total pages
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM kb_contents"
            )
            
            # By sub_intent
            by_sub_intent = {}
            rows = await conn.fetch(
                "SELECT sub_intent, COUNT(*) as count "
                "FROM kb_contents "
                "GROUP BY sub_intent"
            )
            for row in rows:
                by_sub_intent[row["sub_intent"]] = row["count"]
            
            # By language
            by_language = {}
            rows = await conn.fetch(
                "SELECT language, COUNT(*) as count "
                "FROM kb_contents "
                "GROUP BY language"
            )
            for row in rows:
                by_language[row["language"]] = row["count"]
        
        # ✅ H1: Structured logging
        logger.info(
            "kb_stats_retrieved",
            total_pages=total,
            sub_intents_count=len(by_sub_intent),
            languages_count=len(by_language)
        )
        
        return {
            "total_pages": total,
            "by_sub_intent": by_sub_intent,
            "by_language": by_language
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # ✅ H1: Structured error
        logger.error(
            "kb_stats_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )