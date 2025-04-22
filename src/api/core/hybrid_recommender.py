"""
Implementación del recomendador híbrido con variantes.

Este módulo proporciona implementaciones del recomendador híbrido,
incluyendo la versión base y la versión con exclusión de productos ya vistos.
"""

import logging
import random
import time
from typing import List, Dict, Optional, Set, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class HybridRecommender:
    """
    Versión base del recomendador híbrido que combina recomendaciones
    basadas en contenido y basadas en comportamiento.
    """
    
    def __init__(
        self,
        content_recommender,
        retail_recommender,
        content_weight: float = 0.5
    ):
        """
        Inicializa el recomendador híbrido.
        
        Args:
            content_recommender: Recomendador basado en contenido (TF-IDF)
            retail_recommender: Recomendador basado en comportamiento (Retail API)
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
        Obtiene recomendaciones híbridas combinando ambos enfoques.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        logger.info(f"Solicitando recomendaciones híbridas: user_id={user_id}, product_id={product_id}, n={n_recommendations}")
        
        # Obtener recomendaciones de ambos sistemas
        content_recs = []
        retail_recs = []
        
        # Optimización: si content_weight=0, no llamar al recomendador de contenido
        if product_id and self.content_weight > 0:
            try:
                content_recs = await self.content_recommender.get_recommendations(product_id, n_recommendations)
                logger.info(f"Obtenidas {len(content_recs)} recomendaciones basadas en contenido para producto {product_id}")
            except Exception as e:
                logger.error(f"Error al obtener recomendaciones basadas en contenido: {str(e)}")
        
        # Optimización: si content_weight=1, no llamar al recomendador retail
        if self.content_weight < 1.0:
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
            return await self._get_fallback_recommendations(user_id, n_recommendations)
            
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
            n_recommendations: Número de recomendaciones a devolver
            
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
    
    async def _get_fallback_recommendations(
        self, 
        user_id: str, 
        n_recommendations: int = 5
    ) -> List[Dict]:
        """
        Proporciona recomendaciones de respaldo cuando no es posible obtener recomendaciones
        de Google Cloud Retail API ni del recomendador basado en contenido.
        
        Args:
            user_id: ID del usuario
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        logger.info("Generando recomendaciones de fallback")
        
        try:
            # Intentar usar el fallback mejorado
            from src.recommenders.improved_fallback_exclude_seen import ImprovedFallbackStrategies
            
            # Generar eventos sintéticos para usuarios de prueba
            user_events = []
            if user_id.startswith("test_") or user_id.startswith("synthetic_"):
                num_events = random.randint(3, 8)
                for i in range(num_events):
                    user_events.append({
                        "user_id": user_id,
                        "event_type": random.choice(["detail-page-view", "add-to-cart", "purchase-complete"]),
                        "product_id": str(random.choice(self.content_recommender.product_data).get("id", ""))
                    })
            
            return await ImprovedFallbackStrategies.smart_fallback(
                user_id=user_id,
                products=self.content_recommender.product_data,
                user_events=user_events,
                n=n_recommendations
            )
        except Exception as e:
            logger.error(f"Error usando fallback mejorado: {str(e)}, usando fallback básico")
            
            # Verificar si hay productos disponibles
            if not self.content_recommender.loaded or not self.content_recommender.product_data:
                # Si no hay datos, devolver lista vacía
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
            
            logger.info(f"Generadas {len(recommendations)} recomendaciones de fallback básico")
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
            purchase_amount: Monto de la compra (para eventos de compra)
            
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


