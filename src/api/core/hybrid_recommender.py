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
        content_weight: float = 0.5,
        product_cache = None
    ):
        """
        Inicializa el recomendador híbrido.
        
        Args:
            content_recommender: Recomendador basado en contenido (TF-IDF)
            retail_recommender: Recomendador basado en comportamiento (Retail API)
            content_weight: Peso para las recomendaciones basadas en contenido (0-1)
        """
        # Validar parámetros de entrada
        if content_weight < 0 or content_weight > 1:
            raise ValueError(f"content_weight debe estar entre 0 y 1, recibido: {content_weight}")
            
        self.content_recommender = content_recommender
        self.retail_recommender = retail_recommender
        self.content_weight = content_weight
        self.product_cache = product_cache
        
        logger.info(f"HybridRecommender inicializado con content_weight={content_weight}")
        logger.info(f"Cache de productos: {'habilitada' if product_cache else 'deshabilitada'}")
        logger.info(f"Lógica: Retail API se usa SIEMPRE para usuarios, content_weight se aplica solo para productos específicos")
    
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
        
        # DIAGNÓSTICO: Logging detallado para debug
        logger.info(f"[DEBUG] Parámetros recibidos: user_id='{user_id}', product_id='{product_id}', content_weight={self.content_weight}")
        
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
        
        # CORRECCIÓN: Para recomendaciones de usuario (sin product_id), SIEMPRE usar Retail API
        # Para recomendaciones de producto (con product_id), aplicar optimización content_weight
        should_use_retail_api = not product_id or self.content_weight < 1.0
        logger.info(f"Retail API - content_weight={self.content_weight}, product_id={product_id}, using_retail_api={should_use_retail_api}")
        
        if should_use_retail_api:
            # Intentar obtener recomendaciones de Retail API
            try:
                logger.info(f"[DEBUG] ⚙️ Intentando obtener recomendaciones de Retail API para user_id='{user_id}', product_id='{product_id}'")
                
                retail_recs = await self.retail_recommender.get_recommendations(
                    user_id=user_id,
                    product_id=product_id,
                    n_recommendations=n_recommendations
                )
                
                logger.info(f"[DEBUG] ✅ ÉXITO: Obtenidas {len(retail_recs)} recomendaciones de Retail API para usuario {user_id}")
                
                # Log de las primeras recomendaciones para diagnóstico
                if retail_recs:
                    for i, rec in enumerate(retail_recs[:3]):
                        logger.info(f"[DEBUG] Rec {i+1}: ID={rec.get('id')}, Título={rec.get('title', '')[:30]}..., Score={rec.get('score', 0)}")
                else:
                    logger.warning(f"[DEBUG] ⚠️ Retail API devolvió LISTA VACÍA para user_id='{user_id}', product_id='{product_id}'")
                        
            except Exception as e:
                logger.error(f"[DEBUG] ❌ ERROR al obtener recomendaciones de Retail API: {str(e)}")
                logger.error(f"[DEBUG] Tipo de error: {type(e).__name__}")
                
                # Si es un usuario real (no anonymous), esto es un problema serio
                if user_id != "anonymous":
                    logger.warning(f"[DEBUG] ⚠️ PROBLEMA: Usuario real '{user_id}' no obtuvo recomendaciones personalizadas")
        else:
            logger.info(f"⏭️ Saltando Retail API debido a content_weight=1.0 para recomendaciones de producto")
        
        # Si no hay producto_id y tampoco recomendaciones de Retail API,
        # usar recomendaciones inteligentes de fallback
        if not product_id and not retail_recs:
            logger.info(f"[DEBUG] 🔄 Sin product_id y sin retail_recs. Usando fallback para user_id='{user_id}'")
            return await self._get_fallback_recommendations(user_id, n_recommendations)
            
        # Si hay product_id, combinar ambas recomendaciones
        if product_id:
            logger.info(f"[DEBUG] 🔀 COMBINANDO recomendaciones: content_recs={len(content_recs)}, retail_recs={len(retail_recs)}")
            recommendations = await self._combine_recommendations(
                content_recs,
                retail_recs,
                n_recommendations
            )
        else:
            # Si no hay product_id, usar solo recomendaciones de Retail API
            logger.info(f"[DEBUG] 📶 SOLO RETAIL API: Usando {len(retail_recs)} recomendaciones para user_id='{user_id}'")
            recommendations = retail_recs
        
        # Enriquecer recomendaciones si está disponible el sistema de caché
        if self.product_cache:
            return await self._enrich_recommendations(recommendations, user_id)
        else:
            return recommendations
    
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
        
    async def _enrich_recommendations(self, recommendations: List[Dict], user_id: str = None) -> List[Dict]:
        """
        Enriquece las recomendaciones con datos detallados de productos.
        
        Args:
            recommendations: Lista de recomendaciones básicas
            user_id: ID del usuario (para logging)
            
        Returns:
            Lista de recomendaciones enriquecidas
        """
        if not recommendations:
            return []
            
        logger.info(f"Enriqueciendo {len(recommendations)} recomendaciones para usuario {user_id or 'anonymous'}")
        
        # Verificar si tenemos caché de productos
        if not self.product_cache:
            logger.warning("No hay caché de productos disponible para enriquecer recomendaciones")
            return recommendations
            
        # Extraer IDs de productos
        product_ids = [rec.get("id") for rec in recommendations if rec.get("id")]
        
        # Precargar productos
        try:
            await self.product_cache.preload_products(product_ids)
        except Exception as e:
            logger.error(f"Error al precargar productos: {str(e)}")
        
        enriched_recommendations = []
        
        for rec in recommendations:
            product_id = rec.get("id")
            if not product_id:
                enriched_recommendations.append(rec)
                continue
                
            enriched_rec = rec.copy()
            
            try:
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
                            price = 0.0
                    else:
                        price = product.get("price", 0.0)
                        if isinstance(price, str):
                            try:
                                price = float(price)
                            except (ValueError, TypeError):
                                price = 0.0
                    
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
                    # Si no se encuentra información completa en la caché
                    logger.warning(f"No se pudo obtener información completa para producto ID={product_id} (fuente: {rec.get('source', 'unknown')})")
                    
                    # Intentar buscar directamente en el catálogo local si está disponible
                    local_product = None
                    if self.content_recommender and hasattr(self.content_recommender, 'product_data'):
                        for p in self.content_recommender.product_data:
                            if str(p.get('id', '')) == str(product_id):
                                local_product = p
                                break
                    
                    if local_product:
                        logger.info(f"Producto ID={product_id} encontrado en catálogo local como fallback")
                        # Enriquecer con datos del producto local
                        enriched_rec["title"] = local_product.get("title", rec.get("title", "Producto"))
                        enriched_rec["description"] = local_product.get("body_html", "")
                        
                        # Extraer precio
                        price = 0.0
                        if local_product.get("variants") and len(local_product["variants"]) > 0:
                            try:
                                price = float(local_product["variants"][0].get("price", 0.0))
                            except (ValueError, TypeError):
                                price = 0.0
                        
                        enriched_rec["price"] = price
                        enriched_rec["category"] = local_product.get("product_type", "")
                        
                        # Registrar que se usó el fallback
                        logger.info(f"Se usó fallback de catálogo local para enriquecer producto ID={product_id}")
                    else:
                        # Si todavía no tenemos título válido, intentar con Shopify directamente
                        if (not enriched_rec.get("title") or enriched_rec["title"] == "Producto") and self.shopify_client:
                            try:
                                if hasattr(self.shopify_client, 'get_product'):
                                    shopify_product = self.shopify_client.get_product(product_id)
                                    if shopify_product:
                                        enriched_rec["title"] = shopify_product.get("title", f"Producto {product_id}")
                                        enriched_rec["description"] = shopify_product.get("body_html", "")
                                        if shopify_product.get("variants") and len(shopify_product["variants"]) > 0:
                                            try:
                                                enriched_rec["price"] = float(shopify_product["variants"][0].get("price", 0.0))
                                            except (ValueError, TypeError):
                                                pass
                                        enriched_rec["category"] = shopify_product.get("product_type", "")
                                        logger.info(f"Producto ID={product_id} obtenido directamente de Shopify")
                            except Exception as e:
                                logger.error(f"Error al obtener producto de Shopify como fallback: {str(e)}")
                        
                        # Si aún no tenemos título válido, usar valor predeterminado
                        if not enriched_rec.get("title") or enriched_rec["title"] == "Producto":
                            enriched_rec["title"] = f"Producto {product_id}"
                            
                        # Marcar para diagnóstico
                        enriched_rec["_incomplete_data"] = True
                        
                        logger.warning(f"No se pudo enriquecer producto ID={product_id} (fuente: {rec.get('source', 'unknown')})")
            except Exception as e:
                logger.error(f"Error al enriquecer producto ID={product_id}: {str(e)}")
                # Mantener los datos originales si hay un error
            
            enriched_recommendations.append(enriched_rec)
        
        logger.info(f"Enriquecidas {len(enriched_recommendations)} recomendaciones")
        
        # Registrar estadísticas para monitoreo
        if self.product_cache:
            try:
                cache_stats = self.product_cache.get_stats()
                logger.info(f"Estadísticas de caché: Hit ratio={cache_stats['hit_ratio']:.2f}")
            except Exception as e:
                logger.error(f"Error al obtener estadísticas de caché: {str(e)}")
        
        return enriched_recommendations


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
                product_id = event.get("productId") or event.get("product_id")
                if product_id:
                    interacted_products.add(str(product_id))
        else:
            # Intentar obtener eventos del usuario desde Retail API
            try:
                events = await self.retail_recommender.get_user_events(user_id)
                for event in events:
                    product_id = event.get("productId") or event.get("product_id")
                    if product_id:
                        interacted_products.add(str(product_id))
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
