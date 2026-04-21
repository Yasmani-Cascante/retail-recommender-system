"""
Configuration for Shopify Knowledge Base Integration.

Extends existing config.py with KB-specific settings.
"""

from pydantic import Field
from typing import Optional


class KBSettings:
    """
    Knowledge Base configuration settings.
    
    Add these to your main Config class in config.py:
    """
    
    # ═══════════════════════════════════════════════════════════
    # SHOPIFY KB API
    # ═══════════════════════════════════════════════════════════
    
    # Shopify webhook secret for HMAC validation
    SHOPIFY_WEBHOOK_SECRET: Optional[str] = Field(
        default=None,
        env="SHOPIFY_WEBHOOK_SECRET",
        description="Shopify webhook HMAC secret (for security)"
    )
    
    # ═══════════════════════════════════════════════════════════
    # SYNC CONFIGURATION
    # ═══════════════════════════════════════════════════════════
    
    # How often to poll Shopify for changes (fallback to webhooks)
    KB_SYNC_INTERVAL_MINUTES: int = Field(
        default=5,
        env="KB_SYNC_INTERVAL_MINUTES",
        description="Background sync interval (minutes)"
    )
    
    # Enable background sync job
    KB_ENABLE_BACKGROUND_SYNC: bool = Field(
        default=True,
        env="KB_ENABLE_BACKGROUND_SYNC",
        description="Enable periodic background sync"
    )
    
    # ═══════════════════════════════════════════════════════════
    # CACHE CONFIGURATION
    # ═══════════════════════════════════════════════════════════
    
    # Redis cache TTL for KB content (hours)
    KB_CACHE_TTL_HOURS: int = Field(
        default=24,
        env="KB_CACHE_TTL_HOURS",
        description="Redis cache TTL for KB content (hours)"
    )
    
    # PostgreSQL buffer max age before considering stale (hours)
    KB_BUFFER_MAX_AGE_HOURS: int = Field(
        default=48,
        env="KB_BUFFER_MAX_AGE_HOURS",
        description="PostgreSQL buffer staleness threshold (hours)"
    )
    
    # ═══════════════════════════════════════════════════════════
    # FEATURE FLAGS
    # ═══════════════════════════════════════════════════════════
    
    # Use Shopify KB (if False, falls back to hardcoded knowledge_base.py)
    KB_USE_SHOPIFY_CMS: bool = Field(
        default=True,
        env="KB_USE_SHOPIFY_CMS",
        description="Enable Shopify CMS integration"
    )
    
    # Fallback to hardcoded KB if Shopify unavailable
    KB_ENABLE_FALLBACK: bool = Field(
        default=True,
        env="KB_ENABLE_FALLBACK",
        description="Fallback to hardcoded KB on Shopify failure"
    )


# ═══════════════════════════════════════════════════════════════
# EXAMPLE .env ADDITIONS
# ═══════════════════════════════════════════════════════════════

"""
# Shopify KB Configuration
SHOPIFY_WEBHOOK_SECRET=your_webhook_secret_here
KB_SYNC_INTERVAL_MINUTES=5
KB_ENABLE_BACKGROUND_SYNC=true
KB_CACHE_TTL_HOURS=24
KB_BUFFER_MAX_AGE_HOURS=48
KB_USE_SHOPIFY_CMS=true
KB_ENABLE_FALLBACK=true
"""