class HybridRecommenderWithExclusion(HybridRecommender):
    """
    Extensión del recomendador híbrido que excluye productos ya vistos por el usuario.
    """
    
    async def get_user_interactions(
        self, 
        user_id: str, 
        user_events: Optional[List[Dict]] = None
    ) -> Set[str]:
        """
        Obtiene el conjunto de IDs de productos con los que el usuario ha interactuado.
        
        Args:
            user_id: ID del usuario
            user_events: Lista de eventos del usuario (opcional)
            
        Returns:
            Set[str]: Conjunto de IDs de productos con los que el usuario ha interactuado
        """
        interacted_products = set()
        
        # Si se proporcionan eventos, usarlos directamente
        if user_events:
            for event in user_events:
                if event.get("productId"):
                    interacted_products.add(str(event.get("productId")))
        else:
            # Intentar obtener eventos del usuario desde Retail API
            try:
                events = await self.retail_recommender.get_user_events(user_id)
                for event in events:
                    if event.get("productId"):
                        interacted_products.add(str(event.get("productId")))
            except Exception as e:
                logger.warning(f"Error al obtener eventos del usuario {user_id}: {str(e)}")
        
        # Para usuarios de prueba, generar interacciones sintéticas
        if not interacted_products and (user_id.startswith("test_") or user_id.startswith("synthetic_")):
            if self.content_recommender.loaded and self.content_recommender.product_data:
                # Seleccionar algunos productos aleatorios para simular interacciones
                num_interactions = min(3, len(self.content_recommender.product_data))
                if num_interactions > 0:
                    random_products = random.sample(self.content_recommender.product_data, num_interactions)
                    interacted_products = {str(p.get("id", "")) for p in random_products}
        
        logger.info(f"Usuario {user_id} ha interactuado con {len(interacted_products)} productos")
        if interacted_products:
            logger.info(f"Productos: {', '.join(list(interacted_products)[:5])}" + 
                      (f"... y {len(interacted_products) - 5} más" if len(interacted_products) > 5 else ""))
        
        return interacted_products
    
    async def get_recommendations(
        self,
        user_id: str,
        product_id: Optional[str] = None,
        n_recommendations: int = 5
    ) -> List[Dict]:
        """
        Obtiene recomendaciones híbridas excluyendo productos ya vistos.
        
        Args:
            user_id: ID del usuario
            product_id: ID del producto (opcional)
            n_recommendations: Número de recomendaciones a devolver
            
        Returns:
            List[Dict]: Lista de productos recomendados
        """
        logger.info(f"Solicitando recomendaciones con exclusión: user_id={user_id}, product_id={product_id}, n={n_recommendations}")
        
        # Obtener productos con los que el usuario ha interactuado
        interacted_products = await self.get_user_interactions(user_id)
        
        # Solicitar más recomendaciones de las necesarias para compensar las que se filtrarán
        extra_count = min(len(interacted_products), 10)  # Solicitar hasta 10 extras
        total_recommendations = n_recommendations + extra_count
        
        # Obtener recomendaciones del recomendador base
        recommendations = await super().get_recommendations(
            user_id=user_id,
            product_id=product_id,
            n_recommendations=total_recommendations
        )
        
        # Filtrar productos ya vistos
        filtered_recommendations = [
            rec for rec in recommendations 
            if str(rec.get("id", "")) not in interacted_products
        ]
        
        logger.info(f"Filtradas {len(recommendations) - len(filtered_recommendations)} recomendaciones ya vistas")
        
        # Si no hay suficientes después de filtrar, obtener más
        if len(filtered_recommendations) < n_recommendations:
            logger.info(f"Insuficientes recomendaciones después de filtrar ({len(filtered_recommendations)}). Solicitando más.")
            try:
                # Intentar usar el fallback mejorado
                from src.recommenders.improved_fallback_exclude_seen import ImprovedFallbackStrategies
                
                # Calcular cuántas recomendaciones adicionales necesitamos
                additional_needed = n_recommendations - len(filtered_recommendations)
                
                # Obtener recomendaciones adicionales, excluyendo tanto los productos ya vistos
                # como los que ya están en las recomendaciones filtradas
                additional_exclude = interacted_products.union({
                    str(rec.get("id", "")) for rec in filtered_recommendations
                })
                
                # Obtener recomendaciones de fallback
                additional_recs = await ImprovedFallbackStrategies.get_diverse_category_products(
                    products=self.content_recommender.product_data,
                    n=additional_needed,
                    exclude_products=additional_exclude
                )
                
                filtered_recommendations.extend(additional_recs)
                logger.info(f"Añadidas {len(additional_recs)} recomendaciones adicionales de fallback")
            except Exception as e:
                logger.error(f"Error al obtener recomendaciones adicionales: {str(e)}")
        
        # Asegurar que no excedemos el número solicitado
        return filtered_recommendations[:n_recommendations]
