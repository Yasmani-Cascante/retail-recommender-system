"""
API principal para el sistema de recomendaciones con TF-IDF conectado a Shopify.

Esta versiÃ³n de la API utiliza vectorizaciÃ³n TF-IDF para ofrecer recomendaciones
basadas en contenido sin necesidad de cargar modelos ML pesados de transformer,
permitiendo un arranque rÃ¡pido y eficiente en entornos cloud, y se conecta
a Shopify para obtener datos reales de productos.
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

# Importar el recomendador TF-IDF y Google Retail API
from src.recommenders.tfidf_recommender import TFIDFRecommender
from src.recommenders.retail_api import RetailAPIRecommender
from src.api.startup_helper import StartupManager
# Importar el router de mÃ©tricas
from src.api.metrics_router import router as metrics_router

# Importar mÃ³dulos necesarios para la clase HybridRecommender
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
    title="Retail Recommender API",
    description="API para sistema de recomendaciones de retail usando vectorización TF-IDF con conexión a Shopify",
    version="0.5.0"
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

# Crear instancia del recomendador TF-IDF
tfidf_recommender = TFIDFRecommender(model_path="data/tfidf_model.pkl")

# Crear instancia del recomendador Retail API
retail_recommender = RetailAPIRecommender(
    project_number=os.getenv("GOOGLE_PROJECT_NUMBER", "178362262166"),
    location=os.getenv("GOOGLE_LOCATION", "global"),
    catalog=os.getenv("GOOGLE_CATALOG", "default_catalog"),
    serving_config_id=os.getenv("GOOGLE_SERVING_CONFIG", "default_recommendation_config")
)

# Clase para implementar funcionalidad hÃ­brida
class HybridRecommender:
    def __init__(
        self,
        content_recommender,
        retail_recommender,
        content_weight: float = 0.5
    ):
        """
        Inicializa el recomendador hÃ­brido adaptado para TF-IDF.
        
        Args:
            content_recommender: Instancia de TFIDFRecommender
            retail_recommender: Instancia de RetailAPIRecommender
            content_weight: Peso para las recomendaciones basadas en contenido (0-1)
        """
        self.content_recommender = content_recommender
        self.retail_recommender = retail_recommender
        self.content_weight = content_weight
        logger.info(f"HybridRecommender inicializado con content_weight={content_weight}")
        
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        n_recommendations: int = 5
    ) -> List[Dict]:
        """
        Obtiene recomendaciones hÃ­bridas combinando ambos enfoques.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            n_recommendations: NÃºmero de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        logger.info(f"Solicitando recomendaciones hÃ­bridas: user_id={user_id}, product_id={product_id}, n={n_recommendations}")
        
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
            
            # Obtener eventos de usuario si estÃ¡n disponibles
            user_events = []
            try:
                # En un sistema real, aquÃ­ obtendrÃ­amos eventos reales del usuario
                # Por ahora, generamos eventos sintÃ©ticos para usuarios de prueba
                if user_id.startswith("test_") or user_id.startswith("synthetic_"):
                    # Genera eventos sintÃ©ticos para usuarios de prueba
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
        if product_id:
            recommendations = await self._combine_recommendations(
                content_recs,
                retail_recs,
                n_recommendations
            )
            return recommendations
        
        # Si no hay product_id, usar solo recomendaciones de Retail API
        return retail_recs
        
    async def _combine_recommendations(
        self,
        content_recs: List[Dict],
        retail_recs: List[Dict],
        n_recommendations: int
    ) -> List[Dict]:
        """
        Combina las recomendaciones de ambos sistemas usando los pesos definidos.
        
        Args:
            content_recs: Recomendaciones basadas en contenido
            retail_recs: Recomendaciones de Retail API
            n_recommendations: NÃºmero de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista combinada de recomendaciones
        """
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
        
        Args:
            n_recommendations: NÃºmero de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        logger.info("Generando recomendaciones de fallback")
        # Verificar si hay productos disponibles
        if not self.content_recommender.loaded or not self.content_recommender.product_data:
            # Si no hay datos, devolver lista vacÃ­a
            logger.warning("No hay datos de productos disponibles para fallback")
            return []
        
        # Obtener todos los productos disponibles
        all_products = self.content_recommender.product_data
        
        # LÃ³gica para seleccionar productos (podrÃ­a ser por popularidad, fecha, etc.)
        # Por ahora, simplemente tomamos los primeros 'n'
        selected_products = all_products[:min(n_recommendations, len(all_products))]
        
        # Convertir a formato de respuesta
        recommendations = []
        for product in selected_products:
            # Extraer precio del primer variante si estÃ¡ disponible
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
                "recommendation_type": "fallback"  # Indicar que es una recomendaciÃ³n de respaldo
            })
        
        logger.info(f"Generadas {len(recommendations)} recomendaciones de fallback")
        return recommendations
        
    async def record_user_event(
        self,
        user_id: str,
        event_type: str,
        product_id: Optional[str] = None,
        purchase_amount: Optional[float] = None
    ) -> Dict:
        """
        Registra eventos de usuario para mejorar las recomendaciones futuras.
        
        Args:
            user_id: ID del usuario
            event_type: Tipo de evento
            product_id: ID del producto (opcional)
            
        Returns:
            Dict: Resultado del registro del evento
        """
        logger.info(f"Registrando evento de usuario: user_id={user_id}, event_type={event_type}, product_id={product_id}, purchase_amount={purchase_amount}")
        return await self.retail_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id,
            purchase_amount=purchase_amount 
        )

