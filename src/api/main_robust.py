"""
Punto de entrada principal ROBUSTO para la API del sistema de recomendaciones.

MEJORAS IMPLEMENTADAS:
1. Validación defensiva contra errores None
2. Fallback automático y regeneración de modelos
3. Circuit breakers para servicios externos
4. Logging mejorado para diagnóstico
5. Health checks granulares
6. Configuración adaptiva según recursos disponibles

Archivo: src/api/main_robust.py
"""

import os
import time
import logging
import asyncio
from dotenv import load_dotenv
from datetime import datetime
from fastapi import FastAPI, Header, Query, HTTPException, BackgroundTasks, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import math
import random

# Intentar cargar variables de entorno, pero continuar si no existe el archivo
try:
    load_dotenv()
    logging.info("Variables de entorno cargadas desde .env")
except Exception as e:
    logging.warning(f"No se pudo cargar .env, usando variables de entorno del sistema: {e}")

# Importar validación defensiva
try:
    from src.api.core.defensive_validation import DefensiveValidator, defensive_logging, CircuitBreaker
    DEFENSIVE_VALIDATION_AVAILABLE = True
    logging.info("✅ Sistema de validación defensiva cargado")
except ImportError:
    DEFENSIVE_VALIDATION_AVAILABLE = False
    logging.warning("⚠️ Sistema de validación defensiva no disponible")
    
    # Fallback: crear validadores básicos
    class DefensiveValidator:
        @staticmethod
        def safe_dict_get(data, key, default=None):
            return data.get(key, default) if data else default
        
        @staticmethod
        def safe_product_validation(product):
            return product if product else {}
    
    def defensive_logging(func):
        return func
    
    class CircuitBreaker:
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, func):
            return func

# Importar configuración centralizada
from src.api.core.config import get_settings
from src.api.factories import RecommenderFactory
from src.api.startup_helper import StartupManager
from src.api.core.store import get_shopify_client, init_shopify
from src.api.security import get_api_key, get_current_user

# Configuración de logging mejorada
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar configuración
settings = get_settings()

# Crear aplicación FastAPI
app = FastAPI(
    title="Retail Recommender API - Robust Edition",
    description="API robusta para sistema de recomendaciones de retail con validación defensiva",
    version=f"{settings.app_version}-robust"
)

# Agregar middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Variables globales para componentes
tfidf_recommender = None
retail_recommender = None
hybrid_recommender = None
redis_client = None
product_cache = None

# Circuit breakers para servicios externos
shopify_circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=30)
retail_api_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)
redis_circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=30)

# Crear gestor de arranque
startup_manager = StartupManager(startup_timeout=settings.startup_timeout)

# Variables para uptime y health
start_time = time.time()
system_health = {
    "components": {},
    "last_check": None,
    "degraded_mode": False,
    "available_features": []
}

# Modelos de datos
class HealthStatus(BaseModel):
    status: str = Field(description="Estado general del servicio")
    components: Dict[str, Any] = Field(description="Estado de los componentes")
    uptime_seconds: float = Field(description="Tiempo de funcionamiento en segundos")
    degraded_mode: bool = Field(default=False, description="Si el sistema está en modo degradado")
    available_features: List[str] = Field(default=[], description="Características disponibles")

# Funciones auxiliares robustas
@defensive_logging
@shopify_circuit_breaker
async def load_shopify_products():
    """Carga productos desde Shopify con circuit breaker."""
    try:
        client = init_shopify()
        if client:
            products = client.get_products()
            if products:
                # Validar productos defensivamente
                validated_products = []
                for product in products:
                    validated = DefensiveValidator.safe_product_validation(product)
                    if validated.get("id"):  # Solo incluir productos con ID válido
                        validated_products.append(validated)
                
                logger.info(f"✅ Cargados y validados {len(validated_products)} productos desde Shopify")
                return validated_products
            else:
                logger.warning("⚠️ Shopify devolvió lista vacía de productos")
                return await load_sample_data()
        else:
            logger.warning("⚠️ No se pudo inicializar cliente Shopify")
            return await load_sample_data()
    except Exception as e:
        logger.error(f"❌ Error cargando productos desde Shopify: {e}")
        return await load_sample_data()

