"""
API principal para el sistema de recomendaciones con TF-IDF conectado a Shopify.

Esta versiÃ³n de la API utiliza vectorizaciÃ³n TF-IDF para ofrecer recomendaciones
basadas en contenido sin necesidad de cargar modelos ML pesados de transformer,
permitiendo un arranque rÃ¡pido y eficiente en entornos cloud, y se conecta
a Shopify para obtener datos reales de productos.

CORRECCIÓN PRINCIPAL:
- Flujo robusto de carga/entrenamiento del modelo TF-IDF
- Validación completa del estado del recomendador
- Manejo inteligente de modelos legacy vs nuevos
- Actualización automática de datos de productos

Esta versión soluciona el problema donde el sistema funcionaba solo cuando 
el modelo data/tfidf_model.pkl no existía.
"""

import os
import time
import logging
import asyncio
from dotenv import load_dotenv

# Intentar cargar variables de entorno, pero continuar si no existe el archivo
try:
    load_dotenv()
    logging.info("Variables de entorno cargadas desde .env")
except Exception as e:
    logging.warning(f"No se pudo cargar .env, usando variables de entorno del sistema: {e}")

from typing import Dict, List, Optional, Any
from fastapi import FastAPI, Header, Query, HTTPException, BackgroundTasks, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from src.api.core.store import get_shopify_client, init_shopify
from src.api.security import get_api_key, get_current_user

# CORRECCIÓN: Importar el recomendador TF-IDF CORREGIDO
from src.recommenders.tfidf_recommender_fixed import TFIDFRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from src.api.startup_helper import StartupManager
from src.api.metrics_router import router as metrics_router

# Importar módulos necesarios para la clase HybridRecommender
import math
import random
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI correctamente
app = FastAPI(
    title="Retail Recommender API - Hybrid Cache Sistem",
    docs_url="/docs",
    description="API para sistema de recomendaciones de retail usando vectorización TF-IDF con conexión a Shopify - VERSIÓN CORREGIDA",
    version="0.5.1-FIXED"
)

# Incluir el router de métricas DESPUÉS de crear app
app.include_router(metrics_router)

# Agregar middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CORRECCIÓN: Crear instancia del recomendador TF-IDF CORREGIDO
tfidf_recommender = TFIDFRecommender(model_path="data/tfidf_model.pkl")

# Crear instancia del recomendador Retail API
retail_recommender = RetailAPIRecommender(
    project_number=os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166"),
    location=os.getenv("GOOGLE_LOCATION", "global"),
    catalog=os.getenv("GOOGLE_CATALOG", "default_catalog"),
    serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
)