# Crear instancia del recomendador hÃ­brido
hybrid_recommender = HybridRecommender(tfidf_recommender, retail_recommender, content_weight=0.5)

# Crear gestor de arranque
startup_manager = StartupManager(startup_timeout=300.0)

# Modelos de datos
class ProductModel(BaseModel):
    id: str
    title: str
    similarity_score: Optional[float] = None
    product_data: Dict[str, Any]

# Modelo para la respuesta de productos con paginación
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
        # Intento 1: Cargar desde datos de muestra en el mÃ³dulo
        from src.api.core.sample_data import SAMPLE_PRODUCTS
        if SAMPLE_PRODUCTS:
            logger.info(f"Cargados {len(SAMPLE_PRODUCTS)} productos de muestra")
            return SAMPLE_PRODUCTS
    except Exception as e:
        logger.warning(f"No se pudieron cargar productos de muestra desde cÃ³digo: {e}")
    
    # Datos mÃ­nimos de fallback
    minimal_products = [
        {
            "id": "product1",
            "title": "Camiseta bÃ¡sica",
            "body_html": "Camiseta de algodÃ³n de alta calidad.",
            "product_type": "Ropa"
        },
        {
            "id": "product2",
            "title": "PantalÃ³n vaquero",
            "body_html": "PantalÃ³n vaquero clÃ¡sico de corte recto.",
            "product_type": "Ropa"
        },
        {
            "id": "product3",
            "title": "Zapatillas deportivas",
            "body_html": "Zapatillas para running con amortiguaciÃ³n.",
            "product_type": "Calzado"
        }
    ]
    logger.info(f"Usando {len(minimal_products)} productos mÃ­nimos de muestra")
    return minimal_products