@defensive_logging
async def load_sample_data():
    """Carga datos de muestra validados defensivamente."""
    try:
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        if SAMPLE_PRODUCTS:
            # Validar productos de muestra también
            validated_samples = []
            for product in SAMPLE_PRODUCTS:
                validated = DefensiveValidator.safe_product_validation(product)
                if validated.get("id"):
                    validated_samples.append(validated)
            
            logger.info(f"✅ Cargados {len(validated_samples)} productos de muestra validados")
            return validated_samples
    except ImportError:
        logger.warning("⚠️ No se pudieron cargar productos de muestra desde código")
    
    # Datos mínimos de fallback con validación defensiva
    minimal_products = [
        {
            "id": "fallback_product_1",
            "title": "Camiseta básica",
            "body_html": "Camiseta de algodón de alta calidad.",
            "product_type": "Ropa",
            "tags": "básico, algodón",
            "variants": [{"price": "25.99"}]
        },
        {
            "id": "fallback_product_2", 
            "title": "Pantalón vaquero",
            "body_html": "Pantalón vaquero clásico de corte recto.",
            "product_type": "Ropa",
            "tags": "vaquero, clásico",
            "variants": [{"price": "45.99"}]
        },
        {
            "id": "fallback_product_3",
            "title": "Zapatillas deportivas",
            "body_html": "Zapatillas para running con amortiguación.",
            "product_type": "Calzado",
            "tags": "deportivo, running",
            "variants": [{"price": "75.99"}]
        }
    ]
    
    # Aplicar validación defensiva a productos de fallback
    validated_fallback = []
    for product in minimal_products:
        validated = DefensiveValidator.safe_product_validation(product)
        validated_fallback.append(validated)
    
    logger.info(f"✅ Usando {len(validated_fallback)} productos mínimos de fallback validados")
    system_health["degraded_mode"] = True
    return validated_fallback

@defensive_logging
async def load_recommender_with_fallback():
    """Carga recomendador con regeneración automática en caso de fallo."""
    global tfidf_recommender
    
    try:
        # Crear recomendador usando fábrica
        tfidf_recommender = RecommenderFactory.create_tfidf_recommender()
        
        # Intentar cargar modelo existente
        model_path = "data/tfidf_model.pkl"
        if os.path.exists(model_path):
            logger.info(f"📁 Intentando cargar modelo existente: {model_path}")
            try:
                success = await tfidf_recommender.load()
                if success:
                    logger.info("✅ Modelo TF-IDF cargado correctamente desde archivo")
                    system_health["available_features"].append("tfidf_model_loaded")
                    return True
                else:
                    logger.warning("⚠️ Fallo al cargar modelo existente, regenerando...")
            except Exception as e:
                logger.error(f"❌ Error al cargar modelo existente: {e}")
                logger.info("🔄 Eliminando modelo corrupto y regenerando...")
                # Eliminar modelo corrupto
                try:
                    os.remove(model_path)
                    logger.info(f"🗑️ Modelo corrupto eliminado: {model_path}")
                except:
                    pass
        
        # Si no existe modelo o falló la carga, entrenar nuevo
        logger.info("🔄 Generando nuevo modelo TF-IDF...")
        products = await load_shopify_products()
        
        if not products:
            logger.error("❌ No se pudieron cargar productos para entrenar modelo")
            system_health["degraded_mode"] = True
            return False
            
        logger.info(f"🎯 Entrenando modelo TF-IDF con {len(products)} productos")
        success = await tfidf_recommender.fit(products)
        
        if success:
            logger.info("✅ Modelo TF-IDF entrenado correctamente")
            system_health["available_features"].append("tfidf_model_trained")
            
            # Intentar importar a Google Cloud Retail API si está disponible
            try:
                global retail_recommender
                retail_recommender = RecommenderFactory.create_retail_recommender()
                logger.info("🔄 Importando productos a Google Cloud Retail API...")
                import_result = await retail_recommender.import_catalog(products)
                logger.info(f"📊 Resultado de importación: {import_result.get('status', 'unknown')}")
                system_health["available_features"].append("retail_api_catalog")
            except Exception as e:
                logger.error(f"⚠️ Error importando a Retail API (no crítico): {e}")
                
            return True
        else:
            logger.error("❌ Error entrenando modelo TF-IDF")
            system_health["degraded_mode"] = True
            return False
            
    except Exception as e:
        logger.error(f"❌ Error crítico en load_recommender_with_fallback: {e}")
        system_health["degraded_mode"] = True
        return False

