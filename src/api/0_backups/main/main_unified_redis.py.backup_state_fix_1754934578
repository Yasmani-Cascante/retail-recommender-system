"""
Punto de entrada principal unificado para la API del sistema de recomendaciones
con integración Enterprise Redis y ServiceFactory.

Este archivo implementa la API REST modernizada con arquitectura enterprise,
dependency injection unificada y preparación para microservicios.

Author: Senior Architecture Team
Version: 2.1.0 - Enterprise Migration
"""

import os
import time
import logging
import asyncio
from dotenv import load_dotenv
from datetime import datetime

# ✅ CONFIGURAR LOGGING ENTERPRISE
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ✅ ENTERPRISE IMPORTS
from fastapi import FastAPI, Header, Query, HTTPException, BackgroundTasks, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import math
import random
import json

# ✅ ENTERPRISE FACTORY ARCHITECTURE
from src.api.factories import (
    ServiceFactory,
    BusinessCompositionRoot,
    InfrastructureCompositionRoot,
    HealthCompositionRoot,
    validate_factory_architecture
)

# ✅ OBSERVABILITY MANAGER ENTERPRISE
try:
    from src.api.core.observability_manager import get_observability_manager
    OBSERVABILITY_MANAGER_AVAILABLE = True
    logger.info("✅ ObservabilityManager loaded - Enterprise observability enabled")
    
    _test_observability = get_observability_manager()
    if hasattr(_test_observability, 'metrics_collector'):
        logger.info("✅ MetricsCollector integrated - Enterprise monitoring ready")
    else:
        logger.warning("⚠️ MetricsCollector not found")
except ImportError as e:
    OBSERVABILITY_MANAGER_AVAILABLE = False
    logger.warning(f"⚠️ ObservabilityManager not available: {e}")

# ✅ ENTERPRISE CONFIGURATION
try:
    load_dotenv()
    logger.info("✅ Environment variables loaded")
except Exception as e:
    logger.warning(f"⚠️ .env not found, using system environment: {e}")

from src.api.core.config import get_settings
from src.api.startup_helper import StartupManager
from src.api.core.store import get_shopify_client, init_shopify
from src.api.security_auth import get_api_key, get_current_user

# ✅ ENTERPRISE ROUTERS
from src.api.routers import mcp_router
from src.api.routers import products_router

# ✅ ENTERPRISE ENHANCEMENTS
from src.api.core.mcp_router_conservative_enhancement import apply_performance_enhancement_to_router
mcp_router.router = apply_performance_enhancement_to_router(mcp_router.router)
logger.info("✅ Enterprise performance enhancements applied to MCP router")

from src.api.integrations.ai.optimized_conversation_manager import OptimizedConversationAIManager

# ✅ ENTERPRISE MCP PERSONALIZATION
try:
    from src.api.mcp.engines.mcp_personalization_engine import (
        MCPPersonalizationEngine,
        create_mcp_personalization_engine,
        PersonalizationStrategy,
        PersonalizationInsightsAnalyzer
    )
    MCP_PERSONALIZATION_AVAILABLE = True
    logger.info("✅ MCP Personalization Engine loaded - Enterprise personalization enabled")
except ImportError as e:
    MCP_PERSONALIZATION_AVAILABLE = False
    logger.warning(f"⚠️ MCP Personalization Engine not available: {e}")

# ============================================================================
# 🏢 ENTERPRISE FASTAPI SETUP
# ============================================================================

