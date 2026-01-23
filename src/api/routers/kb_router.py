"""
Knowledge Base Router
=====================

Expone endpoints para consultar el Knowledge Base del sistema.

Endpoints:
- GET /kb/answer - Obtener respuesta del KB por sub_intent
- GET /kb/health - Health check del KB
- POST /kb/sync - Trigger manual de sincronización (admin)

Author: Retail Recommender System Team
Date: 2026-01-17
"""

import logging
from typing import Optional
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


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
    request: Request,  # ✅ MODIFICADO: Agregado para access headers
    sub_intent: str = Query(..., description="Sub-intent to query"),
    language: Optional[str] = Query(  # ✅ MODIFICADO: Ahora es Optional
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
        
        **Examples:**
        ```
        # Explicit language
        GET /kb/answer?sub_intent=policy_return&language=en
        
        # Auto-detect from Accept-Language header
        GET /kb/answer?sub_intent=policy_return
        Headers: Accept-Language: en-US,en;q=0.9
        
        # Default to ES
        GET /kb/answer?sub_intent=policy_return
        (No Accept-Language header)
        
        # With category
        GET /kb/answer?sub_intent=product_care&language=es&category=cotton
        ```
        """
        try:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # ✅ NUEVO: Language Detection
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if language:
                # Explicit parameter → Validate
                detected_language = validate_language(language)
                detection_method = "explicit_parameter"
            else:
                # Auto-detect from Accept-Language header
                detected_language = detect_language_from_request(request)
                detection_method = "accept_language_header" if request.headers.get("Accept-Language") else "default"
            
            # Log language detection for debugging
            logger.info(
                f"KB query: sub_intent={sub_intent}, language={detected_language} "
                f"(method: {detection_method}), category={category}"
            )
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # Validate sub_intent
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            try:
                sub_intent_enum = InformationalSubIntent(sub_intent.lower())
            except ValueError:
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
                language=detected_language,  # ✅ MODIFICADO: Use detected language
                category=category
            )
            
            if not answer:
                # No answer found
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "No answer found",
                        "sub_intent": sub_intent,
                        "language": detected_language,  # ✅ MODIFICADO: Use detected
                        "category": category,
                        "suggestion": "Check if content exists in Shopify and has been synced"
                    }
                )
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # Return answer
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            return {
                "sub_intent": sub_intent,
                "language": detected_language,  # ✅ MODIFICADO: Use detected
                "category": category,
                "answer": answer.answer,
                "sub_intent_value": answer.sub_intent.value,
                "sources": answer.sources or [],
                "related_links": answer.related_links or []
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting KB answer: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal server error: {str(e)}"
            )


@router.get("/health")
async def kb_health_check(request: Request = None):
    """
    Health check for Knowledge Base.
    
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
                await kb.redis.ping()
                health_status["details"]["redis_connected"] = True
            except:
                health_status["details"]["redis_connected"] = False
            
            # Test DB connection
            try:
                async with kb.db.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                health_status["details"]["db_connected"] = True
            except:
                health_status["details"]["db_connected"] = False
                
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
        logger.error(f"Error in KB health check: {e}", exc_info=True)
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
        
        logger.info("Manual KB sync triggered via API")
        
        # Trigger sync
        report = await sync_service.sync_all_pages()
        
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
            "errors": report.errors[:10] if report.errors else [],  # Limit errors
            "details": [
                {
                    "sub_intent": d.sub_intent,
                    "language": d.language,
                    "status": d.status.value,
                    "last_error": d.last_error
                }
                for d in report.details[:20]  # Limit details
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering KB sync: {e}", exc_info=True)
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
        
        return {
            "total_pages": total,
            "by_sub_intent": by_sub_intent,
            "by_language": by_language
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting KB stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )