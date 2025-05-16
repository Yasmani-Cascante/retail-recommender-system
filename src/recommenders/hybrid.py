from typing import List, Dict, Optional
import logging
from .content_based import ContentBasedRecommender
from .retail_api import RetailAPIRecommender

logger = logging.getLogger(__name__)

class HybridRecommender:
    def __init__(
        self,
        content_recommender: ContentBasedRecommender,
        retail_recommender: RetailAPIRecommender,
        content_weight: float = 0.5
    ):
        """
        Inicializa el recomendador híbrido.
        
        Args:
            content_recommender: Instancia de ContentBasedRecommender
            retail_recommender: Instancia de RetailAPIRecommender
            content_weight: Peso para las recomendaciones basadas en contenido (0-1)
        """
        self.content_recommender = content_recommender
        self.retail_recommender = retail_recommender
        self.content_weight = content_weight
        
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        n_recommendations: int = 5
    ) -> List[Dict]:
        """
        Obtiene recomendaciones híbridas combinando ambos enfoques.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        logger.info(f"Solicitando recomendaciones híbridas: user_id={user_id}, product_id={product_id}, n={n_recommendations}")
        
        # Verificar disponibilidad del catálogo local
        catalog_available = False
        catalog_size = 0
        
        if hasattr(self.content_recommender, 'product_data') and self.content_recommender.product_data:
            catalog_available = True
            catalog_size = len(self.content_recommender.product_data)
        
        logger.info(f"Estado del catálogo local: Disponible={catalog_available}, Tamaño={catalog_size}")
        if catalog_available and catalog_size > 0:
            sample_product = self.content_recommender.product_data[0]
            logger.info(f"Muestra de producto en catálogo: ID={sample_product.get('id')}, Título={sample_product.get('title')}")
        
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
            logger.info(f"Solicitando recomendaciones a RetailAPIRecommender para usuario {user_id}")
            
            retail_recs = await self.retail_recommender.get_recommendations(
                user_id=user_id,
                product_id=product_id,
                n_recommendations=n_recommendations
            )
            
            logger.info(f"RetailAPIRecommender devolvió {len(retail_recs)} recomendaciones")
            for i, rec in enumerate(retail_recs[:3]):  # Mostrar solo primeras 3 para no saturar logs
                logger.info(f"Recomendación {i+1}: ID={rec.get('id')}, Título={rec.get('title')}, Categoría={rec.get('category')}")
        except Exception as e:
            logger.error(f"Error al obtener recomendaciones de Retail API: {str(e)}")
        
        # Si estamos solicitando recomendaciones para un usuario (sin product_id) 
        # y obtenemos recomendaciones de RetailAPI, enriquecerlas con catálogo local
        if not product_id and retail_recs:
            logger.info(f"Procesando {len(retail_recs)} recomendaciones para usuario {user_id} de RetailAPI")
            
            # Verificar si hay catálogo para enriquecimiento
            if catalog_available:
                # Intentar enriquecer recomendaciones con datos locales
                logger.info("Intentando enriquecer recomendaciones con catálogo local")
                enriched_recs = []
                
                for rec in retail_recs:
                    product_id = rec.get("id")
                    product = next((p for p in self.content_recommender.product_data 
                                  if str(p.get('id', '')) == str(product_id)), None)
                    
                    if product:
                        # Extraer precio si está disponible
                        price = 0.0
                        if product.get("variants") and len(product["variants"]) > 0:
                            try:
                                price = float(product["variants"][0].get("price", "0"))
                            except (ValueError, TypeError):
                                price = 0.0
                        
                        # Crear recomendación enriquecida
                        enriched_rec = {
                            "id": product_id,
                            "title": product.get("title", rec.get("title", "Producto")),
                            "description": product.get("body_html", "").replace("<p>", "").replace("</p>", ""),
                            "price": price,
                            "category": product.get("product_type", rec.get("category", "")),
                            "score": rec.get("score", 0.0),
                            "source": rec.get("source", "retail_api")
                        }
                        
                        enriched_recs.append(enriched_rec)
                        logger.info(f"Producto ID={product_id} enriquecido: Título={enriched_rec['title']}, Categoría={enriched_rec['category']}")
                    else:
                        logger.warning(f"Producto ID={product_id} no encontrado en catálogo local, usando datos originales")
                        enriched_recs.append(rec)
                        
                logger.info(f"Enriquecidas {len(enriched_recs)} recomendaciones para usuario {user_id}")
                return enriched_recs
            else:
                logger.warning("No hay catálogo local para enriquecimiento, devolviendo recomendaciones originales")
            
            return retail_recs
        
        # Si no hay producto_id y tampoco recomendaciones de Retail API,
        # usar recomendaciones basadas en productos populares o aleatorios
        if not product_id and not retail_recs:
            logger.info("Usando recomendaciones de fallback")
            return self._get_fallback_recommendations(n_recommendations)
            
        # Si hay product_id, combinar ambas recomendaciones
        if product_id:
            recommendations = self._combine_recommendations(
                content_recs,
                retail_recs,
                n_recommendations
            )
            return recommendations
        
        # Si no hay product_id, usar solo recomendaciones de Retail API
        return retail_recs
        
    def _combine_recommendations(
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
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista combinada de recomendaciones
        """
        # Crear un diccionario para trackear scores combinados
        combined_scores = {}
        
        # Procesar recomendaciones basadas en contenido
        for rec in content_recs:
            product_id = rec["id"]
            product_data = rec.get("product_data", {})
            
            # Si tenemos product_data, extraer información detallada
            if product_data:
                # Extraer precio si está disponible
                price = 0.0
                if product_data.get("variants") and len(product_data["variants"]) > 0:
                    try:
                        price = float(product_data["variants"][0].get("price", "0"))
                    except (ValueError, TypeError):
                        price = 0.0
                        
                # Crear recomendación con información enriquecida
                enriched_rec = {
                    "id": product_id,
                    "title": product_data.get("title", rec.get("title", "Producto")),
                    "description": product_data.get("body_html", "").replace("<p>", "").replace("</p>", ""),
                    "price": price,
                    "category": product_data.get("product_type", ""),
                    "similarity_score": rec.get("similarity_score", 0),
                    "score": rec.get("similarity_score", 0),  # Para compatibilidad
                    "source": "tfidf"
                }
                
                combined_scores[product_id] = {
                    **enriched_rec,
                    "final_score": rec.get("similarity_score", 0) * self.content_weight
                }
            else:
                # Si no hay product_data, usar la recomendación original
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
        
        # Loguear las recomendaciones combinadas para depuración
        logger.info(f"Combinados {len(sorted_recs)} resultados - Mostrando primeros 3:")
        for i, rec in enumerate(sorted_recs[:3]):
            logger.info(f"Recomendación combinada {i+1}: ID={rec.get('id')}, Título={rec.get('title')}, Score={rec.get('final_score')}")
            
        return sorted_recs[:n_recommendations]
    
    def _get_fallback_recommendations(self, n_recommendations: int = 5) -> List[Dict]:
        """
        Proporciona recomendaciones de respaldo cuando no es posible obtener recomendaciones
        de Google Cloud Retail API ni del recomendador basado en contenido.
        
        Args:
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        # Verificar si hay productos disponibles
        if not hasattr(self.content_recommender, 'product_data') or not self.content_recommender.product_data:
            # Si no hay datos, devolver lista vacía
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
        
        return recommendations
        
    async def record_user_event(
        self,
        user_id: str,
        event_type: str,
        product_id: Optional[str] = None,
        purchase_amount: Optional[float] = None
    ):
        """
        Registra eventos de usuario para mejorar las recomendaciones futuras.
        
        Args:
            user_id: ID del usuario
            event_type: Tipo de evento
            product_id: ID del producto (opcional)
        """
        return await self.retail_recommender.record_user_event(
            user_id=user_id,
            event_type=event_type,
            product_id=product_id,
            purchase_amount=purchase_amount
        )