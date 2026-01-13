"""
Shopify Webhooks Router
=======================

FastAPI router for handling Shopify webhooks.

Supported webhooks:
- pages/create: New KB page created
- pages/update: KB page updated
- pages/delete: KB page deleted
- translations/update: Translation updated

Security:
- HMAC validation (X-Shopify-Hmac-SHA256)
- Async processing (non-blocking)
- Idempotent (safe retries)

Author: Retail Recommender System Team
Date: 2026-01-11
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from src.api.core.models.kb_models import (
    ShopifyPageWebhook,
    ShopifyTranslationWebhook,
    KBSyncMetadata
)
from src.api.services.shopify_kb_sync import ShopifyKBSyncService
from src.api.integrations.shopify_kb_client import ShopifyKBClient

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════

router = APIRouter(
    prefix="/webhooks/shopify",
    tags=["webhooks", "shopify", "kb"]
)


# ══════════════════════════════════════════════════════════════════════════
# DEPENDENCY INJECTION
# ══════════════════════════════════════════════════════════════════════════

# These will be injected via dependency_overrides in main.py
# Example:
# app.dependency_overrides[get_shopify_client] = lambda: shopify_kb_client
# app.dependency_overrides[get_sync_service] = lambda: sync_service

async def get_shopify_client() -> ShopifyKBClient:
    """Get Shopify KB client (to be overridden)."""
    raise HTTPException(500, "Shopify client not configured")


async def get_sync_service() -> ShopifyKBSyncService:
    """Get sync service (to be overridden)."""
    raise HTTPException(500, "Sync service not configured")


# ══════════════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@router.post("/pages/create")
async def handle_page_create(
    request: Request,
    background_tasks: BackgroundTasks,
    shopify_client: ShopifyKBClient = Depends(get_shopify_client),
    sync_service: ShopifyKBSyncService = Depends(get_sync_service)
):
    """
    Handle Shopify pages/create webhook.
    
    Triggered when a new page is created in Shopify.
    
    Security:
    - Validates HMAC signature
    - Processes asynchronously (non-blocking)
    
    Example webhook payload:
    ```json
    {
        "page": {
            "id": 123456789,
            "title": "KB: Return Policy - General",
            "handle": "kb-return-policy-general",
            "body_html": "<h2>Política...</h2>",
            "tags": "kb, policy_return, general",
            ...
        }
    }
    ```
    """
    # Step 1: Get raw body and headers
    body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-SHA256", "")
    
    # Step 2: Validate HMAC
    if not shopify_client.validate_webhook(body, hmac_header):
        logger.error("Invalid webhook HMAC signature (pages/create)")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Step 3: Parse webhook payload
    try:
        import json
        data = json.loads(body)
        webhook = ShopifyPageWebhook(**data)
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
    
    page_id = webhook.page.id
    
    logger.info(f"✅ Received pages/create webhook: Page ID {page_id}")
    
    # Step 4: Process asynchronously (don't block webhook response)
    background_tasks.add_task(
        process_page_webhook,
        sync_service=sync_service,
        page_id=page_id,
        topic="pages/create"
    )
    
    # Step 5: Return 200 OK immediately (Shopify expects fast response)
    return {
        "status": "accepted",
        "message": f"Webhook received for page {page_id}",
        "topic": "pages/create"
    }


@router.post("/pages/update")
async def handle_page_update(
    request: Request,
    background_tasks: BackgroundTasks,
    shopify_client: ShopifyKBClient = Depends(get_shopify_client),
    sync_service: ShopifyKBSyncService = Depends(get_sync_service)
):
    """
    Handle Shopify pages/update webhook.
    
    Triggered when a page is updated in Shopify.
    
    Process:
    1. Validate HMAC
    2. Parse payload
    3. Sync page asynchronously
    4. Invalidate cache
    """
    # Step 1: Get raw body and headers
    body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-SHA256", "")
    
    # Step 2: Validate HMAC
    if not shopify_client.validate_webhook(body, hmac_header):
        logger.error("Invalid webhook HMAC signature (pages/update)")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Step 3: Parse webhook payload
    try:
        import json
        data = json.loads(body)
        webhook = ShopifyPageWebhook(**data)
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
    
    page_id = webhook.page.id
    
    logger.info(f"✅ Received pages/update webhook: Page ID {page_id}")
    
    # Step 4: Process asynchronously
    background_tasks.add_task(
        process_page_webhook,
        sync_service=sync_service,
        page_id=page_id,
        topic="pages/update"
    )
    
    # Step 5: Return 200 OK
    return {
        "status": "accepted",
        "message": f"Webhook received for page {page_id}",
        "topic": "pages/update"
    }


@router.post("/pages/delete")
async def handle_page_delete(
    request: Request,
    background_tasks: BackgroundTasks,
    shopify_client: ShopifyKBClient = Depends(get_shopify_client),
    sync_service: ShopifyKBSyncService = Depends(get_sync_service)
):
    """
    Handle Shopify pages/delete webhook.
    
    Triggered when a page is deleted in Shopify.
    
    Process:
    1. Validate HMAC
    2. Extract page ID
    3. Delete from buffer asynchronously
    4. Invalidate cache
    """
    # Step 1: Get raw body and headers
    body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-SHA256", "")
    
    # Step 2: Validate HMAC
    if not shopify_client.validate_webhook(body, hmac_header):
        logger.error("Invalid webhook HMAC signature (pages/delete)")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Step 3: Parse webhook payload
    # Note: Delete webhooks have a different format (just id)
    try:
        import json
        data = json.loads(body)
        page_id = data.get("id")
        
        if not page_id:
            raise ValueError("No page ID in webhook payload")
            
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
    
    logger.info(f"✅ Received pages/delete webhook: Page ID {page_id}")
    
    # Step 4: Process asynchronously
    background_tasks.add_task(
        process_page_webhook,
        sync_service=sync_service,
        page_id=page_id,
        topic="pages/delete"
    )
    
    # Step 5: Return 200 OK
    return {
        "status": "accepted",
        "message": f"Webhook received for page {page_id}",
        "topic": "pages/delete"
    }


@router.post("/translations/update")
async def handle_translation_update(
    request: Request,
    background_tasks: BackgroundTasks,
    shopify_client: ShopifyKBClient = Depends(get_shopify_client),
    sync_service: ShopifyKBSyncService = Depends(get_sync_service)
):
    """
    Handle Shopify translations/update webhook.
    
    Triggered when a translation is updated in Shopify Markets.
    
    Process:
    1. Validate HMAC
    2. Extract resource ID (page ID)
    3. Re-sync page (all languages) asynchronously
    4. Invalidate cache for all languages
    """
    # Step 1: Get raw body and headers
    body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-SHA256", "")
    
    # Step 2: Validate HMAC
    if not shopify_client.validate_webhook(body, hmac_header):
        logger.error("Invalid webhook HMAC signature (translations/update)")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Step 3: Parse webhook payload
    try:
        import json
        data = json.loads(body)
        webhook = ShopifyTranslationWebhook(**data)
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
    
    # Only process if resource is a Page
    if webhook.resource_type != "Page":
        logger.info(f"Ignoring translation webhook for resource type: {webhook.resource_type}")
        return {
            "status": "ignored",
            "message": f"Not a Page translation (resource_type={webhook.resource_type})"
        }
    
    page_id = webhook.resource_id
    locale = webhook.locale
    
    logger.info(
        f"✅ Received translations/update webhook: "
        f"Page ID {page_id}, Locale {locale}"
    )
    
    # Step 4: Re-sync entire page (all languages)
    background_tasks.add_task(
        process_page_webhook,
        sync_service=sync_service,
        page_id=page_id,
        topic="pages/update"  # Treat as page update
    )
    
    # Step 5: Return 200 OK
    return {
        "status": "accepted",
        "message": f"Translation webhook received for page {page_id} (locale {locale})",
        "topic": "translations/update"
    }


# ══════════════════════════════════════════════════════════════════════════
# BACKGROUND PROCESSING
# ══════════════════════════════════════════════════════════════════════════

async def process_page_webhook(
    sync_service: ShopifyKBSyncService,
    page_id: int,
    topic: str
) -> None:
    """
    Process page webhook in background.
    
    This is called asynchronously via BackgroundTasks.
    
    Args:
        sync_service: Sync service
        page_id: Shopify Page ID
        topic: Webhook topic (pages/create, pages/update, pages/delete)
    """
    logger.info(f"Processing webhook in background: {topic} (page {page_id})")
    
    try:
        # Handle webhook
        result = await sync_service.handle_page_webhook(page_id, topic)
        
        if result.status == "success":
            logger.info(
                f"✅ Webhook processed successfully: {topic} (page {page_id})"
            )
        else:
            logger.error(
                f"❌ Webhook processing failed: {topic} (page {page_id}): "
                f"{result.last_error}"
            )
            
    except Exception as e:
        logger.error(
            f"❌ Exception processing webhook: {topic} (page {page_id}): {e}",
            exc_info=True
        )


# ══════════════════════════════════════════════════════════════════════════
# WEBHOOK VERIFICATION ENDPOINT (For Shopify setup)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/verify")
async def verify_webhook():
    """
    Webhook verification endpoint.
    
    Used during Shopify webhook setup to verify endpoint is accessible.
    
    Returns 200 OK with simple message.
    """
    return {
        "status": "ok",
        "message": "Shopify webhook endpoint is active",
        "endpoints": [
            "/webhooks/shopify/pages/create",
            "/webhooks/shopify/pages/update",
            "/webhooks/shopify/pages/delete",
            "/webhooks/shopify/translations/update"
        ]
    }


# ══════════════════════════════════════════════════════════════════════════
# WEBHOOK STATUS ENDPOINT (For monitoring)
# ══════════════════════════════════════════════════════════════════════════

class WebhookStats(BaseModel):
    """Webhook statistics (placeholder for future metrics)."""
    total_received: int = Field(default=0, description="Total webhooks received")
    total_processed: int = Field(default=0, description="Total webhooks processed")
    total_failed: int = Field(default=0, description="Total webhooks failed")


@router.get("/stats")
async def get_webhook_stats() -> WebhookStats:
    """
    Get webhook statistics.
    
    TODO: Implement actual metrics collection.
    
    Returns:
        WebhookStats with counts
    """
    # TODO: Implement real metrics from observability system
    return WebhookStats(
        total_received=0,
        total_processed=0,
        total_failed=0
    )