async def load_recommender():
    """Carga y entrena el recomendador TF-IDF con productos de Shopify."""
    try:
        # Intentar cargar modelo pre-entrenado
        if os.path.exists("data/tfidf_model.pkl"):
            success = await tfidf_recommender.load()
            if success:
                logger.info("Modelo TF-IDF cargado correctamente desde archivo")
                return True
        
        # Si no existe o falla, entrenar con datos de Shopify o muestra
        products = await load_shopify_products()
        if not products:
            logger.error("No se pudieron cargar productos de ninguna fuente")
            return False
            
        logger.info(f"Entrenando recomendador TF-IDF con {len(products)} productos")
        success = await tfidf_recommender.fit(products)
        
        if success:
            logger.info("Recomendador TF-IDF entrenado correctamente")
            
            # Importar productos a Google Cloud Retail API
            try:
                logger.info("Importando productos a Google Cloud Retail API")
                import_result = await retail_recommender.import_catalog(products)
                logger.info(f"Resultado de importaciÃ³n: {import_result}")
            except Exception as e:
                logger.error(f"Error importando productos a Google Cloud Retail API: {str(e)}")
        else:
            logger.error("Error entrenando recomendador TF-IDF")
            
        return success
    except Exception as e:
        logger.error(f"Error cargando recomendador: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicaciÃ³n."""
    logger.info("ðŸš€ Iniciando API de recomendaciones con conexiÃ³n a Shopify...")
    
    # NUEVO: Verificar estructura del catálogo en Retail API
    try:
        logger.info("Verificando estructura del catálogo en Google Cloud Retail API...")
        await retail_recommender.ensure_catalog_branches()
    except Exception as e:
        logger.warning(f"Error al verificar estructura del catálogo: {str(e)}")
        logger.warning("Continuando con la inicialización a pesar del error en la verificación de ramas")
    
    # Registrar componentes en el gestor de arranque
    startup_manager.register_component(
        name="recommender",
        loader=load_recommender,
        required=True
    )
    
    # Iniciar carga en segundo plano
    loading_task = asyncio.create_task(startup_manager.start_loading())
    
    # Iniciar generaciÃ³n de datos de prueba si es necesario
    if os.getenv("DEBUG", "False").lower() == "true":
        from src.api.core.event_generator import initialize_with_test_data
        logger.info("Modo DEBUG: Programando generaciÃ³n de datos de prueba despuÃ©s de carga inicial")
        # Programar para despuÃ©s de que el recomendador estÃ© cargado
        asyncio.create_task(
            initialize_with_test_data(retail_recommender, tfidf_recommender)
        )

@app.get("/", include_in_schema=False)
def read_root():
    return {
        "message": "Retail Recommender API con TF-IDF y conexiÃ³n a Shopify",
        "version": "0.5.0",
        "status": "online",
        "docs_url": "/docs"
    }

@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Endpoint de verificaciÃ³n de salud del servicio."""
    recommender_status = await tfidf_recommender.health_check()
    startup_status = startup_manager.get_status()
    
    return {
        "status": startup_status["status"],
        "components": {
            "recommender": recommender_status,
            "startup": startup_status
        },
        "uptime_seconds": time.time() - start_time
    }

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
    Requiere autenticaciÃ³n mediante API key.
    """
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    # Obtener recomendaciones
    try:
        # Actualizar peso de contenido en el recomendador hÃ­brido
        hybrid_recommender.content_weight = content_weight
        
        # Obtener producto especÃ­fico
        client = get_shopify_client()
        product = None
        
        if client:
            # Obtener productos
            all_products = client.get_products()
            
            # Encontrar el producto especÃ­fico
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
            
        # Obtener recomendaciones del recomendador hÃ­brido
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
                "source": "hybrid_tfidf",
                "took_ms": processing_time_ms
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
    """
    Obtiene recomendaciones personalizadas para un usuario.
    Requiere autenticaciÃ³n mediante API key.
    """
    start_processing = time.time()
    
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    try:
        client = get_shopify_client()
        
        logger.info(f"Obteniendo recomendaciones para usuario {user_id}")
        
        # Obtener Ã³rdenes del usuario si estÃ¡ disponible Shopify
        user_orders = []
        if client:
            user_orders = client.get_orders_by_customer(user_id)
            
            if user_orders:
                logger.info(f"Se encontraron {len(user_orders)} Ã³rdenes para el usuario {user_id}")
                
                # Registrar eventos de usuario basados en Ã³rdenes
                try:
                    await retail_recommender.process_shopify_orders(user_orders, user_id)
                    logger.info(f"Eventos de Ã³rdenes procesados para usuario {user_id}")
                except Exception as e:
                    logger.error(f"Error procesando Ã³rdenes: {e}")
            else:
                logger.info(f"No se encontraron Ã³rdenes para el usuario {user_id}")
        
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
                "source": "hybrid_tfidf_user",
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
    Requiere autenticaciÃ³n mediante API key.
    
    Tipos de eventos vÃ¡lidos segÃºn Google Cloud Retail API:
    - add-to-cart: Cuando un usuario aÃ±ade un producto al carrito
    - category-page-view: Cuando un usuario ve pÃ¡ginas especiales, como ofertas o promociones
    - detail-page-view: Cuando un usuario ve la pÃ¡gina de detalle de un producto
    - home-page-view: Cuando un usuario visita la pÃ¡gina de inicio
    - purchase-complete: Cuando un usuario completa una compra
    - search: Cuando un usuario realiza una bÃºsqueda
    
    El sistema tambiÃ©n acepta nombres alternativos simplificados:
    - 'view' o 'detail-page' â†’ detail-page-view
    - 'add' o 'cart' â†’ add-to-cart
    - 'buy', 'purchase' o 'checkout' â†’ purchase-complete
    - 'home' â†’ home-page-view
    - 'category' o 'promo' â†’ category-page-view
    """
    try:
        # Validar product_id si estÃ¡ presente
        if product_id:
            # Verificar si es un ID existente en el catÃ¡logo
            if tfidf_recommender.loaded and tfidf_recommender.product_data:
                product_exists = any(str(p.get('id', '')) == product_id for p in tfidf_recommender.product_data)
                if not product_exists:
                    # Si el ID no existe, pero es un ID de desarrollo (empieza con 'prod_test_'), permitirlo
                    if not product_id.startswith(('test_', 'prod_test_', '123')):
                        logger.warning(f"ID de producto no encontrado en el catÃ¡logo: {product_id}")
                        # AÃºn permitimos el evento, pero advertimos
            
        logger.info(f"Registrando evento de usuario: {user_id}, tipo: {event_type}, producto: {product_id or 'N/A'}")
        
        # Registrar el evento
        result = await hybrid_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id,
            purchase_amount=purchase_amount
        )
        
        # AÃ±adir informaciÃ³n adicional a la respuesta
        if result.get("status") == "success":
            result["detail"] = {
                "user_id": user_id,
                "event_type": result.get("event_type", event_type),
                "product_id": product_id,
                "timestamp": datetime.utcnow().isoformat(),
                "note": "El evento fue registrado correctamente y ayudarÃ¡ a mejorar las recomendaciones futuras."
            }
        
        return result
    except Exception as e:
        logger.error(f"Error registrando evento de usuario: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error al registrar el evento: {str(e)}. AsegÃºrate de usar un tipo de evento vÃ¡lido (detail-page-view, add-to-cart, purchase-complete, category-page-view, home-page-view, search)."
        )

@app.get("/v1/customers/")
async def get_customers(
    current_user: str = Depends(get_current_user)
):
    """
    Obtiene la lista de clientes de Shopify.
    Requiere autenticaciÃ³n mediante API key.
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
    
# Modelo para la respuesta de productos
class ProductsResponse(BaseModel):
    products: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int
    loading_complete: bool = True

@app.get("/v1/products/", response_model=ProductsResponse)
async def get_products(
    page: int = Query(1, gt=0, description="Número de página"),
    page_size: int = Query(50, gt=0, le=100, description="Resultados por página")
):
    """
    Obtiene la lista de productos con paginaciÃ³n.
    """
    # Log del valor recibido para debugging
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
        elif tfidf_recommender.loaded and tfidf_recommender.product_data:
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
    """
    Obtiene productos filtrados por categorÃ­a.
    Requiere autenticaciÃ³n mediante API key.
    """
    try:
        client = get_shopify_client()
        all_products = []
        
        if client:
            logger.info(f"Obteniendo productos de Shopify para categorÃ­a: {category}")
            all_products = client.get_products()
        elif tfidf_recommender.loaded and tfidf_recommender.product_data:
            logger.info(f"Obteniendo productos del recomendador para categorÃ­a: {category}")
            all_products = tfidf_recommender.product_data
        else:
            raise HTTPException(
                status_code=503,
                detail="No hay productos disponibles. El servicio estÃ¡ cargando."
            )
            
        logger.info(f"Filtrando {len(all_products)} productos por categorÃ­a: {category}")
        
        # Filtrar por categorÃ­a (product_type en Shopify)
        category_products = [
            p for p in all_products 
            if p.get("product_type", "").lower() == category.lower()
        ]
        
        logger.info(f"Encontrados {len(category_products)} productos en categorÃ­a {category}")
        
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
        logger.error(f"Error en bÃºsqueda por categorÃ­a: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/products/search/", response_model=Dict)
async def search_products(
    q: str = Query(..., min_length=1, description="Texto de bÃºsqueda"),
    current_user: str = Depends(get_current_user)
):
    """
    Busca productos por texto utilizando similitud TF-IDF.
    Requiere autenticaciÃ³n mediante API key.
    """
    # Verificar estado de carga
    is_healthy, reason = startup_manager.is_healthy()
    if not is_healthy:
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {reason}")
    
    if not tfidf_recommender.loaded:
        return {
            "products": [],
            "total": 0,
            "query": q,
            "loading_complete": False,
            "message": "El buscador estÃ¡ cargando. Intente mÃ¡s tarde."
        }
    
    # Realizar bÃºsqueda
    start_processing = time.time()
    try:
        results = await tfidf_recommender.search_products(q, 10)
        processing_time_ms = (time.time() - start_processing) * 1000
        
        return {
            "products": results,
            "total": len(results),
            "query": q,
            "loading_complete": True,
            "took_ms": processing_time_ms
        }
    except Exception as e:
        logger.error(f"Error en bÃºsqueda de productos: {e}")
        raise HTTPException(status_code=500, detail=f"Error en bÃºsqueda: {str(e)}")

# ConfiguraciÃ³n para ejecutar con uvicorn
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_tfidf_shopify:app", host="0.0.0.0", port=port, reload=True)

