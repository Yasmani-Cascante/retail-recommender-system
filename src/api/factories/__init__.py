# src/api/factories/__init__.py
"""
Enterprise Factory Architecture
==============================

Módulo unificado de fábricas enterprise para creación consistente de servicios
con dependency injection unificada y gestión de ciclo de vida.

Architecture:
- Business Domain Factories: Core business logic components
- Infrastructure Factories: Infrastructure services (Redis, Cache, etc.)
- Composition Roots: Microservices preparation patterns

Author: Senior Architecture Team
Version: 2.1.0 - Unified Factory Architecture
"""

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# 🏗️ ENTERPRISE INFRASTRUCTURE FACTORIES
# ============================================================================

from .service_factory import (
    ServiceFactory,
    get_inventory_service,
    get_product_cache,
    get_availability_checker,
    health_check_services
)

# ============================================================================
# 🚀 BUSINESS DOMAIN FACTORIES
# ============================================================================

# ✅ CORRECTED IMPORT PATH - Now importing from same directory
try:
    from .factories import RecommenderFactory, MCPFactory
    BUSINESS_FACTORIES_AVAILABLE = True
    logger.info("✅ Business domain factories loaded successfully")
except ImportError as e:
    # Graceful degradation si factories.py tiene problemas
    RecommenderFactory = None
    MCPFactory = None
    BUSINESS_FACTORIES_AVAILABLE = False
    logger.error(f"❌ Business domain factories not available: {e}")

# ============================================================================
# 🎯 COMPOSITION ROOTS (Microservices Preparation)
# ============================================================================

class BusinessCompositionRoot:
    """
    Composition Root for Business Domain Services
    
    Prepares business logic components for microservices extraction.
    Centralizes business domain service creation with clean dependencies.
    """
    
    @staticmethod
    async def create_recommendation_service():
        """
        Create complete recommendation service for microservices extraction
        
        Returns:
            Hybrid recommender ready for service boundary extraction
        """
        if not BUSINESS_FACTORIES_AVAILABLE:
            raise RuntimeError("Business factories not available")
            
        logger.info("🎯 Creating recommendation service via composition root")
        
        # Create components using business factory
        content_recommender = await RecommenderFactory.create_tfidf_recommender_async()
        retail_recommender = await RecommenderFactory.create_retail_recommender_async()
        
        # Create hybrid recommender
        hybrid_recommender = await RecommenderFactory.create_hybrid_recommender_async(
            content_recommender=content_recommender,
            retail_recommender=retail_recommender
        )
        
        logger.info("✅ Recommendation service created successfully")
        return hybrid_recommender
    
    @staticmethod
    async def create_conversation_service():
        """
        Create complete conversation service for microservices extraction
        
        Returns:
            MCP-aware service ready for conversation microservice
        """
        if not BUSINESS_FACTORIES_AVAILABLE:
            raise RuntimeError("Business factories not available")
            
        logger.info("🎯 Creating conversation service via composition root")
        
        # Create MCP components
        mcp_client = await MCPFactory.create_mcp_client_async()
        
        # Create MCP recommender with integrated infrastructure
        mcp_recommender = await MCPFactory.create_mcp_recommender_async(
            mcp_client=mcp_client
        )
        
        logger.info("✅ Conversation service created successfully")
        return mcp_recommender


class InfrastructureCompositionRoot:
    """
    Composition Root for Infrastructure Services
    
    Prepares infrastructure components for shared services extraction.
    Centralizes infrastructure service creation with enterprise patterns.
    """
    
    @staticmethod
    async def create_cache_service():
        """
        Create enterprise cache service for infrastructure extraction
        
        Returns:
            ProductCache with enterprise Redis integration
        """
        logger.info("🎯 Creating cache service via composition root")
        cache_service = await ServiceFactory.get_product_cache_singleton()
        logger.info("✅ Cache service created successfully")
        return cache_service
    
    @staticmethod
    async def create_inventory_service():
        """
        Create enterprise inventory service for infrastructure extraction
        
        Returns:
            InventoryService with enterprise Redis integration
        """
        logger.info("🎯 Creating inventory service via composition root")
        inventory_service = await ServiceFactory.get_inventory_service_singleton()
        logger.info("✅ Inventory service created successfully")
        return inventory_service
    
    @staticmethod
    async def create_redis_infrastructure():
        """
        Create Redis infrastructure service for shared services extraction
        
        Returns:
            RedisService singleton ready for infrastructure microservice
        """
        logger.info("🎯 Creating Redis infrastructure via composition root")
        redis_service = await ServiceFactory.get_redis_service()
        logger.info("✅ Redis infrastructure created successfully")
        return redis_service