# Clase para implementar funcionalidad híbrida (sin cambios, ya funciona correctamente)
class HybridRecommender:
    def __init__(
        self,
        content_recommender,
        retail_recommender,
        content_weight: float = 0.5,
        product_cache = None
    ):
        """
        Inicializa el recomendador híbrido adaptado para TF-IDF.
        
        Args:
            content_recommender: Instancia de TFIDFRecommender
            retail_recommender: Instancia de RetailAPIRecommender
            content_weight: Peso para las recomendaciones basadas en contenido (0-1)
            product_cache: Caché de productos (opcional)
        """
        self.content_recommender = content_recommender
        self.retail_recommender = retail_recommender
        self.content_weight = content_weight
        self.product_cache = product_cache
        logger.info(f"HybridRecommender inicializado con content_weight={content_weight}")
        if product_cache:
            logger.info("HybridRecommender utilizando sistema de caché de productos")
        else:
            logger.info("HybridRecommender sin sistema de caché de productos")
        
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        n_recommendations: int = 5
    ) -> List[Dict]:
        """
        Obtiene recomendaciones híbridas combinando ambos enfoques.
        """
        logger.info(f"Solicitando recomendaciones híbridas: user_id={user_id}, product_id={product_id}, n={n_recommendations}")
        
        # CORRECCIÓN: Verificar estado completo del recomendador
        if not self.content_recommender._validate_state():
            logger.warning("El recomendador TF-IDF no está en estado válido - usando solo fallback")
            return await self._get_fallback_recommendations(n_recommendations)
        
        # Obtener recomendaciones de ambos sistemas
        content_recs = []
        retail_recs = []
        
        # Si hay un product_id, obtener recomendaciones basadas en contenido
        if product_id:
            try:
                content_recs = await self.content_recommender.get_recommendations(product_id, n_recommendations)
                logger.info(f"Obtenidas {len(content_recs)} recomendaciones basadas en contenido para producto {product_id}")
            except Exception as e:
                logger.error(f"Error al obtener recomendaciones basadas en contenido: {str(e)}")
        
        # Intentar obtener recomendaciones de Retail API
        try:
            retail_recs = await self.retail_recommender.get_recommendations(
                user_id=user_id,
                product_id=product_id,
                n_recommendations=n_recommendations
            )
            logger.info(f"Obtenidas {len(retail_recs)} recomendaciones de Retail API para usuario {user_id}")
        except Exception as e:
            logger.error(f"Error al obtener recomendaciones de Retail API: {str(e)}")
        
        # Si no hay producto_id y tampoco recomendaciones de Retail API,
        # usar recomendaciones inteligentes de fallback
        if not product_id and not retail_recs:
            logger.info("Usando recomendaciones mejoradas de fallback")
            # Usar estrategia de fallback inteligente en lugar de la simple
            from src.recommenders.improved_fallback_exclude_seen import ImprovedFallbackStrategies
            
            # Obtener eventos de usuario si están disponibles
            user_events = []
            try:
                # En un sistema real, aquí obtendríamos eventos reales del usuario
                # Por ahora, generamos eventos sintéticos para usuarios de prueba
                if user_id.startswith("test_") or user_id.startswith("synthetic_"):
                    # Genera eventos sintéticos para usuarios de prueba
                    num_events = random.randint(3, 8)
                    for i in range(num_events):
                        user_events.append({
                            "user_id": user_id,
                            "event_type": random.choice(["detail-page-view", "add-to-cart", "purchase-complete"]),
                            "product_id": str(random.choice(self.content_recommender.product_data).get("id", ""))
                        })
            except Exception as e:
                logger.error(f"Error obteniendo eventos de usuario: {str(e)}")
                
            # Usar fallback inteligente
            return await ImprovedFallbackStrategies.smart_fallback(
                user_id=user_id,
                products=self.content_recommender.product_data,
                user_events=user_events,
                n=n_recommendations
            )
            
        # Si hay product_id, combinar ambas recomendaciones
        combined_recs = None
        if product_id:
            combined_recs = await self._combine_recommendations(
                content_recs,
                retail_recs,
                n_recommendations
            )
        else:
            # Si no hay product_id, usar solo recomendaciones de Retail API
            combined_recs = retail_recs
        
        # Enriquecer recomendaciones si está disponible el sistema de caché
        if self.product_cache:
            return await self._enrich_recommendations(combined_recs, user_id)
        else:
            return combined_recs
        
    async def _combine_recommendations(
        self,
        content_recs: List[Dict],
        retail_recs: List[Dict],
        n_recommendations: int
    ) -> List[Dict]:
        """Combina las recomendaciones de ambos sistemas usando los pesos definidos."""
        # Crear un diccionario para trackear scores combinados
        combined_scores = {}
        
        # Procesar recomendaciones basadas en contenido
        for rec in content_recs:
            product_id = rec["id"]
            combined_scores[product_id] = {
                **rec,
                "final_score": rec.get("similarity_score", 0) * self.content_weight
            }
            
        # Procesar recomendaciones de Retail API
        for rec in retail_recs:
            product_id = rec["id"]
            if product_id in combined_scores:
                combined_scores[product_id]["final_score"] += (
                    rec.get("score", 0) * (1 - self.content_weight)
                )
            else:
                combined_scores[product_id] = {
                    **rec,
                    "final_score": rec.get("score", 0) * (1 - self.content_weight)
                }
                
        # Ordenar por score final y devolver los top N
        sorted_recs = sorted(
            combined_scores.values(),
            key=lambda x: x["final_score"],
            reverse=True
        )
        
        return sorted_recs[:n_recommendations]
    
    async def _get_fallback_recommendations(self, n_recommendations: int = 5) -> List[Dict]:
        """
        Proporciona recomendaciones de respaldo cuando no es posible obtener recomendaciones
        de Google Cloud Retail API ni del recomendador basado en contenido.
        """
        logger.info("Generando recomendaciones de fallback")
        
        # CORRECCIÓN: Verificar estado completo del recomendador
        if not self.content_recommender._validate_state():
            logger.warning("No hay datos de productos disponibles para fallback")
            return []
        
        # Obtener todos los productos disponibles
        all_products = self.content_recommender.product_data
        
        # Lógica para seleccionar productos (podría ser por popularidad, fecha, etc.)
        # Por ahora, simplemente tomamos los primeros 'n'
        selected_products = all_products[:min(n_recommendations, len(all_products))]
        
        # Convertir a formato de respuesta
        recommendations = []
        for product in selected_products:
            # Extraer precio del primer variante si está disponible
            price = 0.0
            if product.get("variants") and len(product["variants"]) > 0:
                price_str = product["variants"][0].get("price", "0")
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    price = 0.0
            
            recommendations.append({
                "id": str(product.get("id", "")),
                "title": product.get("title", ""),
                "description": product.get("body_html", "").replace("<p>", "").replace("</p>", ""),
                "price": price,
                "category": product.get("product_type", ""),
                "score": 0.5,  # Score arbitrario
                "recommendation_type": "fallback"  # Indicar que es una recomendación de respaldo
            })
        
        logger.info(f"Generadas {len(recommendations)} recomendaciones de fallback")
        return recommendations
        
    async def _enrich_recommendations(self, recommendations: List[Dict], user_id: str = None) -> List[Dict]:
        """Enriquece las recomendaciones con datos detallados de productos."""
        if not recommendations:
            return []
            
        logger.info(f"Enriqueciendo {len(recommendations)} recomendaciones para usuario {user_id or 'anonymous'}")
        
        # Verificar si tenemos caché de productos
        if not self.product_cache:
            logger.warning("No hay caché de productos disponible para enriquecer recomendaciones")
            return recommendations
            
        # Extraer IDs de productos
        product_ids = [rec.get("id") for rec in recommendations if rec.get("id")]
        
        # Precargar productos solo si el método está disponible y es awaitable
        if hasattr(self.product_cache, 'preload_products'):
            try:
                import inspect
                import asyncio
                from unittest.mock import AsyncMock
                
                preload_method = self.product_cache.preload_products
                # Verificar si es un AsyncMock, un coroutine o un método asincrónico
                if asyncio.iscoroutinefunction(preload_method) or isinstance(preload_method, AsyncMock):
                    await preload_method(product_ids)
                else:
                    logger.warning("preload_products no es awaitable, omitiendo precarga")
            except Exception as e:
                logger.warning(f"Error precargando productos: {str(e)}")
        
        enriched_recommendations = []
        
        for rec in recommendations:
            product_id = rec.get("id")
            if not product_id:
                enriched_recommendations.append(rec)
                continue
                
            enriched_rec = rec.copy()
            
            # Obtener información completa del producto usando la caché
            product = await self.product_cache.get_product(product_id)
            
            if product:
                # Enriquecer con datos del producto
                enriched_rec["title"] = product.get("title", product.get("name", rec.get("title", "Producto")))
                
                # Extraer descripción
                description = (
                    product.get("body_html") or 
                    product.get("description") or 
                    product.get("body", "")
                )
                enriched_rec["description"] = description
                
                # Extraer precio
                price = 0.0
                if product.get("variants") and len(product["variants"]) > 0:
                    try:
                        price = float(product["variants"][0].get("price", 0.0))
                    except (ValueError, TypeError):
                        price = product.get("price", 0.0)
                else:
                    price = product.get("price", 0.0)
                
                enriched_rec["price"] = price
                
                # Extraer categoría
                category = (
                    product.get("product_type") or 
                    product.get("category", "")
                )
                enriched_rec["category"] = category
                
                # Extraer imágenes si están disponibles
                if product.get("images") and isinstance(product["images"], list) and len(product["images"]) > 0:
                    enriched_rec["image_url"] = product["images"][0].get("src", "")
                
                logger.info(f"Producto ID={product_id} enriquecido: Título={enriched_rec['title'][:30]}..., Categoría={category}")
            else:
                # Si no se encuentra información completa
                logger.warning(f"No se pudo obtener información completa para producto ID={product_id}")
                
                # Usar información existente o valores predeterminados
                if not enriched_rec.get("title") or enriched_rec["title"] == "Producto":
                    enriched_rec["title"] = f"Producto {product_id}"
                    
                # Marcar para diagnóstico
                enriched_rec["_incomplete_data"] = True
            
            enriched_recommendations.append(enriched_rec)
        
        logger.info(f"Enriquecidas {len(enriched_recommendations)} recomendaciones")
        
        # Registrar estadísticas para monitoreo
        if self.product_cache:
            cache_stats = self.product_cache.get_stats()
            logger.info(f"Estadísticas de caché: Hit ratio={cache_stats['hit_ratio']:.2f}")
        
        return enriched_recommendations
    
    async def record_user_event(
        self,
        user_id: str,
        event_type: str,
        product_id: Optional[str] = None,
        purchase_amount: Optional[float] = None
    ) -> Dict:
        """Registra eventos de usuario para mejorar las recomendaciones futuras."""
        logger.info(f"Registrando evento de usuario: user_id={user_id}, event_type={event_type}, product_id={product_id}, purchase_amount={purchase_amount}")
        return await self.retail_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id,
            purchase_amount=purchase_amount 
        )