@defensive_logging
@redis_circuit_breaker  
async def initialize_cache_system():
    """Inicializa sistema de caché con fallback graceful."""
    global redis_client, product_cache
    
    try:
        if settings.use_redis_cache:
            logger.info("🔄 Inicializando sistema de caché Redis...")
            redis_client = RecommenderFactory.create_redis_client()
            
            if redis_client:
                # Intentar conectar
                connected = await redis_client.connect()
                if connected:
                    logger.info("✅ Conexión Redis establecida")
                    
                    # Crear ProductCache
                    shopify_client = get_shopify_client()
                    product_cache = RecommenderFactory.create_product_cache(
                        content_recommender=tfidf_recommender,
                        shopify_client=shopify_client
                    )
                    
                    if product_cache:
                        logger.info("✅ Sistema de caché de productos inicializado")
                        system_health["available_features"].append("redis_cache")
                        return True
                    else:
                        logger.warning("⚠️ ProductCache no pudo inicializarse")
                else:
                    logger.warning("⚠️ No se pudo conectar a Redis")
            else:
                logger.warning("⚠️ No se pudo crear cliente Redis")
        else:
            logger.info("ℹ️ Caché Redis desactivada por configuración")
            
        # Si llegamos aquí, Redis no está disponible pero seguimos funcionando
        logger.info("🔄 Sistema funcionando sin caché Redis")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error inicializando sistema de caché: {e}")
        return False

async def create_hybrid_recommender():
    """Crea recomendador híbrido con los componentes disponibles."""
    global hybrid_recommender
    
    try:
        if not retail_recommender:
            global retail_recommender
            retail_recommender = RecommenderFactory.create_retail_recommender()
        
        hybrid_recommender = RecommenderFactory.create_hybrid_recommender(
            tfidf_recommender, retail_recommender
        )
        
        # Si tenemos product_cache, añadirlo al híbrido
        if product_cache and hasattr(hybrid_recommender, 'product_cache'):
            hybrid_recommender.product_cache = product_cache
            logger.info("✅ Recomendador híbrido creado con caché")
        else:
            logger.info("✅ Recomendador híbrido creado sin caché")
            
        system_health["available_features"].append("hybrid_recommender")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creando recomendador híbrido: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Evento de inicio robusto con manejo de errores."""
    logger.info("🚀 Iniciando API robusta de recomendaciones...")
    
    # Inicializar componentes secuencialmente con manejo de errores
    startup_tasks = [
        ("recomendador", load_recommender_with_fallback),
        ("cache", initialize_cache_system),
        ("híbrido", create_hybrid_recommender)
    ]
    
    for task_name, task_func in startup_tasks:
        try:
            logger.info(f"🔄 Inicializando {task_name}...")
            success = await task_func()
            if success:
                logger.info(f"✅ {task_name} inicializado correctamente")
            else:
                logger.warning(f"⚠️ {task_name} inicializado con limitaciones")
        except Exception as e:
            logger.error(f"❌ Error inicializando {task_name}: {e}")
            system_health["degraded_mode"] = True
    
    # Actualizar estado del sistema
    system_health["last_check"] = time.time()
    
    # Log resumen del estado
    if system_health["degraded_mode"]:
        logger.warning("⚠️ Sistema iniciado en MODO DEGRADADO")
    else:
        logger.info("✅ Sistema iniciado correctamente")
        
    logger.info(f"📊 Características disponibles: {system_health['available_features']}")

# Health check granular
@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Health check granular con detalles de cada componente."""
    current_time = time.time()
    uptime = current_time - start_time
    
    # Verificar cada componente
    components = {}
    
    # TF-IDF Recommender
    if tfidf_recommender:
        try:
            tfidf_status = await tfidf_recommender.health_check()
            components["tfidf"] = {
                "status": "operational" if tfidf_status.get("loaded") else "degraded",
                "details": tfidf_status
            }
        except Exception as e:
            components["tfidf"] = {"status": "error", "error": str(e)}
    else:
        components["tfidf"] = {"status": "unavailable"}
    
    # Redis Cache
    if redis_client:
        try:
            cache_health = await redis_client.health_check()
            components["redis"] = {
                "status": "operational" if cache_health.get("connected") else "degraded",
                "details": cache_health
            }
        except Exception as e:
            components["redis"] = {"status": "error", "error": str(e)}
    else:
        components["redis"] = {"status": "unavailable"}
    
    # Product Cache
    if product_cache:
        try:
            cache_stats = product_cache.get_stats()
            components["product_cache"] = {
                "status": "operational",
                "stats": cache_stats
            }
        except Exception as e:
            components["product_cache"] = {"status": "error", "error": str(e)}
    else:
        components["product_cache"] = {"status": "unavailable"}
    
    # Hybrid Recommender
    if hybrid_recommender:
        components["hybrid"] = {"status": "operational"}
    else:
        components["hybrid"] = {"status": "unavailable"}
    
    # Determinar estado general
    operational_components = sum(1 for comp in components.values() if comp.get("status") == "operational")
    total_components = len(components)
    
    if operational_components >= total_components * 0.8:
        overall_status = "operational"
    elif operational_components >= total_components * 0.5:
        overall_status = "degraded"
    else:
        overall_status = "critical"
    
    return HealthStatus(
        status=overall_status,
        components=components,
        uptime_seconds=uptime,
        degraded_mode=system_health["degraded_mode"],
        available_features=system_health["available_features"]
    )