# ============================================================================
# 🔍 HEALTH CHECK COMPOSITION ROOT
# ============================================================================

class HealthCompositionRoot:
    """
    Composition Root for Health Monitoring
    
    Centralizes health check logic for all factory-created services.
    Prepares monitoring patterns for microservices architecture.
    """
    
    @staticmethod
    async def comprehensive_health_check():
        """
        Perform comprehensive health check across all service domains
        
        Returns:
            Complete health status for business and infrastructure services
        """
        logger.info("🔍 Starting comprehensive health check")
        
        health_report = {
            "timestamp": "2025-08-09",
            "factory_architecture": "enterprise",
            "version": "2.1.0",
            "domains": {}
        }
        
        try:
            # Infrastructure domain health
            infrastructure_health = await ServiceFactory.health_check_all_services()
            health_report["domains"]["infrastructure"] = infrastructure_health
            
            # Business domain health (if available)
            if BUSINESS_FACTORIES_AVAILABLE:
                business_health = {
                    "status": "operational",
                    "factories": {
                        "recommender_factory": "available",
                        "mcp_factory": "available"
                    }
                }
                health_report["domains"]["business"] = business_health
            else:
                health_report["domains"]["business"] = {
                    "status": "unavailable",
                    "error": "Business factories not loaded"
                }
            
            # Determine overall health
            domain_statuses = []
            for domain in health_report["domains"].values():
                if isinstance(domain, dict) and "overall_status" in domain:
                    domain_statuses.append(domain["overall_status"])
                elif isinstance(domain, dict) and "status" in domain:
                    domain_statuses.append(domain["status"])
            
            if all(status in ["healthy", "operational"] for status in domain_statuses):
                health_report["overall_status"] = "healthy"
            elif any(status in ["healthy", "operational"] for status in domain_statuses):
                health_report["overall_status"] = "degraded"
            else:
                health_report["overall_status"] = "unhealthy"
                
        except Exception as e:
            logger.error(f"❌ Comprehensive health check failed: {e}")
            health_report["overall_status"] = "unhealthy"
            health_report["error"] = str(e)
        
        logger.info(f"✅ Health check completed - Status: {health_report['overall_status']}")
        return health_report


# ============================================================================
# 📦 PUBLIC API EXPORTS
# ============================================================================

__all__ = [
    # Infrastructure Services (Enterprise)
    'ServiceFactory',
    'get_inventory_service', 
    'get_product_cache',
    'get_availability_checker',
    'health_check_services',
    
    # Business Domain Services (Core)
    'RecommenderFactory',
    'MCPFactory',
    'BUSINESS_FACTORIES_AVAILABLE',
    
    # Composition Roots (Microservices Preparation)
    'BusinessCompositionRoot',
    'InfrastructureCompositionRoot',
    'HealthCompositionRoot'
]

# ============================================================================
# 🚀 STARTUP VALIDATION
# ============================================================================

def validate_factory_architecture():
    """
    Validate that the factory architecture is properly configured
    
    Returns:
        bool: True if architecture is valid, False otherwise
    """
    validation_results = {
        "infrastructure_factories": ServiceFactory is not None,
        "business_factories": BUSINESS_FACTORIES_AVAILABLE,
        "composition_roots": True,  # Always available
    }
    
    all_valid = all(validation_results.values())
    
    if all_valid:
        logger.info("✅ Factory architecture validation successful")
    else:
        logger.warning(f"⚠️ Factory architecture validation issues: {validation_results}")
    
    return all_valid

# Auto-validate on import
validate_factory_architecture()
