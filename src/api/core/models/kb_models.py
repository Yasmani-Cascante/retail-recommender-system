"""
Pydantic Models for Shopify Knowledge Base Integration
=======================================================

These models define the data structures for:
1. Shopify Page API responses
2. KB Content storage (database)
3. KB Answers (API responses)
4. Sync metadata and status

Author: Retail Recommender System Team
Date: 2026-01-11
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import UUID


# ══════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════

class SyncStatus(str, Enum):
    """Status of KB content sync."""
    PENDING = "pending"
    SYNCING = "syncing"
    SUCCESS = "success"
    FAILED = "failed"
    STALE = "stale"  # Last sync > 48h ago


class ContentFormat(str, Enum):
    """Supported content formats."""
    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN_TEXT = "plain_text"


# ══════════════════════════════════════════════════════════════════════════
# SHOPIFY API MODELS
# ══════════════════════════════════════════════════════════════════════════

class ShopifyPageTranslation(BaseModel):
    """
    Shopify Page Translation (from Shopify Markets API).
    
    Example:
    ```json
    {
        "locale": "en",
        "key": "body_html",
        "value": "<h2>Return Policy</h2>...",
        "created_at": "2026-01-11T10:00:00Z",
        "updated_at": "2026-01-11T12:00:00Z"
    }
    ```
    """
    locale: str = Field(..., description="Language code (en, es, pt)")
    key: str = Field(..., description="Field being translated (body_html, title, etc)")
    value: str = Field(..., description="Translated content")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "locale": "en",
                "key": "body_html",
                "value": "<h2>Return Policy</h2><p>30 days...</p>",
                "created_at": "2026-01-11T10:00:00Z",
                "updated_at": "2026-01-11T12:00:00Z"
            }
        }


class ShopifyPage(BaseModel):
    """
    Shopify Page model (from Admin API).
    
    Documentation:
    https://shopify.dev/docs/api/admin-rest/2024-01/resources/page
    
    Example:
    ```json
    {
        "id": 123456789,
        "title": "KB: Return Policy - General",
        "handle": "kb-return-policy-general",
        "body_html": "<h2>Política de Devoluciones</h2>...",
        "author": "Store Owner",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-11T10:00:00Z",
        "published_at": "2026-01-01T00:00:00Z",
        "template_suffix": "knowledge-base",
        "tags": "kb, policy_return, general"
    }
    ```
    """
    id: int = Field(..., description="Shopify Page ID")
    title: str = Field(..., description="Page title")
    handle: str = Field(..., description="URL-friendly handle")
    body_html: Optional[str] = Field(None, description="Page content (HTML, may be null)")
    
    # Optional fields
    author: Optional[str] = None
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    published_at: Optional[datetime] = None
    template_suffix: Optional[str] = Field(None, description="Template identifier")
    
    # Metadata
    metafields: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    
    # Tags (comma-separated string from Shopify)
    tags: Optional[str] = Field(None, description="Comma-separated tags")
    
    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: Optional[str]) -> Optional[str]:
        """Ensure tags is a string (Shopify returns as string)."""
        if v is None:
            return None
        if isinstance(v, list):
            return ", ".join(v)
        return str(v)
    
    def get_tag_list(self) -> List[str]:
        """Parse tags into a list."""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(",")]
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 123456789,
                "title": "KB: Return Policy - General",
                "handle": "kb-return-policy-general",
                "body_html": "<h2>Política de Devoluciones</h2><p>30 días...</p>",
                "author": "Store Owner",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-11T10:00:00Z",
                "published_at": "2026-01-01T00:00:00Z",
                "template_suffix": "knowledge-base",
                "tags": "kb, policy_return, general"
            }
        }


class ShopifyPagesResponse(BaseModel):
    """Response from Shopify Pages API (list endpoint)."""
    pages: List[ShopifyPage] = Field(default_factory=list)


class ShopifyPageResponse(BaseModel):
    """Response from Shopify Page API (single endpoint)."""
    page: ShopifyPage


# ══════════════════════════════════════════════════════════════════════════
# KB CONTENT MODELS (Database)
# ══════════════════════════════════════════════════════════════════════════

class KBContentBase(BaseModel):
    """Base model for KB Content (shared fields)."""
    sub_intent: str = Field(..., description="InformationalSubIntent value")
    language: str = Field(default="es", description="Language code (es, en, pt)")
    category: Optional[str] = Field(None, description="Product category (ZAPATOS, VESTIDOS, etc)")
    
    content: str = Field(..., description="Content in Markdown format")
    content_html: Optional[str] = Field(None, description="HTML version of content")
    title: Optional[str] = Field(None, description="Page title")
    meta_description: Optional[str] = Field(None, description="SEO meta description")
    
    shopify_page_id: int = Field(..., description="Shopify Page ID (source tracking)")
    shopify_url: Optional[str] = Field(None, description="Shopify Page URL")
    shopify_handle: Optional[str] = Field(None, description="Shopify Page handle")
    
    related_links: Optional[List[Dict[str, str]]] = Field(
        default_factory=list,
        description="Related links: [{'title': '...', 'url': '...'}]"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata (tags, priority, etc)"
    )


class KBContentCreate(KBContentBase):
    """Model for creating KB content (INSERT)."""
    pass


class KBContentUpdate(BaseModel):
    """Model for updating KB content (UPDATE) - all fields optional."""
    content: Optional[str] = None
    content_html: Optional[str] = None
    title: Optional[str] = None
    meta_description: Optional[str] = None
    shopify_url: Optional[str] = None
    shopify_handle: Optional[str] = None
    related_links: Optional[List[Dict[str, str]]] = None
    metadata: Optional[Dict[str, Any]]=None


class KBContent(KBContentBase):
    """
    Full KB Content model (from database).
    Includes all fields from kb_content table.
    """
    id: UUID = Field(..., description="Primary key")
    
    last_synced: datetime = Field(..., description="Last successful sync timestamp")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    cache_version: int = Field(default=1, description="Cache version (for invalidation)")
    
    class Config:
        from_attributes = True  # Enable ORM mode (was orm_mode in Pydantic v1)
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "sub_intent": "policy_return",
                "language": "es",
                "category": "ZAPATOS",
                "content": "**Devolución de Calzado**\n\n30 días...",
                "content_html": "<h2>Devolución de Calzado</h2><p>30 días...</p>",
                "title": "Devolución de Calzado",
                "meta_description": "Política de devoluciones para calzado",
                "shopify_page_id": 123456789,
                "shopify_url": "https://tutienda.myshopify.com/pages/kb-return-shoes",
                "shopify_handle": "kb-return-shoes",
                "last_synced": "2026-01-11T10:00:00Z",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-11T10:00:00Z",
                "cache_version": 5,
                "related_links": [
                    {"title": "Iniciar Devolución", "url": "/account/returns"}
                ],
                "metadata": {
                    "tags": ["policy", "important"],
                    "priority": "high"
                }
            }
        }
    
    def is_stale(self, max_age_hours: int = 48) -> bool:
        """
        Check if content is stale (needs refresh).
        
        Args:
            max_age_hours: Maximum age in hours before considering stale
            
        Returns:
            True if content is older than max_age_hours
        """
        age = datetime.utcnow() - self.last_synced
        return age.total_seconds() > (max_age_hours * 3600)
    
    def is_fresh(self, max_age_hours: int = 48) -> bool:
        """
        Check if content is fresh (doesn't need refresh).
        
        Args:
            max_age_hours: Maximum age in hours to consider fresh
            
        Returns:
            True if content is newer than max_age_hours
        """
        return not self.is_stale(max_age_hours)


# ══════════════════════════════════════════════════════════════════════════
# KB ANSWER MODELS (API Response)
# ══════════════════════════════════════════════════════════════════════════

class KBAnswerLink(BaseModel):
    """Related link in KB answer."""
    title: str = Field(..., description="Link title/text")
    url: str = Field(..., description="Link URL")
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Iniciar Devolución",
                "url": "/account/returns"
            }
        }


class KBAnswer(BaseModel):
    """
    Knowledge Base Answer (API response to user).
    
    This is what gets returned to the user when they ask
    an informational question.
    """
    answer: str = Field(..., description="Answer text (Markdown or HTML)")
    format: ContentFormat = Field(default=ContentFormat.MARKDOWN, description="Content format")
    title: Optional[str] = Field(None, description="Answer title")
    
    related_links: List[KBAnswerLink] = Field(
        default_factory=list,
        description="Related resources"
    )
    
    # Metadata (optional, for debugging/analytics)
    source: Optional[str] = Field(default="shopify_cms", description="Content source")
    language: Optional[str] = Field(None, description="Content language")
    last_updated: Optional[datetime] = Field(None, description="Content last update")
    cache_hit: Optional[bool] = Field(None, description="Was this a cache hit?")
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "**📦 Política de Devoluciones**\n\n✅ 30 días naturales...",
                "format": "markdown",
                "title": "Política de Devoluciones",
                "related_links": [
                    {"title": "Iniciar Devolución", "url": "/account/returns"},
                    {"title": "Seguimiento", "url": "/account/orders"}
                ],
                "source": "shopify_cms",
                "language": "es",
                "last_updated": "2026-01-11T10:00:00Z",
                "cache_hit": True
            }
        }


# ══════════════════════════════════════════════════════════════════════════
# SYNC METADATA MODELS
# ══════════════════════════════════════════════════════════════════════════

class KBSyncMetadata(BaseModel):
    """
    Metadata about KB content sync status.
    Used for monitoring and debugging.
    """
    sub_intent: str
    language: str
    category: Optional[str] = None
    
    status: SyncStatus
    last_synced: Optional[datetime] = None
    last_error: Optional[str] = None
    shopify_page_id: Optional[int] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "sub_intent": "policy_return",
                "language": "es",
                "category": "ZAPATOS",
                "status": "success",
                "last_synced": "2026-01-11T10:00:00Z",
                "last_error": None,
                "shopify_page_id": 123456789
            }
        }


class KBSyncReport(BaseModel):
    """
    Report of sync operation (batch sync results).
    """
    total_pages: int = Field(..., description="Total pages attempted to sync")
    successful: int = Field(default=0, description="Successfully synced pages")
    failed: int = Field(default=0, description="Failed syncs")
    skipped: int = Field(default=0, description="Skipped (already up-to-date)")
    
    sync_started_at: datetime
    sync_completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    errors: List[str] = Field(default_factory=list, description="Error messages")
    details: List[KBSyncMetadata] = Field(default_factory=list, description="Per-page sync status")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_pages": 50,
                "successful": 48,
                "failed": 2,
                "skipped": 0,
                "sync_started_at": "2026-01-11T10:00:00Z",
                "sync_completed_at": "2026-01-11T10:05:00Z",
                "duration_seconds": 300.5,
                "errors": [
                    "Failed to fetch page 12345: Timeout",
                    "Failed to parse tags for page 67890"
                ]
            }
        }


# ══════════════════════════════════════════════════════════════════════════
# WEBHOOK MODELS
# ══════════════════════════════════════════════════════════════════════════

class ShopifyWebhookPage(BaseModel):
    """Simplified page model from webhook payload."""
    id: int
    title: str
    handle: str
    body_html: Optional[str] = None
    updated_at: datetime
    tags: Optional[str] = None


class ShopifyPageWebhook(BaseModel):
    """
    Shopify Page Webhook payload.
    
    Topics:
    - pages/create
    - pages/update
    - pages/delete
    """
    page: ShopifyWebhookPage = Field(..., description="Page data")


class ShopifyTranslationWebhook(BaseModel):
    """
    Shopify Translation Webhook payload.
    
    Topics:
    - translations/create
    - translations/update
    """
    locale: str
    resource_id: int
    resource_type: str  # "Page"
    key: str
    value: str


# ══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════

def kb_content_to_answer(content: KBContent, cache_hit: bool = False) -> KBAnswer:
    """
    Convert KBContent (database model) to KBAnswer (API response).
    
    Args:
        content: KB content from database
        cache_hit: Whether this was served from cache
        
    Returns:
        KBAnswer ready to send to user
    """
    # Parse related links
    links = []
    if content.related_links:
        for link_data in content.related_links:
            links.append(KBAnswerLink(
                title=link_data.get("title", ""),
                url=link_data.get("url", "")
            ))
    
    return KBAnswer(
        answer=content.content,
        format=ContentFormat.MARKDOWN,
        title=content.title,
        related_links=links,
        source="shopify_cms",
        language=content.language,
        last_updated=content.updated_at,
        cache_hit=cache_hit
    )