# Crear instancia del recomendador híbrido
hybrid_recommender = HybridRecommender(tfidf_recommender, retail_recommender, content_weight=0.5)

# Crear gestor de arranque
startup_manager = StartupManager(startup_timeout=300.0)

# Modelos de datos (sin cambios)
class ProductModel(BaseModel):
    id: str
    title: str
    similarity_score: Optional[float] = None
    product_data: Dict[str, Any]

class ProductsResponse(BaseModel):
    products: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int
    loading_complete: bool = True

class RecommendationResponse(BaseModel):
    recommendations: List[Dict]
    loading_complete: bool = Field(description="Indica si la carga del recomendador ha finalizado")
    source: str = Field(description="Fuente de las recomendaciones")
    took_ms: float = Field(description="Tiempo de procesamiento en milisegundos")

class HealthStatus(BaseModel):
    status: str = Field(description="Estado general del servicio")
    components: Dict[str, Any] = Field(description="Estado de los componentes")
    uptime_seconds: float = Field(description="Tiempo de funcionamiento en segundos")

# Variables para uptime
start_time = time.time()

async def load_shopify_products():
    """Carga productos desde Shopify."""
    try:
        # Inicializar cliente Shopify
        client = init_shopify()
        if client:
            products = client.get_products()
            logger.info(f"Cargados {len(products)} productos desde Shopify")
            if products:
                logger.info(f"Primer producto: {products[0].get('title', 'No title')}")
            return products
        else:
            logger.warning("No se pudo inicializar el cliente de Shopify, intentando cargar productos de muestra")
    except Exception as e:
        logger.error(f"Error cargando productos desde Shopify: {e}")
    
    # Si falla Shopify, intentar cargar productos de muestra
    return await load_sample_data()

async def load_sample_data():
    """Carga datos de muestra para el recomendador si no se pueden obtener de Shopify."""
    try:
        # Intento 1: Cargar desde datos de muestra en el módulo
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        if SAMPLE_PRODUCTS:
            logger.info(f"Cargados {len(SAMPLE_PRODUCTS)} productos de muestra")
            return SAMPLE_PRODUCTS
    except Exception as e:
        logger.warning(f"No se pudieron cargar productos de muestra desde código: {e}")
    
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
        },
        {
            "id": "product3",
            "title": "Zapatillas deportivas",
            "body_html": "Zapatillas para running con amortiguación.",
            "product_type": "Calzado"
        }
    ]
    logger.info(f"Usando {len(minimal_products)} productos mínimos de muestra")
    return minimal_products

# CORRECCIÓN PRINCIPAL: Flujo de carga robusto del recomendador
async def load_recommender():
    """
    Carga y entrena el recomendador TF-IDF con productos de Shopify.
    VERSIÓN CORREGIDA que maneja correctamente la carga de modelos existentes.
    """
    try:
        logger.info("🔄 Iniciando carga del recomendador TF-IDF...")
        
        # PASO 1: Cargar productos frescos de Shopify/muestra
        products = await load_shopify_products()
        if not products:
            logger.error("❌ No se pudieron cargar productos de ninguna fuente")
            return False
        
        logger.info(f"✅ Productos cargados: {len(products)}")
        
        # PASO 2: Intentar cargar modelo pre-entrenado
        model_loaded = False
        if os.path.exists("data/tfidf_model.pkl"):
            logger.info("📁 Modelo existente encontrado, intentando cargar...")
            model_loaded = await tfidf_recommender.load()
            
            if model_loaded:
                logger.info("✅ Modelo TF-IDF cargado desde archivo")
                
                # PASO 3: Verificar si necesita actualización de datos de productos
                if tfidf_recommender.needs_product_refresh():
                    logger.info("🔄 Actualizando datos de productos en modelo existente...")
                    refresh_success = await tfidf_recommender.refresh_product_data(products)
                    
                    if not refresh_success:
                        logger.warning("⚠️ No se pudieron actualizar datos de productos - reentrenando modelo completo")
                        model_loaded = False
                    else:
                        logger.info("✅ Datos de productos actualizados correctamente")
                else:
                    logger.info("✅ Datos de productos están actualizados")
            else:
                logger.warning("⚠️ Error cargando modelo existente - se reentrenará")
        else:
            logger.info("📁 No existe modelo pre-entrenado")
        
        # PASO 4: Si no se pudo cargar o está obsoleto, entrenar nuevo modelo
        if not model_loaded:
            logger.info("🏗️ Entrenando nuevo modelo TF-IDF...")
            success = await tfidf_recommender.fit(products)
            
            if not success:
                logger.error("❌ Error entrenando recomendador TF-IDF")
                return False
                
            logger.info("✅ Nuevo modelo TF-IDF entrenado correctamente")
        
        # PASO 5: Validación final del estado
        if not tfidf_recommender._validate_state():
            logger.error("❌ El estado final del recomendador no es válido")
            return False
        
        logger.info("✅ Recomendador TF-IDF completamente operativo")
        
        # PASO 6: Importar productos a Google Cloud Retail API
        try:
            logger.info("🌐 Importando productos a Google Cloud Retail API...")
            import_result = await retail_recommender.import_catalog(products)
            logger.info(f"✅ Resultado de importación: {import_result}")
        except Exception as e:
            logger.error(f"⚠️ Error importando productos a Google Cloud Retail API: {str(e)}")
            # No es un error crítico para el funcionamiento del recomendador TF-IDF
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error general cargando recomendador: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicación - VERSIÓN CORREGIDA."""
    logger.info("🚀 Iniciando API de recomendaciones - VERSIÓN CORREGIDA...")
    
    # Verificar estructura del catálogo en Retail API
    try:
        logger.info("🔍 Verificando estructura del catálogo en Google Cloud Retail API...")
        await retail_recommender.ensure_catalog_branches()
    except Exception as e:
        logger.warning(f"⚠️ Error al verificar estructura del catálogo: {str(e)}")
        logger.warning("Continuando con la inicialización a pesar del error en verificación")
    
    # Inicializar cliente Redis y caché de productos
    try:
        from src.api.factories import RecommenderFactory
        
        # Crear cliente Redis
        global redis_client
        redis_client = RecommenderFactory.create_redis_client()
        logger.info("✅ Cliente Redis inicializado")
        
        # Crear caché de productos
        global product_cache
        product_cache = RecommenderFactory.create_product_cache(
            content_recommender=tfidf_recommender,
            shopify_client=get_shopify_client()
        )
        
        if product_cache:
            logger.info("✅ Sistema de caché de productos inicializado correctamente")
        else:
            logger.warning("⚠️ Sistema de caché de productos no disponible - usando modo sin caché")
        
        # Actualizar hybrid_recommender para usar la caché
        global hybrid_recommender
        hybrid_recommender = HybridRecommender(
            tfidf_recommender,
            retail_recommender,
            content_weight=0.5,
            product_cache=product_cache
        )
        
    except Exception as e:
        logger.error(f"⚠️ Error inicializando sistemas de caché: {str(e)}")
        logger.info("Continuando sin caché...")
    
    # Registrar componentes en el gestor de arranque
    startup_manager.register_component(
        name="recommender",
        loader=load_recommender,
        required=True
    )
    
    # Iniciar carga en segundo plano
    loading_task = asyncio.create_task(startup_manager.start_loading())
    
    # Iniciar generación de datos de prueba si es necesario
    if os.getenv("DEBUG", "False").lower() == "true":
        try:
            from src.api.core.event_generator import initialize_with_test_data
            logger.info("🧪 Modo DEBUG: Programando generación de datos de prueba después de carga inicial")
            # Programar para después de que el recomendador esté cargado
            asyncio.create_task(
                initialize_with_test_data(retail_recommender, tfidf_recommender)
            )
        except ImportError:
            logger.warning("⚠️ No se pudo importar event_generator - continuando sin datos de prueba")

@app.get("/", include_in_schema=False)
def read_root():
    return {
        "message": "Retail Recommender API con TF-IDF y conexión a Shopify - VERSIÓN CORREGIDA",
        "version": "0.5.1-FIXED",
        "status": "online",
        "docs_url": "/docs",
        "corrections": [
            "Flujo robusto de carga/entrenamiento del modelo TF-IDF",
            "Validación completa del estado del recomendador",
            "Manejo inteligente de modelos legacy vs nuevos",
            "Actualización automática de datos de productos"
        ]
    }

@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Endpoint de verificación de salud del servicio - VERSIÓN CORREGIDA."""
    # CORRECCIÓN: Usar el health_check mejorado del recomendador
    recommender_status = await tfidf_recommender.health_check()
    startup_status = startup_manager.get_status()
    
    # Añadir estado de Redis/caché si está disponible
    cache_status = {}
    if 'product_cache' in globals() and product_cache:
        try:
            cache_stats = product_cache.get_stats()
            # Obtener estado de conexión Redis
            redis_status = "connected" if (product_cache.redis and product_cache.redis.connected) else "disconnected"
            
            cache_status = {
                "status": "operational" if redis_status == "connected" else "degraded",
                "redis_connection": redis_status,
                "hit_ratio": cache_stats["hit_ratio"],
                "stats": cache_stats
            }
        except Exception as e:
            cache_status = {
                "status": "error",
                "error": str(e)
            }
    else:
        cache_status = {
            "status": "unavailable",
            "message": "Product cache not initialized"
        }
    
    return {
        "status": startup_status["status"],
        "components": {
            "recommender": recommender_status,
            "startup": startup_status,
            "cache": cache_status
        },
        "uptime_seconds": time.time() - start_time
    }

# RESTO DE ENDPOINTS SIN CAMBIOS (solo copiar desde el archivo original)
@app.get("/v1/recommendations/{product_id}", response_model=Dict)
async def get_recommendations(
    product_id: str,
    user_id: Optional[str] = Header(None),
    n: Optional[int] = Query(5, gt=0, le=20),
    content_weight: Optional[float] = Query(0.5, ge=0.0, le=1.0),
    current_user: str = Depends(get_current_user)
):
    """Obtiene recomendaciones basadas en un producto."""
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    # CORRECCIÓN: Verificar estado del recomendador antes de proceder
    if not tfidf_recommender._validate_state():
        raise HTTPException(
            status_code=503, 
            detail="El recomendador TF-IDF no está en estado válido. Intente más tarde."
        )
    
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
        
        return {
            "product": {
                "id": product.get('id'),
                "title": product.get('title')
            },
            "recommendations": recommendations,
            "metadata": {
                "content_weight": content_weight,
                "total_recommendations": len(recommendations),
                "source": "hybrid_tfidf_fixed",
                "took_ms": processing_time_ms,
                "recommender_state": "validated"
            }
        }
    except ValueError as e:
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
    """Obtiene recomendaciones personalizadas para un usuario."""
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    # CORRECCIÓN: Verificar estado del recomendador antes de proceder
    if not tfidf_recommender._validate_state():
        raise HTTPException(
            status_code=503, 
            detail="El recomendador TF-IDF no está en estado válido. Intente más tarde."
        )
    
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
        
        return {
            "recommendations": recommendations,
            "metadata": {
                "user_id": user_id,
                "total_recommendations": len(recommendations),
                "total_orders": len(user_orders) if user_orders else 0,
                "source": "hybrid_tfidf_user_fixed",
                "took_ms": processing_time_ms,
                "recommender_state": "validated"
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
    """Registra eventos de usuario para mejorar las recomendaciones futuras."""
    try:
        # CORRECCIÓN: Validar product_id solo si el recomendador está en estado válido
        if product_id and tfidf_recommender._validate_state():
            # Verificar si es un ID existente en el catálogo
            product_exists = any(str(p.get('id', '')) == product_id for p in tfidf_recommender.product_data)
            if not product_exists:
                # Si el ID no existe, pero es un ID de desarrollo, permitirlo
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
                "note": "El evento fue registrado correctamente y ayudará a mejorar las recomendaciones futuras.",
                "recommender_state": "validated" if tfidf_recommender._validate_state() else "degraded"
            }
        
        return result
    except Exception as e:
        logger.error(f"Error registrando evento de usuario: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error al registrar el evento: {str(e)}. Asegúrate de usar un tipo de evento válido."
        )

@app.get("/v1/customers/")
async def get_customers(
    current_user: str = Depends(get_current_user)
):
    """Obtiene la lista de clientes de Shopify."""
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

@app.get("/v1/products/", response_model=ProductsResponse)
async def get_products(
    page: int = Query(1, gt=0, description="Número de página"),
    page_size: int = Query(50, gt=0, le=100, description="Resultados por página")
):
    """Obtiene la lista de productos con paginación."""
    logger.info(f"get_products: Parámetros recibidos - page={page}, page_size={page_size}")

    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    try:
        # Intentar obtener productos de Shopify primero
        client = get_shopify_client()
        if client:
            all_products = client.get_products()
            logger.info(f"Obtenidos {len(all_products)} productos desde Shopify")
        elif tfidf_recommender._validate_state():
            all_products = tfidf_recommender.product_data
            logger.info(f"Obtenidos {len(all_products)} productos desde el recomendador")
        else:
            # Si no hay productos disponibles, devolver respuesta vacía
            return ProductsResponse(
                products=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=0,
                loading_complete=False
            )
        
        # Validar explícitamente page_size para asegurar que se respeta el valor
        actual_page_size = min(page_size, 100)  # Asegurar que no exceda 100
        logger.info(f"Usando page_size={actual_page_size}")
        
        # Calcular índices de paginación
        start_idx = (page - 1) * actual_page_size
        end_idx = start_idx + actual_page_size
        
        # Calcular total de páginas
        total_products = len(all_products)
        total_pages = math.ceil(total_products / actual_page_size)

        # Verificar que los índices están dentro de límites
        if start_idx >= total_products:
            # Si página fuera de rango, devolver última página
            page = total_pages
            start_idx = (page - 1) * actual_page_size
            end_idx = total_products
        
        # Obtener productos paginados
        paginated_products = all_products[start_idx:end_idx]
        logger.info(f"Devolviendo {len(paginated_products)} productos (page={page}, page_size={actual_page_size})")
        
        # Construir y devolver respuesta usando el modelo definido
        return ProductsResponse(
            products=paginated_products,
            total=total_products,
            page=page,
            page_size=actual_page_size,
            total_pages=total_pages,
            loading_complete=True
        )
    except Exception as e:
        logger.error(f"Error obteniendo productos: {e}")
        logger.error("Stack trace:", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error obteniendo productos: {str(e)}")

@app.get("/v1/products/category/{category}")
async def get_products_by_category(
    category: str,
    current_user: str = Depends(get_current_user)
):
    """Obtiene productos filtrados por categoría."""
    try:
        client = get_shopify_client()
        all_products = []
        
        if client:
            logger.info(f"Obteniendo productos de Shopify para categoría: {category}")
            all_products = client.get_products()
        elif tfidf_recommender._validate_state():
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

@app.get("/v1/products/search/", response_model=Dict)
async def search_products(
    q: str = Query(..., min_length=1, description="Texto de búsqueda"),
    current_user: str = Depends(get_current_user)
):
    """Busca productos por texto utilizando similitud TF-IDF."""
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    # CORRECCIÓN: Verificar estado completo del recomendador
    if not tfidf_recommender._validate_state():
        return {
            "products": [],
            "total": 0,
            "query": q,
            "loading_complete": False,
            "message": "El buscador está cargando. Intente más tarde."
        }
    
    # Realizar búsqueda
    start_processing = time.time()
    try:
        results = await tfidf_recommender.search_products(q, 10)
        processing_time_ms = (time.time() - start_processing) * 1000
        
        return {
            "products": results,
            "total": len(results),
            "query": q,
            "loading_complete": True,
            "took_ms": processing_time_ms,
            "recommender_state": "validated"
        }
    except Exception as e:
        logger.error(f"Error en búsqueda de productos: {e}")
        raise HTTPException(status_code=500, detail=f"Error en búsqueda: {str(e)}")

# Configuración para ejecutar con uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_tfidf_shopify_with_metrics_fixed:app", host="0.0.0.0", port=port, reload=True)