# Endpoints robustos con validación defensiva
@app.get("/v1/recommendations/{product_id}")
async def get_recommendations_robust(
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    current_user: str = Depends(get_current_user)
):
    """Obtiene recomendaciones con validación defensiva robusta."""
    start_time = time.time()
    
    # Validación defensiva de parámetros
    product_id = DefensiveValidator.safe_string_operation(product_id, "strip")
    if not product_id:
        raise HTTPException(status_code=400, detail="Product ID no puede estar vacío")
    
    n = max(1, min(20, n or 5))  # Asegurar rango válido
    content_weight = max(0.0, min(1.0, content_weight or 0.5))  # Asegurar rango válido
    
    # Verificar disponibilidad del sistema
    if not tfidf_recommender or not tfidf_recommender.loaded:
        logger.error(f"❌ Sistema no disponible para recomendaciones de producto {product_id}")
        raise HTTPException(
            status_code=503, 
            detail="Sistema de recomendaciones no disponible. Intente más tarde."
        )
    
    try:
        # Intentar obtener producto del catálogo con validación defensiva
        product = None
        try:
            product = tfidf_recommender.get_product_by_id(product_id)
            if product:
                product = DefensiveValidator.safe_product_validation(product)
        except Exception as e:
            logger.warning(f"⚠️ Error obteniendo producto {product_id}: {e}")
        
        if not product or not product.get("id"):
            raise HTTPException(
                status_code=404,
                detail=f"Producto {product_id} no encontrado"
            )
        
        # Obtener recomendaciones con el recomendador disponible
        recommendations = []
        
        if hybrid_recommender:
            try:
                # Actualizar peso de contenido
                hybrid_recommender.content_weight = content_weight
                recommendations = await hybrid_recommender.get_recommendations(
                    user_id=user_id or "anonymous",
                    product_id=product_id,
                    n_recommendations=n
                )
            except Exception as e:
                logger.error(f"❌ Error con recomendador híbrido: {e}")
                # Fallback a TF-IDF directo
                try:
                    recommendations = await tfidf_recommender.get_recommendations(product_id, n)
                except Exception as e2:
                    logger.error(f"❌ Error con TF-IDF directo: {e2}")
                    recommendations = []
        else:
            # Solo TF-IDF disponible
            try:
                recommendations = await tfidf_recommender.get_recommendations(product_id, n)
            except Exception as e:
                logger.error(f"❌ Error con TF-IDF: {e}")
                recommendations = []
        
        # Validar recomendaciones defensivamente
        safe_recommendations = []
        for rec in (recommendations or []):
            if rec and isinstance(rec, dict) and rec.get("id"):
                safe_rec = {
                    "id": DefensiveValidator.safe_string_operation(rec.get("id")),
                    "title": DefensiveValidator.safe_string_operation(rec.get("title"), default="Producto"),
                    "score": float(rec.get("similarity_score", 0) or rec.get("score", 0)),
                    "source": DefensiveValidator.safe_string_operation(rec.get("source"), default="tfidf")
                }
                safe_recommendations.append(safe_rec)
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "product": {
                "id": product.get("id"),
                "title": DefensiveValidator.safe_string_operation(product.get("title"))
            },
            "recommendations": safe_recommendations,
            "metadata": {
                "total_recommendations": len(safe_recommendations),
                "content_weight": content_weight,
                "source": "hybrid" if hybrid_recommender else "tfidf",
                "took_ms": processing_time,
                "degraded_mode": system_health["degraded_mode"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error inesperado obteniendo recomendaciones: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno del servidor. El equipo técnico ha sido notificado."
        )

@app.get("/v1/recommendations/user/{user_id}")
async def get_user_recommendations_robust(
    user_id: str,
    n: Optional[int] = Query(5, gt=0, le=20),
    current_user: str = Depends(get_current_user)
):
    """Obtiene recomendaciones de usuario con validación robusta."""
    start_time = time.time()
    
    # Validación defensiva
    user_id = DefensiveValidator.safe_string_operation(user_id, "strip")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID no puede estar vacío")
    
    n = max(1, min(20, n or 5))
    
    if not hybrid_recommender and not tfidf_recommender:
        raise HTTPException(
            status_code=503,
            detail="Sistema de recomendaciones no disponible"
        )
    
    try:
        recommendations = []
        
        # Intentar con híbrido primero
        if hybrid_recommender:
            try:
                recommendations = await hybrid_recommender.get_recommendations(
                    user_id=user_id,
                    n_recommendations=n
                )
            except Exception as e:
                logger.error(f"❌ Error recomendaciones híbridas para {user_id}: {e}")
        
        # Si no hay recomendaciones, usar estrategia de fallback
        if not recommendations and tfidf_recommender and tfidf_recommender.loaded:
            try:
                # Usar estrategia de fallback mejorada
                from src.recommenders.improved_fallback_exclude_seen import ImprovedFallbackStrategies
                
                recommendations = await ImprovedFallbackStrategies.smart_fallback(
                    user_id=user_id,
                    products=tfidf_recommender.product_data or [],
                    user_events=[],  # Sin eventos históricos disponibles
                    n=n
                )
            except Exception as e:
                logger.error(f"❌ Error con fallback inteligente: {e}")
                recommendations = []
        
        # Validar recomendaciones defensivamente
        safe_recommendations = []
        for rec in (recommendations or []):
            if rec and isinstance(rec, dict) and rec.get("id"):
                safe_rec = {
                    "id": DefensiveValidator.safe_string_operation(rec.get("id")),
                    "title": DefensiveValidator.safe_string_operation(rec.get("title"), default="Producto"),
                    "score": float(rec.get("score", 0) or 0),
                    "source": DefensiveValidator.safe_string_operation(rec.get("source"), default="fallback")
                }
                safe_recommendations.append(safe_rec)
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "user_id": user_id,
            "recommendations": safe_recommendations,
            "metadata": {
                "total_recommendations": len(safe_recommendations),
                "source": "hybrid" if hybrid_recommender else "fallback",
                "took_ms": processing_time,
                "degraded_mode": system_health["degraded_mode"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error inesperado recomendaciones usuario {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno del servidor"
        )

@app.get("/", include_in_schema=False)
def read_root():
    """Root endpoint con información del sistema."""
    return {
        "message": "Retail Recommender API - Robust Edition",
        "version": f"{settings.app_version}-robust",
        "status": "operational" if not system_health["degraded_mode"] else "degraded",
        "available_features": system_health["available_features"],
        "docs_url": "/docs"
    }

# Configuración para ejecutar con uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_robust:app", host="0.0.0.0", port=port, reload=True)