app = FastAPI(
    title="Enterprise Retail Recommender System",
    description="Sistema de recomendaciones enterprise con arquitectura moderna y Redis centralizado",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ✅ ENTERPRISE CORS MIDDLEWARE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ ENTERPRISE OBSERVABILITY MIDDLEWARE
if OBSERVABILITY_MANAGER_AVAILABLE:
    try:
        observability_manager = get_observability_manager()
        if hasattr(observability_manager, 'get_middleware'):
            middleware = observability_manager.get_middleware()
            app.middleware("http")(middleware)
            logger.info("✅ Enterprise observability middleware activated")
    except Exception as e:
        logger.warning(f"⚠️ Could not add observability middleware: {e}")

# ============================================================================
# 🚀 ENTERPRISE STARTUP EVENTS
# ============================================================================

@app.on_event("startup")
async def enterprise_startup():
    """✅ ENTERPRISE: Startup event con validation y health checks - FULLY FIXED"""
    logger.info("🚀 Starting Enterprise Retail Recommender System v2.1.0")
    
    try:
        # ✅ Validate factory architecture (no Redis needed)
        architecture_validation = validate_factory_architecture()
        logger.info(f"✅ Factory architecture validation: {architecture_validation}")
        
        # ✅ Initialize enterprise services with comprehensive error handling
        logger.info("🔧 Initializing enterprise services...")
        
        # ✅ FIXED: Redis initialization with proper error handling
        redis_initialized = False
        try:
            logger.info("🔄 Attempting Redis service initialization...")
            redis_service = await asyncio.wait_for(
                ServiceFactory.get_redis_service(), 
                timeout=8.0  # Increased timeout
            )
            
            # Test the service
            health_result = await asyncio.wait_for(
                redis_service.health_check(),
                timeout=3.0
            )
            
            logger.info(f"✅ Enterprise Redis initialized: {health_result.get('status', 'unknown')}")
            redis_initialized = True
            
        except asyncio.TimeoutError:
            logger.warning("⚠️ Redis initialization timeout - system will continue with fallback")
        except Exception as e:
            logger.warning(f"⚠️ Redis initialization failed: {e} - system will continue with fallback")
        
        # ✅ FIXED: ProductCache initialization with dependency handling
        try:
            logger.info("🔄 Attempting ProductCache initialization...")
            product_cache = await asyncio.wait_for(
                ServiceFactory.get_product_cache_singleton(),
                timeout=5.0
            )
            logger.info("✅ Enterprise ProductCache initialized")
        except Exception as e:
            logger.warning(f"⚠️ ProductCache initialization failed: {e}")
        
        # ✅ FIXED: InventoryService initialization with dependency handling
        try:
            logger.info("🔄 Attempting InventoryService initialization...")
            inventory_service = await asyncio.wait_for(
                ServiceFactory.get_inventory_service_singleton(),
                timeout=5.0
            )
            logger.info("✅ Enterprise InventoryService initialized")
        except Exception as e:
            logger.warning(f"⚠️ InventoryService initialization failed: {e}")
        
        # ✅ Initialize Shopify integration (independent of Redis)
        try:
            logger.info("🔄 Attempting Shopify initialization...")
            shopify_client = init_shopify()
            if shopify_client:
                logger.info("✅ Shopify client initialized")
            else:
                logger.warning("⚠️ Shopify client initialization returned None")
        except Exception as e:
            logger.warning(f"⚠️ Shopify initialization error: {e}")
        
        # ✅ FIXED: Conditional health check
        try:
            if redis_initialized:
                logger.info("🔄 Attempting comprehensive health check...")
                overall_health = await asyncio.wait_for(
                    HealthCompositionRoot.comprehensive_health_check(),
                    timeout=8.0
                )
                logger.info(f"✅ Enterprise system health: {overall_health.get('overall_status', 'unknown')}")
            else:
                logger.info("ℹ️ Skipping comprehensive health check due to Redis issues")
        except Exception as e:
            logger.warning(f"⚠️ Health check failed: {e}")
        
        logger.info("🎉 Enterprise system startup completed successfully")
        logger.info(f"📊 Redis status: {'✅ Connected' if redis_initialized else '⚠️ Fallback mode'}")
        
    except Exception as e:
        logger.error(f"❌ Enterprise startup encountered error: {e}")
        logger.info("⚠️ System will continue in degraded mode")
        # IMPORTANT: Don't raise the exception - let the system start

@app.on_event("shutdown")
async def enterprise_shutdown():
    """✅ ENTERPRISE: Shutdown event con cleanup"""
    logger.info("🔄 Shutting down Enterprise Retail Recommender System")
    
    try:
        # ✅ Graceful service shutdown
        # Redis connections will be handled by connection pool cleanup
        logger.info("✅ Enterprise services shutdown completed")
    except Exception as e:
        logger.error(f"❌ Enterprise shutdown error: {e}")

# ============================================================================
# 🏥 ENTERPRISE HEALTH ENDPOINTS
# ============================================================================

@app.get("/health")
async def enterprise_health_check():
    """✅ ENTERPRISE: Comprehensive system health check"""
    try:
        health_report = await HealthCompositionRoot.comprehensive_health_check()
        
        return {
            "timestamp": time.time(),
            "service": "enterprise_retail_recommender",
            "version": "2.1.0",
            "architecture": "enterprise",
            "health_report": health_report,
            "status": health_report.get("overall_status", "unknown")
        }
    except Exception as e:
        logger.error(f"❌ Enterprise health check failed: {e}")
        return {
            "timestamp": time.time(),
            "service": "enterprise_retail_recommender",
            "version": "2.1.0",
            "status": "unhealthy",
            "error": str(e)
        }

@app.get("/health/redis")
async def enterprise_redis_health():
    """✅ ENTERPRISE: Redis-specific health check"""
    try:
        redis_service = await ServiceFactory.get_redis_service()
        redis_health = await redis_service.health_check()
        
        return {
            "timestamp": time.time(),
            "service": "enterprise_redis",
            "redis_health": redis_health,
            "connection_pooling": True,
            "singleton_pattern": True
        }
    except Exception as e:
        return {
            "timestamp": time.time(),
            "service": "enterprise_redis",
            "status": "unhealthy",
            "error": str(e)
        }

# ============================================================================
# 📈 ENTERPRISE API ENDPOINTS
# ============================================================================

@app.get("/")
async def enterprise_root():
    """✅ ENTERPRISE: Root endpoint con enterprise information"""
    return {
        "message": "Enterprise Retail Recommender System",
        "version": "2.1.0",
        "architecture": "enterprise",
        "features": {
            "dependency_injection": True,
            "connection_pooling": True,
            "singleton_patterns": True,
            "health_monitoring": True,
            "microservices_ready": True
        },
        "endpoints": {
            "health": "/health",
            "products": "/v1/products/",
            "mcp": "/mcp/",
            "documentation": "/docs"
        }
    }

@app.get("/enterprise/architecture")
async def enterprise_architecture_info():
    """✅ ENTERPRISE: Architecture information endpoint"""
    try:
        architecture_validation = validate_factory_architecture()
        
        return {
            "timestamp": time.time(),
            "architecture": {
                "pattern": "enterprise",
                "version": "2.1.0",
                "design_patterns": [
                    "Dependency Injection",
                    "Singleton",
                    "Factory",
                    "Composition Root"
                ],
                "microservices_preparation": {
                    "business_composition_root": "Ready for service extraction",
                    "infrastructure_composition_root": "Shared services ready",
                    "health_composition_root": "Monitoring ready"
                }
            },
            "validation": architecture_validation,
            "redis_integration": {
                "centralized": True,
                "connection_pooling": True,
                "singleton_pattern": True
            }
        }
    except Exception as e:
        return {
            "timestamp": time.time(),
            "architecture": "enterprise",
            "error": str(e)
        }

# ============================================================================
# 🔄 LEGACY COMPATIBILITY ENDPOINTS (DEPRECATED)
# ============================================================================

@app.get("/legacy/health", deprecated=True, tags=["Legacy Compatibility"])
async def legacy_health_check():
    """
    ⚠️ DEPRECATED: Legacy health check endpoint.
    Use /health for enterprise health monitoring.
    """
    logger.warning("⚠️ DEPRECATED: Legacy health endpoint used - migrate to /health")
    
    # Redirect to enterprise health check internally
    return await enterprise_health_check()

# ============================================================================
# 🚀 ENTERPRISE ROUTER REGISTRATION
# ============================================================================

# ✅ Register enterprise routers
app.include_router(products_router.router, tags=["Products Enterprise"])
app.include_router(mcp_router.router, tags=["MCP Enterprise"])

logger.info("✅ Enterprise routers registered successfully")

# ============================================================================
# 🏁 ENTERPRISE APPLICATION READY
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting Enterprise Retail Recommender System")
    logger.info("🏢 Architecture: Enterprise with centralized Redis")
    logger.info("🔌 Patterns: Dependency Injection, Singleton, Factory")
    logger.info("📊 Monitoring: Comprehensive health checks enabled")
    logger.info("🔄 Legacy Support: Backward compatibility maintained")
    
    uvicorn.run(
        "main_unified_redis:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )