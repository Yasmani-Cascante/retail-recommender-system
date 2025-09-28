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

from src.api.factories.factories import RecommenderFactory

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

# ✅ Variables globales para compatibilidad con endpoints legacy
settings = None
startup_manager = None  
tfidf_recommender = None
retail_recommender = None
hybrid_recommender = None
start_time = time.time()  # Para uptime tracking
redis_client = None  # Para backward compatibility
product_cache = None  # Para backward compatibility

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
async def enterprise_startup_enhanced():
    """✅ ENTERPRISE: Startup event con variables legacy y enterprise patterns"""
    global settings, startup_manager, tfidf_recommender, retail_recommender
    global hybrid_recommender, redis_client, product_cache
    
    logger.info("🚀 Starting Enterprise Retail Recommender System v2.1.0 - Enhanced")
    
    try:
        # ✅ PASO 1: Inicializar configuración global
        settings = get_settings()
        logger.info("✅ Global settings initialized")
        
        # ✅ PASO 2: Inicializar StartupManager 
        startup_manager = StartupManager(startup_timeout=settings.startup_timeout)
        logger.info("✅ StartupManager initialized")
        
        # ✅ PASO 3: Validate factory architecture (no Redis needed)
        architecture_validation = validate_factory_architecture()
        logger.info(f"✅ Factory architecture validation: {architecture_validation}")
        
        # ✅ PASO 4: Initialize enterprise services with comprehensive error handling
        logger.info("🔧 Initializing enterprise services...")
        
        # ✅ PASO 4.1: Redis initialization with proper error handling
        redis_initialized = False
        try:
            logger.info("🔄 Attempting Redis service initialization...")
            redis_service = await asyncio.wait_for(
                ServiceFactory.get_redis_service(), 
                timeout=8.0
            )
            
            # Test the service
            health_result = await asyncio.wait_for(
                redis_service.health_check(),
                timeout=3.0
            )
            
            logger.info(f"✅ Enterprise Redis initialized: {health_result.get('status', 'unknown')}")
            redis_initialized = True
            
            # ✅ COMPATIBILIDAD: Obtener redis_client para backward compatibility
            if hasattr(redis_service, '_client'):
                redis_client = redis_service._client
                logger.info("✅ Redis client extracted for legacy compatibility")
            
        except asyncio.TimeoutError:
            logger.warning("⚠️ Redis initialization timeout - system will continue with fallback")
        except Exception as e:
            logger.warning(f"⚠️ Redis initialization failed: {e} - system will continue with fallback")
        
        # ✅ PASO 4.2: ProductCache initialization with dependency handling
        try:
            logger.info("🔄 Attempting ProductCache initialization...")
            # product_cache = await asyncio.wait_for(
            #     ServiceFactory.get_product_cache_singleton(),
            #     timeout=5.0
            # )
            product_cache = await ServiceFactory.create_product_cache(
                local_catalog=tfidf_recommender  # ✅ PASS TRAINED RECOMMENDER
            )
            logger.info("✅ Enterprise ProductCache initialized")
        except Exception as e:
            logger.warning(f"⚠️ ProductCache initialization failed: {e}")
            product_cache = None
        
        # ✅ PASO 5: NUEVO - Inicializar componentes de recomendación legacy
        logger.info("🔧 Initializing recommendation components for legacy compatibility...")
        
        try:
            # ✅ PASO 5.1: Crear recomendadores usando fábricas
            tfidf_recommender = RecommenderFactory.create_tfidf_recommender()
            retail_recommender = RecommenderFactory.create_retail_recommender()
            logger.info("✅ TF-IDF and Retail recommenders created")
            
            # ✅ PASO 5.2: Crear recomendador híbrido
            hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
                tfidf_recommender, 
                retail_recommender,
                product_cache=product_cache  # Usar enterprise ProductCache si está disponible
            )
            logger.info("✅ Hybrid recommender created with enterprise integration")
            
        except Exception as e:
            logger.error(f"❌ Error creating recommendation components: {e}")
            # Crear componentes mínimos para evitar crashes
            try:
                tfidf_recommender = RecommenderFactory.create_tfidf_recommender()
                retail_recommender = RecommenderFactory.create_retail_recommender()
                hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
                    tfidf_recommender, retail_recommender
                )
                logger.info("✅ Fallback recommendation components created")
            except Exception as fallback_error:
                logger.error(f"❌ Failed to create fallback components: {fallback_error}")
        
        # ✅ PASO 6: Initialize Shopify integration (independent of Redis)
        try:
            logger.info("🔄 Attempting Shopify initialization...")
            shopify_client = init_shopify()
            if shopify_client:
                logger.info("✅ Shopify client initialized")
            else:
                logger.warning("⚠️ Shopify client initialization returned None")
        except Exception as e:
            logger.warning(f"⚠️ Shopify initialization error: {e}")
        
        # ✅ PASO 7: Registrar componentes en StartupManager para carga asíncrona
        try:
            if startup_manager and tfidf_recommender:
                startup_manager.register_component(
                    name="tfidf_recommender",
                    # loader=lambda: tfidf_recommender.load() if hasattr(tfidf_recommender, 'load') else True,
                    loader=load_recommender,
                    # required=False  # No crítico para arranque
                    required=True
                )
                logger.info("✅ TF-IDF recommender registered in StartupManager")
        except Exception as e:
            logger.warning(f"⚠️ StartupManager registration error: {e}")
        
        # ✅ PASO 8: Health check conditional
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
        
        # ✅ PASO 9: REPORTE FINAL DE ESTADO
        logger.info("📋 ENHANCED STARTUP SUMMARY:")
        logger.info(f"   ✅ Settings: {'Loaded' if settings else 'Error'}")
        logger.info(f"   ✅ StartupManager: {'Active' if startup_manager else 'Error'}")
        logger.info(f"   ✅ TF-IDF Recommender: {'Ready' if tfidf_recommender else 'Error'}")
        logger.info(f"   ✅ Retail Recommender: {'Ready' if retail_recommender else 'Error'}")
        logger.info(f"   ✅ Hybrid Recommender: {'Ready' if hybrid_recommender else 'Error'}")
        logger.info(f"   ✅ Redis: {'Connected' if redis_initialized else 'Fallback'}")
        logger.info(f"   ✅ ProductCache: {'Available' if product_cache else 'Fallback'}")
        
        logger.info("🎉 Enterprise enhanced startup completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Enterprise startup encountered error: {e}")
        logger.info("⚠️ System will continue in degraded mode")
        
        # ✅ EMERGENCY FALLBACK: Crear componentes mínimos
        try:
            if not settings:
                settings = get_settings()
            if not startup_manager:
                startup_manager = StartupManager()
            logger.info("✅ Emergency fallback components created")
        except Exception as emergency_error:
            logger.error(f"❌ Emergency fallback failed: {emergency_error}")

    # ✅ EJECUTAR STARTUP MANAGER
    if startup_manager:
        try:
            logger.info("⏳ Iniciando carga de componentes en segundo plano...")
            loading_task = asyncio.create_task(startup_manager.start_loading())
            
            await asyncio.wait_for(loading_task, timeout=60.0)
            logger.info("✅ Carga de componentes completada")
            
            # Verificar estado del TF-IDF
            if tfidf_recommender and hasattr(tfidf_recommender, 'loaded'):
                logger.info(f"✅ TF-IDF Status: loaded={tfidf_recommender.loaded}")
            
        except asyncio.TimeoutError:
            logger.warning("⚠️ Timeout en carga de componentes - continuando")
        except Exception as e:
            logger.error(f"❌ Error en startup manager: {e}")
                
# async def enterprise_startup():
#     """✅ ENTERPRISE: Startup event con validation y health checks - FULLY FIXED"""
#     logger.info("🚀 Starting Enterprise Retail Recommender System v2.1.0")
    
#     try:
#         # ✅ Validate factory architecture (no Redis needed)
#         architecture_validation = validate_factory_architecture()
#         logger.info(f"✅ Factory architecture validation: {architecture_validation}")
        
#         # ✅ Initialize enterprise services with comprehensive error handling
#         logger.info("🔧 Initializing enterprise services...")
        
#         # ✅ FIXED: Redis initialization with proper error handling
#         redis_initialized = False
#         try:
#             logger.info("🔄 Attempting Redis service initialization...")
#             redis_service = await asyncio.wait_for(
#                 ServiceFactory.get_redis_service(), 
#                 timeout=8.0  # Increased timeout
#             )
            
#             # Test the service
#             health_result = await asyncio.wait_for(
#                 redis_service.health_check(),
#                 timeout=3.0
#             )
            
#             logger.info(f"✅ Enterprise Redis initialized: {health_result.get('status', 'unknown')}")
#             redis_initialized = True
            
#         except asyncio.TimeoutError:
#             logger.warning("⚠️ Redis initialization timeout - system will continue with fallback")
#         except Exception as e:
#             logger.warning(f"⚠️ Redis initialization failed: {e} - system will continue with fallback")
        
#         # ✅ FIXED: ProductCache initialization with dependency handling
#         try:
#             logger.info("🔄 Attempting ProductCache initialization...")
#             product_cache = await asyncio.wait_for(
#                 ServiceFactory.get_product_cache_singleton(),
#                 timeout=5.0
#             )
#             logger.info("✅ Enterprise ProductCache initialized")
#         except Exception as e:
#             logger.warning(f"⚠️ ProductCache initialization failed: {e}")
        
#         # ✅ FIXED: InventoryService initialization with dependency handling
#         try:
#             logger.info("🔄 Attempting InventoryService initialization...")
#             inventory_service = await asyncio.wait_for(
#                 ServiceFactory.get_inventory_service_singleton(),
#                 timeout=5.0
#             )
#             logger.info("✅ Enterprise InventoryService initialized")
#         except Exception as e:
#             logger.warning(f"⚠️ InventoryService initialization failed: {e}")
        
#         # ✅ Initialize Shopify integration (independent of Redis)
#         try:
#             logger.info("🔄 Attempting Shopify initialization...")
#             shopify_client = init_shopify()
#             if shopify_client:
#                 logger.info("✅ Shopify client initialized")
#             else:
#                 logger.warning("⚠️ Shopify client initialization returned None")
#         except Exception as e:
#             logger.warning(f"⚠️ Shopify initialization error: {e}")
        
#         # ✅ FIXED: Conditional health check
#         try:
#             if redis_initialized:
#                 logger.info("🔄 Attempting comprehensive health check...")
#                 overall_health = await asyncio.wait_for(
#                     HealthCompositionRoot.comprehensive_health_check(),
#                     timeout=8.0
#                 )
#                 logger.info(f"✅ Enterprise system health: {overall_health.get('overall_status', 'unknown')}")
#             else:
#                 logger.info("ℹ️ Skipping comprehensive health check due to Redis issues")
#         except Exception as e:
#             logger.warning(f"⚠️ Health check failed: {e}")
        
#         # ✅ FINAL STATE VERIFICATION - Check actual Redis status
#         final_redis_status = "unknown"
#         try:
#             # Verify actual Redis status through ServiceFactory
#             redis_service = await asyncio.wait_for(
#                 ServiceFactory.get_redis_service(),
#                 timeout=3.0  # Quick check
#             )
#             health_result = await redis_service.health_check()
#             final_redis_status = health_result.get('status', 'unknown')
            
#             # Update redis_initialized based on actual status
#             if final_redis_status in ['healthy', 'connected', 'operational']:
#                 redis_initialized = True
#                 logger.info("✅ Final Redis status verification: Redis is healthy")
#             else:
#                 logger.info(f"⚠️ Final Redis status verification: {final_redis_status}")
                
#         except Exception as e:
#             logger.warning(f"⚠️ Final Redis status check failed: {e}")
        
#         logger.info("🎉 Enterprise system startup completed successfully")
#         logger.info(f"📊 Redis status: {'✅ Connected' if redis_initialized else '⚠️ Fallback mode'}")
#         logger.info(f"🔍 Final Redis verification: {final_redis_status}")
        
#     except Exception as e:
#         logger.error(f"❌ Enterprise startup encountered error: {e}")
#         logger.info("⚠️ System will continue in degraded mode")
#         # IMPORTANT: Don't raise the exception - let the system start

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
# 🚀 Core Business Endpoints
# ============================================================================

@app.get("/v1/recommendations/{product_id}", response_model=Dict)
async def get_recommendations(
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene recomendaciones basadas en un producto.
    Requiere autenticación mediante API key.
    """
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    # Obtener recomendaciones
    try:
        # Actualizar peso de contenido en el recomendador híbrido
        hybrid_recommender.content_weight = content_weight
        
        # Obtener producto específico
        client = get_shopify_client()
        product = None
        
        if client:
            # Obtener productos
            all_products = client.get_products()
            
            # Encontrar el producto específico
            product = next(
                (p for p in all_products if str(p.get('id')) == str(product_id)),
                None
            )
        
        if not product and tfidf_recommender.loaded:
            # Intentar obtener producto del recomendador
            product = tfidf_recommender.get_product_by_id(product_id)
        
        if not product:
            # Cambiar a HTTPException para mantener consistencia
            raise HTTPException(
                status_code=404,
                detail=f"Product ID {product_id} not found"
            )
            
        # Obtener recomendaciones del recomendador híbrido
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id or "anonymous",
            product_id=str(product_id),
            n_recommendations=n
        )
        
        # Calcular tiempo de procesamiento
        processing_time_ms = (time.time() - start_processing) * 1000
        
        # Registrar métricas si están habilitadas
        if settings.metrics_enabled and 'recommendation_metrics' in globals():
            from src.api.core.metrics import recommendation_metrics
            recommendation_metrics.record_recommendation_request(
                request_data={
                    "product_id": product_id,
                    "user_id": user_id or "anonymous",
                    "n": n,
                    "content_weight": content_weight
                },
                recommendations=recommendations,
                response_time_ms=processing_time_ms,
                user_id=user_id or "anonymous",
                product_id=product_id
            )
        
        return {
            "product": {
                "id": product.get('id'),
                "title": product.get('title')
            },
            "recommendations": recommendations,
            "metadata": {
                "content_weight": content_weight,
                "total_recommendations": len(recommendations),
                "source": "hybrid_tfidf_redis",
                "took_ms": processing_time_ms
            }
        }
    except HTTPException:
        # Re-lanzar HTTPExceptions directamente para mantener el código y mensaje
        raise
    except ValueError as e:
        # Convertir ValueError a HTTPException 404
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error obteniendo recomendaciones: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/recommendations/user/{user_id}", response_model=Dict)
async def get_user_recommendations(
    user_id: str,
    n: Optional[int] = Query(5, gt=0, le=20),
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene recomendaciones personalizadas para un usuario.
    Requiere autenticación mediante API key.
    """
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    try:
        client = get_shopify_client()
        
        logger.info(f"Obteniendo recomendaciones para usuario {user_id}")
        
        # Obtener órdenes del usuario si está disponible Shopify
        user_orders = []
        if client:
            user_orders = client.get_orders_by_customer(user_id)
            
            if user_orders:
                logger.info(f"Se encontraron {len(user_orders)} órdenes para el usuario {user_id}")
                
                # Registrar eventos de usuario basados en órdenes
                try:
                    await retail_recommender.process_shopify_orders(user_orders, user_id)
                    logger.info(f"Eventos de órdenes procesados para usuario {user_id}")
                except Exception as e:
                    logger.error(f"Error procesando órdenes: {e}")
            else:
                logger.info(f"No se encontraron órdenes para el usuario {user_id}")
        
        # Obtener recomendaciones
        recommendations = await hybrid_recommender.get_recommendations(
            user_id=user_id,
            n_recommendations=n
        )
        
        # Calcular tiempo de procesamiento
        processing_time_ms = (time.time() - start_processing) * 1000
        
        # Registrar métricas si están habilitadas
        if settings.metrics_enabled and 'recommendation_metrics' in globals():
            from src.api.core.metrics import recommendation_metrics
            recommendation_metrics.record_recommendation_request(
                request_data={
                    "user_id": user_id,
                    "n": n
                },
                recommendations=recommendations,
                response_time_ms=processing_time_ms,
                user_id=user_id,
                product_id=None
            )
        
        return {
            "recommendations": recommendations,
            "metadata": {
                "user_id": user_id,
                "total_recommendations": len(recommendations),
                "total_orders": len(user_orders) if user_orders else 0,
                "source": "hybrid_tfidf_user_redis",
                "took_ms": processing_time_ms
            }
        }
    except Exception as e:
        logger.error(f"Error obteniendo recomendaciones para usuario {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo recomendaciones: {str(e)}"
        )

@app.post("/v1/events/user/{user_id}")
async def record_user_event(
    user_id: str,
    event_type: str = Query(..., description="Tipo de evento (detail-page-view, add-to-cart, purchase-complete, etc.)"),
    product_id: Optional[str] = Query(None, description="ID del producto relacionado con el evento"),
    purchase_amount: Optional[float] = Query(None, description="Monto de la compra para eventos de tipo purchase-complete"),
    current_user: str = Depends(get_current_user)
):
    """
    Registra eventos de usuario para mejorar las recomendaciones futuras.
    Requiere autenticación mediante API key.
    
    Tipos de eventos válidos según Google Cloud Retail API:
    - add-to-cart: Cuando un usuario añade un producto al carrito
    - category-page-view: Cuando un usuario ve páginas especiales, como ofertas o promociones
    - detail-page-view: Cuando un usuario ve la página de detalle de un producto
    - home-page-view: Cuando un usuario visita la página de inicio
    - purchase-complete: Cuando un usuario completa una compra
    - search: Cuando un usuario realiza una búsqueda
    
    El sistema también acepta nombres alternativos simplificados:
    - 'view' o 'detail-page' → detail-page-view
    - 'add' o 'cart' → add-to-cart
    - 'buy', 'purchase' o 'checkout' → purchase-complete
    - 'home' → home-page-view
    - 'category' o 'promo' → category-page-view
    """
    try:
        # Validar product_id si está presente
        if product_id:
            # Verificar si es un ID existente en el catálogo
            if tfidf_recommender.loaded and tfidf_recommender.product_data:
                product_exists = any(str(p.get('id', '')) == product_id for p in tfidf_recommender.product_data)
                if not product_exists:
                    # Si el ID no existe, pero es un ID de desarrollo (empieza con 'prod_test_'), permitirlo
                    if not product_id.startswith(('test_', 'prod_test_', '123')):
                        logger.warning(f"ID de producto no encontrado en el catálogo: {product_id}")
                        # Aún permitimos el evento, pero advertimos
            
        logger.info(f"Registrando evento de usuario: {user_id}, tipo: {event_type}, producto: {product_id or 'N/A'}")
        
        # Registrar el evento
        result = await hybrid_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id,
            purchase_amount=purchase_amount
        )
        
        # Añadir información adicional a la respuesta
        if result.get("status") == "success":
            result["detail"] = {
                "user_id": user_id,
                "event_type": result.get("event_type", event_type),
                "product_id": product_id,
                "timestamp": datetime.utcnow().isoformat(),
                "note": "El evento fue registrado correctamente y ayudará a mejorar las recomendaciones futuras."
            }
            
            # Registrar interacción en métricas si están habilitadas
            if settings.metrics_enabled and 'recommendation_metrics' in globals():
                from src.api.core.metrics import recommendation_metrics
                recommendation_metrics.record_user_interaction(
                    user_id=user_id,
                    product_id=product_id,
                    event_type=event_type,
                    recommendation_id=None  # No podemos saber si vino de una recomendación sin contexto adicional
                )
        
        return result
    except Exception as e:
        logger.error(f"Error registrando evento de usuario: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error al registrar el evento: {str(e)}. Asegúrate de usar un tipo de evento válido (detail-page-view, add-to-cart, purchase-complete, category-page-view, home-page-view, search)."
        )

@app.get("/v1/customers/")
async def get_customers(
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene la lista de clientes de Shopify.
    Requiere autenticación mediante API key.
    """
    try:
        client = get_shopify_client()
        if not client:
            raise HTTPException(status_code=500, detail="Shopify client not initialized")
            
        customers = client.get_customers()
        
        if not customers:
            logger.warning("No customers found")
            return {
                "total": 0,
                "customers": []
            }
            
        return {
            "total": len(customers),
            "customers": customers
        }
    except Exception as e:
        logger.error(f"Error fetching customers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/v1/products/category/{category}")
async def get_products_by_category(
    category: str,
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene productos filtrados por categoría.
    Requiere autenticación mediante API key.
    """
    try:
        client = get_shopify_client()
        all_products = []
        
        if client:
            logger.info(f"Obteniendo productos de Shopify para categoría: {category}")
            all_products = client.get_products()
        elif tfidf_recommender.loaded and tfidf_recommender.product_data:
            logger.info(f"Obteniendo productos del recomendador para categoría: {category}")
            all_products = tfidf_recommender.product_data
        else:
            raise HTTPException(
                status_code=503,
                detail="No hay productos disponibles. El servicio está cargando."
            )
            
        logger.info(f"Filtrando {len(all_products)} productos por categoría: {category}")
        
        # Filtrar por categoría (product_type en Shopify)
        category_products = [
            p for p in all_products 
            if p.get("product_type", "").lower() == category.lower()
        ]
        
        logger.info(f"Encontrados {len(category_products)} productos en categoría {category}")
        
        if not category_products:
            raise HTTPException(
                status_code=404,
                detail=f"No products found in category: {category}"
            )
        return category_products
    except HTTPException:
        # Re-lanzar excepciones HTTP que ya hemos creado
        raise
    except Exception as e:
        logger.error(f"Error en búsqueda por categoría: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 🚀 ENTERPRISE ROUTER REGISTRATION
# ============================================================================

# ✅ Register enterprise routers
app.include_router(products_router.router, tags=["Products Enterprise"])
app.include_router(mcp_router.router, tags=["MCP Enterprise"])

logger.info("✅ Enterprise routers registered successfully")


# ============================================================================
# 🔍 HELPER FUNCTIONS ADICIONALES
# ============================================================================

# AÑADIR estas funciones helper que pueden ser requeridas por los endpoints:

async def load_shopify_products():
    """Carga productos desde Shopify (compatibilidad legacy)."""
    try:
        client = init_shopify()
        if client:
            products = client.get_products()
            logger.info(f"Cargados {len(products)} productos desde Shopify")
            return products
        else:
            logger.warning("No se pudo inicializar el cliente de Shopify")
            return await load_sample_data()
    except Exception as e:
        logger.error(f"Error cargando productos desde Shopify: {e}")
        return await load_sample_data()

async def load_sample_data():
    """Carga datos de muestra para el recomendador (compatibilidad legacy)."""
    try:
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        if SAMPLE_PRODUCTS:
            logger.info(f"Cargados {len(SAMPLE_PRODUCTS)} productos de muestra")
            return SAMPLE_PRODUCTS
    except Exception as e:
        logger.warning(f"No se pudieron cargar productos de muestra: {e}")
    
    # Datos mínimos de fallback
    minimal_products = [
        {
            "id": "product1",
            "title": "Camiseta básica",
            "body_html": "Camiseta de algodón de alta calidad.",
            "product_type": "Ropa"
        },
        {
            "id": "product2", 
            "title": "Pantalón vaquero",
            "body_html": "Pantalón vaquero clásico de corte recto.",
            "product_type": "Ropa"
        }
    ]
    logger.info(f"Usando {len(minimal_products)} productos mínimos de muestra")
    return minimal_products

async def load_recommender():
    """Carga y entrena el recomendador TF-IDF (compatibilidad legacy)."""
    global tfidf_recommender, retail_recommender
    
    try:
        if not tfidf_recommender:
            logger.warning("⚠️ tfidf_recommender not initialized in load_recommender")
            return False
            
        # Intentar cargar modelo pre-entrenado
        if os.path.exists("data/tfidf_model.pkl"):
            success = await tfidf_recommender.load()
            if success:
                logger.info("Modelo TF-IDF cargado correctamente desde archivo")
                return True
        
        # Si no existe, entrenar con datos
        products = await load_shopify_products()
        if not products:
            logger.error("No se pudieron cargar productos para entrenamiento")
            return False
            
        logger.info(f"Entrenando recomendador TF-IDF con {len(products)} productos")
        success = await tfidf_recommender.fit(products)
        
        if success:
            logger.info("Recomendador TF-IDF entrenado correctamente")
            
            # Importar productos a Google Cloud Retail API
            if retail_recommender:
                try:
                    logger.info("Importando productos a Google Cloud Retail API")
                    import_result = await retail_recommender.import_catalog(products)
                    logger.info(f"Resultado de importación: {import_result}")
                except Exception as e:
                    logger.error(f"Error importando productos a Google Cloud Retail API: {e}")
        else:
            logger.error("Error entrenando recomendador TF-IDF")
            
        return success
    except Exception as e:
        logger.error(f"Error en load_recommender: {e}")
        return False

# ============================================================================
# 📊 HEALTH CHECK COMPATIBILITY
# ============================================================================

# AÑADIR endpoint de health check que incluya variables legacy:

@app.get("/health/legacy")
async def legacy_compatibility_health():
    """Health check que incluye estado de variables legacy"""
    
    global settings, startup_manager, tfidf_recommender, retail_recommender
    global hybrid_recommender, redis_client, product_cache
    
    return {
        "timestamp": time.time(),
        "service": "enterprise_with_legacy_compatibility",
        "version": "2.1.0",
        "legacy_components": {
            "settings": settings is not None,
            "startup_manager": startup_manager is not None,
            "tfidf_recommender": tfidf_recommender is not None,
            "retail_recommender": retail_recommender is not None,
            "hybrid_recommender": hybrid_recommender is not None,
            "redis_client": redis_client is not None,
            "product_cache": product_cache is not None
        },
        "uptime_seconds": time.time() - start_time,
        "ready_for_legacy_endpoints": all([
            settings is not None,
            startup_manager is not None,
            hybrid_recommender is not None
        ])
    }


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